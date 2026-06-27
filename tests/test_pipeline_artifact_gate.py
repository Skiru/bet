"""Tests for pipeline artifact gate validation and pre-requisite step checking."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    detect_secrets,
    evaluate_gate_before_step,
    find_forbidden_decision_signals,
    load_artifact,
    validate_pipeline_artifact,
)
from bet.pipeline.readiness_contracts import PipelineReadinessStatus


def base_artifact(
    step_id: str = "S2.9",
    artifact_type: str = "AGENT_ARTIFACT",
    status: str = "PASS",
) -> dict[str, object]:
    """Build a baseline artifact aligned with the main-aware readiness contract."""
    return {
        "schema_version": 1,
        "artifact_type": artifact_type,
        "step_id": step_id,
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": "run-001",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["merged-main-enrichment-shadow-foundation"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": ["Betclic market validation evidence event"],
        "payload": {
            "provider_authorization_status": "BLOCKED_NO_CREDENTIALS",
            "single_flight_probe": "Betclic market validation evidence event",
            "production_selectable": False,
            "betting_decisions_enabled": False,
        },
    }


def write_artifact(root: Path, artifact: dict[str, object]) -> Path:
    """Write a pipeline artifact to its canonical location for gate tests."""
    path = artifact_path_for(root, str(artifact["betting_day"]), str(artifact["run_id"]), str(artifact["step_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


def test_load_artifact_fails_closed(tmp_path):
    """Verify load_artifact raises errors for missing or invalid JSON."""
    with pytest.raises(ValueError, match="not found"):
        load_artifact(tmp_path / "does_not_exist.json")

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{malformed", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        load_artifact(bad_json)

    list_json = tmp_path / "list.json"
    list_json.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level must be an object"):
        load_artifact(list_json)


def test_validate_pipeline_artifact_valid():
    """Verify that a correct artifact dictionary validates with zero issues."""
    artifact, issues = validate_pipeline_artifact(base_artifact(), "S2.9")
    assert artifact is not None
    assert not issues


def test_forbidden_decision_signals_blocking_keys():
    """Verify nested forbidden decision keys trigger blocks."""
    raw = base_artifact()
    raw["payload"] = {"nested": {"edge": 0.05, "coupon": {"id": "1"}}}
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is None
    assert any(i.code == "FORBIDDEN_DECISION_SIGNALS" for i in issues)


def test_allowed_negative_assertions_do_not_block():
    """Verify explicit safety/readiness assertions remain legal."""
    raw = base_artifact()
    raw["payload"] = {
        "no_pick_edge_stake_coupon_emitted": True,
        "betting_decisions_enabled": False,
        "production_selectable": False,
        "provider_authorization": {"status": "BLOCKED_NO_CREDENTIALS"},
        "authorized_for_sanitized_live_probe": False,
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is not None
    assert not issues


def test_secrets_blocking():
    """Verify forbidden secret/header keys still block."""
    raw = base_artifact()
    raw["payload"] = {"credentials": {"api_key": "some-value-secret"}}
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is None
    assert any(i.code == "RAW_SECRETS_FOUND" for i in issues)


def test_safe_main_enrichment_strings_do_not_false_positive():
    """Verify current main readiness/evidence phrases remain legal."""
    assert find_forbidden_decision_signals({"note": "Betclic market validation evidence event"}) == []
    assert find_forbidden_decision_signals({"note": "provider_authorization_status=BLOCKED_NO_CREDENTIALS"}) == []


def test_forbidden_decision_phrases_block():
    """Verify phrase-strict string scanning blocks only explicit decision phrases."""
    assert find_forbidden_decision_signals({"note": "recommended pick: home win"})
    assert find_forbidden_decision_signals({"note": "stake: 1u"})


def test_secret_scanner_allows_main_authorization_metadata():
    """Verify current main authorization metadata does not trip the secret scanner."""
    raw = base_artifact()
    raw["payload"]["provider_authorization"] = {"status": "BLOCKED_NO_CREDENTIALS"}
    assert detect_secrets(raw) == []


def test_authorized_sanitized_live_probe_metadata_does_not_block():
    """Verify sanitized live-probe authorization metadata stays allowed."""
    raw = base_artifact()
    raw["payload"] = {
        "authorization_status": "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        "provider_authorization_status": "AUTHORIZED_FOR_SANITIZED_LIVE_PROBE",
        "authorized_for_sanitized_live_probe": True,
        "single_flight_probe": "sanitized evidence event",
    }
    assert detect_secrets(raw) == []
    assert find_forbidden_decision_signals(raw) == []
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is not None
    assert not issues


def test_secret_scanner_blocks_authorization_header():
    """Verify secret/header keys still block even when readiness metadata is allowed."""
    raw = base_artifact()
    raw["payload"]["authorization_header"] = "Bearer abc"
    assert any(path.endswith("authorization_header") for path in detect_secrets(raw))


@pytest.mark.parametrize("key", ["edge", "coupon"])
def test_find_forbidden_decision_keys_block(key: str):
    """Verify exact forbidden decision keys still block."""
    raw = base_artifact()
    raw["payload"][key] = 0.07
    signals = find_forbidden_decision_signals(raw)
    assert any(f"'{key}'" in signal for signal in signals)


@pytest.mark.parametrize(
    ("status", "should_pass"),
    [("WARN", False), ("SKIPPED", False), ("HUMAN_APPROVED", False), ("PASS", True)],
)
def test_s2_9_status_semantics(status: str, should_pass: bool):
    """Verify S2.9 accepts PASS only as a required AGENT_ARTIFACT gate."""
    artifact, issues = validate_pipeline_artifact(base_artifact(status=status), "S2.9")
    if should_pass:
        assert artifact is not None
        assert not issues
    else:
        assert artifact is None
        assert any(issue.code == "INVALID_REQUIRED_ARTIFACT_STATUS" for issue in issues)


def test_evaluate_gate_s3_requires_s2_9(tmp_path):
    """Verify S3 gate requires a valid S2.9 PASS artifact."""
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S2.9" in item for item in decision.failed_requirements)

    s2_9_path = artifact_path_for(tmp_path, "2026-06-25", "run-001", "S2.9")
    s2_9_path.parent.mkdir(parents=True, exist_ok=True)
    s2_9_path.write_text("{malformed", encoding="utf-8")
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Malformed" in item or "JSON" in item for item in decision.failed_requirements)

    for status, expected in (
        ("WARN", PipelineReadinessStatus.BLOCK),
        ("SKIPPED", PipelineReadinessStatus.BLOCK),
        ("HUMAN_APPROVED", PipelineReadinessStatus.BLOCK),
        ("PASS", PipelineReadinessStatus.PASS),
    ):
        root = tmp_path / status
        write_artifact(root, base_artifact(status=status))
        decision = evaluate_gate_before_step("S3", root, "2026-06-25", "run-001")
        assert decision.verdict == expected


def test_evaluate_gate_s8_requires_s7_and_s7b(tmp_path):
    """Verify S8 gate requires S7 and S7b SCRIPT_EVIDENCE PASS artifacts."""
    s7 = base_artifact(step_id="S7", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S7b" in item for item in decision.failed_requirements)

    s7b = base_artifact(step_id="S7b", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7b["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.PASS


def test_evaluate_gate_s8_blocks_agent_artifact_s7b(tmp_path):
    """Verify S7b AGENT_ARTIFACT blocks S8 even with PASS status."""
    s7 = base_artifact(step_id="S7", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7["no_pick_edge_stake_coupon_emitted"] = False
    s7b = base_artifact(step_id="S7b", artifact_type="AGENT_ARTIFACT", status="PASS")
    write_artifact(tmp_path, s7)
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert "S7b" in decision.blocked_artifacts


def test_evaluate_gate_s8_blocks_agent_artifact_s7(tmp_path):
    """Verify S7 AGENT_ARTIFACT blocks S8 even when S7b is valid script evidence."""
    s7 = base_artifact(step_id="S7", artifact_type="AGENT_ARTIFACT", status="PASS")
    s7b = base_artifact(step_id="S7b", artifact_type="SCRIPT_EVIDENCE", status="PASS")
    s7b["no_pick_edge_stake_coupon_emitted"] = False
    write_artifact(tmp_path, s7)
    write_artifact(tmp_path, s7b)

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert "S7" in decision.blocked_artifacts


def test_unknown_step_type_pair_does_not_satisfy_required_gate():
    """Verify unknown step/type pairs fail closed instead of accepting PASS."""
    artifact, issues = validate_pipeline_artifact(base_artifact(), "S8")
    assert artifact is None
    assert any(issue.code == "INVALID_REQUIRED_ARTIFACT_STATUS" for issue in issues)


def test_evaluate_gate_s10_requires_s9(tmp_path):
    """Verify S10 requires S9 HUMAN_GATE/HUMAN_APPROVED."""
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-25", "run-001")
    assert decision.verdict == PipelineReadinessStatus.BLOCK

    for status, expected in (
        ("PASS", PipelineReadinessStatus.BLOCK),
        ("HUMAN_REJECTED", PipelineReadinessStatus.BLOCK),
        ("UNKNOWN", PipelineReadinessStatus.BLOCK),
        ("HUMAN_APPROVED", PipelineReadinessStatus.PASS),
    ):
        artifact = base_artifact(step_id="S9", artifact_type="HUMAN_GATE", status=status)
        artifact["point_in_time_as_of"] = None
        artifact["source_bound"] = False
        artifact["no_pick_edge_stake_coupon_emitted"] = False
        artifact["sources"] = []
        artifact["sport"] = None
        if status == "HUMAN_APPROVED":
            artifact["manual_review"] = {
                "reviewed_by_user": "test-user",
                "reviewed_at_utc": "2026-06-25T12:00:00Z",
                "betclic_manual_verification": "VERIFIED",
                "coupon_draft_path": str(tmp_path / "mock_drafts.json"),
            }
        write_artifact(tmp_path / status, artifact)
        decision = evaluate_gate_before_step("S10", tmp_path / status, "2026-06-25", "run-001")
        assert decision.verdict == expected
