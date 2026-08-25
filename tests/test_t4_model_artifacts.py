"""Checkpoint T4 tests: removal of fake model promotion and verifiable pricing requirements."""
from __future__ import annotations

<<<<<<< HEAD
=======
import json
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
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
<<<<<<< HEAD
    models_dir = Path(__file__).resolve().parent.parent / "models"
    models_dir.mkdir(exist_ok=True)

    ds_content = b"dataset_receipt_2222"
    cal_content = b"calibration_report_3333"
    ds_hash = hashlib.sha256(ds_content).hexdigest()
    cal_hash = hashlib.sha256(cal_content).hexdigest()

    (models_dir / f"ds_{ds_hash[:8]}.bin").write_bytes(ds_content)
    (models_dir / f"cal_{cal_hash[:8]}.bin").write_bytes(cal_content)
=======
    models_dir = Path(__file__).resolve().parent.parent / "models" / "store" / "test_pkg_t4"
    models_dir.mkdir(parents=True, exist_ok=True)

    ds_content = b"dataset_receipt_2222"
    cal_content = b"calibration_report_3333"
    code_content = b"code_content_4444"
    schema_content = b"schema_content_5555"
    split_content = b"split_content_6666"
    back_content = b"backtest_content_7777"
    unc_content = b"uncertainty_content_8888"
    card_content = b"model_card_content_9999"

    ds_hash = hashlib.sha256(ds_content).hexdigest()
    cal_hash = hashlib.sha256(cal_content).hexdigest()
    code_hash = hashlib.sha256(code_content).hexdigest()
    schema_hash = hashlib.sha256(schema_content).hexdigest()
    fit_hash = "e" * 64
    split_hash = hashlib.sha256(split_content).hexdigest()
    back_hash = hashlib.sha256(back_content).hexdigest()
    unc_hash = hashlib.sha256(unc_content).hexdigest()
    card_hash = hashlib.sha256(card_content).hexdigest()

    prom_data = {
        "status": "PROMOTED",
        "bound_artifact_hashes": {
            "dataset_receipt_sha256": ds_hash,
            "calibration_report_sha256": cal_hash,
        }
    }
    prom_bytes = json.dumps(prom_data, sort_keys=True).encode("utf-8")
    prom_hash = hashlib.sha256(prom_bytes).hexdigest()

    (models_dir / "dataset-receipt.json").write_bytes(ds_content)
    (models_dir / "calibration.json").write_bytes(cal_content)
    (models_dir / "code-receipt.json").write_bytes(code_content)
    (models_dir / "feature-schema.json").write_bytes(schema_content)
    (models_dir / "temporal-split.json").write_bytes(split_content)
    (models_dir / "backtest.json").write_bytes(back_content)
    (models_dir / "uncertainty-method.json").write_bytes(unc_content)
    (models_dir / "model-card.json").write_bytes(card_content)
    (models_dir / "promotion-decision.json").write_bytes(prom_bytes)
    (models_dir / "model-package.json").write_text(json.dumps({
        "package_id": "TEST_PROMOTED_001",
        "sport": "football",
        "competition": "eng.1",
        "market": "result",
        "model_package_sha256": card_hash,
        "dataset_receipt_sha256": ds_hash,
        "feature_schema_sha256": schema_hash,
        "fitted_model_sha256": fit_hash,
        "code_receipt_sha256": code_hash,
        "temporal_split_sha256": split_hash,
        "backtest_report_sha256": back_hash,
        "calibration_report_sha256": cal_hash,
        "uncertainty_method_sha256": unc_hash,
        "promotion_decision_sha256": prom_hash,
        "model_card_sha256": card_hash,
    }))
>>>>>>> fix/bet-v5-final-one-pass-closure-v4

    promoted_card = ModelCardV1(
        model_id="TEST_PROMOTED_001",
        model_version="1.0.0",
<<<<<<< HEAD
        code_sha256="a" * 64,
        feature_schema_hash="b" * 64,
=======
        package_path=str(models_dir),
        code_sha256=code_hash,
        feature_schema_hash=schema_hash,
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
        sport="football",
        competition_scope="eng.1",
        market_family="result",
        dataset_receipt_sha256=ds_hash,
        calibration_report_sha256=cal_hash,
        promotion_status="PRICING_ELIGIBLE",
<<<<<<< HEAD
        model_card_sha256="c" * 64,
=======
        model_card_sha256=card_hash,
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
    )

    with pytest.raises(ValueError, match="at or after event_start_time"):
        ProbabilityEstimateV2.create(
            model_card=promoted_card,
            dataset_receipt_sha256=ds_hash,
<<<<<<< HEAD
            feature_snapshot_sha256="b" * 64,
=======
            feature_snapshot_sha256=schema_hash,
>>>>>>> fix/bet-v5-final-one-pass-closure-v4
            prediction_as_of="2026-07-27T18:00:00Z",
            canonical_event_id="EVT_001",
            market_family="result",
            selection="home",
            calibrated_probability=0.50,
            event_start_time="2026-07-27T18:00:00Z",
        )
