#!/usr/bin/env python3
"""Data rotation — clean up old pipeline artifacts.

Usage:
    python3 scripts/data_rotation.py --days 30           # dry run (default)
    python3 scripts/data_rotation.py --days 30 --execute  # actually delete
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
DATA_DIR = ROOT_DIR / "betting" / "data"
DB_PATH = DATA_DIR / "betting.db"

# Files that must NEVER be deleted regardless of age
PROTECTED_FILES = {
    "betclic_bets_history.json",
    "picks-ledger.csv",
    "picks-ledger-v2.csv",
    "scan_urls.json",
    "betting_config.json",
    "betting.db",
}

PROTECTED_PATTERNS = [
    "picks-ledger*.csv",
    "*.bak",
]

# File patterns eligible for rotation (must also match a date pattern)
ROTATABLE_PATTERNS = [
    "*_s2_shortlist.*",
    "*_s3_deep_stats.*",
    "market_matrix_*",
    "decision_matrix_*",
    "weather_*",
    "tipster_aggregation_*",
    "analysis_pool_*",
    "odds_api_snapshot*",
    "odds_api_io_snapshot*",
    "espn_enrichment_*",
    "fixtures_*",
]

ROTATABLE_STATE_PATTERNS = [
    "pipeline_*",
]

# Date patterns to extract dates from filenames
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
DATE_COMPACT_RE = re.compile(r"(\d{8})")


def _is_protected(path: Path) -> bool:
    """Check if a file is protected from deletion."""
    name = path.name
    if name in PROTECTED_FILES:
        return True
    if name.endswith(".bak"):
        return True
    if name.startswith("picks-ledger"):
        return True
    return False


def _extract_date(filename: str) -> datetime | None:
    """Extract a date from a filename, return as datetime or None."""
    m = DATE_RE.search(filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    m = DATE_COMPACT_RE.search(filename)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except ValueError:
            pass
    return None


def _matches_rotatable(filename: str, patterns: list[str]) -> bool:
    """Check if filename matches any of the rotatable glob-like patterns."""
    from fnmatch import fnmatch
    return any(fnmatch(filename, pat) for pat in patterns)


def find_old_files(days: int) -> list[Path]:
    """Find dated files in betting/data/ older than `days` days."""
    cutoff = datetime.now() - timedelta(days=days)
    candidates = []

    # Scan main data dir
    if DATA_DIR.exists():
        for f in DATA_DIR.iterdir():
            if f.is_dir():
                continue
            if _is_protected(f):
                continue
            if not _matches_rotatable(f.name, ROTATABLE_PATTERNS):
                continue
            file_date = _extract_date(f.name)
            if file_date and file_date < cutoff:
                candidates.append(f)

    # Scan pipeline_state subdir
    state_dir = DATA_DIR / "pipeline_state"
    if state_dir.exists():
        for f in state_dir.iterdir():
            if f.is_dir():
                continue
            if not _matches_rotatable(f.name, ROTATABLE_STATE_PATTERNS):
                continue
            file_date = _extract_date(f.name)
            if file_date and file_date < cutoff:
                candidates.append(f)

    # Scan agent_reviews subdirectories (date-named dirs)
    reviews_dir = DATA_DIR / "agent_reviews"
    if reviews_dir.exists():
        for d in reviews_dir.iterdir():
            if not d.is_dir():
                continue
            dir_date = _extract_date(d.name)
            if dir_date and dir_date < cutoff:
                candidates.append(d)

    return sorted(candidates)


def count_old_db_rows(days_scan: int = 60, days_odds: int = 90) -> dict[str, int]:
    """Count DB rows older than retention periods."""
    import sqlite3
    counts = {"scan_results": 0, "match_stats": 0, "odds_history": 0, "fixtures": 0}
    if not DB_PATH.exists():
        return counts

    cutoff_scan = (datetime.now() - timedelta(days=days_scan)).strftime("%Y-%m-%d")
    cutoff_odds = (datetime.now() - timedelta(days=days_odds)).strftime("%Y-%m-%d")

    try:
        from bet.db.connection import get_db

        with get_db(DB_PATH) as conn:
            # scan_results: has betting_date column
            try:
                row = conn.execute("SELECT COUNT(*) FROM scan_results WHERE betting_date < ?", (cutoff_scan,)).fetchone()
                counts["scan_results"] = row[0]
            except sqlite3.OperationalError:
                pass

            # match_stats: join through fixtures to get date
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM match_stats ms "
                    "JOIN fixtures f ON ms.fixture_id = f.id "
                    "WHERE f.kickoff < ?",
                    (cutoff_scan,),
                ).fetchone()
                counts["match_stats"] = row[0]
            except sqlite3.OperationalError:
                pass

            # odds_history: join through fixtures
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM odds_history oh "
                    "JOIN fixtures f ON oh.fixture_id = f.id "
                    "WHERE f.kickoff < ?",
                    (cutoff_odds,),
                ).fetchone()
                counts["odds_history"] = row[0]
            except sqlite3.OperationalError:
                pass

            # orphaned fixtures (older than scan cutoff with no children)
            try:
                row = conn.execute(
                    "SELECT COUNT(*) FROM fixtures f "
                    "WHERE f.kickoff < ? "
                    "AND NOT EXISTS (SELECT 1 FROM match_stats ms WHERE ms.fixture_id = f.id) "
                    "AND NOT EXISTS (SELECT 1 FROM odds_history oh WHERE oh.fixture_id = f.id) "
                    "AND NOT EXISTS (SELECT 1 FROM bets b WHERE b.fixture_id = f.id)",
                    (cutoff_scan,),
                ).fetchone()
                counts["fixtures"] = row[0]
            except sqlite3.OperationalError:
                pass
    except Exception as e:
        print(f"  [warn] DB access error: {e}")

    return counts


def delete_old_db_rows(days_scan: int = 60, days_odds: int = 90) -> dict[str, int]:
    """Delete old DB rows. Returns counts of deleted rows."""
    import sqlite3
    deleted = {"scan_results": 0, "match_stats": 0, "odds_history": 0, "fixtures": 0}
    if not DB_PATH.exists():
        return deleted

    cutoff_scan = (datetime.now() - timedelta(days=days_scan)).strftime("%Y-%m-%d")
    cutoff_odds = (datetime.now() - timedelta(days=days_odds)).strftime("%Y-%m-%d")

    try:
        from bet.db.connection import get_db

        with get_db(DB_PATH) as conn:
            try:
                cur = conn.execute("DELETE FROM scan_results WHERE betting_date < ?", (cutoff_scan,))
                deleted["scan_results"] = cur.rowcount
            except sqlite3.OperationalError:
                pass

            try:
                cur = conn.execute(
                    "DELETE FROM match_stats WHERE fixture_id IN "
                    "(SELECT id FROM fixtures WHERE kickoff < ?)",
                    (cutoff_scan,),
                )
                deleted["match_stats"] = cur.rowcount
            except sqlite3.OperationalError:
                pass

            try:
                cur = conn.execute(
                    "DELETE FROM odds_history WHERE fixture_id IN "
                    "(SELECT id FROM fixtures WHERE kickoff < ?)",
                    (cutoff_odds,),
                )
                deleted["odds_history"] = cur.rowcount
            except sqlite3.OperationalError:
                pass

            # Clean orphaned fixtures (no children, no bets referencing them)
            try:
                cur = conn.execute(
                    "DELETE FROM fixtures WHERE kickoff < ? "
                    "AND id NOT IN (SELECT DISTINCT fixture_id FROM match_stats WHERE fixture_id IS NOT NULL) "
                    "AND id NOT IN (SELECT DISTINCT fixture_id FROM odds_history WHERE fixture_id IS NOT NULL) "
                    "AND id NOT IN (SELECT DISTINCT fixture_id FROM bets WHERE fixture_id IS NOT NULL)",
                    (cutoff_scan,),
                )
                deleted["fixtures"] = cur.rowcount
            except sqlite3.OperationalError:
                pass
    except Exception as e:
        print(f"  [warn] DB cleanup error: {e}")

    return deleted


def main():
    parser = argparse.ArgumentParser(description="Data rotation — clean up old pipeline artifacts")
    parser.add_argument("--days", type=int, default=30, help="Delete files older than N days (default: 30)")
    parser.add_argument("--execute", action="store_true", help="Actually delete files (default: dry run)")
    args = parser.parse_args()

    print(f"Data Rotation — {'EXECUTE' if args.execute else 'DRY RUN'}")
    print(f"  Retention: {args.days} days for files, 60 days for scan/stats DB, 90 days for odds DB")
    print()

    # Find old files
    old_files = find_old_files(args.days)
    total_size = 0
    dirs_found = []
    files_found = []

    for path in old_files:
        if path.is_dir():
            dir_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            total_size += dir_size
            dirs_found.append((path, dir_size))
        else:
            fsize = path.stat().st_size
            total_size += fsize
            files_found.append((path, fsize))

    print(f"Files to {'delete' if args.execute else 'rotate'}: {len(files_found)}")
    for path, size in files_found:
        rel = path.relative_to(ROOT_DIR)
        print(f"  {'DEL' if args.execute else '---'} {rel} ({size / 1024:.1f} KB)")

    if dirs_found:
        print(f"\nDirectories to {'delete' if args.execute else 'rotate'}: {len(dirs_found)}")
        for path, size in dirs_found:
            rel = path.relative_to(ROOT_DIR)
            print(f"  {'DEL' if args.execute else '---'} {rel}/ ({size / 1024:.1f} KB)")

    print(f"\nTotal space: {total_size / 1024 / 1024:.2f} MB")

    # DB cleanup
    db_counts = count_old_db_rows()
    total_db = sum(db_counts.values())
    print(f"\nDB rows to clean: {total_db}")
    for table, count in db_counts.items():
        if count > 0:
            print(f"  {table}: {count} rows")

    if not args.execute:
        print("\n[DRY RUN] No files or DB rows were deleted. Use --execute to delete.")
        return

    # Execute deletions
    deleted_files = 0
    deleted_dirs = 0

    for path, _ in files_found:
        try:
            path.unlink()
            deleted_files += 1
        except OSError as e:
            print(f"  [error] Failed to delete {path}: {e}")

    for path, _ in dirs_found:
        try:
            shutil.rmtree(path)
            deleted_dirs += 1
        except OSError as e:
            print(f"  [error] Failed to delete {path}: {e}")

    db_deleted = delete_old_db_rows()

    print(f"\n[DONE] Deleted {deleted_files} files, {deleted_dirs} directories")
    print(f"[DONE] Deleted DB rows: {sum(db_deleted.values())} "
          f"(scan: {db_deleted['scan_results']}, stats: {db_deleted['match_stats']}, "
          f"odds: {db_deleted['odds_history']}, fixtures: {db_deleted['fixtures']})")
    print(f"[DONE] Freed {total_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
