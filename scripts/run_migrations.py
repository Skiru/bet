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
DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./bet.db").replace("sqlite:///", "")


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
