"""RESOLVE may add and may correct; it may not silently narrow a date (F54).

Sofascore's `events/next` drops a fixture at kickoff and `events/last` does not
pick it up until the match is marked finished, so a live or just-finished match
is in NEITHER listing. Replaying RESOLVE at 21:30 UTC against the same board
the 12:20 run used took the 2026-09-18 slate from 491 fixtures to 408: 131
lost, every one of them already kicked off, six of them on that day's coupon.

A `--from-stage RESOLVE` rebuild in the evening therefore used to replace the
morning's slate with a strictly smaller one, and report it as an ordinary bad
recall day.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _board(entries):
    return [
        {
            "superbet_event_id": e["superbet_event_id"],
            "sport": "football",
            "match_name": e["match_name"],
            "side_a": e["match_name"].split("·")[0],
            "side_b": e["match_name"].split("·")[1],
            "kickoff_utc": "2026-09-18T18:30:00Z",
            "tournament_id": 1,
            "category_id": 1,
        }
        for e in entries
    ]


def _fixture(event_id, superbet_ids, home="Home FC", away="Away FC"):
    return {
        "sofascore_event_id": event_id,
        "superbet_event_ids": superbet_ids,
        "sport": "football",
        "kickoff_utc": "2026-09-18T18:30:00Z",
        "home_name": home,
        "away_name": away,
        "home_entity_id": 1,
        "away_entity_id": 2,
        "competition_name": "Test League",
        "competition_id": 1,
        "season_id": 1,
        "category_name": "Testland",
        "identity": "CONFIRMED",
        "round_number": None,
        "round_name": None,
        "cup_round_type": None,
        "previous_leg_event_id": None,
        "venue_name": None,
        "referee": None,
        "ground_type": None,
        "default_period_count": 2,
        "superbet_kickoff_utc": "2026-09-18T18:30:00Z",
        "kickoff_disagreement_h": 0.0,
    }


@pytest.fixture()
def run_dir(tmp_path):
    date_dir = tmp_path / "2026-09-18"
    date_dir.mkdir()
    return tmp_path, date_dir


def _run(runs_dir, db_path):
    """RESOLVE against a board of names Sofascore will never match.

    The point is the merge, not the matching: with nothing resolvable the new
    pass contributes zero, which is exactly the shape of the evening re-run
    that lost 131 fixtures.
    """
    env = {
        "PATH": "/usr/bin:/bin",
        "PYTHONPATH": str(ROOT / "src") + ":" + str(ROOT),
        "SOFA_RUNS_DIR": str(runs_dir),
        "SOFA_DB_PATH": str(db_path),
        "SOFA_TRANSPORT": "bridge",
        "SOFA_BRIDGE_URL": "http://127.0.0.1:1",  # unreachable: every fetch fails
        "SOFA_BREAKER_THRESHOLD": "1",
        "SOFA_BREAKER_COOLDOWN_S": "1",
    }
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "sofa" / "run_resolve.py"),
            "--date",
            "2026-09-18",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(ROOT),
        timeout=120,
    )


def test_a_second_pass_that_resolves_nothing_keeps_the_first_pass(run_dir, tmp_path):
    runs_dir, date_dir = run_dir
    (date_dir / "01_board.json").write_text(
        json.dumps(_board([{"superbet_event_id": "S1", "match_name": "Zzz·Qqq"}]))
    )
    (date_dir / "02_fixtures.json").write_text(json.dumps([_fixture(999, ["S9"])]))

    _run(runs_dir, tmp_path / "sofa.db")

    kept = json.loads((date_dir / "02_fixtures.json").read_text())
    assert [f["sofascore_event_id"] for f in kept] == [999], (
        "the evening pass saw nothing and must not have deleted the morning"
    )


def test_the_summary_separates_carried_from_newly_resolved(run_dir, tmp_path):
    runs_dir, date_dir = run_dir
    (date_dir / "01_board.json").write_text(
        json.dumps(_board([{"superbet_event_id": "S1", "match_name": "Zzz·Qqq"}]))
    )
    (date_dir / "02_fixtures.json").write_text(json.dumps([_fixture(999, ["S9"])]))

    result = _run(runs_dir, tmp_path / "sofa.db")
    summary = json.loads(
        [ln for ln in result.stdout.splitlines() if ln.startswith("SOFA_SUMMARY")][
            -1
        ].split("SOFA_SUMMARY: ")[1]
    )
    metrics = summary["metrics"]
    assert metrics["carried_from_previous_run"] == 1
    assert metrics["resolved_this_run"] == 0
    assert metrics["output_fixtures"] == 1


def test_a_first_run_with_no_previous_artifact_still_works(run_dir, tmp_path):
    runs_dir, date_dir = run_dir
    (date_dir / "01_board.json").write_text(
        json.dumps(_board([{"superbet_event_id": "S1", "match_name": "Zzz·Qqq"}]))
    )
    result = _run(runs_dir, tmp_path / "sofa.db")
    assert (date_dir / "02_fixtures.json").exists()
    summary = json.loads(
        [ln for ln in result.stdout.splitlines() if ln.startswith("SOFA_SUMMARY")][
            -1
        ].split("SOFA_SUMMARY: ")[1]
    )
    assert summary["metrics"]["carried_from_previous_run"] == 0


def test_an_unreadable_previous_artifact_does_not_kill_the_stage(run_dir, tmp_path):
    runs_dir, date_dir = run_dir
    (date_dir / "01_board.json").write_text(
        json.dumps(_board([{"superbet_event_id": "S1", "match_name": "Zzz·Qqq"}]))
    )
    (date_dir / "02_fixtures.json").write_text("{ not json")
    result = _run(runs_dir, tmp_path / "sofa.db")
    assert "PREVIOUS_ARTIFACT_UNREADABLE" in result.stderr
    assert (date_dir / "02_fixtures.json").exists()
