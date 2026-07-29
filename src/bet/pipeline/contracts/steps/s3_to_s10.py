"""Typed candidate contracts for S3 through S10 pipeline steps."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, field_validator, model_validator
from bet.pipeline.contracts.base import StrictBaseModel


class ProbabilityRecordV1(StrictBaseModel):
    canonical_event_id: str
    market_family: str
    selection: str
    calibrated_probability: float | None = Field(default=None, ge=0.0, le=1.0)
    uncertainty_margin: float = Field(default=0.02, ge=0.0)
    model_id: str | None = None
    dataset_receipt_sha256: str | None = None
    calibration_report_sha256: str | None = None
    terminal_status: str = "PASS"


class S3CalibratedProbabilitiesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S3_CALIBRATED_PROBABILITIES"] = "S3_CALIBRATED_PROBABILITIES"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_probabilities_derived: int = Field(ge=0, default=0)
    probabilities: list[ProbabilityRecordV1] = Field(default_factory=list)


class ValuationRecordV1(StrictBaseModel):
    canonical_event_id: str
    market_family: str
    selection: str
    fair_odds: float | None = Field(default=None, ge=1.0)
    ev_estimate: float | None = None
    minimum_acceptable_odds: float | None = Field(default=None, ge=1.0)
    status: str = "PASS"


class S4ExpectedValueEstimatesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S4_EXPECTED_VALUE_ESTIMATES"] = "S4_EXPECTED_VALUE_ESTIMATES"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_candidates_valued: int = Field(ge=0, default=0)
    estimates: list[ValuationRecordV1] = Field(default_factory=list)


class ContextRecordV1(StrictBaseModel):
    canonical_event_id: str
    sport: str
    motivation_score: float = Field(default=1.0, ge=0.0, le=2.0)
    risk_classification: Literal["LOW", "MEDIUM", "HIGH", "UNACCEPTABLE"] = "LOW"
    context_notes: str | None = None
    terminal_status: str = "PASS"


class S5ContextMotivationRiskV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S5_CONTEXT_MOTIVATION_RISK"] = "S5_CONTEXT_MOTIVATION_RISK"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_candidates_screened: int = Field(ge=0, default=0)
    context_records: list[ContextRecordV1] = Field(default_factory=list)


class FilteredCandidateRecordV1(StrictBaseModel):
    canonical_event_id: str
    selection: str
    repeat_risk_flag: bool
    action: str
    terminal_status: str


class S6PortfolioRepeatGuardV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S6_PORTFOLIO_REPEAT_GUARD"] = "S6_PORTFOLIO_REPEAT_GUARD"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_candidates_guarded: int = Field(ge=0, default=0)
    guarded_records: list[FilteredCandidateRecordV1] = Field(default_factory=list)


class S7CandidateRecord(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    selection_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    market_family: str
    selection: str
    line: float | None = None
    manual_operator: str = "SUPERBET"
    mapping_ambiguity: str = "EXACT_NAME_MATCH"
    operator_availability_asserted: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False
    recommended_minimum_odds: float | None = None
    minimum_acceptable_odds: float | None = None
    fair_odds: float | None = None
    model_fair_odds: float | None = None
    model_fair_probability: float | None = None
    calibrated_probability: float | None = None
    model_package_path: str | None = None
    model_package_id: str | None = None


class S7bCandidateRecord(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    selection_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    market_family: str
    selection: str
    line: float | None = None
    manual_operator: str = "SUPERBET"
    mapping_ambiguity: str = "EXACT_NAME_MATCH"
    operator_availability_asserted: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False
    recommended_minimum_odds: float | None = None
    minimum_acceptable_odds: float | None = None
    fair_odds: float | None = None
    model_fair_odds: float | None = None
    model_fair_probability: float | None = None
    calibrated_probability: float | None = None
    model_package_path: str | None = None
    model_package_id: str | None = None


class S8InputCandidateRecord(StrictBaseModel):
    quote_card_id: str
    source_candidate_id: str
    selection_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    market_family: str
    selection: str
    line: float | None = None
    manual_operator: str = "SUPERBET"
    mapping_ambiguity: str = "EXACT_NAME_MATCH"
    operator_availability_asserted: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False
    recommended_minimum_odds: float | None = None
    minimum_acceptable_odds: float | None = None
    fair_odds: float | None = None
    model_fair_odds: float | None = None
    model_fair_probability: float | None = None
    calibrated_probability: float | None = None
    model_package_path: str | None = None
    model_package_id: str | None = None


class S7ApprovedPicksV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S7_APPROVED_PICKS"
    status: str
    betting_day: str
    run_id: str
    event_records: list[dict[str, Any]] = Field(default_factory=list)


class S7bSuperbetManualMappingV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: str = "S7B_SUPERBET_MANUAL_MAPPING"
    status: str
    betting_day: str
    run_id: str
    operator_workflow: str = "SUPERBET_MANUAL_BET_BUILDER"
    source_s7_evidence_path: str | None = None
    source_s7_evidence_sha256: str | None = None
    source_s7_output_path: str | None = None
    source_s7_output_sha256: str | None = None
    approved_candidate_count: int = 0
    represented_candidate_count: int = 0
    mapping_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    event_records: list[dict[str, Any]] = Field(default_factory=list)
    manual_verification_required: bool = False
    operator_availability_asserted: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False


class S8SuperbetManualQuotePackV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: str = "S8_SUPERBET_MANUAL_QUOTE_PACK"
    status: str
    betting_day: str
    run_id: str
    operator_workflow: str = "SUPERBET_MANUAL_BET_BUILDER"
    source_s7b_evidence_path: str | None = None
    source_s7b_evidence_sha256: str | None = None
    source_s7b_output_path: str | None = None
    source_s7b_output_sha256: str | None = None
    quote_card_count: int = 0
    quote_cards: list[dict[str, Any]] = Field(default_factory=list)
    idea_groups: list[dict[str, Any]] = Field(default_factory=list)
    rejections: list[dict[str, Any]] = Field(default_factory=list)
    event_records: list[dict[str, Any]] = Field(default_factory=list)
    analytical_status: str = "NO_ACTION"
    pricing_status: str = "UNPRICED"
    risk_status: str = "NO_ACTION"
    final_status: str = "NO_ACTION_TERMINAL"
    ev_available: bool = False
    kelly_available: bool = False
    stake_available: bool = False
    combined_bookmaker_odds: float | None = None
    requires_human_gate: bool = False
    ready_for_human_gate: bool = False
    ready_for_production_execution: bool = False
    production_selectable: bool = False
    production_coupon_write: bool = False
    executable_coupon: bool = False
    betting_valid: bool = False
    can_place_bet_now: bool = False
    operator_availability_asserted: bool = False
    operator_automation_enabled: bool = False

    @model_validator(mode="after")
    def validate_s8_status_semantics(self) -> S8SuperbetManualQuotePackV1:
        if self.pricing_status == "UNPRICED" and self.executable_coupon:
            raise ValueError("UNPRICED_CANNOT_BE_EXECUTABLE: UNPRICED S8 quote pack cannot be executable coupon")
        if self.pricing_status == "UNPRICED" and (self.ev_available or self.stake_available):
            raise ValueError("UNPRICED_CANNOT_HAVE_EV_OR_STAKE: UNPRICED S8 quote pack cannot have EV or stake available without human quote")
        return self


class S9ExecutedBetsJournalV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S9_HUMAN_OPERATOR_APPROVAL", "S9_EXECUTED_BETS_JOURNAL"] = "S9_HUMAN_OPERATOR_APPROVAL"
    status: str = "HUMAN_APPROVED"
    betting_day: str
    run_id: str
    approved_bets: list[dict[str, Any]] = Field(default_factory=list)


class S10SettlementHandoffV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S10_POSTEVENT_ACCOUNTING", "S10_SETTLEMENT_HANDOFF"] = "S10_POSTEVENT_ACCOUNTING"
    status: str = "PASS"
    betting_day: str
    run_id: str
    settled_bets: list[dict[str, Any]] = Field(default_factory=list)
