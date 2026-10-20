"""Audit 2026-10-21 D7: Sofascore names referees late, after the morning
SHEET, so football cards / fouls rows go out with referee_read NO_REFEREE.
A rebuild re-runs SHEET when the DB now names the referee of an open such
fixture: at plan time (a label, or the /event RESOLVE / an earlier
FIXTURE_CHECK cached) and right after its own FIXTURE_CHECK - the plan's
SHEET step runs BEFORE FIXTURE_CHECK, so rebuild_day asks
rebuild_plan.after_fixture_check and inserts SHEET before CONFIDENCE.
Offline: a fake DB and a fake day dir."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import rebuild_plan as rp
from scripts.sofa import rebuild_day

LIMIT = timedelta(minutes=45)
DAY = "2026-10-21"
NOW = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
OPEN, STARTED, NAMED_NONE, PRICED = 11, 12, 13, 14


@pytest.fixture(autouse=True)
def _referee_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC",
                        datetime(2026, 10, 21, tzinfo=UTC))


def _fixture(eid: int, kickoff: str) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "sport": "football",
            "kickoff_utc": kickoff, "superbet_kickoff_utc": kickoff}


def _row(eid: int, market: str, status: str | None) -> dict[str, Any]:
    row: dict[str, Any] = {"sofascore_event_id": eid, "sport": "football",
                           "market": market, "line": 4.5, "direction": "OVER"}
    if status is not None:
        row["referee_read"] = {"status": status}
    return row


def _day(runs: Path) -> Path:
    run = runs / DAY
    run.mkdir(parents=True)
    (run / "02_fixtures.json").write_text(json.dumps([
        _fixture(OPEN, "2026-10-21T18:00:00Z"),
        _fixture(STARTED, "2026-10-21T08:00:00Z"),
        _fixture(NAMED_NONE, "2026-10-21T19:00:00Z"),
        _fixture(PRICED, "2026-10-21T20:00:00Z")]))
    (run / "05_sheet.json").write_text(json.dumps([
        _row(OPEN, "cards_points_total", "NO_REFEREE"),
        _row(OPEN, "goals_total", None),
        _row(STARTED, "fouls_total", "NO_REFEREE"),
        _row(NAMED_NONE, "fouls_for", "NO_REFEREE"),
        _row(PRICED, "cards_points_for", "APPLIED")]))
    return run


def _db(path: Path, named: dict[int, int | None]) -> Path:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE sofa_event_detail (sofascore_event_id INTEGER "
                "PRIMARY KEY, fetched_at TEXT, status_type TEXT, "
                "detail_json TEXT)")
    for eid, rid in named.items():
        event: dict[str, Any] = {"id": eid, "startTimestamp": 1}
        if rid is not None:
            event["referee"] = {"id": rid, "name": f"Ref {rid}"}
        con.execute("INSERT INTO sofa_event_detail VALUES (?, ?, ?, ?)",
                    (eid, NOW.isoformat(), "notstarted",
                     json.dumps({"event": event})))
    con.commit()
    con.close()
    return path


def _all_named(tmp_path: Path) -> Path:
    # every fixture's /event names a referee except NAMED_NONE's
    return _db(tmp_path / "sofa.db", {OPEN: 7, STARTED: 8, NAMED_NONE: None,
                                      PRICED: 9})


def test_only_an_open_no_referee_fixture_now_named_counts(tmp_path: Path) -> None:
    _day(tmp_path)
    db = _all_named(tmp_path)
    assert rp.referee_now_known(str(tmp_path), DAY, NOW, db) == (OPEN,)


def test_nothing_without_a_db_a_sheet_or_the_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day(tmp_path)
    db = _all_named(tmp_path)
    assert rp.referee_now_known(str(tmp_path), DAY, NOW, None) == ()
    assert rp.referee_now_known(str(tmp_path), DAY, NOW,
                                tmp_path / "absent.db") == ()
    assert rp.referee_now_known(str(tmp_path), "2026-10-20", NOW, db) == ()
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC", None)
    assert rp.referee_now_known(str(tmp_path), DAY, NOW, db) == ()


def test_a_referee_still_unnamed_re_runs_nothing(tmp_path: Path) -> None:
    _day(tmp_path)
    db = _db(tmp_path / "sofa.db", {OPEN: None})
    assert rp.referee_now_known(str(tmp_path), DAY, NOW, db) == ()
    assert rp.after_fixture_check(str(tmp_path), DAY, NOW, db) == []


def test_the_plan_re_runs_sheet_before_fixture_check(tmp_path: Path) -> None:
    _day(tmp_path)
    db = _all_named(tmp_path)
    state = rp.observe(str(tmp_path), DAY, NOW, LIMIT, db_path=db)
    assert state.referee_now_known == (OPEN,)
    plan = rp.build_plan(rp.DayState(DAY, NOW, LIMIT,
                                     referee_now_known=state.referee_now_known))
    names = plan.names()
    sheet = next(s for s in plan.steps if s.name == "SHEET")
    assert "referee" in sheet.reason and str(OPEN) in sheet.reason
    assert names.index("SHEET") < names.index("FIXTURE_CHECK")
    # the same day observed without a DB (the old call) plans no SHEET for it
    assert rp.observe(str(tmp_path), DAY, NOW, LIMIT).referee_now_known == ()
    assert "SHEET" not in rp.build_plan(rp.DayState(DAY, NOW, LIMIT)).names()


def test_after_fixture_check_names_the_new_referees(tmp_path: Path) -> None:
    _day(tmp_path)
    db = _all_named(tmp_path)
    steps = rp.after_fixture_check(str(tmp_path), DAY, NOW, db, run_id="r")
    assert [s.name for s in steps] == ["SHEET"]
    assert "--only" in steps[0].argv and "SHEET" in steps[0].argv
    assert "after FIXTURE_CHECK" in steps[0].reason


def test_rebuild_day_inserts_sheet_after_fixture_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / DAY).mkdir()
    ran: list[str] = []
    plan = rp.Plan(DAY, "stats_only", False, steps=[
        rp.Step("FIXTURE_CHECK", ("x",), "fresh /event", soft=True),
        rp.Step("CONFIDENCE", ("x",), "football / tennis"),
        rp.Step("PDF", ("x",), "pdf")])
    asked: list[str] = []

    def after(runs_dir: str, date: str, now: datetime, db_path: Any,
              run_id: str = "rebuild") -> list[rp.Step]:
        asked.append(str(db_path))
        return [rp.Step("SHEET", ("x",), "referee named")]

    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "sofa.db"))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(sys, "argv", ["rebuild_day.py", "--date", DAY])
    monkeypatch.setattr(rp, "observe", lambda *a, **k: rp.DayState(DAY, NOW, LIMIT))
    monkeypatch.setattr(rp, "build_plan", lambda *a, **k: plan)
    monkeypatch.setattr(rp, "after_fixture_check", after)
    monkeypatch.setattr(rebuild_day, "run_step",
                        lambda step, env, log: (ran.append(step.name), (0, []))[1])
    assert rebuild_day.main() == 0
    assert ran == ["FIXTURE_CHECK", "SHEET", "CONFIDENCE", "PDF"]
    assert asked == [str((tmp_path / "sofa.db").resolve())]
