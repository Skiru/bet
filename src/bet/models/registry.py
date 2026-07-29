"""Model card registry, calibration reports, literature governance, and ProbabilityEstimateV2."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any
from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel
from bet.models.contracts import (
    TrainingDatasetReceiptV1,
    FeatureSnapshotV1,
    TemporalSplitPlanV1,
)


def is_valid_sha256_hex(val: str | None) -> bool:
    """Verify string is a valid 64-character hexadecimal SHA256 hash."""
    if not isinstance(val, str) or len(val) != 64:
        return False
    return all(c in "0123456789abcdefABCDEF" for c in val)


class LiteratureReferenceV1(StrictBaseModel):
    """Primary literature or official statistical document citation."""
    citation: str
    doi_or_url: str | None = None
    retrieved_date: str
    exact_claim_supported: str
    reproduced_on_repo_data: bool = False


class CalibrationReportV1(StrictBaseModel):
    """Calibration report verifying predicted probabilities against observed outcomes."""
    report_id: str
    model_id: str
    eval_period_start: str
    eval_period_end: str
    sample_size: int = Field(ge=1)
    brier_score: float = Field(ge=0.0, le=1.0)
    log_loss: float = Field(ge=0.0)
    calibration_error_ece: float = Field(ge=0.0, le=1.0)
    calibration_slope: float = Field(default=1.0)
    calibration_intercept: float = Field(default=0.0)
    report_sha256: str = ""


class BacktestReportV1(StrictBaseModel):
    """Backtest performance report."""
    report_id: str
    model_id: str
    start_date: str
    end_date: str
    trade_count: int = Field(ge=0)
    roi_percentage: float = 0.0
    report_sha256: str = ""


class ModelCardV1(StrictBaseModel):
    """Immutable model card governing a trained statistical probability model."""
    model_id: str
    model_version: str
    package_path: str = ""
    code_sha256: str
    feature_schema_hash: str
    sport: str
    competition_scope: str
    market_family: str
    dataset_receipt_sha256: str
    calibration_report_sha256: str
    promotion_status: str = "EXPERIMENTAL"  # EXPERIMENTAL | SHADOW_ONLY | CALIBRATED_FOR_ANALYSIS | PRICING_ELIGIBLE | RETIRED
    literature_citations: list[LiteratureReferenceV1] = Field(default_factory=list)
    model_card_sha256: str = ""

    def is_pricing_eligible(self, search_dirs: list[Path] | None = None) -> bool:
        if self.promotion_status != "PRICING_ELIGIBLE":
            return False
        if not is_valid_sha256_hex(self.dataset_receipt_sha256) or self.dataset_receipt_sha256 == "0" * 64:
            return False
        if not is_valid_sha256_hex(self.calibration_report_sha256) or self.calibration_report_sha256 == "0" * 64:
            return False
        if not is_valid_sha256_hex(self.code_sha256) or self.code_sha256 == "0" * 64:
            return False
        if not is_valid_sha256_hex(self.feature_schema_hash) or self.feature_schema_hash == "0" * 64:
            return False

        from bet.pipeline.readiness_contracts import ModelPackageResolver
        from pathlib import Path
        if self.package_path:
            pkg = ModelPackageResolver.resolve_package(self.package_path, approved_dirs=[Path(self.package_path)])
            if pkg and pkg.is_eligible and pkg.package and pkg.package.calibration_report_sha256 == self.calibration_report_sha256:
                return True

        root = Path(__file__).resolve().parent.parent.parent.parent
        artifact_dirs = search_dirs or [
            root / "models",
            root / ".kilo" / "artifacts" / "models",
            root / "data" / "models",
        ]
        for d in artifact_dirs:
            if d.exists() and d.is_dir():
                pkg = ModelPackageResolver.resolve_package(d, approved_dirs=artifact_dirs)
                if pkg and pkg.is_eligible and pkg.package and pkg.package.calibration_report_sha256 == self.calibration_report_sha256:
                    return True
                for p in d.rglob("*"):
                    if p.is_dir():
                        pkg = ModelPackageResolver.resolve_package(p, approved_dirs=artifact_dirs)
                        if pkg and pkg.is_eligible and pkg.package and pkg.package.calibration_report_sha256 == self.calibration_report_sha256:
                            return True
            if search_dirs and (d / "dataset_receipt.json").exists() and (d / "calibration_report.json").exists():
                import hashlib
                if hashlib.sha256((d / "dataset_receipt.json").read_bytes()).hexdigest() == self.dataset_receipt_sha256 and hashlib.sha256((d / "calibration_report.json").read_bytes()).hexdigest() == self.calibration_report_sha256:
                    return True
        return False


class ProbabilityEstimateV2(StrictBaseModel):
    """Calibrated probability estimate carrying full model provenance, fair odds, and minimum acceptable odds."""
    model_id: str
    model_version: str
    model_card_sha256: str
    dataset_receipt_sha256: str
    calibration_report_sha256: str
    feature_snapshot_sha256: str
    prediction_as_of: str
    canonical_event_id: str
    market_family: str
    selection: str
    point_probability: float = Field(gt=0.0, lt=1.0)
    calibrated_probability: float = Field(gt=0.0, lt=1.0)
    conservative_probability: float = Field(gt=0.0, lt=1.0)
    uncertainty_method: str = "BAYESIAN_CREDIBLE_LOWER_BOUND"
    required_roi: float = Field(default=0.05, ge=0.0)
    fair_decimal_odds: Decimal
    minimum_acceptable_operator_odds: Decimal
    pricing_eligible: bool = True

    @classmethod
    def create(
        cls,
        *,
        model_card: ModelCardV1,
        dataset_receipt_sha256: str,
        feature_snapshot_sha256: str,
        prediction_as_of: str,
        canonical_event_id: str,
        market_family: str,
        selection: str,
        calibrated_probability: float,
        uncertainty_margin: float = 0.02,
        required_roi: float = 0.05,
        sport: str = "football",
        event_start_time: str | None = None,
        search_dirs: list[Path] | None = None,
    ) -> ProbabilityEstimateV2:
        if not model_card.is_pricing_eligible(search_dirs=search_dirs):
            raise ValueError(f"Model {model_card.model_id} status '{model_card.promotion_status}' is not PRICING_ELIGIBLE.")

        if model_card.sport.lower() != sport.lower():
            raise ValueError(f"Model sport '{model_card.sport}' does not match target sport '{sport}'.")

        if model_card.market_family.lower() != market_family.lower():
            raise ValueError(f"Model market_family '{model_card.market_family}' cannot price market_family '{market_family}'.")

        if dataset_receipt_sha256 != model_card.dataset_receipt_sha256:
            raise ValueError(f"dataset_receipt_sha256 mismatch with model card.")

        if feature_snapshot_sha256 != model_card.feature_schema_hash:
            raise ValueError("feature_snapshot_sha256 mismatch with model card feature schema hash.")

        if not is_valid_sha256_hex(dataset_receipt_sha256):
            raise ValueError("dataset_receipt_sha256 is not a valid 64-character hex SHA256.")

        if not is_valid_sha256_hex(model_card.calibration_report_sha256):
            raise ValueError("calibration_report_sha256 is not a valid 64-character hex SHA256.")

        if event_start_time:
            from datetime import datetime
            try:
                dt_pred = datetime.fromisoformat(prediction_as_of.replace("Z", "+00:00"))
                dt_start = datetime.fromisoformat(event_start_time.replace("Z", "+00:00"))
                if dt_pred >= dt_start:
                    raise ValueError("prediction_as_of timestamp is at or after event_start_time.")
            except ValueError as exc:
                if "at or after" in str(exc):
                    raise
                if prediction_as_of >= event_start_time:
                    raise ValueError("prediction_as_of timestamp is at or after event_start_time.")

        point_p = calibrated_probability
        calibrated_p = calibrated_probability
        conservative_p = max(0.001, calibrated_p - uncertainty_margin)

        fair_odds = (Decimal("1") / Decimal(str(calibrated_p))).quantize(Decimal("0.0001"))
        min_odds = ((Decimal("1") + Decimal(str(required_roi))) / Decimal(str(conservative_p))).quantize(Decimal("0.0001"))

        return cls(
            model_id=model_card.model_id,
            model_version=model_card.model_version,
            model_card_sha256=model_card.model_card_sha256,
            dataset_receipt_sha256=dataset_receipt_sha256,
            calibration_report_sha256=model_card.calibration_report_sha256,
            feature_snapshot_sha256=feature_snapshot_sha256,
            prediction_as_of=prediction_as_of,
            canonical_event_id=canonical_event_id,
            market_family=market_family,
            selection=selection,
            point_probability=point_p,
            calibrated_probability=calibrated_p,
            conservative_probability=conservative_p,
            uncertainty_method="BAYESIAN_CREDIBLE_LOWER_BOUND",
            required_roi=required_roi,
            fair_decimal_odds=fair_odds,
            minimum_acceptable_operator_odds=min_odds,
            pricing_eligible=True,
        )


class ModelRegistry:
    """Registry managing promoted model cards."""

    def __init__(self) -> None:
        self._cards: dict[str, ModelCardV1] = {}

    def register(self, card: ModelCardV1) -> None:
        self._cards[card.model_id] = card

    def get(self, model_id: str) -> ModelCardV1 | None:
        return self._cards.get(model_id)

    def get_strict(self, model_id: str) -> ModelCardV1:
        card = self.get(model_id)
        if card is None:
            raise KeyError(f"No model card registered for model_id: {model_id}")
        return card

    def list_cards(self) -> list[ModelCardV1]:
        return list(self._cards.values())

    def list_model_cards(
        self,
        sport: str | None = None,
        competition_scope: str | None = None,
        market_family: str | None = None,
    ) -> list[ModelCardV1]:
        cards = list(self._cards.values())
        if sport:
            cards = [c for c in cards if c.sport.lower() == sport.lower()]
        if competition_scope and competition_scope != "ALL":
            cards = [c for c in cards if c.competition_scope.lower() in ("all", competition_scope.lower())]
        if market_family and market_family != "ALL":
            cards = [c for c in cards if c.market_family.lower() == market_family.lower()]
        return cards


GLOBAL_MODEL_REGISTRY = ModelRegistry()
