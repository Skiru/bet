"""Market-specific evidence sufficiency and quality grading for the betting pipeline.

Delegates to the programmatic GLOBAL_SPORT_PROTOCOL_REGISTRY for all 8 sports.
"""
from __future__ import annotations

from typing import Any, Mapping
from src.bet.pipeline.sports.registry import GLOBAL_SPORT_PROTOCOL_REGISTRY


def evaluate_evidence_sufficiency(
    sport: str,
    market_family: str,
    event: Mapping[str, Any],
    row: Mapping[str, Any],
    evidence_pack: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Evaluates the evidence sufficiency for a given event and market row using registered sport protocols.

    Returns:
        tuple[str, list[str]]: (Quality grade "HIGH"/"MEDIUM"/"LOW"/"UNKNOWN", list of blockers/reasons)
    """
    sport_name = str(sport or event.get("sport") or "football").lower()
    protocol = GLOBAL_SPORT_PROTOCOL_REGISTRY.get(sport_name)

    canonical_event_id = str(event.get("canonical_event_id") or event.get("event_id") or "UNKNOWN")

    if protocol is None:
        # Fallback for unknown sport
        return "UNKNOWN", ["UNSUPPORTED_SPORT"]

    decision = protocol.evaluate_market_readiness(
        canonical_event_id=canonical_event_id,
        market_family=market_family,
        event_data=event,
        row_data=row,
        evidence_pack=evidence_pack,
    )

    blockers = list(decision.missing_requirements) + list(decision.reason_codes)
    return decision.quality_grade, blockers
