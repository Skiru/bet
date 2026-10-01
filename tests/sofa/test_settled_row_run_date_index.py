"""Per-day readers of sofa_settled_row use an index, not a 26M-row scan
(review 2026-10-01)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from bet.sofa.db import migrate


def test_run_date_queries_use_the_index(tmp_path: Path) -> None:
    db = str(tmp_path / "s.db")
    migrate(db)
    plan = sqlite3.connect(db).execute(
        "EXPLAIN QUERY PLAN SELECT * FROM sofa_settled_row WHERE run_date = ?",
        ("2026-09-30",),
    ).fetchall()
    assert any("sofa_settled_row_run_date" in str(row) for row in plan)
