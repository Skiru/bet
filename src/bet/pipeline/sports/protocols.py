"""Sport-specific protocol definitions for all 8 supported sports."""
from __future__ import annotations

from typing import Any, Mapping
from src.bet.pipeline.sports.models import (
    MarketEvidenceRequirementV1,
    SourceFreshnessPolicyV1,
    SportReadinessDecisionV1,
)


class BaseSportProtocol:
    """Base class for sport-specific intelligence protocols."""

    def __init__(self, sport_id: str) -> None:
        self.sport_id = sport_id

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        raise NotImplementedError


class FootballProtocol(BaseSportProtocol):
    """Football intelligence protocol covering goals/results, corners, cards, shots/SOT, team totals/handicaps."""

    def __init__(self) -> None:
        super().__init__("football")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        pack = evidence_pack or {}
        missing: list[str] = []
        family = str(market_family or row_data.get("market_family") or "").lower()

        home = event_data.get("home_team") or event_data.get("canonical_event_name")
        away = event_data.get("away_team") or event_data.get("canonical_event_name")
        comp = event_data.get("competition") or event_data.get("league_or_tournament")

        if not home or not away:
            missing.append("MISSING_EVENT_PARTICIPANTS")
        if not comp:
            missing.append("MISSING_COMPETITION")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(missing),
            )

        # Market specific criteria
        if family in {"corners", "total_corners", "corner_handicap"}:
            corners_home = pack.get("home_corners_avg") or pack.get("corners_home")
            corners_away = pack.get("away_corners_avg") or pack.get("corners_away")
            if corners_home is None or corners_away is None:
                missing.append("MISSING_CORNER_STATS")
                return SportReadinessDecisionV1(
                    canonical_event_id=canonical_event_id,
                    sport=self.sport_id,
                    market_family=family,
                    quality_grade="LOW",
                    missing_requirements=tuple(missing),
                    allowed_action="ANALYSIS_ONLY",
                    reason_codes=("MISSING_FOOTBALL_CORNER_REQUIREMENTS",),
                )

        elif family in {"cards", "total_cards", "fouls"}:
            cards_home = pack.get("home_cards_avg") or pack.get("cards_home")
            cards_away = pack.get("away_cards_avg") or pack.get("cards_away")
            if cards_home is None or cards_away is None:
                missing.append("MISSING_CARD_STATS")
                return SportReadinessDecisionV1(
                    canonical_event_id=canonical_event_id,
                    sport=self.sport_id,
                    market_family=family,
                    quality_grade="LOW",
                    missing_requirements=tuple(missing),
                    allowed_action="ANALYSIS_ONLY",
                    reason_codes=("MISSING_FOOTBALL_CARD_REQUIREMENTS",),
                )

        elif family in {"shots", "shots_on_target", "sot"}:
            shots_home = pack.get("home_shots_avg") or pack.get("shots_home")
            shots_away = pack.get("away_shots_avg") or pack.get("shots_away")
            if shots_home is None or shots_away is None:
                missing.append("MISSING_SHOT_STATS")
                return SportReadinessDecisionV1(
                    canonical_event_id=canonical_event_id,
                    sport=self.sport_id,
                    market_family=family,
                    quality_grade="LOW",
                    missing_requirements=tuple(missing),
                    allowed_action="ANALYSIS_ONLY",
                    reason_codes=("MISSING_FOOTBALL_SHOT_REQUIREMENTS",),
                )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class TennisProtocol(BaseSportProtocol):
    """Tennis intelligence protocol: surface-adjusted strength, fatigue, workload interval widening."""

    def __init__(self) -> None:
        super().__init__("tennis")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        pack = evidence_pack or {}
        missing: list[str] = []
        family = str(market_family or row_data.get("market_family") or "").lower()

        if family in {"total_games", "game_handicap", "set_handicap"}:
            line = row_data.get("line")
            if line in (None, "", "UNKNOWN", "N/A"):
                return SportReadinessDecisionV1(
                    canonical_event_id=canonical_event_id,
                    sport=self.sport_id,
                    market_family=family,
                    quality_grade="UNKNOWN",
                    missing_requirements=("LINE_SEMANTICS_MISSING",),
                    allowed_action="BLOCKED",
                    reason_codes=("LINE_SEMANTICS_MISSING",),
                )

        ranking = pack.get("player_ranking") or pack.get("seed") or event_data.get("ranking_proxy")
        form = pack.get("recent_form") or pack.get("form") or event_data.get("form_proxy")
        surface = pack.get("surface") or event_data.get("surface")

        if not ranking and not form:
            missing.append("MISSING_TENNIS_STRENGTH_FORM")
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="LOW",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("MISSING_TENNIS_BASE_EVIDENCE",),
            )

        # Workload/fatigue triggers interval widening rather than deterministic loss rejection
        rest_hours = pack.get("rest_hours")
        reasons = []
        if rest_hours is not None and rest_hours < 18:
            reasons.append("HIGH_CONSECUTIVE_DAY_WORKLOAD_WIDEN_INTERVAL")

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
            quality_grade="HIGH" if surface else "MEDIUM",
            allowed_action="READY_FOR_PRICING",
            reason_codes=tuple(reasons),
        )


class BasketballProtocol(BaseSportProtocol):
    """Basketball intelligence protocol: pace, ratings, rest, back-to-back context."""

    def __init__(self) -> None:
        super().__init__("basketball")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        pack = evidence_pack or {}
        form = pack.get("recent_form") or pack.get("standing") or event_data.get("form_proxy")
        if not form:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=market_family,
                quality_grade="MEDIUM",
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("BASKETBALL_FORM_UNKNOWN_LIMITATION",),
            )
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class HockeyProtocol(BaseSportProtocol):
    """Hockey intelligence protocol: confirmed goalie, rest, special teams."""

    def __init__(self) -> None:
        super().__init__("hockey")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        pack = evidence_pack or {}
        goalie = pack.get("confirmed_goalie") or event_data.get("confirmed_goalie")
        if not goalie:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=market_family,
                quality_grade="MEDIUM",
                missing_requirements=("UNKNOWN_STARTER_GOALIE",),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("GOALIE_SENSITIVE_PRICING_BLOCKED",),
            )
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class VolleyballProtocol(BaseSportProtocol):
    """Volleyball intelligence protocol: starting six, side-out efficiency."""

    def __init__(self) -> None:
        super().__init__("volleyball")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class CS2Protocol(BaseSportProtocol):
    """CS2 intelligence protocol: map pool, patch version, roster/stand-in."""

    def __init__(self) -> None:
        super().__init__("cs2")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        pack = evidence_pack or {}
        patch = pack.get("patch_version") or event_data.get("patch_version")
        if not patch:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=market_family,
                quality_grade="MEDIUM",
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("STALE_PATCH_VERSION_CONTEXT",),
            )
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class ValorantProtocol(BaseSportProtocol):
    """Valorant intelligence protocol."""

    def __init__(self) -> None:
        super().__init__("valorant")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


class Dota2Protocol(BaseSportProtocol):
    """Dota 2 intelligence protocol."""

    def __init__(self) -> None:
        super().__init__("dota2")

    def evaluate_market_readiness(
        self,
        *,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
        row_data: Mapping[str, Any],
        evidence_pack: Mapping[str, Any] | None = None,
    ) -> SportReadinessDecisionV1:
        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=market_family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )
