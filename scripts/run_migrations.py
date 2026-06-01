"""Migration helper used in development to run SQL migrations.

This is intentionally small: in production teams often use Alembic; this runner
keeps the repo free of heavy dependencies while providing a safe, repeatable
migration mechanism for the initial refactor.
"""
from __future__ import annotations

import os
from pathlib import Path
import sqlite3

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./bet.db")


def _sqlite_db_path(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    if url.startswith("sqlite://"):
        # sqlite://:memory: or other forms - only support file-based for migrations
        raise RuntimeError("Unsupported sqlite URL for migrations: use sqlite:///path/to/file.db")
    raise RuntimeError("Migration runner only supports sqlite file DB via DATABASE_URL env var")


DB_PATH = _sqlite_db_path(DATABASE_URL)


def run_migrations():
    if not MIGRATIONS_DIR.exists():
        print("No migrations directory found")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            print(f"Applying migration: {sql_file.name}")
            with open(sql_file, "r", encoding="utf-8") as fh:
                sql = fh.read()
                conn.executescript(sql)
        print("Migrations applied")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
