"""A sport-coupon leg nobody can grade is not a measurement (2026-10-01).

Two defects, one test group each:

- the build printed legs from events the measurement never finds on Sofascore
  (09-30 volleyball: 6 of 8 legs NOT_ON_SOFASCORE; 30 of 50 volleyball events,
  6/6 club friendlies), so they could never be graded;
- such a leg stayed PENDING for ever, because SETTLE's own 7-day give-up only
  fires when somebody settles that date again, and the daily loops settle D
  and D-1 only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import cs2
from bet.sofa import sport_coupon as sc
from tests.sofa.test_sport_coupon import (
    AT,
    DATE,
    build_cands,
    coupon,
    leg,
    run_build,
    snap,
    total_pair,
    write_snaps,
)

REPO = Path(__file__).resolve().parents[2]


def with_tournament(row: dict[str, Any], name: str) -> dict[str, Any]:
    return {**row, "tournament": name}


def write_settled(
    root: Path, sport: sc.SportKey, date: str, events: dict[str, dict[str, Any]]
) -> None:
    d = sc.day_dir(str(root), sport, date)
    d.mkdir(parents=True, exist_ok=True)
    (d / cs2.SETTLED_FILE).write_text(
        json.dumps({"date": date, "sport": sport, "events": events}), encoding="utf-8"
    )


# --- which tournaments are refused -------------------------------------------------


def test_a_friendly_is_never_a_leg() -> None:
    fresh = AT - timedelta(minutes=5)
    cands, counts = build_cands(
        [
            with_tournament(
                snap("1", total_pair("1", 1.20, 4.20), fresh),
                "Mecze towarzyskie - klubowe",
            ),
            with_tournament(
                snap("2", total_pair("2", 1.20, 4.20), fresh),
                "Mecze towarzyskie (K) - klubowe",
            ),
            snap("3", total_pair("3", 1.20, 4.20), fresh),
        ]
    )
    assert [c["superbet_event_id"] for c in cands] == ["3"]
    assert counts["friendly_tournament"] == 2


def test_the_unsettleable_list_is_read_from_earlier_settled_days(
    tmp_path: Path,
) -> None:
    def ev(tournament: str, state: str, **kw: Any) -> dict[str, Any]:
        return {"tournament": tournament, "state": state, **kw}

    write_settled(
        tmp_path,
        "volleyball",
        "2026-09-29",
        {
            "1": ev("Regional", "NOT_ON_SOFASCORE"),
            "2": ev("Liga", "SETTLED"),
            "3": ev("Once", "NOT_ON_SOFASCORE"),
        },
    )
    write_settled(
        tmp_path,
        "volleyball",
        "2026-09-28",
        {
            "4": ev("Regional", "GAVE_UP", gave_up_on="NOT_ON_SOFASCORE"),
            "5": ev("Liga", "SETTLED"),
            "6": ev("Liga", "NOT_ON_SOFASCORE"),
        },
    )
    # the day itself is never read: its outcomes are not known at build time
    write_settled(
        tmp_path, "volleyball", DATE, {"7": ev("Liga", "NOT_ON_SOFASCORE")}
    )
    got = sc.unsettleable_tournaments(str(tmp_path), "volleyball", DATE)
    # Regional 2/2; Liga 1/3 is under the share; Once is a single event
    assert got == {"Regional": "2/2"}


def test_an_unsettleable_tournament_is_left_out_whole() -> None:
    fresh = AT - timedelta(minutes=5)
    counts: dict[str, int] = {}
    events = sc.latest_events(
        "volleyball",
        [
            with_tournament(snap("1", total_pair("1", 1.20, 4.20), fresh), "Regional"),
            with_tournament(snap("2", total_pair("2", 1.20, 4.20), fresh), "Liga"),
        ],
    )
    cands = sc.candidates(
        "volleyball", events, AT, sc.Rule(), counts, unsettleable={"Regional": "2/2"}
    )
    assert {c["superbet_event_id"] for c in cands} == {"2"}
    assert counts["unsettleable_tournament"] == 1


def test_the_build_records_what_it_refused_and_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_settled(
        tmp_path,
        "hockey",
        "2026-09-29",
        {
            "a": {"tournament": "Gone", "state": "NOT_ON_SOFASCORE"},
            "b": {"tournament": "Gone", "state": "NOT_ON_SOFASCORE"},
        },
    )
    d = write_snaps(
        tmp_path,
        "hockey",
        DATE,
        [
            with_tournament(
                snap(
                    str(i),
                    total_pair(str(i), 1.20, 4.20),
                    AT - timedelta(minutes=5),
                    kickoff=AT + timedelta(hours=1 + i),
                ),
                name,
            )
            for i, name in enumerate(["Gone", "Liga", "Mecze towarzyskie"])
        ],
    )
    assert run_build(monkeypatch, tmp_path, AT) == 0
    doc = json.loads((d / sc.COUPON_FILE).read_text(encoding="utf-8"))
    assert [x["superbet_event_id"] for x in doc["legs"]] == ["1"]
    assert doc["unsettleable_tournaments"] == {"Gone": "2/2"}
    assert doc["counts"]["unsettleable_tournament"] == 1
    assert doc["counts"]["friendly_tournament"] == 1
    assert "UNSETTLEABLE_SHARE" in doc["UNFITTED_CONSTANTS"]


# --- a leg still waiting past the deadline is final --------------------------------


def test_a_leg_waiting_past_the_deadline_is_not_graded_not_pending() -> None:
    waiting = {DATE: {"events": {"1": {"state": "NOT_ON_SOFASCORE"}}}}
    soon = AT + timedelta(days=1)
    late = AT + sc.GIVE_UP_AFTER + timedelta(minutes=1)
    [g] = sc.grade_coupon(coupon(leg()), waiting, at=soon)
    assert g["outcome"] == "PENDING:NOT_ON_SOFASCORE", "inside the deadline: wait"
    [g] = sc.grade_coupon(coupon(leg()), waiting, at=late)
    assert g["outcome"] == "NOT_GRADED:GAVE_UP"
    [g] = sc.grade_coupon(coupon(leg()), {DATE: {"events": {}}}, at=late)
    assert g["outcome"] == "NOT_GRADED:GAVE_UP", "never settled at all"
    [g] = sc.grade_coupon(coupon(leg()), waiting)
    assert g["outcome"] == "PENDING:NOT_ON_SOFASCORE", "no clock, no give-up"


def test_settle_sport_coupon_stops_counting_a_dead_leg_as_pending(
    tmp_path: Path,
) -> None:
    d = sc.day_dir(str(tmp_path), "hockey", DATE)
    d.mkdir(parents=True)
    old = leg(kickoff_utc="2026-09-01T18:00:00Z")
    (d / sc.COUPON_FILE).write_text(json.dumps(coupon(old)), encoding="utf-8")
    write_settled(tmp_path, "hockey", DATE, {"1": {"state": "NOT_ON_SOFASCORE"}})
    env = {
        **dict(__import__("os").environ),
        "SOFA_RUNS_DIR": str(tmp_path),
        "PYTHONPATH": f"{REPO / 'src'}:{REPO}",
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts/sofa/settle_sport_coupon.py"),
            "--from",
            DATE,
            "--to",
            DATE,
            "--sport",
            "hockey",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    graded = json.loads((d / "sport_coupon_settled.json").read_text(encoding="utf-8"))
    assert [g["outcome"] for g in graded["legs"]] == ["NOT_GRADED:GAVE_UP"]
    row = next(ln for ln in proc.stdout.splitlines() if ln.startswith(f"| {DATE}"))
    cells = [c.strip() for c in row.strip("|").split("|")]
    assert cells[5] == "1" and cells[8] == "0", f"ungraded 1, pending 0: {row}"
