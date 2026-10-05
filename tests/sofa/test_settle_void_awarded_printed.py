"""SETTLE repair 4A (plan 2026-10-05): A1 moved beyond the void window, A3
awarded, A4 a printed leg the final SHEET has no row for, A5 7c and the ledger
grading a printed leg from the same rows.

Everton 2026-09-24: event 16997888 was moved 66 h and graded LOSS; Superbet
voids a match not played within 48 h of the start it was offered at.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import settle as settle_mod
from bet.sofa import shadow
from bet.sofa.cs2 import event_state as cs2_event_state
from bet.sofa.db import migrate
from bet.sofa.settle import (
    VOID_AFTER,
    is_completed_event,
    moved_beyond_void,
    refund_event_ids,
    settle_completed,
)
from scripts.sofa import audit_settlement, run_settle, settle_multi_coupon

DATE = "2026-09-24"
KICKOFF = datetime(2026, 9, 24, 18, 0, tzinfo=UTC)


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# A1 / A3 - the predicates
# ---------------------------------------------------------------------------


def _ev(offset_h: float, **extra: Any) -> dict[str, Any]:
    return {
        "id": 1,
        "startTimestamp": int((KICKOFF + timedelta(hours=offset_h)).timestamp()),
        "status": {"type": "finished", "code": 100, "description": "Ended"},
        **extra,
    }


def test_void_after_is_one_constant_for_every_sport() -> None:
    assert VOID_AFTER == timedelta(hours=48)
    assert shadow.VOID_AFTER is settle_mod.VOID_AFTER


@pytest.mark.parametrize(("offset", "moved"), [(66, True), (-66, True), (47, False),
                                               (-47, False), (0, False)])
def test_moved_beyond_void_either_direction(offset: float, moved: bool) -> None:
    assert moved_beyond_void(_ev(offset), [KICKOFF]) is moved


def test_moved_is_measured_from_the_earliest_clock() -> None:
    # Superbet's seen clock followed the move; the earliest clock is the one
    # the leg was printed under.
    later = KICKOFF + timedelta(hours=66)
    assert moved_beyond_void(_ev(66), [later, KICKOFF])


def test_no_start_or_no_clock_is_never_moved() -> None:
    assert not moved_beyond_void({"id": 1}, [KICKOFF])
    assert not moved_beyond_void(_ev(66), [])


def test_an_awarded_result_is_completed_but_not_settleable() -> None:
    awarded = _ev(0, isAwarded=True)
    assert is_completed_event(awarded), "is_completed_event is unchanged"
    assert not settle_completed(awarded)
    assert settle_completed(_ev(0))


def test_refund_event_ids_reads_the_two_reasons_only() -> None:
    doc = {"skipped_events": [
        {"sofascore_event_id": 1, "skipped": {"MOVED_BEYOND_VOID": 3}},
        {"sofascore_event_id": 2, "skipped": {"AWARDED": 1}},
        {"sofascore_event_id": 3, "skipped": {"NOT_FINISHED": 2}},
    ]}
    assert refund_event_ids(doc) == {1: "MOVED_BEYOND_VOID", 2: "AWARDED"}
    assert refund_event_ids(None) == {}
    assert refund_event_ids({}) == {}


def test_shadow_build_result_refuses_an_awarded_game() -> None:
    detail = {
        "isAwarded": True,
        "status": {"type": "finished", "code": 100, "description": "Ended"},
        "winnerCode": 2,
        "homeScore": {"current": 0, "period1": 0, "period2": 0, "period3": 0},
        "awayScore": {"current": 3, "period1": 25, "period2": 25, "period3": 25},
    }
    sport = shadow.SPORTS["volleyball"]
    assert shadow.build_result(detail, sport, True) is None
    # The same payload without the flag would grade as a 0-3 - the check is
    # what keeps a forfeit's paper score out.
    assert shadow.build_result({**detail, "isAwarded": False}, sport, True) is not None


def test_cs2_already_refuses_a_walkover_and_an_awarded_series() -> None:
    now = KICKOFF + timedelta(hours=3)
    for description in ("Walkover", "Awarded"):
        detail = {"status": {"type": "finished", "description": description}}
        assert cs2_event_state(detail, KICKOFF, now) == "UNUSUAL"
    ended = {"status": {"type": "finished", "description": "Ended"}}
    assert cs2_event_state(ended, KICKOFF, now) == "FINISHED"


# ---------------------------------------------------------------------------
# run_settle end to end
# ---------------------------------------------------------------------------


def _row(eid: int, market: str = "goals_total", line: float = 2.5,
         subject: str = "") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "sport": "football", "market": market,
        "subject": subject, "line": line, "direction": "OVER",
        "sample_size": 10, "sample_mean": 2.6, "sample_sd": 1.2,
        "p_central": 0.55, "p_bar": 0.55, "market_p": 0.5,
        "offered_odds": 1.9, "verdict": "VALUE",
    }


def _event(eid: int, offset_h: float, **extra: Any) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": int((KICKOFF + timedelta(hours=offset_h)).timestamp()),
        "status": {"type": "finished", "code": 100, "description": "Ended"},
        "homeScore": {"current": 2}, "awayScore": {"current": 1},
        "homeTeam": {"id": 100 + eid}, "awayTeam": {"id": 200 + eid},
        "tournament": {"uniqueTournament": {"id": 17}},
        **extra,
    }


def _day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
         sheet: list[dict[str, Any]], ids: list[int]) -> Path:
    run_dir = tmp_path / "runs" / DATE
    run_dir.mkdir(parents=True)
    (run_dir / "05_sheet.json").write_text(json.dumps(sheet), encoding="utf-8")
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


def _payloads(events: dict[int, Any]) -> Any:
    def fake(client: Any, cache: Any, event_id: int, refetch: bool = False) -> Any:
        got = events[event_id]
        if isinstance(got, str):
            return got
        return got, {"statistics": []}, {"incidents": []}
    return fake


def _run(monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["run_settle", "--date", DATE])
    return run_settle.main()


def _db_rows(tmp_path: Path) -> list[tuple[Any, ...]]:
    con = sqlite3.connect(tmp_path / "sofa.db")
    try:
        return con.execute(
            "select sofascore_event_id, outcome from sofa_settled_row order by 1"
        ).fetchall()
    finally:
        con.close()


def _skips(run_dir: Path) -> dict[int, dict[str, int]]:
    doc = json.loads((run_dir / "07_settle_skips.json").read_text(encoding="utf-8"))
    return {int(e["sofascore_event_id"]): e["skipped"] for e in doc["skipped_events"]}


def test_a_match_moved_66_h_either_way_writes_no_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet = [_row(1), _row(2), _row(3), _row(3, "corners_total")]
    run_dir = _day(tmp_path, monkeypatch, sheet, [1, 2, 3])
    monkeypatch.setattr(run_settle, "_event_payload", _payloads(
        {1: _event(1, 66), 2: _event(2, -66), 3: _event(3, 47)}))
    _run(monkeypatch)
    assert _db_rows(tmp_path) == [(3, "WIN")], "only the +47 h match is graded"
    skips = _skips(run_dir)
    assert skips[1] == {"MOVED_BEYOND_VOID": 1}
    assert skips[2] == {"MOVED_BEYOND_VOID": 1}
    assert "MOVED_BEYOND_VOID" not in skips.get(3, {})


def test_an_unfinished_match_moved_beyond_the_window_is_void_not_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _day(tmp_path, monkeypatch, [_row(1)], [1])
    unplayed = _event(1, 66, status={"type": "notstarted"})
    monkeypatch.setattr(run_settle, "_event_payload", _payloads(
        {1: run_settle.Unsettled("NOT_FINISHED", unplayed)}))
    _run(monkeypatch)
    assert _skips(run_dir)[1] == {"MOVED_BEYOND_VOID": 1}


def test_the_seen_superbet_clock_is_one_of_the_clocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 02_fixtures says 18:00 on the day; OFFER saw Superbet start it 50 h
    # earlier - the earliest clock decides, so a +10 h Sofascore start is
    # 60 h from it.
    run_dir = _day(tmp_path, monkeypatch, [_row(1)], [1])
    (run_dir / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": 1,
         "superbet_kickoff_seen_utc": _z(KICKOFF - timedelta(hours=50))}]))
    monkeypatch.setattr(run_settle, "_event_payload", _payloads({1: _event(1, 10)}))
    _run(monkeypatch)
    assert _skips(run_dir)[1] == {"MOVED_BEYOND_VOID": 1}
    assert _db_rows(tmp_path) == []


def test_event_payload_says_awarded() -> None:
    class Client:
        def event(self, event_id: int) -> dict[str, Any]:
            return {"event": _event(event_id, 0, isAwarded=True)}

    class Cache:
        def save_event_detail(self, *_: Any) -> None: ...

    got = run_settle._event_payload(Client(), Cache(), 5)  # type: ignore[arg-type]
    assert got == "AWARDED"
    assert isinstance(got, run_settle.Unsettled) and got.event is not None


def test_an_awarded_match_writes_no_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _day(tmp_path, monkeypatch, [_row(1), _row(2)], [1, 2])
    monkeypatch.setattr(run_settle, "_event_payload", _payloads({
        1: run_settle.Unsettled("AWARDED", _event(1, 0, isAwarded=True)),
        2: _event(2, 0)}))
    _run(monkeypatch)
    assert _db_rows(tmp_path) == [(2, "WIN")]
    assert _skips(run_dir)[1] == {"AWARDED": 1}


# ---------------------------------------------------------------------------
# A4 - a printed leg with no SHEET row
# ---------------------------------------------------------------------------


def _single(eid: int, market: str = "goals_total", line: float = 2.5,
            odds: float = 1.9) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football", "market": market,
            "subject": "", "line": line, "direction": "OVER",
            "offered_odds": odds, "confidence": 0.8,
            "match": f"Home {eid} - Away {eid}"}


def _artifact(run_dir: Path, singles: list[dict[str, Any]],
              builders: list[dict[str, Any]] | None = None) -> None:
    doc = {
        "created_at_utc": _z(KICKOFF - timedelta(hours=6)),
        "profile": "standard",
        "confidence_floor": 0.7, "min_ev": 0.9, "max_overround": 0.15,
        "pdf_max_singles": None, "prints_builders": True,
        "legs": singles, "singles": singles, "builders": builders or [],
    }
    (run_dir / "08_confidence.json").write_text(json.dumps(doc), encoding="utf-8")


def test_a_printed_leg_without_a_sheet_row_is_graded_beside_the_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Event 2 was printed, started, then OFFER dropped it and SHEET has no row.
    run_dir = _day(tmp_path, monkeypatch, [_row(1)], [1, 2])
    _artifact(run_dir, [_single(1), _single(2)])
    monkeypatch.setattr(run_settle, "_event_payload", _payloads(
        {1: _event(1, 0), 2: _event(2, 0)}))
    _run(monkeypatch)
    assert _db_rows(tmp_path) == [(1, "WIN")], "the A4 leg never enters the DB"
    printed = json.loads((run_dir / "07_settled_printed.json").read_text())
    assert [(r["sofascore_event_id"], r["market"], r["outcome"], r["actual_value"])
            for r in printed] == [(2, "goals_total", "WIN", 3.0)]
    assert printed[0]["source"] == "event_payload"
    assert "p_bar" not in printed[0] and "sample_mean" not in printed[0]


def test_a_day_without_such_legs_writes_no_printed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir = _day(tmp_path, monkeypatch, [_row(1)], [1])
    _artifact(run_dir, [_single(1)])
    monkeypatch.setattr(run_settle, "_event_payload", _payloads({1: _event(1, 0)}))
    _run(monkeypatch)
    assert not (run_dir / "07_settled_printed.json").exists()


# ---------------------------------------------------------------------------
# 7c and the ledger: refunds, A4, A5 - one source
# ---------------------------------------------------------------------------


def _insert(db: Path, run_date: str, eid: int, outcome: str,
            market: str = "goals_total", line: float = 2.5) -> None:
    migrate(str(db))
    con = sqlite3.connect(db)
    con.execute(
        "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
        " competition_id, market, subject, line, direction, sample_size,"
        " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
        " outcome, settled_at, offered_odds, verdict) values"
        " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_date, eid, "football", 9, market, "", line, "OVER", 10, 2.6, 1.2,
         0.6, 0.6, 0.5, 3.0 if outcome == "WIN" else 1.0, outcome,
         _z(KICKOFF), 1.9, "VALUE"),
    )
    con.commit()
    con.close()


def _ledger(runs: Path, db: Path) -> dict[str, Any]:
    from scripts.sofa.record_results import confidence_rows

    rows = {r["variant"]: r for r in confidence_rows(str(runs), DATE, str(db))}
    return rows["official"]


def _seven_c(run_dir: Path, db: Path, singles: list[dict[str, Any]]) -> dict[str, Any]:
    keys = {audit_settlement._key(s) for s in singles}
    by_key = audit_settlement.coupon_settled_by_key(str(db), run_dir, DATE, keys)
    return audit_settlement.settle_singles(singles, by_key)


def test_a_moved_leg_is_a_refund_in_7c_and_the_ledger_never_a_loss(
    tmp_path: Path,
) -> None:
    runs = tmp_path / "runs"
    run_dir = runs / DATE
    run_dir.mkdir(parents=True)
    db = tmp_path / "s.db"
    singles = [_single(1), _single(2, odds=2.0), _single(3)]
    _artifact(run_dir, singles)
    _insert(db, DATE, 2, "WIN")
    # The moved match was played (and priced) three days later: that day's
    # row must not grade this day's void bet.
    _insert(db, "2026-09-27", 1, "LOSS")
    (run_dir / "07_settle_skips.json").write_text(json.dumps({"skipped_events": [
        {"sofascore_event_id": 1, "skipped": {"MOVED_BEYOND_VOID": 1}},
        {"sofascore_event_id": 3, "skipped": {"AWARDED": 1}},
    ]}))

    res = _seven_c(run_dir, db, singles)
    assert (res["won"], res["lost"], res["refunded"], res["unsettled"]) == (1, 0, 2, 0)
    assert res["units"] == pytest.approx(1.0)
    table = dict((str(a), b) for a, b in audit_settlement.singles_summary_rows(3, res))
    assert table["zwrot (mecz przesunięty > 48 h / przyznany), 0 j."] == 2

    led = _ledger(runs, db)
    assert led["refunded"] == 2
    assert led["outcomes"] == {"REFUND": 2, "WIN": 1}
    s = led["singles"]
    assert (s["settled"], s["won"], s["lost"]) == (1, 1, 0)
    assert led["singles"]["units"] == pytest.approx(1.0)
    assert led["pending"] == 0


def test_a_refunded_builder_is_zwrot() -> None:
    assert audit_settlement.slip_status(["REFUND", "REFUND"]) == "ZWROT"
    [], [b] = settle_multi_coupon.grade_confidence_positions(
        [], [{"source": {"sofascore_event_id": 1, "odds_if_product": 3.0,
                         "legs": [{"market": "goals_total", "subject": "",
                                   "line": 2.5, "direction": "OVER"}]}}],
        {(1, "goals_total", "", 2.5, "OVER"): {"outcome": "REFUND"}}, {})
    assert b["outcome"] == "REFUND"


def test_an_old_day_reads_exactly_as_before(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    run_dir = runs / DATE
    run_dir.mkdir(parents=True)
    db = tmp_path / "s.db"
    singles = [_single(1), _single(2)]
    _artifact(run_dir, singles)
    _insert(db, DATE, 1, "LOSS")
    res = _seven_c(run_dir, db, singles)
    assert (res["won"], res["lost"], res["refunded"], res["unsettled"]) == (0, 1, 0, 1)
    labels = [r[0] for r in audit_settlement.singles_summary_rows(2, res)]
    assert not any("zwrot" in str(x) for x in labels), "no new row on an old day"


def test_7c_and_the_ledger_grade_printed_legs_from_the_same_rows(
    tmp_path: Path,
) -> None:
    # Event 4 is not on the final sheet (OFFER dropped it after the start);
    # its row sits under the previous day. Event 5 has only an A4 grade.
    runs = tmp_path / "runs"
    run_dir = runs / DATE
    run_dir.mkdir(parents=True)
    db = tmp_path / "s.db"
    singles = [_single(1), _single(4, odds=2.2), _single(5, odds=1.7)]
    _artifact(run_dir, singles)
    (run_dir / "05_sheet.json").write_text(json.dumps([_row(1)]))
    _insert(db, DATE, 1, "LOSS")
    _insert(db, "2026-09-23", 4, "WIN")
    (run_dir / "07_settled_printed.json").write_text(json.dumps([
        {"run_date": DATE, "sofascore_event_id": 5, "market": "goals_total",
         "subject": "", "line": 2.5, "direction": "OVER", "actual_value": 3.0,
         "outcome": "WIN", "source": "event_payload"}]))

    res = _seven_c(run_dir, db, singles)
    led = _ledger(runs, db)["singles"]
    assert (res["won"], res["lost"], res["unsettled"]) == (2, 1, 0)
    assert (led["won"], led["lost"], led["settled"]) == (res["won"], res["lost"],
                                                         res["settled"])
    assert led["units"] == pytest.approx(res["units"]) == pytest.approx(0.9)
