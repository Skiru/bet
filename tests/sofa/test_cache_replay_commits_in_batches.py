"""The streamed cache replay does not hold the write lock for its whole run
(night review 2026-10-04).

write_settled consumes a generator that computes the replay as it goes; one
transaction around it held sofa.db's write lock through all of that
computation, so a settle or a daily loop writing meanwhile failed with
"database is locked". It now commits every WRITE_BATCH rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

import scripts.sofa.calibrate_from_cache as cfc
from bet.sofa.db import migrate
from scripts.sofa.calibrate_from_cache import SettledRow, write_settled


def _replay(event_id: int) -> SettledRow:
    return SettledRow(
        event_id=event_id, sport="football", competition_id=17,
        market="goals_total", subject="", line=2.5, direction="OVER",
        sample_size=10, sample_mean=2.6, sample_sd=1.2, p_central=0.55,
        actual=3.0, outcome="WIN",
    )


def test_another_writer_gets_in_between_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    monkeypatch.setattr(cfc, "WRITE_BATCH", 2)
    other_writes: list[bool] = []

    def rows() -> Iterator[SettledRow]:
        for event_id in range(1, 6):
            if event_id == 5:
                other = sqlite3.connect(db, timeout=0.1)
                try:
                    other.execute("CREATE TABLE IF NOT EXISTS probe (x INTEGER)")
                    other.commit()
                    other_writes.append(True)
                except sqlite3.OperationalError:
                    other_writes.append(False)
                finally:
                    other.close()
            yield _replay(event_id)

    # Row 5 is yielded right after row 4 completed the second batch, i.e.
    # just after a commit: the outside writer must not be locked out.
    assert write_settled(rows(), db) == 5
    assert other_writes == [True]
    with sqlite3.connect(db) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM sofa_settled_row WHERE run_date = 'cache-calibration'"
        ).fetchone()[0]
    assert n == 5


def test_stale_ids_are_still_dropped_after_batched_inserts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    write_settled([_replay(10), _replay(20), _replay(30)], db)
    monkeypatch.setattr(cfc, "WRITE_BATCH", 1)
    write_settled(iter([_replay(10), _replay(30)]), db, drop_event_ids={20, 10})
    with sqlite3.connect(db) as conn:
        ids = {r[0] for r in conn.execute(
            "SELECT sofascore_event_id FROM sofa_settled_row")}
    assert ids == {10, 30}
