"""Safety score computation — ported from scripts/compute_safety_scores.py.

Core algorithm produces identical results to the original script for same inputs.
Adapted to read from DB models instead of JSON files.
"""

import statistics
from dataclasses import dataclass

from bet.db.models import Fixture, MarketCandidate, Team, TeamForm
from bet.stats.market_ranking import SPORT_MARKETS, STANDARD_MARKET_LINES

# Standard lines for computing safety scores across multiple thresholds
STANDARD_LINES: dict[str, list[float]] = {
    "corners": [7.5, 8.5, 9.5, 10.5, 11.5],
    "fouls": [20.5, 21.5, 22.5, 23.5, 24.5],
    "yellow_cards": [2.5, 3.5, 4.5, 5.5],
    "red_cards": [0.5, 1.5],
    "shots": [20.5, 22.5, 24.5, 26.5],
    "shots_on_target": [8.5, 9.5, 10.5, 11.5],
    "goals": [1.5, 2.5, 3.5],
    "possession": [],
    "offsides": [2.5, 3.5, 4.5],
    "saves": [4.5, 5.5, 6.5],
    "points": [195.5, 205.5, 215.5, 225.5],
    "rebounds": [40.5, 42.5, 44.5],
    "assists": [22.5, 24.5, 26.5],
    "steals": [12.5, 14.5, 16.5],
    "blocks": [8.5, 9.5, 10.5],
    "turnovers": [24.5, 26.5, 28.5],
    "total_games": [20.5, 21.5, 22.5, 23.5],
    "aces": [8.5, 10.5, 12.5],
    "double_faults": [4.5, 6.5, 8.5],
    "sets_won": [2.5],
    "total_points": [140.5, 150.5, 160.5, 170.5],
    "total_frames": [7.5, 8.5, 9.5, 10.5, 12.5],
    "centuries": [0.5, 1.5],
    "fifty_plus_breaks": [2.5, 3.5],
    "heat_points": [35.5, 40.5, 45.5],
    "heat_wins": [5.5, 6.5, 7.5],
    "games_won": [8.5, 9.5, 10.5],
    "break_points_won": [3.5, 4.5, 5.5],
    "first_serve_pct": [],
    "fg_pct": [],
    "three_pct": [],
    "ft_pct": [],
    "faceoff_pct": [],
    "pim": [8.5, 10.5, 12.5],
    "hits": [40.5, 45.5, 50.5],
    "powerplay_goals": [0.5, 1.5],
    "errors": [10.5, 12.5, 14.5],
    "attack_pct": [],
    "frames_won": [3.5, 4.5, 5.5],
    "highest_break": [],
}


def compute_hit_rate(
    values: list[float], line: float, direction: str
) -> tuple[int, int]:
    """Count how many values are over/under the line.

    Returns: (hits, total)
    """
    if not values:
        return 0, 0

    hits = 0
    for v in values:
        if direction == "OVER" and v > line:
            hits += 1
        elif direction == "UNDER" and v < line:
            hits += 1

    return hits, len(values)


def infer_direction(avg: float, line: float) -> str:
    """Infer whether OVER or UNDER is the natural bet direction."""
    return "OVER" if avg > line else "UNDER"


def compute_safety_score(
    l10_values: list[float],
    h2h_values: list[float] | None,
    l5_values: list[float],
    line: float,
    direction: str | None = None,
) -> dict:
    """Compute safety score for a single market+line.

    Returns:
        {
            "hit_rate_l10": float,
            "hit_rate_h2h": float | None,
            "hit_rate_l5": float,
            "safety_score": float,
            "direction": str,
            "three_way_aligned": bool,
            "trend": str,
        }
    """
    l10_avg = statistics.mean(l10_values) if l10_values else 0.0
    l5_avg = statistics.mean(l5_values) if l5_values else 0.0
    h2h_avg = statistics.mean(h2h_values) if h2h_values else 0.0

    # Infer direction if not specified
    if direction is None:
        direction = infer_direction(l10_avg, line)

    # Compute hit rates
    hits_l10, total_l10 = compute_hit_rate(l10_values, line, direction)
    rate_l10 = hits_l10 / total_l10 if total_l10 > 0 else 0.0

    rate_h2h = None
    if h2h_values:
        hits_h2h, total_h2h = compute_hit_rate(h2h_values, line, direction)
        rate_h2h = hits_h2h / total_h2h if total_h2h > 0 else 0.0

    hits_l5, total_l5 = compute_hit_rate(l5_values, line, direction)
    rate_l5 = hits_l5 / total_l5 if total_l5 > 0 else 0.0

    # Safety score = min(L10, H2H) or L10 * 0.7 if no H2H
    if rate_h2h is not None:
        safety = round(min(rate_l10, rate_h2h), 2)
    else:
        safety = round(rate_l10 * 0.7, 2)

    # Three-way alignment
    l10_dir = infer_direction(l10_avg, line)
    l5_dir = infer_direction(l5_avg, line)
    h2h_dir = infer_direction(h2h_avg, line) if h2h_values else None

    aligned = l10_dir == l5_dir
    if h2h_dir is not None:
        aligned = aligned and (h2h_dir == l10_dir)

    # Trend
    if l10_avg > 0:
        pct_change = (l5_avg - l10_avg) / l10_avg * 100
        if pct_change > 5:
            trend = "up"
        elif pct_change < -5:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"

    return {
        "hit_rate_l10": round(rate_l10, 4),
        "hit_rate_h2h": round(rate_h2h, 4) if rate_h2h is not None else None,
        "hit_rate_l5": round(rate_l5, 4),
        "safety_score": safety,
        "direction": direction,
        "three_way_aligned": aligned,
        "trend": trend,
    }


def compute_all_markets(
    fixture: Fixture,
    home_form: dict[str, TeamForm],
    away_form: dict[str, TeamForm],
    h2h_form: dict[str, list[float]],
    sport: str,
    home_team: Team | None = None,
    away_team: Team | None = None,
    competition_name: str = "",
) -> list[MarketCandidate]:
    """Compute safety scores for ALL available markets on a fixture.

    For each market definition (from SPORT_MARKETS):
    1. Get L10/L5 values for relevant stat keys
    2. Try multiple standard lines
    3. Compute safety score for each line
    4. Return ranked list of MarketCandidates
    """
    markets = SPORT_MARKETS.get(sport, [])
    if not markets:
        return []

    candidates: list[MarketCandidate] = []

    for market_def in markets:
        name = market_def["name"]
        stat_a = market_def.get("stat_a")
        stat_b = market_def.get("stat_b")
        is_combined = market_def.get("is_combined", True)

        # Get form data for the relevant stat keys
        home_l10: list[float] = []
        away_l10: list[float] = []
        home_l5: list[float] = []
        away_l5: list[float] = []

        if stat_a and stat_a in home_form:
            home_l10 = home_form[stat_a].l10_values
            home_l5 = home_form[stat_a].l5_values
        if stat_b and stat_b in away_form:
            away_l10 = away_form[stat_b].l10_values
            away_l5 = away_form[stat_b].l5_values

        # Compute combined values
        if is_combined:
            min_len_l10 = min(len(home_l10), len(away_l10)) if home_l10 and away_l10 else 0
            combined_l10 = [home_l10[i] + away_l10[i] for i in range(min_len_l10)]
            min_len_l5 = min(len(home_l5), len(away_l5)) if home_l5 and away_l5 else 0
            combined_l5 = [home_l5[i] + away_l5[i] for i in range(min_len_l5)]
        else:
            # Team-specific market — use whichever team's stat is specified
            combined_l10 = home_l10 if stat_a else away_l10
            combined_l5 = home_l5 if stat_a else away_l5

        if not combined_l10:
            continue

        # Get H2H values for this stat
        h2h_key = stat_a or stat_b or ""
        h2h_vals = h2h_form.get(h2h_key, [])

        # Determine lines to evaluate
        stat_key_for_lines = stat_a or stat_b or ""
        lines = STANDARD_LINES.get(stat_key_for_lines, [])
        if not lines:
            # Use average-based synthetic line
            avg = statistics.mean(combined_l10) if combined_l10 else 0.0
            lines = [round(avg - 0.5, 1), round(avg + 0.5, 1)]

        # Evaluate each line
        for line in lines:
            result = compute_safety_score(
                l10_values=combined_l10,
                h2h_values=h2h_vals if h2h_vals else None,
                l5_values=combined_l5,
                line=line,
            )

            hit_rate = result["hit_rate_l10"]
            min_odds = round(1.0 / hit_rate, 2) if hit_rate > 0 else 99.0

            candidate = MarketCandidate(
                fixture=fixture,
                home_team=home_team or Team(id=fixture.home_team_id, sport_id=fixture.sport_id, name=""),
                away_team=away_team or Team(id=fixture.away_team_id, sport_id=fixture.sport_id, name=""),
                sport_name=sport,
                competition_name=competition_name,
                market_name=name,
                direction=result["direction"],
                line=line,
                safety_score=result["safety_score"],
                hit_rate_l10=result["hit_rate_l10"],
                hit_rate_h2h=result["hit_rate_h2h"],
                hit_rate_l5=result["hit_rate_l5"],
                three_way_aligned=result["three_way_aligned"],
                min_odds=min_odds,
                best_odds=None,
                ev=None,
                betclic_hit_rate=None,
                l10_values=combined_l10[:10],
                l5_values=combined_l5[:5],
                trend=result["trend"],
            )
            candidates.append(candidate)

    # Sort by safety score (desc), then by three_way_aligned (True first)
    candidates.sort(
        key=lambda c: (c.safety_score, c.three_way_aligned),
        reverse=True,
    )

    return candidates
