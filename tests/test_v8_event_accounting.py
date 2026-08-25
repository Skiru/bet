import sqlite3

import pytest

from bet.db.schema import init_db
from bet.pipeline.runtime_event_classification import (
    RuntimeEventDecision,
    persist_runtime_event_decisions,
)


def _decision(event_id, decision):
    return {
        "canonical_event_id": event_id,
        "fixture_id": int(event_id),
        "decision": decision,
        "input_fingerprint": f"fp-{event_id}",
        "reason": "test",
        "observed_status": "SCHEDULED",
        "observed_kickoff": "2026-07-30T12:00:00+00:00",
    }


def test_59_each_event_gets_one_decision(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    counts = persist_runtime_event_decisions(
        conn,
        "run-1",
        "2026-07-30",
        [_decision("1", RuntimeEventDecision.ANALYZE_FROM_S2)],
    )
    assert counts[RuntimeEventDecision.ANALYZE_FROM_S2.value] == 1


def test_60_event_cannot_have_two_decisions(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    with pytest.raises(ValueError, match="DUPLICATE_CANONICAL_EVENT_ID"):
        persist_runtime_event_decisions(
            conn,
            "run-1",
            "2026-07-30",
            [
                _decision("1", RuntimeEventDecision.ANALYZE_FROM_S2),
                _decision("1", RuntimeEventDecision.ALREADY_VALID_COMPLETE),
            ],
        )


def test_61_multiple_attempts_still_one_final_decision(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    persist_runtime_event_decisions(
        conn,
        "run-1",
        "2026-07-30",
        [_decision("1", RuntimeEventDecision.PROVIDER_RECHECK_REQUIRED)],
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM pipeline_runtime_event_selection"
        ).fetchone()[0]
        == 1
    )


def test_62_accounting_is_exact(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    rows = [
        _decision("1", RuntimeEventDecision.ANALYZE_FROM_S2),
        _decision("2", RuntimeEventDecision.POSTPONED),
    ]
    counts = persist_runtime_event_decisions(conn, "run-1", "2026-07-30", rows)
    assert sum(counts.values()) == len(rows)


def test_63_missing_selection_row_is_error(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    with pytest.raises(ValueError, match="MISSING_CANONICAL_EVENT_ID"):
        persist_runtime_event_decisions(
            conn,
            "run-1",
            "2026-07-30",
            [{"decision": RuntimeEventDecision.ANALYZE_FROM_S2}],
        )


def test_64_duplicate_event_fails_atomically(tmp_path):
    conn = sqlite3.connect(tmp_path / "db.sqlite")
    init_db(conn)
    with pytest.raises(ValueError, match="DUPLICATE_CANONICAL_EVENT_ID"):
        persist_runtime_event_decisions(
            conn,
            "run-1",
            "2026-07-30",
            [
                _decision("1", RuntimeEventDecision.ANALYZE_FROM_S2),
                _decision("1", RuntimeEventDecision.FINISHED),
            ],
        )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM pipeline_runtime_event_selection"
        ).fetchone()[0]
        == 0
    )
