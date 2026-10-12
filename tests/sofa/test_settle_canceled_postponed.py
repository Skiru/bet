"""SETTLE refunds a cancelled match, and a postponed one not played within
VOID_AFTER of the start it was offered at (2026-10-12).

Before this a printed football / tennis leg on such a match stayed ungraded
for good - CANCELED / POSTPONED were plain skips: 15 + 21 printed legs of
2026-10-06..10-11 (Copa Chile Colo-Colo, UTR Belgrade, Samsun, Montenegrin
First League, Saudi Pro League Abha). Superbet's rule (Regulamin 5.E.1.a,
operator 2026-10-07): a match not played within 48 h is void, the stake comes
back. The measured sports already void both (shadow.event_state).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import settleability as st
from bet.sofa.settle import (
    CANCELED,
    POSTPONED_BEYOND_VOID,
    REFUND_REASONS,
    not_played_beyond_void,
    refund_event_ids,
)
from scripts.sofa import audit_settlement, run_settle

DATE = "2026-10-08"
KICKOFF = datetime(2026, 10, 8, 16, 0, tzinfo=UTC)


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _ev(kind: str, offset_h: float = 0.0) -> dict[str, Any]:
    return {
        "id": 1,
        "startTimestamp": int((KICKOFF + timedelta(hours=offset_h)).timestamp()),
        "status": {"type": kind},
    }


# --- the predicates ---------------------------------------------------------


def test_canceled_and_postponed_beyond_void_are_refunds() -> None:
    assert CANCELED in REFUND_REASONS
    assert POSTPONED_BEYOND_VOID in REFUND_REASONS
    assert "POSTPONED" not in REFUND_REASONS  # within 48 h: pending
    assert "ABANDONED" not in REFUND_REASONS


@pytest.mark.parametrize("kind", ["canceled", "cancelled"])
def test_unfinished_reason_names_a_cancelled_match_a_refund(kind: str) -> None:
    assert run_settle.unfinished_reason({"status": {"type": kind}}) == CANCELED


@pytest.mark.parametrize(
    ("kind", "after_h", "void"),
    [("postponed", 49, True), ("postponed", 47, False), ("delayed", 49, True),
     ("notstarted", 72, False), ("finished", 72, False), ("canceled", 72, False)],
)
def test_not_played_beyond_void(kind: str, after_h: float, void: bool) -> None:
    at = KICKOFF + timedelta(hours=after_h)
    assert not_played_beyond_void(_ev(kind), [KICKOFF], at) is void


def test_the_offered_clock_decides_not_sofascores_new_start() -> None:
    # Sofascore moved the postponed match's start to now; the offer was 50 h ago.
    at = KICKOFF + timedelta(hours=50)
    event = _ev("postponed", 50)
    assert not_played_beyond_void(event, [KICKOFF], at)
    # No pipeline clock: Sofascore's own start is read.
    assert not not_played_beyond_void(event, [], at)
    assert not_played_beyond_void(_ev("postponed"), [], at)
    assert not not_played_beyond_void({"status": {"type": "postponed"}}, [], at)


def test_refund_event_ids_and_settleability_read_the_new_reasons() -> None:
    doc = {"skipped_events": [
        {"sofascore_event_id": 1, "skipped": {"CANCELED": 4}},
        {"sofascore_event_id": 2, "skipped": {"POSTPONED_BEYOND_VOID": 2}},
        {"sofascore_event_id": 3, "skipped": {"POSTPONED": 2}},
    ]}
    assert refund_event_ids(doc) == {1: CANCELED, 2: POSTPONED_BEYOND_VOID}
    assert st.reason_class(CANCELED) == st.VOID
    assert st.reason_class(POSTPONED_BEYOND_VOID) == st.VOID
    assert st.reason_class("POSTPONED") == st.NOT_PLAYED


# --- run_settle end to end --------------------------------------------------


def _row(eid: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "sport": "football", "market": "goals_total",
        "subject": "", "line": 2.5, "direction": "OVER",
        "sample_size": 10, "sample_mean": 2.6, "sample_sd": 1.2,
        "p_central": 0.55, "p_bar": 0.55, "market_p": 0.5,
        "offered_odds": 1.9, "verdict": "VALUE",
    }


def _day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: list[int]) -> Path:
    run_dir = tmp_path / "runs" / DATE
    run_dir.mkdir(parents=True)
    (run_dir / "05_sheet.json").write_text(
        json.dumps([_row(i) for i in ids]), encoding="utf-8")
    (run_dir / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": i, "sport": "football", "kickoff_utc": _z(KICKOFF),
         "superbet_kickoff_utc": None, "home_entity_id": 100 + i,
         "away_entity_id": 200 + i,
         "home_name": f"Home {i}", "away_name": f"Away {i}"} for i in ids
    ]), encoding="utf-8")
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.setenv("SOFA_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(run_settle, "SofascoreClient", lambda config: object())
    monkeypatch.setattr(run_settle, "SofaCache", lambda config: object())
    return run_dir


def _skips(run_dir: Path) -> dict[int, dict[str, int]]:
    doc = json.loads((run_dir / "07_settle_skips.json").read_text(encoding="utf-8"))
    return {int(e["sofascore_event_id"]): e["skipped"] for e in doc["skipped_events"]}


def test_settle_refunds_cancelled_and_long_postponed_keeps_a_fresh_postponement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _day(tmp_path, monkeypatch, [1, 2, 3])
    payloads = {
        1: run_settle.Unsettled(CANCELED, _ev("canceled")),
        2: run_settle.Unsettled("POSTPONED", _ev("postponed")),
        3: run_settle.Unsettled("POSTPONED", _ev("postponed")),
    }

    def fake(client: Any, cache: Any, event_id: int, refetch: bool = False) -> Any:
        return payloads[event_id]

    monkeypatch.setattr(run_settle, "_event_payload", fake)
    # Event 3 is still inside the window from its own (later) offered clock.
    fixtures = json.loads((run_dir / "02_fixtures.json").read_text())
    fixtures[2]["kickoff_utc"] = _z(KICKOFF + timedelta(hours=10))
    (run_dir / "02_fixtures.json").write_text(json.dumps(fixtures))
    monkeypatch.setattr(run_settle, "now", lambda: KICKOFF + timedelta(hours=50))
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", DATE])
    run_settle.main()

    skips = _skips(run_dir)
    assert skips[1] == {CANCELED: 1}
    assert skips[2] == {POSTPONED_BEYOND_VOID: 1}
    assert skips[3] == {"POSTPONED": 1}
    # 7c and the ledger read every printed leg on 1 and 2 as a refund.
    refunds = audit_settlement.refund_events(run_dir)
    assert refunds == {1: CANCELED, 2: POSTPONED_BEYOND_VOID}
