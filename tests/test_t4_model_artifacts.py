"""Checkpoint T4 tests: removal of fake model promotion and verifiable pricing requirements."""
from __future__ import annotations

import pytest
from bet.models.registry import ModelCardV1, ProbabilityEstimateV2, GLOBAL_MODEL_REGISTRY


def test_t4_dixon_coles_analysis_only():
    """Verify default Dixon-Coles model is ANALYSIS_ONLY and not PRICING_ELIGIBLE."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "ANALYSIS_ONLY"
    assert not card.is_pricing_eligible()


def test_t4_prediction_time_at_or_after_event_start_rejected():
    """Verify prediction_as_of >= event_start_time is rejected."""
    promoted_card = ModelCardV1(
        model_id="TEST_PROMOTED_001",
        model_version="1.0.0",
        code_sha256="0" * 64,
        feature_schema_hash="1" * 64,
        sport="football",
        competition_scope="eng.1",
        market_family="result",
        dataset_receipt_sha256="2" * 64,
        calibration_report_sha256="3" * 64,
        promotion_status="PRICING_ELIGIBLE",
        model_card_sha256="4" * 64,
    )

    with pytest.raises(ValueError, match="at or after event_start_time"):
        ProbabilityEstimateV2.create(
            model_card=promoted_card,
            dataset_receipt_sha256="2" * 64,
            feature_snapshot_sha256="1" * 64,
            prediction_as_of="2026-07-27T18:00:00Z",
            canonical_event_id="EVT_001",
            market_family="result",
            selection="home",
            calibrated_probability=0.50,
            event_start_time="2026-07-27T18:00:00Z",
        )
