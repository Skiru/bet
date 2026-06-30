"""Typed contracts and schema validators for unpriced Bet Builder analytical candidate path."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class UnpricedBetBuilderAnalyticalCandidate:
    candidate_id: str
    event_id: str
    sport: str
    competition: str
    participants: List[str]
    bet_builder_legs: List[Dict[str, Any]]
    preferred_lines: List[Any]
    alternative_lines: List[Any]
    model_probability: Decimal
    fair_odds: Decimal
    min_acceptable_operator_odds: Decimal
    confidence_label: str
    evidence_pack: List[Dict[str, Any]]
    counter_evidence: List[Dict[str, Any]]
    source_gaps: List[Dict[str, Any]]
    correlation_risk: str
    scenario_summary: str
    operator_market_required: bool = True
    operator_quote_required: bool = True
    operator_line_required: bool = True
    operator_timestamp_required: bool = True
    combined_bookmaker_odds_computed: bool = False
    status: str = "PRICE_PENDING_OPERATOR_CHECK"

    def __post_init__(self):
        # Convert numeric fields to Decimal
        if not isinstance(self.model_probability, Decimal):
            self.model_probability = Decimal(str(self.model_probability))
        if not isinstance(self.fair_odds, Decimal):
            self.fair_odds = Decimal(str(self.fair_odds))
        if not isinstance(self.min_acceptable_operator_odds, Decimal):
            self.min_acceptable_operator_odds = Decimal(str(self.min_acceptable_operator_odds))

        # Probability validation
        if self.model_probability <= Decimal("0") or self.model_probability >= Decimal("1"):
            raise ValueError("model_probability must be > 0 and < 1")

        # Fair odds validation (must be 1 / probability, rounded to 4 decimals)
        expected_fair_odds = (Decimal("1") / self.model_probability).quantize(Decimal("0.0001"))
        if abs(self.fair_odds - expected_fair_odds) > Decimal("0.01"):
            raise ValueError(f"fair_odds {self.fair_odds} is not derived from model_probability {self.model_probability} (expected ~{expected_fair_odds})")

        # Min acceptable odds validation
        margin_multipliers = {
            "HIGH": Decimal("1.05"),
            "MEDIUM": Decimal("1.08"),
            "LOW": Decimal("1.12")
        }
        mult = margin_multipliers.get(self.confidence_label.upper(), Decimal("1.08"))
        expected_min_acceptable = (self.fair_odds * mult).quantize(Decimal("0.0001"))
        if abs(self.min_acceptable_operator_odds - expected_min_acceptable) > Decimal("0.01"):
            raise ValueError(f"min_acceptable_operator_odds {self.min_acceptable_operator_odds} is not derived correctly (expected ~{expected_min_acceptable})")


@dataclass
class ManualSuperbetOperatorQuote:
    candidate_id: str
    operator: str
    market_label: str
    line: str
    odds_decimal: Decimal
    combined_odds_decimal: Decimal
    as_of_utc: str
    entered_by_human: bool = True
    computed_by_pipeline: bool = False
    screenshot_reference_optional: Optional[str] = None
    quote_status: str = "QUOTE_ENTERED"

    def __post_init__(self):
        if not isinstance(self.odds_decimal, Decimal):
            self.odds_decimal = Decimal(str(self.odds_decimal))
        if not isinstance(self.combined_odds_decimal, Decimal):
            self.combined_odds_decimal = Decimal(str(self.combined_odds_decimal))

        if not self.entered_by_human:
            raise ValueError("no operator quote can have entered_by_human=False")
        if self.computed_by_pipeline:
            raise ValueError("no quote can have computed_by_pipeline=True")


@dataclass
class ManualQuoteDecision:
    candidate_id: str
    min_acceptable_operator_odds: Decimal
    actual_operator_odds: Decimal
    actual_operator_line: str
    decision: str  # BETTABLE_MANUAL_ONLY | REJECTED_BY_PRICE | LINE_MISMATCH_REQUIRES_REMODEL | NO_OPERATOR_MARKET_FOUND | PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW
    reason: str

    def __post_init__(self):
        if not isinstance(self.min_acceptable_operator_odds, Decimal):
            self.min_acceptable_operator_odds = Decimal(str(self.min_acceptable_operator_odds))
        if not isinstance(self.actual_operator_odds, Decimal):
            self.actual_operator_odds = Decimal(str(self.actual_operator_odds))


@dataclass
class BetBuilderReadinessReport:
    ready_for_manual_operator_quote_review: bool
    ready_for_manual_placement: bool
    ready_for_production_execution: bool
    ready_for_automated_bet_placement: bool
    status: str
    blockers: List[str] = field(default_factory=list)


def validate_no_multiplied_leg_odds(legs_odds: List[Decimal], combined_odds: Decimal) -> None:
    """Ensure combined odds is not a simple multiplication of leg odds."""
    if len(legs_odds) > 1:
        product = Decimal("1")
        for odd in legs_odds:
            product *= odd
        if abs(combined_odds - product) < Decimal("0.0001"):
            raise ValueError("no Bet Builder combined odds can be synthesized by multiplying leg odds")
