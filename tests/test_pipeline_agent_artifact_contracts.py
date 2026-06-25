"""Tests for agent artifact contracts, schema parsing, and validation."""
from __future__ import annotations

import pytest
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.agent_work_orders import build_agent_work_order
from bet.pipeline.agent_artifact_contracts import (
    agent_steps_from_manifest,
    required_agent_output_contract,
    validate_agent_artifact_for_work_order,
    agent_artifact_template_for_step,
)


def test_agent_steps_from_manifest():
    """Verify agent steps are correctly filtered and found from pipeline manifest."""
    manifest = load_pipeline_manifest()
    steps = agent_steps_from_manifest(manifest)
    assert steps == ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]


def test_required_agent_output_contract():
    """Verify required output contract retrieval works for defined steps."""
    for step_id in ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]:
        contract = required_agent_output_contract(step_id)
        assert contract["step_id"] == step_id
        assert contract["artifact_type"] == "AGENT_ARTIFACT"
        assert contract["required_statuses"] == ["PASS", "BLOCK"]
        assert isinstance(contract["schema_requirements"], dict)

    with pytest.raises(ValueError):
        required_agent_output_contract("S2")  # Not an agent step


def test_agent_artifact_template_for_step():
    """Verify templates can be built for each agent step."""
    for step_id in ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]:
        tpl = agent_artifact_template_for_step(step_id, "2026-06-25", "run-smoke")
        assert tpl["step_id"] == step_id
        assert tpl["betting_day"] == "2026-06-25"
        assert tpl["run_id"] == "run-smoke"
        assert tpl["artifact_type"] == "AGENT_ARTIFACT"
        assert isinstance(tpl["payload"], dict)


def test_validate_agent_artifact_for_work_order_success(tmp_path):
    """Verify validation passes on a correct artifact conforming to work order rules."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    
    # Valid S5 artifact payload conforming to S5 structure and contract
    artifact = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "run-smoke",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T14:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["injuries_db", "travel_db"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "injuries_context": {"player_A": "out"},
            "motivation_context": {"importance": "high"},
            "travel_schedule": {"distance": "short"},
            "morale_context": {"recent_form": "good"},
            "upset_risk": {"volatility": "low"}
        }
    }
    
    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert len(errors) == 0, f"Expected no errors, got: {errors}"


def test_validate_agent_artifact_for_work_order_failures(tmp_path):
    """Verify validation detects mismatches, forbidden outputs, and missing fields."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    
    # Mismatch run_id
    artifact = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S5",
        "status": "PASS",
        "betting_day": "2026-06-25",
        "run_id": "wrong-run-id",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T14:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["injuries_db", "travel_db"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [],
        "payload": {
            "injuries_context": {},
            "motivation_context": {},
            "travel_schedule": {},
            "morale_context": {},
            "upset_risk": {}
        }
    }
    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("run_id mismatch" in e for e in errors)

    # Forbidden decision signal in payload (e.g., stake or pick)
    artifact["run_id"] = "run-smoke"
    artifact["payload"]["pick"] = "Arsenal to win"
    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("Forbidden decision signal found" in e for e in errors)

    # S5 payload missing injuries check
    del artifact["payload"]["pick"]
    del artifact["payload"]["injuries_context"]
    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("S5 payload must contain context check for category 'injuries'" in e for e in errors)
