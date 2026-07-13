"""Independent analytical, pricing, risk, and final status classification."""
from __future__ import annotations

from typing import Any


def has_explicit_test_provenance(payload: dict[str, Any]) -> bool:
    provenance = payload.get("provenance")
    return isinstance(provenance, dict) and provenance.get("kind") in {"TEST_FIXTURE", "CERTIFICATION_FIXTURE"}


def classify_candidate_status(
    *,
    analysis_ready: bool,
    model_probability: float | None,
    human_operator_odds: float | None,
    risk_approved: bool | None,
) -> dict[str, Any]:
    analytical_status = "ANALYTICAL_READY" if analysis_ready and model_probability is not None else "ANALYSIS_BLOCKED"
    has_real_price = human_operator_odds is not None and human_operator_odds > 1.0
    pricing_status = "PRICED_HUMAN_OPERATOR" if has_real_price else "PRICE_PENDING_OPERATOR_QUOTE"
    risk_status = "RISK_APPROVED" if risk_approved is True else ("RISK_REJECTED" if risk_approved is False else "RISK_PENDING")
    bettable = analytical_status == "ANALYTICAL_READY" and has_real_price and risk_status == "RISK_APPROVED"
    return {
        "analytical_status": analytical_status,
        "pricing_status": pricing_status,
        "risk_status": risk_status,
        "final_status": "BETTABLE_PENDING_HUMAN_S9" if bettable else "NOT_BETTABLE",
        "ev_available": bettable,
        "kelly_available": bettable,
        "stake_available": bettable,
        "executable_coupon": False,
        "can_place_bet_now": False,
    }
