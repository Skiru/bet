"""C4 acceptance tests for model governance, literature, temporal validation, and pricing."""
from __future__ import annotations

import pytest
from decimal import Decimal
from src.bet.models.contracts import TemporalSplitPlanV1
from src.bet.models.registry import (
    ModelCardV1,
    ProbabilityEstimateV2,
    GLOBAL_MODEL_REGISTRY,
)
from src.bet.models.dixon_coles import calculate_dixon_coles_outcomes


def test_promoted_model_card_is_pricing_eligible():
    """Verify FOOTBALL_DIXON_COLES_ENG1_V1 is registered and PRICING_ELIGIBLE."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "PRICING_ELIGIBLE"
    assert card.is_pricing_eligible()
    assert len(card.literature_citations) >= 1
    assert "Dixon" in card.literature_citations[0].citation


def test_unpromoted_model_cannot_produce_pricing_estimate():
    """Verify an EXPERIMENTAL or SHADOW_ONLY model card rejects pricing probability estimate creation."""
    exp_card = ModelCardV1(
        model_id="EXPERIMENTAL_MODEL_001",
        model_version="0.1.0",
        code_sha256="code123",
        feature_schema_hash="feat123",
        sport="football",
        competition_scope="eng.1",
        market_family="corners",
        dataset_receipt_sha256="dataset123",
        calibration_report_sha256="calib123",
        promotion_status="EXPERIMENTAL",
    )

    with pytest.raises(ValueError, match="is not PRICING_ELIGIBLE"):
        ProbabilityEstimateV2.create(
            model_card=exp_card,
            dataset_receipt_sha256="ds_sha",
            feature_snapshot_sha256="feat_sha",
            prediction_as_of="2026-07-27T10:00:00Z",
            canonical_event_id="EVT_001",
            market_family="corners",
            selection="over_9.5",
            calibrated_probability=0.55,
        )


def test_minimum_odds_decimal_calculation():
    """Verify minimum acceptable odds uses conservative probability and Decimal precision."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")

    estimate = ProbabilityEstimateV2.create(
        model_card=card,
        dataset_receipt_sha256="ds_sha_123",
        feature_snapshot_sha256="feat_sha_123",
        prediction_as_of="2026-07-27T10:00:00Z",
        canonical_event_id="EVT_ARS_CHE_001",
        market_family="result",
        selection="home",
        calibrated_probability=0.50,
        uncertainty_margin=0.02,  # conservative_p = 0.48
        required_roi=0.05,  # 1.05 / 0.48 = 2.1875
    )

    assert estimate.calibrated_probability == 0.50
    assert estimate.conservative_probability == 0.48
    assert estimate.fair_decimal_odds == Decimal("2.0000")  # 1 / 0.50 = 2.0
    assert estimate.minimum_acceptable_operator_odds == Decimal("2.1875")  # (1.05) / 0.48 = 2.1875


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
