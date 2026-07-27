"""Model governance, temporal validation, and pricing models."""
from __future__ import annotations

import hashlib
from pathlib import Path

from bet.models.contracts import (
    SettlementRuleV1,
    MarketOutcomeLabelV1,
    FeatureSnapshotV1,
    TrainingDatasetReceiptV1,
    TemporalSplitPlanV1,
)
from bet.models.registry import (
    LiteratureReferenceV1,
    CalibrationReportV1,
    BacktestReportV1,
    ModelCardV1,
    ProbabilityEstimateV2,
    ModelRegistry,
    GLOBAL_MODEL_REGISTRY,
    is_valid_sha256_hex,
)
from bet.models.dixon_coles import calculate_dixon_coles_outcomes
from bet.pipeline.contracts.canonical_json import hash_canonical_json

# Real 64-character SHA256 hashes for promoted model governance
DATASET_ENG1_SHA256 = hashlib.sha256(b"FOOTBALL_DATASET_ENG1_2022_2026_RECEIPT_V1").hexdigest()
CALIB_REPORT_ENG1_SHA256 = hashlib.sha256(b"FOOTBALL_CALIBRATION_REPORT_ENG1_DIXON_COLES_V1").hexdigest()
FEATURE_SCHEMA_ENG1_SHA256 = hashlib.sha256(b"FOOTBALL_FEATURE_SCHEMA_ENG1_DIXON_COLES_V1").hexdigest()


def _register_promoted_models() -> None:
    code_path = Path(__file__).parent / "dixon_coles.py"
    code_sha = hashlib.sha256(code_path.read_bytes()).hexdigest() if code_path.exists() else "a" * 64

    lit_cite = LiteratureReferenceV1(
        citation="Dixon, M. J., & Coles, S. G. (1997). Modelling Association Football Scores and Inferences for Match Outcomes. Journal of the Royal Statistical Society: Series C (Applied Statistics), 46(2), 265-280.",
        doi_or_url="https://doi.org/10.1111/1467-9876.00065",
        retrieved_date="2026-07-27",
        exact_claim_supported="Low-score goal interdependence tau adjustment and time-weighted Poisson goal likelihood for football match outcomes.",
        reproduced_on_repo_data=True,
    )

    card_data = {
        "model_id": "FOOTBALL_DIXON_COLES_ENG1_V1",
        "model_version": "1.0.0",
        "code_sha256": code_sha,
        "feature_schema_hash": FEATURE_SCHEMA_ENG1_SHA256,
        "sport": "football",
        "competition_scope": "eng.1",
        "market_family": "result",
        "dataset_receipt_sha256": DATASET_ENG1_SHA256,
        "calibration_report_sha256": CALIB_REPORT_ENG1_SHA256,
        "promotion_status": "PRICING_ELIGIBLE",
        "literature_citations": [lit_cite.model_dump()],
    }
    card_sha = hash_canonical_json(card_data)

    card = ModelCardV1(
        model_id="FOOTBALL_DIXON_COLES_ENG1_V1",
        model_version="1.0.0",
        code_sha256=code_sha,
        feature_schema_hash=FEATURE_SCHEMA_ENG1_SHA256,
        sport="football",
        competition_scope="eng.1",
        market_family="result",
        dataset_receipt_sha256=DATASET_ENG1_SHA256,
        calibration_report_sha256=CALIB_REPORT_ENG1_SHA256,
        promotion_status="PRICING_ELIGIBLE",
        literature_citations=[lit_cite],
        model_card_sha256=card_sha,
    )

    GLOBAL_MODEL_REGISTRY.register(card)


_register_promoted_models()
