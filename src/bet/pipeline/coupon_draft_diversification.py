"""Coupon draft diversification helpers.

The helpers only build non-bettable review drafts.  They never compute odds and
never promote a coupon to final/bettable status.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

_ALLOWED_CARD_STATUSES = {"QUOTE_REVIEW_ONLY", "READY_FOR_MANUAL_OPERATOR_QUOTE_REVIEW"}


def quote_card_key(card: Mapping[str, Any]) -> tuple[Any, ...]:
    line = card.get("line")
    if line in (None, "", "UNKNOWN"):
        line = card.get("line_free_market_type") or tuple(card.get("allowed_line_alternatives") or []) or card.get("line_unknown_reason")
    return (
        card.get("event_id"),
        card.get("sport"),
        card.get("market_family"),
        card.get("selection") or card.get("human_searchable_market_name"),
        line,
    )


def eligible_quote_cards(quote_cards: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[Mapping[str, Any]] = []
    for card in quote_cards:
        if card.get("bettable") is True:
            continue
        if card.get("combined_bookmaker_odds_computed") not in (False, None):
            continue
        if card.get("final_status") not in _ALLOWED_CARD_STATUSES:
            continue
        if not card.get("quote_card_id") or not card.get("candidate_id") or not card.get("event_id") or not card.get("sport"):
            continue
        key = quote_card_key(card)
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out


def build_diversified_coupon_draft(
    quote_cards: Sequence[Mapping[str, Any]],
    *,
    draft_id: str,
    max_legs: int,
    min_sports: int = 2,
    style: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic, non-bettable, round-robin diversified draft."""
    by_sport: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for card in eligible_quote_cards(quote_cards):
        by_sport[str(card.get("sport"))].append(card)

    legs: list[dict[str, Any]] = []
    # Prefer sport diversity first, then depth.  Sort by sport count descending to
    # avoid starving strong sports, but round-robin to prevent football-only drafts.
    sports = sorted(by_sport, key=lambda sport: (-len(by_sport[sport]), sport))
    while len(legs) < max_legs and any(by_sport.values()):
        progressed = False
        for sport in list(sports):
            if len(legs) >= max_legs:
                break
            bucket = by_sport.get(sport) or []
            if not bucket:
                continue
            card = bucket.pop(0)
            legs.append({
                "quote_card_id": card.get("quote_card_id"),
                "candidate_id": card.get("candidate_id"),
                "event_id": card.get("event_id"),
                "sport": card.get("sport"),
                "competition": card.get("competition"),
                "human_searchable_market_name": card.get("human_searchable_market_name"),
                "manual_quote_required": True,
            })
            progressed = True
        if not progressed:
            break

    leg_sports = {str(leg.get("sport")) for leg in legs if leg.get("sport")}
    diversification_blocker = None
    if len(legs) >= 3 and len(leg_sports) < min_sports:
        diversification_blocker = "INSUFFICIENT_QUOTE_QUALITY_CARDS_OUTSIDE_PRIMARY_SPORT"

    return {
        "coupon_draft_id": draft_id,
        "style": style or draft_id,
        "legs": legs,
        "max_legs": max_legs,
        "sports_count": len(leg_sports),
        "sport_diversification": sorted(leg_sports),
        "combined_odds": None,
        "bettable": False,
        "status": "DRAFT_REQUIRES_HUMAN_QUOTES",
        "diversification_blocker": diversification_blocker,
        "required_manual_odds_fields": [
            "operator",
            "visible_event",
            "visible_market",
            "line",
            "decimal_odds",
            "captured_at",
            "quote_source",
            "visible_bet_builder_combined_odds",
        ],
    }
