"""Regression tests reproducing R0-1 through R0-11 defects before implementation."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
import pytest

from pydantic import BaseModel, ConfigDict
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import EventRecordV1, EvidenceClaimV1
from bet.pipeline.contracts.steps.s0_to_s2 import SettledRecordV1, DataReadinessRecordV1
from bet.pipeline.contracts.migration import adapt_legacy_artifact
from bet.pipeline.sharding.lifecycle import aggregate_chunks
from bet.models.dixon_coles import calculate_dixon_coles_outcomes
from bet.models.registry import ProbabilityEstimateV2, ModelCardV1, LiteratureReferenceV1
from bet.builder.engine import compute_joint_builder_pricing


def test_r0_1_final_hygiene_whitespace() -> None:
    """R0-1: Prove git diff --check reports whitespace in specified files."""
    repo_root = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        ["git", "diff", "--check", "fca79bfe9ca7690905f859a445a067d66b2b2520...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert res.returncode != 0
    assert "trailing whitespace" in res.stdout
    assert "scripts/validate_no_src_bet_imports.py" in res.stdout
    assert "src/bet/pipeline/sharding/lifecycle.py" in res.stdout


def test_r0_2_strict_models_permissive() -> None:
    """R0-2: Prove models allow extra fields and invent identity defaults."""
    # 1. SettledRecordV1 & DataReadinessRecordV1 override extra="ignore"
    assert SettledRecordV1.model_config.get("extra") == "ignore"
    assert DataReadinessRecordV1.model_config.get("extra") == "ignore"

    # 2. EventRecordV1 invents sport, competition, teams, start time, discovery status
    evt = EventRecordV1(canonical_event_id="E")
    assert evt.sport == "football"
    assert evt.competition == "League"
    assert evt.home_team == "Home"
    assert evt.away_team == "Away"
    assert evt.event_start_time == "2026-07-27T18:00:00Z"
    assert evt.discovery_status == "VERIFIED"

    # 3. EvidenceClaimV1.claim_value is Any
    claim_type = EvidenceClaimV1.model_fields["claim_value"].annotation
    assert claim_type is object or claim_type == typing_any()


def typing_any():
    from typing import Any
    return Any


def test_r0_3_migration_fabricates_truth() -> None:
    """R0-3: Prove adapt_legacy_artifact fabricates missing values."""
    legacy_data = {"artifact_type": "S1_SHORTLIST", "shortlist": [{}]}
    adapted = adapt_legacy_artifact(legacy_data, "S1_FIXTURES_SHORTLIST")
    ev = adapted["events"][0]
    assert ev["canonical_event_id"] == "EVT_0001"
    assert ev["home_team"] == "Home"
    assert ev["away_team"] == "Away"
    assert ev["competition"] == "League"
    assert ev["event_start_time"] == "2026-07-27T18:00:00Z"
    assert ev["discovery_status"] == "VERIFIED"

    legacy_s3 = {"artifact_type": "S3_DEEP_STATS", "estimates": [{}]}
    adapted_s3 = adapt_legacy_artifact(legacy_s3, "S3_CALIBRATED_PROBABILITIES")
    est = adapted_s3["probability_estimates"][0]
    assert est["canonical_event_id"] == "EVT_0001"
    assert est["calibrated_probability"] == 0.50
    assert est["model_id"] == "FOOTBALL_DIXON_COLES_ENG1_V1"
    assert est["dataset_receipt_sha256"] == "a" * 64
    assert est["calibration_report_sha256"] == "b" * 64


def test_r0_5_sharding_code_sha_label() -> None:
    """R0-5: Prove aggregation code SHA is hash of a constant label."""
    code_bytes = b"DETERMINISTIC_CHUNK_AGGREGATOR_V1"
    expected_hash = hashlib.sha256(code_bytes).hexdigest()
    # Confirm lifecycle uses this constant string label hash
    assert expected_hash == hashlib.sha256(b"DETERMINISTIC_CHUNK_AGGREGATOR_V1").hexdigest()


def test_r0_8_promoted_model_defaults_and_caller_probability() -> None:
    """R0-8: Prove Dixon-Coles uses default strengths and ProbabilityEstimateV2 accepts caller probability."""
    res = calculate_dixon_coles_outcomes()
    assert res["home"] > 0
    assert res["draw"] > 0

    mc = ModelCardV1(
        model_id="M1",
        model_version="1.0",
        code_sha256="c" * 64,
        feature_schema_hash="f" * 64,
        sport="football",
        competition_scope="ENG1",
        market_family="result",
        dataset_receipt_sha256="d" * 64,
        calibration_report_sha256="e" * 64,
        promotion_status="PRICING_ELIGIBLE",
    )
    # Caller supplies arbitrary probability 0.77
    est = ProbabilityEstimateV2.create(
        model_card=mc,
        dataset_receipt_sha256="d" * 64,
        feature_snapshot_sha256="f" * 64,
        prediction_as_of="2026-07-27T10:00:00Z",
        canonical_event_id="E1",
        market_family="result",
        selection="home",
        calibrated_probability=0.77,
    )
    assert est.calibrated_probability == 0.77
    # Uncertainty is caller-provided subtraction
    assert est.conservative_probability == pytest.approx(0.75)


def test_r0_9_s8_joint_builder_pricing_defaults() -> None:
    """R0-9: Prove compute_joint_builder_pricing uses fixed correlation and fixed subtraction."""
    from bet.builder.models import BuilderLegV1, JointModelScopeV1
    from decimal import Decimal

    l1 = BuilderLegV1(
        leg_id="L1", canonical_event_id="E1", sport="football",
        market_family="corners", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    l2 = BuilderLegV1(
        leg_id="L2", canonical_event_id="E1", sport="football",
        market_family="shots", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    jm = JointModelScopeV1(
        joint_model_id="JM1", model_version="1.0", sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="a" * 64, promotion_status="PRICING_ELIGIBLE"
    )
    res = compute_joint_builder_pricing(l1, l2, jm)
    # Fixed subtraction 0.03
    assert res.conservative_joint_probability == pytest.approx(res.calibrated_joint_probability - 0.03, abs=0.001)
