"""Downstream decision readiness and match resolution for tipster evidence."""
from __future__ import annotations

import re
from typing import Any
from .contracts import TipsterPick
from .normalization import normalize_key, clean_team_name

ALLOWED_DECISION_LABELS = {
    "USE_AS_CONTEXT",
    "USE_AS_MARKET_SANITY_CHECK",
    "USE_AS_QUALITATIVE_REASONING",
    "USE_AS_TIPSTER_SENTIMENT",
    "NEEDS_MATCH_ID_RESOLUTION",
    "NEEDS_MANUAL_REVIEW",
    "REJECT_GARBAGE",
    "REJECT_DUPLICATE",
    "REJECT_LOW_QUALITY",
}

FORBIDDEN_ACTIONS = [
    "EV",
    "stake",
    "coupon",
    "final bet",
    "Superbet combined odds",
]

ALLOWED_PIPELINE_STAGES = [
    "S3 contextual cross-check",
    "S4 market sanity",
    "manual Superbet quote review",
]


def split_participants(event: str, sport: str) -> list[str]:
    """Sport-aware participant splitting with Polish character preservation."""
    event = event.strip()
    if not event:
        return []

    # Try typical vs delimiters first (order-insensitive)
    for sep in (r"\s+vs\.?\s+", r"\s+v\.?\s+"):
        parts = re.split(sep, event, flags=re.IGNORECASE)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return [clean_team_name(parts[0]), clean_team_name(parts[1])]

    # Try dash/hyphen delimiters
    for sep in (r"\s+[-–—]\s+", r"\s*[-–—]\s*"):
        parts = re.split(sep, event, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return [clean_team_name(parts[0]), clean_team_name(parts[1])]

    return [clean_team_name(event)]


def generate_event_identity(event: str, sport: str) -> dict[str, Any]:
    """Generate sport-aware order-insensitive event identity and resolution metadata."""
    participants = split_participants(event, sport)

    requires_match_resolution = False
    ambiguity_flags = []

    if len(participants) != 2:
        requires_match_resolution = True
        ambiguity_flags.append("ambiguous_split")

    cleaned_participants = [clean_team_name(p) for p in participants]

    # Generate order-insensitive key
    sorted_norms = sorted(normalize_key(p) for p in cleaned_participants)
    normalized_event_key = "|".join(sorted_norms) if sorted_norms else normalize_key(event)

    # Check if original event order is reversed compared to alphabetical order
    if len(cleaned_participants) == 2:
        original_norms = [normalize_key(p) for p in cleaned_participants]
        if original_norms != sorted_norms:
            ambiguity_flags.append("order_reversed")

    return {
        "normalized_event_key": normalized_event_key,
        "participants": cleaned_participants,
        "requires_match_resolution": requires_match_resolution,
        "ambiguity_flags": ambiguity_flags,
    }


def analyze_pick_readiness(pick: TipsterPick) -> dict[str, Any]:
    """Downstream agent decision and match identity readiness evaluation."""
    warnings = pick.warnings or []
    reasoning = pick.reasoning or ""

    identity = generate_event_identity(pick.event, pick.sport)

    # 1. Determine decision label based on quality and completeness
    agent_use_decision = "USE_AS_CONTEXT"
    decision_reason = "Fully compliant public tipster evidence with reference odds."
    confidence_in_extraction = "HIGH"

    # Detect low quality or garbage
    is_garbage = False
    low_event = pick.event.lower()
    if not pick.event or any(spam in low_event for spam in ["zawód typer", "zawod typer", "promo", "cookie", "rules"]):
        is_garbage = True
        agent_use_decision = "REJECT_GARBAGE"
        decision_reason = "Event name matches known promotional, metadata or garbage pattern."
        confidence_in_extraction = "LOW"
    elif pick.extraction_quality < 0.45:
        agent_use_decision = "REJECT_LOW_QUALITY"
        decision_reason = f"Extraction quality ({pick.extraction_quality}) is below acceptable contract threshold (0.45)."
        confidence_in_extraction = "LOW"
    elif not reasoning or len(reasoning) < 30:
        agent_use_decision = "NEEDS_MANUAL_REVIEW"
        decision_reason = "Evidence has empty or extremely brief qualitative reasoning."
        confidence_in_extraction = "MEDIUM"
    elif identity["requires_match_resolution"]:
        agent_use_decision = "NEEDS_MATCH_ID_RESOLUTION"
        decision_reason = "Fixture split is ambiguous or could not be confidently resolved."
        confidence_in_extraction = "MEDIUM"
    elif "order_reversed" in identity["ambiguity_flags"]:
        agent_use_decision = "USE_AS_CONTEXT"
        decision_reason = "Compliant evidence, but team order is reversed compared to canonical alphabetical key."
        confidence_in_extraction = "HIGH"

    can_influence_pipeline = agent_use_decision in {
        "USE_AS_CONTEXT",
        "USE_AS_MARKET_SANITY_CHECK",
        "USE_AS_QUALITATIVE_REASONING",
        "USE_AS_TIPSTER_SENTIMENT",
    }

    return {
        "source_id": pick.source_id,
        "event": pick.event,
        "market": pick.market,
        "agent_use_decision": agent_use_decision,
        "decision_reason": decision_reason,
        "confidence_in_extraction": confidence_in_extraction,
        "can_influence_pipeline": can_influence_pipeline,
        "allowed_pipeline_stages": ALLOWED_PIPELINE_STAGES if can_influence_pipeline else [],
        "forbidden_actions": FORBIDDEN_ACTIONS,
        **identity,
    }
