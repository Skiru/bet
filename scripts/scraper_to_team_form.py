#!/usr/bin/env python3
"""Scraper-to-team_form bridge — transforms league_profiles into team_form data.

Reads aggregate stats from league_profiles table and converts them into
per-team team_form entries for use by deep_stats_report.py.

Supports: --sport, --league, --dry-run, --verbose flags.
Emits AGENT_SUMMARY at completion.
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from bet.db.connection import get_db
from bet.db.repositories import StatsRepo, LeagueProfileRepo

logger = logging.getLogger(__name__)

SPORT_MAP = {
    "football": 1,
    "basketball": 4,
    "hockey": 5,
    "tennis": 6,
    "volleyball": 7,
}


def _get_teams_for_competition(conn, competition_id: int) -> list[dict]:
    """Get all teams linked to a competition via fixtures."""
    rows = conn.execute(
        """SELECT DISTINCT t.id, t.name FROM teams t
           JOIN fixtures f ON (f.home_team_id = t.id OR f.away_team_id = t.id)
           WHERE f.competition_id = ?""",
        (competition_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _compute_trend(values: list[float]) -> str:
    """Compute trend indicator from value list."""
    if len(values) < 4:
        return "→"
    recent = sum(values[-3:]) / 3
    older = sum(values[:3]) / 3
    if recent > older * 1.1:
        return "↑"
    elif recent < older * 0.9:
        return "↓"
    return "→"


def bridge_league_profiles(
    conn, sport: str | None = None, league: str | None = None,
    dry_run: bool = False, verbose: bool = False,
) -> dict:
    """Convert league_profiles into team_form entries."""
    stats_repo = StatsRepo(conn)
    profile_repo = LeagueProfileRepo(conn)

    stats = {"processed": 0, "written": 0, "skipped": 0, "errors": 0}

    # Get competitions to process
    query = "SELECT DISTINCT id, name FROM competitions WHERE 1=1"
    params: list = []
    if sport and sport in SPORT_MAP:
        query += " AND sport_id = ?"
        params.append(SPORT_MAP[sport])
    if league:
        query += " AND name LIKE ?"
        params.append(f"%{league}%")

    competitions = conn.execute(query, params).fetchall()

    for comp in competitions:
        comp_id = comp["id"]
        comp_name = comp["name"]

        # Get league profiles for this competition
        profiles = profile_repo.get_for_competition(comp_id)
        if not profiles:
            continue

        # Get teams in this competition
        teams = _get_teams_for_competition(conn, comp_id)
        if not teams:
            continue

        if verbose:
            print(f"  {comp_name}: {len(profiles)} stat profiles, {len(teams)} teams")

        # For each stat profile, create team_form entry for each team
        for profile in profiles:
            for team in teams:
                stats["processed"] += 1
                # Create a synthetic l10_values from the league average
                # (teams get league-average as baseline; actual per-team data
                # should be enriched later by data_enrichment_agent)
                avg_val = profile.avg_value
                if avg_val is None:
                    stats["skipped"] += 1
                    continue

                # Build form data
                form = {
                    "team_id": team["id"],
                    "sport_id": SPORT_MAP.get(sport, 1) if sport else 1,
                    "stat_key": profile.stat_key,
                    "l10_values": json.dumps([avg_val] * 5),  # league avg as baseline
                    "l5_values": json.dumps([avg_val] * 3),
                    "l10_avg": avg_val,
                    "l5_avg": avg_val,
                    "h2h_values": json.dumps([]),
                    "h2h_opponent_id": None,
                    "trend": "→",  # league avg doesn't have a trend
                    "source": "league-profile-bridge",
                }

                if dry_run:
                    if verbose and stats["processed"] <= 10:
                        print(f"    [DRY-RUN] {team['name']} / {profile.stat_key} = {avg_val}")
                    stats["written"] += 1
                    continue

                try:
                    stats_repo.save_team_form(form)
                    stats["written"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    if verbose:
                        logger.warning(f"Error writing form for {team['name']}/{profile.stat_key}: {e}")

    if not dry_run:
        conn.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Bridge scraper league profiles → team_form")
    parser.add_argument("--sport", choices=list(SPORT_MAP.keys()), help="Filter by sport")
    parser.add_argument("--league", help="Filter by league name (substring match)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be written without writing")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    print("=" * 60)
    print("SCRAPER-TO-TEAM_FORM BRIDGE")
    print("=" * 60)

    if args.dry_run:
        print("  ⚠️  DRY-RUN MODE — no data will be written")

    with get_db() as conn:
        stats = bridge_league_profiles(
            conn,
            sport=args.sport,
            league=args.league,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )

    print(f"\n  Processed: {stats['processed']}")
    print(f"  Written: {stats['written']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")

    verdict = "OK" if stats["errors"] == 0 else "PARTIAL"
    print(f'\nAGENT_SUMMARY:{{"verdict":"{verdict}",'
          f'"processed":{stats["processed"]},'
          f'"written":{stats["written"]},'
          f'"skipped":{stats["skipped"]},'
          f'"errors":{stats["errors"]}}}')


if __name__ == "__main__":
    main()
