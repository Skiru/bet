"""A measured sport's day on disk (bet.sofa.sport_day): the snapshot
files, the settled results, and the coupon's sport legs graded at the
printed price."""

from __future__ import annotations

import fcntl
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2
from bet.sofa import sport_day as sd
from tests.sofa.coupon_fixtures import (
    AT,
    DATE,
    hline,
    iso,
    snap,
    total_pair,
    write_snaps,
)

# --- grading ------------------------------------------------------------------------


def hockey_event(state: str = "SETTLED", **kw: Any) -> dict[str, Any]:
    return {
        "state": state,
        "t1_periods": [1, 2, 1],
        "t2_periods": [0, 1, 1],
        "t1_full": 4,
        "t2_full": 2,
        "overtime": False,
        "graded": [],
        **kw,
    }


def leg(side: str = "OVER", line: float | None = 5.5, **kw: Any) -> dict[str, Any]:
    return {
        **hline("1", 623, "total", side, 1.30, line),
        "fair_p": 0.75,
        "team1": "A",
        "team2": "B",
        "kickoff_utc": iso(AT),
        **kw,
    }


def coupon(*legs: dict[str, Any], sport: str = "hockey") -> dict[str, Any]:
    return {"sport": sport, "date": DATE, "legs": list(legs)}


def test_a_leg_is_graded_from_the_result_even_when_its_line_was_taken_down() -> None:
    # 4-2: six goals. The 5.5 line is not among the measurement's graded rows
    # (Superbet recentred the ladder before the start) - it is still graded.
    [g] = sd.grade_legs(coupon(leg()), {DATE: {"events": {"1": hockey_event()}}})
    assert g["outcome"] == "WIN" and g["odds"] == 1.30
    [g] = sd.grade_legs(
        coupon(leg(line=6.0)), {DATE: {"events": {"1": hockey_event()}}}
    )
    assert g["outcome"] == "VOID"  # a push


def test_a_disagreement_with_the_measurements_own_grade_is_a_mismatch() -> None:
    measured = [{**hline("1", 623, "total", "OVER", 1.2, 5.5), "outcome": "LOSS"}]
    ev = hockey_event(graded=measured)
    [g] = sd.grade_legs(coupon(leg()), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "MISMATCH"


def test_states_other_than_settled_are_named_not_guessed() -> None:
    cases = {
        None: "PENDING",
        "VOID": "VOID",
        "GAVE_UP": "NOT_GRADED:GAVE_UP",
        "NOT_ON_SOFASCORE": "PENDING:NOT_ON_SOFASCORE",
    }
    for state, want in cases.items():
        events = {} if state is None else {"1": {"state": state}}
        [g] = sd.grade_legs(coupon(leg()), {DATE: {"events": events}})
        assert g["outcome"] == want


def test_a_leg_settles_in_the_file_of_its_source_date() -> None:
    night = leg(source_date="2026-10-01")
    settled = {DATE: {"events": {}}, "2026-10-01": {"events": {"1": hockey_event()}}}
    [g] = sd.grade_legs(coupon(night), settled)
    assert g["outcome"] == "WIN"


def test_a_shootout_winner_is_never_read_from_the_score() -> None:
    ev = hockey_event(
        t1_periods=[1, 1, 0],
        t2_periods=[0, 1, 1],
        t1_full=2,
        t2_full=2,
        overtime=True,
        status="AP",
    )
    win = {**leg(side="T1", line=None), "market_id": 630, "family": "winner"}
    [g] = sd.grade_legs(coupon(win), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "UNGRADEABLE"
    ev["winner"] = "T1"
    [g] = sd.grade_legs(coupon(win), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "WIN"


def test_an_unclear_orientation_grades_only_orientation_free_legs() -> None:
    ev = hockey_event(orientation_unclear=True)
    handicap = {**leg(side="T1", line=-1.5), "market_id": 604, "family": "handicap"}
    [t, h] = sd.grade_legs(coupon(leg(), handicap), {DATE: {"events": {"1": ev}}})
    assert (t["outcome"], h["outcome"]) == ("WIN", "UNGRADEABLE")


def test_a_cs2_leg_is_graded_from_the_stored_maps() -> None:
    cleg = {
        **cs2.Cs2Line("1", "maps_handicap", 0, "", -1.5, "T1", 1.9).as_dict(),
        "fair_p": 0.7,
        "team1": "A",
        "team2": "B",
        "kickoff_utc": iso(AT),
    }
    ev = {"state": "SETTLED", "maps": [[13, 7], [13, 10]], "graded": []}
    [g] = sd.grade_legs(coupon(cleg, sport="cs2"), {DATE: {"events": {"1": ev}}})
    assert g["outcome"] == "WIN"  # 2-0 covers -1.5


def test_a_leg_waiting_past_the_deadline_is_not_graded_not_pending() -> None:
    waiting = {DATE: {"events": {"1": {"state": "NOT_ON_SOFASCORE"}}}}
    soon = AT + timedelta(days=1)
    late = AT + sd.GIVE_UP_AFTER + timedelta(minutes=1)
    [g] = sd.grade_legs(coupon(leg()), waiting, at=soon)
    assert g["outcome"] == "PENDING:NOT_ON_SOFASCORE", "inside the deadline: wait"
    [g] = sd.grade_legs(coupon(leg()), waiting, at=late)
    assert g["outcome"] == "NOT_GRADED:GAVE_UP"
    [g] = sd.grade_legs(coupon(leg()), {DATE: {"events": {}}}, at=late)
    assert g["outcome"] == "NOT_GRADED:GAVE_UP", "never settled at all"
    [g] = sd.grade_legs(coupon(leg()), waiting)
    assert g["outcome"] == "PENDING:NOT_ON_SOFASCORE", "no clock, no give-up"


def test_a_price_taken_after_the_real_start_is_not_counted() -> None:
    ev = hockey_event(
        t1_periods=[3, 2, 1], t2_periods=[0, 0, 0], t1_full=6, t2_full=0,
        sofascore_start_utc=iso(AT - timedelta(minutes=5)),
    )
    [g] = sd.grade_legs(
        coupon(leg(price_fetched_at_utc=iso(AT))), {DATE: {"events": {"1": ev}}}
    )
    assert g["outcome"] == "IN_PLAY_PRICE"


# --- the files ----------------------------------------------------------------------


def write_settled(
    root: Path, sport: sd.SportKey, date: str, events: dict[str, dict[str, Any]]
) -> None:
    d = sd.day_dir(str(root), sport, date)
    d.mkdir(parents=True, exist_ok=True)
    (d / cs2.SETTLED_FILE).write_text(
        json.dumps({"date": date, "sport": sport, "events": events}), encoding="utf-8"
    )


def test_settled_tournaments_are_read_from_earlier_days_only(tmp_path: Path) -> None:
    write_settled(tmp_path, "volleyball", "2026-10-03", {
        "1": {"tournament": "Liga", "state": "SETTLED"},
        "2": {"tournament": "Puchar", "state": "NOT_ON_SOFASCORE"},
    })
    write_settled(tmp_path, "volleyball", "2026-10-04", {
        "3": {"tournament": "Dzisiaj", "state": "SETTLED"},
    })
    assert sd.settled_tournaments(str(tmp_path), "volleyball", "2026-10-04") == ["Liga"]


def test_a_torn_snapshot_line_is_skipped_and_counted(tmp_path: Path) -> None:
    d = write_snaps(tmp_path, "hockey", DATE,
                    [snap("1", total_pair("1", 1.20, 4.20), AT - timedelta(minutes=5))])
    # a torn line in the middle (a crash, then the next append) ...
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"half a line\n')
    write_snaps(tmp_path, "hockey", DATE,
                [snap("2", total_pair("2", 1.25, 3.80), AT - timedelta(minutes=4))])
    # ... and an append still in progress at the end (no newline yet)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"superbet_event_id": "3", "fetc')
    rows, lines, bad = sd.read_snapshots(d / "snapshots.jsonl")
    assert [r["superbet_event_id"] for r in rows] == ["1", "2"]
    # the unfinished last line is neither read nor counted: a replay after
    # it completes must not see a record the build never saw
    assert (lines, bad) == (3, 1)
    assert sd.load_snapshots(d / "snapshots.jsonl", upto_lines=1)[0][
        "superbet_event_id"] == "1"


def test_the_directory_lock_serialises_writers(tmp_path: Path) -> None:
    d = tmp_path / "x"
    with sd.dir_lock(d):
        with (d / ".lock").open("a") as fh, pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with (d / ".lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released


def test_a_moved_record_is_followed_to_its_file(tmp_path: Path) -> None:
    write_settled(tmp_path, "hockey", DATE, {"1": {"state": "MOVED_TO:2026-10-01"}})
    write_settled(tmp_path, "hockey", "2026-10-01", {"1": hockey_event()})
    settled = sd.settled_for(str(tmp_path), "hockey", {DATE})
    assert set(settled) == {DATE, "2026-10-01"}
    [g] = sd.grade_legs(coupon(leg()), settled)
    assert g["outcome"] == "WIN"
