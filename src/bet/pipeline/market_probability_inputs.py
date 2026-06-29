"""Market-specific probability inputs schema, derivation and validation."""
from __future__ import annotations
import json
import statistics
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class MarketProbabilityInput:
    candidate_id: str
    sport: str
    market_family: str
    market_type: str
    selection: str
    direction: str
    line: Optional[float]
    team_a_name: str
    team_b_name: str
    team_a_l10: List[float] = field(default_factory=list)
    team_b_l10: List[float] = field(default_factory=list)
    h2h_l5: Optional[List[float]] = None
    source_artifact_path: str = ""
    stats_as_of: str = "UNKNOWN"
    sample_size: int = 0
    missing_fields: List[str] = field(default_factory=list)


def derive_l10_series_for_market_family(
    stats_seed: dict[str, Any],
    market_family: str,
    line: float | None,
    direction: str,
) -> tuple[list[float], list[float], list[float] | None]:
    raw_data = stats_seed.get("raw_data") or {}
    safety_input = raw_data.get("safety_input") or {}
    markets = safety_input.get("markets") or []

    # Path 1: safety_input markets
    if markets:
        family_map = {
            "GOALS_TOTALS": ["goals total", "total goals", "goals"],
            "CORNERS": ["corners total", "total corners", "corners"],
            "CARDS": ["cards total", "total cards", "yellow_cards", "cards"],
            "SHOTS": ["shots total", "total shots", "shots"],
            "SHOTS_ON_TARGET": ["shots on target", "shots_on_target"],
            "RESULT": ["match winner", "ml", "winner", "moneyline", "goals"],
        }
        
        keywords = family_map.get(market_family, [market_family.lower()])
        matching_market = None
        for m in markets:
            name_lower = str(m.get("name") or "").lower()
            if any(kw in name_lower for kw in keywords):
                if line is not None and abs(float(m.get("line") or 0.0) - line) < 0.01:
                    matching_market = m
                    break
                if matching_market is None:
                    matching_market = m
        
        if matching_market:
            team_a_l10 = matching_market.get("team_a_l10") or []
            team_b_l10 = matching_market.get("team_b_l10") or []
            h2h_l5 = matching_market.get("h2h_values") or []
            return team_a_l10, team_b_l10, h2h_l5

    # Path 2: Reconstruct from l10_matches or summaries
    stats_a = stats_seed.get("stats_a_summary") or {}
    stats_b = stats_seed.get("stats_b_summary") or {}
    
    stat_key_map = {
        "GOALS_TOTALS": "goals",
        "CORNERS": "corners",
        "CARDS": "yellow_cards",
        "SHOTS": "shots",
        "SHOTS_ON_TARGET": "shots_on_target",
        "RESULT": "goals",
    }
    
    stat_key = stat_key_map.get(market_family)
    if not stat_key:
        return [], [], None

    team_a_l10 = []
    team_b_l10 = []
    
    team_a_raw = raw_data.get("team_a_l10") or {}
    team_b_raw = raw_data.get("team_b_l10") or {}
    
    for team_raw, target_list in ((team_a_raw, team_a_l10), (team_b_raw, team_b_l10)):
        matches = team_raw.get("l10_matches") or []
        for match in matches:
            stats = match.get("stats", match)
            val = stats.get(stat_key)
            if val is not None:
                if isinstance(val, dict):
                    target_list.append(float(val.get("home", 0) + val.get("away", 0)))
                else:
                    target_list.append(float(val))
                    
    if not team_a_l10 and stats_a.get("has_data"):
        l10_avg = stats_a.get("l10_avg", {}).get(stat_key)
        l5_avg = stats_a.get("l5_avg", {}).get(stat_key)
        if l10_avg is not None:
            from normalize_stats import _synthesize_l10
            team_a_l10 = _synthesize_l10(l10_avg, l5_avg, seed_key=stats_a.get("team", "A"))
            
    if not team_b_l10 and stats_b.get("has_data"):
        l10_avg = stats_b.get("l10_avg", {}).get(stat_key)
        l5_avg = stats_b.get("l5_avg", {}).get(stat_key)
        if l10_avg is not None:
            from normalize_stats import _synthesize_l10
            team_b_l10 = _synthesize_l10(l10_avg, l5_avg, seed_key=stats_b.get("team", "B"))

    h2h_summary = stats_seed.get("h2h_summary") or {}
    h2h_l5 = []
    if h2h_summary.get("has_data"):
        avg_val = h2h_summary.get("averages", {}).get(stat_key)
        if avg_val is not None:
            h2h_l5 = [float(avg_val)] * min(5, h2h_summary.get("meetings_count", 0))

    return team_a_l10, team_b_l10, h2h_l5 if h2h_l5 else None


def build_market_probability_input(candidate: dict[str, Any], stats_seed: dict[str, Any] | None) -> MarketProbabilityInput:
    candidate_id = candidate.get("candidate_id") or candidate.get("fixture_key") or ""
    sport = candidate.get("sport") or ""
    market_family = candidate.get("market_family") or ""
    market_type = candidate.get("market_type") or ""
    selection = candidate.get("selection") or candidate.get("pick") or ""
    direction = candidate.get("direction") or ""
    line = candidate.get("line")
    if line is not None:
        try:
            line = float(line)
        except (ValueError, TypeError):
            line = None

    team_a_name = candidate.get("home_team") or ""
    team_b_name = candidate.get("away_team") or ""

    if not stats_seed:
        return MarketProbabilityInput(
            candidate_id=candidate_id,
            sport=sport,
            market_family=market_family,
            market_type=market_type,
            selection=selection,
            direction=direction,
            line=line,
            team_a_name=team_a_name,
            team_b_name=team_b_name,
            missing_fields=["stats_seed"],
        )

    best_market = stats_seed.get("best_market") or {}
    if not market_family and best_market:
        market_family = best_market.get("market_family") or ""
    if not market_type and best_market:
        market_type = best_market.get("name") or ""
    if not direction and best_market:
        direction = best_market.get("direction") or ""
    if line is None and best_market:
        line_val = best_market.get("line")
        if line_val is not None:
            try:
                line = float(line_val)
            except (ValueError, TypeError):
                line = None

    team_a_l10, team_b_l10, h2h_l5 = derive_l10_series_for_market_family(stats_seed, market_family, line, direction)

    sample_size = max(len(team_a_l10), len(team_b_l10))
    stats_as_of = stats_seed.get("probability_as_of") or stats_seed.get("generated_at") or "UNKNOWN"

    missing_fields = []
    if not market_family:
        missing_fields.append("market_family")
    if not direction:
        missing_fields.append("direction")
    if line is None and market_family in ("GOALS_TOTALS", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"):
        missing_fields.append("line")

    return MarketProbabilityInput(
        candidate_id=candidate_id,
        sport=sport,
        market_family=market_family,
        market_type=market_type,
        selection=selection,
        direction=direction,
        line=line,
        team_a_name=team_a_name,
        team_b_name=team_b_name,
        team_a_l10=team_a_l10,
        team_b_l10=team_b_l10,
        h2h_l5=h2h_l5,
        source_artifact_path=stats_seed.get("source_artifact_path") or "",
        stats_as_of=stats_as_of,
        sample_size=sample_size,
        missing_fields=missing_fields,
    )


def validate_market_probability_input(input_data: MarketProbabilityInput) -> tuple[bool, str]:
    if not input_data.market_family:
        return False, "MARKET_SPECIFIC_INPUT_NOT_BUILT"
        
    if "UNSUPPORTED" in input_data.market_family or "PROP" in input_data.market_family or "tackles" in input_data.market_type:
        return False, "MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE"
        
    if input_data.market_family not in ("GOALS_TOTALS", "RESULT", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"):
        return False, "MARKET_FAMILY_NOT_SUPPORTED_BY_ENGINE"

    if input_data.market_family in ("GOALS_TOTALS", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"):
        if input_data.line is None:
            return False, "LINE_MISSING"

    if input_data.market_family in ("GOALS_TOTALS", "CORNERS", "CARDS", "SHOTS", "SHOTS_ON_TARGET"):
        if not input_data.team_a_l10 or not input_data.team_b_l10:
            return False, "L10_SERIES_MISSING"
        if len(input_data.team_a_l10) < 5 or len(input_data.team_b_l10) < 5:
            return False, "INSUFFICIENT_SAMPLE_SIZE"
            
    elif input_data.market_family == "RESULT":
        if not input_data.team_a_l10 or not input_data.team_b_l10:
            return False, "L10_SERIES_MISSING"
        if len(input_data.team_a_l10) < 5 or len(input_data.team_b_l10) < 5:
            return False, "INSUFFICIENT_SAMPLE_SIZE"

    if input_data.market_family != "RESULT" and not input_data.direction:
        return False, "DIRECTION_MISSING"

    return True, "PASS"


def explain_probability_input_gap(input_data: MarketProbabilityInput) -> str:
    valid, reason = validate_market_probability_input(input_data)
    if valid:
        return ""
    return reason
