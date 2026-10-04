"""The cache replay deletes the rows it once stored under a duplicate
listing's other event id (2026-10-02).

calibrate_from_cache collapses a match listed twice to its lowest event id
(one_listing_per_match), but upserts on the event id, so the rows an earlier
run had written under the other id stayed in sofa_settled_row and every fit
kept reading the match twice.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from bet.sofa.db import migrate
from scripts.sofa.calibrate_from_cache import SettledRow, load_cache, write_settled


def _replay(event_id: int) -> SettledRow:
    return SettledRow(
        event_id=event_id, sport="football", competition_id=17,
        market="goals_total", subject="", line=2.5, direction="OVER",
        sample_size=10, sample_mean=2.6, sample_sd=1.2, p_central=0.55,
        actual=3.0, outcome="WIN",
    )


def _ids(db: Path, run_date: str) -> set[int]:
    with sqlite3.connect(db) as conn:
        return {r[0] for r in conn.execute(
            "SELECT sofascore_event_id FROM sofa_settled_row WHERE run_date = ?",
            (run_date,))}


def test_load_cache_reports_the_ids_the_collapse_dropped(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))

    def event(eid: int) -> dict[str, Any]:
        return {"id": eid, "status": {"type": "finished"},
                "startTimestamp": 1_780_000_000,
                "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 2, "name": "B"},
                "homeScore": {"current": 1}, "awayScore": {"current": 0},
                "tournament": {"uniqueTournament": {"id": 17},
                               "category": {"sport": {"slug": "football"}}}}

    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO sofa_entity_events VALUES (1, 'last', 0, 'x', ?)",
                     (json.dumps({"events": [event(20), event(10)]}),))
    dropped: set[int] = set()
    played = load_cache(db, dropped)
    assert dropped == {20}
    assert all(p.event_id != 20 for p in played)


def test_write_settled_deletes_only_the_dropped_ids_replay_rows(tmp_path: Path) -> None:
    db = tmp_path / "sofa.db"
    migrate(str(db))
    # An earlier replay stored the match under both ids.
    write_settled([_replay(10), _replay(20), _replay(30)], db)
    # A live SETTLE row of the dropped id, on another market.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, actual_value, outcome,"
            " settled_at) VALUES ('2026-09-28', 20, 'football', 17, 'corners_total',"
            " '', 9.5, 'OVER', 10, 9.0, 2.0, 0.5, 0.5, 11, 'WIN', 'x')")

    write_settled([_replay(10), _replay(30)], db, drop_event_ids={20, 10})
    assert _ids(db, "cache-calibration") == {10, 30}, "an id being written stays"
    assert _ids(db, "2026-09-28") == {20}, "a live row is never deleted"


def test_the_stale_delete_reads_the_event_id_index(tmp_path: Path) -> None:
    # Since the replay streams its rows, the stale ids are deleted AFTER ~59M
    # cache rows are written; through the run_date index each DELETE read all
    # of them, and the 2026-10-04 rehearsal stood there for hours.
    from scripts.sofa.calibrate_from_cache import _DELETE_STALE_REPLAY_ROWS

    db = tmp_path / "sofa.db"
    migrate(str(db))
    with sqlite3.connect(db) as conn:
        plan = " ".join(
            str(r[-1]) for r in conn.execute(
                "EXPLAIN QUERY PLAN " + _DELETE_STALE_REPLAY_ROWS, (1,))
        )
    assert "sofascore_event_id=?" in plan, plan
    assert "run_date" not in plan, plan
