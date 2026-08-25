from __future__ import annotations

import sqlite3
from typing import Any
from bet.db.schema import init_db, SCHEMA_VERSION, get_schema_version


def create_temp_sqlite_store() -> sqlite3.Connection:
    """Create a temporary in-memory SQLite connection with foreign keys enabled
    and initialized with the project's repository schema.
    """
    # Create an in-memory database
    conn = sqlite3.connect(":memory:")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    # Initialize schema
    init_db(conn)

    return conn


def get_table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Expose a helper to snapshot table counts for tables relevant to this phase."""
    relevant_tables = [
        "sports",
        "competitions",
        "teams",
        "fixtures",
        "fixture_sources",
        "scan_results",
        "sports_entity",
        "source_entity_reference",
        "evidence_package_revision",
        "sports_enrichment_run",
        "source_operation_attempt",
        "fixture_capability_observation",
        "fixture_capability_projection",
    ]

    counts: dict[str, int] = {}
    for table in relevant_tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            counts[table] = row[0] if row else 0
        except sqlite3.OperationalError:
            counts[table] = -1  # Indicates the table does not exist or has schema issues

    return counts
