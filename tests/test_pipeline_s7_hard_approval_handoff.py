"""Focused S7 wrapper handoff tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pipeline_steps import s5_gate


def _runtime_environ(tmp_path: Path) -> dict[str, str]:
    run_root = Path("/tmp") / f"bet-s7-handoff-{tmp_path.name}"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-25",
        "BET_PIPELINE_RUN_ID": "run-s7-handoff",
        "BET_PIPELINE_RUN_ROOT": str(run_root),
        "BET_PIPELINE_DATA_DIR": str(run_root / "data"),
        "BET_PIPELINE_COUPON_DIR": str(run_root / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(run_root / "artifacts"),
    }


def _canonical_evidence_path(environ: dict[str, str]) -> Path:
    return (
        Path(environ["BET_PIPELINE_RUN_ROOT"])
        / "pipeline_runs"
        / environ["BET_PIPELINE_BETTING_DAY"]
        / environ["BET_PIPELINE_RUN_ID"]
        / "artifacts"
        / "S7.json"
    )


def test_s7_wrapper_resolves_sandbox_input_and_passes_input_flag(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    data_dir = Path(environ["BET_PIPELINE_DATA_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    input_path = data_dir / "2026-06-25_s3_deep_stats.json"
    input_path.write_text(json.dumps({"analyses": [{"home_team": "Alpha", "away_team": "Beta"}]}), encoding="utf-8")

    recorded: dict[str, object] = {}

    def fake_run(cmd, env=None, capture_output=None, text=None):
        recorded["cmd"] = cmd
        recorded["env"] = env
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 0
    assert recorded["cmd"][-2] == "--input"
    assert Path(recorded["cmd"][-1]).resolve() == input_path.resolve()
    assert recorded["env"]["BET_PIPELINE_DATA_DIR"] == environ["BET_PIPELINE_DATA_DIR"]

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert Path(evidence["payload"]["s7_input_path"]).resolve() == input_path.resolve()
    assert evidence["payload"]["s7_json_output"].startswith("/tmp/")
    assert evidence["payload"]["s7_markdown_output"].startswith("/tmp/")


def test_s7_wrapper_missing_input_blocks_with_controlled_reason(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7_GATE_INPUT_MISSING"]
    assert evidence["payload"]["s7_input_path"] is None
