from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping, Sequence


class BetBuilderConceptType(StrEnum):
    CORNERS_CARDS_GOALS = "CORNERS_CARDS_GOALS"
    SHOTS_GOALS = "SHOTS_GOALS"
    CARDS_CORNERS = "CARDS_CORNERS"
    TENNIS_GAMES_SETS = "TENNIS_GAMES_SETS"
    BASKETBALL_SPREAD_TOTAL = "BASKETBALL_SPREAD_TOTAL"
    ESPORTS_MAPS = "ESPORTS_MAPS"
    OTHER = "OTHER"


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def infer_concept_type(sport: str, legs: Sequence[Mapping[str, Any]]) -> BetBuilderConceptType:
    sport_text = _text(sport).lower()
    families = {_text(leg.get("market_family")).lower() for leg in legs}
    if sport_text == "tennis":
        return BetBuilderConceptType.TENNIS_GAMES_SETS
    if sport_text == "basketball":
        return BetBuilderConceptType.BASKETBALL_SPREAD_TOTAL
    if sport_text in {"cs2", "valorant", "dota2", "esports"}:
        return BetBuilderConceptType.ESPORTS_MAPS
    if {"cards", "corners"}.issubset(families):
        return BetBuilderConceptType.CARDS_CORNERS
    if "shots" in families and ({"goals_totals", "team_goals", "result"} & families):
        return BetBuilderConceptType.SHOTS_GOALS
    if families & {"corners", "cards", "goals_totals", "team_goals", "result"}:
        return BetBuilderConceptType.CORNERS_CARDS_GOALS
    return BetBuilderConceptType.OTHER


def validate_bet_builder_concept(concept: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if concept.get("combined_odds_status") != "OPERATOR_SCREEN_ONLY":
        errors.append("combined_odds_status_must_be_operator_screen_only")
    if concept.get("combined_bookmaker_odds_computed") is not False:
        errors.append("combined_bookmaker_odds_computed_must_be_false")
    if concept.get("bettable") is not False:
        errors.append("bet_builder_concept_must_not_be_bettable")
    legs = concept.get("legs") or []
    if not isinstance(legs, Sequence) or isinstance(legs, (str, bytes)) or not legs:
        errors.append("bet_builder_concept_requires_legs")
    return errors
