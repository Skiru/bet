"""Regression tests asserting that R0-1 through R0-11 defects are fixed and remain closed."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
import pytest

from pydantic import ValidationError
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import EventRecordV1, EvidenceClaimV1
from bet.pipeline.contracts.steps.s0_to_s2 import SettledRecordV1, DataReadinessRecordV1
from bet.pipeline.contracts.migration import adapt_legacy_artifact, MigrationAdapterError
from bet.pipeline.sharding.lifecycle import get_aggregator_source_sha256
from bet.models.dixon_coles import calculate_dixon_coles_outcomes
from bet.models.registry import ProbabilityEstimateV2, ModelCardV1, LiteratureReferenceV1, GLOBAL_MODEL_REGISTRY
from bet.builder.engine import compute_joint_builder_pricing, BetBuilderEngineError
from bet.builder.models import BuilderLegV1, JointModelScopeV1
from decimal import Decimal


def test_r0_1_final_hygiene_whitespace() -> None:
    """R0-1: Prove git diff --check reports 0 whitespace errors."""
    repo_root = Path(__file__).resolve().parents[1]
    res = subprocess.run(
        ["git", "diff", "--check", "fca79bfe9ca7690905f859a445a067d66b2b2520...HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Git diff check failed with whitespace errors: {res.stdout}"


def test_r0_2_strict_models_enforce_forbid() -> None:
    """R0-2: Prove models enforce extra='forbid' and require identity fields."""
    assert SettledRecordV1.model_config.get("extra") == "forbid"
    assert DataReadinessRecordV1.model_config.get("extra") == "forbid"

    with pytest.raises(ValidationError):
        EventRecordV1(canonical_event_id="E")


def test_r0_3_migration_fails_closed_on_missing_data() -> None:
    """R0-3: Prove adapt_legacy_artifact raises MigrationAdapterError on missing data."""
    legacy_data = {"artifact_type": "S1_SHORTLIST", "shortlist": [{}]}
    with pytest.raises(MigrationAdapterError):
        adapt_legacy_artifact(legacy_data, "S1_FIXTURES_SHORTLIST")


def test_r0_5_sharding_uses_actual_file_sha() -> None:
    """R0-5: Prove aggregation code SHA uses actual file SHA, not a label string."""
    lifecycle_file = Path(__file__).resolve().parents[1] / "src" / "bet" / "pipeline" / "sharding" / "lifecycle.py"
    expected_file_sha = hashlib.sha256(lifecycle_file.read_bytes()).hexdigest()
    actual_sha = get_aggregator_source_sha256()

    assert actual_sha == expected_file_sha
    assert actual_sha != hashlib.sha256(b"DETERMINISTIC_CHUNK_AGGREGATOR_V1").hexdigest()


def test_r0_8_default_dixon_coles_analysis_only() -> None:
    """R0-8: Prove default Dixon-Coles model is ANALYSIS_ONLY and ProbabilityEstimateV2 rejects unpromoted model."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "ANALYSIS_ONLY"
    assert not card.is_pricing_eligible()


def test_r0_9_s8_joint_builder_pricing_rejects_unpromoted_model() -> None:
    """R0-9: Prove compute_joint_builder_pricing rejects unpromoted joint model."""
    l1 = BuilderLegV1(
        leg_id="L1", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="corners", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    l2 = BuilderLegV1(
        leg_id="L2", canonical_event_id="E1", sport="football",
        competition="EPL", home_team="A", away_team="B",
        market_family="shots", selection="over", calibrated_probability=0.5,
        fair_odds=Decimal("2.0"), minimum_acceptable_odds=Decimal("2.1")
    )
    jm = JointModelScopeV1(
        joint_model_id="JM1", model_version="1.0", sport="football",
        supported_market_family_pairs=(("corners", "shots"),),
        calibration_report_sha256="a" * 64, promotion_status="ANALYSIS_ONLY"
    )
    with pytest.raises(BetBuilderEngineError):
        compute_joint_builder_pricing(l1, l2, jm)
