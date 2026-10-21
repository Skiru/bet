"""The late RESOLVE pass (epochs.LATE_RESOLVE_FROM_UTC, bet.sofa.late_resolve,
scripts/sofa/run_late_resolve.py).

RESOLVE ran once, in the morning; an ITF match Sofascore created after it
never reached a fixture (measured 2026-10-21: 39 of 65 tennis entries lost
10-07..10-20 had an id above every id their day's RESOLVE bridged). The late
pass re-asks the unbridged entries that have not started and adds only the
NEW fixtures - every fixture, sample and sheet row of the morning untouched.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from bet.sofa import late_resolve as lr
from bet.sofa import rebuild_plan as rp
from bet.sofa.contracts import BoardFixture, Fixture, GapReason

DATE = "2026-10-21"
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
ON = datetime(2026, 10, 21, 8, 48, tzinfo=UTC)


def z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def entry(sid: str, kickoff: datetime, name: str = "A Player·B Player",
          sport: str = "tennis") -> dict[str, Any]:
    a, b = name.split("·")
    return {"superbet_event_id": sid, "sport": sport, "match_name": name,
            "side_a": a, "side_b": b, "kickoff_utc": z(kickoff),
            "tournament_id": 7, "category_id": 8}


def fixture(eid: int, sids: list[str], kickoff: datetime,
            sport: str = "tennis") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "superbet_event_ids": sids, "sport": sport,
        "kickoff_utc": z(kickoff), "home_name": f"H{eid}", "away_name": f"A{eid}",
        "home_entity_id": 1, "away_entity_id": 2, "competition_name": "ITF M15",
        "competition_id": 9, "season_id": 1, "category_name": "ITF Men",
        "identity": "CONFIRMED", "round_number": None, "round_name": None,
        "cup_round_type": None, "previous_leg_event_id": None,
        "venue_name": None, "referee": None, "ground_type": None,
        "default_period_count": 3, "superbet_kickoff_utc": z(kickoff),
        "kickoff_disagreement_h": 0.0,
    }


# --- candidates -------------------------------------------------------------


def test_candidates_skip_bridged_started_and_placeholders() -> None:
    later = NOW + timedelta(hours=3)
    board = [
        entry("1", later),                                  # bridged
        entry("2", later),                                  # open: asked
        entry("3", NOW + timedelta(minutes=10)),            # starts too soon
        entry("4", NOW - timedelta(hours=1)),               # started
        entry("5", datetime(2026, 10, 21, tzinfo=UTC)),     # 00:00Z placeholder
    ]
    found = lr.candidates(board, [fixture(10, ["1"], later)], NOW)
    assert [e["superbet_event_id"] for e in found.entries] == ["2"]
    assert found.summary() == {"candidates": 1, "already_bridged": 1,
                               "skipped_started": 2,
                               "skipped_midnight_placeholder": 1}


def test_min_minutes_is_the_offer_refresh_cutoff() -> None:
    assert lr.MIN_MINUTES_TO_KICKOFF == rp.OFFER_MIN_MINUTES_TO_KICKOFF


def test_fixture_open_reads_the_earliest_clock() -> None:
    fx = fixture(1, ["1"], NOW + timedelta(hours=2))
    assert lr.fixture_open(fx, {}, NOW)
    # Superbet's clock earlier than Sofascore's: the earliest decides
    fx["superbet_kickoff_utc"] = z(NOW + timedelta(minutes=5))
    assert not lr.fixture_open(fx, {}, NOW)


def test_pending_fixtures() -> None:
    later = NOW + timedelta(hours=2)
    fixtures = [fixture(1, ["1"], later), fixture(2, ["2"], later),
                fixture(3, ["3"], NOW - timedelta(hours=1)),
                fixture(4, ["4"], later)]
    # 1 sampled and finished; 2 never sampled; 3 started; 4 sampled but its
    # late pass did not reach SHEET
    record = {"events": {"4": {"added_at_utc": "x", "sheet_at_utc": None},
                         "1": {"added_at_utc": "x", "sheet_at_utc": "y"}}}
    assert lr.unfinished(record) == {4}
    assert lr.pending_fixtures(fixtures, {1, 3, 4}, lr.unfinished(record),
                               {}, NOW) == [2, 4]


# --- merges -----------------------------------------------------------------


def test_merge_by_event_keeps_old_rows_and_appends_new() -> None:
    old = [{"sofascore_event_id": 1, "p": 0.1234567890123},
           {"sofascore_event_id": 2, "p": 0.5}]
    fresh = [{"sofascore_event_id": 9, "p": 0.7}]
    merged, replaced = lr.merge_by_event(old, fresh, {9})
    assert merged[:2] == old and merged[2:] == fresh and replaced == 0
    # a pending event's partial rows are replaced, nobody else's
    merged2, replaced2 = lr.merge_by_event(
        merged, [{"sofascore_event_id": 9, "p": 0.8}], {9})
    assert merged2 == [*old, {"sofascore_event_id": 9, "p": 0.8}] and replaced2 == 1


def test_merge_by_event_refuses_a_row_outside_the_pass() -> None:
    with pytest.raises(ValueError):
        lr.merge_by_event([], [{"sofascore_event_id": 1}], {2})


def test_parse_event_ids() -> None:
    assert lr.parse_event_ids(None) is None
    assert lr.parse_event_ids("") == set()
    assert lr.parse_event_ids("3, 4,5") == {3, 4, 5}


# --- the switch and the plan ------------------------------------------------


def test_switch() -> None:
    assert epochs.LATE_RESOLVE_FROM_UTC is not None
    at = epochs.LATE_RESOLVE_FROM_UTC
    day = at.strftime("%Y-%m-%d")
    assert not epochs.late_resolve(day, at - timedelta(minutes=1))
    assert epochs.late_resolve(day, at)
    prev = (at - timedelta(days=1)).strftime("%Y-%m-%d")
    assert not epochs.late_resolve(prev, at + timedelta(hours=1))


def _state(**kw: Any) -> rp.DayState:
    return rp.DayState(date=DATE, now=NOW, price_max_age=timedelta(minutes=45),
                       open_fixtures=1, oldest_open_rung=NOW, offer_fixtures=1,
                       **kw)


def test_plan_runs_late_resolve_first_when_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)
    plan = rp.build_plan(_state(late_candidates=3))
    assert plan.names()[:2] == ["BRIDGE", "LATE_RESOLVE"]
    assert plan.steps[1].soft
    assert plan.steps[1].argv[1] == "scripts/sofa/run_late_resolve.py"
    # 06_coupon follows the sheet the pass adds to
    assert "COUPON" in plan.names()
    # one bridge before LATE_RESOLVE serves FIXTURE_CHECK too
    assert plan.names().count("BRIDGE") == 1
    assert "LATE_RESOLVE" in rp.build_plan(_state(late_pending=1)).names()


def test_plan_without_work_or_switch_runs_nothing(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)
    assert "LATE_RESOLVE" not in rp.build_plan(_state()).names()
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", None)
    assert "LATE_RESOLVE" not in rp.build_plan(_state(late_candidates=3)).names()


def _day(runs: Path) -> Path:
    run = runs / DATE
    run.mkdir(parents=True)
    later = NOW + timedelta(hours=3)
    (run / "01_board.json").write_text(json.dumps([
        entry("1", later), entry("2", later, "C D·E F"),
        entry("3", NOW - timedelta(hours=2), "G H·I J"),
        entry("4", later, "K L·M N")]))
    (run / "02_fixtures.json").write_text(json.dumps(
        [fixture(10, ["1"], later)], indent=2))
    (run / "03_samples.json").write_text(json.dumps(
        [{"sofascore_event_id": 10, "readiness": "READY"}]))
    return run


def test_observe_counts_the_work(tmp_path: Path,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    _day(tmp_path)
    assert lr.observe_work(tmp_path, DATE, NOW) == (2, 0)
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)
    assert rp._late_work(str(tmp_path), DATE, NOW) == {
        "late_candidates": 2, "late_pending": 0}
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", None)
    assert rp._late_work(str(tmp_path), DATE, NOW) == {}


# --- the script -------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, runs: Path, *argv: str) -> int:
    from scripts.sofa import run_late_resolve

    monkeypatch.setenv("SOFA_RUNS_DIR", str(runs))
    monkeypatch.setenv("SOFA_DB_PATH", str(runs / "none.db"))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(run_late_resolve, "now", lambda: NOW)
    monkeypatch.setattr(sys, "argv", ["run_late_resolve.py", "--date", DATE, *argv])
    return run_late_resolve.main()


def test_switch_off_writes_nothing(tmp_path: Path,
                                   monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    run = _day(tmp_path)
    before = (run / "02_fixtures.json").read_bytes()
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", None)
    assert _main(monkeypatch, tmp_path) == 0
    assert (run / "02_fixtures.json").read_bytes() == before
    assert not (run / lr.RECORD_FILE).exists()
    assert '"switch": "off' in capsys.readouterr().out


def test_late_pass_adds_only_new_open_fixtures(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sofa import run_late_resolve, run_resolve

    run = _day(tmp_path)
    before = json.loads((run / "02_fixtures.json").read_text())
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)
    later = NOW + timedelta(hours=3)
    asked: list[str] = []

    def fake_resolve(boards: list[BoardFixture], *_a: Any) -> Any:
        for bf in boards:
            asked.append(bf.superbet_event_id)
            if bf.superbet_event_id == "2":    # a new event
                yield run_resolve.ResolveOutcome(
                    bf, event_id=20,
                    fixture=Fixture.model_validate_json(
                        json.dumps(fixture(20, ["2"], later))))
            else:                               # Sofascore still has nothing
                yield run_resolve.ResolveOutcome(
                    bf, gap=GapReason.NO_MATCHING_EVENT)

    steps: list[tuple[str, list[int]]] = []

    def fake_step(script: str, date: str, ids: list[int]) -> tuple[int, Any]:
        steps.append((script, ids))
        return 0, {"metrics": {}}

    monkeypatch.setattr(run_resolve, "resolve_board_concurrently", fake_resolve)
    monkeypatch.setattr(run_resolve, "learn_tournaments", lambda *_a: 0)
    monkeypatch.setattr(run_late_resolve, "run_step", fake_step)
    assert _main(monkeypatch, tmp_path) == 1  # PARTIAL: one gap
    # the started entry "3" is never asked, the bridged "1" neither
    assert asked == ["2", "4"]
    after = json.loads((run / "02_fixtures.json").read_text())
    assert after[:1] == before
    assert [f["sofascore_event_id"] for f in after] == [10, 20]
    assert [s for s, _ in steps] == [s for _, s in run_late_resolve.STEPS]
    assert all(ids == [20] for _, ids in steps)
    record = json.loads((run / lr.RECORD_FILE).read_text())
    assert record["events"]["20"]["sheet_at_utc"] is not None
    assert record["passes"][0]["new_event_ids"] == [20]
    # the next pass finds no work for 20 (bridged, sheet done)
    assert lr.observe_work(tmp_path, DATE, NOW) == (1, 1)  # 20 not sampled here


def test_known_event_and_started_fixture_are_not_added(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sofa import run_late_resolve, run_resolve

    run = _day(tmp_path)
    before = (run / "02_fixtures.json").read_bytes()
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)

    def fake_resolve(boards: list[BoardFixture], *_a: Any) -> Any:
        for bf in boards:
            if bf.superbet_event_id == "2":    # a second listing of fixture 10
                yield run_resolve.ResolveOutcome(
                    bf, event_id=10, fixture=Fixture.model_validate_json(
                        json.dumps(fixture(10, ["2"], NOW + timedelta(hours=3)))))
            else:                               # Sofascore's clock: started
                yield run_resolve.ResolveOutcome(
                    bf, event_id=40, fixture=Fixture.model_validate_json(
                        json.dumps(fixture(40, ["4"], NOW - timedelta(hours=1)))))

    steps: list[Any] = []
    monkeypatch.setattr(run_resolve, "resolve_board_concurrently", fake_resolve)
    monkeypatch.setattr(run_resolve, "learn_tournaments", lambda *_a: 0)
    monkeypatch.setattr(run_late_resolve, "run_step",
                        lambda *a: steps.append(a) or (0, None))
    assert _main(monkeypatch, tmp_path) == 0
    assert (run / "02_fixtures.json").read_bytes() == before
    assert steps == []


def test_failed_step_leaves_the_events_pending(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sofa import run_late_resolve, run_resolve

    run = _day(tmp_path)
    monkeypatch.setattr(epochs, "LATE_RESOLVE_FROM_UTC", ON)
    later = NOW + timedelta(hours=3)

    def fake_resolve(boards: list[BoardFixture], *_a: Any) -> Any:
        for bf in boards:
            yield run_resolve.ResolveOutcome(
                bf, event_id=int(bf.superbet_event_id) * 10,
                fixture=Fixture.model_validate_json(json.dumps(
                    fixture(int(bf.superbet_event_id) * 10,
                            [bf.superbet_event_id], later))))

    calls: list[str] = []

    def failing(script: str, date: str, ids: list[int]) -> tuple[int, Any]:
        calls.append(script)
        return (2, None) if script.endswith("run_samples.py") else (0, None)

    monkeypatch.setattr(run_resolve, "resolve_board_concurrently", fake_resolve)
    monkeypatch.setattr(run_resolve, "learn_tournaments", lambda *_a: 0)
    monkeypatch.setattr(run_late_resolve, "run_step", failing)
    assert _main(monkeypatch, tmp_path) == 2
    assert calls == ["scripts/sofa/run_offer.py", "scripts/sofa/run_samples.py"]
    record = json.loads((run / lr.RECORD_FILE).read_text())
    assert lr.unfinished(record) == {20, 40}
    # the next pass carries them on
    assert lr.observe_work(tmp_path, DATE, NOW) == (0, 2)


def test_samples_fault_keeps_events_pending() -> None:
    from scripts.sofa import run_late_resolve

    assert run_late_resolve.samples_faulted(
        {"metrics": {"provider_fault_fixtures": 1}})
    assert run_late_resolve.samples_faulted({"metrics": {"breaker_open": True}})
    assert not run_late_resolve.samples_faulted({"metrics": {}})
    assert not run_late_resolve.samples_faulted(None)


# --- the stages' --event-ids merge -------------------------------------------


def test_samples_event_ids_merges_without_touching_old_entries(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa.contracts import FixtureSamples
    from scripts.sofa import run_samples

    run = tmp_path / DATE
    run.mkdir()
    later = NOW + timedelta(hours=3)
    (run / "02_fixtures.json").write_text(json.dumps(
        [fixture(10, ["1"], later), fixture(20, ["2"], later)]))
    old = [{"sofascore_event_id": 10, "readiness": "READY", "metrics": {},
            "gaps": [], "players": {}, "schedule": None, "extra_old": 1.23456789}]
    (run / "03_samples.json").write_text(json.dumps(old, indent=2))
    seen: list[list[int]] = []

    def fake_sample(fixtures: list[Any], *_a: Any, **_k: Any) -> list[Any]:
        seen.append([f.sofascore_event_id for f in fixtures])
        return [FixtureSamples(sofascore_event_id=f.sofascore_event_id,
                               readiness="READY", metrics={}, gaps=[])
                for f in fixtures]

    monkeypatch.setattr(run_samples, "sample_fixtures_concurrently", fake_sample)
    monkeypatch.setattr(run_samples, "check_coverage_floor", lambda *_a: [])
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setattr(sys, "argv", ["run_samples.py", "--date", DATE,
                                      "--event-ids", "20"])
    run_samples.main()
    assert seen == [[20]]
    written = json.loads((run / "03_samples.json").read_text())
    assert written[0] == old[0]
    assert [s["sofascore_event_id"] for s in written] == [10, 20]


def test_sheet_event_ids_prices_only_the_new_fixture(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from bet.sofa.contracts import SheetRow
    from scripts.sofa import run_sheet

    run = tmp_path / DATE
    run.mkdir()
    later = NOW + timedelta(hours=3)
    (run / "02_fixtures.json").write_text(json.dumps(
        [fixture(10, ["1"], later), fixture(20, ["2"], later)]))
    (run / "03_samples.json").write_text(json.dumps([
        {"sofascore_event_id": e, "readiness": "READY", "metrics": {},
         "gaps": []} for e in (10, 20)]))
    (run / "04_offer.json").write_text(json.dumps([
        {"sofascore_event_id": e, "status": "PRICED", "rungs": [],
         "unmapped_markets": []} for e in (10, 20)]))
    old = [{"sofascore_event_id": 10, "sport": "tennis", "market": "games_total",
            "p_central": 0.61234567891, "config_sha": "morning"}]
    (run / "05_sheet.json").write_text(json.dumps(old, indent=2))
    priced: list[int] = []

    def fake_process(fx: Any, *_a: Any, **_k: Any) -> tuple[list[Any], list[Any]]:
        priced.append(fx.sofascore_event_id)
        return [SheetRow.model_construct(sofascore_event_id=fx.sofascore_event_id,
                                         sport="tennis", market="games_total",
                                         verdict="NO_BET")], []

    monkeypatch.setattr(run_sheet, "process_fixture", fake_process)
    monkeypatch.setattr(run_sheet, "sheet_row_json", lambda r: {
        "sofascore_event_id": r.sofascore_event_id, "sport": r.sport,
        "market": r.market, "config_sha": r.config_sha})
    monkeypatch.setenv("SOFA_TENNIS_RATING", "0")
    monkeypatch.setenv("SOFA_FOOTBALL_RATING", "0")
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.delenv("SOFA_NOW", raising=False)
    monkeypatch.setattr(sys, "argv", ["run_sheet.py", "--date", DATE,
                                      "--event-ids", "20"])
    assert run_sheet.main() == 0
    assert priced == [20]
    written = json.loads((run / "05_sheet.json").read_text())
    assert written[0] == old[0]
    assert [r["sofascore_event_id"] for r in written] == [10, 20]
    assert written[1]["config_sha"] != "morning"
