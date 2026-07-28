"""Typed candidate contracts for S7, S7b and S8 pipeline steps."""
from __future__ import annotations

from typing import Any
from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel


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
    mapping_suggestions: list[dict[str, Any]] = Field(default_factory=list)


class S8SuperbetManualQuotePackV1(StrictBaseModel):
    schema_version: int = 2
    artifact_type: str = "S8_SUPERBET_MANUAL_QUOTE_PACK"
    status: str
    betting_day: str
    run_id: str
    operator_workflow: str = "SUPERBET_MANUAL_BET_BUILDER"
    quote_card_count: int = 0
    quote_cards: list[dict[str, Any]] = Field(default_factory=list)
    idea_groups: list[dict[str, Any]] = Field(default_factory=list)
    rejections: list[dict[str, Any]] = Field(default_factory=list)
    event_records: list[dict[str, Any]] = Field(default_factory=list)
    analytical_status: str = "NO_ACTION"
    pricing_status: str = "UNPRICED"
    requires_human_gate: bool = False
    ready_for_human_gate: bool = False
