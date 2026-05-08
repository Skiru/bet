"""Schema initialization and migration for the betting database."""

import sqlite3
from pathlib import Path

SCHEMA_SQL = Path(__file__).parent / "schema.sql"
SCHEMA_VERSION = 6


def init_db(conn: sqlite3.Connection) -> None:
    """Execute schema.sql against the connection. Idempotent (IF NOT EXISTS).

    For existing databases, runs migrations BEFORE applying schema.sql
    to clean up data that would violate new constraints.
    """
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    # Run migrations BEFORE schema to fix data that would violate new constraints
    current_version = get_schema_version(conn)
    if current_version < SCHEMA_VERSION:
        migrate(conn, current_version, SCHEMA_VERSION)

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
    """Run incremental migrations."""
    if from_version >= to_version:
        return

    if from_version < 3 and from_version > 0:
        # v3: Add stats_detail column to bets table
        try:
            conn.execute("ALTER TABLE bets ADD COLUMN stats_detail TEXT")
        except sqlite3.OperationalError:
            pass  # Column already exists (IF NOT EXISTS not supported for ALTER)

        # v2: Expression-based unique index for team_form NULL h2h_opponent_id
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_team_form_upsert "
            "ON team_form(team_id, stat_key, COALESCE(h2h_opponent_id, 0))"
        )

        # v2: Clean up duplicate team_form rows with NULL h2h_opponent_id
        conn.execute(
            "DELETE FROM team_form WHERE id NOT IN ("
            "  SELECT MIN(id) FROM team_form "
            "  GROUP BY team_id, stat_key, COALESCE(h2h_opponent_id, 0)"
            ")"
        )

    if from_version < 4:
        # v4: Decision learning tables
        migration_path = Path(__file__).parent / "migrations" / "003_decision_learning.sql"
        if migration_path.exists():
            conn.executescript(migration_path.read_text(encoding="utf-8"))

    if from_version < 5:
        # v5: ESPN deep integration tables
        migration_path = Path(__file__).parent / "migrations" / "005_espn_deep_tables.sql"
        if migration_path.exists():
            conn.executescript(migration_path.read_text(encoding="utf-8"))

    if from_version < 6:
        # v6: Composite indexes for common query patterns + schema_meta table
        # These indexes are also in schema.sql, so for fresh DBs they'll be created there.
        # For existing DBs, the tables exist but the indexes don't.
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_decision_outcomes_sport_market "
                "ON decision_outcomes(sport, market)"
            )
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet (fresh DB — schema.sql will create it)
        try:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_odds_history_lookup "
                "ON odds_history(fixture_id, market, selection)"
            )
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet (fresh DB — schema.sql will create it)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_meta "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )

    conn.commit()
