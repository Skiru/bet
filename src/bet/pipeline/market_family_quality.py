from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from bet.pipeline.multisport_market_promotion import map_multisport_market


@dataclass(frozen=True)
class MarketReference:
    market_family: str
    human_searchable_market_name: str
    line: Any
    allowed_line_alternatives: list[str]
    line_free_market_type: str | None
    provider_market_refs: list[str]
    selection: str | None
    searchability_score: int
    superbet_availability_status: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_market_family(sport: str, row: Mapping[str, Any]) -> str | None:
    sport_lower = _text(sport).lower()
    mapped = map_multisport_market(sport_lower, row, {})
    if mapped and mapped.get("market_family") != "unknown":
        return mapped["market_family"]

    # Fallback to simple original matching if mapping dictionary is empty/unknown
    family = _text(row.get("market_family")).lower()
    market_type = _text(row.get("market_type")).lower()
    market_name = _text(row.get("market") or row.get("market_label")).lower()
    combined = " ".join(part for part in (family, market_type, market_name) if part)
    if sport_lower == "football":
        if family in {"result", "goals_totals", "corners", "cards", "shots", "shots_on_target"}:
            return family
        if market_type == "draw_no_bet":
            return "result"
        if market_type == "double_chance":
            return "double_chance"
        if "team_goals" in market_type:
            return "team_goals"
    if sport_lower == "tennis":
        if family in {"result", "total_games", "set_handicap", "game_handicap", "aces", "tie_break", "set_betting"}:
            return family
        if market_type in {"winner", "match_winner"} or market_name.startswith("ml:") or "match winner" in combined:
            return "result"
        if "totals_(games)" in combined or "total games" in combined or "games total" in combined or "totals_1st_set" in combined:
            return "total_games"
        if "spread_(games)" in combined or "game handicap" in combined or "games handicap" in combined:
            return "game_handicap"
        if "aces" in combined:
            return "aces"
    if sport_lower == "basketball":
        if family == "result":
            return "result"
        if market_type == "spread":
            return "spread"
        if market_type == "totals":
            return "totals"
        if "team_total" in market_type:
            return "team_totals"
    return None


def build_market_reference(event: Mapping[str, Any], row: Mapping[str, Any]) -> MarketReference | None:
    sport = _text(event.get("sport")).lower()
    mapped = map_multisport_market(sport, row, event)
    if not mapped or mapped.get("promotion_blocker"):
        return None

    line = row.get("line")
    score = 72 if sport == "football" else 45
    if sport == "tennis":
        score = 60
    if sport == "basketball":
        score = 30
    if line not in (None, "", "UNKNOWN"):
        score += 20

    # Ensure selection matches row's normalized value or fallback
    sel = _text(row.get("selection") or row.get("outcome_name") or "Unknown")

    return MarketReference(
        market_family=mapped["market_family"],
        human_searchable_market_name=mapped["human_searchable_market_name"],
        line="NO_NUMERIC_LINE_REQUIRED" if mapped["line_semantics"] == "LINE_FREE" else line,
        allowed_line_alternatives=mapped["allowed_line_alternatives"],
        line_free_market_type=mapped["line_free_market_type"],
        provider_market_refs=mapped["provider_market_refs"],
        selection=sel,
        searchability_score=score,
        superbet_availability_status="MANUAL_SUPERBET_SEARCH_REQUIRED",
    )
