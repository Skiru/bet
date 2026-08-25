"""Test suite for S2-S8 selection scope enforcement (B19)."""

import sqlite3
from pathlib import Path
import pytest


def test_b19_direct_sql_bypasses_selection_scope(tmp_path):
    """B19: direct SQL and wrapper-specific paths can bypass runtime selection."""
    try:
        from bet.db.repositories import FixtureRepo
        from bet.pipeline.launch_bridge import get_scoped_fixtures_for_stage
        
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE fixtures (id INTEGER PRIMARY KEY, kickoff TEXT)")
        conn.execute("INSERT INTO fixtures VALUES (101, '2026-07-30T15:00:00Z')")
        conn.execute("INSERT INTO fixtures VALUES (102, '2026-07-30T18:00:00Z')")
        conn.commit()
        conn.close()

        # Get scoped fixtures when active selection only contains fixture 101
        fixtures = get_scoped_fixtures_for_stage(
            db_path=db_path,
            stage_id="S2",
            allowed_fixture_ids={101},
        )
        returned_ids = {f["id"] for f in fixtures}
        assert 102 not in returned_ids, "B19 defect: direct SQL query returned excluded fixture 102"
    except (ImportError, AttributeError):
        pytest.fail("B19 defect: get_scoped_fixtures_for_stage missing in production launch_bridge", pytrace=False)
