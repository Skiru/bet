"""Sport-specific protocol definitions for all 8 supported sports."""
from __future__ import annotations

from typing import Any, Mapping
from bet.pipeline.sports.models import (
    MarketEvidenceRequirementV1,
    SourceFreshnessPolicyV1,
    SportReadinessDecisionV1,
)


class BaseSportProtocol:
    """Base class for sport-specific intelligence protocols."""

    def __init__(self, sport_id: str) -> None:
        self.sport_id = sport_id

    def _validate_base_event(
        self,
        canonical_event_id: str,
        market_family: str,
        event_data: Mapping[str, Any],
    ) -> list[str]:
        missing: list[str] = []
        home = event_data.get("home_team") or event_data.get("canonical_event_name")
        away = event_data.get("away_team") or event_data.get("canonical_event_name")
        comp = event_data.get("competition") or event_data.get("league_or_tournament")

        if not home or not away:
            missing.append("MISSING_EVENT_PARTICIPANTS")
        if not comp:
            missing.append("MISSING_COMPETITION")
        return missing

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
        family = str(market_family or row_data.get("market_family") or "").lower()

        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        missing: list[str] = []
        sample_size = pack.get("sample_size") or row_data.get("sample_size")
        data_freshness_hours = pack.get("data_freshness_hours") or row_data.get("data_freshness_hours")
        sources = pack.get("sources") or row_data.get("sources")

        # Football count markets require sample size >= 5, freshness <= 72h, source lineage, and for/against stats
        if family in {"corners", "total_corners", "corner_handicap"}:
            c_home_for = pack.get("home_corners_avg") or pack.get("corners_home")
            c_away_for = pack.get("away_corners_avg") or pack.get("corners_away")
            c_home_against = pack.get("home_corners_against_avg")
            c_away_against = pack.get("away_corners_against_avg")

            if c_home_for is None or c_away_for is None or c_home_against is None or c_away_against is None:
                missing.append("MISSING_CORNER_FOR_AGAINST_STATS")
            if sample_size is None or sample_size < 5:
                missing.append("INSUFFICIENT_CORNER_SAMPLE_SIZE")
            if data_freshness_hours is not None and data_freshness_hours > 72:
                missing.append("STALE_CORNER_DATA")
            if not sources:
                missing.append("MISSING_CORNER_SOURCE_LINEAGE")

            if missing:
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
            referee = pack.get("referee_discipline") or pack.get("referee")

            if cards_home is None or cards_away is None or not referee:
                missing.append("MISSING_CARD_OR_REFEREE_DISCIPLINE_STATS")
            if sample_size is None or sample_size < 5:
                missing.append("INSUFFICIENT_CARD_SAMPLE_SIZE")
            if not sources:
                missing.append("MISSING_CARD_SOURCE_LINEAGE")

            if missing:
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
            opponent_adj = pack.get("opponent_adjustment")

            if shots_home is None or shots_away is None or opponent_adj is None:
                missing.append("MISSING_SHOT_STATS_OR_OPPONENT_ADJUSTMENT")
            if sample_size is None or sample_size < 5:
                missing.append("INSUFFICIENT_SHOT_SAMPLE_SIZE")

            if missing:
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

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
        serve_win_pct = pack.get("serve_win_pct") or pack.get("holding_pct")
        surface = pack.get("surface") or event_data.get("surface")
        injury_status = pack.get("injury_status") or pack.get("retirement_risk") or event_data.get("injury_status") or "NO_INJURY_REPORTED"

        if not surface:
            missing.append("MISSING_SURFACE_CONTEXT")
        if not ranking and serve_win_pct is None:
            missing.append("MISSING_SERVE_RETURN_STRENGTH_STATS")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="LOW",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("MISSING_TENNIS_BASE_EVIDENCE",),
            )

        rest_hours = pack.get("rest_hours")
        reasons = []
        if rest_hours is not None and rest_hours < 18:
            reasons.append("HIGH_CONSECUTIVE_DAY_WORKLOAD_WIDEN_INTERVAL")

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
            quality_grade="HIGH",
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        pace = pack.get("pace") or pack.get("offensive_rating")
        injuries = pack.get("key_injuries") or pack.get("rotation_confirmed")
        rest = pack.get("rest_days") or pack.get("back_to_back")

        if pace is None:
            missing.append("MISSING_BASKETBALL_PACE_RATINGS")
        if injuries is None:
            missing.append("MISSING_ROTATION_INJURY_STATUS")
        if rest is None:
            missing.append("MISSING_REST_TRAVEL_CONTEXT")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="MEDIUM",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("BASKETBALL_INSUFFICIENT_PRICING_EVIDENCE",),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        goalie = pack.get("confirmed_goalie") or event_data.get("confirmed_goalie") or pack.get("home_goalie")
        special_teams = pack.get("special_teams") or pack.get("powerplay_pct")
        rest = pack.get("rest_days") or pack.get("back_to_back")

        if not goalie:
            missing.append("UNKNOWN_STARTER_GOALIE")
        if special_teams is None:
            missing.append("MISSING_SPECIAL_TEAMS_OR_XG_STATS")
        if rest is None:
            missing.append("MISSING_HOCKEY_REST_TRAVEL_CONTEXT")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="MEDIUM",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("HOCKEY_INSUFFICIENT_PRICING_EVIDENCE",),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        starting_six = pack.get("starting_six") or pack.get("lineup_confirmed")
        sideout = pack.get("sideout_pct") or pack.get("attack_efficiency")
        rest = pack.get("rest_days") or pack.get("rest_hours")

        if not starting_six:
            missing.append("MISSING_VOLLEYBALL_STARTING_SIX")
        if sideout is None:
            missing.append("MISSING_VOLLEYBALL_SIDEOUT_EFFICIENCY")
        if rest is None:
            missing.append("MISSING_VOLLEYBALL_REST_TRAVEL")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="LOW",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("MISSING_VOLLEYBALL_LINEUP_OR_EFFICIENCY",),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        patch = pack.get("patch_version") or event_data.get("patch_version")
        roster = pack.get("roster_confirmed") or pack.get("stand_in_info")
        map_pool = pack.get("map_pool") or pack.get("map_history")

        if not patch:
            missing.append("STALE_PATCH_VERSION_CONTEXT")
        if not roster:
            missing.append("UNCONFIRMED_ROSTER_OR_STANDIN")
        if not map_pool:
            missing.append("MISSING_MAP_POOL_STATS")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="MEDIUM",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=tuple(missing),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        patch = pack.get("patch_version") or event_data.get("patch_version")
        map_pool = pack.get("map_pool") or pack.get("map_history")
        roster = pack.get("roster_confirmed") or pack.get("agent_comps")

        if not patch:
            missing.append("MISSING_VALORANT_PATCH")
        if not map_pool:
            missing.append("MISSING_VALORANT_MAP_POOL")
        if not roster:
            missing.append("MISSING_VALORANT_ROSTER")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="LOW",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("MISSING_VALORANT_CONTEXT",),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
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
        family = str(market_family or row_data.get("market_family") or "").lower()
        base_missing = self._validate_base_event(canonical_event_id, family, event_data)
        if base_missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="UNKNOWN",
                missing_requirements=tuple(base_missing),
                allowed_action="BLOCKED",
                reason_codes=tuple(base_missing),
            )

        pack = evidence_pack or {}
        missing: list[str] = []

        patch = pack.get("patch_version") or event_data.get("patch_version")
        hero_stats = pack.get("draft_stats") or pack.get("hero_pool")
        roster = pack.get("roster_confirmed") or pack.get("stand_in_info")

        if not patch:
            missing.append("MISSING_DOTA2_PATCH")
        if not hero_stats:
            missing.append("MISSING_DOTA2_DRAFT_STATS")
        if not roster:
            missing.append("MISSING_DOTA2_ROSTER")

        if missing:
            return SportReadinessDecisionV1(
                canonical_event_id=canonical_event_id,
                sport=self.sport_id,
                market_family=family,
                quality_grade="LOW",
                missing_requirements=tuple(missing),
                allowed_action="ANALYSIS_ONLY",
                reason_codes=("MISSING_DOTA2_CONTEXT",),
            )

        return SportReadinessDecisionV1(
            canonical_event_id=canonical_event_id,
            sport=self.sport_id,
            market_family=family,
            quality_grade="HIGH",
            allowed_action="READY_FOR_PRICING",
        )


def get_sport_protocol_handler(sport_id: str) -> BaseSportProtocol | None:
    """Retrieve the registered sport protocol handler for a given sport ID."""
    from bet.pipeline.sports.registry import GLOBAL_SPORT_PROTOCOL_REGISTRY
    return GLOBAL_SPORT_PROTOCOL_REGISTRY.get(str(sport_id).lower())
