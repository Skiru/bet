import sqlite3
import pytest


def test_direct_sql_gateway_has_no_empty_scope_fallback(tmp_path):
    from bet.pipeline.runtime_selection import get_scoped_fixtures_for_stage
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY)")
    conn.execute("INSERT INTO fixtures VALUES (1)")
    conn.commit(); conn.close()
    with pytest.raises(ValueError, match="BLOCKED_RUNTIME_SELECTION_REQUIRED"):
        get_scoped_fixtures_for_stage(db, "S2", set())
    assert [row["id"] for row in get_scoped_fixtures_for_stage(db, "S2", {1})] == [1]
