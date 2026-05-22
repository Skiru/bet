#!/usr/bin/env python3
"""Live test: Bovada/Bodog public JSON feed — all sports discovery.

Public endpoint: https://www.bovada.lv/services/sports/event/v2/events/A/description/{sport}/{league}
No API key. No auth. American + Decimal + Fractional odds. Player props.
"""

import json
import time
from datetime import datetime, timezone

import requests

BASE = "https://www.bovada.lv/services/sports/event/v2/events/A/description"

# Known sport/league paths to test
ENDPOINTS = {
    # US Sports
    "basketball/nba": "NBA",
    "basketball/wnba": "WNBA",
    "basketball/ncaab": "NCAA Basketball",
    # Hockey
    "hockey/nhl": "NHL",
    # Football (soccer)
    "soccer/uefa-champions-league": "UEFA Champions League",
    "soccer/england-premier-league": "EPL",
    "soccer/spain-la-liga": "La Liga",
    "soccer/germany-bundesliga": "Bundesliga",
    "soccer/italy-serie-a": "Serie A",
    "soccer/france-ligue-1": "Ligue 1",
    "soccer/usa-major-league-soccer": "MLS",
    "soccer/copa-america": "Copa America",
    "soccer/world-cup": "World Cup",
    "soccer/poland-ekstraklasa": "Ekstraklasa",
    # Tennis
    "tennis/atp": "ATP",
    "tennis/wta": "WTA",
    "tennis/roland-garros": "Roland Garros",
    # American Football
    "football/nfl": "NFL",
    # Baseball
    "baseball/mlb": "MLB",
    # Other
    "hockey/international": "Intl Hockey",
    "volleyball": "Volleyball",
    "handball": "Handball",
    "table-tennis": "Table Tennis",
    "esports": "Esports",
    "mma/ufc": "UFC",
    "boxing": "Boxing",
}


def test_endpoint(path: str, label: str) -> dict | None:
    """Test a single Bovada endpoint."""
    url = f"{BASE}/{path}"
    try:
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        })
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                # Count events
                events = []
                for group in data:
                    events.extend(group.get("events", []))
                return {"status": "OK", "events": len(events), "data": data}
            elif isinstance(data, list) and len(data) == 0:
                return {"status": "EMPTY", "events": 0}
            else:
                return {"status": "UNEXPECTED", "events": 0}
        else:
            return {"status": f"HTTP_{r.status_code}", "events": 0}
    except Exception as e:
        return {"status": f"ERROR: {e}", "events": 0}


def analyze_markets(data: list) -> dict:
    """Analyze available markets in a response."""
    market_types = set()
    total_markets = 0
    total_outcomes = 0
    has_player_props = False
    has_team_totals = False
    has_live = False
    
    for group in data:
        for event in group.get("events", []):
            if event.get("live", False):
                has_live = True
            for dg in event.get("displayGroups", []):
                for market in dg.get("markets", []):
                    total_markets += 1
                    desc = market.get("description", "")
                    key = market.get("key", "")
                    market_types.add(dg.get("description", "unknown"))
                    total_outcomes += len(market.get("outcomes", []))
                    if "Player" in desc or "O/U -" in desc:
                        has_player_props = True
                    if "Team" in desc and "Total" in desc:
                        has_team_totals = True
    
    return {
        "market_groups": sorted(market_types),
        "total_markets": total_markets,
        "total_outcomes": total_outcomes,
        "has_player_props": has_player_props,
        "has_team_totals": has_team_totals,
        "has_live": has_live,
    }


def main():
    print("BOVADA PUBLIC JSON FEED — FULL SPORTS SCAN")
    print("=" * 60)
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Base: {BASE}")
    print()

    results = {}
    
    for path, label in ENDPOINTS.items():
        result = test_endpoint(path, label)
        status = result["status"]
        events = result["events"]
        
        if status == "OK":
            analysis = analyze_markets(result["data"])
            print(f"  ✓ {label:30s} | {events:3d} events | {analysis['total_markets']:5d} markets | {analysis['total_outcomes']:6d} outcomes | props={analysis['has_player_props']} | live={analysis['has_live']}")
            results[path] = {"label": label, "events": events, **analysis}
        else:
            print(f"  ✗ {label:30s} | {status}")
            results[path] = {"label": label, "events": 0, "status": status}
        
        time.sleep(0.3)  # Be respectful

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    working = {k: v for k, v in results.items() if v.get("events", 0) > 0}
    print(f"\nWorking endpoints: {len(working)}/{len(ENDPOINTS)}")
    
    print("\n--- PIPELINE RELEVANCE (5 sports) ---")
    relevance = {
        "Football (Soccer)": [k for k in working if "soccer" in k],
        "Basketball": [k for k in working if "basketball" in k],
        "Hockey": [k for k in working if "hockey" in k],
        "Tennis": [k for k in working if "tennis" in k],
        "Volleyball": [k for k in working if "volleyball" in k],
    }
    
    for sport, endpoints in relevance.items():
        if endpoints:
            total_events = sum(results[e]["events"] for e in endpoints)
            total_markets = sum(results[e].get("total_markets", 0) for e in endpoints)
            has_props = any(results[e].get("has_player_props", False) for e in endpoints)
            print(f"  {sport:20s}: {len(endpoints)} leagues, {total_events} events, {total_markets} markets, props={has_props}")
        else:
            print(f"  {sport:20s}: ✗ NOT FOUND")
    
    # Market depth example for best sport
    if working:
        best = max(working.items(), key=lambda x: x[1].get("total_markets", 0))
        print(f"\n--- DEEPEST MARKET ({best[1]['label']}) ---")
        print(f"  Market groups: {best[1].get('market_groups', [])[:15]}")

    print("\n--- VALUE PROPOSITION vs CURRENT PIPELINE ---")
    print("  + FREE (no API key, no credits, no rate limits documented)")
    print("  + American + Decimal + Fractional odds in SAME response")
    print("  + Player props depth (every player, multiple lines)")
    print("  + Period/Quarter/Half markets")
    print("  + SGP availability flags")
    print("  + Competitive sharp-adjacent odds (Bovada = high-volume book)")
    print("  + Alternative spreads/totals in single call")
    print("  - US-focused book (may not have all EU leagues)")
    print("  - No Betclic comparison directly (but great cross-reference)")
    print("  - May block non-US IPs or add Cloudflare challenges")


if __name__ == "__main__":
    main()
