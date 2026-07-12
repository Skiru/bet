"""Tests for the pipeline Orchestrator."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.pipeline.manifest import load_pipeline_manifest, validate_pipeline_manifest
from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


@pytest.fixture
def base_artifact_payload():
    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
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
        "payload": {},
    }


def write_test_artifact(base_dir: Path, step_id: str, status: str, payload_override: dict | None = None) -> Path:
    from bet.pipeline.artifact_gate import artifact_path_for, expected_s8_coupon_draft_path, sha256_file

    s9_manual_review = None
    if step_id == "S9" and status == "HUMAN_APPROVED":
        draft_path = expected_s8_coupon_draft_path(base_dir, "2026-06-25", "run-999")
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "artifact_type": "S8_COUPON_DRAFTS",
                    "betting_day": "2026-06-25",
                    "run_id": "run-999",
                    "requires_human_gate": True,
                    "ready_for_human_gate": True,
                    "ready_for_production_execution": False,
                    "production_selectable": False,
                    "production_coupon_write": False,
                    "executable_coupon": False,
                    "betclic_execution_enabled": False,
                    "coupon_draft_count": 1,
                    "drafts": [{"id": "quote-card-1"}],
                }
            ),
            encoding="utf-8",
        )
        s9_manual_review = {
            "reviewed_by_user": "mkoziol",
            "reviewed_at_utc": "2026-06-27T12:00:00Z",
            "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
            "approval_origin": "HUMAN_OPERATOR",
            "visible_operator_market_name": "Match winner",
            "visible_operator_line": "Home",
            "human_entered_decimal_quote": 2.1,
            "quote_as_of": "2026-06-27T11:59:00Z",
            "source_quote_card_id": "quote-card-1",
            "explicit_operator_decision": "APPROVE",
            "coupon_draft_path": str(draft_path),
            "coupon_draft_sha256": sha256_file(draft_path),
        }

    art = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT" if step_id != "S9" else "HUMAN_GATE",
        "step_id": step_id,
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": "run-999",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z" if step_id != "S9" else None,
        "source_bound": True if step_id != "S9" else False,
        "no_pick_edge_stake_coupon_emitted": True if step_id != "S9" else False,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["test-source"] if step_id != "S9" else [],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {},
        "manual_review": s9_manual_review,
    }
    if s9_manual_review is not None:
        art["checksum"] = s9_manual_review["coupon_draft_sha256"]
    if payload_override:
        art.update(payload_override)
    path = artifact_path_for(base_dir, "2026-06-25", "run-999", step_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(art), encoding="utf-8")
    return path


def test_manifest_loading_and_ordering():
    """Verify loading manifest, ensuring ordering is as expected."""
    manifest = load_pipeline_manifest()
    assert manifest.pipeline_id == "bet_pipeline_v1"
    assert manifest.global_rules["fail_closed"] is True

    steps = [s.id for s in manifest.steps if s.id]
    expected_order = [
        "S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9",
        "S3", "S4", "S5", "S6", "S7", "S7b", "S8", "S9", "S10",
    ]
    assert steps == expected_order


def test_s3_blocks_if_s2_9_is_missing(tmp_path):
    """Verify S3 is blocked if S2.9 artifact is missing or invalid."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    # Start-step is S3, requiring S2.9
    summary = orch.run(start_step="S3", stop_after_step="S3")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S3"
    assert any("Missing required artifact for S2.9" in b for b in summary["blockers"])


def test_agent_step_generates_work_order_and_blocks_when_artifact_missing(tmp_path):
    """Verify agent steps generate a work order and fail closed when artifact is missing."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )

    summary = orch.run(start_step="S2.3", stop_after_step="S2.3")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S2.3"
    assert summary["work_order_path"].endswith("S2.3_work_order.json")
    assert Path(summary["work_order_path"]).exists()
    assert any("Missing required agent artifact for step S2.3" in b for b in summary["blockers"])


def test_s3_can_proceed_if_s2_9_exists_and_valid(tmp_path, base_artifact_payload):
    """Verify S3 is executed if S2.9 artifact exists and passes."""
    # Write S2.9 PASS artifact to reports dir
    write_test_artifact(tmp_path / "reports", "S2.9", "PASS")

    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )

    # Mock the wrapper execution of S3 to write its script evidence and succeed
    with patch("bet.pipeline.orchestrator.subprocess.run") as mock_run:
        def side_effect(*args, **kwargs):
            from bet.pipeline.integration_artifacts import write_script_evidence
            write_script_evidence(
                "S3",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
            )
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m
        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S3", stop_after_step="S3")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S3"


def test_s8_blocks_if_s7_s7b_script_evidence_missing(tmp_path):
    """Verify S8 blocks if S7 or S7b script evidence is missing."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S8", stop_after_step="S8")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S8"


def test_s8_can_proceed_when_s7_s7b_exists(tmp_path):
    """Verify S8 can proceed when S7 and S7b SCRIPT_EVIDENCE are valid PASS."""
    # Write S7 and S7b PASS SCRIPT_EVIDENCE artifacts
    write_test_artifact(tmp_path / "reports", "S7", "PASS", {"artifact_type": "SCRIPT_EVIDENCE", "no_pick_edge_stake_coupon_emitted": False})
    write_test_artifact(tmp_path / "reports", "S7b", "PASS", {"artifact_type": "SCRIPT_EVIDENCE", "no_pick_edge_stake_coupon_emitted": False})

    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )

    with patch("subprocess.run") as mock_run:
        def side_effect(*args, **kwargs):
            from bet.pipeline.integration_artifacts import write_script_evidence
            write_script_evidence(
                "S8",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
            )
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m
        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S8", stop_after_step="S8")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S8"


def test_s10_blocks_if_s9_human_approved_missing(tmp_path):
    """Verify S10 blocks if S9 HUMAN_APPROVED is missing."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S10", stop_after_step="S10")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S10"


def test_s10_can_proceed_if_s9_approved(tmp_path):
    """Verify S10 runs if S9 HUMAN_APPROVED exists."""
    write_test_artifact(tmp_path / "reports", "S9", "HUMAN_APPROVED")

    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S10", stop_after_step="S10")
    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S10"


def test_s9_human_gate_step_blocks_on_unbound_coupon_draft(tmp_path):
    """Verify direct S9 execution fails closed for stale or arbitrary draft paths."""
    write_test_artifact(
        tmp_path / "reports",
        "S9",
        "HUMAN_APPROVED",
        payload_override={
            "checksum": "0" * 64,
            "manual_review": {
                "reviewed_by_user": "mkoziol",
                "reviewed_at_utc": "2026-06-27T12:00:00Z",
                "operator_workflow": "SUPERBET_MANUAL_BET_BUILDER",
                "approval_origin": "HUMAN_OPERATOR",
                "visible_operator_market_name": "Match winner",
                "visible_operator_line": "Home",
                "human_entered_decimal_quote": 2.1,
                "quote_as_of": "2026-06-27T11:59:00Z",
                "source_quote_card_id": "quote-card-1",
                "explicit_operator_decision": "APPROVE",
                "coupon_draft_path": "/tmp/2026-06-25_s8_coupon_drafts.json",
                "coupon_draft_sha256": "0" * 64,
            }
        },
    )

    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S9", stop_after_step="S9")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S9"
    assert any("MISMATCH_COUPON_DRAFT_PATH" in blocker for blocker in summary["blockers"])


def test_state_only_steps_write_marker_evidence(tmp_path):
    """Verify that state_only steps write STATE_MARKER evidence file."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S1e", stop_after_step="S1e")
    assert summary["status"] == "PASS"

    marker_path = tmp_path / "reports/pipeline_runs/2026-06-25/run-999/artifacts/S1e.json"
    assert marker_path.exists()
    data = json.loads(marker_path.read_text(encoding="utf-8"))
    assert data["artifact_type"] == "STATE_MARKER"
    assert data["status"] == "PASS"


def test_s4_live_shadow_without_live_ack_blocks_and_no_subprocess(tmp_path):
    """Verify S4 in LIVE_SHADOW mode blocks and does not invoke subprocess if ack is missing."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="LIVE_SHADOW",
        base_run_dir=tmp_path / "reports",
        allow_live_network=False,
    )
    with patch("subprocess.run") as mock_run:
        summary = orch.run(start_step="S4", stop_after_step="S4")
        assert summary["status"] == "BLOCK"
        assert summary["blocked_at_step"] == "S4"
        assert any("live network acknowledgment missing" in b for b in summary["blockers"])
        mock_run.assert_not_called()


def test_s4_live_shadow_with_live_ack_runs_subprocess(tmp_path):
    """Verify S4 in LIVE_SHADOW mode runs subprocess if live ack is present."""
    with patch.dict(os.environ, {"BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS"}):
        orch = Orchestrator(
            betting_day="2026-06-25",
            run_id="run-999",
            runtime_mode="LIVE_SHADOW",
            base_run_dir=tmp_path / "reports",
            allow_live_network=True,
        )
        with patch("subprocess.run") as mock_run:
            def side_effect(*args, **kwargs):
                from bet.pipeline.integration_artifacts import write_script_evidence
                write_script_evidence(
                    "S4",
                    status="PASS",
                    payload={"test": True},
                    sources=(),
                    evidence_refs=(),
                    environ=orch.env,
                )
                from unittest.mock import MagicMock
                m = MagicMock()
                m.returncode = 0
                return m
            mock_run.side_effect = side_effect
            summary = orch.run(start_step="S4", stop_after_step="S4")

        assert summary["status"] == "PASS"
        assert summary["last_completed_step"] == "S4"
        mock_run.assert_called_once()


def test_script_step_fails_closed_when_evidence_missing(tmp_path):
    """Verify a script step blocks if its process exits 0 but does not write script evidence."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    with patch("subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        m = MagicMock()
        m.returncode = 0
        mock_run.return_value = m
        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S0"
    assert any("Canonical script evidence missing" in b for b in summary["blockers"])
    assert any(step["blocked_reason"] == "BLOCKED_SCRIPT_EVIDENCE_MISSING" for step in summary["steps"] if step["step_id"] == "S0")


def test_script_step_passes_when_evidence_present(tmp_path):
    """Verify a script step passes if its process exits 0 and writes script evidence."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    with patch("subprocess.run") as mock_run:
        def side_effect(*args, **kwargs):
            from bet.pipeline.integration_artifacts import write_script_evidence
            write_script_evidence(
                "S0",
                status="PASS",
                payload={"test": True},
                sources=(),
                evidence_refs=(),
                environ=orch.env,
            )
            from unittest.mock import MagicMock
            m = MagicMock()
            m.returncode = 0
            return m
        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S0", stop_after_step="S0")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S0"


def test_run_summary_written_on_missing_script_evidence(tmp_path):
    """Verify run_summary.json is written with blocked condition when script evidence is missing."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    with patch("subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        m = MagicMock()
        m.returncode = 0
        mock_run.return_value = m
        summary = orch.run(start_step="S0", stop_after_step="S0")

    summary_path = orch.run_root / "run_summary.json"
    assert summary_path.exists()
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_data["status"] == "BLOCK"
    assert summary_data["blocked_at_step"] == "S0"
    assert any("Canonical script evidence missing" in b for b in summary_data["blockers"])


def test_s1_controlled_block_populates_run_summary_evidence_path(tmp_path):
    from bet.pipeline.integration_artifacts import script_evidence_path, write_script_evidence

    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-s1-summary",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "sandbox",
    )
    write_script_evidence(
        "S1",
        status="BLOCK",
        payload={"test": True},
        sources=(),
        evidence_refs=(),
        environ=orch.env,
        no_pick_edge_stake_coupon_emitted=True,
        production_selectable=False,
        betting_decisions_enabled=False,
        blocked_reasons=("BLOCKED_MISSING_MARKET_MATRIX",),
    )

    with patch("bet.pipeline.orchestrator.subprocess.run") as mock_run:
        from unittest.mock import MagicMock

        result = MagicMock()
        result.returncode = 2
        mock_run.return_value = result
        summary = orch.run(start_step="S1", stop_after_step="S1")

    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S1"
    s1_step = next(step for step in summary["steps"] if step["step_id"] == "S1")
    assert s1_step["status"] == "BLOCK"
    assert not any("Canonical script evidence missing for step 'S1'" in blocker for blocker in summary["blockers"])
    assert not any("BLOCKED_SCRIPT_EVIDENCE_MISSING" in str(blocker) and "S1" in str(blocker) for blocker in summary["blockers"])

    canonical_evidence = script_evidence_path("S1", orch.env)
    assert canonical_evidence is not None
    assert canonical_evidence.exists()

    summary_path = orch.run_root / "run_summary.json"
    assert summary_path.exists()
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))
    s1_summary_step = next(step for step in summary_data["steps"] if step["step_id"] == "S1")
    assert s1_summary_step["evidence_path"] == str(canonical_evidence)
    assert any("BLOCKED_MISSING_MARKET_MATRIX" in blocker for blocker in summary_data["blockers"])


def test_orchestrator_writes_work_order_when_s2_3_missing(tmp_path):
    """Verify orchestrator writes work order when S2.3 artifact is missing, blocks, and does not run S2.5."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S2.3", stop_after_step="S2.5")
    
    # Blocks at S2.3
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S2.3"
    
    # Work order is written
    from bet.pipeline.agent_work_orders import work_order_path_for
    wo_path = work_order_path_for(tmp_path / "reports", "2026-06-25", "run-999", "S2.3")
    assert wo_path.exists()
    
    # Contains work order path in top level and in individual steps
    assert summary["work_order_path"] == str(wo_path)
    s23_step = next(s for s in summary["steps"] if s["step_id"] == "S2.3")
    assert s23_step["work_order_path"] == str(wo_path)
    
    # S2.5 was not executed (skipped/not reached in loop execution list)
    steps_executed = [s["step_id"] for s in summary["steps"]]
    assert "S2.3" in steps_executed
    assert "S2.5" not in steps_executed


def test_orchestrator_writes_work_order_when_s5_missing(tmp_path):
    """Verify orchestrator writes work order when S5 artifact is missing, blocks, and does not run S6."""
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S5", stop_after_step="S6")
    
    # Blocks at S5
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S5"
    
    # Work order is written
    from bet.pipeline.agent_work_orders import work_order_path_for
    wo_path = work_order_path_for(tmp_path / "reports", "2026-06-25", "run-999", "S5")
    assert wo_path.exists()
    
    assert summary["work_order_path"] == str(wo_path)
    
    steps_executed = [s["step_id"] for s in summary["steps"]]
    assert "S5" in steps_executed
    assert "S6" not in steps_executed


def test_orchestrator_proceeds_on_valid_agent_artifact(tmp_path):
    """Verify orchestrator proceeds when a valid agent artifact exists."""
    # Write a fully valid S2.3 artifact
    write_test_artifact(
        tmp_path / "reports",
        "S2.3",
        "PASS",
        payload_override={
            "unknowns": [],
            "sources": ["tipster-s2"],
            "payload": {
                "enrichment_gaps": [],
                "gaps_status": "bounded",
            },
        }
    )
    
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S2.3", stop_after_step="S2.3")
    
    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S2.3"


def test_orchestrator_blocks_on_invalid_agent_artifact(tmp_path):
    """Verify orchestrator blocks when an agent artifact is invalid."""
    # Write S2.3 artifact with missing key fields / forbidden fields
    write_test_artifact(
        tmp_path / "reports",
        "S2.3",
        "PASS",
        payload_override={
            "payload": {
                "pick": "Arbitrary selection",
                "enrichment_gaps": []
            }
        }
    )
    
    orch = Orchestrator(
        betting_day="2026-06-25",
        run_id="run-999",
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path / "reports",
    )
    summary = orch.run(start_step="S2.3", stop_after_step="S2.3")
    
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S2.3"
    assert any("contract validation failure" in b for b in summary["blockers"])
