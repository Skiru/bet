#!/usr/bin/env python3
"""Clean phantom fixtures from the database.

Phantom fixtures are playwright-scan entries where teams appear in multiple
matches on the same date — a telltale sign of league schedule pages being
scraped and ALL their matchdays assigned to today's date.

Usage:
    python3 scripts/clean_phantom_fixtures.py --date 2026-05-11 --dry-run
    python3 scripts/clean_phantom_fixtures.py --date 2026-05-11
"""
import argparse
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.db.connection import get_db


def clean_phantom_fixtures(date: str, dry_run: bool = True) -> dict:
    """Remove phantom playwright-scan fixtures from DB.

    Strategy:
    1. Find all fixtures for the date, separate API vs scan sources
    2. Count team appearances in scan fixtures
    3. Teams appearing in >2 scan fixtures are phantoms (schedule page leak)
    4. Delete all scan fixtures involving phantom teams (unless also in API)

    Returns dict with counts of deleted/kept fixtures.
    """
    with get_db() as conn:
        conn.row_factory = sqlite3.Row

        # Get all fixtures for date
        all_fixtures = conn.execute(
            """SELECT f.id, f.source, f.kickoff,
                      h.name AS home_team, a.name AS away_team,
                      c.name AS competition, s.name AS sport
               FROM fixtures f
               LEFT JOIN teams h ON f.home_team_id = h.id
               LEFT JOIN teams a ON f.away_team_id = a.id
               LEFT JOIN competitions c ON f.competition_id = c.id
               LEFT JOIN sports s ON f.sport_id = s.id
               WHERE f.kickoff LIKE ?""",
            (f"{date}%",),
        ).fetchall()

        print(f"Total fixtures for {date}: {len(all_fixtures)}")

        # Separate by source
        api_fixtures = [r for r in all_fixtures if r["source"] not in ("playwright-scan", "scan-expansion")]
        scan_fixtures = [r for r in all_fixtures if r["source"] in ("playwright-scan", "scan-expansion")]

        print(f"  API-sourced: {len(api_fixtures)}")
        print(f"  Scan-sourced: {len(scan_fixtures)}")

        if not scan_fixtures:
            print("No scan fixtures to clean.")
            return {"deleted": 0, "kept": len(api_fixtures)}

        # Build set of teams confirmed by API
        api_teams: set[str] = set()
        for r in api_fixtures:
            api_teams.add(r["home_team"].lower())
            api_teams.add(r["away_team"].lower())

        # Count scan team appearances
        scan_team_counts: Counter = Counter()
        for r in scan_fixtures:
            scan_team_counts[r["home_team"].lower()] += 1
            scan_team_counts[r["away_team"].lower()] += 1

        # Identify phantom teams (>2 appearances NOT in API)
        phantom_teams: set[str] = set()
        for team, count in scan_team_counts.items():
            if count > 2 and team not in api_teams:
                phantom_teams.add(team)

        print(f"\nPhantom teams (>2 matches, not in API): {len(phantom_teams)}")
        if phantom_teams:
            top_phantoms = sorted(phantom_teams, key=lambda t: scan_team_counts[t], reverse=True)[:20]
            for t in top_phantoms:
                print(f"  {t}: {scan_team_counts[t]} matches")

        # Identify fixtures to delete
        to_delete = []
        to_keep = []
        for r in scan_fixtures:
            home_lower = r["home_team"].lower()
            away_lower = r["away_team"].lower()
            if home_lower in phantom_teams or away_lower in phantom_teams:
                to_delete.append(r)
            else:
                to_keep.append(r)

        print(f"\nScan fixtures to DELETE: {len(to_delete)}")
        print(f"Scan fixtures to KEEP: {len(to_keep)}")
        print(f"Total after cleanup: {len(api_fixtures) + len(to_keep)}")

        if dry_run:
            print("\n[DRY RUN] No changes made. Run without --dry-run to delete.")
        else:
            delete_ids = [r["id"] for r in to_delete]
            if delete_ids:
                # Delete dependent rows first (FK constraints)
                dependent_tables = [
                    "match_stats", "odds_history", "analysis_results",
                    "gate_results", "analysis_raw_data", "decision_snapshots",
                    "decision_outcomes", "player_gamelogs", "espn_predictions", "bets",
                ]
                batch_size = 500
                for table in dependent_tables:
                    for i in range(0, len(delete_ids), batch_size):
                        batch = delete_ids[i:i + batch_size]
                        placeholders = ",".join("?" * len(batch))
                        conn.execute(f"DELETE FROM {table} WHERE fixture_id IN ({placeholders})", batch)

                # Now delete fixtures
                for i in range(0, len(delete_ids), batch_size):
                    batch = delete_ids[i:i + batch_size]
                    placeholders = ",".join("?" * len(batch))
                    conn.execute(f"DELETE FROM fixtures WHERE id IN ({placeholders})", batch)
                conn.commit()
                print(f"\n✓ Deleted {len(delete_ids)} phantom fixtures (and dependent rows) from DB.")

        return {
            "deleted": len(to_delete),
            "kept": len(api_fixtures) + len(to_keep),
            "phantom_teams": len(phantom_teams),
        }


def main():
    parser = argparse.ArgumentParser(description="Clean phantom fixtures from DB")
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting")
    args = parser.parse_args()

    result = clean_phantom_fixtures(args.date, dry_run=args.dry_run)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    main()
