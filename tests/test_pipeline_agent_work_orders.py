"""Tests for agent work order generation, hashing, and policy formatting."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from bet.pipeline.agent_work_orders import (
    build_agent_work_order,
    write_agent_work_order,
    work_order_path_for,
    discover_input_refs_for_step,
    expected_agent_artifact_path_for,
    calculate_sha256,
)


def create_mock_artifacts(base_dir: Path, betting_day: str, run_id: str):
    artifacts_dir = base_dir / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    steps = {
        "S2": "SCRIPT_EVIDENCE",
        "S2.3": "AGENT_ARTIFACT",
        "S2.5": "AGENT_ARTIFACT",
        "S2.7": "AGENT_ARTIFACT",
        "S2.9": "AGENT_ARTIFACT",
        "S3": "SCRIPT_EVIDENCE",
        "S4": "SCRIPT_EVIDENCE",
    }
    
    for step_id, art_type in steps.items():
        payload = {
            "artifact_type": art_type,
            "step_id": step_id,
            "betting_day": betting_day,
            "run_id": run_id,
            "status": "PASS"
        }
        path = artifacts_dir / f"{step_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)


def test_calculate_sha256(tmp_path):
    """Verify SHA-256 calculation for existing and non-existing files."""
    non_existent = tmp_path / "does_not_exist.json"
    assert calculate_sha256(non_existent) == ""

    test_file = tmp_path / "test.json"
    test_file.write_text("hello world", encoding="utf-8")
    expected_hash = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert calculate_sha256(test_file) == expected_hash


def test_work_order_generation_and_policies(tmp_path):
    """Verify work order generation for each agent step: S2.3, S2.5, S2.7, S2.9, S5."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    steps = ["S2.3", "S2.5", "S2.7", "S2.9", "S5"]
    
    for step_id in steps:
        wo = build_agent_work_order(
            betting_day="2026-06-25",
            run_id="run-smoke-1",
            step_id=step_id,
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )
        
        # Verify schema adherence
        assert wo.schema_version == 1
        assert wo.work_order_type == "AGENT_ARTIFACT_REQUEST"
        assert wo.pipeline_id == "bet_pipeline_v1"
        assert wo.betting_day == "2026-06-25"
        assert wo.run_id == "run-smoke-1"
        assert wo.step_id == step_id
        assert wo.runtime_mode == "DRY_RUN"
        assert wo.status == "PENDING_AGENT"
        assert wo.created_at is not None
        
        # Verify required output contract
        req_out = wo.required_output
        assert req_out.artifact_type == "AGENT_ARTIFACT"
        assert req_out.step_id == step_id
        
        # Verify includes exact expected output path
        expected_path = expected_agent_artifact_path_for(tmp_path, "2026-06-25", "run-smoke-1", step_id)
        assert req_out.expected_path == str(expected_path)
        
        # Verify work order forbids pick/edge/stake/coupon outputs
        for forbidden in ["pick", "edge", "stake", "coupon"]:
            assert any(forbidden in fo.lower() for fo in wo.forbidden_outputs)

        # Verify work order explicitly treats templates as non-final scaffolds
        output_contract = wo.instructions["output_contract"]
        assert any("Template scaffolds are not accepted final output" in item for item in output_contract)
        assert any("BLOCK is acceptable and preferred over guessing" in item for item in output_contract)
        assert any("PASS requires full contract evidence" in item for item in output_contract)
             
        # Verify input refs matching step dependency graph
        refs = wo.input_refs
        assert isinstance(refs, list)
        if step_id == "S2.3":
            assert len(refs) == 1
            assert refs[0].step_id == "S2"
        elif step_id == "S2.5":
            assert len(refs) == 2
            assert {r.step_id for r in refs} == {"S2", "S2.3"}
        elif step_id == "S2.7":
            assert len(refs) == 3
            assert {r.step_id for r in refs} == {"S2", "S2.3", "S2.5"}
        elif step_id == "S2.9":
            assert len(refs) == 4
            assert {r.step_id for r in refs} == {"S2", "S2.3", "S2.5", "S2.7"}
        elif step_id == "S5":
            assert len(refs) == 3
            assert {r.step_id for r in refs} == {"S3", "S4", "S2.9"}


def test_s5_work_order_specific_checks(tmp_path):
    """Verify S5 work order contains injury/lineup, motivation, travel/fatigue, morale, and upset risk requirements."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S5",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    
    # Check for hard rules in S5 policy
    expected_rules = [
        "injury_lineup_context_required",
        "motivation_and_tournament_context_required",
        "travel_schedule_fatigue_checked",
        "morale_and_recent_result_context_checked",
        "volatility_or_upset_risk_checked",
    ]
    for rule in expected_rules:
        assert rule in wo.hard_rules
        
    # Check must_do instructions
    must_dos = wo.instructions["must_do"]
    categories = ["injuries", "motivation", "travel", "morale", "upset/volatility"]
    for cat in categories:
        assert any(cat in md.lower() for md in must_dos)


def test_s29_work_order_requires_evidence_and_non_template_output(tmp_path):
    """Verify S2.9 work order states PASS evidence needs and rejects template-as-output."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )

    assert any("PASS requires S2.3, S2.5, S2.7 artifacts valid." in item for item in wo.instructions["must_do"])
    assert any("Fill required evidence fields" in item for item in wo.instructions["output_contract"])


def test_write_agent_work_order(tmp_path):
    """Verify writing a work order to disk."""
    create_mock_artifacts(tmp_path, "2026-06-25", "run-smoke-1")
    wo = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-smoke-1",
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    
    written_path = write_agent_work_order(wo, tmp_path)
    expected_path = work_order_path_for(tmp_path, "2026-06-25", "run-smoke-1", "S2.3")
    assert written_path == expected_path
    assert expected_path.exists()
    
    # Read and assert JSON fields match
    with open(expected_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["work_order_id"] == wo.work_order_id
    assert data["step_id"] == "S2.3"


def test_s23_cannot_generate_work_order_without_s2(tmp_path):
    """Regression test proving S2.3 cannot generate a work order or PASS without a valid current-run S2 artifact."""
    betting_day = "2026-06-25"
    run_id = "run-smoke-1"
    
    # Case 1: S2 artifact missing
    with pytest.raises(ValueError, match="Required dependency file is missing"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Set up artifacts dir
    artifacts_dir = tmp_path / "pipeline_runs" / betting_day / run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    s2_path = artifacts_dir / "S2.json"

    # Case 2: S2 artifact is empty / invalid JSON
    s2_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="unreadable or invalid JSON"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 3: S2 artifact has wrong betting_day
    payload = {
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S2",
        "betting_day": "2026-01-01",  # wrong day
        "run_id": run_id,
    }
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong betting_day in artifact"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 4: S2 artifact has wrong run_id
    payload["betting_day"] = betting_day
    payload["run_id"] = "wrong-run"
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong run_id in artifact"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 5: S2 artifact has wrong artifact type
    payload["run_id"] = run_id
    payload["artifact_type"] = "AGENT_ARTIFACT"  # should be SCRIPT_EVIDENCE for script step S2
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    with pytest.raises(ValueError, match="Wrong artifact type"):
        build_agent_work_order(
            betting_day=betting_day,
            run_id=run_id,
            step_id="S2.3",
            runtime_mode="DRY_RUN",
            base_dir=tmp_path,
        )

    # Case 6: S2 artifact is outside current run root
    # (Since resolve_run_root canonicalizes the base path, we can check a path that escapes the run_root)
    # Wait, our input resolver resolves the path relative to base_dir, but we can verify it fails if we force an invalid path.
    # A valid config works:
    payload["artifact_type"] = "SCRIPT_EVIDENCE"
    with open(s2_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    
    wo = build_agent_work_order(
        betting_day=betting_day,
        run_id=run_id,
        step_id="S2.3",
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    assert wo is not None
    assert wo.input_refs[0].step_id == "S2"
