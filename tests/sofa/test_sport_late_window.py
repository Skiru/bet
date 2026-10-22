"""The measured sports' rolling day window (epochs.SPORT_LATE_WINDOW_FROM_UTC,
2026-10-23 00:00Z, operator 2026-10-22): day D's hockey / basketball /
volleyball / CS2 games run to D+1 05:00Z, so the North American evening is
D's coupon's (the manual evening rebuild), not the next morning's KICKED_OFF.
Football and tennis keep the UTC day. Offline."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import coupon_sports, epochs
from bet.sofa import rebuild_plan as rp
from bet.sofa import sport_identity as si
from scripts.sofa import (
    build_coupon,
    cs2_daily,
    day_status,
    run_cs2,
    run_shadow,
    settle_cs2,
    settle_shadow,
    shadow_daily,
)
from scripts.sofa import run_sport_confidence as rsc

D = "2026-10-23"  # the switch day
NEXT = "2026-10-24"
EVENING = datetime(2026, 10, 23, 20, 0, tzinfo=UTC)


def z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


# --- the window ------------------------------------------------------------------


def test_the_window_is_the_utc_day_before_the_switch_and_to_five_after_it() -> None:
    assert si.day_window("2026-10-22") == (utc("2026-10-22T00:00:00Z"),
                                           utc("2026-10-23T00:00:00Z"))
    # the switch day starts where 10-22 ended and runs into 10-24
    assert si.day_window(D) == (utc("2026-10-23T00:00:00Z"),
                                utc("2026-10-24T05:00:00Z"))
    assert si.day_window(NEXT) == (utc("2026-10-24T05:00:00Z"),
                                   utc("2026-10-25T05:00:00Z"))
    assert not epochs.sport_late_window("2026-10-22")
    assert epochs.sport_late_window(D) and epochs.sport_late_window(NEXT)


def test_consecutive_windows_meet_end_to_end_across_the_switch() -> None:
    day = datetime(2026, 10, 18)
    for _ in range(12):
        d = day.strftime("%Y-%m-%d")
        nxt = (day + timedelta(days=1)).strftime("%Y-%m-%d")
        lo, hi = si.day_window(d)
        assert lo < hi
        assert si.day_window(nxt)[0] == hi  # no gap, no overlap
        day += timedelta(days=1)


def test_off_every_window_is_the_utc_day(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SPORT_LATE_WINDOW_FROM_UTC", None)
    assert si.day_window(NEXT) == (utc("2026-10-24T00:00:00Z"),
                                   utc("2026-10-25T00:00:00Z"))
    assert not si.late_window(D, utc("2026-10-24T01:30:00Z"))


def test_a_late_game_is_the_one_starting_on_the_next_utc_day() -> None:
    assert si.late_window(D, utc("2026-10-24T01:30:00Z"))
    assert not si.late_window(D, utc("2026-10-23T23:30:00Z"))
    assert not si.late_window(D, utc("2026-10-24T05:00:00Z"))
    assert not si.late_window("2026-10-22", utc("2026-10-23T01:30:00Z"))


# --- SPORT_CONFIDENCE ----------------------------------------------------------------


class FakeForecaster:
    def probability(self, sport: str, fixture: Any, ev: Any, line: Any) -> float | None:
        return {"OVER": 0.81, "UNDER": 0.19}.get(line.side)

    def sample(self, sport: str, fixture: Any, ev: Any, line: Any) -> tuple[int, int]:
        return 7, 10


def _calibration() -> Any:
    from bet.sofa import sport_confidence as scf

    curve = {"0.800-0.825": {"n": 400, "realised": 0.84, "realised_lo95": 0.80},
             "0.000-0.600": {"n": 900, "realised": 0.45, "realised_lo95": 0.42}}
    keys = ["total|OVER", "total|UNDER"]
    return scf.SportCalibration({
        "min_bucket": 200, "fitted_from": {"before": "2026-10-05"},
        "sports": {"hockey": {"curves": {k: curve for k in keys}, "admitted": keys}}})


def _snap(runs: Path, file_day: str, kickoff: str, fetched: datetime,
          sb: str = "1") -> None:
    day = runs / "shadow" / "hockey" / file_day
    day.mkdir(parents=True, exist_ok=True)
    rec = {"fetched_at_utc": z(fetched), "superbet_event_id": sb,
           "match_name": "Boston Bruins·Utah", "team1": "Boston Bruins",
           "team2": "Utah", "kickoff_utc": kickoff, "tournament": "NHL",
           "lines": [{"superbet_event_id": sb, "market_id": 623, "family": "total",
                      "period": 0, "subject": "", "line": 5.5, "side": side,
                      "odds": odds} for side, odds in (("OVER", 1.30),
                                                       ("UNDER", 3.40))]}
    with (day / "snapshots.jsonl").open("a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _fixtures(runs: Path, date: str, kickoff: str, sb: str = "1") -> dict[str, Any]:
    doc = {"date": date, "sports_run": list(si.SPORT_KEYS), "fixtures": [
        {"superbet_event_id": sb, "sport": "hockey", "status": si.IDENTIFIED,
         "sofascore_event_id": 9001, "home_id": 10, "away_id": 20,
         "home_is_team1": True, "competition_id": 55,
         "sofascore_start_utc": kickoff}]}
    (runs / date).mkdir(parents=True, exist_ok=True)
    (runs / date / si.FIXTURES_FILE).write_text(json.dumps(doc))
    return doc


def _price(runs: Path, date: str, at: datetime, printed: rsc.PrevPrinted | None = None
           ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = si.load_fixtures(runs / date / si.FIXTURES_FILE)
    return rsc.build_sport("hockey", date, str(runs), doc, _calibration(),
                           FakeForecaster(), at, None, None, None,
                           printed or rsc.prev_printed(str(runs), date))


def test_a_game_after_midnight_is_priced_for_the_evening_before(tmp_path: Path) -> None:
    kick = "2026-10-24T01:30:00Z"
    # SHADOW wrote it into D+1's file (the next day's game, fetched on D)
    _snap(tmp_path, NEXT, kick, EVENING - timedelta(minutes=10))
    _fixtures(tmp_path, D, kick)
    entry, legs = _price(tmp_path, D, EVENING)
    (leg,) = legs
    assert leg["kickoff_utc"] == kick and leg["source_date"] == NEXT
    assert leg["window"] == epochs.LATE_WINDOW_MARKER
    # D+1's own build never sees it: it is outside D+1's window
    _fixtures(tmp_path, NEXT, kick)
    entry, legs = _price(tmp_path, NEXT, utc("2026-10-24T00:30:00Z"))
    assert legs == [] and entry["refused"] == {}


def test_a_game_of_the_evening_itself_carries_no_late_stamp(tmp_path: Path) -> None:
    kick = "2026-10-23T23:00:00Z"
    _snap(tmp_path, D, kick, EVENING - timedelta(minutes=10))
    _fixtures(tmp_path, D, kick)
    _, (leg,) = _price(tmp_path, D, EVENING)
    assert "window" not in leg


def test_before_the_switch_a_next_day_game_is_not_the_days(tmp_path: Path) -> None:
    kick = "2026-10-23T01:30:00Z"
    _snap(tmp_path, D, kick, utc("2026-10-22T20:00:00Z"))
    _fixtures(tmp_path, "2026-10-22", kick)
    _, legs = _price(tmp_path, "2026-10-22", utc("2026-10-22T20:10:00Z"))
    assert legs == []


def _coupon(runs: Path, date: str, singles: list[dict[str, Any]],
            builders: list[dict[str, Any]] | None = None) -> None:
    (runs / date).mkdir(parents=True, exist_ok=True)
    (runs / date / "11_coupon.json").write_text(json.dumps(
        {"singles": singles, "builders": builders or []}))


def test_an_event_printed_the_day_before_is_refused(tmp_path: Path) -> None:
    # printed on D's evening coupon at 04:30Z; Superbet then moved it to
    # 06:00Z - inside D+1's window
    _coupon(tmp_path, D, [{"sport": "hockey", "sofascore_event_id": 9001,
                           "superbet_event_id": "1"}])
    kick = "2026-10-24T06:00:00Z"
    _snap(tmp_path, NEXT, kick, utc("2026-10-24T05:30:00Z"))
    _fixtures(tmp_path, NEXT, kick)
    entry, legs = _price(tmp_path, NEXT, utc("2026-10-24T05:40:00Z"))
    assert legs == []
    assert {k: n for k, n in entry["refused"].items() if n} == {
        rsc.ALREADY_PRINTED_PREV_DAY: 2}


def test_the_prev_day_set_reads_printed_singles_and_builders_only(
        tmp_path: Path) -> None:
    _coupon(tmp_path, D,
            [{"sport": "hockey", "sofascore_event_id": 1, "superbet_event_id": "11"},
             {"sport": "football", "sofascore_event_id": 2}],
            [{"sofascore_event_id": 3}])
    got = rsc.prev_printed(str(tmp_path), NEXT)
    assert got.sofascore_ids == frozenset({1, 3})
    assert got.superbet_ids == frozenset({"11"})
    assert got.holds("11", None) and got.holds("x", {"sofascore_event_id": 3})
    assert not got.holds("x", {"sofascore_event_id": 2})
    # 08_confidence.json is no print; before the switch nothing is read
    assert rsc.prev_printed(str(tmp_path), "2026-10-25") == rsc.PrevPrinted()
    _coupon(tmp_path, "2026-10-21", [{"sport": "hockey", "sofascore_event_id": 1}])
    assert rsc.prev_printed(str(tmp_path), "2026-10-22") == rsc.PrevPrinted()


# --- COUPON_ASSEMBLY's window -------------------------------------------------------


def test_the_coupon_window_is_the_utc_day_for_football_the_sport_window_else() -> None:
    def leg(sport: str, kick: str) -> dict[str, Any]:
        return {"sport": sport, "kickoff_utc": kick}

    assert not build_coupon.in_day_window(leg("football", "2026-10-24T01:30:00Z"), D)
    assert not build_coupon.in_day_window(leg("tennis", "2026-10-24T01:30:00Z"), D)
    assert build_coupon.in_day_window(leg("football", "2026-10-23T21:00:00Z"), D)
    assert build_coupon.in_day_window(leg("hockey", "2026-10-24T01:30:00Z"), D)
    assert build_coupon.in_day_window(leg("cs2", "2026-10-24T04:59:00Z"), D)
    assert not build_coupon.in_day_window(leg("basketball", "2026-10-24T05:00:00Z"), D)
    assert not build_coupon.in_day_window(leg("hockey", "2026-10-24T01:30:00Z"), NEXT)
    assert not build_coupon.in_day_window(leg("hockey", "2026-10-23T01:30:00Z"),
                                          "2026-10-22")


# --- SHADOW / CS2 snapshots -------------------------------------------------------


class _Board:
    """Superbet's board: basketball (sportId 4) and CS2 (55) games."""

    def __init__(self, rows: list[tuple[str, int, str]]) -> None:
        self.rows = rows
        self.asked: list[str] = []
        self.window: tuple[datetime, datetime] | None = None

    def events_by_date(self, start: datetime, end: datetime, offer_state: str
                       ) -> list[dict[str, Any]]:
        self.window = (start, end)
        return [{"sportId": sport, "eventId": eid, "matchName": "A·B",
                 "utcDate": kick, "tournamentId": 1}
                for eid, sport, kick in self.rows]

    def event_odds(self, event_id: str) -> dict[str, Any]:
        self.asked.append(event_id)
        return {"odds": [
            {"marketName": "Liczba map", "name": n, "info": n, "price": p,
             "specifiers": {"total": "2.5"}, "status": "active"}
            for n, p in (("poniżej 2.5", 1.8), ("powyżej 2.5", 1.95))]}

    def _get_json(self, path: str) -> dict[str, Any]:
        return {"data": {"tournaments": []}}


def test_shadow_fetches_a_late_game_beyond_its_horizon_once(tmp_path: Path) -> None:
    board = _Board([("late", 4, "2026-10-24T03:00:00Z"),
                    ("morning", 4, "2026-10-24T06:00:00Z")])
    run_shadow.snapshot(D, board, str(tmp_path), at=EVENING)  # type: ignore[arg-type]
    assert board.window is not None and board.window[1] >= utc("2026-10-24T05:00:00Z")
    # 7 h ahead, past the 3 h horizon, but D's: asked; the 06:00Z game is D+1's
    assert board.asked == ["late"]


def test_shadow_before_the_switch_keeps_the_horizon(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(epochs, "SPORT_LATE_WINDOW_FROM_UTC", None)
    board = _Board([("late", 4, "2026-10-24T03:00:00Z")])
    run_shadow.snapshot(D, board, str(tmp_path), at=EVENING)  # type: ignore[arg-type]
    assert board.asked == []


def test_cs2_snapshots_a_night_series_of_the_window_into_the_next_file(
        tmp_path: Path) -> None:
    board = _Board([("night", 55, "2026-10-24T01:00:00Z"),
                    ("day2", 55, "2026-10-24T09:00:00Z"),
                    ("today", 55, "2026-10-23T21:00:00Z")])
    result = run_cs2.snapshot(
        D, board, str(tmp_path), at=EVENING)  # type: ignore[arg-type]
    assert sorted(board.asked) == ["night", "today"]
    assert result["metrics"]["events_on_board"] == 1
    assert result["metrics"]["next_day_events_with_lines"] == 1

    def ids(day: str) -> list[str]:
        path = tmp_path / "cs2" / day / "snapshots.jsonl"
        return [json.loads(x)["superbet_event_id"]
                for x in path.read_text().splitlines()]

    assert ids(D) == ["today"] and ids(NEXT) == ["night"]


# --- the rebuild sees the late game -----------------------------------------


def test_the_rebuild_sees_a_late_game_on_file_and_refreshes_to_it(
        tmp_path: Path) -> None:
    kick = "2026-10-24T02:00:00Z"
    _snap(tmp_path, NEXT, kick, utc("2026-10-23T12:00:00Z"))  # the loop's one fetch
    state = rp.observe_sport(str(tmp_path), "hockey", D, EVENING)
    assert state.events == 1 and state.open_events == 1
    assert state.farthest_open_kickoff == utc(kick)
    horizon = rp.shadow_horizon_h(EVENING, state.farthest_open_kickoff)
    assert EVENING + timedelta(hours=horizon) >= utc(kick)
    # D+1 does not count it
    assert rp.observe_sport(str(tmp_path), "hockey", NEXT, EVENING).events == 0


# --- settlement --------------------------------------------------------------


def test_the_loops_settle_the_late_games_the_next_morning() -> None:
    _, morning, _ = shadow_daily.plan(D)
    assert ["scripts/sofa/settle_shadow.py", "--date", NEXT,
            "--kickoff-before", "2026-10-24T05:00:00Z"] in morning
    _, before, _ = shadow_daily.plan("2026-10-22")
    assert not any("--kickoff-before" in step for step in before)
    _, cs2_morning, _ = cs2_daily.plan(D, 30, EVENING, EVENING, 0)
    assert ["scripts/sofa/settle_cs2.py", "--date", NEXT,
            "--kickoff-before", "2026-10-24T05:00:00Z"] in cs2_morning
    # before the ledger, which re-records D with those grades
    names = [" ".join(s) for s in cs2_morning]
    assert names.index(next(n for n in names if "--kickoff-before" in n)) < \
        names.index(next(n for n in names if "record_results" in n))


def _shadow_snaps(runs: Path, day: str, kicks: dict[str, str]) -> None:
    path = runs / "shadow" / "hockey" / day
    path.mkdir(parents=True, exist_ok=True)
    path.joinpath("snapshots.jsonl").write_text("".join(json.dumps({
        "fetched_at_utc": z(utc(k) - timedelta(hours=1)), "superbet_event_id": eid,
        "match_name": "A·B", "team1": "A", "team2": "B", "kickoff_utc": k,
        "tournament": "NHL", "lines": []}) + "\n" for eid, k in kicks.items()))


def test_settle_shadow_up_to_a_kickoff_leaves_the_rest_untouched(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _shadow_snaps(tmp_path, NEXT, {"early": "2026-10-24T00:30:00Z",
                                   "late": "2026-10-24T18:00:00Z"})
    seen: list[str] = []

    def fake_settle_one(ev: Any, *a: Any, **k: Any) -> dict[str, Any]:
        seen.append(ev.superbet_event_id)
        return {"match_name": ev.match_name, "kickoff_utc": ev.kickoff_utc,
                "state": "VOID"}

    monkeypatch.setattr(settle_shadow, "settle_one", fake_settle_one)
    at = utc("2026-10-24T05:15:00Z")
    out = settle_shadow.settle_sport(
        settle_shadow.SPORTS["hockey"], NEXT,
        None, None, None,  # type: ignore[arg-type]
        str(tmp_path), at + timedelta(days=1),
        kickoff_before=utc("2026-10-24T05:00:00Z"))
    assert seen == ["early"]
    assert out["metrics"]["after_cutoff"] == 1
    settled = tmp_path / "shadow" / "hockey" / NEXT / "settled.json"
    doc = json.loads(settled.read_text())
    assert set(doc["events"]) == {"early"}


def test_settle_cs2_up_to_a_kickoff_leaves_the_rest_untouched(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "cs2" / NEXT
    path.mkdir(parents=True)
    path.joinpath("snapshots.jsonl").write_text("".join(json.dumps({
        "fetched_at_utc": z(utc(k) - timedelta(hours=1)), "superbet_event_id": eid,
        "match_name": "A·B", "team1": "A", "team2": "B", "kickoff_utc": k,
        "lines": []}) + "\n" for eid, k in (("early", "2026-10-24T00:30:00Z"),
                                            ("late", "2026-10-24T18:00:00Z"))))
    seen: list[str] = []

    def fake_settle_one(ev: Any, *a: Any, **k: Any) -> dict[str, Any]:
        seen.append(ev.superbet_event_id)
        return {"match_name": ev.match_name, "kickoff_utc": ev.kickoff_utc,
                "state": "VOID"}

    monkeypatch.setattr(settle_cs2, "settle_one", fake_settle_one)
    out = settle_cs2.settle(NEXT, None, str(tmp_path),  # type: ignore[arg-type]
                            utc("2026-10-25T05:00:00Z"),
                            kickoff_before=utc("2026-10-24T05:00:00Z"))
    assert seen == ["early"] and out["metrics"]["after_cutoff"] == 1
    doc = json.loads((path / "settled.json").read_text())
    assert set(doc["events"]) == {"early"}


def test_a_late_leg_is_graded_from_the_next_days_file(tmp_path: Path) -> None:
    leg = {"sport": "hockey", "superbet_event_id": "1", "source_date": NEXT,
           "kickoff_utc": "2026-10-24T01:30:00Z", "market_id": 623,
           "family": "total", "period": 0, "subject": "", "line": 5.5,
           "side": "OVER", "odds": 1.3}
    asked: list[set[str]] = []

    def load(runs: str, sport: Any, dates: set[str]) -> dict[str, Any]:
        asked.append(set(dates))
        return {D: {"events": {}}, NEXT: {"events": {"1": {"state": "VOID"}}}}

    (graded,) = coupon_sports.grade(str(tmp_path), D, [leg], EVENING, load=load)
    assert asked == [{D, NEXT}] and graded["outcome"] == "VOID"


# --- day_status -----------------------------------------------------------------------


def _record(runs: Path, sub: str, day: str, fetched: datetime) -> None:
    path = runs / sub / day
    path.mkdir(parents=True, exist_ok=True)
    rec = json.dumps({"fetched_at_utc": z(fetched)})
    (path / "snapshots.jsonl").write_text(rec + "\n")


def test_day_status_reads_the_next_days_file_and_the_window_end(tmp_path: Path) -> None:
    subs = ["shadow/hockey", "shadow/basketball", "shadow/volleyball", "cs2"]
    for sub in subs:
        _record(tmp_path, sub, D, utc("2026-10-23T22:00:00Z"))
    # 03:00Z: before the window's end, D's file 5 h old - a stalled loop
    checks = day_status.sport_checks(tmp_path, D, utc("2026-10-24T03:00:00Z"))
    assert {c.status for c in checks} == {day_status.WARN}
    # D+1's file holds the late games' fresh snapshots
    for sub in subs:
        _record(tmp_path, sub, NEXT, utc("2026-10-24T02:30:00Z"))
    checks = day_status.sport_checks(tmp_path, D, utc("2026-10-24T03:00:00Z"))
    assert {c.status for c in checks} == {day_status.OK}
    assert all("2026-10-24T02:30:00Z" in c.detail for c in checks)
    # after 05:00Z the day is over
    for sub in subs:
        (tmp_path / sub / NEXT / "snapshots.jsonl").unlink()
    checks = day_status.sport_checks(tmp_path, D, utc("2026-10-24T05:30:00Z"))
    assert {c.status for c in checks} == {day_status.OK}
