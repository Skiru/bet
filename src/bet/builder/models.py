"""Typed models for same-event Bet Builder candidates, joint probability, and S8 quote packs."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from pydantic import Field
from src.bet.pipeline.contracts.base import StrictBaseModel


class BuilderLegV1(StrictBaseModel):
    """An individual leg within a same-event Bet Builder."""
    leg_id: str
    canonical_event_id: str
    sport: str
    market_family: str
    selection: str
    line: str | float | None = None
    calibrated_probability: float = Field(gt=0.0, lt=1.0)
    fair_odds: Decimal
    minimum_acceptable_odds: Decimal


class BuilderCompatibilityDecisionV1(StrictBaseModel):
    """Decision validating whether two or more legs can form a valid Bet Builder."""
    compatible: bool
    canonical_event_id: str
    leg_ids: tuple[str, ...]
    rejection_reason: str | None = None


class JointModelScopeV1(StrictBaseModel):
    """Model card and scope for a joint probability model."""
    joint_model_id: str
    model_version: str
    sport: str
    supported_market_family_pairs: tuple[tuple[str, str], ...]
    calibration_report_sha256: str
    promotion_status: str = "PRICING_ELIGIBLE"


class JointProbabilityEstimateV1(StrictBaseModel):
    """Calibrated joint probability estimate for a same-event conjunction outcome."""
    joint_model_id: str
    calibrated_joint_probability: float = Field(gt=0.0, lt=1.0)
    conservative_joint_probability: float = Field(gt=0.0, lt=1.0)
    independence_assumed: bool = False  # NEVER True without explicit independence test proof
    fair_combined_odds: Decimal
    minimum_acceptable_combined_odds: Decimal


class SameEventBuilderCandidateV1(StrictBaseModel):
    """Candidate same-event Bet Builder idea group."""
    builder_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    legs: tuple[BuilderLegV1, ...]
    joint_model_id: str
    joint_probability: JointProbabilityEstimateV1
    correlation_risk: str = "LOW"
    visible_superbet_combined_odds: Decimal | None = None  # Human-entered in S9 only; MUST be None in S8


class S8IdeaGroupV1(StrictBaseModel):
    """S8 idea group representation for human Superbet operator review."""
    idea_group_id: str
    canonical_event_id: str
    sport: str
    competition: str
    event_name: str
    builder_candidates: list[SameEventBuilderCandidateV1] = Field(default_factory=list)


class BuilderRejectionV1(StrictBaseModel):
    """Rejection record for an incompatible or unpriced pair."""
    rejection_id: str
    canonical_event_id: str
    leg_ids: tuple[str, ...]
    reason_code: str
