"""The day-runner wrapper: sequencing, artifact threading, verdict aggregation.

These exercise `scripts/simple/run_pipeline.py` against stub steps rather than live
providers. The wrapper's job is orchestration, and orchestration bugs -- a
failed step whose successor runs anyway, a resumed run that invents a new
run_id, a crashed step read as OK -- are exactly the ones a live run hides
behind provider noise.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "scripts" / "simple" / "run_pipeline.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_pipeline_under_test", PIPELINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return _load_module()


def _stub(path: Path, *, verdict: str, metrics: dict, exit_code: int, writes: str | None = None) -> str:
    """Write a stub step speaking the AGENT_SUMMARY contract."""
    path.write_text(
        "import json, sys, argparse\n"
        "p = argparse.ArgumentParser()\n"
        "_, _rest = p.parse_known_args()\n"
        f"writes = {writes!r}\n"
        "if writes:\n"
        "    from pathlib import Path\n"
        "    Path(writes).write_text('{}')\n"
        "print('stub running')\n"
        f"print('AGENT_SUMMARY:' + json.dumps({{'step': 'stub', 'verdict': {verdict!r},"
        f" 'metrics': {metrics!r}, 'issues': [], 'counts': {{'errors': 0, 'warnings': 0}}}}))\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return str(path)


def _run(tmp_path: Path, stubs: dict[str, str], *extra: str) -> tuple[int, dict, str]:
    """Run the wrapper with STEP_SCRIPTS pointed at stubs; return (code, summary, stdout)."""
    harness = tmp_path / "harness.py"
    harness.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('rp', {str(PIPELINE)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"m.STEP_SCRIPTS.update({stubs!r})\n"
        "m.main()\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(harness), *extra],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    summary = {}
    for line in proc.stdout.splitlines():
        if line.startswith("AGENT_SUMMARY:"):
            summary = json.loads(line[len("AGENT_SUMMARY:"):])
    return proc.returncode, summary, proc.stdout


@pytest.fixture()
def out_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    return d


ALL_STEPS = ["discover", "enrich", "market_context", "tipsters", "superbet", "analyze"]


def _all_ok_stubs(tmp_path, out_dir, date="2026-08-25", run_id="RID-1"):
    event_list = out_dir / f"{date}_event_list.json"
    dossier = out_dir / f"{date}_event_dossiers.json"
    sheet = out_dir / f"{date}_event_dossiers_stats_sheet.json"
    context = out_dir / f"{date}_market_context.json"
    signal = out_dir / f"{date}_tipster_signal.json"
    superbet = out_dir / f"{date}_superbet_offer.json"
    return {
        "discover": _stub(
            tmp_path / "d.py", verdict="OK",
            metrics={"run_id": run_id, "output_path": str(event_list), "persisted": True},
            exit_code=0, writes=str(event_list),
        ),
        "enrich": _stub(
            tmp_path / "e.py", verdict="OK",
            metrics={"run_id": run_id, "output_path": str(dossier), "persisted": True},
            exit_code=0, writes=str(dossier),
        ),
        "market_context": _stub(
            tmp_path / "m.py", verdict="OK",
            metrics={"run_id": run_id, "output_path": str(context), "persisted": None},
            exit_code=0, writes=str(context),
        ),
        "tipsters": _stub(
            tmp_path / "t.py", verdict="OK",
            metrics={"run_id": run_id, "output_path": str(signal), "persisted": None},
            exit_code=0, writes=str(signal),
        ),
        "superbet": _stub(
            tmp_path / "s.py", verdict="OK",
            metrics={"run_id": run_id, "offer_path": str(superbet), "persisted": None},
            exit_code=0, writes=str(superbet),
        ),
        "analyze": _stub(
            tmp_path / "a.py", verdict="OK",
            metrics={"run_id": run_id, "output_path": str(sheet), "persisted": True},
            exit_code=0, writes=str(sheet),
        ),
    }


def test_clean_run_is_ok_and_exits_zero(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 0
    assert summary["verdict"] == "OK"
    assert summary["metrics"]["steps_run"] == ALL_STEPS


def test_exactly_one_agent_summary_is_emitted(tmp_path, out_dir):
    """Each child emits its own; a monitoring agent must not have to guess which
    of four is the run's verdict."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    _, _, stdout = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert sum(line.startswith("AGENT_SUMMARY:") for line in stdout.splitlines()) == 1


def test_verdict_is_the_worst_step_not_the_last(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    date = "2026-08-25"
    stubs["enrich"] = _stub(
        tmp_path / "e_partial.py", verdict="PARTIAL",
        metrics={"run_id": "RID-1", "output_path": str(out_dir / f"{date}_event_dossiers.json")},
        exit_code=1, writes=str(out_dir / f"{date}_event_dossiers.json"),
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", date, "--output-dir", str(out_dir))
    assert summary["metrics"]["step_verdicts"] == {
        "discover": "OK",
        "enrich": "PARTIAL",
        "market_context": "OK",
        "tipsters": "OK",
        "superbet": "OK",
        "analyze": "OK",
    }
    assert summary["verdict"] == "PARTIAL"
    assert code == 1


def test_a_failed_step_stops_the_run_before_the_next_one(tmp_path, out_dir):
    """ENRICH failing leaves ANALYZE nothing to read; continuing would only
    spend quota producing an artifact nobody can use."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["enrich"] = _stub(
        tmp_path / "e_fail.py", verdict="FAILED", metrics={"run_id": "RID-1"}, exit_code=2,
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 2
    assert summary["verdict"] == "FAILED"
    assert "analyze" not in summary["metrics"]["steps_run"]


def test_precondition_failed_propagates_and_stops(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["enrich"] = _stub(
        tmp_path / "e_pre.py", verdict="PRECONDITION_FAILED",
        metrics={"run_id": "RID-1"}, exit_code=2,
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 2
    assert summary["verdict"] == "PRECONDITION_FAILED"
    assert "analyze" not in summary["metrics"]["steps_run"]


def test_a_step_that_dies_without_a_summary_is_failed_not_ok(tmp_path, out_dir):
    """Reading a missing summary as OK is the silent-success failure mode."""
    crash = tmp_path / "crash.py"
    crash.write_text("import sys; sys.exit(137)\n", encoding="utf-8")
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["discover"] = str(crash)
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 2
    assert summary["verdict"] == "FAILED"
    assert summary["metrics"]["step_verdicts"]["discover"] == "FAILED"


def test_artifact_path_comes_from_metrics_not_a_filename_convention(tmp_path, out_dir):
    """DISCOVER writing somewhere unconventional must still feed ENRICH."""
    odd = out_dir / "somewhere-else.json"
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["discover"] = _stub(
        tmp_path / "d_odd.py", verdict="OK",
        metrics={"run_id": "RID-1", "output_path": str(odd)}, exit_code=0, writes=str(odd),
    )
    _, summary, stdout = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert summary["verdict"] == "OK"
    assert "somewhere-else.json" in stdout  # threaded into ENRICH's --event-list


def test_resume_adopts_the_run_id_stamped_in_the_artifact(tmp_path, out_dir):
    """A restarted run keeps its identity; minting a fresh id would report a
    run_id no step and no DB row ever used."""
    date = "2026-08-25"
    (out_dir / f"{date}_event_dossiers.json").write_text("{}", encoding="utf-8")
    stubs = _all_ok_stubs(tmp_path, out_dir, run_id="ORIGINAL-RUN")
    _, summary, _ = _run(
        tmp_path, stubs, "--date", date, "--output-dir", str(out_dir), "--start-at", "analyze"
    )
    assert summary["metrics"]["run_id"] == "ORIGINAL-RUN"
    assert summary["metrics"]["steps_run"] == ["analyze"]


def test_resume_without_the_upstream_artifact_is_precondition_failed(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir), "--start-at", "enrich"
    )
    assert code == 2
    assert summary["verdict"] == "PRECONDITION_FAILED"


def test_stop_after_runs_a_prefix_only(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir), "--stop-after", "discover"
    )
    assert code == 0
    assert summary["metrics"]["steps_run"] == ["discover"]


def test_stop_after_before_start_at_is_rejected(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, _, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir),
        "--start-at", "analyze", "--stop-after", "discover",
    )
    assert code == 2  # argparse error


def test_a_receipt_is_written_next_to_the_artifacts(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    receipt = json.loads((out_dir / "2026-08-25_run_summary.json").read_text())
    assert receipt["verdict"] == "OK"
    assert receipt["run_id"] == "RID-1"
    assert set(receipt["steps"]) == set(ALL_STEPS)
    assert receipt["steps"]["analyze"]["persisted"] is True


def test_summary_validates_against_the_repo_agent_contract(tmp_path, out_dir, module):
    from agent_output import AgentOutput

    stubs = _all_ok_stubs(tmp_path, out_dir)
    _, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert AgentOutput.validate_summary(summary) == []
    assert summary["step"] == "simple_stats:PIPELINE"


def test_severity_ordering_puts_failed_above_partial(module):
    sev = module._SEVERITY
    assert sev["OK"] < sev["PARTIAL"] < sev["PRECONDITION_FAILED"] <= sev["FAILED"]


# --- the two optional steps ------------------------------------------------
#
# TIPSTERS reaches third-party web pages and MARKET_CONTEXT reaches a paid API
# whose entitlement can lapse, so each will fail sometimes for reasons that have
# nothing to do with the betting day. These pin down that such a failure costs
# the run one column and nothing else.


def test_a_failed_tipster_step_does_not_fail_the_run(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["tipsters"] = _stub(
        tmp_path / "t_fail.py", verdict="FAILED", metrics={"run_id": "RID-1"}, exit_code=2
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 0
    assert summary["verdict"] == "OK"
    # Recorded per step, so the failure is visible rather than swallowed...
    assert summary["metrics"]["step_verdicts"]["tipsters"] == "FAILED"
    # ...and ANALYZE still ran, which is the whole point.
    assert summary["metrics"]["step_verdicts"]["analyze"] == "OK"


def test_a_failed_tipster_step_does_not_halt_the_pipeline(tmp_path, out_dir):
    """A non-optional failure stops the run; an optional one must not."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["tipsters"] = _stub(
        tmp_path / "t_pf.py", verdict="PRECONDITION_FAILED", metrics={"run_id": "RID-1"}, exit_code=2
    )
    _, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert summary["metrics"]["steps_run"] == ALL_STEPS


def test_skip_tipsters_omits_the_step_entirely(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir), "--skip-tipsters"
    )
    assert code == 0
    assert summary["metrics"]["steps_run"] == [
        "discover", "enrich", "market_context", "superbet", "analyze"
    ]
    assert summary["metrics"]["tipster_signal"] is None


def test_a_failed_market_context_step_does_not_fail_the_run(tmp_path, out_dir):
    """An entitlement that lapsed overnight, or a provider outage, costs the run
    its market column. It is not a bad betting day, and reporting it as one would
    train the operator to ignore the field that matters."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["market_context"] = _stub(
        tmp_path / "m_fail.py", verdict="FAILED", metrics={"run_id": "RID-1"}, exit_code=2
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 0
    assert summary["verdict"] == "OK"
    # Visible per step rather than swallowed...
    assert summary["metrics"]["step_verdicts"]["market_context"] == "FAILED"
    # ...and the run reached ANALYZE, which is the whole point of it being optional.
    assert summary["metrics"]["step_verdicts"]["analyze"] == "OK"


def test_skip_market_context_omits_the_step_entirely(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir),
        "--skip-market-context",
    )
    assert code == 0
    assert summary["metrics"]["steps_run"] == [
        "discover", "enrich", "tipsters", "superbet", "analyze"
    ]
    assert summary["metrics"]["market_context"] is None


def test_player_props_is_forwarded_to_enrich_only_when_passed(tmp_path, out_dir):
    """docs/PLAN_BOGATE_STATYSTYKI.md Faza 4b: --player-props must reach ENRICH
    when the operator asks for it, and must not appear (and so must not spend
    the extra bzzoiro calls) on an ordinary run that never mentioned it."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    echo = tmp_path / "e_echo.py"
    echo.write_text(
        "import json, sys\n"
        "print('ARGV:' + json.dumps(sys.argv[1:]))\n"
        "from pathlib import Path\n"
        f"Path({str(out_dir / '2026-08-25_event_dossiers.json')!r}).write_text('{{}}')\n"
        "print('AGENT_SUMMARY:' + json.dumps({'step': 'stub', 'verdict': 'OK',"
        " 'metrics': {'run_id': 'RID-1'}, 'issues': [], 'counts': {'errors': 0, 'warnings': 0}}))\n",
        encoding="utf-8",
    )
    stubs["enrich"] = str(echo)

    _, _, stdout_without = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    argv_without = next(line for line in stdout_without.splitlines() if line.startswith("ARGV:"))
    assert "--player-props" not in argv_without

    _, _, stdout_with = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir), "--player-props",
    )
    argv_with = next(line for line in stdout_with.splitlines() if line.startswith("ARGV:"))
    assert "--player-props" in argv_with


def test_analyze_is_handed_the_market_context_only_when_it_exists(tmp_path, out_dir):
    """Passing a path that was never written would make ANALYZE warn on every run
    in which this optional step was skipped -- the same trap the tipster flag
    already avoids."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    # A market-context step that reports a verdict but writes no artifact.
    stubs["market_context"] = _stub(
        tmp_path / "m_empty.py", verdict="PARTIAL", metrics={"run_id": "RID-1"}, exit_code=1
    )
    echo = tmp_path / "a_echo_market.py"
    echo.write_text(
        "import json, sys\n"
        "print('ARGV:' + json.dumps(sys.argv[1:]))\n"
        "print('AGENT_SUMMARY:' + json.dumps({'step': 'stub', 'verdict': 'OK',"
        " 'metrics': {'run_id': 'RID-1'}, 'issues': [], 'counts': {'errors': 0, 'warnings': 0}}))\n",
        encoding="utf-8",
    )
    stubs["analyze"] = str(echo)
    _, _, stdout = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    argv_line = next(line for line in stdout.splitlines() if line.startswith("ARGV:"))
    assert "--market-context" not in argv_line


def test_analyze_is_handed_the_signal_only_when_it_exists(tmp_path, out_dir):
    """The --tipster-signal flag must not appear when the file was never written.

    Passing a path that does not exist would make ANALYZE warn on every run in
    which the tipster step was skipped, training the operator to ignore warnings.
    """
    date = "2026-08-25"
    stubs = _all_ok_stubs(tmp_path, out_dir)
    # A tipster step that reports OK but writes nothing (every source blocked).
    stubs["tipsters"] = _stub(
        tmp_path / "t_empty.py", verdict="PARTIAL", metrics={"run_id": "RID-1"}, exit_code=1
    )
    echo = tmp_path / "a_echo.py"
    echo.write_text(
        "import json, sys\n"
        "print('ARGV:' + json.dumps(sys.argv[1:]))\n"
        "print('AGENT_SUMMARY:' + json.dumps({'step': 'stub', 'verdict': 'OK',"
        " 'metrics': {'run_id': 'RID-1'}, 'issues': [], 'counts': {'errors': 0, 'warnings': 0}}))\n",
        encoding="utf-8",
    )
    stubs["analyze"] = str(echo)
    _, _, stdout = _run(tmp_path, stubs, "--date", date, "--output-dir", str(out_dir))
    argv_line = next(line for line in stdout.splitlines() if line.startswith("ARGV:"))
    assert "--tipster-signal" not in argv_line


def _echo_stub(tmp_path, name="a_echo.py"):
    """An ANALYZE stub that prints the argv it was handed."""
    echo = tmp_path / name
    echo.write_text(
        "import json, sys\n"
        "print('ARGV:' + json.dumps(sys.argv[1:]))\n"
        "print('AGENT_SUMMARY:' + json.dumps({'step': 'stub', 'verdict': 'OK',"
        " 'metrics': {'run_id': 'RID-1'}, 'issues': [], 'counts': {'errors': 0, 'warnings': 0}}))\n",
        encoding="utf-8",
    )
    return str(echo)


def test_analyze_is_handed_the_superbet_offer_when_the_step_wrote_one(tmp_path, out_dir):
    """The wiring, end to end: SUPERBET writes it, ANALYZE is told where.

    A flag declared on both sides but never threaded between them is how a
    column silently stays empty on every real run while every unit test passes.
    """
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["analyze"] = _echo_stub(tmp_path)
    _, _, stdout = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    argv_line = next(line for line in stdout.splitlines() if line.startswith("ARGV:"))
    assert "--superbet-offer" in argv_line
    assert "2026-08-25_superbet_offer.json" in argv_line


def test_analyze_is_not_handed_a_superbet_offer_that_was_never_written(tmp_path, out_dir):
    """Passing a path that does not exist would make ANALYZE warn on every run
    where SUPERBET was skipped, which trains the operator to ignore warnings."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["analyze"] = _echo_stub(tmp_path)
    _, _, stdout = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir),
        "--skip-superbet",
    )
    argv_line = next(line for line in stdout.splitlines() if line.startswith("ARGV:"))
    assert "--superbet-offer" not in argv_line


def test_skip_superbet_omits_the_step_entirely(tmp_path, out_dir):
    stubs = _all_ok_stubs(tmp_path, out_dir)
    code, summary, _ = _run(
        tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir),
        "--skip-superbet",
    )
    assert code == 0
    assert "superbet" not in summary["metrics"]["steps_run"]


def test_a_failed_superbet_step_does_not_fail_the_run(tmp_path, out_dir):
    """A public offer host that moved costs the run its Superbet column. The
    stats sheet is unaffected, so the day is not a failure."""
    stubs = _all_ok_stubs(tmp_path, out_dir)
    stubs["superbet"] = _stub(
        tmp_path / "s_fail.py", verdict="FAILED", metrics={"run_id": "RID-1"}, exit_code=2
    )
    code, summary, _ = _run(tmp_path, stubs, "--date", "2026-08-25", "--output-dir", str(out_dir))
    assert code == 0
    assert summary["verdict"] == "OK"
    assert summary["metrics"]["step_verdicts"]["superbet"] == "FAILED"
    assert summary["metrics"]["step_verdicts"]["analyze"] == "OK"
