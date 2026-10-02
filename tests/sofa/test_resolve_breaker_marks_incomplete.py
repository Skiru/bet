"""A breaker that opens mid-RESOLVE leaves the slate marked incomplete.

The breaker's `break` in run_resolve.main() is not an exception, so before
this fix the stage cleared 02_fixtures.json.INCOMPLETE and returned PARTIAL -
the verdict a healthy RESOLVE returns too - and OFFER..PDF built the day on
whatever had resolved before the trip (reviewer's sim on the 10-01 board:
120 of 461, recall 26%, no marker). A clean `--from-stage RESOLVE` re-run must
remove the marker again and still carry the earlier pass forward.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from bet.sofa.artifact_guard import incomplete_reason, marker_path

REPO = Path(__file__).resolve().parents[2]
DATE = "2026-01-01"
N_BOARD = 10

_DRIVER = """
    import json, sys
    from datetime import UTC, datetime
    import scripts.sofa.run_resolve as run_resolve
    from bet.sofa.contracts import Fixture

    def fx(i, sid):
        return Fixture(
            sofascore_event_id=1000 + i, superbet_event_ids=[sid], sport="football",
            kickoff_utc=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
            home_name="a", away_name="b", home_entity_id=1, away_entity_id=2,
            competition_name="C", competition_id=1, season_id=1,
            category_name="X", identity="CONFIRMED", round_number=None,
            round_name=None, cup_round_type=None, previous_leg_event_id=None,
            venue_name=None, referee=None, ground_type=None,
            default_period_count=None,
        )

    def fake(bf, resolver, client, cache, stage):
        i = int(bf.superbet_event_id)
        if i in RESOLVE_IDS:
            f = fx(i, bf.superbet_event_id)
            return run_resolve.ResolveOutcome(
                bf, event_id=f.sofascore_event_id, fixture=f
            )
        if i >= TRIP_AT:
            return run_resolve.ResolveOutcome(
                bf, gap=run_resolve.GapReason.PROVIDER_ERROR, circuit_open=True
            )
        return run_resolve.ResolveOutcome(bf, gap=run_resolve.GapReason.PROVIDER_ERROR)

    run_resolve._resolve_one = fake
    sys.argv = ["run_resolve", "--date", "2026-01-01"]
    sys.exit(run_resolve.main())
"""


def _run(
    tmp_path: Path, resolve_ids: list[int], trip_at: int
) -> subprocess.CompletedProcess[str]:
    driver = tmp_path / "driver.py"
    driver.write_text(
        f"RESOLVE_IDS = {set(resolve_ids)!r}\nTRIP_AT = {trip_at}\n"
        + textwrap.dedent(_DRIVER),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), str(REPO)])
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")
    env["SOFA_DB_PATH"] = str(tmp_path / "t.db")
    env["SOFA_MAX_CONCURRENCY"] = "1"  # the trip lands at a fixed board index
    return subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO),
        timeout=120,
    )


def _board(tmp_path: Path) -> Path:
    day = tmp_path / "runs" / DATE
    day.mkdir(parents=True, exist_ok=True)
    board = [
        {
            "superbet_event_id": str(i),
            "sport": "football",
            "match_name": f"Team A{i} · Team B{i}",
            "side_a": f"Team A{i}",
            "side_b": f"Team B{i}",
            "kickoff_utc": "2026-01-01T18:00:00Z",
        }
        for i in range(N_BOARD)
    ]
    (day / "01_board.json").write_text(json.dumps(board), encoding="utf-8")
    return day


def _summary(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    line = next(
        ln for ln in proc.stdout.splitlines() if ln.startswith("SOFA_SUMMARY: ")
    )
    out: dict[str, object] = json.loads(line.removeprefix("SOFA_SUMMARY: "))
    return out


def test_breaker_trip_marks_the_slate_incomplete(tmp_path: Path) -> None:
    day = _board(tmp_path)
    proc = _run(tmp_path, resolve_ids=[0, 1, 2], trip_at=3)
    assert proc.returncode == 1, proc.stderr[-3000:]
    artifact = day / "02_fixtures.json"
    assert len(json.loads(artifact.read_text(encoding="utf-8"))) == 3, (
        "what resolved before the trip is still written"
    )
    reason = incomplete_reason(artifact)
    assert reason is not None, "a breaker-thinned slate was written without a marker"
    assert f"CIRCUIT_OPEN at 4/{N_BOARD}" in reason
    metrics = _summary(proc)["metrics"]
    assert isinstance(metrics, dict) and metrics["breaker_open"] is True


def test_clean_rerun_clears_the_marker_and_carries_the_earlier_pass(
    tmp_path: Path,
) -> None:
    day = _board(tmp_path)
    artifact = day / "02_fixtures.json"
    _run(tmp_path, resolve_ids=[0, 1, 2], trip_at=3)
    assert marker_path(artifact).exists()

    # The re-run resolves a different subset and never trips: the first
    # pass's fixtures are carried forward and the marker goes.
    proc = _run(tmp_path, resolve_ids=list(range(2, N_BOARD)), trip_at=N_BOARD + 1)
    assert proc.returncode in (0, 1), proc.stderr[-3000:]
    assert not marker_path(artifact).exists(), "a clean re-run left the marker"
    ids = sorted(f["sofascore_event_id"] for f in json.loads(artifact.read_text()))
    assert ids == [1000 + i for i in range(N_BOARD)]
    metrics = _summary(proc)["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["carried_from_previous_run"] == 2
    assert metrics["breaker_open"] is False


def test_pipeline_summary_surfaces_the_marker(tmp_path: Path) -> None:
    day = _board(tmp_path)
    _run(tmp_path, resolve_ids=[0], trip_at=1)
    driver = tmp_path / "pipe.py"
    driver.write_text(
        textwrap.dedent(
            """
            import sys, types
            import scripts.sofa.run_pipeline as rp
            mod = types.ModuleType("noop_stage")
            mod.main = lambda: 1
            sys.modules["noop_stage"] = mod
            rp.STAGE_MODULES = {"NOOP": "noop_stage"}
            rp.DEFAULT_SEQUENCE = [("NOOP", "NOOP")]
            sys.argv = ["run_pipeline", "--date", "2026-01-01"]
            rp.main()
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), str(REPO)])
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")
    env["SOFA_DB_PATH"] = str(tmp_path / "t.db")
    proc = subprocess.run(
        [sys.executable, str(driver)], capture_output=True, text=True,
        env=env, cwd=str(REPO), timeout=120,
    )
    metrics = _summary(proc)["metrics"]
    assert isinstance(metrics, dict)
    assert "CIRCUIT_OPEN at 2/10" in str(metrics["fixtures_incomplete"])
    assert (day / "02_fixtures.json.INCOMPLETE").exists()
