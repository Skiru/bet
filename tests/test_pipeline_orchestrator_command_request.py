"""Tests for orchestrator COMMAND_REQUEST execution, hardening, and verification."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.readiness_contracts import PipelineReadinessStatus, PipelineArtifactType
from bet.pipeline.artifact_gate import artifact_path_for, expected_s8_coupon_draft_path
from bet.pipeline.run_coordination import BoundedProcessResult


@pytest.fixture
def base_artifact_payload():
    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.3",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "run-999",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "gaps": ["gap-1"],
            "gaps_bounded": True,
        },
    }


def write_test_artifact(base_dir: Path, step_id: str, status: str, payload_override: dict | None = None) -> Path:
    art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": "run-999",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {},
    }
    
    if step_id == "S2.3":
        art["payload"] = {
            "gaps": ["gap-1"],
            "gaps_bounded": True,
        }
    elif step_id == "S2.5":
        art["payload"] = {
            "provider_observations": ["coverage improved"],
        }
        
    if payload_override:
        art.update(payload_override)
        
    path = artifact_path_for(base_dir, "2026-06-25", "run-999", step_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art), encoding="utf-8")
    return path


def test_command_request_autopromotion_success(tmp_path, base_artifact_payload):
    """Verify standard structured COMMAND_REQUEST execution and autopromotion PASS."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Write S2.3 with COMMAND_REQUEST
    cmd_req = {
        "reason": "Run tests",
        "argv": [".venv/bin/python3", "-m", "pytest", "tests/test_pipeline_readiness_contracts.py", "-q"],
        "cwd": "REPO_ROOT",
        "timeout_seconds": 30,
        "expected_exit_code": 0,
        "postconditions": ["rerun_validate_agent_artifact"]
    }
    
    # Base payload override
    payload = {
        "command_request": cmd_req,
        "gaps": ["gap-1"],
        "gaps_bounded": True,
    }
    
    expected_path = write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {
        "command_request": cmd_req,
        "payload": payload,
        "unknowns": [],
    })
    
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    # Mock subprocess.run
    mock_res = MagicMock()
    mock_res.returncode = 0
    mock_res.stdout = "pytest passed successfully"
    mock_res.stderr = ""
    mock_res.timed_out = False
    
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_res) as mock_run:
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        
        mock_run.assert_called_once_with(
            cmd_req["argv"],
            cwd=str(orc.repo_root),
            env=orc.env,
            timeout_seconds=30.0,
        )
        
        assert summary["status"] == "PASS"
        assert summary["command_request_count"] == 1
        assert summary["executed_count"] == 1
        assert summary["failed_count"] == 0
        assert summary["unresolved_count"] == 0
        
        # Verify separate evidence file is written
        evidence_path = reports_dir / "pipeline_runs/2026-06-25/run-999/artifacts/S2.3_command_evidence.json"
        assert evidence_path.exists()
        ev_data = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert ev_data["status"] == "PASS"
        assert ev_data["exit_code"] == 0
        
        # Verify logs were written (logs folder is directly under run_root, not pipeline_runs)
        assert (reports_dir / "2026-06-25/run-999/logs/S2.3_cmd_stdout.log").exists()
        assert (reports_dir / "2026-06-25/run-999/logs/S2.3_cmd_stderr.log").exists()
        
        # Verify original command_request preservation
        assert (reports_dir / "pipeline_runs/2026-06-25/run-999/artifacts/S2.3_command_request.json").exists()
        
        # Verify original S2.3 was promoted to PASS and contains reference
        final_artifact = json.loads(expected_path.read_text(encoding="utf-8"))
        assert final_artifact["status"] == "PASS"
        assert any("S2.3_command_evidence.json" in ref for ref in final_artifact["evidence_refs"])


def test_command_request_string_and_metacharacter_rejection(tmp_path):
    """Verify string commands with metacharacters are rejected before execution."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_path = write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {
        "command_request": "pytest tests/; rm -rf /",
        "unknowns": [],
    })
    
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        mock_run.assert_not_called()
        
        assert summary["status"] == "BLOCK"
        # Since contract validation fails before step executes, counters remain 0, which is correct
        assert summary["command_request_count"] == 0
        assert summary["failed_count"] == 0
        assert summary["unresolved_count"] == 0
        assert any("Step S2.3 contract validation failure" in b for b in summary["blockers"])


def test_command_request_disallowed_executable_rejection(tmp_path):
    """Verify commands with disallowed executables are blocked before execution."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_path = write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {
        "command_request": {
            "argv": ["curl", "https://malicious.com"],
            "cwd": "REPO_ROOT"
        },
        "unknowns": [],
    })
    
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        mock_run.assert_not_called()
        
        assert summary["status"] == "BLOCK"
        assert summary["command_request_count"] == 0
        assert summary["failed_count"] == 0
        assert summary["unresolved_count"] == 0
        assert any("Step S2.3 contract validation failure" in b for b in summary["blockers"])


def test_command_request_nonzero_exit_code_blocks(tmp_path):
    """Verify nonzero exit code blocks execution and keeps status as BLOCK."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_path = write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {
        "command_request": {
            "argv": [".venv/bin/pytest", "tests/failing_test.py"],
            "cwd": "REPO_ROOT"
        },
        "unknowns": [],
    })
    
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    mock_res = MagicMock()
    mock_res.returncode = 1
    mock_res.stdout = "1 test failed"
    mock_res.stderr = ""
    mock_res.timed_out = False
    
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=mock_res):
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        
        assert summary["status"] == "BLOCK"
        assert summary["command_request_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["unresolved_count"] == 1
        assert any("exited with code 1, expected 0" in b for b in summary["blockers"])
        
        # Verify original S2.3 remained in COMMAND_REQUEST status (not promoted)
        final_artifact = json.loads(expected_path.read_text(encoding="utf-8"))
        assert final_artifact["status"] == "COMMAND_REQUEST"


def test_command_request_timeout_blocks(tmp_path):
    """Verify timeout is handled safely and blocks advancement."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    expected_path = write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {
        "command_request": {
            "argv": ["sleep", "10"],
            "timeout_seconds": 1
        },
        "unknowns": [],
    })
    
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    timed_out = BoundedProcessResult(returncode=-124, timed_out=True, stdout="", stderr="")
    with patch("bet.pipeline.orchestrator.run_bounded_process", return_value=timed_out):
        summary = orc.run(start_step="S2.3", stop_after_step="S2.3")
        
        assert summary["status"] == "BLOCK"
        assert summary["command_request_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["unresolved_count"] == 1
        assert any("execution timed out after 1s" in b for b in summary["blockers"])


def test_unresolved_command_request_blocks_downstream(tmp_path):
    """Verify unresolved command requests block downstream step execution."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # S2.3 has COMMAND_REQUEST, but we try to run S2.5
    write_test_artifact(reports_dir, "S2.3", "COMMAND_REQUEST", {"unknowns": []})
    
    # We do NOT run S2.3, we try to run S2.5 directly.
    # Prerequisite gate before S2.5 checks S2.3 artifact.
    orc = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=reports_dir,
    )
    
    summary = orc.run(start_step="S2.5", stop_after_step="S2.5")
    
    # S2.5 must be blocked because its prerequisite S2.3 is in COMMAND_REQUEST status (which is not PASS)
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S2.5"
    assert any("Artifact S2.3/AGENT_ARTIFACT requires one of ['PASS']" in b for b in summary["blockers"])
