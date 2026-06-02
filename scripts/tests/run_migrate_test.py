"""Quick test runner to validate `migrate_datetimes_to_utc.sample_and_apply`.

Creates a temporary sqlite file with test rows and runs the migration function.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
import tempfile

from scripts import migrate_datetimes_to_utc as migrator
sample_and_apply = migrator.sample_and_apply


def create_test_db(path: Path):
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY AUTOINCREMENT, event_time TEXT, created_at TEXT)")
    # naive ISO
    cur.execute("INSERT INTO fixtures (event_time, created_at) VALUES (?, ?)", ("2026-06-02T12:00:00", "2026-06-02 12:00:00"))
    # epoch
    cur.execute("INSERT INTO fixtures (event_time, created_at) VALUES (?, ?)", ("1710000000", "1710000000"))
    # already with timezone
    cur.execute("INSERT INTO fixtures (event_time, created_at) VALUES (?, ?)", ("2026-06-02T10:00:00+02:00", "2026-06-02T10:00:00+02:00"))
    conn.commit()
    conn.close()


def main():
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test_migrate.sqlite"
        create_test_db(db_path)
        print("Before migration sample:")
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        for r in cur.execute("SELECT id, event_time, created_at FROM fixtures").fetchall():
            print(r)
        conn.close()

        sample_and_apply(db_path, apply=True)

        print('\nAfter migration sample:')
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        for r in cur.execute("SELECT id, event_time, created_at FROM fixtures").fetchall():
            print(r)
        conn.close()


if __name__ == "__main__":
    main()
