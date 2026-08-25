"""Test suite for provider observation schema, migrations, and DDL rules (C3)."""

import sqlite3
from pathlib import Path
import pytest

from bet.db.schema import init_db, get_schema_version, SCHEMA_VERSION


def test_c3_fresh_db_has_committed_observation_schema(tmp_path):
    """C3 test 1 & 4: fresh database initialization contains committed pipeline_provider_observation_attempts table."""
    db_path = tmp_path / "fresh.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)

    # Check table existence in sqlite_schema
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall()]
    assert "pipeline_provider_observation_attempts" in tables, (
        "C3 defect: pipeline_provider_observation_attempts table missing from fresh DB initialized via schema.sql"
    )

    # Check schema version
    ver = get_schema_version(conn)
    assert ver == 27, f"Expected SCHEMA_VERSION = 27, got {ver}"
    conn.close()


def test_c3_migration_023_is_idempotent(tmp_path):
    """C3 test 2 & 19: migration 023 upgrades v22 schema and is idempotent."""
    db_path = tmp_path / "upgrade.db"
    conn = sqlite3.connect(db_path)
    
    # Initialize v22 database manually
    v22_migration_path = Path.cwd() / "src" / "bet" / "db" / "migrations" / "022_pipeline_runtime_bridge.sql"
    conn.executescript(v22_migration_path.read_text())
    conn.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO schema_meta VALUES ('version', '22')")
    conn.commit()

    # Run init_db which should execute migration 023
    init_db(conn)

    assert get_schema_version(conn) == 27
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(pipeline_provider_observation_attempts)").fetchall()]
    assert "participant_identity_sha256" in cols
    assert "observation_envelope_sha256" in cols

    # Run init_db again to test idempotency
    init_db(conn)
    assert get_schema_version(conn) == 27
    conn.close()


def test_c3_fresh_schema_and_migration_replay_match(tmp_path):
    """C3 test 4: fresh DB schema and migration replay schema are structurally identical."""
    # 1. Fresh DB
    fresh_db = tmp_path / "fresh.db"
    conn_fresh = sqlite3.connect(fresh_db)
    init_db(conn_fresh)
    fresh_cols = [r[1] for r in conn_fresh.execute("PRAGMA table_info(pipeline_provider_observation_attempts)").fetchall()]
    fresh_indexes = [r[1] for r in conn_fresh.execute("PRAGMA index_list(pipeline_provider_observation_attempts)").fetchall()]
    conn_fresh.close()

    # 2. Migrated DB
    mig_db = tmp_path / "migrated.db"
    conn_mig = sqlite3.connect(mig_db)
    # Replay all migrations up to 022, then init_db
    v22_sql = (Path.cwd() / "src" / "bet" / "db" / "migrations" / "022_pipeline_runtime_bridge.sql").read_text()
    conn_mig.executescript(v22_sql)
    conn_mig.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn_mig.execute("INSERT INTO schema_meta VALUES ('version', '22')")
    conn_mig.commit()

    init_db(conn_mig)
    mig_cols = [r[1] for r in conn_mig.execute("PRAGMA table_info(pipeline_provider_observation_attempts)").fetchall()]
    mig_indexes = [r[1] for r in conn_mig.execute("PRAGMA index_list(pipeline_provider_observation_attempts)").fetchall()]
    conn_mig.close()

    assert fresh_cols == mig_cols, f"Fresh cols {fresh_cols} != Migrated cols {mig_cols}"
    assert set(fresh_indexes) == set(mig_indexes), f"Fresh indexes {fresh_indexes} != Migrated indexes {mig_indexes}"


def test_c3_no_dynamic_ddl_and_fail_closed_if_missing(tmp_path):
    """C3 test 3: repository or runtime fails closed when observation schema is missing (no dynamic DDL)."""
    db_path = tmp_path / "legacy_no_schema.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE dummy (id INT)")
    conn.commit()

    try:
        from bet.db.repositories import ProviderObservationAttemptRepository
        repo = ProviderObservationAttemptRepository(conn)
        with pytest.raises((sqlite3.OperationalError, RuntimeError, ValueError), match="PROVIDER_OBSERVATION_SCHEMA_MISSING|no such table"):
            repo.get_attempt_by_id(1)
    except (ImportError, AttributeError):
        pytest.fail("C3 defect: ProviderObservationAttemptRepository missing", pytrace=False)
    finally:
        conn.close()


def test_c3_schema_check_constraints(tmp_path):
    """C3 test 16, 17: check constraints on phase and request_status in database schema."""
    db_path = tmp_path / "constraints.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)

    cur = conn.cursor()

    # Test invalid phase constraint
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute("""
            INSERT INTO pipeline_provider_observation_attempts (
                run_id, phase, attempt_number, canonical_event_id, provider,
                attempted_at_utc, request_status, canonical_event_status, created_at
            ) VALUES ('r1', 'INVALID_PHASE', 1, 'evt_1', 'api_football', '2026-07-30T12:00:00Z', 'SUCCESS', 'SCHEDULED', '2026-07-30T12:00:00Z')
        """)

    # Test invalid request_status constraint
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute("""
            INSERT INTO pipeline_provider_observation_attempts (
                run_id, phase, attempt_number, canonical_event_id, provider,
                attempted_at_utc, request_status, canonical_event_status, created_at
            ) VALUES ('r1', 'PLAN', 1, 'evt_1', 'api_football', '2026-07-30T12:00:00Z', 'INVALID_REQ_STATUS', 'SCHEDULED', '2026-07-30T12:00:00Z')
        """)

    conn.close()
