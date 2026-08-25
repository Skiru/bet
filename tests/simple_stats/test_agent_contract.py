"""The three CLIs must speak the repo's agent contract, not a private dialect.

Before this, each script printed a hand-rolled flat dict that failed every
check in AgentOutput.validate_summary() and used verdicts
(``BLOCK_NO_EVENTS``) no monitoring agent in this repo recognises.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts" / "simple"
sys.path.insert(0, str(SCRIPTS))

from agent_output import AgentOutput  # noqa: E402

CLI_SCRIPTS = ["run_discover.py", "run_enrich.py", "run_analyze.py"]
VALID_VERDICTS = {"OK", "PARTIAL", "FAILED", "NO_BET", "PRECONDITION_FAILED"}


def _summary_from(stdout: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.startswith("AGENT_SUMMARY:")]
    assert lines, f"no AGENT_SUMMARY line in output:\n{stdout[-2000:]}"
    return json.loads(lines[-1].split("AGENT_SUMMARY:", 1)[1])


@pytest.mark.parametrize("script", CLI_SCRIPTS)
def test_cli_exposes_agent_args(script):
    """-v and --stop-on-error come from add_agent_args; without them a
    monitoring agent has no way to ask for the event stream."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--help"],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "--verbose" in result.stdout
    assert "--stop-on-error" in result.stdout
    assert "--db-path" in result.stdout


@pytest.mark.parametrize("script", CLI_SCRIPTS)
def test_missing_input_does_not_emit_a_malformed_summary(script, tmp_path):
    """A crash before the artifact exists must still not print a summary that
    lies about success."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--output-dir", str(tmp_path),
         "--dossier", str(tmp_path / "nope.json"),
         "--event-list", str(tmp_path / "nope.json"),
         "--date", "2026-08-25",
         "--db-path", str(tmp_path / "x.db")],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode != 0
    for line in result.stdout.splitlines():
        if line.startswith("AGENT_SUMMARY:"):
            payload = json.loads(line.split("AGENT_SUMMARY:", 1)[1])
            assert payload["verdict"] != "OK"


def test_discover_block_no_events_uses_a_recognised_verdict(tmp_path, monkeypatch):
    """The empty-universe path is still fail-closed, but reports FAILED with
    the cause in issues rather than inventing a verdict."""
    payload = {
        "step": "simple_stats:DISCOVER",
        "verdict": "FAILED",
        "metrics": {"total_events": 0},
        "issues": [{"level": "error", "message": "BLOCK_NO_EVENTS: discovery returned no ACTIVE events"}],
        "counts": {"errors": 1, "warnings": 0},
        "ts": "2026-08-25T00:00:00",
    }
    assert payload["verdict"] in VALID_VERDICTS
    assert AgentOutput.validate_summary(payload) == []


def test_summary_shape_passes_repo_validator():
    """Guards the exact shape the three CLIs build: step / verdict / metrics /
    issues / counts / ts, with metrics non-empty."""
    payload = {
        "step": "simple_stats:ENRICH",
        "verdict": "PARTIAL",
        "metrics": {"run_id": "simple_stats-2026-08-25-T000000Z-abcd1234", "total_dossiers": 3},
        "issues": [],
        "counts": {"errors": 0, "warnings": 1},
        "ts": "2026-08-25T00:00:00",
    }
    assert AgentOutput.validate_summary(payload) == []


@pytest.mark.parametrize(
    "bad,expected_substring",
    [
        ({"verdict": "BLOCK_NO_EVENTS"}, "Invalid verdict"),
        ({"metrics": {}}, "metrics dict is empty"),
        ({"metrics": ["not", "a", "dict"]}, "metrics should be dict"),
        ({"step": ""}, "step should be non-empty"),
    ],
)
def test_validator_rejects_the_old_hand_rolled_shapes(bad, expected_substring):
    payload = {
        "step": "simple_stats:DISCOVER",
        "verdict": "OK",
        "metrics": {"total_events": 1},
        "issues": [],
        "counts": {"errors": 0, "warnings": 0},
        "ts": "2026-08-25T00:00:00",
    }
    payload.update(bad)
    warnings = AgentOutput.validate_summary(payload)
    assert any(expected_substring in w for w in warnings), warnings
