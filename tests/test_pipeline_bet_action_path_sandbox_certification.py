"""Integration test certifying the S8/S9 bet-action sandbox path."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


@pytest.fixture
def sandbox_env(tmp_path: Path) -> dict[str, str]:
    reports_dir = tmp_path / "reports"
    return {
        "BET_PIPELINE_RUNTIME_MODE": "DRY_RUN",
        "BET_PIPELINE_BETTING_DAY": "2026-06-26",
        "BET_PIPELINE_RUN_ID": "s8-s9-sandbox-test",
        "BET_PIPELINE_RUN_ROOT": str(reports_dir),
        "BET_PIPELINE_DATA_DIR": str(reports_dir / "pipeline_runs" / "2026-06-26" / "s8-s9-sandbox-test" / "data"),
        "BET_PIPELINE_COUPON_DIR": str(reports_dir / "pipeline_runs" / "2026-06-26" / "s8-s9-sandbox-test" / "coupons"),
        "BET_PIPELINE_ARTIFACT_DIR": str(reports_dir / "pipeline_runs" / "2026-06-26" / "s8-s9-sandbox-test" / "artifacts"),
    }


def test_bet_action_path_sandbox_certification(tmp_path: Path, sandbox_env: dict[str, str]):
    base_run_dir = tmp_path / "reports"
    orch = Orchestrator(
        betting_day="2026-06-26",
        run_id="s8-s9-sandbox-test",
        runtime_mode="DRY_RUN",
        base_run_dir=base_run_dir,
    )

    data_dir = Path(sandbox_env["BET_PIPELINE_DATA_DIR"])
    artifact_dir = Path(sandbox_env["BET_PIPELINE_ARTIFACT_DIR"])
    data_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # 1. Prepare S7 gate results and write to standard data dir
    s7_output_filename = "2026-06-26_s7_gate_results.json"
    s7_payload = {
        "date": "2026-06-26",
        "gate_results": {
            "approved": [
                {
                    "home_team": "Alpha",
                    "away_team": "Beta",
                    "sport": "football",
                    "odds": {"market_best": 1.95},
                    "best_market": {
                        "name": "Goals Over 2.5",
                        "direction": "OVER",
                        "line": 2.5,
                        "safety_score": 0.85,
                        "probability": 0.85,
                    }
                }
            ],
            "extended_pool": [],
            "rejected": []
        }
    }

    s7_data_path = data_dir / s7_output_filename
    s7_data_path.write_text(json.dumps(s7_payload), encoding="utf-8")

    # Write validation sidecar so S8 validates market availability successfully
    validation_filename = "betclic_market_validation_2026-06-26.json"
    validation_payload = {
        "date": "2026-06-26",
        "validation_status": "PASS",
        "validation": [
            {
                "event": "Alpha vs Beta",
                "market": "Goals Over 2.5",
                "betclic_available": True,
                "home_team": "Alpha",
                "away_team": "Beta",
                "sport": "football",
                "odds": {"market_best": 1.95},
                "best_market": {
                    "name": "Goals Over 2.5",
                    "direction": "OVER",
                    "line": 2.5,
                    "safety_score": 0.85,
                    "probability": 0.85,
                }
            }
        ]
    }
    val_path = data_dir / validation_filename
    val_path.write_text(json.dumps(validation_payload), encoding="utf-8")

    # 2. Prepare S7 and S7b script evidences payloads
    s7_evidence_payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S7",
        "status": "PASS",
        "betting_day": "2026-06-26",
        "run_id": "s8-s9-sandbox-test",
        "payload": {
            "approved_count": 1,
            "s7_json_output": str(s7_data_path),
            "sandbox_certification_fixture": True,
            "not_real_betting_recommendation": True,
            "market_availability_status": "AVAILABLE"
        }
    }

    s7b_evidence_payload = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S7b",
        "status": "PASS",
        "betting_day": "2026-06-26",
        "run_id": "s8-s9-sandbox-test",
        "payload": {
            "s7b_input_path": str(s7_data_path),
            "s7b_json_output": str(val_path)
        }
    }

    # Write S7.json and S7b.json to both places
    for name, payload in [("S7.json", s7_evidence_payload), ("S7b.json", s7b_evidence_payload)]:
        (artifact_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    # Force Orchestrator env to match sandbox_env exactly
    orch.env.update(sandbox_env)

    # Run S8 and S9
    with patch.dict(os.environ, sandbox_env, clear=False):
        summary = orch.run(start_step="S8", stop_after_step="S9")

    # 4. Verify outcomes
    s8_step = next(s for s in summary["steps"] if s["step_id"] == "S8")
    if s8_step["status"] != "PASS":
        stdout_log = Path(s8_step.get("stdout_path") or "")
        stderr_log = Path(s8_step.get("stderr_path") or "")
        if stdout_log.exists():
            print("--- S8 STDOUT ---")
            print(stdout_log.read_text())
        if stderr_log.exists():
            print("--- S8 STDERR ---")
            print(stderr_log.read_text())

    # Assert S8 PASS
    assert s8_step["status"] == "PASS"

    # Assert S8 draft path exists and matches expected contents
    s8_payload = json.loads(Path(s8_step["evidence_path"]).read_text(encoding="utf-8"))["payload"]
    draft_path = Path(s8_payload["s8_coupon_draft_path"])
    assert draft_path.exists()
    assert str(draft_path.resolve()).startswith(str(base_run_dir.resolve()))
    assert "/data/" in str(draft_path)
    assert str(draft_path) != "/tmp/2026-06-26_s8_coupon_drafts.json"
    assert s8_payload["executable_coupon"] is False
    assert s8_payload["requires_human_gate"] is True
    
    draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
    assert draft_data["artifact_type"] == "S8_COUPON_DRAFTS"
    assert draft_data["coupon_draft_count"] > 0
    assert draft_data["executable_coupon"] is False
    assert draft_data["production_coupon_write"] is False
    assert draft_data["betclic_execution_enabled"] is False

    # Assert S9 BLOCKS waiting for human approval
    s9_step = next(s for s in summary["steps"] if s["step_id"] == "S9")
    assert s9_step["status"] == "BLOCK"
    assert s9_step["blocked_reason"] == "BLOCKED_WAITING_FOR_HUMAN_APPROVAL"

    # Assert S10 not reached
    assert not any(s["step_id"] == "S10" for s in summary["steps"] if s["status"] != "SKIPPED")

    # Assert overall summary safety properties
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S9"
    assert summary["ready_for_production_execution"] is False
    assert summary["ready_for_human_gate_test"] is True
