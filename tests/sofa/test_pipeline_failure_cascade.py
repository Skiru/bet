"""A failed stage must not feed, or overwrite, the stages after it (2026-10-01).

The day: `sqlite3.OperationalError: database is locked` stopped RESOLVE at 15
of 461 board fixtures. RESOLVE's `finally` wrote those 15 (F15, right), and
then OFFER and SAMPLES ran on them and replaced the day's 04_offer.json and
03_samples.json with a 15-fixture stub (wrong). Two defences, both tested:

1. run_pipeline skips every stage after a FAILED one unless
   --continue-on-failure is given;
2. a RESOLVE that dies leaves 02_fixtures.json.INCOMPLETE beside the
   artifact, and every stage that builds the product refuses to read it, so a
   hand-run `--only OFFER` cannot repeat the overwrite either.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from bet.sofa.artifact_guard import (
    clear_incomplete,
    incomplete_reason,
    mark_incomplete,
    marker_path,
)

REPO = Path(__file__).resolve().parents[2]
DATE = "2026-01-01"


def _env(tmp_path: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO / "src"), str(REPO / "scripts"), str(REPO)]
    )
    env["SOFA_RUNS_DIR"] = str(tmp_path / "runs")
    env["SOFA_DB_PATH"] = str(tmp_path / "t.db")
    return env


def _run_driver(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    driver = tmp_path / "driver.py"
    driver.write_text(textwrap.dedent(body), encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(driver)],
        capture_output=True,
        text=True,
        env=_env(tmp_path),
        cwd=str(REPO),
        timeout=120,
    )


_PIPELINE_DRIVER = """
    import json, sys, types
    import scripts.sofa.run_pipeline as rp

    ran = []
    def stage(name, fn):
        mod = types.ModuleType(name)
        mod.main = fn
        sys.modules[name] = mod

    def _boom():
        ran.append("BOOM")
        raise RuntimeError("database is locked")
    def _after():
        ran.append("AFTER")
        return 0
    def _last():
        ran.append("LAST")
        return 0
    stage("boom_stage", _boom)
    stage("after_stage", _after)
    stage("last_stage", _last)

    rp.STAGE_MODULES = {
        "BOOM": "boom_stage", "AFTER": "after_stage", "LAST": "last_stage"
    }
    rp.DEFAULT_SEQUENCE = [("BOOM", "BOOM"), ("AFTER", "AFTER"), ("LAST", "LAST")]
    sys.argv = ["run_pipeline", "--date", "2026-01-01"] + EXTRA
    code = rp.main()
    print("PROBE: " + json.dumps({"ran": ran, "code": code}))
"""


def _probe(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    assert proc.returncode == 0, proc.stderr[-3000:]
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("PROBE: "))
    probe: dict[str, object] = json.loads(line.removeprefix("PROBE: "))
    return probe


def _summary(proc: subprocess.CompletedProcess[str]) -> dict[str, object]:
    line = next(
        ln for ln in proc.stdout.splitlines() if ln.startswith("SOFA_SUMMARY: ")
    )
    summary: dict[str, object] = json.loads(line.removeprefix("SOFA_SUMMARY: "))
    return summary


def test_a_failed_stage_skips_every_stage_after_it(tmp_path: Path) -> None:
    proc = _run_driver(tmp_path, "EXTRA = []\n" + textwrap.dedent(_PIPELINE_DRIVER))
    probe = _probe(proc)
    assert probe["ran"] == ["BOOM"], "a stage ran on the failed stage's leftovers"
    assert probe["code"] == 2
    assert "STAGE_EXCEPTION" in proc.stderr
    assert "AFTER: SKIPPED (upstream BOOM FAILED" in proc.stderr
    stages = _summary(proc)["metrics"]["stages"]  # type: ignore[index]
    assert [s["verdict"] for s in stages] == ["FAILED", "SKIPPED", "SKIPPED"]
    assert _summary(proc)["verdict"] == "FAILED"


def test_continue_on_failure_runs_them_deliberately(tmp_path: Path) -> None:
    proc = _run_driver(
        tmp_path,
        'EXTRA = ["--continue-on-failure"]\n' + textwrap.dedent(_PIPELINE_DRIVER),
    )
    probe = _probe(proc)
    assert probe["ran"] == ["BOOM", "AFTER", "LAST"]
    assert probe["code"] == 2, "the run is still FAILED"


def test_old_stop_on_failure_flag_is_still_accepted(tmp_path: Path) -> None:
    proc = _run_driver(
        tmp_path, 'EXTRA = ["--stop-on-failure"]\n' + textwrap.dedent(_PIPELINE_DRIVER)
    )
    assert _probe(proc)["ran"] == ["BOOM"]


def test_a_partial_stage_does_not_stop_the_run(tmp_path: Path) -> None:
    """PARTIAL is the normal shape of RESOLVE/OFFER/SAMPLES; only FAILED stops."""
    body = textwrap.dedent(_PIPELINE_DRIVER).replace(
        'raise RuntimeError("database is locked")', "return 1"
    )
    proc = _run_driver(tmp_path, "EXTRA = []\n" + body)
    assert _probe(proc)["ran"] == ["BOOM", "AFTER", "LAST"]


# --------------------------------------------------------------------------
# the marker
# --------------------------------------------------------------------------


def test_marker_round_trip(tmp_path: Path) -> None:
    artifact = tmp_path / "02_fixtures.json"
    artifact.write_text("[]", encoding="utf-8")
    assert incomplete_reason(artifact) is None
    mark_incomplete(artifact, stage="RESOLVE", reason="OperationalError: locked")
    reason = incomplete_reason(artifact)
    assert reason is not None
    assert reason.startswith("UPSTREAM_INCOMPLETE 02_fixtures.json: RESOLVE")
    assert "OperationalError: locked" in reason
    clear_incomplete(artifact)
    assert incomplete_reason(artifact) is None
    clear_incomplete(artifact)  # idempotent


_RESOLVE_DRIVER = """
    import sqlite3, sys
    import bet.sofa.resolve as R
    import scripts.sofa.run_resolve as run_resolve
    from datetime import UTC, datetime
    from bet.sofa.contracts import Fixture

    calls = {"n": 0}
    def fake_resolve(self, sport, side, kickoff, opponent, **kw):
        calls["n"] += 1
        if calls["n"] > FAIL_AFTER:
            raise sqlite3.OperationalError("database is locked")
        return 10 + calls["n"], {"id": 100 + calls["n"]}, False

    R.SofaResolver.resolve_entity = fake_resolve
    R.SofaResolver.match_quality = lambda self, event, kickoff, opponent, **kw: 100.0

    def fake_parse(event, sport, ids, client, identity, **kw):
        return Fixture(
            sofascore_event_id=event["id"], superbet_event_ids=ids, sport=sport,
            kickoff_utc=datetime(2026, 1, 1, 18, 0, tzinfo=UTC),
            home_name="a", away_name="b", home_entity_id=1, away_entity_id=2,
            competition_name="C", competition_id=1, season_id=1,
            category_name="X", identity=identity, round_number=None,
            round_name=None, cup_round_type=None, previous_leg_event_id=None,
            venue_name=None, referee=None, ground_type=None,
            default_period_count=None,
        )

    run_resolve.parse_fixture = fake_parse
    sys.argv = ["run_resolve", "--date", "2026-01-01"]
    sys.exit(run_resolve.main())
"""


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
        for i in (1, 2, 3)
    ]
    (day / "01_board.json").write_text(json.dumps(board), encoding="utf-8")
    return day


def test_resolve_that_dies_marks_its_artifact(tmp_path: Path) -> None:
    day = _board(tmp_path)
    proc = _run_driver(tmp_path, "FAIL_AFTER = 2\n" + textwrap.dedent(_RESOLVE_DRIVER))
    assert proc.returncode != 0, "the scenario is a RESOLVE that dies"
    artifact = day / "02_fixtures.json"
    assert len(json.loads(artifact.read_text(encoding="utf-8"))) == 2, (
        "F15 still holds: what resolved survives"
    )
    reason = incomplete_reason(artifact)
    assert reason is not None, "a partial slate was written without a marker"
    assert "OperationalError: database is locked" in reason


def test_a_clean_resolve_clears_the_marker(tmp_path: Path) -> None:
    day = _board(tmp_path)
    artifact = day / "02_fixtures.json"
    mark_incomplete(artifact, stage="RESOLVE", reason="earlier failure")
    proc = _run_driver(tmp_path, "FAIL_AFTER = 99\n" + textwrap.dedent(_RESOLVE_DRIVER))
    assert proc.returncode in (0, 1), proc.stderr[-3000:]
    assert not marker_path(artifact).exists(), "a clean re-run left the marker"


# --------------------------------------------------------------------------
# every stage that builds the product refuses a marked artifact
# --------------------------------------------------------------------------

_SENTINEL = '{"sentinel": "the day before the failure"}'

READERS = [
    ("scripts.sofa.run_offer", ["--date", DATE], "04_offer.json"),
    ("scripts.sofa.run_samples", ["--date", DATE], "03_samples.json"),
    ("scripts.sofa.run_sheet", ["--date", DATE], "05_sheet.json"),
    ("scripts.sofa.run_coupon", ["--date", DATE], "06_coupon.json"),
    ("scripts.sofa.run_confidence", ["--date", DATE], "08_confidence.json"),
    ("scripts.sofa.build_coupon_pdf", ["--date", DATE], "KUPON_2026-01-01.pdf"),
]


@pytest.mark.parametrize(("module", "argv", "own_artifact"), READERS)
def test_reader_refuses_an_incomplete_fixtures_artifact(
    tmp_path: Path, module: str, argv: list[str], own_artifact: str
) -> None:
    day = tmp_path / "runs" / DATE
    day.mkdir(parents=True)
    (day / "02_fixtures.json").write_text("[]", encoding="utf-8")
    for name in ("03_samples.json", "04_offer.json", "05_sheet.json"):
        (day / name).write_text(_SENTINEL, encoding="utf-8")
    (day / own_artifact).write_text(_SENTINEL, encoding="utf-8")
    mark_incomplete(day / "02_fixtures.json", stage="RESOLVE", reason="locked")

    body = f"""
        import sys, importlib
        mod = importlib.import_module({module!r})
        sys.argv = [{module!r}] + {argv!r}
        sys.exit(mod.main())
    """
    proc = _run_driver(tmp_path, body)
    assert proc.returncode == 2, (proc.returncode, proc.stderr[-2000:])
    assert "UPSTREAM_INCOMPLETE 02_fixtures.json" in proc.stderr
    assert (day / own_artifact).read_text(encoding="utf-8") == _SENTINEL, (
        f"{module} overwrote {own_artifact} from a partial slate"
    )
