"""Tests for pipeline artifact gate validation and pre-requisite step checking."""
from __future__ import annotations

from pathlib import Path
import pytest

from bet.pipeline.readiness_contracts import PipelineReadinessStatus
from bet.pipeline.artifact_gate import (
    load_artifact,
    validate_pipeline_artifact,
    evaluate_gate_before_step,
    artifact_path_for,
    find_forbidden_decision_signals,
)


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
    raw = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "status": "PASS",
        "betting_day": "2026-06-24",
        "run_id": "run-1",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-24T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["understat"],
        "payload": {},
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert artifact is not None
    assert not issues


def test_forbidden_decision_signals_blocking_keys():
    """Verify that nested keys representing forbidden decision terms trigger blocks."""
    raw = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "status": "PASS",
        "betting_day": "2026-06-24",
        "run_id": "run-1",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-24T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["understat"],
        "payload": {"nested": {"edge": 0.05, "coupon": {"id": "1"}}},
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert any(i.code == "FORBIDDEN_DECISION_SIGNALS" for i in issues)


def test_allowed_negative_assertions_do_not_block():
    """Verify that explicit safety/negative assertions are allowed to be true or false."""
    raw = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "status": "PASS",
        "betting_day": "2026-06-24",
        "run_id": "run-1",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-24T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["understat"],
        "payload": {
            "no_pick_edge_stake_coupon_emitted": True,
            "betting_decisions_enabled": False,
            "production_selectable": False,
        },
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert not issues


def test_secrets_blocking():
    """Verify that raw secret terms found inside payload cause BLOCK issues."""
    raw = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "status": "PASS",
        "betting_day": "2026-06-24",
        "run_id": "run-1",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-24T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["understat"],
        "payload": {"credentials": {"api_key": "some-value-secret"}},
    }
    artifact, issues = validate_pipeline_artifact(raw, "S2.9")
    assert any(i.code == "RAW_SECRETS_FOUND" for i in issues)


def test_evaluate_gate_s3_requires_s2_9(tmp_path):
    """Verify that gate evaluation for S3 checks S2.9 correctly."""
    # 1. S2.9 missing
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S2.9" in f for f in decision.failed_requirements)

    # 2. S2.9 malformed
    s2_9_path = artifact_path_for(tmp_path, "2026-06-24", "run-1", "S2.9")
    s2_9_path.parent.mkdir(parents=True, exist_ok=True)
    s2_9_path.write_text("{malformed", encoding="utf-8")
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Malformed" in r or "JSON" in r for r in decision.failed_requirements)

    # 3. S2.9 has UNKNOWN status
    s2_9_path.write_text(
        '{"schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": "S2.9", "status": "UNKNOWN", "betting_day": "2026-06-24", "run_id": "run-1", "sport": "Football", "fixture_id": null, "fixture_key": null, "point_in_time_as_of": "2026-06-24T12:00:00Z", "source_bound": true, "no_pick_edge_stake_coupon_emitted": true, "production_selectable": false, "betting_decisions_enabled": false, "sources": ["understat"], "payload": {}}',
        encoding="utf-8",
    )
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK

    # 4. S2.9 PASS
    s2_9_path.write_text(
        '{"schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": "S2.9", "status": "PASS", "betting_day": "2026-06-24", "run_id": "run-1", "sport": "Football", "fixture_id": null, "fixture_key": null, "point_in_time_as_of": "2026-06-24T12:00:00Z", "source_bound": true, "no_pick_edge_stake_coupon_emitted": true, "production_selectable": false, "betting_decisions_enabled": false, "sources": ["understat"], "payload": {}}',
        encoding="utf-8",
    )
    decision = evaluate_gate_before_step("S3", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.PASS


def test_evaluate_gate_s8_requires_s7_and_s7b(tmp_path):
    """Verify that S8 gate requires both S7 and S7b artifacts to pass."""
    # Write S7 PASS
    s7_path = artifact_path_for(tmp_path, "2026-06-24", "run-1", "S7")
    s7_path.parent.mkdir(parents=True, exist_ok=True)
    s7_path.write_text(
        '{"schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": "S7", "status": "PASS", "betting_day": "2026-06-24", "run_id": "run-1", "sport": "Football", "fixture_id": null, "fixture_key": null, "point_in_time_as_of": "2026-06-24T12:00:00Z", "source_bound": false, "no_pick_edge_stake_coupon_emitted": false, "production_selectable": true, "betting_decisions_enabled": true, "sources": ["model"], "payload": {}}',
        encoding="utf-8",
    )

    # S7b is missing
    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert any("Missing required artifact for S7b" in f for f in decision.failed_requirements)

    # Write S7b PASS
    s7b_path = artifact_path_for(tmp_path, "2026-06-24", "run-1", "S7b")
    s7b_path.write_text(
        '{"schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": "S7b", "status": "PASS", "betting_day": "2026-06-24", "run_id": "run-1", "sport": "Football", "fixture_id": null, "fixture_key": null, "point_in_time_as_of": "2026-06-24T12:00:00Z", "source_bound": false, "no_pick_edge_stake_coupon_emitted": false, "production_selectable": true, "betting_decisions_enabled": true, "sources": ["betclic_validate"], "payload": {}}',
        encoding="utf-8",
    )

    decision = evaluate_gate_before_step("S8", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.PASS


def test_evaluate_gate_s10_requires_s9(tmp_path):
    """Verify that S10 requires S9 to pass/be HUMAN_APPROVED."""
    s9_path = artifact_path_for(tmp_path, "2026-06-24", "run-1", "S9")
    s9_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. S9 missing
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK

    # 2. S9 HUMAN_REJECTED
    s9_path.write_text(
        '{"schema_version": 1, "artifact_type": "HUMAN_GATE", "step_id": "S9", "status": "HUMAN_REJECTED", "betting_day": "2026-06-24", "run_id": "run-1", "sport": null, "fixture_id": null, "fixture_key": null, "point_in_time_as_of": null, "source_bound": false, "no_pick_edge_stake_coupon_emitted": false, "production_selectable": true, "betting_decisions_enabled": true, "sources": [], "payload": {}}',
        encoding="utf-8",
    )
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.BLOCK

    # 3. S9 HUMAN_APPROVED
    s9_path.write_text(
        '{"schema_version": 1, "artifact_type": "HUMAN_GATE", "step_id": "S9", "status": "HUMAN_APPROVED", "betting_day": "2026-06-24", "run_id": "run-1", "sport": null, "fixture_id": null, "fixture_key": null, "point_in_time_as_of": null, "source_bound": false, "no_pick_edge_stake_coupon_emitted": false, "production_selectable": true, "betting_decisions_enabled": true, "sources": [], "payload": {}}',
        encoding="utf-8",
    )
    decision = evaluate_gate_before_step("S10", tmp_path, "2026-06-24", "run-1")
    assert decision.verdict == PipelineReadinessStatus.PASS
