"""C4 acceptance tests for model governance, literature, temporal validation, and pricing."""
from __future__ import annotations

import pytest
from decimal import Decimal
from bet.models.contracts import TemporalSplitPlanV1
from bet.models.registry import (
    ModelCardV1,
    ProbabilityEstimateV2,
    GLOBAL_MODEL_REGISTRY,
)
from bet.models.dixon_coles import calculate_dixon_coles_outcomes


def test_dixon_coles_registered_as_analysis_only():
    """Verify default Dixon-Coles model is ANALYSIS_ONLY until verified fitted artifacts exist."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "ANALYSIS_ONLY"
    assert not card.is_pricing_eligible()


def test_unpromoted_model_cannot_produce_pricing_estimate():
    """Verify an EXPERIMENTAL, ANALYSIS_ONLY or SHADOW_ONLY model card rejects pricing probability estimate creation."""
    exp_card = ModelCardV1(
        model_id="EXPERIMENTAL_MODEL_001",
        model_version="0.1.0",
        code_sha256="0" * 64,
        feature_schema_hash="1" * 64,
        sport="football",
        competition_scope="eng.1",
        market_family="corners",
        dataset_receipt_sha256="2" * 64,
        calibration_report_sha256="3" * 64,
        promotion_status="EXPERIMENTAL",
    )

    with pytest.raises(ValueError, match="is not PRICING_ELIGIBLE"):
        ProbabilityEstimateV2.create(
            model_card=exp_card,
            dataset_receipt_sha256="2" * 64,
            feature_snapshot_sha256="1" * 64,
            prediction_as_of="2026-07-27T10:00:00Z",
            canonical_event_id="EVT_001",
            market_family="corners",
            selection="over_9.5",
            calibrated_probability=0.55,
        )


def test_promoted_model_minimum_odds_decimal_calculation(tmp_path):
    """Verify a truly promoted model card calculates fair/minimum odds with Decimal precision when backed by test artifacts."""
    import hashlib
    dataset_file = tmp_path / "dataset_receipt.json"
    dataset_file.write_text('{"dataset_id": "eng1_train"}', encoding="utf-8")
    dataset_sha = hashlib.sha256(dataset_file.read_bytes()).hexdigest()

    calibration_file = tmp_path / "calibration_report.json"
    calibration_file.write_text('{"brier_score": 0.1}', encoding="utf-8")
    calibration_sha = hashlib.sha256(calibration_file.read_bytes()).hexdigest()

    code_sha = hashlib.sha256(b"code").hexdigest()
    schema_sha = hashlib.sha256(b"schema").hexdigest()

    promoted_card = ModelCardV1(
        model_id="PROMOTED_MODEL_001",
        model_version="1.0.0",
        code_sha256=code_sha,
        feature_schema_hash=schema_sha,
        sport="football",
        competition_scope="eng.1",
        market_family="result",
        dataset_receipt_sha256=dataset_sha,
        calibration_report_sha256=calibration_sha,
        promotion_status="PRICING_ELIGIBLE",
        model_card_sha256="4" * 64,
    )

    estimate = ProbabilityEstimateV2.create(
        model_card=promoted_card,
        dataset_receipt_sha256=dataset_sha,
        feature_snapshot_sha256=schema_sha,
        prediction_as_of="2026-07-27T10:00:00Z",
        canonical_event_id="EVT_ARS_CHE_001",
        market_family="result",
        selection="home",
        calibrated_probability=0.50,
        uncertainty_margin=0.02,  # conservative_p = 0.48
        required_roi=0.05,
        search_dirs=[tmp_path],
    )

    assert estimate.calibrated_probability == 0.50
    assert estimate.conservative_probability == 0.48
    assert estimate.fair_decimal_odds == Decimal("2.0000")
    assert estimate.minimum_acceptable_operator_odds == Decimal("2.1875")


def test_chronological_temporal_split_order():
    """Verify temporal split plan asserts strictly ordered train/calibration/test windows."""
    plan = TemporalSplitPlanV1(
        plan_id="SPLIT_ENG1_2026",
        train_start="2022-08-01",
        train_end="2025-05-31",
        calibration_start="2025-06-01",
        calibration_end="2025-12-31",
        test_start="2026-01-01",
        test_end="2026-06-30",
        gap_days=0,
    )
    assert plan.chronological_order_verified


def test_dixon_coles_goal_grid_probabilities():
    """Verify Dixon-Coles goal grid returns valid probabilities summing to 1.0."""
    outcomes = calculate_dixon_coles_outcomes(
        home_attack=1.2,
        home_defence=0.9,
        away_attack=1.0,
        away_defence=1.1,
        home_advantage=1.25,
    )
    p_sum = outcomes["home"] + outcomes["draw"] + outcomes["away"]
    assert abs(p_sum - 1.0) < 1e-6
    assert 0.0 < outcomes["home"] < 1.0
    assert 0.0 < outcomes["draw"] < 1.0
    assert 0.0 < outcomes["away"] < 1.0
