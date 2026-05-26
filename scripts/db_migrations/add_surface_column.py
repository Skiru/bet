#!/usr/bin/env python3
"""Add 'surface' column to fixtures table for tennis events.

Idempotent — safe to run multiple times.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from bet.db.connection import get_db


def migrate():
    with get_db() as conn:
        # Check if column already exists
        columns = [row[1] for row in conn.execute("PRAGMA table_info(fixtures)").fetchall()]
        if "surface" not in columns:
            conn.execute("ALTER TABLE fixtures ADD COLUMN surface TEXT DEFAULT NULL")
            conn.commit()
            print("[migration] Added 'surface' column to fixtures table")
        else:
            print("[migration] 'surface' column already exists — skipping")


if __name__ == "__main__":
    migrate()
