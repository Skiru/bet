"""Multi-API fixture discovery — finds ALL matches on a date across all sports.

Usage:
    python3 scripts/discover_fixtures.py --date 2026-04-28
    python3 scripts/discover_fixtures.py --date 2026-04-28 --sports football,basketball
"""

import argparse
import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# Add scripts to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

# --- DB support (optional — falls back gracefully) ---
try:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SportRepo, TeamRepo, CompetitionRepo, FixtureRepo
    from bet.db.models import Fixture as DBFixture
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

from normalize_stats import NormalizedFixture
from api_clients import get_client, CLIENT_REGISTRY
from api_clients.rate_limiter import RateLimiter


from utils import normalize_team_name


def deduplicate_fixtures(fixtures: list) -> list:
    """Deduplicate by normalized team names + date."""
    seen = set()
    unique = []
    for f in fixtures:
        if isinstance(f, NormalizedFixture):
            home = normalize_team_name(f.home_team)
            away = normalize_team_name(f.away_team)
            date_part = f.kickoff[:10] if f.kickoff else ""
        elif isinstance(f, dict):
            home = normalize_team_name(f.get("home_team", ""))
            away = normalize_team_name(f.get("away_team", ""))
            date_part = f.get("kickoff", "")[:10]
        else:
            unique.append(f)
            continue

        key = f"{min(home, away)}|{max(home, away)}|{date_part}"
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


def merge_fixtures(api_fixtures: list, scan_fixtures: list) -> list:
    """Merge API-discovered fixtures with Playwright scan results.

    API fixtures take priority. Scan fixtures are added only if
    no matching API fixture exists.
    """
    merged = list(api_fixtures)
    merged.extend(scan_fixtures)
    return deduplicate_fixtures(merged)


def _load_scan_summary(date: str) -> list:
    """Load fixtures from Playwright scan_summary.json if it exists.

    Includes items WITH matching date AND items WITHOUT a date field
    (since the scan runs daily, dateless items are from today's scrape).
    Only includes items with a valid time field as a proxy for being a fixture.
    """
    scan_file = PROJECT_ROOT / "betting" / "data" / "scan_summary.json"
    if not scan_file.exists():
        return []

    try:
        data = json.loads(scan_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    # scan_summary.json format is {url: [items]} — flatten all URL arrays
    raw_events = []
    if isinstance(data, list):
        raw_events = data
    elif isinstance(data, dict):
        # Actual format from scan_events.py: {url_string: [event_dicts]}
        if data.get("events"):
            raw_events = data["events"]
        else:
            # Flatten all URL-keyed arrays
            for key, value in data.items():
                if isinstance(value, list):
                    raw_events.extend(value)

    fixtures = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue

        event_date = event.get("date", "")
        event_time = event.get("time", "")

        # Include items that either:
        # 1. Match the target date explicitly
        # 2. Have no date but DO have a time field (likely today's fixture from daily scan)
        if event_date:
            if date and not event_date.startswith(date):
                continue
        else:
            # No date field — only include if there's a time (indicates fixture, not stats)
            if not event_time:
                continue

        home = event.get("home", event.get("home_team", ""))
        away = event.get("away", event.get("away_team", ""))
        # Basic validity checks
        if not home or not away or len(home) < 3 or len(away) < 3:
            continue
        if len(home) > 60 or len(away) > 60:
            continue

        sport = event.get("sport", "football").lower()
        fixture = NormalizedFixture(
            fixture_id=event.get("id", event.get("event_id", "")),
            source="playwright-scan",
            sport=sport,
            competition=event.get("league", event.get("competition", "")),
            home_team=home,
            away_team=away,
            kickoff=event_date or event_time,
            status="scheduled",
        )
        fixtures.append(fixture)

    return fixtures


def discover_all_fixtures(
    date: str,
    sports: list[str] | None = None,
    include_playwright: bool = True,
) -> list:
    """Query all available APIs for fixtures on the date.

    Args:
        date: Date in YYYY-MM-DD format
        sports: Filter to specific sports (e.g., ["football", "basketball"])
        include_playwright: Whether to merge with scan_summary.json

    Returns:
        List of NormalizedFixture objects
    """
    rate_limiter = RateLimiter()
    all_fixtures = []

    # Football sources
    if not sports or "football" in sports:
        # Primary: API-Football
        if "api-football" in CLIENT_REGISTRY:
            try:
                client = get_client("api-football", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] api-football: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] api-football error: {e}")

        # Fallback: Football-Data.org
        if "football-data-org" in CLIENT_REGISTRY:
            try:
                client = get_client("football-data-org", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] football-data-org: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] football-data-org error: {e}")

    # Basketball sources
    if not sports or "basketball" in sports:
        # Primary: API-Basketball
        if "api-basketball" in CLIENT_REGISTRY:
            try:
                client = get_client("api-basketball", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] api-basketball: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] api-basketball error: {e}")

        # Supplementary: BallDontLie (NBA only)
        if "balldontlie" in CLIENT_REGISTRY:
            try:
                client = get_client("balldontlie", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] balldontlie: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] balldontlie error: {e}")

    # Hockey sources
    if not sports or "hockey" in sports:
        if "api-hockey" in CLIENT_REGISTRY:
            try:
                client = get_client("api-hockey", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] api-hockey: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] api-hockey error: {e}")

    # Tennis sources
    if not sports or "tennis" in sports:
        if "api-tennis" in CLIENT_REGISTRY:
            try:
                client = get_client("api-tennis", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] api-tennis: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] api-tennis error: {e}")

    # Volleyball sources
    if not sports or "volleyball" in sports:
        if "api-volleyball" in CLIENT_REGISTRY:
            try:
                client = get_client("api-volleyball", rate_limiter)
                fixtures = client.get_fixtures(date)
                all_fixtures.extend(fixtures)
                print(f"[discover] api-volleyball: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] api-volleyball error: {e}")

    # TheSportsDB fallback — covers sports without a dedicated API
    covered_sports = set()
    if not sports or "football" in sports:
        covered_sports.add("football")
    if not sports or "basketball" in sports:
        covered_sports.add("basketball")
    if not sports or "hockey" in sports:
        covered_sports.add("hockey")
    if not sports or "tennis" in sports:
        covered_sports.add("tennis")
    if not sports or "volleyball" in sports:
        covered_sports.add("volleyball")

    uncovered_sports = set(sports or []) - covered_sports if sports else set()
    if uncovered_sports or not sports:
        if "thesportsdb" in CLIENT_REGISTRY:
            try:
                client = get_client("thesportsdb", rate_limiter)
                fixtures = client.get_fixtures(date)
                if sports:
                    fixtures = [f for f in fixtures if f.sport in sports]
                all_fixtures.extend(fixtures)
                print(f"[discover] thesportsdb: {len(fixtures)} fixtures")
            except Exception as e:
                print(f"[discover] thesportsdb error: {e}")

    # Merge with Playwright scan results
    scan_fixtures = []
    if include_playwright:
        scan_fixtures = _load_scan_summary(date)
        if scan_fixtures:
            print(f"[discover] playwright-scan: {len(scan_fixtures)} events")

    merged = merge_fixtures(all_fixtures, scan_fixtures)
    print(f"[discover] Total after dedup: {len(merged)} fixtures")

    return merged


def main():
    parser = argparse.ArgumentParser(description="Discover fixtures across APIs")
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--sports", help="Comma-separated sports filter")
    parser.add_argument(
        "--no-playwright",
        action="store_true",
        help="Skip Playwright scan_summary.json merge",
    )
    args = parser.parse_args()

    sports = args.sports.split(",") if args.sports else None
    fixtures = discover_all_fixtures(
        args.date, sports, include_playwright=not args.no_playwright
    )

    # Save output
    output_dir = PROJECT_ROOT / "betting" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"fixtures_{args.date}.json"

    output_data = {
        "date": args.date,
        "fixtures": [
            asdict(f) if hasattr(f, "__dataclass_fields__") else f for f in fixtures
        ],
        "count": len(fixtures),
    }
    output_path.write_text(
        json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[discover] Saved {len(fixtures)} fixtures to {output_path}")

    # --- DB persistence (dual-write) ---
    _persist_fixtures_to_db(fixtures, args.date)


def _persist_fixtures_to_db(fixtures: list, date: str) -> None:
    """Write discovered fixtures to SQLite DB alongside JSON."""
    if not _HAS_DB:
        return

    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            comp_repo = CompetitionRepo(conn)
            fixture_repo = FixtureRepo(conn)

            now_ts = datetime.now(timezone.utc).isoformat()
            db_fixtures = []

            # In-memory caches to avoid repeated DB lookups for same team/comp
            _sport_cache: dict[str, object] = {}
            _team_cache: dict[tuple[str, int], object] = {}
            _comp_cache: dict[tuple[str, int], int] = {}

            for f in fixtures:
                # Extract fields from NormalizedFixture or dict
                if hasattr(f, "__dataclass_fields__"):
                    sport_name = f.sport.lower()
                    home_team = f.home_team
                    away_team = f.away_team
                    competition = f.competition
                    kickoff = f.kickoff
                    external_id = f.fixture_id
                    source = f.source
                    status = f.status
                else:
                    sport_name = f.get("sport", "football").lower()
                    home_team = f.get("home_team", "")
                    away_team = f.get("away_team", "")
                    competition = f.get("competition", "")
                    kickoff = f.get("kickoff", "")
                    external_id = f.get("fixture_id", "")
                    source = f.get("source", "")
                    status = f.get("status", "scheduled")

                if not home_team or not away_team:
                    continue

                # Resolve sport (cached)
                if sport_name not in _sport_cache:
                    _sport_cache[sport_name] = sport_repo.get_by_name(sport_name)
                sport_obj = _sport_cache[sport_name]
                if not sport_obj:
                    continue

                # Resolve teams (cached)
                home_key = (home_team, sport_obj.id)
                if home_key not in _team_cache:
                    _team_cache[home_key] = team_repo.find_or_create(home_team, sport_obj.id)
                home = _team_cache[home_key]

                away_key = (away_team, sport_obj.id)
                if away_key not in _team_cache:
                    _team_cache[away_key] = team_repo.find_or_create(away_team, sport_obj.id)
                away = _team_cache[away_key]

                # Resolve competition (cached)
                comp_id = None
                if competition:
                    comp_key = (competition, sport_obj.id)
                    if comp_key not in _comp_cache:
                        _comp_cache[comp_key] = comp_repo.find_or_create(
                            competition, sport_obj.id
                        )
                    comp_id = _comp_cache[comp_key]

                db_fixtures.append(DBFixture(
                    id=None,
                    sport_id=sport_obj.id,
                    competition_id=comp_id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff=kickoff or f"{date}T00:00:00",
                    status=status or "scheduled",
                    external_id=str(external_id) if external_id else "",
                    source=source or "discover_fixtures",
                    fetched_at=now_ts,
                ))

            if db_fixtures:
                ids = fixture_repo.bulk_upsert(db_fixtures)
                print(f"[discover] DB: persisted {len(ids)} fixtures")
    except Exception as e:
        print(f"[discover] DB persistence error (non-fatal): {e}")


if __name__ == "__main__":
    main()
