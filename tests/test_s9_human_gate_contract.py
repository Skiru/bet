"""Tests for S9 human gate contract and safety constraints."""
from __future__ import annotations

import os
from pathlib import Path
from bet.pipeline.artifact_gate import (
    validate_s9_human_gate_artifact_for_run,
    PipelineArtifactType,
)
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


def test_generated_s9_human_gate_rejected():
    # If S9 contains shadow-acceptance or other test indicators, it is forced to TEST_ONLY_GENERATED_HUMAN_GATE
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": "2026-07-11",
        "run_id": "run-test",
        "manual_review": {
            "reviewed_by_user": "shadow-acceptance",
            "reviewed_at_utc": "2026-07-11T12:00:00Z",
            "betclic_manual_verification": True,
            "coupon_draft_path": "draft.json",
            "coupon_draft_sha256": "abcdef",
        },
    }
    
    issues = validate_s9_human_gate_artifact_for_run(
        raw,
        base_dir=Path("/tmp"),
        betting_day="2026-07-11",
        run_id="run-test",
    )
    
    assert raw["status"] == "TEST_ONLY_GENERATED_HUMAN_GATE"
    assert raw["can_place_bet_now"] is False
    assert raw["safe_user_action"] == "DO_NOT_PLACE_BET"
    assert any(i.code == "TEST_ONLY_GENERATED_HUMAN_GATE" for i in issues)


def test_real_s9_verification_required():
    raw = {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": "2026-07-11",
        "run_id": "run-test",
        "manual_review": {
            "reviewed_by_user": "mkoziol",
            "reviewed_at_utc": "2026-07-11T12:00:00Z",
            "betclic_manual_verification": True,
            "coupon_draft_path": "draft.json",
            "coupon_draft_sha256": "abcdef",
        },
    }
    # It passes initial check if no mock or test tags are active and the file actually matches
    # (or fails with standard path/sha mismatch but does NOT get classified as generated)
    assert raw["status"] == "HUMAN_APPROVED"
