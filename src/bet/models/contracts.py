"""Point-in-time dataset, feature, label, and temporal split contracts."""
from __future__ import annotations

from typing import Any
from pydantic import Field
from bet.strict_model import StrictBaseModel


class SettlementRuleV1(StrictBaseModel):
    """Rule defining how a market outcome is settled from official match results."""
    market_family: str
    rule_description: str
    void_push_handled: bool = True


class MarketOutcomeLabelV1(StrictBaseModel):
    """Ground truth outcome label for a settled market."""
    canonical_event_id: str
    market_family: str
    selection: str
    outcome: str  # WON | LOST | VOID | HALF_WON | HALF_LOST
    settled_at: str
    official_score_or_stat: str
    settlement_rule: SettlementRuleV1


class FeatureSnapshotV1(StrictBaseModel):
    """Point-in-time feature vector snapshot."""
    snapshot_id: str
    canonical_event_id: str
    prediction_as_of: str
    features: dict[str, Any]
    feature_schema_hash: str
    future_leakage_checked: bool = True


class TrainingDatasetReceiptV1(StrictBaseModel):
    """Immutable receipt binding a training dataset to its source records and hashes."""
    dataset_id: str
    dataset_name: str
    sport: str
    competition_scope: str
    start_date: str
    end_date: str
    sample_count: int = Field(ge=1)
    dataset_sha256: str
    point_in_time_verified: bool = True


class TemporalSplitPlanV1(StrictBaseModel):
    """Chronological expanding/rolling window split plan preventing temporal leakage."""
    plan_id: str
    train_start: str
    train_end: str
    calibration_start: str
    calibration_end: str
    test_start: str
    test_end: str
    gap_days: int = Field(default=0, ge=0)
    chronological_order_verified: bool = True
