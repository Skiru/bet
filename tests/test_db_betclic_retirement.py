from __future__ import annotations

import sqlite3
from pathlib import Path

from bet.db.schema import SCHEMA_VERSION, get_schema_version, init_db, migrate


def _object_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'view', 'trigger')"
    ).fetchall()
    return {str(row[0]).lower() for row in rows}


def test_fresh_bootstrap_contains_no_retired_operator_objects(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "fresh.sqlite")
    try:
        init_db(conn)
        assert get_schema_version(conn) == SCHEMA_VERSION == 21
        assert not {name for name in _object_names(conn) if "betclic" in name}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(coupons)")}
        assert "operator_ref" in columns
        assert "betclic_ref" not in columns
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_version_20_upgrade_retires_objects_and_preserves_data(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "historical.sqlite")
    try:
        conn.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT);
            INSERT INTO schema_meta VALUES ('version', '20');
            CREATE TABLE coupons (
                id INTEGER PRIMARY KEY,
                coupon_id TEXT NOT NULL,
                betclic_ref TEXT
            );
            INSERT INTO coupons VALUES (1, 'coupon-1', 'legacy-reference');
            CREATE TABLE betclic_markets (id INTEGER PRIMARY KEY, event_name TEXT);
            CREATE TABLE betclic_competition_profiles (id INTEGER PRIMARY KEY, sport TEXT);
            CREATE INDEX idx_betclic_markets_event ON betclic_markets(event_name);
            CREATE TABLE unrelated (id INTEGER PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO unrelated VALUES (1, 'preserved');
            """
        )
        migrate(conn, 20, SCHEMA_VERSION)

        assert get_schema_version(conn) == 21
        assert not {name for name in _object_names(conn) if "betclic" in name}
        assert conn.execute("SELECT operator_ref FROM coupons WHERE id = 1").fetchone()[0] == "legacy-reference"
        assert conn.execute("SELECT value FROM unrelated WHERE id = 1").fetchone()[0] == "preserved"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        migrate(conn, SCHEMA_VERSION, SCHEMA_VERSION)
        assert get_schema_version(conn) == 21
    finally:
        conn.close()
