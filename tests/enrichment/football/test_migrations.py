import sqlite3

import pytest

from bet.db.schema import get_schema_version, init_db, migrate


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    yield conn
    conn.close()

def test_fresh_v20_initialization(memory_db):
    init_db(memory_db)
    assert get_schema_version(memory_db) == 20

    cursor = memory_db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert "sports_sync_cursor" in tables
    assert "sports_sync_run" in tables
    assert "sports_sync_item" in tables

    assert memory_db.execute("PRAGMA foreign_key_check").fetchall() == []
    assert memory_db.execute("PRAGMA quick_check").fetchone()[0] == "ok"

def test_v19_to_v20_migration_and_idempotency(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)

    from bet.db.schema import SCHEMA_SQL, _set_schema_version
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    conn.executescript(sql)
    _set_schema_version(conn, 19)
    conn.commit()

    migrate(conn, 19, 20)
    assert get_schema_version(conn) == 20

    migrate(conn, 19, 20)
    assert get_schema_version(conn) == 20

    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    conn.close()

def test_conflict_aborts(memory_db):
    from bet.db.schema import SCHEMA_SQL, _set_schema_version, migrate
    sql = SCHEMA_SQL.read_text(encoding="utf-8")

    # Strip the v20 unique index so we can insert duplicates
    sql = sql.replace("CREATE UNIQUE INDEX IF NOT EXISTS analysis_snapshot_run_id_idx ON analysis_snapshot(run_id);", "")

    memory_db.executescript(sql)
    _set_schema_version(memory_db, 19)

    memory_db.execute("INSERT INTO sports_enrichment_run (run_identity, sport, canonical_event_id, analysis_cutoff_at, started_at, status, policy_config_hash, requested_capabilities) VALUES ('run_1', 'football', 1, '2023', '2023', 'COMPLETE', 'hash', '[]')")
    run_id = memory_db.execute("SELECT last_insert_rowid()").fetchone()[0]

    memory_db.execute("INSERT INTO analysis_snapshot (schema_version, run_id, canonical_fixture_id, analysis_cutoff_at, status, snapshot_hash, payload_json, created_at) VALUES ('1', ?, 1, '2023', 'COMPLETE', 'hash1', '{}', '2023')", (run_id,))
    memory_db.execute("INSERT INTO analysis_snapshot (schema_version, run_id, canonical_fixture_id, analysis_cutoff_at, status, snapshot_hash, payload_json, created_at) VALUES ('1', ?, 1, '2023', 'COMPLETE', 'hash2', '{}', '2023')", (run_id,))

    with pytest.raises(ValueError, match="Duplicate run_id in analysis_snapshot"):
        migrate(memory_db, 19, 20)

def test_logical_identity_uniqueness(memory_db):
    init_db(memory_db)
    # create dependencies to satisfy foreign keys
    memory_db.execute("INSERT INTO sports (id, name, tier) VALUES (1, 'football', 1)")
    memory_db.execute("INSERT INTO teams (id, name, sport_id) VALUES (1, 't1', 1)")
    memory_db.execute("INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at) VALUES (1, 1, 1, 1, '2023', 'finished', '2023')")

    memory_db.execute("INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, request_identity, status, observed_at, valid_at, logical_identity) VALUES (1, 1, 'cap', 'src', 'req', 'SUCCESS', '2023', '2023', 'log_id1')")

    with pytest.raises(sqlite3.IntegrityError):
        memory_db.execute("INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, request_identity, status, observed_at, valid_at, logical_identity) VALUES (1, 1, 'cap2', 'src', 'req2', 'SUCCESS', '2023', '2023', 'log_id1')")

