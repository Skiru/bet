import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_complete_control_plane_validator_passes():
    env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        "POWER_AGENT_VALIDATION_SKIP_WORKTREE_REPORTS": "1",
    }
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_power_agent_control_plane.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_agent_config_validator_covers_all_four_skills():
    validator = (ROOT / "scripts/validate-bet-agent-config.py").read_text(
        encoding="utf-8"
    )
    for name in (
        "betting-pipeline-contract",
        "betting-evidence-contract",
        "betting-pipeline-runtime",
        "context-safe-agentics",
    ):
        assert f'"{name}"' in validator


def test_tool_matrix_matches_agent_capability_contract():
    matrix = (ROOT / ".kilo/docs/betting_agent_tool_matrix.md").read_text(
        encoding="utf-8"
    )
    expected_rows = (
        "| `bet-executor` | allow | deny | deny | allow | "
        "exactly six partner agents; wildcard deny |",
        "| `bet-researcher` | deny | allow | allow | allow | deny |",
        "| `bet-modeler` | deny | allow | deny | allow | deny |",
        "| `bet-risk-gatekeeper` | deny | allow | allow | allow | deny |",
        "| `bet-builder` | deny | deny | deny | allow | deny |",
        "| `bet-auditor` | allow (verification only) | allow | deny | allow | deny |",
        "| `bet-settler-postevent` | deny | allow | deny | allow | deny |",
    )
    for row in expected_rows:
        assert row in matrix
