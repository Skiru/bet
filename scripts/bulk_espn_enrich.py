#!/usr/bin/env python3
"""Fast bulk enrichment using ESPN API — targets today's fixtures directly.

Optimized for speed: parallel workers, direct DB writes, no fallback chains.
ESPN API is free, no key required, generous rate limits.

Usage:
    python3 scripts/bulk_espn_enrich.py --date 2026-05-20
    python3 scripts/bulk_espn_enrich.py --date 2026-05-20 --workers 10
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import time
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.api_clients.espn import (
    ESPNClient, ESPN_LEAGUES, ESPN_SPORT_MAP,
    COMPETITION_TO_ESPN_LEAGUE,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("bulk_espn_enrich")

DB_PATH = Path(__file__).parent.parent / "betting" / "data" / "betting.db"
_db_lock = threading.Lock()
_progress_lock = threading.Lock()
_progress = {"enriched": 0, "failed": 0, "skipped": 0}


def get_teams_needing_enrichment(date: str, min_stats: int = 3) -> list[dict]:
    """Get teams from today's fixtures that need enrichment."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT DISTINCT t.id, t.name, s.name as sport, c.name as competition
        FROM fixtures f
        JOIN sports s ON f.sport_id = s.id
        JOIN teams t ON (t.id = f.home_team_id OR t.id = f.away_team_id)
        LEFT JOIN competitions c ON f.competition_id = c.id
        WHERE f.kickoff LIKE ?
        AND (SELECT COUNT(*) FROM team_form tf WHERE tf.team_id = t.id AND tf.l5_avg IS NOT NULL) < ?
    """, (f"{date}%", min_stats)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_espn_league(team_name: str, sport: str, competition: str | None) -> str | None:
    """Resolve ESPN league code from competition name."""
    if not competition:
        return None
    comp_lower = competition.lower().strip()
    # Direct lookup
    if comp_lower in COMPETITION_TO_ESPN_LEAGUE:
        return COMPETITION_TO_ESPN_LEAGUE[comp_lower]
    # Partial match
    for key, league in COMPETITION_TO_ESPN_LEAGUE.items():
        if key in comp_lower or comp_lower in key:
            return league
    # Default leagues for each sport
    defaults = {
        "football": ESPN_LEAGUES.get("football", []),
        "basketball": ["nba", "wnba"],
        "hockey": ["nhl"],
        "tennis": ["atp", "wta"],
    }
    sport_defaults = defaults.get(sport, [])
    return sport_defaults[0] if sport_defaults else None


def enrich_single_team(team_info: dict) -> dict:
    """Enrich a single team using ESPN API. Returns stats dict or empty."""
    team_id = team_info["id"]
    team_name = team_info["name"]
    sport = team_info["sport"]
    competition = team_info.get("competition", "")

    league = resolve_espn_league(team_name, sport, competition)
    if not league:
        return {"team_id": team_id, "status": "no_league", "stats": {}}

    try:
        client = ESPNClient(sport=sport, league=league)

        if sport == "tennis":
            # Tennis: use athlete search → recent matches
            return _enrich_tennis_player(client, team_id, team_name, sport)
        else:
            # Team sports: find team → get last fixtures → get stats
            return _enrich_team_sport(client, team_id, team_name, sport)
    except Exception as e:
        log.debug("Failed %s (%s): %s", team_name, sport, e)
        return {"team_id": team_id, "status": "error", "stats": {}, "error": str(e)}


def _enrich_team_sport(client: ESPNClient, team_id: int, team_name: str, sport: str) -> dict:
    """Enrich a team sport (football, basketball, hockey)."""
    # Find ESPN team ID
    espn_team_id = client.resolve_team_id(team_name)
    if not espn_team_id:
        return {"team_id": team_id, "status": "not_found", "stats": {}}

    # Get last 5-10 fixtures
    fixtures = client.get_team_last_fixtures(espn_team_id, last_n=7)
    if not fixtures:
        return {"team_id": team_id, "status": "no_fixtures", "stats": {}}

    # Accumulate stats from each fixture
    stat_accum: dict[str, list[float]] = defaultdict(list)

    for fix in fixtures[:7]:
        fix_id = fix.get("id")
        if not fix_id:
            continue
        try:
            match_stats_list = client.get_fixture_stats(str(fix_id))
            if not match_stats_list:
                continue
            ms = match_stats_list[0]
            stats = ms.stats if hasattr(ms, "stats") else {}

            # Determine side
            home_name = ms.home_team_name if hasattr(ms, "home_team_name") else ""
            away_name = ms.away_team_name if hasattr(ms, "away_team_name") else ""
            side = _guess_side(team_name, home_name, away_name)

            for stat_key, side_vals in stats.items():
                if isinstance(side_vals, dict) and side in side_vals:
                    val = side_vals[side]
                    if isinstance(val, (int, float)) and val >= 0:
                        stat_accum[stat_key].append(float(val))
        except Exception:
            continue

    if not stat_accum:
        return {"team_id": team_id, "status": "no_stats", "stats": {}}

    # Compute averages
    averages = {}
    for key, vals in stat_accum.items():
        if vals:
            averages[key] = round(sum(vals) / len(vals), 2)

    return {"team_id": team_id, "status": "enriched", "stats": averages, "matches": len(fixtures)}


def _enrich_tennis_player(client: ESPNClient, team_id: int, player_name: str, sport: str) -> dict:
    """Enrich a tennis player using ESPN match data."""
    try:
        # Resolve athlete ID then get recent matches
        athlete_id = client.resolve_team_id(player_name)  # For tennis, this resolves athlete
        if not athlete_id:
            return {"team_id": team_id, "status": "not_found", "stats": {}}
        matches = client._get_athlete_recent_matches(athlete_id, last_n=7)
        if not matches:
            return {"team_id": team_id, "status": "no_matches", "stats": {}}

        stat_accum: dict[str, list[float]] = defaultdict(list)
        for match in matches:
            stats = match.get("stats", {})
            for key, val in stats.items():
                if isinstance(val, (int, float)) and val >= 0:
                    stat_accum[key].append(float(val))

        if not stat_accum:
            # Even without detailed stats, record match counts
            total_games = [m.get("total_games", 0) for m in matches if m.get("total_games")]
            if total_games:
                stat_accum["total_games"] = total_games

        averages = {}
        for key, vals in stat_accum.items():
            if vals:
                averages[key] = round(sum(vals) / len(vals), 2)

        return {"team_id": team_id, "status": "enriched", "stats": averages, "matches": len(matches)}
    except Exception as e:
        return {"team_id": team_id, "status": "error", "stats": {}, "error": str(e)}


def _guess_side(team_name: str, home: str, away: str) -> str:
    tn = team_name.lower().split()
    h = home.lower()
    a = away.lower()
    home_score = sum(1 for w in tn if len(w) > 2 and w in h)
    away_score = sum(1 for w in tn if len(w) > 2 and w in a)
    return "home" if home_score >= away_score else "away"


def write_stats_to_db(results: list[dict]) -> int:
    """Write enriched stats to team_form table."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    now = datetime.now(timezone.utc).isoformat()
    written = 0

    for result in results:
        if result["status"] != "enriched" or not result["stats"]:
            continue
        team_id = result["team_id"]
        matches_used = result.get("matches", 5)

        for stat_key, avg_val in result["stats"].items():
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO team_form
                    (team_id, stat_key, l5_avg, l10_avg, matches_used, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (team_id, stat_key, avg_val, avg_val, matches_used, now))
                written += 1
            except Exception as e:
                log.debug("DB write error for team %d/%s: %s", team_id, stat_key, e)

    conn.commit()
    conn.close()
    return written


def main():
    parser = argparse.ArgumentParser(description="Fast bulk ESPN enrichment")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=8, help="Parallel workers")
    parser.add_argument("--min-stats", type=int, default=3, help="Min stats threshold")
    parser.add_argument("--sport", help="Filter by sport")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get teams needing enrichment
    teams = get_teams_needing_enrichment(args.date, args.min_stats)
    if args.sport:
        teams = [t for t in teams if t["sport"] == args.sport]

    log.info("Teams needing enrichment: %d", len(teams))
    by_sport = defaultdict(int)
    for t in teams:
        by_sport[t["sport"]] += 1
    for sport, count in sorted(by_sport.items()):
        log.info("  %s: %d", sport, count)

    if not teams:
        print("AGENT_SUMMARY:" + json.dumps({"verdict": "OK", "message": "All teams enriched"}))
        return

    # Parallel enrichment
    results: list[dict] = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(enrich_single_team, t): t for t in teams}
        done = 0
        for future in as_completed(futures):
            done += 1
            try:
                result = future.result()
                results.append(result)
                if result["status"] == "enriched":
                    with _progress_lock:
                        _progress["enriched"] += 1
                elif result["status"] in ("error", "not_found", "no_league"):
                    with _progress_lock:
                        _progress["failed"] += 1
                else:
                    with _progress_lock:
                        _progress["skipped"] += 1
            except Exception as e:
                with _progress_lock:
                    _progress["failed"] += 1
                results.append({"team_id": 0, "status": "crash", "stats": {}})

            if done % 50 == 0:
                elapsed = time.time() - start_time
                log.info(
                    "Progress: %d/%d (%.0fs) — enriched=%d failed=%d",
                    done, len(teams), elapsed,
                    _progress["enriched"], _progress["failed"],
                )

    # Write to DB
    written = write_stats_to_db(results)
    elapsed = time.time() - start_time

    # Final stats
    enriched = sum(1 for r in results if r["status"] == "enriched")
    failed = sum(1 for r in results if r["status"] in ("error", "crash"))
    not_found = sum(1 for r in results if r["status"] == "not_found")
    no_stats = sum(1 for r in results if r["status"] == "no_stats")

    log.info("=" * 60)
    log.info("ENRICHMENT COMPLETE in %.1fs", elapsed)
    log.info("  Enriched: %d teams, %d stat rows written", enriched, written)
    log.info("  Not found: %d | No stats: %d | Errors: %d", not_found, no_stats, failed)

    print("\nAGENT_SUMMARY:" + json.dumps({
        "verdict": "OK" if enriched > 100 else "PARTIAL",
        "enriched_teams": enriched,
        "stat_rows_written": written,
        "not_found": not_found,
        "no_stats": no_stats,
        "errors": failed,
        "elapsed_seconds": round(elapsed, 1),
        "total_teams": len(teams),
    }))


if __name__ == "__main__":
    main()
