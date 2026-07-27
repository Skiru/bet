"""Business contracts for ANALYSIS_BUILD, EXECUTION, and POST_EVENT steps (S3 to S10)."""
from __future__ import annotations

from typing import Any
from pydantic import Field
from src.bet.pipeline.contracts.base import StrictBaseModel


# S3 Contract
class S3CalibratedProbabilitiesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S3_CALIBRATED_PROBABILITIES"
    status: str = "PASS"
    betting_day: str
    run_id: str
    probabilities_count: int = Field(ge=0, default=0)
    probability_estimates: list[dict[str, Any]] = Field(default_factory=list)


# S4 Contract
class S4ExpectedValueEstimatesV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S4_EXPECTED_VALUE_ESTIMATES"
    status: str = "PASS"
    betting_day: str
    run_id: str
    candidates_valuated_count: int = Field(ge=0, default=0)
    valuation_candidates: list[dict[str, Any]] = Field(default_factory=list)


# S5 Contract
class S5ContextMotivationRiskV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S5_CONTEXT_MOTIVATION_RISK"
    status: str = "PASS"
    betting_day: str
    run_id: str
    events_reviewed_count: int = Field(ge=0, default=0)
    context_reviews: list[dict[str, Any]] = Field(default_factory=list)


# S6 Contract
class S6PortfolioRepeatGuardV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S6_PORTFOLIO_REPEAT_GUARD"
    status: str = "PASS"
    betting_day: str
    run_id: str
    repeats_filtered_count: int = Field(ge=0, default=0)
    filtered_candidates: list[dict[str, Any]] = Field(default_factory=list)


# S7 Contract
class S7ApprovedPicksV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S7_APPROVED_PICKS"
    status: str = "PASS"  # PASS | NO_ACTION_TERMINAL
    betting_day: str
    run_id: str
    approved_candidate_count: int = Field(ge=0, default=0)
    approved_picks: list[dict[str, Any]] = Field(default_factory=list)


# S7b Contract
class S7bSuperbetManualMappingV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: str = "S7B_SUPERBET_MANUAL_MAPPING"
    status: str = "READY_FOR_MANUAL_MAPPING"  # READY_FOR_MANUAL_MAPPING | NO_ACTION_TERMINAL
    betting_day: str
    run_id: str
    operator_workflow: str = "SUPERBET_MANUAL_BET_BUILDER"
    operator_availability_asserted: bool = False
    approved_candidate_count: int = Field(ge=0, default=0)
    represented_candidate_count: int = Field(ge=0, default=0)
    mapping_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    event_records: list[dict[str, Any]] = Field(default_factory=list)


# S8 Contract
class S8SuperbetManualQuotePackV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: str = "S8_SUPERBET_MANUAL_QUOTE_PACK"
    status: str = "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW"  # READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW | NO_ACTION_TERMINAL
    betting_day: str
    run_id: str
    operator_workflow: str = "SUPERBET_MANUAL_BET_BUILDER"
    source_s7b_evidence_path: str | None = None
    source_s7b_evidence_sha256: str | None = None
    source_s7b_output_path: str | None = None
    source_s7b_output_sha256: str | None = None
    quote_card_count: int = Field(ge=0, default=0)
    quote_cards: list[dict[str, Any]] = Field(default_factory=list)
    idea_groups: list[dict[str, Any]] = Field(default_factory=list)
    event_records: list[dict[str, Any]] = Field(default_factory=list)
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


# S9 Contract
class S9ExecutedBetsJournalV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S9_EXECUTED_BETS_JOURNAL"
    status: str = "EXECUTED"  # EXECUTED | NO_BET | REJECTED
    betting_day: str
    run_id: str
    human_operator_verified: bool = True
    executed_bets: list[dict[str, Any]] = Field(default_factory=list)


# S10 Contract
class S10SettlementHandoffV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S10_SETTLEMENT_HANDOFF"
    status: str = "PASS"
    betting_day: str
    run_id: str
    post_session_learning_records: list[dict[str, Any]] = Field(default_factory=list)
