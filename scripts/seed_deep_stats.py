#!/usr/bin/env python3
"""Live data seeder — fetches real data from all new deep-stats API clients.

Runs each client against live APIs and seeds the stats_cache with real data
for use in the betting pipeline. Reports findings per sport.

Usage:
    PYTHONPATH=src:. python3 scripts/seed_deep_stats.py
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.api_clients.rate_limiter import RateLimiter
from scripts.api_clients.sofascore_darts import SofascoreDartsClient
from scripts.api_clients.snooker_org import SnookerOrgClient
from scripts.api_clients.opendota import OpenDotaClient
from scripts.api_clients.ittf_client import ITTFClient


def seed_darts(rate_limiter: RateLimiter) -> dict:
    """Seed darts data: fixtures + match stats for recent completed matches."""
    print("\n" + "=" * 60)
    print("🎯 DARTS — Sofascore API")
    print("=" * 60)

    client = SofascoreDartsClient(rate_limiter=rate_limiter)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = {"fixtures": 0, "with_stats": 0, "stat_samples": []}

    # Get today's fixtures
    fixtures = client.get_fixtures(today)
    results["fixtures"] = len(fixtures)
    print(f"  Fixtures today: {len(fixtures)}")

    # Get stats for finished matches
    finished = [f for f in fixtures if f.status == "finished"]
    print(f"  Finished matches: {len(finished)}")

    for f in finished[:10]:  # Limit to 10 to avoid rate limits
        time.sleep(1)  # Polite delay
        stats = client.get_fixture_stats(f.fixture_id)
        if stats:
            results["with_stats"] += 1
            results["stat_samples"].append({
                "match": f"{f.home_team} vs {f.away_team}",
                "competition": f.competition,
                "stats": stats,
            })
            print(f"  ✅ {f.home_team} vs {f.away_team}: {len(stats)} stat keys")
            if "avg_score" in stats:
                print(f"     Avg 3 Darts: {stats['avg_score']['home']} vs {stats['avg_score']['away']}")
        else:
            print(f"  ❌ {f.home_team} vs {f.away_team}: no stats")

    print(f"\n  Summary: {results['with_stats']}/{len(finished)} matches have deep stats")
    return results


def seed_snooker(rate_limiter: RateLimiter) -> dict:
    """Seed snooker data: fixtures, results, rankings, events."""
    print("\n" + "=" * 60)
    print("🎱 SNOOKER — api.snooker.org")
    print("=" * 60)

    client = SnookerOrgClient(rate_limiter=rate_limiter)
    results = {"upcoming": 0, "recent_results": 0, "rankings": 0, "events": 0}

    # Upcoming matches
    fixtures = client.get_fixtures()
    results["upcoming"] = len(fixtures)
    print(f"  Upcoming matches: {len(fixtures)}")
    for f in fixtures[:5]:
        print(f"    - {f.home_team} vs {f.away_team} ({f.competition})")

    time.sleep(1)

    # Recent results
    recent = client.get_recent_results()
    results["recent_results"] = len(recent)
    print(f"\n  Recent results: {len(recent)}")
    for m in recent[:5]:
        print(f"    - {m['player1_name']} {m['score1']}-{m['score2']} {m['player2_name']} "
              f"({m['event_name']})")

    time.sleep(1)

    # Season events
    events = client.get_season_events(2025)
    results["events"] = len(events)
    print(f"\n  Events in 2025 season: {len(events)}")
    for ev in events[:5]:
        print(f"    - {ev['name']} ({ev['start_date'][:10]} to {ev['end_date'][:10]})")

    time.sleep(1)

    # Rankings
    rankings = client.get_rankings(2025)
    results["rankings"] = len(rankings)
    print(f"\n  World rankings: {len(rankings)} players")
    for r in rankings[:5]:
        print(f"    #{r['position']} {r['name']}")

    return results


def seed_opendota(rate_limiter: RateLimiter) -> dict:
    """Seed Dota 2 esports data: pro matches + team stats."""
    print("\n" + "=" * 60)
    print("🎮 ESPORTS (Dota 2) — OpenDota API")
    print("=" * 60)

    client = OpenDotaClient(rate_limiter=rate_limiter)
    results = {"pro_matches": 0, "with_stats": 0, "teams": 0, "stat_samples": []}

    # Pro matches
    fixtures = client.get_fixtures()
    results["pro_matches"] = len(fixtures)
    print(f"  Recent pro matches: {len(fixtures)}")

    # Get detailed stats for first 5 matches
    for f in fixtures[:5]:
        time.sleep(2)  # Rate limit: 60/min
        stats = client.get_fixture_stats(f.fixture_id)
        if stats:
            results["with_stats"] += 1
            results["stat_samples"].append({
                "match": f"{f.home_team} vs {f.away_team}",
                "competition": f.competition,
                "stats": {k: v for k, v in stats.items()
                         if k in ("kills", "deaths", "gpm", "duration_minutes")},
            })
            print(f"  ✅ {f.home_team} vs {f.away_team}")
            print(f"     Kills: {stats['kills']['home']} vs {stats['kills']['away']}")
            print(f"     Avg GPM: {stats['gpm']['home']} vs {stats['gpm']['away']}")
        else:
            print(f"  ❌ {f.home_team} vs {f.away_team}: no stats (parse pending)")

    time.sleep(1)

    # Teams
    teams = client.get_teams()
    results["teams"] = len(teams)
    print(f"\n  Pro teams: {len(teams)}")
    for t in teams[:5]:
        print(f"    - {t['name']} (rating: {t['rating']}, W/L: {t['wins']}/{t['losses']})")

    return results


def seed_table_tennis(rate_limiter: RateLimiter) -> dict:
    """Seed table tennis data: fixtures + set scores."""
    print("\n" + "=" * 60)
    print("🏓 TABLE TENNIS — ITTF/Sofascore")
    print("=" * 60)

    client = ITTFClient(rate_limiter=rate_limiter)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = {"fixtures": 0, "with_stats": 0, "stat_samples": []}

    # Today's fixtures
    fixtures = client.get_fixtures(today)
    results["fixtures"] = len(fixtures)
    print(f"  Fixtures today: {len(fixtures)}")

    # Get stats for finished matches
    finished = [f for f in fixtures if f.status == "finished"]
    print(f"  Finished matches: {len(finished)}")

    for f in finished[:10]:
        time.sleep(1)
        stats = client.get_fixture_stats(f.fixture_id)
        if stats and stats.get("sets_won", {}).get("home", 0) > 0:
            results["with_stats"] += 1
            results["stat_samples"].append({
                "match": f"{f.home_team} vs {f.away_team}",
                "competition": f.competition,
                "stats": stats,
            })
            print(f"  ✅ {f.home_team} vs {f.away_team}: "
                  f"sets {stats['sets_won']['home']}-{stats['sets_won']['away']}, "
                  f"total pts {stats.get('total_points', {}).get('home', '?')}")
        else:
            print(f"  ❌ {f.home_team} vs {f.away_team}: no stats")

    print(f"\n  Summary: {results['with_stats']}/{len(finished)} matches have set score data")
    return results


def main():
    """Run all seeders and produce summary report."""
    print("=" * 60)
    print("  DEEP STATS SEEDER — Live API Data Fetch")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    rl = RateLimiter()
    all_results = {}

    try:
        all_results["darts"] = seed_darts(rl)
    except Exception as e:
        print(f"\n  ⚠️ Darts seeder error: {e}")
        all_results["darts"] = {"error": str(e)}

    try:
        all_results["snooker"] = seed_snooker(rl)
    except Exception as e:
        print(f"\n  ⚠️ Snooker seeder error: {e}")
        all_results["snooker"] = {"error": str(e)}

    try:
        all_results["esports_dota2"] = seed_opendota(rl)
    except Exception as e:
        print(f"\n  ⚠️ OpenDota seeder error: {e}")
        all_results["esports_dota2"] = {"error": str(e)}

    try:
        all_results["table_tennis"] = seed_table_tennis(rl)
    except Exception as e:
        print(f"\n  ⚠️ Table Tennis seeder error: {e}")
        all_results["table_tennis"] = {"error": str(e)}

    # Final summary
    print("\n" + "=" * 60)
    print("  SEEDING SUMMARY")
    print("=" * 60)
    for sport, data in all_results.items():
        if "error" in data:
            print(f"  ❌ {sport}: ERROR — {data['error']}")
        else:
            stats_count = data.get("with_stats", data.get("recent_results", 0))
            fixtures_count = data.get("fixtures", data.get("pro_matches", data.get("upcoming", 0)))
            print(f"  ✅ {sport}: {fixtures_count} fixtures, {stats_count} with deep stats")

    # Save summary
    summary_path = Path(__file__).parent.parent / "betting" / "data" / "deep_stats_seed_summary.json"
    summary_path.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")
    print(f"\n  Summary saved to: {summary_path}")


if __name__ == "__main__":
    main()
