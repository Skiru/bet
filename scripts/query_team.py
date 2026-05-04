#!/usr/bin/env python3
"""Query team knowledge from the betting database.

Usage:
    python3 scripts/query_team.py "Liverpool" --sport football
    python3 scripts/query_team.py "Liverpool" --sport football --stat corners
    python3 scripts/query_team.py --top-teams --sport football --stat corners --min-avg 5.0
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo, StatsRepo


def query_team(team_name: str, sport_name: str, stat_key: str | None = None):
    with get_db() as conn:
        sport_repo = SportRepo(conn)
        team_repo = TeamRepo(conn)
        stats_repo = StatsRepo(conn)

        sport = sport_repo.get_by_name(sport_name)
        if not sport:
            print(f"Sport '{sport_name}' not found")
            return

        team = team_repo.resolve(team_name, sport.id)
        if not team:
            print(f"Team '{team_name}' not found in {sport_name}")
            return

        print(f"\n{'='*50}")
        print(f"Team: {team.name} (ID: {team.id})")
        print(f"Sport: {sport.name} | Aliases: {team.aliases}")
        if team.style_tags:
            print(f"Style: {', '.join(team.style_tags)}")
        print(f"{'='*50}")

        stat_keys = [stat_key] if stat_key else sport.stat_keys

        for key in stat_keys:
            form = stats_repo.get_form(team.id, key, n=10)
            if form:
                avg = sum(form) / len(form)
                l5 = form[:5]
                l5_avg = sum(l5) / len(l5) if l5 else 0
                trend = "↑" if l5_avg > avg else "↓" if l5_avg < avg else "→"
                print(f"\n  {key}:")
                print(f"    L10: {form} → avg {avg:.2f}")
                print(f"    L5:  {l5} → avg {l5_avg:.2f} {trend}")


def query_top_teams(sport_name: str, stat_key: str, min_avg: float = 0):
    """Find teams with highest average for a stat."""
    with get_db() as conn:
        # Query all teams with form data for this stat
        rows = conn.execute(
            "SELECT t.name, tf.l10_avg, tf.l5_avg, tf.trend "
            "FROM team_form tf "
            "JOIN teams t ON tf.team_id = t.id "
            "JOIN sports s ON tf.sport_id = s.id "
            "WHERE s.name = ? AND tf.stat_key = ? AND tf.h2h_opponent_id IS NULL "
            "AND tf.l10_avg >= ? "
            "ORDER BY tf.l10_avg DESC",
            (sport_name, stat_key, min_avg),
        ).fetchall()

        if not rows:
            print(f"No data for {sport_name}/{stat_key}")
            return

        print(f"\nTop teams for {stat_key} in {sport_name} (min avg: {min_avg}):")
        print(f"{'Team':<30} {'L10 avg':>8} {'L5 avg':>8} {'Trend':>6}")
        print("-" * 55)
        for r in rows[:20]:
            print(f"{r['name']:<30} {r['l10_avg']:>8.2f} {r['l5_avg'] or 0:>8.2f} {r['trend'] or '':>6}")


def main():
    parser = argparse.ArgumentParser(description="Query team knowledge from betting DB")
    parser.add_argument("team", nargs="?", help="Team name to query")
    parser.add_argument("--sport", required=True, help="Sport name")
    parser.add_argument("--stat", help="Specific stat key (default: all)")
    parser.add_argument("--top-teams", action="store_true", help="Show top teams for a stat")
    parser.add_argument("--min-avg", type=float, default=0, help="Minimum average for --top-teams")
    args = parser.parse_args()

    if args.top_teams:
        if not args.stat:
            print("--stat required with --top-teams")
            return
        query_top_teams(args.sport, args.stat, args.min_avg)
    elif args.team:
        query_team(args.team, args.sport, args.stat)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
