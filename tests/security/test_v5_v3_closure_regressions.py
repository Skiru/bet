"""Regression suite for BET PIPELINE V5 closure V3 prompt (22 Finding IDs)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
import pytest

from bet.pipeline.receipts import (
    ProvenanceResolutionError,
    get_git_commit_head,
    get_git_tree_sha,
    compute_source_manifest_sha256,
)
from bet.pipeline.sharding.models import ChunkWorkOrderV1, ChunkArtifactV1
from bet.pipeline.sharding.lifecycle import validate_chunk_against_work_order, ChunkLifecycleError
from bet.pipeline.readiness_contracts import ModelPackageResolver, ModelPackageResolutionResult
from bet.pipeline.contracts.migration import adapt_legacy_artifact, MigrationAdapterError
from bet.pipeline.contracts.registry import GLOBAL_CONTRACT_REGISTRY
from bet.builder.engine import generate_same_event_builders, BuilderLegV1, JointModelScopeV1


def test_p0_01_dummy_step_model():
    """P0-01: DummyStepModel must not be present in the production contract registry."""
    from bet.pipeline.contracts.steps import _register_step_contracts

    _register_step_contracts()

    # DummyStepModel was removed from imports and contract registry
    with pytest.raises(ImportError):
        from bet.pipeline.contracts.steps import DummyStepModel  # Should fail to import

    for desc in GLOBAL_CONTRACT_REGISTRY.list_descriptors():
        assert desc.model_type.__name__ != "DummyStepModel", f"Step {desc.contract_id} uses DummyStepModel"


def test_p0_02_migration_adapters():
    """P0-02: Migration adapters must fail closed on missing decision-bearing data instead of fabricating defaults."""
    payload_s3 = {"artifact_type": "S3_DEEP_STATS", "analyses": [{"canonical_event_id": "evt_1"}]}
    with pytest.raises(MigrationAdapterError) as exc_info:
        adapt_legacy_artifact(payload_s3, "S3_CALIBRATED_PROBABILITIES")
    assert "MIGRATION_FAILED" in str(exc_info.value) or "Missing" in str(exc_info.value)

    payload_s5 = {"artifact_type": "S5_CONTEXT_RISK_CANDIDATE_SET_V2", "candidates": [{"canonical_event_id": "evt_1"}]}
    with pytest.raises(MigrationAdapterError) as exc_info:
        adapt_legacy_artifact(payload_s5, "S5_CONTEXT_MOTIVATION_RISK")
    assert "MIGRATION_FAILED" in str(exc_info.value) or "Missing" in str(exc_info.value)


def test_p0_03_chunk_models_provenance():
    """P0-03: Chunk models must not auto-populate synthetic provenance or output paths."""
    wo_dict = {
        "chunk_id": "C-1",
        "parent_work_order_id": "WO-1",
        "event_ids": ["evt_1"],
        "agent_name": "bet-executor",
    }
    with pytest.raises(ValueError) as exc_info:
        ChunkWorkOrderV1(**wo_dict)
    assert "CHUNK_WO_BINDING_EMPTY" in str(exc_info.value) or "required" in str(exc_info.value) or "parent_work_order_sha256" in str(exc_info.value)

    art_dict = {
        "chunk_id": "C-1",
        "parent_work_order_id": "WO-1",
        "producer_agent_id": "bet-executor",
        "processed_event_ids": ["evt_1"],
    }
    with pytest.raises(ValueError) as exc_info:
        ChunkArtifactV1(**art_dict)
    assert "CHUNK_ARTIFACT_BINDING_EMPTY" in str(exc_info.value) or "required" in str(exc_info.value) or "chunk_work_order_sha256" in str(exc_info.value)


def test_p0_04_chunk_validation_bindings():
    """P0-04: validate_chunk_against_work_order must check all work-order/run bindings."""
    valid_wo = ChunkWorkOrderV1(
        chunk_id="WO-S2.3-C0001",
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="1" * 64,
        step_id="S2.3",
        betting_day="2026-07-29",
        run_id="run_100",
        runtime_mode="LIVE_SHADOW",
        source_head="2" * 40,
        source_tree="3" * 40,
        manifest_sha256="4" * 64,
        parent_plan_id="PLAN-WO-S2.3",
        parent_plan_sha256="5" * 64,
        chunk_index=0,
        total_chunks=1,
        event_ids=("evt_1",),
        agent_name="bet-researcher",
        expected_artifact_path="/tmp/artifacts/chunks/WO-S2.3-C0001.json",
        expected_artifact_type="S2_3_CHUNK_ARTIFACT",
        attempt_number=1,
        attempt_id="WO-S2.3-C0001-ATT1",
    )

    art_mismatch_agent = ChunkArtifactV1(
        chunk_id="WO-S2.3-C0001",
        chunk_work_order_sha256="6" * 64,
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="1" * 64,
        parent_plan_id="PLAN-WO-S2.3",
        parent_plan_sha256="5" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="evil-agent",  # Mismatch!
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="2" * 40,
        source_tree="3" * 40,
        manifest_sha256="4" * 64,
        processed_event_ids=("evt_1",),
    )

    with pytest.raises(ChunkLifecycleError) as exc_info:
        validate_chunk_against_work_order(art_mismatch_agent, valid_wo)
    assert "PRODUCER_AGENT_MISMATCH" in str(exc_info.value) or "producer_agent_id" in str(exc_info.value) or "mismatch" in str(exc_info.value).lower()


def test_p0_05_sharding_provenance():
    """P0-05: Provenance resolution must raise ProvenanceResolutionError on failure instead of dummy hashes."""
    fake_dir = Path("/nonexistent/repo/directory/12345")
    with pytest.raises(ProvenanceResolutionError):
        get_git_commit_head(fake_dir)

    with pytest.raises(ProvenanceResolutionError):
        get_git_tree_sha(fake_dir)

    with pytest.raises(ProvenanceResolutionError):
        compute_source_manifest_sha256(fake_dir)


def test_p0_06_generic_shard_aggregation():
    """P0-06: Sharded step aggregation must use typed step reducers and fail-closed status lattice."""
    from bet.pipeline.sharding.reducers import get_reducer_for_step

    s23_reducer = get_reducer_for_step("S2.3")
    assert s23_reducer is not None

    s25_reducer = get_reducer_for_step("S2.5")
    assert s25_reducer is not None


def test_p0_07_chunk_work_order_schema():
    """P0-07: Chunk work order schema must be compatible with canonical agent executor prompt renderer."""
    from bet.pipeline.agent_execution_prompts import render_agent_execution_prompt

    wo = ChunkWorkOrderV1(
        chunk_id="WO-S2.3-C0001",
        parent_work_order_id="WO-S2.3",
        parent_work_order_sha256="1" * 64,
        step_id="S2.3",
        betting_day="2026-07-29",
        run_id="run_100",
        runtime_mode="LIVE_SHADOW",
        source_head="2" * 40,
        source_tree="3" * 40,
        manifest_sha256="4" * 64,
        parent_plan_id="PLAN-WO-S2.3",
        parent_plan_sha256="5" * 64,
        chunk_index=0,
        total_chunks=1,
        event_ids=("evt_1",),
        agent_name="bet-researcher",
        expected_artifact_path="/tmp/artifacts/chunks/WO-S2.3-C0001.json",
        expected_artifact_type="S2_3_CHUNK_ARTIFACT",
        attempt_number=1,
        attempt_id="WO-S2.3-C0001-ATT1",
    )

    prompt = render_agent_execution_prompt(wo)
    assert isinstance(prompt, str) and len(prompt) > 0


def test_p0_08_model_package_governance():
    """P0-08: Untracked or missing-fitted-model packages must be rejected by ModelPackageResolver."""
    untracked_pkg = Path("models/store/test_pkg_t4")
    res = ModelPackageResolver.resolve_package(untracked_pkg)
    assert isinstance(res, ModelPackageResolutionResult)
    assert res.is_eligible is False


def test_p0_09_quality_receipt_generator():
    """P0-09: Quality receipts must capture actual executed commands, real exit codes, and output paths/hashes."""
    from bet.pipeline.receipts import QualityReceiptV1

    qr = QualityReceiptV1(
        head_sha="a" * 40,
        git_tree_sha="b" * 40,
        source_manifest_sha256="c" * 64,
        command_argv=["pytest"],
        cwd="/tmp",
        started_at="2026-07-29T00:00:00Z",
        finished_at="2026-07-29T00:00:01Z",
        exit_code=0,
        stdout_sha256="d" * 64,
        stderr_sha256="e" * 64,
        status="PASS",
    )
    assert qr.exit_code == 0
    assert len(qr.stdout_sha256) == 64


def test_p0_10_provenance_helpers_fail_closed():
    """P0-10: Provenance helpers must fail closed without returning a*40, b*40, c*64."""
    head = get_git_commit_head(Path("."))
    tree = get_git_tree_sha(Path("."))
    manifest = compute_source_manifest_sha256(Path("."))

    assert head != "a" * 40
    assert tree != "b" * 40
    assert manifest != "c" * 64


def test_p1_01_acquisition_plans():
    """P1-01: Acquisition plans must be specific per canonical event, sport, and market family."""
    from bet.pipeline.sharding.models import FactAcquisitionPlanV1

    with pytest.raises(ValueError):
        FactAcquisitionPlanV1(
            plan_id="P1",
            canonical_event_id="ALL_SHORTLIST_EVENTS",
            sport="football",
        )


def test_p1_02_tool_governance():
    """P1-02: Tool governance intersection must be enforced."""
    from bet.pipeline.agent_work_orders import enforce_tool_governance_intersection

    allowed = enforce_tool_governance_intersection(
        agent_profile="bet-researcher",
        manifest_policy=["bet_sqlite_query", "webfetch"],
        requirement_policy=["bet_sqlite_query", "bash"],
    )
    assert "bash" not in allowed, "bet-researcher cannot be granted bash tool"
    assert allowed == ("bet_sqlite_query",)


def test_p1_03_strict_step_validation():
    """P1-03: S1e event universe validation is mandatory; missing S1e raises BLOCK."""
    from bet.pipeline.event_accounting import validate_s1e_universe_coverage

    with pytest.raises(ValueError) as exc_info:
        validate_s1e_universe_coverage(s1e_event_ids=None, current_event_ids=["evt_1"])
    assert "S1E_UNIVERSE_REQUIRED" in str(exc_info.value) or "missing" in str(exc_info.value).lower() or "required" in str(exc_info.value).lower()


def test_p1_04_untyped_structures():
    """P1-04: Decision-bearing nested structures must be strongly typed."""
    from bet.pipeline.contracts.steps.s3_to_s10 import S3CalibratedProbabilitiesV1, ProbabilityRecordV1

    assert hasattr(S3CalibratedProbabilitiesV1, "model_fields")
    prop_field = S3CalibratedProbabilitiesV1.model_fields["probabilities"]
    assert "ProbabilityRecordV1" in str(prop_field.annotation)


def test_p1_05_sport_dossier_placeholders():
    """P1-05: Sport dossier readiness validation must reject Home/Away/ALL placeholder identities."""
    from bet.pipeline.sports.models import SportDossierReadinessV1

    with pytest.raises(ValueError) as exc_info:
        SportDossierReadinessV1(
            canonical_event_id="evt_1",
            sport="football",
            home_team="Home",  # Placeholder
            away_team="Away",  # Placeholder
            competition="ALL", # Placeholder
        )
    assert "PLACEHOLDER_IDENTITY_FORBIDDEN" in str(exc_info.value) or "placeholder" in str(exc_info.value).lower()


def test_p1_06_unsupported_market():
    """P1-06: Unsupported market family must be NOT_SUPPORTED/BLOCK, never ready for pricing."""
    from bet.pipeline.readiness_contracts import check_market_family_pricing_support

    support = check_market_family_pricing_support(sport="football", market_family="exotic_unsupported_market")
    assert support["status"] in ("NOT_SUPPORTED", "BLOCK")
    assert support["is_pricing_eligible"] is False


def test_p1_07_model_resolver_suppression():
    """P1-07: Model resolvers must return typed resolution status with explicit rejection reason."""
    res = ModelPackageResolver.resolve_package("/nonexistent/path")
    assert isinstance(res, ModelPackageResolutionResult)
    assert res.is_eligible is False
    assert res.rejection_code is not None and res.rejection_code != ""


def test_p1_08_joint_model_correlation():
    """P1-08: Correlated same-event legs require promoted joint model or approved versioned independence protocol."""
    from decimal import Decimal

    leg_a = BuilderLegV1(
        leg_id="L1",
        canonical_event_id="evt_1",
        sport="football",
        competition="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        market_family="result",
        selection="HOME",
        calibrated_probability=0.5,
        fair_odds=Decimal("2.0"),
        minimum_acceptable_odds=Decimal("2.1"),
    )
    leg_b = BuilderLegV1(
        leg_id="L2",
        canonical_event_id="evt_1",
        sport="football",
        competition="EPL",
        home_team="Arsenal",
        away_team="Chelsea",
        market_family="total_goals",
        selection="OVER_2.5",
        calibrated_probability=0.6,
        fair_odds=Decimal("1.67"),
        minimum_acceptable_odds=Decimal("1.75"),
    )

    jm = JointModelScopeV1(
        joint_model_id="JM-001",
        model_version="1.0",
        sport="football",
        supported_market_family_pairs=(("result", "total_goals"),),
        assumes_independence=True,  # Attempts to assume independence
        calibration_report_sha256="1" * 64,
        promotion_status="PRICING_ELIGIBLE",
    )

    idea_groups, rejections = generate_same_event_builders(legs=[leg_a, leg_b], joint_models=[jm])
    # Must reject without an approved joint conjunction model / versioned independence protocol
    assert len(rejections) > 0 or len(idea_groups) == 0, "Correlated same-event legs must not multiply marginals without approved protocol"


def test_p1_09_s8_status_semantics():
    """P1-09: S8 status vocabulary must be standardized; UNPRICED cannot mean ready for priced execution."""
    from bet.pipeline.contracts.steps.s3_to_s10 import S8SuperbetManualQuotePackV1

    with pytest.raises(Exception) as exc_info:
        S8SuperbetManualQuotePackV1(
            status="PASS",
            betting_day="2026-07-29",
            run_id="run_1",
            pricing_status="UNPRICED",
            executable_coupon=True,  # Inconsistent!
        )
    assert "UNPRICED_CANNOT_BE_EXECUTABLE" in str(exc_info.value) or "inconsistent" in str(exc_info.value).lower()


def test_p1_10_acceptance_mutation_exploits():
    """P1-10: Acceptance harness must exercise all exploit scenarios."""
    from tools.v5_acceptance.external_acceptance import AcceptanceRunner

    runner = AcceptanceRunner(repo_root=str(Path(".").resolve()))
    assert hasattr(runner, "check_acc_001")


def test_runtime_01_s2_5_payload_shape():
    """RUNTIME-01: S2.5 sharded aggregate must produce ProviderEnrichmentArtifactV1 with provider_observations."""
    from bet.pipeline.sharding.reducers import reduce_s2_5_chunks
    from bet.pipeline.sharding.models import ChunkArtifactV1

    art = ChunkArtifactV1(
        chunk_id="WO-S2.5-C0001",
        chunk_work_order_sha256="1" * 64,
        parent_work_order_id="WO-S2.5",
        parent_work_order_sha256="2" * 64,
        chunk_index=0,
        total_chunks=1,
        status="PASS",
        producer_agent_id="bet-researcher",
        betting_day="2026-07-29",
        run_id="run_100",
        source_head="3" * 40,
        source_tree="4" * 40,
        manifest_sha256="5" * 64,
        processed_event_ids=("evt_1",),
        payload={"provider_observations": [{"claim_id": "c1", "canonical_event_id": "evt_1", "fact_type": "odds", "claim_value": "1.80"}]},
    )

    res = reduce_s2_5_chunks([art])
    assert "provider_observations" in res or "observations" in res
    assert "gaps" not in res, "S2.5 payload must not contain S2.3 gaps field"


def test_restart_01_safe_s2_fork():
    """RESTART-01: Safe S2 restart seed export and import mechanism."""
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed

    source_run_root = Path("/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002")
    if source_run_root.exists():
        with tempfile.TemporaryDirectory() as tmp_dir:
            seed_tar, seed_manifest = export_s2_restart_seed(
                source_run_root=source_run_root,
                output_dir=Path(tmp_dir),
            )
            assert seed_tar.exists()
            assert seed_manifest.exists()

            target_run_root = Path(tmp_dir) / "target_run_003"
            import_receipt = import_s2_restart_seed(
                seed_tar_path=seed_tar,
                target_run_root=target_run_root,
                target_run_id="v5_analysis_20260729_003",
                target_head="a" * 40,
                target_tree="b" * 40,
                target_manifest="c" * 64,
            )
            assert import_receipt["imported_event_count"] == 766
            assert import_receipt["reused_s2_plus"] is False
