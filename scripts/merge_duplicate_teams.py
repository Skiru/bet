"""
Merge duplicate teams in the database caused by diacritics and scraper pollution.

Finds teams that are duplicates (diacritic vs ASCII variants, multiple entries for same club)
and merges their team_form data into a single canonical entry.

Usage:
    PYTHONPATH=src python3 scripts/merge_duplicate_teams.py --dry-run
    PYTHONPATH=src python3 scripts/merge_duplicate_teams.py --execute
"""
import argparse
import unicodedata
from collections import defaultdict

from bet.db.connection import get_db


def normalize_name(name: str) -> str:
    """Strip diacritics and normalize to ASCII for comparison."""
    return unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().strip()


def find_diacritic_duplicates(db) -> list[tuple]:
    """Find team pairs where one has diacritics and the other is ASCII equivalent."""
    cursor = db.execute("SELECT id, name FROM teams WHERE length(name) < 50")
    all_teams = cursor.fetchall()

    # Build ASCII → list of (id, original_name)
    ascii_map: dict[str, list] = defaultdict(list)
    for tid, name in all_teams:
        ascii_key = normalize_name(name).lower()
        ascii_map[ascii_key].append((tid, name))

    duplicates = []
    for ascii_key, entries in ascii_map.items():
        if len(entries) > 1:
            # Pick canonical: the one with most team_form records
            best_id, best_name, best_count = None, None, -1
            for tid, name in entries:
                cnt = db.execute(
                    'SELECT COUNT(*) FROM team_form WHERE team_id = ?', (tid,)
                ).fetchone()[0]
                if cnt > best_count:
                    best_id, best_name, best_count = tid, name, cnt

            # All others are duplicates to merge into canonical
            for tid, name in entries:
                if tid != best_id:
                    dup_count = db.execute(
                        'SELECT COUNT(*) FROM team_form WHERE team_id = ?', (tid,)
                    ).fetchone()[0]
                    duplicates.append((tid, name, dup_count, best_id, best_name, best_count))

    return duplicates


def find_garbage_teams(db) -> list[tuple]:
    """Find teams whose names are clearly not team names (scraped content)."""
    cursor = db.execute("""
        SELECT id, name FROM teams WHERE 
            length(name) > 60
            OR name LIKE '%PLN%'
            OR name LIKE '%Bonus%'
            OR name LIKE '%VIDEO%'
            OR name LIKE '%http%'
            OR name LIKE '%połowa%'
            OR name LIKE '%Picks & Odds%'
            OR name LIKE '%Picks &%'
            OR name LIKE '%WYDARZENIE%'
            OR name LIKE '%Typy%'
            OR name LIKE '%Today%'
            OR name LIKE '%🕑%'
            OR name LIKE '%🔫%'
            OR name LIKE '%Dziś%'
            OR name LIKE '%konto główne%'
    """)
    return cursor.fetchall()


def merge_team_form(db, source_id: int, target_id: int, dry_run: bool) -> int:
    """Move team_form records from source to target. Returns count moved."""
    cursor = db.execute(
        'SELECT COUNT(*) FROM team_form WHERE team_id = ?', (source_id,)
    )
    count = cursor.fetchone()[0]

    if count > 0 and not dry_run:
        # Check for stat_key conflicts
        db.execute("""
            UPDATE team_form SET team_id = ?
            WHERE team_id = ? 
            AND stat_key NOT IN (SELECT stat_key FROM team_form WHERE team_id = ?)
        """, (target_id, source_id, target_id))

        # Delete remaining duplicates (source had same stat_key as target)
        db.execute('DELETE FROM team_form WHERE team_id = ?', (source_id,))

    return count


def update_fixtures(db, source_id: int, target_id: int, dry_run: bool) -> int:
    """Update fixtures referencing source_id to point to target_id."""
    cursor = db.execute(
        'SELECT COUNT(*) FROM fixtures WHERE home_team_id = ? OR away_team_id = ?',
        (source_id, source_id)
    )
    count = cursor.fetchone()[0]

    if count > 0 and not dry_run:
        db.execute(
            'UPDATE fixtures SET home_team_id = ? WHERE home_team_id = ?',
            (target_id, source_id)
        )
        db.execute(
            'UPDATE fixtures SET away_team_id = ? WHERE away_team_id = ?',
            (target_id, source_id)
        )

    return count


def main():
    parser = argparse.ArgumentParser(description='Merge duplicate teams')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='Show what would be done without making changes')
    parser.add_argument('--execute', action='store_true',
                        help='Actually perform the merge (DESTRUCTIVE)')
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    dry_run = not args.execute

    with get_db() as db:
        # 1. Find garbage teams
        garbage = find_garbage_teams(db)
        print(f"=== GARBAGE TEAMS: {len(garbage)} ===")
        garbage_form_total = 0
        for tid, name in garbage[:10] if not args.verbose else garbage:
            cnt = db.execute(
                'SELECT COUNT(*) FROM team_form WHERE team_id = ?', (tid,)
            ).fetchone()[0]
            garbage_form_total += cnt
            if args.verbose or cnt > 0:
                print(f"  [{tid}] \"{name[:70]}\" — {cnt} form records")

        if not dry_run:
            for tid, name in garbage:
                db.execute('DELETE FROM team_form WHERE team_id = ?', (tid,))
                db.execute('DELETE FROM teams WHERE id = ?', (tid,))
            print(f"  DELETED {len(garbage)} garbage teams, {garbage_form_total} form records")
        else:
            print(f"  [DRY-RUN] Would delete {len(garbage)} garbage teams, {garbage_form_total} form records")

        # 2. Find diacritic duplicates
        duplicates = find_diacritic_duplicates(db)
        print(f"\n=== DIACRITIC DUPLICATES: {len(duplicates)} ===")

        merged_form = 0
        merged_fixtures = 0
        for dup_id, dup_name, dup_count, canon_id, canon_name, canon_count in duplicates:
            if args.verbose or dup_count > 0:
                print(f"  MERGE [{dup_id}]\"{dup_name}\"({dup_count}) → [{canon_id}]\"{canon_name}\"({canon_count})")

            form_moved = merge_team_form(db, dup_id, canon_id, dry_run)
            fix_moved = update_fixtures(db, dup_id, canon_id, dry_run)
            merged_form += form_moved
            merged_fixtures += fix_moved

            if not dry_run:
                db.execute('DELETE FROM teams WHERE id = ?', (dup_id,))

        action = "MERGED" if not dry_run else "[DRY-RUN] Would merge"
        print(f"\n  {action}: {len(duplicates)} duplicates, {merged_form} form records, {merged_fixtures} fixtures")

        # Summary
        remaining = db.execute('SELECT COUNT(*) FROM teams').fetchone()[0]
        print(f"\n=== SUMMARY ===")
        print(f"  Teams before: {remaining + (len(garbage) + len(duplicates) if not dry_run else 0)}")
        print(f"  Garbage removed: {len(garbage)}")
        print(f"  Duplicates merged: {len(duplicates)}")
        print(f"  Teams after: {remaining if not dry_run else remaining - len(garbage) - len(duplicates)}")


if __name__ == '__main__':
    main()
