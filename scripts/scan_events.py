import argparse
import concurrent.futures
import json
import logging
import sys
import time
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

# DB Integration
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo, CompetitionRepo, FixtureRepo, ScanResultRepo
from bet.db.models import Fixture, ScanResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json",
}

# Unified sport mapping for Sofascore
SPORT_MAP = {
    "football": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "hockey": "ice-hockey",
    "volleyball": "volleyball"
}

# Tournament keywords for priority enrichment (R7)
TOURNAMENT_KEYWORDS = [
    "champions league", "europa league", "conference league",
    "world cup", "euro 20", "copa america", "olympics",
    "grand slam", "roland garros", "wimbledon", "us open", "australian open",
    "masters 1000", "atp finals", "wta finals",
    "nba", "nhl", "stanley cup", "playoffs",
    "euroleague", "eurocup",
]

# Protected domestic leagues (R13) — substring matches
PROTECTED_LEAGUES = [
    "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
    "eredivisie", "primeira liga", "süper lig", "jupiler",
    "brasileirão", "brasileirao", "mls", "liga mx", "liga profesional",
    "liga betplay", "chinese super league", "j-league", "j1 league",
    "k league", "saudi pro league", "a-league",
    "indian super league", "egyptian premier",
    "liga acb", "nba", "bbl", "vtb united", "khl",
    "superliga", "v-league", "plusliga",
]

# Per-worker rate limiter for Sofascore API
_rate_lock = threading.Lock()
_last_request_time = 0.0
RATE_LIMIT_SECONDS = 0.35  # slightly above 0.3 for safety

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

from bet.api_clients.unified import UnifiedAPIClient

def fetch_events_for_sport(sport_key: str, date_str: str) -> list:
    client = UnifiedAPIClient()
    logger.info(f"Scanning {sport_key.upper()} events for {date_str}...")
    try:
        events = client.get_fixtures(date_str, sport=sport_key)
        logger.info(f"Found {len(events)} {sport_key.upper()} events.")
        
        normalized = []
        for ev in events:
            normalized.append({
                "id": ev.external_id,
                "sport": ev.sport,
                "tournament": ev.competition_name,
                "country": "Unknown", # Fallback for now if APIFixture doesn't guarantee country
                "home_team": ev.home_team_name,
                "away_team": ev.away_team_name,
                "start_time": ev.kickoff
            })
        return normalized
    except Exception as e:
        logger.error(f"Error fetching {sport_key}: {e}")
        
    return []

# Thread-local storage for per-thread sessions
_thread_local = threading.local()

def _get_thread_session() -> requests.Session:
    """Get or create a thread-local requests.Session."""
    if not hasattr(_thread_local, 'session'):
        _thread_local.session = requests.Session()
        _thread_local.session.headers.update(HEADERS)
    return _thread_local.session


def _rate_limited_get(session: requests.Session, url: str, timeout: int = 10, max_retries: int = 2) -> requests.Response | None:
    """Thread-safe rate-limited GET with exponential backoff on 429."""
    global _last_request_time
    for attempt in range(max_retries + 1):
        # Reserve a time slot inside the lock, sleep OUTSIDE
        with _rate_lock:
            now = time.monotonic()
            wait = RATE_LIMIT_SECONDS - (now - _last_request_time)
            _last_request_time = time.monotonic() + max(0.0, wait)
        if wait > 0:
            time.sleep(wait)
        try:
            r = session.get(url, timeout=timeout)
            if r.status_code == 403:
                logger.warning(f"Forbidden (403) on {url} — not retryable")
                return None
            if r.status_code == 429:
                backoff = (2 ** attempt) * 1.0
                logger.warning(f"Rate limited (429) on {url}, backoff {backoff:.1f}s")
                time.sleep(backoff)
                continue
            return r
        except Exception:
            if attempt < max_retries:
                time.sleep(1.0)
            else:
                return None
    return None


def _compute_enrichment_priority(ev: dict) -> int:
    """Score an event for deep enrichment priority. Higher = enrich first."""
    score = 0
    tournament = (ev.get("tournament") or "").lower()
    sport = ev.get("sport", "")

    # Tournament matches (R7): highest priority
    for kw in TOURNAMENT_KEYWORDS:
        if kw in tournament:
            score += 100
            break

    # Protected domestic leagues (R13)
    for kw in PROTECTED_LEAGUES:
        if kw in tournament:
            score += 80
            break

    # Football and basketball are data-rich on Sofascore — prioritize
    if sport == "football":
        score += 30
    elif sport == "basketball":
        score += 25
    elif sport == "hockey":
        score += 20
    elif sport == "volleyball":
        score += 15
    elif sport == "tennis":
        score += 10  # Tennis has less form/H2H on Sofascore

    return score


def fetch_deep_data(event_id: str) -> tuple:
    """Fetch form, H2H, odds, and statistics for an event using UnifiedAPIClient."""
    from bet.api_clients.unified import UnifiedAPIClient
    client = UnifiedAPIClient()
    
    form_data, h2h_data, odds_data, stats_data = {}, {}, [], {}
    
    # Try fetching with unified client. Usually stats contains all of it or we could directly use
    # sofascore fallback
    try:
        raw_stats = client.sofascore.get_fixture_stats(event_id)
        if raw_stats:
            stats_data = raw_stats.get('stats', {})
    except Exception as e:
        logger.warning(f"Error fetching stats for {event_id}: {e}")

    try:
        form_data = client.sofascore.client.get(f"/api/v1/event/{event_id}/pregame-form") or {}
    except:
        pass
        
    try:
        h2h_data = client.sofascore.client.get(f"/api/v1/event/{event_id}/h2h") or {}
    except:
        pass
        
    try:
        odds_json = client.sofascore.client.get(f"/api/v1/event/{event_id}/odds/1/all")
        if odds_json:
            odds_data = odds_json.get("markets", [])
    except:
        pass

    return form_data, h2h_data, odds_data, stats_data

def _enrich_single_event(ev: dict, session: requests.Session, verbose: bool = False) -> dict:
    """Enrich a single event with deep data. Returns the event dict (mutated)."""
    if not ev.get("id"):
        return ev
    if verbose:
        print(json.dumps({"event": "enriching", "id": ev["id"], "match": f"{ev['home_team']} vs {ev['away_team']}"}))
        
    form, h2h, odds, stats = fetch_deep_data(str(ev["id"]))
    ev["form"] = form
    ev["h2h"] = h2h
    ev["odds"] = odds
    if stats:
        ev["expected_stats"] = stats
    return ev


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument("--sport", help="Optional sport filter")
    parser.add_argument("--verbose", action="store_true", help="Print JSON-line events")
    parser.add_argument("--stats-first", action="store_true", help="Include events without odds")
    parser.add_argument("--skip-deep", action="store_true", help="Skip deep enrichment")
    parser.add_argument("--stop-on-error", action="store_true", help="Halt on first critical error")
    parser.add_argument("--deep-workers", type=int, default=3, help="Concurrent deep enrichment workers (default: 3)")
    parser.add_argument("--deep-limit", type=int, default=0, help="Max events to deep-enrich (0=all)")
    args = parser.parse_args()

    sports_to_scan = [args.sport] if args.sport and args.sport in SPORT_MAP else list(SPORT_MAP.keys())
    all_events = []
    
    verdict = "OK"
    errors = 0
    issues = []
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_sport = {executor.submit(fetch_events_for_sport, sport, args.date): sport for sport in sports_to_scan}
            for future in concurrent.futures.as_completed(future_to_sport):
                sport_events = future.result()
                all_events.extend(sport_events)
    except Exception as e:
        logger.error(f"Error scanning events: {e}")
        errors += 1
        issues.append(str(e))
        verdict = "FAILED"

    by_sport = {}
    for ev in all_events:
        by_sport[ev["sport"]] = by_sport.get(ev["sport"], 0) + 1

    logger.info(f"Discovered {len(all_events)} events across {len(by_sport)} sports: {json.dumps(by_sport)}")

    deep_enriched = 0
    deep_enriched_by_sport = {}
    deep_with_form = 0
    deep_with_h2h = 0
    deep_with_odds = 0
    deep_with_stats = 0
    
    if not args.skip_deep and all_events:
        # Sort events by enrichment priority (highest first)
        for ev in all_events:
            ev["_priority"] = _compute_enrichment_priority(ev)
        all_events.sort(key=lambda e: e["_priority"], reverse=True)

        events_to_enrich = all_events
        if args.deep_limit > 0:
            events_to_enrich = all_events[:args.deep_limit]
            logger.info(f"Deep enrichment limited to top {args.deep_limit} priority events")

        total_to_enrich = len(events_to_enrich)
        logger.info(f"Starting concurrent deep enrichment ({args.deep_workers} workers, {total_to_enrich} events)...")
        
        enriched_count = [0]  # mutable for thread-safe counter
        count_lock = threading.Lock()
        
        def _enrich_and_track(ev):
            _enrich_single_event(ev, None, verbose=args.verbose)
            with count_lock:
                enriched_count[0] += 1
                if enriched_count[0] % 50 == 0:
                    logger.info(f"Deep enrichment progress: {enriched_count[0]}/{total_to_enrich}")
            return ev
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.deep_workers) as executor:
                futures = {executor.submit(_enrich_and_track, ev): ev for ev in events_to_enrich}
                for future in concurrent.futures.as_completed(futures):
                    try:
                        ev = future.result()
                        has_data = False
                        sport = ev.get("sport", "unknown")
                        
                        if ev.get("form"):
                            form = ev["form"]
                            if isinstance(form, dict) and (form.get("homeTeam") or form.get("awayTeam")):
                                deep_with_form += 1
                                has_data = True
                        if ev.get("h2h"):
                            h2h = ev["h2h"]
                            if isinstance(h2h, dict) and h2h.get("teamDuel"):
                                deep_with_h2h += 1
                                has_data = True
                        if ev.get("odds") and len(ev["odds"]) > 0:
                            deep_with_odds += 1
                            has_data = True
                        if ev.get("expected_stats"):
                            deep_with_stats += 1
                            has_data = True
                        
                        if has_data:
                            deep_enriched += 1
                            deep_enriched_by_sport[sport] = deep_enriched_by_sport.get(sport, 0) + 1
                    except Exception as e:
                        errors += 1
                        issues.append(str(e))
        finally:
            # Clean up priority field even if exceptions occur (BUG 9)
            for ev in all_events:
                ev.pop("_priority", None)

        logger.info(f"Deep enrichment complete: {deep_enriched}/{total_to_enrich} events enriched")
        logger.info(f"  Form: {deep_with_form} | H2H: {deep_with_h2h} | Odds: {deep_with_odds} | Stats: {deep_with_stats}")
        logger.info(f"  By sport: {json.dumps(deep_enriched_by_sport)}")

    db_fixtures_written = 0
    db_scan_results = 0

    try:
        with get_db() as db_conn:
            sport_repo = SportRepo(db_conn)
            team_repo = TeamRepo(db_conn)
            comp_repo = CompetitionRepo(db_conn)
            fix_repo = FixtureRepo(db_conn)
            scan_repo = ScanResultRepo(db_conn)
            
            sport_repo.seed_defaults()
            
            scan_results_to_insert = []
            
            for ev in all_events:
                sport_obj = sport_repo.get_by_name(ev["sport"])
                if not sport_obj:
                    continue
                sport_id = sport_obj.id
                
                home_team = team_repo.find_or_create(ev["home_team"], sport_id)
                away_team = team_repo.find_or_create(ev["away_team"], sport_id)
                comp_id = comp_repo.find_or_create(ev["tournament"], sport_id, country=ev["country"])
                
                fix = Fixture(
                    id=None,
                    sport_id=sport_id,
                    competition_id=comp_id,
                    home_team_id=home_team.id,
                    away_team_id=away_team.id,
                    kickoff=ev["start_time"],
                    status='scheduled',
                    external_id=str(ev["id"]) if ev.get("id") else "",
                    source='sofascore-api'
                )
                fix_repo.upsert(fix)
                db_fixtures_written += 1
                
                scan_res = ScanResult(
                    id=None,
                    betting_date=args.date,
                    sport=ev["sport"],
                    source_domain="sofascore.com",
                    event_key=f"{ev['sport']}:{ev['home_team']}:{ev['away_team']}",
                    home_team=ev["home_team"],
                    away_team=ev["away_team"],
                    competition=ev["tournament"],
                    kickoff=ev["start_time"],
                    raw_data=ev,
                    scan_timestamp=_now()
                )
                scan_results_to_insert.append(scan_res)
                
            db_scan_results = scan_repo.bulk_insert(scan_results_to_insert)
            
    except Exception as e:
        logger.error(f"Error persisting to DB: {e}")
        errors += 1
        issues.append(str(e))
        verdict = "FAILED"

    output_file = "betting/data/global_events_api.json"
    if all_events:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(all_events, f, ensure_ascii=False, indent=2)
    else:
        logger.warning("No events scanned — preserving existing output file")
        verdict = "FAILED" if verdict == "OK" else verdict
        issues.append("Zero events scanned — output not written")
        
    summary = {
        "verdict": verdict,
        "events_total": len(all_events),
        "by_sport": by_sport,
        "deep_enriched": deep_enriched,
        "deep_enriched_by_sport": deep_enriched_by_sport,
        "deep_with_form": deep_with_form,
        "deep_with_h2h": deep_with_h2h,
        "deep_with_odds": deep_with_odds,
        "deep_with_stats": deep_with_stats,
        "db_fixtures_written": db_fixtures_written,
        "db_scan_results": db_scan_results,
        "errors": errors,
        "issues": issues
    }
    
    # Always print AGENT_SUMMARY before any exit (BUG 4 fix)
    print(f"AGENT_SUMMARY:{json.dumps(summary)}")
    
    if verdict == "FAILED" and args.stop_on_error:
        sys.exit(2)

if __name__ == "__main__":
    main()