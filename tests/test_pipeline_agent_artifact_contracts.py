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
        assert contract["required_statuses"] == ["PASS", "BLOCK", "COMMAND_REQUEST"]
        assert isinstance(contract["schema_requirements"], dict)

    with pytest.raises(ValueError):
        required_agent_output_contract("S2")  # Not an agent step


def test_agent_artifact_template_for_step():
    """Verify templates are safe non-final scaffolds for each agent step."""
    for step_id in ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]:
        tpl = agent_artifact_template_for_step(step_id, "2026-06-25", "run-smoke")
        assert tpl["step_id"] == step_id
        assert tpl["betting_day"] == "2026-06-25"
        assert tpl["run_id"] == "run-smoke"
        assert tpl["artifact_type"] == "AGENT_ARTIFACT"
        assert tpl["status"] == "BLOCK"
        assert tpl["blocked_reasons"] == ["TEMPLATE_NOT_FILLED"]
        assert tpl["source_bound"] is False
        assert tpl["no_pick_edge_stake_coupon_emitted"] is True
        assert tpl["production_selectable"] is False
        assert tpl["betting_decisions_enabled"] is False
        assert tpl["sources"] == []
        assert tpl["evidence_refs"] == []
        assert isinstance(tpl["payload"], dict)
        assert "TODO_FILL_BY_AGENT" in str(tpl["payload"])

    s29_tpl = agent_artifact_template_for_step("S2.9", "2026-06-25", "run-smoke")
    assert s29_tpl["payload"]["s3_may_proceed"] is False


def _build_base_artifact(step_id: str, status: str = "PASS") -> dict:
    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": status,
        "betting_day": "2026-06-25",
        "run_id": "run-smoke",
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": "2026-06-25T14:00:00Z" if status == "PASS" else None,
        "source_bound": True if status == "PASS" else False,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["verified-source"] if status == "PASS" else [],
        "unknowns": [],
        "blocked_reasons": [] if status == "PASS" else ["UPSTREAM_DATA_MISSING"],
        "evidence_refs": [],
        "payload": {},
    }


def test_validate_agent_artifact_for_work_order_success(tmp_path):
    """Verify validation passes on a correct artifact conforming to work order rules."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    artifact = _build_base_artifact("S5")
    artifact["sources"] = ["team-news", "travel-report"]
    artifact["evidence_refs"] = ["artifact_S3_run-smoke", "artifact_S4_run-smoke"]
    artifact["payload"] = {
        "injuries_context": {"player_A": "out"},
        "motivation_context": {"importance": "high"},
        "travel_schedule": {"distance": "short"},
        "morale_context": {"recent_form": "good"},
        "upset_risk": {"volatility": "low"},
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

    artifact = _build_base_artifact("S5")
    artifact["run_id"] = "wrong-run-id"
    artifact["evidence_refs"] = ["artifact_S3_run-smoke"]
    artifact["payload"] = {
        "injuries_context": {},
        "motivation_context": {},
        "travel_schedule": {},
        "morale_context": {},
        "upset_risk": {},
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
    assert any("S5 PASS payload must contain context check for category 'injuries/lineups'" in e for e in errors)


def test_template_like_artifact_does_not_validate_as_pass_output(tmp_path):
    """Verify a draft-like template cannot masquerade as a PASS artifact."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = agent_artifact_template_for_step("S2.9", "2026-06-25", "run-smoke")
    artifact["status"] = "PASS"

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("point_in_time_as_of" in e for e in errors)
    assert any("source_bound must be true" in e for e in errors)
    assert any("must contain non-empty 'evidence_refs'" in e for e in errors)


def test_s29_pass_with_only_s3_may_proceed_true_fails_validation(tmp_path):
    """Verify S2.9 PASS cannot rely on s3_may_proceed alone."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S2.9")
    artifact["evidence_refs"] = ["artifact_S2.3_run-smoke", "artifact_S2.5_run-smoke", "artifact_S2.7_run-smoke"]
    artifact["payload"] = {"s3_may_proceed": True}

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("readiness verdict" in e for e in errors)
    assert any("must not rely on s3_may_proceed alone" in e for e in errors)


def test_s29_pass_with_required_evidence_refs_passes_validation(tmp_path):
    """Verify S2.9 PASS validates when required upstream evidence refs and readiness verdict exist."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S2.9")
    artifact["evidence_refs"] = ["artifact_S2.3_run-smoke", "artifact_S2.5_run-smoke", "artifact_S2.7_run-smoke"]
    artifact["payload"] = {
        "readiness": "PASS",
        "readiness_basis": "S2.3/S2.5/S2.7 validated",
        "s3_may_proceed": True,
    }

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert errors == []


def test_s5_pass_missing_required_category_fails_validation(tmp_path):
    """Verify S5 PASS fails when one required context category is missing."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S5")
    artifact["evidence_refs"] = ["artifact_S3_run-smoke", "artifact_S4_run-smoke"]
    artifact["payload"] = {
        "injuries_context": {},
        "motivation_context": {},
        "travel_schedule": {},
        "morale_context": {},
    }

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("upset/volatility risk" in e for e in errors)


def test_s5_pass_with_all_required_categories_and_evidence_refs_passes(tmp_path):
    """Verify S5 PASS validates when all context categories and evidence refs are present."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S5")
    artifact["sources"] = ["injury-report", "motivation-brief"]
    artifact["evidence_refs"] = ["artifact_S3_run-smoke", "artifact_S4_run-smoke", "artifact_S2.9_run-smoke"]
    artifact["payload"] = {
        "injuries_lineups": {"status": "checked"},
        "motivation_tournament_context": {"status": "checked"},
        "travel_fatigue": {"status": "checked"},
        "morale_recent_form": {"status": "checked"},
        "upset_volatility_risk": {"status": "checked"},
    }

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert errors == []


def test_block_artifact_with_explicit_blocked_reasons_passes_validation(tmp_path):
    """Verify BLOCK artifacts validate when they remain explicit non-success outputs."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S2.3", status="BLOCK")
    artifact["payload"] = {
        "enrichment_gaps": ["missing_fixture_identity"],
        "gaps_status": "blocking",
    }

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert errors == []


def test_s25_pass_rejects_provider_promotion_changes(tmp_path):
    """Verify S2.5 PASS rejects provider promotion or selection changes."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    artifact = _build_base_artifact("S2.5")
    artifact["payload"] = {
        "provider_observations": ["coverage improved"],
        "preferred_provider": "new-provider",
    }

    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert any("provider promotion or selection changes" in e for e in errors)


def test_command_request_artifact_validation(tmp_path):
    """Verify COMMAND_REQUEST artifacts validate when they contain a command_request."""
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    
    # Valid typed COMMAND_REQUEST from the closed registry.
    artifact = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    artifact["command_request"] = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    errors = validate_agent_artifact_for_work_order(artifact, wo.to_jsonable())
    assert errors == []

    # Raw argv remains invalid even when it looks benign.
    artifact_structured = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    artifact_structured["command_request"] = {
        "argv": [".venv/bin/python3", "-m", "pytest", "tests/test_live_fixture_audit.py", "-q"],
    }
    errors_structured = validate_agent_artifact_for_work_order(artifact_structured, wo.to_jsonable())
    assert any("UNKNOWN_FIELDS" in e for e in errors_structured)

    # Invalid COMMAND_REQUEST (missing command_request)
    artifact_invalid = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    errors_invalid = validate_agent_artifact_for_work_order(artifact_invalid, wo.to_jsonable())
    assert any("COMMAND_REQUEST artifacts must contain a non-empty command_request" in e for e in errors_invalid)

    # Invalid COMMAND_REQUEST (shell metacharacters in string)
    artifact_meta = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    artifact_meta["command_request"] = "pytest tests/test_live_fixture_audit.py; rm -rf /"
    errors_meta = validate_agent_artifact_for_work_order(artifact_meta, wo.to_jsonable())
    assert any("MUST_BE_STRUCTURED" in e for e in errors_meta)

    # Invalid COMMAND_REQUEST (disallowed executable)
    artifact_bad_exec = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    artifact_bad_exec["command_request"] = {
        "command_id": "DOWNLOAD_REMOTE_SCRIPT",
        "parameters": {"url": "https://evil.example"},
    }
    errors_bad_exec = validate_agent_artifact_for_work_order(artifact_bad_exec, wo.to_jsonable())
    assert any("ID_NOT_ALLOWLISTED" in e for e in errors_bad_exec)

    # Invalid COMMAND_REQUEST (contains pick/coupon/stake/edge in payload keys)
    artifact_forbidden = _build_base_artifact("S2.3", status="COMMAND_REQUEST")
    artifact_forbidden["command_request"] = {
        "command_id": "WAIT_FOR_RATE_LIMIT",
        "parameters": {"seconds": 1},
    }
    artifact_forbidden["payload"] = {"pick_selection": "something"}
    errors_forbidden = validate_agent_artifact_for_work_order(artifact_forbidden, wo.to_jsonable())
    assert any("contains forbidden key" in e for e in errors_forbidden)
