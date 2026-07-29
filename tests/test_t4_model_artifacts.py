"""Checkpoint T4 tests: removal of fake model promotion and verifiable pricing requirements."""
from __future__ import annotations

import pytest
from bet.models.registry import ModelCardV1, ProbabilityEstimateV2, GLOBAL_MODEL_REGISTRY


def test_t4_dixon_coles_analysis_only():
    """Verify default Dixon-Coles model is ANALYSIS_ONLY and not PRICING_ELIGIBLE."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "ANALYSIS_ONLY"
    assert not card.is_pricing_eligible()


def test_t4_prediction_time_at_or_after_event_start_rejected(tmp_path):
    """Verify prediction_as_of >= event_start_time is rejected."""
    import hashlib
    from pathlib import Path
    models_dir = Path(__file__).resolve().parent.parent / "models"
    models_dir.mkdir(exist_ok=True)

    ds_content = b"dataset_receipt_2222"
    cal_content = b"calibration_report_3333"
    ds_hash = hashlib.sha256(ds_content).hexdigest()
    cal_hash = hashlib.sha256(cal_content).hexdigest()

    (models_dir / f"ds_{ds_hash[:8]}.bin").write_bytes(ds_content)
    (models_dir / f"cal_{cal_hash[:8]}.bin").write_bytes(cal_content)

    promoted_card = ModelCardV1(
        model_id="TEST_PROMOTED_001",
        model_version="1.0.0",
        code_sha256="a" * 64,
        feature_schema_hash="b" * 64,
        sport="football",
        competition_scope="eng.1",
        market_family="result",
        dataset_receipt_sha256=ds_hash,
        calibration_report_sha256=cal_hash,
        promotion_status="PRICING_ELIGIBLE",
        model_card_sha256="c" * 64,
    )

    with pytest.raises(ValueError, match="at or after event_start_time"):
        ProbabilityEstimateV2.create(
            model_card=promoted_card,
            dataset_receipt_sha256=ds_hash,
            feature_snapshot_sha256="b" * 64,
            prediction_as_of="2026-07-27T18:00:00Z",
            canonical_event_id="EVT_001",
            market_family="result",
            selection="home",
            calibrated_probability=0.50,
            event_start_time="2026-07-27T18:00:00Z",
        )
