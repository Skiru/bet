"""Focused S9 human gate boundary tests."""
from __future__ import annotations

import json
from pathlib import Path

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    evaluate_gate_before_step,
    expected_s8_coupon_draft_path,
    sha256_file,
    validate_pipeline_artifact,
    validate_s9_human_gate_artifact_for_run,
)
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


BETTING_DAY = "2026-06-25"
RUN_ID = "run-001"


def _write_s8_draft(base_dir: Path, run_id: str = RUN_ID, **overrides: object) -> Path:
    draft = {
        "schema_version": 1,
        "artifact_type": "S8_COUPON_DRAFTS",
        "betting_day": BETTING_DAY,
        "run_id": run_id,
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_selectable": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betclic_execution_enabled": False,
        "coupon_draft_count": 1,
        "drafts": [{"id": "draft-1"}],
    }
    draft.update(overrides)
    path = expected_s8_coupon_draft_path(base_dir, BETTING_DAY, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(draft), encoding="utf-8")
    return path


def _build_s9_artifact(draft_path: Path | str, draft_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "betting_day": BETTING_DAY,
        "run_id": RUN_ID,
        "manual_review": {
            "reviewed_by_user": "mkoziol",
            "reviewed_at_utc": "2026-06-27T12:00:00Z",
            "betclic_manual_verification": True,
            "coupon_draft_path": str(draft_path),
            "coupon_draft_sha256": draft_sha256,
        },
    }


def _write_s9_artifact(base_dir: Path, artifact: dict[str, object]) -> Path:
    path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, "S9")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def test_missing_s9_artifact_blocks(tmp_path: Path):
    # Verify that if S9 is evaluated and missing, it returns BLOCK
    # S10 requires S9
    decision = evaluate_gate_before_step("S10", tmp_path, BETTING_DAY, "run-999")
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
            # missing betclic_manual_verification, coupon_draft_path, and coupon_draft_sha256
        }
    }
    artifact, issues = validate_pipeline_artifact(raw_incomplete, "S9")
    assert any(i.code == "INCOMPLETE_MANUAL_REVIEW" for i in issues)


def test_s9_human_approved_with_bare_tmp_coupon_draft_path_blocks(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path)
    raw = _build_s9_artifact("/tmp/2026-06-25_s8_coupon_drafts.json", sha256_file(draft_path))

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)

    assert any(issue.severity == PipelineReadinessStatus.BLOCK for issue in issues)
    assert any(issue.code == "MISMATCH_COUPON_DRAFT_PATH" for issue in issues)


def test_s9_human_gate_accepts_only_matching_run_scoped_s8_draft(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path)
    raw = _build_s9_artifact(draft_path, sha256_file(draft_path))
    _write_s9_artifact(tmp_path, raw)

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)
    decision = evaluate_gate_before_step("S10", tmp_path, BETTING_DAY, RUN_ID)

    assert issues == []
    assert decision.verdict == PipelineReadinessStatus.PASS


def test_s9_human_gate_rejects_wrong_run_id_draft_path(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path, run_id="run-OTHER")
    raw = _build_s9_artifact(draft_path, sha256_file(draft_path))

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)

    assert any(issue.code == "MISMATCH_COUPON_DRAFT_PATH" for issue in issues)


def test_s9_human_gate_rejects_wrong_sha256(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path)
    raw = _build_s9_artifact(draft_path, "0" * 64)

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)

    assert any(issue.code == "MISMATCH_COUPON_DRAFT_SHA256" for issue in issues)


def test_s9_human_gate_rejects_unsafe_s8_draft_flags(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path, ready_for_production_execution=True)
    raw = _build_s9_artifact(draft_path, sha256_file(draft_path))

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)

    assert any(issue.code == "INVALID_S8_DRAFT_READY_FOR_PRODUCTION_EXECUTION" for issue in issues)


def test_s9_human_gate_rejects_repo_protected_coupon_draft_path(tmp_path: Path):
    draft_path = _write_s8_draft(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    protected_path = repo_root / "reports" / "pipeline_runs" / BETTING_DAY / RUN_ID / "data" / f"{BETTING_DAY}_s8_coupon_drafts.json"
    raw = _build_s9_artifact(protected_path, sha256_file(draft_path))

    issues = validate_s9_human_gate_artifact_for_run(raw, base_dir=tmp_path, betting_day=BETTING_DAY, run_id=RUN_ID)

    assert any(issue.code == "PROTECTED_COUPON_DRAFT_PATH" for issue in issues)
