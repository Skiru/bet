#!/usr/bin/env python3
"""Deep verification of volleyball adapter output + DB persistence."""
import sys, json, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import date
import requests

TODAY = date.today().isoformat()
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

def test_sofascore():
    """Test Sofascore volleyball adapter — check match_url field."""
    print("\n" + "="*60)
    print("SOFASCORE VOLLEYBALL")
    print("="*60)
    from adapters.sofascore_adapter import parse
    url = f"https://api.sofascore.com/api/v1/sport/volleyball/scheduled-events/{TODAY}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    results = parse(resp.text, url)
    print(f"Events: {len(results)}")
    for r in results[:3]:
        print(f"  {r.get('home')} vs {r.get('away')}")
        print(f"    sport={r.get('sport')}, league={r.get('league')}")
        print(f"    match_url={r.get('match_url', 'MISSING')}")
        print(f"    sofascore_id={r.get('sofascore_id', 'MISSING')}")
        print(f"    time={r.get('time')}")
    # Check match_url present
    with_url = sum(1 for r in results if r.get("match_url"))
    print(f"\n  match_url coverage: {with_url}/{len(results)} ({100*with_url//max(1,len(results))}%)")
    return results

def test_flashscore():
    """Test Flashscore volleyball adapter — check volleyball stats extraction."""
    print("\n" + "="*60)
    print("FLASHSCORE VOLLEYBALL")
    print("="*60)
    from adapters.flashscore_adapter import parse
    url = "https://www.flashscore.com/volleyball/"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    results = parse(resp.text, url)
    print(f"Events: {len(results)}")
    for r in results[:3]:
        print(f"  {r.get('home')} vs {r.get('away')}")
        print(f"    sport={r.get('sport')}, league={r.get('league')}")
        print(f"    match_id={r.get('match_id', 'MISSING')}")
        ps = r.get("period_scores")
        print(f"    period_scores={ps}")
        vb = r.get("volleyball")
        if vb:
            print(f"    volleyball_stats={vb}")
        else:
            print(f"    volleyball_stats=NOT_PRESENT (expected for scheduled matches)")
    return results

def test_betexplorer():
    """Test BetExplorer volleyball adapter — basic events."""
    print("\n" + "="*60)
    print("BETEXPLORER VOLLEYBALL")
    print("="*60)
    from adapters.betexplorer_adapter import parse
    url = "https://www.betexplorer.com/volleyball/"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    results = parse(resp.text, url)
    print(f"Events: {len(results)}")
    for r in results[:3]:
        print(f"  {r.get('home')} vs {r.get('away')}")
        print(f"    time={r.get('time')}, league={r.get('league')}")
        print(f"    odds={r.get('odds')}")
    return results

def test_scores24():
    """Test Scores24 volleyball — needs Playwright but test parse logic."""
    print("\n" + "="*60)
    print("SCORES24 VOLLEYBALL (HTTP — expects 0 events, JS-heavy)")
    print("="*60)
    from adapters.scores24_adapter import parse, _extract_volleyball_stats
    # Test the volleyball stat extraction function directly
    # Scores24 uses separate lines: label on one line, value on next
    test_lines = [
        "Aces",
        "5.2",
        "3.1",
        "Blocks",
        "3.1",
        "2.8",
        "Kills",
        "12.8",
        "11.5",
        "Digs",
        "8.4",
        "7.2",
        "Assists",
        "11.2",
        "10.8",
        "Errors",
        "7.3",
        "6.1",
        "Attack",
        "48.5",
        "45.2",
        "Hitting",
        ".285",
        ".262",
        "Service Errors",
        "2.1",
        "1.9",
        "Total Points",
        "78",
        "72",
    ]
    stats = _extract_volleyball_stats(test_lines)
    print(f"  Volleyball stat extraction test:")
    for k, v in stats.items():
        print(f"    {k} = {v}")
    expected = {"aces", "blocks", "kills", "digs", "assists", "errors", "attack_pct", "hitting_pct", "service_errors", "total_points"}
    found = set(stats.keys())
    missing = expected - found
    if missing:
        print(f"  ⚠️ MISSING keys: {missing}")
    else:
        print(f"  ✅ All {len(expected)} volleyball stat keys extracted")
    return stats

def test_normalization():
    """Test that volleyball fields survive normalization."""
    print("\n" + "="*60)
    print("NORMALIZATION TEST")
    print("="*60)
    from adapters import normalize_adapter_output
    event = {
        "home": "Team A",
        "away": "Team B",
        "sport": "volleyball",
        "source_type": "sofascore",
        "match_url": "https://api.sofascore.com/api/v1/event/123/statistics",
        "sofascore_id": "123",
        "volleyball": {
            "sets_won_home": 3,
            "sets_won_away": 1,
            "total_points": 178,
            "kills": 45,
            "aces": 8,
        }
    }
    normalized = normalize_adapter_output(event, "sofascore")
    vb = normalized.get("volleyball", {})
    print(f"  volleyball.sets_won_home = {vb.get('sets_won_home')}")
    print(f"  volleyball.sets_won_away = {vb.get('sets_won_away')}")
    print(f"  volleyball.total_points = {vb.get('total_points')}")
    print(f"  volleyball.kills = {vb.get('kills')}")
    print(f"  volleyball.aces = {vb.get('aces')}")
    
    all_ok = (vb.get("sets_won_home") == 3 and 
              vb.get("sets_won_away") == 1 and 
              vb.get("total_points") == 178)
    print(f"  {'✅' if all_ok else '❌'} Volleyball fields preserved through normalization")
    return normalized

def test_db_persistence():
    """Test that volleyball data can be written/read from DB."""
    print("\n" + "="*60)
    print("DB PERSISTENCE TEST")
    print("="*60)
    from bet.db.connection import get_db
    with get_db() as db:
        cur = db.cursor()
        
        # Check scan_results table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_results'")
        if not cur.fetchone():
            print("  ⚠️ scan_results table does not exist — first scan needed")
            return
        
        # Check for any volleyball data
        cur.execute("SELECT COUNT(*) FROM scan_results WHERE sport='volleyball'")
        count = cur.fetchone()[0]
        print(f"  Volleyball entries in scan_results: {count}")
        
        if count > 0:
            cur.execute("SELECT home, away, league, source_type, raw_data FROM scan_results WHERE sport='volleyball' ORDER BY created_at DESC LIMIT 3")
            for row in cur.fetchall():
                home, away, league, source, raw = row
                print(f"  {home} vs {away} | {league} | {source}")
                if raw:
                    try:
                        raw_dict = json.loads(raw)
                        vb = raw_dict.get("volleyball", {})
                        if any(v is not None for v in vb.values()):
                            print(f"    volleyball stats: {vb}")
                        else:
                            print(f"    volleyball stats: all None (scheduled match)")
                    except json.JSONDecodeError:
                        print(f"    raw_data not JSON parseable")
        else:
            print("  No volleyball data in DB yet — need to run a scan first")
        
        # Check scan_results schema has raw_data column
        cur.execute("PRAGMA table_info(scan_results)")
        columns = [r[1] for r in cur.fetchall()]
        print(f"\n  scan_results columns: {', '.join(columns)}")
        has_raw = "raw_data" in columns
        print(f"  {'✅' if has_raw else '❌'} raw_data column present (stores volleyball stats)")

def test_espn_client():
    """Test ESPN volleyball client registration."""
    print("\n" + "="*60)
    print("ESPN VOLLEYBALL CLIENT")
    print("="*60)
    from bet.api_clients import CLIENT_REGISTRY, API_ESPN
    vb_key = API_ESPN.get("volleyball")
    print(f"  API_ESPN['volleyball'] = {vb_key}")
    client_exists = vb_key in CLIENT_REGISTRY
    print(f"  {'✅' if client_exists else '❌'} Client registered in CLIENT_REGISTRY")
    if client_exists:
        client = CLIENT_REGISTRY[vb_key]()
        print(f"  Client type: {type(client).__name__}")
        print(f"  Base URL check: {'volleyball' in str(getattr(client, 'sport', '')) or 'fivb' in str(getattr(client, 'league', ''))}")

if __name__ == "__main__":
    test_sofascore()
    test_flashscore()
    test_betexplorer()
    test_scores24()
    test_normalization()
    test_db_persistence()
    test_espn_client()
    print("\n" + "="*60)
    print("DEEP VOLLEYBALL VERIFICATION COMPLETE")
    print("="*60)
