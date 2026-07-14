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
    run_root = Path(environ["BET_PIPELINE_RUN_ROOT"])
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)

    # Seed S6 output
    s6_output_path = run_root / "data" / "repeat_loss_handoff_2026-06-25.json"
    s6_output_path.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "run-s7-handoff",
        "accepted": [
            {
                "candidate_id": "c1",
                "decision": "ACCEPTED",
                "reason_codes": [],
                "explanation": "Passed",
                "original_candidate": {
                    "candidate_id": "c1",
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "sport": "football"
                }
            }
        ],
        "repeat_rejected": [],
        "correlation_rejected": [],
        "conflict_rejected": [],
        "portfolio_rejected": [],
        "invalid_input": [],
        "accounting": {
            "unaccounted_candidate_ids": [],
            "duplicate_candidate_ids": [],
            "overlapping_terminal_categories": []
        }
    }), encoding="utf-8")

    # Seed S6 evidence
    s6_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "betting_day": "2026-06-25",
        "run_id": "run-s7-handoff",
        "status": "PASS",
        "payload": {
            "s6_output_path": str(s6_output_path)
        }
    }
    (run_root / "artifacts" / "S6.json").write_text(json.dumps(s6_ev), encoding="utf-8")

    recorded: dict[str, object] = {}

    def fake_run(scripts, **kwargs):
        recorded["invocations"] = scripts
        return 0

    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]
    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv), patch("scripts.pipeline_steps._script_evidence.run_scripts", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 0
    assert recorded["invocations"][0].argv[-2] == "--input"
    assert Path(recorded["invocations"][0].argv[-1]).resolve() == s6_output_path.resolve()

    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert Path(evidence["payload"]["s7_input_path"]).resolve() == s6_output_path.resolve()
    assert evidence["payload"]["s7_input_source_step"] == "S6"


def test_s7_wrapper_missing_input_blocks_with_controlled_reason(tmp_path: Path):
    environ = _runtime_environ(tmp_path)
    argv = ["s5_gate.py", "--date", "2026-06-25", "--run-id", environ["BET_PIPELINE_RUN_ID"], "--runtime-mode", "DRY_RUN", "--dry-run"]

    with patch.dict(os.environ, environ, clear=False), patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            s5_gate.main()

    assert exc_info.value.code == 5
    evidence = json.loads(_canonical_evidence_path(environ).read_text(encoding="utf-8"))
    assert evidence["status"] == "BLOCK"
    assert evidence["blocked_reasons"] == ["BLOCKED_S7_S6_INPUT_MISSING"]
