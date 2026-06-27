"""Focused S9 human gate boundary tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.readiness_contracts import PipelineReadinessStatus, PipelineArtifactType
from bet.pipeline.artifact_gate import validate_pipeline_artifact, evaluate_gate_before_step


def test_missing_s9_artifact_blocks(tmp_path: Path):
    # Verify that if S9 is evaluated and missing, it returns BLOCK
    # S10 requires S9
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-25", "run-999")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S9" in r for r in decision.failed_requirements)


def test_non_human_approved_s9_artifact_blocks():
    # If S9 exists but is BLOCK status, it fails validation
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "BLOCK"
    }
    artifact, issues = validate_pipeline_artifact(raw, "S9")
    # Since allow_block_status is False by default for prerequisite validation, it should contain BLOCK issues
    assert any(i.severity == PipelineReadinessStatus.BLOCK for i in issues)


def test_human_approved_missing_proof_blocks():
    # 1. Missing manual_review object completely
    raw_missing_review = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED"
    }
    artifact, issues = validate_pipeline_artifact(raw_missing_review, "S9")
    assert any(i.code == "MISSING_MANUAL_REVIEW" for i in issues)

    # 2. Incomplete manual_review object (missing fields)
    raw_incomplete = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "manual_review": {
            "reviewed_by_user": "mkoziol",
            "reviewed_at_utc": "2026-06-27T12:00:00Z",
            # missing betclic_manual_verification and coupon_draft_path
        }
    }
    artifact, issues = validate_pipeline_artifact(raw_incomplete, "S9")
    assert any(i.code == "INCOMPLETE_MANUAL_REVIEW" for i in issues)


def test_fully_valid_human_approved_passes_isolated_contract_test():
    raw_valid = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "manual_review": {
            "reviewed_by_user": "mkoziol",
            "reviewed_at_utc": "2026-06-27T12:00:00Z",
            "betclic_manual_verification": True,
            "coupon_draft_path": "/tmp/2026-06-25_s8_coupon_drafts.json"
        }
    }
    artifact, issues = validate_pipeline_artifact(raw_valid, "S9")
    assert len(issues) == 0
    assert artifact is not None
    assert artifact.status == PipelineReadinessStatus.HUMAN_APPROVED
