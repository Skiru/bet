"""Settleability (plan 2026-10-05, F0.6): when a printed leg was graded, the
day selection of the D-14..D-2 re-settle sweep, the fitted NOT_SETTLEABLE
list and its epoch."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import settleability as st
from bet.sofa.db import migrate
from bet.sofa.sport_confidence import wilson_lo

DAY = "2026-09-26"
H = st.horizon_end(DAY)  # 2026-09-30T00:00Z


def _leg(eid: int = 1, market: str = "corners_total", cid: int | None = 173,
         profiles: tuple[str, ...] = ("standard",)) -> st.PrintedLeg:
    return st.PrintedLeg(DAY, (eid, market, "", 9.5, "UNDER"), "football", cid,
                         "National League", set(profiles))


# --- reasons and families ---------------------------------------------------


def test_reason_classes() -> None:
    assert st.reason_class("corners_total:STAT_KEY_ABSENT") == st.DATA_GAP
    assert st.reason_class("NO_STATISTICS") == st.DATA_GAP
    assert st.reason_class("POSTPONED") == st.NOT_PLAYED
    assert st.reason_class("FINISHED_ABNORMALLY") == st.NOT_PLAYED
    assert st.reason_class("SUBJECT_NOT_MATCHED") == st.IDENTITY
    assert st.reason_class("PLAYER_SOMETHING_NEW") == st.IDENTITY
    assert st.reason_class("MOVED_BEYOND_VOID") == st.VOID
    assert st.reason_class("PUSH") == st.VOID
    assert st.reason_class("PROVIDER_ERROR") == st.PROVIDER
    assert st.reason_class(None) == st.UNKNOWN


def test_the_refetched_gaps_are_data_gaps() -> None:
    from scripts.sofa.run_settle import STAT_GAP_REASONS

    assert set(STAT_GAP_REASONS) <= st.DATA_GAP_REASONS
    assert set(STAT_GAP_REASONS) <= st.RESETTLE_REASONS


def test_settle_family() -> None:
    assert st.settle_family("corners_1h_for") == "corners"
    assert st.settle_family("corners_total") == "corners"
    assert st.settle_family("goals_2h_total") == "goals"
    assert st.settle_family("games_won_for") == "games"
    assert st.settle_family("player_shots_for") == "player_props"
    assert st.settle_family("most_corners") == "corners"


def test_leg_reason_prefers_the_markets_own_gap_and_a_refund() -> None:
    reasons = {"corners_total:STAT_KEY_ABSENT": 2, "PLAYER_NOT_MATCHED": 5,
               "goals_total:NO_STATISTICS": 1}
    assert st.leg_reason("corners_total", reasons) == "corners_total:STAT_KEY_ABSENT"
    assert st.leg_reason("fouls_total", reasons) == "PLAYER_NOT_MATCHED"
    assert st.leg_reason("x", {"MOVED_BEYOND_VOID": 3, "x:NO_STATISTICS": 1}) == (
        "MOVED_BEYOND_VOID")
    assert st.leg_reason("x", None) is None


# --- one leg's state --------------------------------------------------------


def test_classify_every_state() -> None:
    legs = [_leg(i) for i in range(1, 8)]
    grades = {
        legs[0].key: st.Grade("WIN", H - timedelta(hours=1)),
        legs[1].key: st.Grade("LOSS", H + timedelta(days=3)),  # late, data
        legs[2].key: st.Grade("LOSS", H + timedelta(days=3)),  # late, process
        legs[6].key: st.Grade("WIN", None),  # time unknown: by the horizon
    }
    reasons = {4: {"corners_total:NO_STATISTICS": 1}, 5: {"CANCELED": 1},
               6: {"MOVED_BEYOND_VOID": 1}}
    fetched = {2: H + timedelta(days=3), 3: H - timedelta(days=2)}
    states = st.classify(legs, grades, reasons, H, fetched)
    got = [(s.leg.key[0], s.status, s.reason_class, s.late_cause) for s in states]
    assert got == [
        (1, st.GRADED_BY_HORIZON, "", None),
        (2, st.GRADED_LATER, "", st.LATE_DATA),
        (3, st.GRADED_LATER, "", st.LATE_PROCESS),
        (4, st.UNGRADED, st.DATA_GAP, None),
        (5, st.UNGRADED, st.NOT_PLAYED, None),
        (6, st.VOIDED, st.VOID, None),
        (7, st.GRADED_BY_HORIZON, "", None),
    ]
    t = st.Tally()
    for s in states:
        t.add(s)
    d = t.as_dict()
    assert (d["printed"], d["voided"], d["due"]) == (7, 1, 6)
    assert d["unsettled_at_horizon"] == 4  # 2 late + 2 ungraded
    assert d["graded_later_process"] == 1
    # The fit judges graded and data-gap legs; a cancelled match says nothing.
    assert (d["judged"], d["data_unsettled"]) == (5, 2)


def test_a_refund_overrides_a_row() -> None:
    leg = _leg(1)
    states = st.classify([leg], {leg.key: st.Grade("LOSS", H)},
                         {1: {"AWARDED": 1}}, H)
    assert states[0].status == st.VOIDED


def test_horizon_is_the_end_of_d_plus_3() -> None:
    assert st.horizon_end("2026-09-26") == datetime(2026, 9, 30, tzinfo=UTC)


# --- grade times from the DB and the regrade logs ---------------------------


def _db(tmp_path: Path) -> sqlite3.Connection:
    path = tmp_path / "sofa.db"
    migrate(str(path))
    return sqlite3.connect(path)


def _insert(conn: sqlite3.Connection, run_date: str, eid: int, at: str,
            outcome: str = "WIN") -> int:
    cur = conn.execute(
        "INSERT INTO sofa_settled_row (run_date, sofascore_event_id, sport, "
        "competition_id, market, subject, line, direction, sample_size, "
        "sample_mean, sample_sd, p_central, p_bar, actual_value, outcome, "
        "settled_at) VALUES (?, ?, 'football', 173, 'corners_total', '', 9.5, "
        "'UNDER', 10, 9, 2, 0.7, 0.7, 8, ?, ?)",
        (run_date, eid, outcome, at))
    conn.commit()
    return int(cur.lastrowid or 0)


def test_first_graded_time_survives_a_regrade(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    rid = _insert(conn, DAY, 1, "2026-10-04T08:00:00+00:00")  # regraded 10-04
    logs = [[{"id": rid, "old_settled_at": "2026-09-27T05:00:00+00:00"}],
            [{"id": rid, "old_settled_at": "2026-10-01T05:00:00+00:00"}],
            {"mode": "moved_void", "actions": []}]
    first = st.first_graded_times(logs)
    grades = st.db_grades(conn, DAY, {1}, first)
    assert grades[(1, "corners_total", "", 9.5, "UNDER")].graded_at == datetime(
        2026, 9, 27, 5, tzinfo=UTC)


def test_db_grades_reads_another_live_date_never_the_replay(tmp_path: Path) -> None:
    conn = _db(tmp_path)
    _insert(conn, "2026-09-27", 1, "2026-09-28T05:00:00+00:00")
    _insert(conn, "cache-calibration", 2, "2026-09-20T05:00:00+00:00")
    grades = st.db_grades(conn, DAY, {1, 2}, {})
    assert set(k[0] for k in grades) == {1}


# --- the printed legs -------------------------------------------------------


def _single(eid: int, market: str = "corners_total") -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football", "market": market,
            "subject": "", "line": 9.5, "direction": "UNDER", "confidence": 0.8,
            "offered_odds": 1.3, "competition": "From the leg"}


def test_printed_legs_unites_the_profiles(tmp_path: Path) -> None:
    run = tmp_path / DAY
    run.mkdir()
    (run / "02_fixtures.json").write_text(json.dumps([
        {"sofascore_event_id": 1, "sport": "football", "competition_id": 173,
         "competition_name": "National League"}]))
    # The official PDF printed the first single only (pdf_max_singles 1).
    (run / "08_confidence.json").write_text(json.dumps(
        {"singles": [_single(1), _single(2)], "pdf_max_singles": 1, "builders": []}))
    (run / "08_confidence_wariant.json").write_text(json.dumps(
        {"singles": [_single(1), _single(3, "goals_total")],
         "pdf_max_singles": None, "builders": []}))
    legs = st.printed_legs(run, DAY, st.load_fixtures(run))
    by_eid = {lg.key[0]: lg for lg in legs}
    assert set(by_eid) == {1, 3}
    assert by_eid[1].profiles == {"standard", "wariant"}
    assert by_eid[1].competition_id == 173
    assert by_eid[3].competition_id is None
    assert by_eid[3].competition_name == "From the leg"


# --- the fit ----------------------------------------------------------------


def _states(cid: int, data_unsettled: int, graded: int,
            market: str = "corners_total") -> list[st.LegState]:
    out = []
    for i in range(data_unsettled):
        out.append(st.LegState(_leg(1000 + i, market, cid), st.UNGRADED,
                               f"{market}:NO_STATISTICS", st.DATA_GAP, None))
    for i in range(graded):
        out.append(st.LegState(_leg(2000 + i, market, cid), st.GRADED_BY_HORIZON,
                               None, "", None))
    return out


def test_fit_needs_enough_legs_and_a_lower_bound_above_the_threshold() -> None:
    assert wilson_lo(3, 8) > st.MAX_UNSETTLED_LOWER >= wilson_lo(2, 8)
    states = (
        _states(1, 3, 5)  # 3/8: listed
        + _states(2, 2, 6)  # 2/8: not
        + _states(3, 5, 1)  # 5/6: under MIN_LEGS
        + _states(4, 3, 5, "goals_total")  # its own family
        + [st.LegState(_leg(9, cid=5), st.UNGRADED, "CANCELED", st.NOT_PLAYED, None)]
        * 20  # not played: never judged
    )
    refused = st.fit_refusals(states)
    assert [(e["competition_id"], e["family"]) for e in refused] == [
        (1, "corners"), (4, "goals")]
    assert refused[0]["judged"] == 8 and refused[0]["data_unsettled"] == 3


def test_fit_never_lists_a_leg_without_a_competition() -> None:
    assert st.fit_refusals(_states(1, 10, 0)[:0] + [
        st.LegState(_leg(i, cid=None), st.UNGRADED, "NO_STATISTICS", st.DATA_GAP,
                    None) for i in range(20)]) == []


def test_fit_script_reads_closed_days_and_writes_metadata() -> None:
    from scripts.sofa.fit_settleability import build_doc, closed_days

    days = closed_days("2026-09-28", "2026-10-05", 3)
    assert days == ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    doc = build_doc(_states(1, 3, 5), before="2026-10-05", start="2026-09-28",
                    days=days, horizon_days=3, min_legs=8,
                    max_unsettled_lower=0.10, stamp={"fitted_at_utc": "x"})
    meta = doc["fitted_from"]
    assert meta["before"] == "2026-10-05" and meta["never_mid_day"] is True
    assert meta["legs_judged"] == 8 and meta["fitted_at_utc"] == "x"
    assert [e["competition_id"] for e in doc["refused"]] == [1]


def test_fit_script_refuses_a_future_before(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.sofa import fit_settleability

    monkeypatch.setenv("SOFA_NOW", "2026-10-05T12:00:00Z")
    monkeypatch.setattr(sys, "argv", ["fit", "--before", "2026-10-06", "--dry-run"])
    assert fit_settleability.main() == 2
    assert "after today" in capsys.readouterr().err


# --- the gate ---------------------------------------------------------------


def test_the_gate_reads_the_fitted_file(tmp_path: Path) -> None:
    assert not st.Settleability.load(tmp_path / "absent.json").fitted
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"fitted_from": {"before": "2026-10-06"},
                                "refused": [{"competition_id": 173,
                                             "family": "corners"}]}))
    gate = st.Settleability.load(path)
    assert gate.fitted and gate.fitted_before == "2026-10-06"
    assert gate.refuses(173, "corners_1h_for")
    assert gate.refuses(173, "corners_total")
    assert not gate.refuses(173, "goals_total")
    assert not gate.refuses(174, "corners_total")
    assert not gate.refuses(None, "corners_total")


def test_the_installed_file_loads() -> None:
    path = Path(__file__).resolve().parents[2] / "config" / st.SETTLEABILITY_FILE
    gate = st.Settleability.load(path)
    assert gate.fitted and gate.refused
    doc = json.loads(path.read_text())
    assert doc["fitted_from"]["before"] and doc["fitted_from"]["fitted_at_utc"]


def test_the_epoch_starts_on_10_06() -> None:
    at = epochs.SETTLEABILITY_FROM_UTC
    assert at == datetime(2026, 10, 6, tzinfo=UTC)
    assert epochs.settleability_gate("2026-10-06", at)
    assert epochs.settleability_gate("2026-10-07", at + timedelta(days=1))
    # 10-05 was live: a rebuild of it after midnight keeps its rule.
    assert not epochs.settleability_gate("2026-10-05", at + timedelta(hours=1))
    # A build of 10-06 before the cutover (none is planned) is not gated.
    assert not epochs.settleability_gate("2026-10-06", at - timedelta(seconds=1))


# --- CONFIDENCE end to end --------------------------------------------------


def _confidence_day(tmp_path: Path) -> Path:
    from tests.sofa.test_stats_only_confidence import KO, _conf, _day, _row, _under

    p = 0.75
    odds = round(0.95 / _conf(p), 2)
    return _day(tmp_path, [_row(1, p, odds, 0.70)], {1: KO[1]},
                {1: (odds, _under(odds))})


def _confidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                refused: list[dict[str, Any]] | None) -> tuple[dict[str, Any], str]:
    from tests.sofa.test_stats_only_confidence import _doc, _run

    runs = _confidence_day(tmp_path)
    path = tmp_path / "settleability.json"
    if refused is not None:
        path.write_text(json.dumps({"fitted_from": {"before": "2026-10-06"},
                                    "refused": refused}))
    monkeypatch.setattr(st, "DEFAULT_SETTLEABILITY", path)
    assert _run(runs, monkeypatch) == 0
    return _doc(runs), ""


def test_confidence_refuses_a_listed_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The fixture of test_locked_print is competition 9; the row goals_total.
    doc, _ = _confidence(tmp_path, monkeypatch,
                         [{"competition_id": 9, "family": "goals"}])
    out = capsys.readouterr().out
    assert doc["singles"] == []
    assert '"NOT_SETTLEABLE": 1' in out


def test_confidence_keeps_an_unlisted_cell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc, _ = _confidence(tmp_path, monkeypatch,
                         [{"competition_id": 9, "family": "corners"}])
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [1]
    assert "NOT_SETTLEABLE" not in capsys.readouterr().out


def test_confidence_says_when_the_list_is_not_fitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    doc, _ = _confidence(tmp_path, monkeypatch, None)
    assert [s["sofascore_event_id"] for s in doc["singles"]] == [1]
    assert "SETTLEABILITY_NOT_FITTED" in capsys.readouterr().err


def test_confidence_refuses_after_the_operator_and_before_the_curve() -> None:
    source = (Path(__file__).resolve().parents[2]
              / "scripts/sofa/run_confidence.py").read_text()
    i = source.index("refused[NOT_SETTLEABLE] += 1")
    assert source.index('refused["OPERATOR_REFUSED"]') < i
    assert i < source.index("hit = cal.realised(")


# --- the sweep --------------------------------------------------------------


def test_days_needing_resettle() -> None:
    leg = _leg(1)
    states = {
        "2026-09-20": [st.LegState(leg, st.GRADED_BY_HORIZON, None, "", None)],
        "2026-09-21": [st.LegState(leg, st.UNGRADED, "CANCELED", st.NOT_PLAYED, None),
                       st.LegState(leg, st.UNGRADED, "SUBJECT_NOT_MATCHED",
                                   st.IDENTITY, None),
                       st.LegState(leg, st.VOIDED, "MOVED_BEYOND_VOID", st.VOID, None)],
        "2026-09-22": [st.LegState(leg, st.UNGRADED, "corners_total:STAT_KEY_ABSENT",
                                   st.DATA_GAP, None)] * 2,
        "2026-09-23": [st.LegState(leg, st.UNGRADED, None, st.UNKNOWN, None)],
        "2026-09-24": [st.LegState(leg, st.UNGRADED, "POSTPONED", st.NOT_PLAYED, None),
                       st.LegState(leg, st.UNGRADED, "PROVIDER_ERROR", st.PROVIDER,
                                   None)],
        "2026-09-25": [],
    }
    assert st.days_needing_resettle(states) == {
        "2026-09-22": 2, "2026-09-23": 1, "2026-09-24": 2}


def test_sweep_range_is_d14_to_d2() -> None:
    assert st.sweep_range("2026-10-05") == ("2026-09-21", "2026-10-03")
    assert st.date_range("2026-09-30", "2026-10-02") == [
        "2026-09-30", "2026-10-01", "2026-10-02"]


def test_bridge_ready() -> None:
    assert st.bridge_ready(None)[0] is False
    assert st.bridge_ready({"ok": True})[0] is False
    assert st.bridge_ready({"last_pull_age_s": 300})[0] is False
    assert st.bridge_ready({"last_pull_age_s": 2.0}) == (True, "")


def test_sweep_verdict() -> None:
    assert st.sweep_verdict({}, False, False, None) == "PARTIAL"
    assert st.sweep_verdict({"a": 1, "b": 0}, False, True, 1) == "OK"
    assert st.sweep_verdict({"a": 2, "b": 1}, False, True, 0) == "PARTIAL"
    assert st.sweep_verdict({"a": 2}, False, True, 0) == "FAILED"
    assert st.sweep_verdict({"a": 1}, True, True, 0) == "PARTIAL"
    assert st.sweep_verdict({"a": 1}, False, True, 2) == "PARTIAL"
    assert st.sweep_verdict({}, False, True, None) == "OK"


def _sweep(monkeypatch: pytest.MonkeyPatch, todo: dict[str, int],
           health: dict[str, Any] | None, argv: list[str]) -> tuple[int, list[Any]]:
    from scripts.sofa import resettle_sweep

    calls: list[Any] = []
    monkeypatch.setattr(resettle_sweep, "plan", lambda *a, **k: dict(todo))
    monkeypatch.setattr(resettle_sweep, "bridge_health", lambda: health)

    def fake_run(cmd: list[str]) -> tuple[int, dict[str, Any]]:
        calls.append(cmd)
        return 1, {"metrics": {"breaker_open": False}}

    monkeypatch.setattr(resettle_sweep, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["resettle_sweep.py", *argv])
    return resettle_sweep.main(), calls


def test_sweep_without_a_bridge_resettles_nothing_and_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, calls = _sweep(monkeypatch, {"2026-09-26": 3}, None,
                         ["--from", "2026-09-21", "--to", "2026-10-03"])
    assert code == 1 and calls == []
    captured = capsys.readouterr()
    assert "NO_BRIDGE" in captured.err
    assert '"verdict": "PARTIAL"' in captured.out


def test_sweep_settles_each_planned_day_then_regrades_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, calls = _sweep(monkeypatch, {"2026-09-26": 3, "2026-09-30": 0},
                         {"last_pull_age_s": 1.0},
                         ["--from", "2026-09-21", "--to", "2026-10-03"])
    assert code == 0
    assert [c[-3:] for c in calls[:2]] == [
        ["--date", "2026-09-26", "--refetch-stat-gaps"],
        ["--date", "2026-09-30", "--refetch-stat-gaps"]]
    assert calls[0][1].endswith("run_settle.py")
    assert calls[2][1].endswith("regrade_settled.py") and calls[2][-1] == "--apply"
    assert len(calls) == 3


def test_sweep_dry_run_needs_no_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    code, calls = _sweep(monkeypatch, {"2026-09-26": 3}, None,
                         ["--from", "2026-09-21", "--to", "2026-10-03", "--dry-run"])
    assert code == 0 and calls == []


def test_sweep_with_nothing_to_do_needs_no_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, calls = _sweep(monkeypatch, {}, None,
                         ["--from", "2026-09-21", "--to", "2026-10-03"])
    assert code == 0 and calls == []


def test_sweep_plan_forces_an_included_day(tmp_path: Path) -> None:
    from scripts.sofa.resettle_sweep import plan

    path = tmp_path / "sofa.db"
    migrate(str(path))
    assert plan(tmp_path, str(path), ["2026-09-26"], ["2026-09-28"]) == {
        "2026-09-28": 0}
