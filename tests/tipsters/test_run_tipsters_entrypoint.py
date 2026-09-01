"""The TIPSTERS entrypoint must survive being started.

Why this file exists
--------------------
``run_tipsters.py`` failed on every invocation from 2026-08-31 to 2026-09-01 and
no test noticed, because no test referenced the script at all. The 213 tests in
this directory import ``bet.tipsters.*`` directly, so none of them ever executed
the import chain that was broken -- ``run_tipsters`` -> ``bet.tipsters.live`` ->
``extractors`` -> ``zawodtyper`` -> ``bet.pipeline`` -> a manifest validated at
module scope against agent files that had been deleted.

The failure was invisible in every way a test usually looks. It happened during
import, so it preceded argparse and the try block that was supposed to keep a
bad tipster day non-fatal; the process exited 1 with no AGENT_SUMMARY and wrote
no ``pipeline_runs`` row. A green unit suite sat next to a step that had not run
once in two days.

So these tests start the actual script in a subprocess. They are deliberately
offline -- no source is fetched -- because what they guard is not scraping but
the far more basic property that the entrypoint can be launched at all.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "simple" / "run_tipsters.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=ROOT, timeout=120,
    )


def test_the_entrypoint_imports_and_starts():
    """--help does nothing but prove every module on the path loads."""
    result = _run("--help")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr
    assert "--event-list" in result.stdout


def test_the_live_tipster_path_does_not_import_the_legacy_pipeline():
    """``bet.pipeline`` validates a manifest at import and may raise.

    The live step must not be able to die from that, so the coupling is checked
    directly rather than only through its symptom.
    """
    probe = (
        "import sys; sys.path.insert(0, 'src');"
        "import bet.tipsters.live;"
        "print(sorted(m for m in sys.modules if m.startswith('bet.pipeline')))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=ROOT, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", (
        f"bet.tipsters.live pulled in {result.stdout.strip()}; the live TIPSTERS "
        "step must stay independent of the legacy S0-S10 package"
    )


def test_a_missing_event_list_fails_the_precondition_cleanly(tmp_path):
    """Exit 2 and a parseable summary, not a traceback."""
    result = _run(
        "--event-list", str(tmp_path / "absent.json"),
        "--output-dir", str(tmp_path),
        "--no-persist",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    summary = [ln for ln in result.stdout.splitlines() if ln.startswith("AGENT_SUMMARY:")]
    assert summary, result.stdout
    assert json.loads(summary[0][len("AGENT_SUMMARY:"):])["verdict"] == "PRECONDITION_FAILED"


def test_a_missing_attestation_refuses_to_fetch(tmp_path):
    """No source may be fetched without the operator's review file."""
    event_list = tmp_path / "events.json"
    event_list.write_text(json.dumps({
        "run_id": "RID-1", "generated_at": "2026-09-01T09:00:00Z",
        "date": "2026-09-01", "sports": ["football"], "events": [],
    }), encoding="utf-8")
    result = _run(
        "--event-list", str(event_list),
        "--output-dir", str(tmp_path),
        "--review-json", str(tmp_path / "no-such-review.json"),
        "--no-persist",
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
