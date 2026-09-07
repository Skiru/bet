"""Checkpoint T4: no fake model promotion, and pricing must be verifiable."""
from __future__ import annotations

import hashlib

import pytest

from bet.models.registry import (
    GLOBAL_MODEL_REGISTRY,
    ModelCardV1,
    ProbabilityEstimateV2,
)


def test_t4_dixon_coles_analysis_only():
    """Verify default Dixon-Coles model is ANALYSIS_ONLY and not PRICING_ELIGIBLE."""
    card = GLOBAL_MODEL_REGISTRY.get_strict("FOOTBALL_DIXON_COLES_ENG1_V1")
    assert card.promotion_status == "ANALYSIS_ONLY"
    assert not card.is_pricing_eligible()


def test_t4_prediction_time_at_or_after_event_start_rejected(tmp_path):
    """Verify prediction_as_of >= event_start_time is rejected.

    ``create`` runs the eligibility gate before the time gate, so the card has
    to clear eligibility for the clock to be consulted at all. It is cleared
    here through the hash fallback in ``is_pricing_eligible`` -- two named
    receipts under an explicit ``search_dirs`` -- and not through
    ``ModelPackageResolver``, which lives in the quarantined S0-S10 stack
    (``legacy/bet_pipeline/readiness_contracts.py``) and cannot be imported.
    Both sides of the merge conflict this file carried built a package for the
    resolver instead, so both asserted the time gate while never reaching it:
    the ValueError they caught was "is not PRICING_ELIGIBLE".

    The property under test is the time gate, not the package format, which is
    why substituting the fallback is a repair and not a weakening -- and the
    precondition below is what keeps that honest.

    Receipts go to ``tmp_path``. The previous version wrote them into the
    repository's own ``models/`` tree and left them behind.
    """
    ds_content = b"dataset_receipt_2222"
    cal_content = b"calibration_report_3333"
    (tmp_path / "dataset_receipt.json").write_bytes(ds_content)
    (tmp_path / "calibration_report.json").write_bytes(cal_content)
    ds_hash = hashlib.sha256(ds_content).hexdigest()
    cal_hash = hashlib.sha256(cal_content).hexdigest()

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

    # Without this the assertion below would pass for the wrong reason: an
    # ineligible card is refused before the clock is read, and the test would
    # certify the time gate while only ever exercising the eligibility gate.
    assert promoted_card.is_pricing_eligible(search_dirs=[tmp_path])

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
            search_dirs=[tmp_path],
        )
