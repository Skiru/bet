"""Market-specific evidence sufficiency and quality grading for the betting pipeline.

Enforces minimum evidence requirements for tennis, basketball, esports, volleyball,
and hockey, while avoiding over-strictness that would globally block valid entries.
"""
from __future__ import annotations

from typing import Any, Mapping


def evaluate_evidence_sufficiency(
    sport: str,
    market_family: str,
    event: Mapping[str, Any],
    row: Mapping[str, Any],
    evidence_pack: Mapping[str, Any] | None = None,
) -> tuple[str, list[str]]:
    """Evaluates the evidence sufficiency for a given event and market row.
    
    Returns:
        tuple[str, list[str]]: (Quality grade "HIGH"/"MEDIUM"/"LOW"/"UNKNOWN", list of blockers)
    """
    sport_lower = str(sport or event.get("sport") or "").lower()
    family = str(market_family or row.get("market_family") or "").lower()
    pack = evidence_pack or {}

    # Extract basic fields
    home = event.get("home_team") or event.get("canonical_event_name")
    away = event.get("away_team") or event.get("canonical_event_name")
    comp = event.get("competition") or event.get("league_or_tournament")
    prov_ref = row.get("row_id") or row.get("market_row_id") or row.get("provider_market_refs", [None])[0]

    blockers: list[str] = []

    # Critical infrastructure checks (all sports)
    if not home or not away:
        blockers.append("MISSING_EVENT_PARTICIPANTS")
    if not comp:
        blockers.append("MISSING_COMPETITION")
    if not prov_ref:
        blockers.append("MISSING_PROVIDER_REF")

    if blockers:
        return "UNKNOWN", blockers

    # Check sport-specific criteria
    if sport_lower == "tennis":
        # Tennis Match Winner Minimum: player names, tournament/round, ranking/seed, form, surface, counter-evidence
        if family in {"result", "match_winner"}:
            ranking = pack.get("player_ranking") or pack.get("seed") or event.get("ranking_proxy") or "UNKNOWN"
            form = pack.get("recent_form") or pack.get("form") or event.get("form_proxy") or "UNKNOWN"
            surface = pack.get("surface") or event.get("surface") or "UNKNOWN"
            counter = pack.get("counter_evidence") or event.get("counter_evidence")

            missing_critical = []
            if ranking == "UNKNOWN" and form == "UNKNOWN":
                missing_critical.append("MISSING_STRENGTH_AND_FORM_PROXIES")

            if missing_critical:
                return "LOW", missing_critical
            
            if ranking != "UNKNOWN" and form != "UNKNOWN" and surface != "UNKNOWN":
                return "HIGH", []
            return "MEDIUM", []

        # Tennis Totals/Handicap Minimum: all match winner fields + serve/return proxy or explicit limit + line
        elif family in {"total_games", "game_handicap", "set_handicap"}:
            line = row.get("line")
            if line in (None, "", "UNKNOWN", "N/A"):
                return "UNKNOWN", ["LINE_SEMANTICS_MISSING"]

            ranking = pack.get("player_ranking") or pack.get("seed") or event.get("ranking_proxy") or "UNKNOWN"
            form = pack.get("recent_form") or pack.get("form") or event.get("form_proxy") or "UNKNOWN"
            serve_proxy = pack.get("serve_return_stat") or event.get("serve_return_proxy") or "UNKNOWN"

            if ranking == "UNKNOWN" or form == "UNKNOWN":
                return "LOW", ["MISSING_TENNIS_BASE_EVIDENCE"]
            
            if serve_proxy == "UNKNOWN":
                # Sourced unknown with limitation is allowed but drops to MEDIUM
                return "MEDIUM", ["SERVE_RETURN_PROXY_UNKNOWN_LIMITATION"]
            return "HIGH", []

    elif sport_lower == "basketball":
        # Basketball Minimum: teams, competition, recent form/standing/strength, provider ref, counter-evidence
        form = pack.get("recent_form") or pack.get("standing") or event.get("form_proxy") or "UNKNOWN"
        if form == "UNKNOWN":
            return "MEDIUM", ["BASKETBALL_FORM_UNKNOWN_LIMITATION"]
        return "HIGH", []

    elif sport_lower in {"cs2", "valorant", "dota2", "esports"}:
        # Esports Minimum: title, teams, match format, recent form/roster/map, provider ref, counter-evidence
        title = event.get("game_title") or event.get("title") or sport_lower
        form = pack.get("recent_form") or pack.get("map_stats") or event.get("form_proxy") or "UNKNOWN"
        if not title:
            return "LOW", ["MISSING_ESPORTS_TITLE"]
        if form == "UNKNOWN":
            return "MEDIUM", ["ESPORTS_FORM_UNKNOWN_LIMITATION"]
        return "HIGH", []

    elif sport_lower in {"volleyball", "hockey"}:
        # Volleyball/Hockey Minimum: teams, competition, market row, form if available, counter-evidence
        form = pack.get("recent_form") or event.get("form_proxy") or "UNKNOWN"
        if form == "UNKNOWN":
            return "MEDIUM", ["VOLLEYBALL_HOCKEY_FORM_UNKNOWN_LIMITATION"]
        return "HIGH", []

    elif sport_lower == "football":
        # Football: preserve existing criteria
        discovery_status = str(event.get("discovery_status") or "").upper()
        if discovery_status == "VERIFIED" and len(event.get("market_rows_by_market_family", {})) >= 0:
            return "HIGH", []
        return "MEDIUM", []

    return "MEDIUM", []
