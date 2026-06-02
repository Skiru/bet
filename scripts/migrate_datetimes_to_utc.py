#!/usr/bin/env python3
"""Migrate datetime-like text fields in SQLite DB to timezone-aware UTC ISO strings.

This script is conservative by default: it only shows a sample of rows that
would be converted. Use `--apply` to perform the updates. A backup is created
for file-based SQLite DBs before applying changes.

Usage:
  python3 scripts/migrate_datetimes_to_utc.py --db-url sqlite:///./bet.db --apply
  python3 scripts/migrate_datetimes_to_utc.py --db-url sqlite:///./betting/data/betting.db
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dateutil import parser


def _sqlite_db_path(url: str) -> Path:
    if url.startswith("sqlite:///"):
        return Path(url.replace("sqlite:///", "", 1))
    if url.startswith("sqlite://"):
        raise RuntimeError("Unsupported sqlite URL for migration: use sqlite:///path/to/file.db")
    raise RuntimeError("Migration runner only supports sqlite file DB via --db-url")


def _find_date_columns(conn: sqlite3.Connection) -> List[tuple[str, str]]:
    """Return list of (table, column) pairs that look like datetime columns.

    Heuristic: column name contains one of keywords.
    """
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    candidates = []
    keywords = ("date", "time", "created", "kickoff", "started", "completed", "generated")
    for t in tables:
        try:
            cols = cur.execute(f"PRAGMA table_info('{t}')").fetchall()
        except Exception:
            continue
        for col in cols:
            name = col[1]
            if any(k in name.lower() for k in keywords):
                candidates.append((t, name))
    return candidates


def _try_parse(value: str) -> datetime | None:
    if value is None:
        return None
    v = str(value).strip()
    if v == "":
        return None
    # Numeric epoch
    try:
        if v.isdigit():
            return datetime.fromtimestamp(int(v), tz=timezone.utc)
        # float epoch
        if "." in v and all(p.replace("-", "").isdigit() for p in v.split(".")):
            return datetime.fromtimestamp(float(v), tz=timezone.utc)
    except Exception:
        pass
    # Parse with dateutil
    try:
        dt = parser.parse(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def sample_and_apply(db_path: Path, apply: bool = False):
    if not db_path.exists():
        raise RuntimeError(f"DB path not found: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        candidates = _find_date_columns(conn)
        print(f"Found {len(candidates)} candidate columns for conversion")
        cur = conn.cursor()
        for table, col in candidates:
            print(f"\nTable: {table}, Column: {col}")
            rows = cur.execute(f"SELECT rowid, {col} FROM {table} LIMIT 20").fetchall()
            previews = []
            for r in rows:
                rowid = r[0]
                val = r[1]
                parsed = _try_parse(val)
                previews.append((rowid, val, parsed.isoformat() if parsed else None))
            for pid, raw, conv in previews:
                print(f"  row {pid}: {raw!r} -> {conv}")

            if apply:
                print(f"  Applying conversion for table {table}.{col} ...")
                # Backup in case of large changes already performed by user
                # We'll run a cursor over all rows and update those that parse
                all_rows = cur.execute(f"SELECT rowid, {col} FROM {table}").fetchall()
                updates = []
                for r in all_rows:
                    rowid = r[0]
                    val = r[1]
                    parsed = _try_parse(val)
                    if parsed:
                        iso = parsed.isoformat()
                        updates.append((iso, rowid))
                print(f"  {len(updates)} rows to update in {table}.{col}")
                for iso, rowid in updates:
                    cur.execute(f"UPDATE {table} SET {col} = ? WHERE rowid = ?", (iso, rowid))
                conn.commit()
                print(f"  Updates applied for {table}.{col}")

    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate DB datetime-like fields to UTC ISO strings")
    parser.add_argument("--db-url", default=None, help="sqlite:///path/to/db.sqlite")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    args = parser.parse_args()

    db_url = args.db_url or "sqlite:///./bet.db"
    db_path = _sqlite_db_path(db_url)
    if args.apply:
        # create backup
        bak = db_path.with_suffix(db_path.suffix + ".bak")
        shutil.copy2(db_path, bak)
        print(f"Backup created: {bak}")
    sample_and_apply(db_path, apply=args.apply)


if __name__ == "__main__":
    main()
