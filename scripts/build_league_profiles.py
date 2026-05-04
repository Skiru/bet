#!/usr/bin/env python3
"""Build league-level statistical profiles from accumulated match data.

Computes avg/median/stddev per stat per competition from the match_stats table.
These profiles serve as Bayesian priors for the probability engine.

Usage:
    python3 scripts/build_league_profiles.py
    python3 scripts/build_league_profiles.py --sport football --season 2025-26
"""
import argparse
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bet.db.connection import get_db
from bet.db.repositories import LeagueProfileRepo, SportRepo
from bet.db.models import LeagueProfile


def build_profiles(sport_filter: str | None = None, season: str = ""):
    with get_db() as conn:
        lp_repo = LeagueProfileRepo(conn)
        sport_repo = SportRepo(conn)

        # Get competitions with match data
        where_clause = ""
        params: list = []
        if sport_filter:
            sport = sport_repo.get_by_name(sport_filter)
            if not sport:
                print(f"Sport '{sport_filter}' not found")
                return
            where_clause = "WHERE c.sport_id = ?"
            params.append(sport.id)

        competitions = conn.execute(
            f"SELECT DISTINCT c.id, c.name, s.name as sport_name "
            f"FROM competitions c "
            f"JOIN sports s ON c.sport_id = s.id "
            f"JOIN fixtures f ON f.competition_id = c.id "
            f"JOIN match_stats ms ON ms.fixture_id = f.id "
            f"{where_clause} "
            f"ORDER BY s.name, c.name",
            params,
        ).fetchall()

        now = datetime.now(timezone.utc).isoformat()
        total_profiles = 0

        for comp in competitions:
            # Get all stat values for this competition
            stat_rows = conn.execute(
                "SELECT ms.stat_key, ms.stat_value "
                "FROM match_stats ms "
                "JOIN fixtures f ON ms.fixture_id = f.id "
                "WHERE f.competition_id = ? AND f.status = 'finished'",
                (comp["id"],),
            ).fetchall()

            # Group by stat_key
            stat_groups: dict[str, list[float]] = {}
            for row in stat_rows:
                stat_groups.setdefault(row["stat_key"], []).append(row["stat_value"])

            for stat_key, values in stat_groups.items():
                if len(values) < 3:
                    continue  # Need minimum sample

                profile = LeagueProfile(
                    id=None,
                    competition_id=comp["id"],
                    stat_key=stat_key,
                    season=season,
                    avg_value=statistics.mean(values),
                    median_value=statistics.median(values),
                    std_dev=statistics.stdev(values) if len(values) > 1 else None,
                    sample_size=len(values),
                    updated_at=now,
                )
                lp_repo.upsert(profile)
                total_profiles += 1

            if stat_groups:
                print(f"  {comp['sport_name']}/{comp['name']}: {len(stat_groups)} stat profiles")

        print(f"\n✓ Built {total_profiles} league profiles across {len(competitions)} competitions")


def main():
    parser = argparse.ArgumentParser(description="Build league statistical profiles")
    parser.add_argument("--sport", help="Filter by sport")
    parser.add_argument("--season", default="", help="Season label (e.g., 2025-26)")
    args = parser.parse_args()

    build_profiles(args.sport, args.season)


if __name__ == "__main__":
    main()
