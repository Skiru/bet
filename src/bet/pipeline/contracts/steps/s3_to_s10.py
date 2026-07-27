"""Business contracts for ANALYSIS_BUILD, EXECUTION, and POST_EVENT steps (S3 to S10)."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, field_validator, model_validator
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
    fair_odds: float | None = None
    ev_estimate: float | None = None
    minimum_acceptable_odds: float | None = None
    status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED", "UNPRICED", "PRICE_PENDING", "ANALYSIS_ONLY"]


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
    motivation_score: float
    risk_classification: str
    context_notes: str | None = None
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"]


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
    repeat_risk_flag: bool
    action: Literal["ALLOW", "FILTER_DUPLICATE", "FILTER_EXPOSURE"]
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"]


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
    calibrated_probability: float | None = None
    model_fair_probability: float | None = None
    fair_decimal_odds: float | None = None
    minimum_acceptable_operator_odds: float | None = None
    recommended_minimum_odds: float | None = None
    pricing_status: str = "UNPRICED"
    model_id: str | None = None
    model_card_sha256: str | None = None
    dataset_receipt_sha256: str | None = None
    calibration_report_sha256: str | None = None
    terminal_status: Literal["PASS", "DEGRADED_CONTINUE", "REJECTED", "NO_ACTION", "BLOCKED"]


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
    sport: str | None = None
    competition: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    event_start_time: str | None = None
    market_family: str | None = None
    selection: str | None = None
    line: float | None = None
    calibrated_probability: float | None = None
    model_fair_probability: float | None = None
    fair_decimal_odds: float | None = None
    minimum_acceptable_operator_odds: float | None = None
    recommended_minimum_odds: float | None = None
    pricing_status: str = "UNPRICED"
    model_id: str | None = None
    model_card_sha256: str | None = None
    dataset_receipt_sha256: str | None = None
    calibration_report_sha256: str | None = None
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
    manual_verification_required: bool = True
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False

    @model_validator(mode="after")
    def validate_s7b_invariants(self) -> S7bSuperbetManualMappingV1:
        if self.status in ("READY_FOR_MANUAL_MAPPING", "READY"):
            if not self.event_records and self.approved_candidate_count > 0:
                raise ValueError("S7B_INVARIANT_VIOLATION: READY S7b artifact requires non-empty event_records")
            if len(self.mapping_suggestions) != self.approved_candidate_count or len(self.mapping_suggestions) != self.represented_candidate_count:
                raise ValueError("S7B_INVARIANT_VIOLATION: mapping_suggestions count must equal approved_candidate_count and represented_candidate_count")
            rec_eids = {e.canonical_event_id for e in self.event_records}
            for sug in self.mapping_suggestions:
                if rec_eids and sug.canonical_event_id not in rec_eids:
                    raise ValueError(f"S7B_INVARIANT_VIOLATION: suggestion event {sug.canonical_event_id} not in event_records")
                if sug.human_entered_decimal_quote is not None or sug.quote_as_of is not None:
                    raise ValueError("S7B_INVARIANT_VIOLATION: operator-entered fields must be null prior to manual quote entry")
            if not self.manual_verification_required:
                raise ValueError("S7B_INVARIANT_VIOLATION: manual_verification_required must be True for READY S7b artifact")
            if self.executable_coupon or self.betting_valid or self.can_place_bet_now:
                raise ValueError("S7B_INVARIANT_VIOLATION: automated execution flags must be False")
        elif self.status == "NO_ACTION_TERMINAL":
            if self.mapping_suggestions:
                raise ValueError("S7B_INVARIANT_VIOLATION: NO_ACTION_TERMINAL cannot have mapping suggestions")
        return self


class QuoteCardRecordV1(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    canonical_event_id: str
    selection_id: str
    sport: str | None = None
    competition: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    event_start_time: str | None = None
    market_family: str | None = None
    selection: str | None = None
    line: float | None = None
    calibrated_probability: float | None = None
    fair_decimal_odds: float | None = None
    minimum_acceptable_operator_odds: float | None = None
    minimum_acceptable_odds: float | None = None
    pricing_status: str = "UNPRICED"
    model_id: str | None = None
    model_card_sha256: str | None = None
    dataset_receipt_sha256: str | None = None
    calibration_report_sha256: str | None = None
    manual_operator: Literal["SUPERBET"] = "SUPERBET"
    mapping_ambiguity: str | None = "UNAMBIGUOUS"


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
    status: Literal["READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW", "ANALYSIS_ONLY_OUTPUT", "NO_ACTION_TERMINAL", "BLOCK"]
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
    rejections: list[dict[str, Any]] = Field(default_factory=list)
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

    @model_validator(mode="after")
    def validate_s8_invariants(self) -> S8SuperbetManualQuotePackV1:
        if self.status in ("READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW", "READY"):
            if len(self.quote_cards) == 0 and len(self.idea_groups) == 0:
                raise ValueError("S8_INVARIANT_VIOLATION: Zero valid cards/groups must be typed NO_ACTION_TERMINAL or ANALYSIS_ONLY_OUTPUT, not READY")
            if self.quote_card_count != len(self.quote_cards):
                raise ValueError("S8_INVARIANT_VIOLATION: quote_card_count does not match len(quote_cards)")
            rec_eids = {e.canonical_event_id for e in self.event_records}
            for qc in self.quote_cards:
                if rec_eids and qc.canonical_event_id not in rec_eids:
                    raise ValueError(f"S8_INVARIANT_VIOLATION: quote card event {qc.canonical_event_id} not in event_records")
                min_price = qc.minimum_acceptable_operator_odds or qc.minimum_acceptable_odds
                if min_price is None or min_price <= 1.0:
                    raise ValueError("S8_INVARIANT_VIOLATION: READY status requires verified minimum acceptable odds > 1.0 on every quote card")
            for ig in self.idea_groups:
                if ig.minimum_acceptable_odds is not None and ig.minimum_acceptable_odds <= 1.0:
                    raise ValueError("S8_INVARIANT_VIOLATION: idea group minimum_acceptable_odds must be > 1.0")
            if not self.ready_for_human_gate:
                raise ValueError("S8_INVARIANT_VIOLATION: ready_for_human_gate must be True for READY S8 artifact")
            if self.ready_for_production_execution or self.production_selectable or self.production_coupon_write:
                raise ValueError("S8_INVARIANT_VIOLATION: production execution flags must be False")
        elif self.status in ("ANALYSIS_ONLY_OUTPUT", "NO_ACTION_TERMINAL"):
            if self.ready_for_human_gate:
                raise ValueError("S8_INVARIANT_VIOLATION: ready_for_human_gate must be False for ANALYSIS_ONLY_OUTPUT or NO_ACTION_TERMINAL")
            if self.status == "NO_ACTION_TERMINAL" and (self.quote_cards or self.idea_groups):
                raise ValueError("S8_INVARIANT_VIOLATION: NO_ACTION_TERMINAL cannot contain quote cards or idea groups")
        return self
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
