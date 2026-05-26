#!/usr/bin/env python3
"""Fix hockey data contamination — removes football stats from hockey teams.

Identifies and deletes team_form entries where hockey teams have football-only
stat keys (corners, possession, tackles, offsides, etc.).

Usage:
    PYTHONPATH=src .venv/bin/python scripts/db_migrations/fix_hockey_contamination.py
    PYTHONPATH=src .venv/bin/python scripts/db_migrations/fix_hockey_contamination.py --dry-run
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bet.db.connection import get_db
from bet.stats.stat_validation import detect_contamination, VALID_STATS


# Stat keys that should NEVER appear on hockey/volleyball/basketball teams
CONTAMINATION_BLOCKLIST = {
    "hockey": {"corners", "possession", "ball_possession", "tackles", "offsides",
               "free_kicks", "shots_off_target", "yellow_cards", "red_cards"},
    "volleyball": {"corners", "possession", "ball_possession", "tackles", "offsides",
                   "shots_on_target", "shots_off_target", "yellow_cards", "goals"},
    "basketball": {"corners", "possession", "ball_possession", "tackles", "offsides",
                   "shots_on_target", "goals", "saves"},
}


def find_contaminated_entries(sport_name: str) -> list[dict]:
    """Find all team_form entries with contaminated stat keys for a sport."""
    blocklist = CONTAMINATION_BLOCKLIST.get(sport_name, set())
    if not blocklist:
        return []

    entries = []
    with get_db() as conn:
        rows = conn.execute(
            """SELECT tf.id, tf.stat_key, t.name as team_name, s.name as sport
               FROM team_form tf
               JOIN teams t ON tf.team_id = t.id
               JOIN sports s ON tf.sport_id = s.id
               WHERE LOWER(s.name) = LOWER(?)""",
            (sport_name,),
        ).fetchall()

        for row in rows:
            if row["stat_key"] in blocklist:
                entries.append({
                    "id": row["id"],
                    "team_name": row["team_name"],
                    "stat_key": row["stat_key"],
                    "sport": row["sport"],
                })

    return entries


def delete_contaminated_entries(entry_ids: list[int]) -> int:
    """Delete contaminated entries by ID."""
    if not entry_ids:
        return 0

    with get_db() as conn:
        placeholders = ",".join("?" * len(entry_ids))
        conn.execute(f"DELETE FROM team_form WHERE id IN ({placeholders})", entry_ids)
        conn.commit()

    return len(entry_ids)


def main():
    parser = argparse.ArgumentParser(description="Fix hockey/volleyball/basketball data contamination")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't delete")
    parser.add_argument("--sport", default=None, help="Fix specific sport (default: all)")
    args = parser.parse_args()

    sports_to_fix = [args.sport] if args.sport else list(CONTAMINATION_BLOCKLIST.keys())
    total_deleted = 0

    print("═══════════════════════════════════════")
    print("  DATA CONTAMINATION FIX")
    print("═══════════════════════════════════════\n")

    for sport in sports_to_fix:
        entries = find_contaminated_entries(sport)
        print(f"{sport}: {len(entries)} contaminated entries found")

        if entries and not args.dry_run:
            ids = [e["id"] for e in entries]
            deleted = delete_contaminated_entries(ids)
            total_deleted += deleted
            print(f"  → Deleted {deleted} entries")
        elif entries and args.dry_run:
            # Show sample
            for e in entries[:5]:
                print(f"  • {e['team_name']}: {e['stat_key']}")
            if len(entries) > 5:
                print(f"  ... and {len(entries) - 5} more")

    print(f"\nTotal: {'would delete' if args.dry_run else 'deleted'} {total_deleted if not args.dry_run else sum(len(find_contaminated_entries(s)) for s in sports_to_fix)} entries")


if __name__ == "__main__":
    main()
