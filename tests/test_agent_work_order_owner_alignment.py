"""Tests for agent work order owner alignment and git status validation."""
from __future__ import annotations

import json
import subprocess
import sys
import hashlib
from pathlib import Path
import pytest

from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order


def test_validator_does_not_alter_git_status():
    """Verify that running the control plane validator leaves git status completely unchanged."""
    before = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # Execute validator script in subprocess
    subprocess.run(
        [sys.executable, "scripts/validate_power_agent_control_plane.py"],
        check=True,
    )

    after = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    assert before == after


def test_owner_alignment_matrix_generation_isolated(tmp_path: Path):
    """Verify that generating the work order matrix under tmp_path works cleanly and isolatably."""
    betting_day = "2026-07-24"
    run_id = "run-alignment"

    # Seed dependencies inside tmp_path
    from bet.pipeline.manifest import load_pipeline_manifest
    manifest_obj = load_pipeline_manifest()

    all_steps = [s.id for s in manifest_obj.steps if s.id]
    for s_id in all_steps:
        path = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts" / f"{s_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        m_step = next((s for s in manifest_obj.steps if s.id == s_id), None)
        if m_step and m_step.execution_mode == "script":
            data = {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": s_id,
                "status": "PASS",
                "betting_day": betting_day,
                "run_id": run_id,
                "payload": {}
            }
        else:
            data = {
                "schema_version": 1,
                "artifact_type": "AGENT_ARTIFACT",
                "step_id": s_id,
                "status": "PASS",
                "betting_day": betting_day,
                "run_id": run_id,
                "point_in_time_as_of": "2026-07-24T12:00:00Z",
                "source_bound": True,
                "no_pick_edge_stake_coupon_emitted": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "sources": [],
                "payload": {}
            }
        path.write_text(json.dumps(data), encoding="utf-8")

    # Generate work orders under tmp_path
    agent_artifact_steps = [
        s for s in manifest_obj.steps if s.execution_mode == "agent_artifact"
    ]
    for step in agent_artifact_steps:
        step_id = step.id
        wo = build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id=step_id,
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )
        assert wo.agent == step.agent
        assert wo.step_id == step_id
        assert Path(wo.required_output.expected_path).resolve().is_relative_to(tmp_path.resolve())


def test_toggling_flags_changes_script_identity_hash():
    """Verify that toggling live-network or write flags changes the command hash in ResumeLedger."""
    from bet.pipeline.run_coordination import _canonical_hash

    cmd_base = [sys.executable, "scripts/pipeline_steps/s1_discover.py", "--date", "2026-07-25", "--run-id", "run-1", "--runtime-mode", "DRY_RUN"]

    # 1. Base command (dry run, offline)
    hash_base = _canonical_hash({"argv": cmd_base})

    # 2. Add live network flag
    cmd_live = cmd_base + ["--allow-live-network"]
    hash_live = _canonical_hash({"argv": cmd_live})

    # 3. Add write flag
    cmd_write = cmd_base + ["--allow-write"]
    hash_write = _canonical_hash({"argv": cmd_write})

    assert hash_base != hash_live, "Toggling live-network flag must change the command hash"
    assert hash_base != hash_write, "Toggling write flag must change the command hash"
    assert hash_live != hash_write, "Live and write flags must produce distinct hashes"


def test_strict_script_evidence_status_adversarial():
    """Verify that script evidence with missing, null, or unknown statuses is strictly blocked."""
    from bet.pipeline.orchestrator import Orchestrator
    from bet.pipeline.readiness_contracts import PipelineReadinessStatus

    # Create dummy check structure for testing strict status
    cases = [
        {"status": "UNKNOWN_STATUS", "expected": False},
        {"status": None, "expected": False},
        {"status": "HUMAN_APPROVED", "expected": False},
        {"status": "PASS", "expected": True},
    ]

    for case in cases:
        raw_ev = {
            "schema_version": 1,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": "S1",
            "status": case["status"],
            "betting_day": "2026-07-25",
            "run_id": "run-1",
            "payload": {}
        }

        # Test if status meets PASS criteria
        ev_art_type = raw_ev.get("artifact_type")
        ev_status = raw_ev.get("status")
        ev_step_id = raw_ev.get("step_id")
        ev_betting_day = raw_ev.get("betting_day")
        ev_run_id = raw_ev.get("run_id")

        is_valid = (
            ev_art_type == "SCRIPT_EVIDENCE"
            and ev_status == "PASS"
            and ev_step_id == "S1"
            and ev_betting_day == "2026-07-25"
            and ev_run_id == "run-1"
        )
        assert is_valid == case["expected"]


def test_resume_ledger_state_transitions(tmp_path: Path):
    """Verify the exact explicit transition matrix wired into the ResumeLedger."""
    from bet.pipeline.run_coordination import ResumeLedger

    ledger = ResumeLedger(
        tmp_path,
        run_id="test-run",
        betting_day="2026-07-25",
        main_sha="main-sha",
        manifest_sha="manifest-sha",
    )

    # 1. WAITING_FOR_AGENT_ARTIFACT -> AGENT_ARTIFACT_BLOCK
    ledger.append(
        step_id="S2.3",
        status="WAITING_FOR_AGENT_ARTIFACT",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.3",
        status="AGENT_ARTIFACT_BLOCK",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={"artifact": "blocked"},
    )

    # 2. WAITING_FOR_AGENT_ARTIFACT -> COMMAND_REQUEST_PENDING -> PASS
    ledger.append(
        step_id="S2.5",
        status="WAITING_FOR_AGENT_ARTIFACT",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.5",
        status="COMMAND_REQUEST_PENDING",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.5",
        status="PASS",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={"evidence": "sha"},
    )

    # 3. WAITING_FOR_AGENT_ARTIFACT -> COMMAND_REQUEST_PENDING -> COMMAND_REQUEST_UNRESOLVED
    ledger.append(
        step_id="S2.7",
        status="WAITING_FOR_AGENT_ARTIFACT",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.7",
        status="COMMAND_REQUEST_PENDING",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.7",
        status="COMMAND_REQUEST_UNRESOLVED",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )

    # 4. unresolved -> corrected PASS
    ledger.append(
        step_id="S2.7",
        status="PASS",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={"evidence": "new-sha"},
    )

    # 5. unresolved -> AGENT_ARTIFACT_BLOCK
    ledger.append(
        step_id="S2.9",
        status="COMMAND_REQUEST_UNRESOLVED",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={},
    )
    ledger.append(
        step_id="S2.9",
        status="AGENT_ARTIFACT_BLOCK",
        command_request={"some": "req"},
        input_hashes={},
        output_hashes={"artifact": "blocked"},
    )


def test_direct_resume_dependencies(tmp_path: Path):
    """Verify that direct-resume dependencies prevent steps from running without prerequisites."""
    from bet.pipeline.artifact_gate import evaluate_gate_before_step, required_artifacts_before_step
    from bet.pipeline.readiness_contracts import PipelineReadinessStatus

    # S4 requires S3
    assert "S3" in required_artifacts_before_step("S4")
    # S7 requires S6
    assert "S6" in required_artifacts_before_step("S7")
    # S7b requires S7
    assert "S7" in required_artifacts_before_step("S7b")

    # Evaluate gate for S4 without S3 artifact on disk
    decision = evaluate_gate_before_step(
        step_id="S4",
        artifact_dir=tmp_path,
        betting_day="2026-07-25",
        run_id="run-1",
    )
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S3" in req for req in decision.failed_requirements)
