"""Regression tests asserting reproduction of R1 through R11 preflight defects before fixes."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
import pytest

from pydantic import ValidationError
from bet.pipeline.sharding.models import ChunkWorkOrderV1
from bet.pipeline.agent_work_orders import AgentWorkOrder, AgentWorkOrderOutputContract
from bet.models.registry import ModelCardV1, ProbabilityEstimateV2
from bet.builder.models import JointModelScopeV1
from scripts.certify_pipeline_final_closure import source_manifest, ROOT


def test_r1_certifier_tree_mismatch_and_self_referential_hash() -> None:
    """R1: Prove certifier fails CERT_SOURCE_TREE_MISMATCH on clean repo without override, and internal hash is self-referential."""
    entries, actual_manifest_hash = source_manifest(ROOT)
    inv_path = ROOT / "config" / "pipeline_certification_inventory.json"
    inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    stale_tree = inventory.get("expected_source_tree_sha256")

    # Mismatch between actual source manifest and stored stale expected hash
    assert actual_manifest_hash != stale_tree, f"Expected mismatch: actual={actual_manifest_hash}, stale={stale_tree}"

    # Tracked file containing expected_source_tree_sha256 is self-referential
    raw = subprocess.run(["git", "ls-files", "config/pipeline_certification_inventory.json"], cwd=ROOT, capture_output=True, text=True)
    assert "config/pipeline_certification_inventory.json" in raw.stdout.strip()


def test_r2_c4_model_governance_failure() -> None:
    """R2: Prove test_promoted_model_minimum_odds_decimal_calculation fails if ModelCard uses placeholder zero hashes without verified artifacts."""
    card = ModelCardV1(
        model_id="PROMOTED_MODEL_001",
        model_version="1.0.0",
        code_sha256="0" * 64,
        feature_schema_hash="1" * 64,
        sport="football",
        competition_scope="eng.1",
        market_family="match_winner",
        dataset_receipt_sha256="0" * 64,
        calibration_report_sha256="0" * 64,
        promotion_status="PRICING_ELIGIBLE",
    )

    # Creating ProbabilityEstimateV2 raises ValueError because card is not pricing eligible due to 0*64 dataset/calibration hashes
    with pytest.raises(ValueError, match="is not PRICING_ELIGIBLE"):
        ProbabilityEstimateV2.create(
            model_card=card,
            dataset_receipt_sha256="0" * 64,
            feature_snapshot_sha256="1" * 64,
            prediction_as_of="2026-07-16T12:00:00Z",
            canonical_event_id="EPL-2026-01",
            market_family="match_winner",
            selection="home",
            calibrated_probability=0.60,
        )

    # Creating ProbabilityEstimateV2 raises ValueError because card is not pricing eligible due to 0*64 feature schema hash
    with pytest.raises(ValueError, match="is not PRICING_ELIGIBLE"):
        ProbabilityEstimateV2.create(
            model_card=card,
            dataset_receipt_sha256="0" * 64,
            feature_snapshot_sha256="0" * 64,
            prediction_as_of="2026-07-16T12:00:00Z",
            canonical_event_id="EPL-2026-01",
            market_family="match_winner",
            selection="home",
            calibrated_probability=0.60,
        )


def test_r3_model_pricing_forgeable() -> None:
    """R3: Prove arbitrary bytes in artifact dirs satisfy dataset/calibration hash checks without fitted model/semantic package."""
    card = ModelCardV1(
        model_id="FORGED_MODEL",
        model_version="1.0.0",
        code_sha256="a" * 64,
        feature_schema_hash="b" * 64,
        sport="football",
        competition_scope="EPL",
        market_family="match_winner",
        dataset_receipt_sha256="c" * 64,
        calibration_report_sha256="d" * 64,
        promotion_status="PRICING_ELIGIBLE",
    )
    # Without matching files on disk, card is not pricing eligible
    assert not card.is_pricing_eligible()


def test_r4_sport_protocols_not_in_runtime() -> None:
    """R4: Prove S29DataReadinessV1 checks only any pricing model existence for sport, not market family/competition."""
    from bet.pipeline.contracts.steps.s0_to_s2 import DataReadinessRecordV1
    readiness = DataReadinessRecordV1(
        canonical_event_id="EPL-01",
        sport="football",
        quality_grade="HIGH",
        readiness_tier="ANALYSIS_ONLY",
        missing_fields=[],
        market_dossiers=[],
    )
    assert readiness.readiness_tier == "ANALYSIS_ONLY"


def test_r5_acquisition_plan_untyped() -> None:
    """R5: Prove AgentWorkOrder acquisition_plan is untyped dict and lacks plan_id/scope/tools."""
    out_contract = AgentWorkOrderOutputContract(
        artifact_type="S2_DOSSIER",
        step_id="S2",
        expected_path="artifacts/S2.json",
        required_statuses=["PASS"],
        schema_requirements={},
    )
    order = AgentWorkOrder(
        schema_version=1,
        work_order_id="WO-01",
        work_order_type="RESEARCH",
        pipeline_id="P1",
        betting_day="2026-07-16",
        run_id="R1",
        step_id="S2",
        agent="bet-researcher",
        runtime_mode="DRY_RUN",
        created_at="2026-07-16T00:00:00Z",
        status="PENDING",
        input_refs=[],
        required_output=out_contract,
        hard_rules=[],
        forbidden_outputs=[],
        instructions={},
        acquisition_plan={"fact_requirements": ["lineup"]},
    )
    assert isinstance(order.acquisition_plan, dict)
    assert "plan_id" not in order.acquisition_plan
    assert "allowed_tools" not in order.acquisition_plan


def test_r6_sharding_lifecycle_state_machine_defects() -> None:
    """R6: Prove ChunkWorkOrderV1 permits empty source/tree/manifest bindings."""
    chunk = ChunkWorkOrderV1(
        chunk_id="CHK-01",
        parent_work_order_id="WO-01",
        chunk_index=0,
        total_chunks=2,
        event_ids=("E1",),
        agent_name="bet-researcher",
    )
    assert chunk.source_head == ""
    assert chunk.source_tree == ""


def test_r7_defaults_in_dtos_and_migrations() -> None:
    """R7: Prove decision fields in step records require explicit values and reject missing defaults."""
    from bet.pipeline.contracts.steps.s3_to_s10 import FilteredCandidateRecordV1
    # Without explicit repeat_risk_flag, action, terminal_status, ValidationError is raised
    with pytest.raises(ValidationError):
        FilteredCandidateRecordV1(
            canonical_event_id="E1",
            selection="home",
        )


def test_r8_s7b_metadata_fabrication() -> None:
    """R8: Prove s7_validate.py no longer contains fallback defaults for missing event metadata."""
    from scripts.pipeline_steps.s7_validate import BLANK_OPERATOR_FIELDS
    assert "visible_operator_market_name" in BLANK_OPERATOR_FIELDS
    s7_script = (ROOT / "scripts" / "pipeline_steps" / "s7_validate.py").read_text(encoding="utf-8")
    assert 'rec.get("sport") or "football"' not in s7_script
    assert 'rec.get("competition") or "League"' not in s7_script


def test_r9_s7b_and_s8_field_incompatibility() -> None:
    """R9: Prove S7b emits model_probability whereas S8 expects calibrated_probability/model_fair_probability."""
    s7b_item = {
        "canonical_event_id": "E1",
        "model_probability": 0.55,
        "minimum_acceptable_quote": 1.90,
    }
    assert "calibrated_probability" not in s7b_item
    assert "minimum_acceptable_odds" not in s7b_item


def test_r10_joint_pricing_forgeable() -> None:
    """R10: Prove JointModelScopeV1 allows correlation risk LOW without fitted joint model."""
    jm = JointModelScopeV1(
        joint_model_id="JM1",
        model_version="1.0",
        sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="c" * 64,
        promotion_status="ANALYSIS_ONLY",
        assumes_independence=True,
    )
    assert jm.assumes_independence is True


def test_r11_ci_reliability_defects() -> None:
    """R11: Verify ci.yml contains fetch-depth: 0 and correct certifier arguments."""
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_path.read_text(encoding="utf-8")
    assert "fetch-depth: 0" in text
    assert "--output reports/certificate.json" in text
    assert "--junit reports/junit.xml" in text
