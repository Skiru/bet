"""Business contracts for ANALYSIS_BUILD, EXECUTION, and POST_EVENT steps (S3 to S10)."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, field_validator
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import EventRecordV1, SourceReferenceV1, EvidenceClaimV1, _validate_sha256


def _check_opt_sha(v: str | None) -> str | None:
    if v is None or v == "":
        return v
    return _validate_sha256(v)


class ProbabilityEstimateRecordV1(StrictBaseModel):
    canonical_event_id: str
    market_family: str
    selection: str
    calibrated_probability: float = Field(ge=0.0, le=1.0)
    uncertainty_margin: float = Field(ge=0.0)
    model_id: str
    dataset_receipt_sha256: str
    calibration_report_sha256: str
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED", "UNPRICED"] = "PASS"

    @field_validator("dataset_receipt_sha256", "calibration_report_sha256")
    @classmethod
    def check_hashes(cls, v: str) -> str:
        res = _validate_sha256(v)
        if res is None:
            raise ValueError("Receipt SHA256 cannot be None")
        return res


# S3 Contract
class S3CalibratedProbabilitiesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S3_CALIBRATED_PROBABILITIES"] = "S3_CALIBRATED_PROBABILITIES"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    probabilities_count: int = Field(ge=0, default=0)
    probability_estimates: list[ProbabilityEstimateRecordV1] = Field(default_factory=list)


class ValuationCandidateRecordV1(StrictBaseModel):
    canonical_event_id: str
    market_family: str
    selection: str
    fair_odds: float = Field(ge=1.0)
    ev_estimate: float = 0.0
    minimum_acceptable_odds: float = Field(ge=1.0)
    status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED", "UNPRICED", "PRICE_PENDING"] = "PASS"


# S4 Contract
class S4ExpectedValueEstimatesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S4_EXPECTED_VALUE_ESTIMATES"] = "S4_EXPECTED_VALUE_ESTIMATES"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    candidates_valuated_count: int = Field(ge=0, default=0)
    valuation_candidates: list[ValuationCandidateRecordV1] = Field(default_factory=list)


class ContextReviewRecordV1(StrictBaseModel):
    canonical_event_id: str
    sport: str
    motivation_score: float = 1.0
    risk_classification: str = "LOW"
    context_notes: str | None = None
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"] = "PASS"


# S5 Contract
class S5ContextMotivationRiskV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S5_CONTEXT_MOTIVATION_RISK"] = "S5_CONTEXT_MOTIVATION_RISK"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    events_reviewed_count: int = Field(ge=0, default=0)
    context_reviews: list[ContextReviewRecordV1] = Field(default_factory=list)


class FilteredCandidateRecordV1(StrictBaseModel):
    canonical_event_id: str
    selection: str
    repeat_risk_flag: bool = False
    action: Literal["ALLOW", "FILTER_DUPLICATE", "FILTER_EXPOSURE"] = "ALLOW"
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"] = "PASS"


# S6 Contract
class S6PortfolioRepeatGuardV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S6_PORTFOLIO_REPEAT_GUARD"] = "S6_PORTFOLIO_REPEAT_GUARD"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    repeats_filtered_count: int = Field(ge=0, default=0)
    filtered_candidates: list[FilteredCandidateRecordV1] = Field(default_factory=list)


class ApprovedPickRecordV1(StrictBaseModel):
    pick_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    market_family: str
    selection: str
    line: float | None = None
    model_fair_probability: float = Field(ge=0.0, le=1.0)
    recommended_minimum_odds: float = Field(ge=1.0)
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"] = "PASS"


# S7 Contract
class S7ApprovedPicksV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S7_APPROVED_PICKS"] = "S7_APPROVED_PICKS"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    approved_candidate_count: int = Field(ge=0, default=0)
    approved_picks: list[ApprovedPickRecordV1] = Field(default_factory=list)


class MappingSuggestionRecordV1(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    canonical_event_id: str
    selection_id: str
    manual_operator: Literal["SUPERBET"] = "SUPERBET"
    mapping_ambiguity: str = "UNAMBIGUOUS"
    visible_operator_market_name: str | None = None
    visible_operator_line: str | None = None
    human_entered_decimal_quote: float | None = None
    quote_as_of: str | None = None
    operator_availability_asserted: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False


# S7b Contract
class S7bSuperbetManualMappingV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: Literal["S7B_SUPERBET_MANUAL_MAPPING"] = "S7B_SUPERBET_MANUAL_MAPPING"
    status: Literal["READY_FOR_MANUAL_MAPPING", "NO_ACTION_TERMINAL", "BLOCK"] = "READY_FOR_MANUAL_MAPPING"
    betting_day: str
    run_id: str
    operator_workflow: Literal["SUPERBET_MANUAL_BET_BUILDER"] = "SUPERBET_MANUAL_BET_BUILDER"
    operator_availability_asserted: bool = False
    approved_candidate_count: int = Field(ge=0, default=0)
    represented_candidate_count: int = Field(ge=0, default=0)
    mapping_suggestions: list[MappingSuggestionRecordV1] = Field(default_factory=list)
    event_records: list[EventRecordV1] = Field(default_factory=list)
    source_s7_evidence_path: str | None = None
    source_s7_evidence_sha256: str | None = None
    source_s7_output_path: str | None = None
    source_s7_output_sha256: str | None = None
    manual_verification_required: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False


class QuoteCardRecordV1(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    canonical_event_id: str
    selection_id: str
    manual_operator: Literal["SUPERBET"] = "SUPERBET"
    minimum_acceptable_odds: float | None = None


class S8IdeaGroupV1(StrictBaseModel):
    group_id: str
    canonical_event_id: str
    sport: str
    competition: str
    leg_ids: list[str] = Field(default_factory=list)
    joint_probability: float | None = None
    joint_fair_odds: float | None = None
    minimum_acceptable_odds: float | None = None
    joint_model_id: str | None = None
    joint_model_sha256: str | None = None
    calibration_report_sha256: str | None = None

    @field_validator("joint_model_sha256", "calibration_report_sha256")
    @classmethod
    def check_hashes(cls, v: str | None) -> str | None:
        return _check_opt_sha(v)


# S8 Contract
class S8SuperbetManualQuotePackV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: Literal["S8_SUPERBET_MANUAL_QUOTE_PACK"] = "S8_SUPERBET_MANUAL_QUOTE_PACK"
    status: Literal["READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW", "NO_ACTION_TERMINAL", "BLOCK"] = "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
    betting_day: str
    run_id: str
    operator_workflow: Literal["SUPERBET_MANUAL_BET_BUILDER"] = "SUPERBET_MANUAL_BET_BUILDER"
    source_s7b_evidence_path: str | None = None
    source_s7b_evidence_sha256: str | None = None
    source_s7b_output_path: str | None = None
    source_s7b_output_sha256: str | None = None
    quote_card_count: int = Field(ge=0, default=0)
    quote_cards: list[QuoteCardRecordV1] = Field(default_factory=list)
    idea_groups: list[S8IdeaGroupV1] = Field(default_factory=list)
    event_records: list[EventRecordV1] = Field(default_factory=list)
    analytical_status: str = "READY"
    pricing_status: str = "UNPRICED"
    risk_status: str = "ACCEPTABLE_FOR_MANUAL_QUOTE"
    final_status: str = "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"
    ev_available: bool = False
    kelly_available: bool = False
    stake_available: bool = False
    combined_bookmaker_odds: float | None = None
    requires_human_gate: bool = True
    ready_for_human_gate: bool = True
    ready_for_production_execution: bool = False
    production_selectable: bool = False
    production_coupon_write: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False
    operator_availability_asserted: bool = False
    operator_automation_enabled: bool = False

    @field_validator("source_s7b_evidence_sha256", "source_s7b_output_sha256")
    @classmethod
    def check_hashes(cls, v: str | None) -> str | None:
        return _check_opt_sha(v)


class ExecutedBetRecordV1(StrictBaseModel):
    execution_id: str
    canonical_event_id: str
    market_family: str
    selection: str
    operator_odds: float = Field(ge=1.0)
    stake_amount: float = Field(ge=0.0)
    executed_at: str
    human_operator_id: str


# S9 Contract
class S9ExecutedBetsJournalV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S9_EXECUTED_BETS_JOURNAL"] = "S9_EXECUTED_BETS_JOURNAL"
    status: Literal["EXECUTED", "NO_BET", "REJECTED", "BLOCK"] = "EXECUTED"
    betting_day: str
    run_id: str
    human_operator_verified: bool = True
    executed_bets: list[ExecutedBetRecordV1] = Field(default_factory=list)


class PostSessionLearningRecordV1(StrictBaseModel):
    record_id: str
    canonical_event_id: str
    model_id: str
    actual_outcome: str
    prediction_error: float
    learned_notes: str | None = None


# S10 Contract
class S10SettlementHandoffV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S10_SETTLEMENT_HANDOFF"] = "S10_SETTLEMENT_HANDOFF"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    post_session_learning_records: list[PostSessionLearningRecordV1] = Field(default_factory=list)
