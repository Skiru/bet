from pathlib import Path

from bet.sofa.db import get_connection, migrate


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test.db")

    # Run first time
    migrate(db_path)

    with get_connection(db_path) as conn:
        tables_before = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert "sofa_entity" in tables_before
    assert "sofa_event_stats" in tables_before
    assert "sofa_entity_events" in tables_before
    assert "sofa_settled_row" in tables_before

    # Run second time
    migrate(db_path)

    with get_connection(db_path) as conn:
        tables_after = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert tables_before == tables_after
