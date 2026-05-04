#!/usr/bin/env python3
"""Orchestrate multi-API stats fetching for discovered fixtures.

Usage:
    python3 scripts/fetch_api_stats.py --date 2026-04-28
    python3 scripts/fetch_api_stats.py --fixtures betting/data/fixtures_2026-04-28.json
    python3 scripts/fetch_api_stats.py --date 2026-04-28 --sports football,basketball
    python3 scripts/fetch_api_stats.py --usage
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Imports from project
sys.path.insert(0, str(Path(__file__).parent))
from api_clients import get_client, RateLimiter, CLIENT_REGISTRY
from api_clients.base_client import APIRateLimitError, APIError
from normalize_stats import NormalizedMatchStats, build_safety_score_input, SPORT_MARKETS
from build_stats_cache import (
    read_cache,
    update_cache,
    create_team_cache_entry,
    slugify,
)

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"

# Fallback chains per sport — ESPN first (free, unlimited, no API key)
# SerpAPI last (250/month limit, supplementary Google search data)
FALLBACK_CHAINS = {
    "football": ["espn-football", "api-football", "football-data-org", "understat", "serpapi"],
    "basketball": ["espn-basketball", "api-basketball", "balldontlie", "serpapi"],
    "hockey": ["espn-hockey", "api-hockey", "serpapi"],
    "tennis": ["espn-tennis", "api-tennis", "serpapi"],
    "volleyball": ["api-volleyball", "serpapi"],
    "handball": ["api-handball", "serpapi"],
    "baseball": ["espn-baseball", "api-baseball", "serpapi"],
    "mma": ["espn-mma", "serpapi"],
}

# Tier 1 sports get enriched first
TIER_1_SPORTS = {"football", "volleyball", "basketball", "tennis"}


def fetch_team_stats(
    client, team_name: str, sport: str, last_n: int = 10, competition: str = ""
) -> list[NormalizedMatchStats]:
    """Fetch last N matches with stats for a team.

    1. Resolve team ID
    2. Get last N finished fixtures
    3. For each fixture, get detailed stats (budget-aware)
    4. Return list of NormalizedMatchStats
    """
    # Resolve team ID (pass competition for ESPN league hint)
    try:
        team_id = client.resolve_team_id(team_name, competition=competition)
    except TypeError:
        # Clients that don't accept competition kwarg
        team_id = client.resolve_team_id(team_name)
    if not team_id:
        print(f"[fetch] Could not resolve team ID for '{team_name}'")
        return []

    # Get last N finished fixtures
    try:
        fixtures = client.get_team_last_fixtures(team_id, last_n=last_n)
    except (APIRateLimitError, APIError) as e:
        print(f"[fetch] Error getting fixtures for '{team_name}': {e}")
        return []

    if not fixtures:
        print(f"[fetch] No recent fixtures found for '{team_name}'")
        return []

    # Fetch detailed stats per fixture (budget-aware: stop on rate limit)
    match_stats = []
    for fixture in fixtures:
        try:
            stats = client.get_fixture_stats(fixture.fixture_id)
        except APIRateLimitError:
            print(f"[fetch] Rate limited — returning {len(match_stats)} partial stats for '{team_name}'")
            break
        except APIError as e:
            print(f"[fetch] Error fetching stats for fixture {fixture.fixture_id}: {e}")
            continue

        if stats:
            # Fill in the date from the fixture metadata
            if not stats.date and fixture.kickoff:
                stats.date = fixture.kickoff[:10]
            match_stats.append(stats)

    return match_stats


def fetch_h2h_stats(
    client, team1_name: str, team2_name: str, sport: str, last_n: int = 10, competition: str = ""
) -> list[NormalizedMatchStats]:
    """Fetch H2H meetings with stats."""
    try:
        team1_id = client.resolve_team_id(team1_name, competition=competition)
        team2_id = client.resolve_team_id(team2_name, competition=competition)
    except TypeError:
        team1_id = client.resolve_team_id(team1_name)
        team2_id = client.resolve_team_id(team2_name)

    if not team1_id or not team2_id:
        print(f"[fetch] Could not resolve team IDs for H2H: '{team1_name}' vs '{team2_name}'")
        return []

    try:
        h2h_fixtures = client.get_h2h(team1_id, team2_id, last_n=last_n)
    except (APIRateLimitError, APIError) as e:
        print(f"[fetch] Error getting H2H fixtures: {e}")
        return []

    if not h2h_fixtures:
        return []

    # Fetch stats for each H2H fixture (budget-aware)
    match_stats = []
    for fixture in h2h_fixtures:
        try:
            stats = client.get_fixture_stats(fixture.fixture_id)
        except APIRateLimitError:
            print(f"[fetch] Rate limited — returning {len(match_stats)} partial H2H stats")
            break
        except APIError:
            continue

        if stats:
            if not stats.date and fixture.kickoff:
                stats.date = fixture.kickoff[:10]
            match_stats.append(stats)

    return match_stats


def _store_in_cache(
    sport: str,
    team_name: str,
    team_matches: list[NormalizedMatchStats],
    api_source: str,
    opponent: str | None = None,
    h2h_matches: list[NormalizedMatchStats] | None = None,
) -> None:
    """Store fetched stats in the stats cache using the extended format."""
    from build_stats_cache import update_from_api

    update_from_api(
        sport=sport,
        team=team_name,
        normalized_matches=team_matches,
        api_source=api_source,
        opponent=opponent,
        h2h_matches=h2h_matches,
    )


def enrich_fixture(fixture: dict, rate_limiter: RateLimiter) -> dict:
    """Enrich a single fixture with stats from the best available API.

    1. Determine sport
    2. Get fallback chain
    3. Try each API in chain
    4. Build safety score input
    5. Store in cache
    6. Return enriched data with status
    """
    sport = fixture.get("sport", "football").lower()
    home_team = fixture.get("home_team", "")
    away_team = fixture.get("away_team", "")
    competition = fixture.get("competition", "")
    fixture_id = fixture.get("fixture_id", "")

    result = {
        "fixture_id": fixture_id,
        "sport": sport,
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "status": "skipped",
        "api_source": None,
        "team_a_matches": 0,
        "team_b_matches": 0,
        "h2h_matches": 0,
        "safety_input_built": False,
    }

    if not home_team or not away_team:
        result["status"] = "failed"
        result["error"] = "Missing team names"
        return result

    chain = FALLBACK_CHAINS.get(sport, [])
    if not chain:
        result["status"] = "skipped"
        result["error"] = f"No API coverage for sport: {sport}"
        return result

    for api_name in chain:
        if api_name not in CLIENT_REGISTRY:
            continue

        if not rate_limiter.can_request(api_name):
            continue

        try:
            client = get_client(api_name, rate_limiter)
        except (ValueError, Exception) as e:
            print(f"[enrich] Error creating client {api_name}: {e}")
            continue

        # Check if the client is available (has API key or doesn't need one)
        if not client.is_available():
            continue

        # Fetch team A stats
        team_a_stats = fetch_team_stats(client, home_team, sport, competition=competition)

        # Fetch team B stats
        team_b_stats = fetch_team_stats(client, away_team, sport, competition=competition)

        # Fetch H2H
        h2h_stats = fetch_h2h_stats(client, home_team, away_team, sport, competition=competition)

        # Check if we got anything useful
        if not team_a_stats and not team_b_stats:
            print(f"[enrich] No stats from {api_name} for {home_team} vs {away_team}")
            continue

        # Store in cache
        if team_a_stats:
            _store_in_cache(
                sport, home_team, team_a_stats, api_name,
                opponent=away_team, h2h_matches=h2h_stats,
            )
        if team_b_stats:
            _store_in_cache(
                sport, away_team, team_b_stats, api_name,
                opponent=home_team, h2h_matches=h2h_stats,
            )

        result["api_source"] = api_name
        result["team_a_matches"] = len(team_a_stats)
        result["team_b_matches"] = len(team_b_stats)
        result["h2h_matches"] = len(h2h_stats)

        # Build safety score input
        safety_input = build_safety_score_input(
            sport=sport,
            team_a=home_team,
            team_b=away_team,
            competition=competition,
            team_a_matches=team_a_stats,
            team_b_matches=team_b_stats,
            h2h_matches=h2h_stats,
            source=api_name,
        )

        if safety_input:
            result["status"] = "enriched"
            result["safety_input_built"] = True
            result["markets_built"] = len(safety_input.get("markets", []))
        elif team_a_stats or team_b_stats:
            result["status"] = "partial"
        else:
            result["status"] = "failed"

        # Success (full or partial) — don't try next API in chain
        break

    return result


def fetch_stats_for_date(
    date: str,
    sports: list[str] | None = None,
    rate_limiter: RateLimiter | None = None,
) -> dict:
    """Main entry: fetch stats for all fixtures on a date.

    1. Load fixtures from fixtures_{date}.json (or discover)
    2. Filter by sports if specified
    3. Sort by enrichment priority (Tier 1 sports first)
    4. For each fixture, enrich with stats
    5. Save summary to api_stats_summary_{date}.json
    6. Return summary dict
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    fixtures_file = DATA_DIR / f"fixtures_{date}.json"

    if fixtures_file.exists():
        try:
            fixtures_data = json.loads(fixtures_file.read_text(encoding="utf-8"))
            fixtures = fixtures_data.get("fixtures", [])
            print(f"[fetch_stats] Loaded {len(fixtures)} fixtures from {fixtures_file}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"[fetch_stats] Error reading {fixtures_file}: {e}")
            fixtures = []
    else:
        # Try to discover fixtures
        print(f"[fetch_stats] No fixtures file found, running discovery for {date}")
        try:
            from discover_fixtures import discover_all_fixtures
            discovered = discover_all_fixtures(date, sports)
            fixtures = [
                asdict(f) if hasattr(f, "__dataclass_fields__") else f
                for f in discovered
            ]
        except Exception as e:
            print(f"[fetch_stats] Discovery failed: {e}")
            fixtures = []

    # Filter by sports
    if sports:
        sports_lower = {s.lower() for s in sports}
        fixtures = [
            f for f in fixtures
            if f.get("sport", "").lower() in sports_lower
        ]

    # Sort: Tier 1 sports first, then alphabetically
    def sort_key(f):
        sport = f.get("sport", "").lower()
        tier = 0 if sport in TIER_1_SPORTS else 1
        return (tier, sport, f.get("competition", ""), f.get("home_team", ""))

    fixtures.sort(key=sort_key)

    # Group fixtures by sport for parallel enrichment
    sport_groups: dict[str, list[dict]] = {}
    for fixture in fixtures:
        sport = fixture.get("sport", "").lower()
        sport_groups.setdefault(sport, []).append(fixture)

    print(f"[fetch_stats] Enriching {len(fixtures)} fixtures across {len(sport_groups)} sports in parallel")

    results = []
    counts = {"enriched": 0, "partial": 0, "failed": 0, "skipped": 0}
    counts_lock = threading.Lock()

    if not sport_groups:
        print("[fetch_stats] No fixtures to enrich")
        return {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_fixtures": 0,
            "counts": counts,
            "results": [],
        }

    def _enrich_sport_group(sport: str, sport_fixtures: list[dict]) -> list[dict]:
        """Enrich all fixtures for a single sport."""
        sport_results = []
        for fixture in sport_fixtures:
            try:
                result = enrich_fixture(fixture, rate_limiter)
                sport_results.append(result)
            except Exception as e:
                home = fixture.get('home_team', '?')
                away = fixture.get('away_team', '?')
                print(f"[fetch_stats] Error enriching {home} vs {away}: {e}")
                sport_results.append({
                    "fixture_id": fixture.get("fixture_id", ""),
                    "sport": sport,
                    "home_team": home,
                    "away_team": away,
                    "status": "failed",
                    "error": str(e),
                })
        return sport_results

    max_workers = min(len(sport_groups), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sport = {
            executor.submit(_enrich_sport_group, sport, sport_fixtures): sport
            for sport, sport_fixtures in sport_groups.items()
        }
        for future in as_completed(future_to_sport):
            sport = future_to_sport[future]
            try:
                sport_results = future.result()
                results.extend(sport_results)
                for r in sport_results:
                    status = r.get("status", "skipped")
                    with counts_lock:
                        counts[status] = counts.get(status, 0) + 1
                print(f"[fetch_stats] {sport}: {len(sport_results)} fixtures processed")
            except Exception as e:
                print(f"[fetch_stats] ERROR enriching {sport}: {e}")
                with counts_lock:
                    counts["failed"] = counts.get("failed", 0) + len(sport_groups.get(sport, []))

    # Build summary
    summary = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(fixtures),
        "counts": counts,
        "results": results,
    }

    # Save summary
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DATA_DIR / f"api_stats_summary_{date}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[fetch_stats] Summary saved to {summary_path}")
    print(f"[fetch_stats] Results: {counts}")

    return summary


def show_usage(rate_limiter: RateLimiter):
    """Print API usage summary."""
    summary = rate_limiter.get_usage_summary()
    print("\n=== API Usage Summary ===")
    for api, info in summary.items():
        print(f"  {api}: {info['used']}/{info['limit']} (remaining: {info['remaining']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch stats from APIs")
    parser.add_argument("--date", help="Date YYYY-MM-DD")
    parser.add_argument("--fixtures", help="Path to fixtures JSON file")
    parser.add_argument("--sports", help="Comma-separated sports filter")
    parser.add_argument("--usage", action="store_true", help="Show API usage summary")
    args = parser.parse_args()

    rate_limiter = RateLimiter()

    if args.usage:
        show_usage(rate_limiter)
        sys.exit(0)

    if not args.date and not args.fixtures:
        # Default to today
        args.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sports = args.sports.split(",") if args.sports else None

    if args.fixtures:
        fixtures_path = Path(args.fixtures)
        if not fixtures_path.exists():
            print(f"Error: fixtures file not found: {fixtures_path}")
            sys.exit(1)
        fixtures_data = json.loads(fixtures_path.read_text(encoding="utf-8"))
        fixtures = fixtures_data.get("fixtures", fixtures_data if isinstance(fixtures_data, list) else [])
        if sports:
            sports_lower = {s.lower() for s in sports}
            fixtures = [f for f in fixtures if f.get("sport", "").lower() in sports_lower]

        # Enrich from fixture list
        results = []
        for fixture in fixtures:
            result = enrich_fixture(fixture, rate_limiter)
            results.append(result)
            print(f"  {result['home_team']} vs {result['away_team']}: {result['status']}")

        # Determine date for summary filename
        date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_fixtures": len(fixtures),
            "results": results,
        }
        summary_path = DATA_DIR / f"api_stats_summary_{date}.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nSummary saved to {summary_path}")
    else:
        result = fetch_stats_for_date(args.date, sports, rate_limiter)

    show_usage(rate_limiter)
