"""Schema initialization and migration for the betting database."""

import sqlite3
from pathlib import Path

SCHEMA_SQL = Path(__file__).parent / "schema.sql"
SCHEMA_VERSION = 1


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the connection. Idempotent (IF NOT EXISTS)."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(sql)
    # Store schema version
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_meta "
        "(key TEXT PRIMARY KEY, value TEXT)"
    )
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("version", str(SCHEMA_VERSION)),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read current schema version from the metadata table."""
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?", ("version",)
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0


def migrate(conn: sqlite3.Connection, from_version: int, to_version: int) -> None:
    """Run incremental migrations. For v1, this is a no-op."""
    if from_version >= to_version:
        return
    # Future migrations go here as elif blocks
