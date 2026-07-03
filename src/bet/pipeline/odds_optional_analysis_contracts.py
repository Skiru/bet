from __future__ import annotations

from enum import StrEnum
from typing import Any


class OddsStatus(StrEnum):
    PRICED = "PRICED"
    PARTIALLY_PRICED = "PARTIALLY_PRICED"
    UNPRICED = "UNPRICED"
    PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
    OPERATOR_SCREEN_ONLY = "OPERATOR_SCREEN_ONLY"
    UNKNOWN = "UNKNOWN"


class PricingTier(StrEnum):
    PRICED_ANALYTICAL = "PRICED_ANALYTICAL"
    PARTIALLY_PRICED_ANALYTICAL = "PARTIALLY_PRICED_ANALYTICAL"
    UNPRICED_DEEP_ANALYTICAL = "UNPRICED_DEEP_ANALYTICAL"
    OPERATOR_QUOTE_REQUIRED_FOR_BETTABLE = "OPERATOR_QUOTE_REQUIRED_FOR_BETTABLE"


class AnalysisStatus(StrEnum):
    ANALYTICAL_RECOMMENDATION = "ANALYTICAL_RECOMMENDATION"
    READY_FOR_OPTIONAL_OPERATOR_QUOTE_CHECK = "READY_FOR_OPTIONAL_OPERATOR_QUOTE_CHECK"
    WATCH = "WATCH"
    REJECTED = "REJECTED"


class EvStatus(StrEnum):
    EV_AVAILABLE = "EV_AVAILABLE"
    EV_BLOCKED_UNTIL_OPERATOR_ODDS = "EV_BLOCKED_UNTIL_OPERATOR_ODDS"
    EV_NOT_CALCULABLE = "EV_NOT_CALCULABLE"
    EV_NOT_REQUIRED_FOR_ANALYSIS = "EV_NOT_REQUIRED_FOR_ANALYSIS"


class StakeStatus(StrEnum):
    STAKE_BLOCKED_UNTIL_PRICE_GATE = "STAKE_BLOCKED_UNTIL_PRICE_GATE"
    STAKE_NOT_APPLICABLE_TO_ANALYSIS = "STAKE_NOT_APPLICABLE_TO_ANALYSIS"
    STAKE_ALLOWED_AFTER_PRICE_GATE_ONLY = "STAKE_ALLOWED_AFTER_PRICE_GATE_ONLY"


class BettableStatus(StrEnum):
    NOT_BETTABLE_ANALYSIS_ONLY = "NOT_BETTABLE_ANALYSIS_ONLY"
    NOT_BETTABLE_WAITING_FOR_OPERATOR_ODDS = "NOT_BETTABLE_WAITING_FOR_OPERATOR_ODDS"
    NOT_BETTABLE_PRICE_GATE_FAILED = "NOT_BETTABLE_PRICE_GATE_FAILED"
    BETTABLE_AFTER_HUMAN_ODDS_ONLY = "BETTABLE_AFTER_HUMAN_ODDS_ONLY"


class OptionalOperatorQuotePriority(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOT_NEEDED_NOW = "NOT_NEEDED_NOW"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def has_exact_human_odds(candidate: dict[str, Any] | Any) -> bool:
    if not isinstance(candidate, dict):
        return False
    quote = candidate.get("human_entered_quote")
    if isinstance(quote, dict) and quote.get("decimal_odds") not in (None, ""):
        return True
    manual = candidate.get("manual_superbet_quote_fields")
    return isinstance(manual, dict) and manual.get("decimal_odds") not in (None, "")


def derive_odds_status(
    *,
    has_human_odds: bool,
    provider_odds_present: bool,
    line_source_status: str,
    provider_blocked: bool = False,
    operator_screen_only: bool = False,
) -> OddsStatus:
    if operator_screen_only:
        return OddsStatus.OPERATOR_SCREEN_ONLY
    if has_human_odds:
        return OddsStatus.PRICED
    if provider_blocked:
        return OddsStatus.PROVIDER_BLOCKED
    if not provider_odds_present:
        return OddsStatus.UNPRICED
    if _text(line_source_status).upper() in {
        "LINE_REQUIRES_OPERATOR_CHECK",
        "ALTERNATIVE_LINES_ONLY",
        "UNKNOWN",
    }:
        return OddsStatus.UNPRICED
    return OddsStatus.PARTIALLY_PRICED


def derive_pricing_tier(odds_status: OddsStatus | str) -> PricingTier:
    status = _text(odds_status).upper()
    if status == OddsStatus.PRICED.value:
        return PricingTier.PRICED_ANALYTICAL
    if status == OddsStatus.PARTIALLY_PRICED.value:
        return PricingTier.PARTIALLY_PRICED_ANALYTICAL
    return PricingTier.UNPRICED_DEEP_ANALYTICAL


def derive_analysis_status(
    *,
    confidence: str,
    data_quality: str,
    odds_status: OddsStatus | str,
    optional_quote_priority: OptionalOperatorQuotePriority | str,
) -> AnalysisStatus:
    confidence_text = _text(confidence).upper()
    quality_text = _text(data_quality).upper()
    priority_text = _text(optional_quote_priority).upper()
    if confidence_text in {"LOW", "UNKNOWN"} and quality_text in {"LOW", "UNKNOWN"}:
        return AnalysisStatus.WATCH
    if priority_text in {
        OptionalOperatorQuotePriority.HIGH.value,
        OptionalOperatorQuotePriority.MEDIUM.value,
    } and _text(odds_status).upper() in {
        OddsStatus.PRICED.value,
        OddsStatus.PARTIALLY_PRICED.value,
    }:
        return AnalysisStatus.READY_FOR_OPTIONAL_OPERATOR_QUOTE_CHECK
    return AnalysisStatus.ANALYTICAL_RECOMMENDATION


def derive_ev_status(
    *,
    fair_odds: Any,
    has_human_odds: bool,
    bettable: bool = False,
) -> EvStatus:
    if fair_odds in (None, ""):
        return EvStatus.EV_BLOCKED_UNTIL_OPERATOR_ODDS if not has_human_odds else EvStatus.EV_NOT_CALCULABLE
    if has_human_odds and bettable:
        return EvStatus.EV_AVAILABLE
    return EvStatus.EV_BLOCKED_UNTIL_OPERATOR_ODDS


def derive_stake_status(*, has_human_odds: bool, bettable: bool = False) -> StakeStatus:
    if has_human_odds and bettable:
        return StakeStatus.STAKE_ALLOWED_AFTER_PRICE_GATE_ONLY
    return StakeStatus.STAKE_BLOCKED_UNTIL_PRICE_GATE


def derive_bettable_status(
    *,
    odds_status: OddsStatus | str,
    has_human_odds: bool,
    price_gate_passed: bool = False,
) -> BettableStatus:
    if has_human_odds and price_gate_passed:
        return BettableStatus.BETTABLE_AFTER_HUMAN_ODDS_ONLY
    if has_human_odds and not price_gate_passed:
        return BettableStatus.NOT_BETTABLE_PRICE_GATE_FAILED
    if _text(odds_status).upper() in {OddsStatus.PRICED.value, OddsStatus.PARTIALLY_PRICED.value}:
        return BettableStatus.NOT_BETTABLE_WAITING_FOR_OPERATOR_ODDS
    return BettableStatus.NOT_BETTABLE_ANALYSIS_ONLY


def derive_optional_quote_priority(*, confidence: str, line_sensitivity: str, odds_status: OddsStatus | str) -> OptionalOperatorQuotePriority:
    confidence_text = _text(confidence).upper()
    line_text = _text(line_sensitivity).upper()
    status_text = _text(odds_status).upper()
    if status_text == OddsStatus.PRICED.value:
        return OptionalOperatorQuotePriority.HIGH
    if status_text == OddsStatus.PARTIALLY_PRICED.value and confidence_text in {"HIGH", "MEDIUM"}:
        return OptionalOperatorQuotePriority.HIGH if line_text == "HIGH" else OptionalOperatorQuotePriority.MEDIUM
    if status_text == OddsStatus.UNPRICED.value and confidence_text in {"HIGH", "MEDIUM"}:
        return OptionalOperatorQuotePriority.MEDIUM if line_text == "HIGH" else OptionalOperatorQuotePriority.LOW
    return OptionalOperatorQuotePriority.NOT_NEEDED_NOW
