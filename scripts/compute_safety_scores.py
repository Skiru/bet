#!/usr/bin/env python3
"""Deterministic §3.0 safety score calculator for betting market ranking.

Given structured stats data (JSON), computes the §3.0 ranking table:
- Hit rates for OVER/UNDER per market
- Safety score = min(hit_rate_L10, hit_rate_H2H)
- Three-way cross-check (L10 + H2H + L5)
- Ranked market table with markdown output

Input: JSON file with team stats and available market data
Output: JSON with computed rankings + markdown table
"""

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from probability_engine import optimize_line
except ImportError:
    optimize_line = None

# Minimum markets required per sport
MIN_MARKETS = {
    "football": 4,  # fouls + cards + corners + shots
    "tennis": 3,
    "basketball": 3,
    "volleyball": 3,
    "hockey": 3,

}

# Sport-specific H2H penalty — niche sports rarely have H2H data
H2H_MISSING_PENALTY = {
    "football": 0.70,     # 30% penalty — H2H expected
    "tennis": 0.70,       # 30% penalty — H2H expected
    "basketball": 0.70,   # 30% penalty — H2H expected
    "volleyball": 0.75,   # 25% penalty — H2H common but not universal
    "hockey": 0.75,       # 25% penalty

}

# ---------------------------------------------------------------------------
# Pattern C: Sport-specific volatility caps (May 2026 post-mortem)
# ---------------------------------------------------------------------------
# Single-game variance differs enormously across sports. Baseball CV ~70-80%,
# basketball ~15%. These caps prevent inflated safety scores
# on inherently volatile per-game stats.

SPORT_VOLATILITY_CAPS: dict[str, dict[str, float]] = {
    "hockey": {
        "team_goals": 0.60,
        "total_goals": 0.60,
    },
    "basketball": {
        "team_points": 0.70,
    },
    "football": {
        "team_goals": 0.65,
        "total_goals": 0.65,
        # Corners, cards, fouls are MORE predictable — no cap (standard)
    },
}


def _market_category(market_name: str) -> str:
    """Map a market name to its volatility category."""
    lower = market_name.lower()

    # Baseball
    if any(kw in lower for kw in ("runs", "run")):
        if "team" in lower:
            return "team_runs"
        return "total_runs"
    if "hit" in lower:
        if "team" in lower:
            return "team_hits"
        return "total_hits"
    if "strikeout" in lower or "k's" in lower:
        return "strikeouts"

    # Hockey/Handball/Football goals
    if "goal" in lower:
        if "team" in lower:
            return "team_goals"
        return "total_goals"

    # Basketball
    if "point" in lower:
        if "team" in lower:
            return "team_points"
        return "total_points"

    return ""


# ---------------------------------------------------------------------------
# Pattern E: Data tier caps (youth, state leagues, women's)
# ---------------------------------------------------------------------------

def _compute_data_tier_cap(competition: str) -> float:
    """Return maximum safety score based on competition tier.

    Lower-quality data sources → lower safety cap.
    """
    comp_lower = competition.lower()

    # Youth leagues (U17, U19, U20, U21)
    if any(kw in comp_lower for kw in ("u17", "u19", "u20", "u21", "youth", "junior", "sub-20", "sub-17")):
        return 0.60

    # State/regional leagues (Brazil Campeonato Estadual, etc.)
    if any(kw in comp_lower for kw in (
        "capixaba", "paulista", "carioca", "gaúcho", "gaucho",
        "mineiro", "paranaense", "catarinense", "baiano",
        "sergipano", "alagoano", "potiguar", "paraibano",
    )):
        return 0.55

    # Women's leagues (except top — NWSL, WSL, D1F, Liga F, Serie A Femminile)
    top_womens = ("nwsl", "wsl", "d1 arkema", "liga f", "serie a femm")
    if ("women" in comp_lower or "feminin" in comp_lower or "kobiet" in comp_lower or
            "w." in comp_lower or "ladies" in comp_lower):
        if not any(top in comp_lower for top in top_womens):
            return 0.60

    # Second/third division (smaller penalty)
    if any(kw in comp_lower for kw in (
        "2. liga", "segunda", "serie b", "ligue 2", "2. bundesliga",
        "championship", "league one", "league two",
        "primera b", "serie c", "3. liga",
    )):
        return 0.70  # Small discount — decent data usually available

    # No cap for standard competitions
    return 1.0


# ---------------------------------------------------------------------------
# Pattern G: High-stakes context detection (CL SF, playoffs, finals)
# ---------------------------------------------------------------------------

# Keywords indicating knockout/playoff/final matches where regular L10
# stats may be less applicable due to different tactical approaches
HIGH_STAKES_KEYWORDS = (
    "champions league", "europa league", "conference league",
    "playoff", "play-off", "final", "semi-final", "semifinal",
    "quarter-final", "quarterfinal", "knockout", "elimination",
    "world cup", "copa america", "euro 202", "nations league final",
    "nba playoff", "nhl playoff", "stanley cup",
    "grand slam", "masters 1000",
)


def _detect_high_stakes_context(competition: str) -> dict | None:
    """Detect if a competition represents a high-stakes context.

    Returns a warning dict if L10 stats may be unreliable for this context,
    or None if regular analysis applies.
    """
    comp_lower = competition.lower()
    for kw in HIGH_STAKES_KEYWORDS:
        if kw in comp_lower:
            return {
                "type": "HIGH_STAKES_CONTEXT",
                "competition": competition,
                "keyword_matched": kw,
                "message": (
                    f"⚠️ KONTEKST WYSOKIEJ STAWKI: '{competition}' to mecz eliminacyjny/pucharowy. "
                    f"Statystyki L10 mogą pochodzić z meczów ligowych o NIŻSZEJ intensywności. "
                    f"Zespoły grają inaczej w KO — defensywniej na wyjeździe, desperacko w domu. "
                    f"Wymagany dodatkowy margines bezpieczeństwa (+15% na linii)."
                ),
                "safety_discount": 0.90,  # 10% discount on safety score
            }
    return None


# Input JSON schema description (for --help)
INPUT_SCHEMA = """
Input JSON format:
{
  "sport": "football",
  "team_a": "Liverpool",
  "team_b": "Arsenal",
  "competition": "Premier League",
  "markets": [
    {
      "name": "Corners Total O/U",
      "line": 9.5,
      "team_a_l10": [11, 8, 13, ...],     // raw values per match (last 10)
      "team_b_l10": [6, 9, 8, ...],       // raw values per match (last 10)
      "h2h_values": [12, 9, 14, ...],     // combined values from H2H meetings
      "team_a_l5": [12, 7, 11, ...],      // recent form (last 5)
      "team_b_l5": [10, 5, 8, ...],       // recent form (last 5)
      "is_combined": true,                 // true=add team values, false=use as-is
      "source": "TotalCorner + SoccerStats"
    }
  ]
}

For combined markets (total corners, total fouls):
  - L10 combined = team_a_l10[i] + team_b_l10[i] for each match
For team-specific markets (team corners O/U, team shots):
  - L10 values = team_a_l10 only (team_b not used for hit rate)
"""


def compute_data_quality_score(ranking_result: dict, has_injuries: bool = False,
                                has_league_context: bool = False,
                                has_tipster: bool = False,
                                odds_sources: int = 0,
                                has_elo: bool = False) -> dict:
    """Compute data quality score (0-10) based on data availability."""
    score = 0
    breakdown = {}

    # +2 for L10 data with ≥3 ranked markets (proxy for sufficient data points)
    l10_ok = len(ranking_result.get("ranking", [])) >= 3
    if l10_ok:
        score += 2
    breakdown["l10_data"] = l10_ok

    # +2 for H2H with ≥3 meetings (not H2H-blind)
    h2h_ok = not ranking_result.get("ranking", [{}])[0].get("h2h_blind", True) if ranking_result.get("ranking") else False
    if h2h_ok:
        score += 2
    breakdown["h2h_data"] = h2h_ok

    # +1 for L5 trend
    l5_ok = (ranking_result.get("ranking", [{}])[0].get("hit_rate_l5", "N/A") != "N/A") if ranking_result.get("ranking") else False
    if l5_ok:
        score += 1
    breakdown["l5_trend"] = l5_ok

    # +1 each for additional data
    if has_injuries:
        score += 1
    breakdown["injuries"] = has_injuries

    if has_league_context:
        score += 1
    breakdown["league_context"] = has_league_context

    if has_tipster:
        score += 1
    breakdown["tipster_data"] = has_tipster

    if odds_sources >= 2:
        score += 1
    breakdown["odds_validated"] = odds_sources >= 2

    # +1 for Elo ratings available (tennis: surface-specific Elo from TennisAbstract)
    if has_elo:
        score += 1
    breakdown["elo_data"] = has_elo

    # +1 for three-way check alignment
    twc = ranking_result.get("three_way_check")
    three_ok = twc is not None and twc.get("alignment") is not None and "SUPPORT" in str(twc.get("alignment", "")).upper()
    if three_ok:
        score += 1
    breakdown["three_way_check"] = three_ok

    label = "FULL" if score >= 7 else "PARTIAL" if score >= 4 else "MINIMAL"

    return {"score": score, "label": label, "breakdown": breakdown}


def validate_input(data: dict) -> list[str]:
    """Validate input JSON structure. Returns list of errors."""
    errors = []

    if "sport" not in data:
        errors.append("Missing required field: 'sport'")
    if "team_a" not in data:
        errors.append("Missing required field: 'team_a'")
    if "team_b" not in data:
        errors.append("Missing required field: 'team_b'")
    if "markets" not in data or not isinstance(data.get("markets"), list):
        errors.append("Missing or invalid 'markets' array")
        return errors

    for i, market in enumerate(data["markets"]):
        prefix = f"markets[{i}]"
        if "name" not in market:
            errors.append(f"{prefix}: missing 'name'")
        if "line" not in market:
            errors.append(f"{prefix}: missing 'line'")
        elif not isinstance(market["line"], (int, float)):
            errors.append(f"{prefix}: 'line' must be numeric")

        for field in ["team_a_l10", "team_b_l10"]:
            if field not in market:
                errors.append(f"{prefix}: missing '{field}'")
            elif not isinstance(market[field], list):
                errors.append(f"{prefix}: '{field}' must be an array")
            elif not all(isinstance(v, (int, float)) for v in market[field]):
                errors.append(f"{prefix}: '{field}' must contain only numbers")

        if "h2h_values" in market:
            if not isinstance(market["h2h_values"], list):
                errors.append(f"{prefix}: 'h2h_values' must be an array")
            elif not all(isinstance(v, (int, float)) for v in market["h2h_values"]):
                errors.append(f"{prefix}: 'h2h_values' must contain only numbers")

    return errors


def compute_combined_values(market: dict) -> list[float]:
    """Compute combined L10 values from team A + team B."""
    is_combined = market.get("is_combined", True)
    a_vals = market.get("team_a_l10", [])
    b_vals = market.get("team_b_l10", [])

    if is_combined:
        # Combined market: add corresponding values
        min_len = min(len(a_vals), len(b_vals))
        return [a_vals[i] + b_vals[i] for i in range(min_len)]
    else:
        # Team-specific market: use team A only
        return list(a_vals)


def compute_combined_l5(market: dict) -> list[float]:
    """Compute combined L5 values from team A + team B."""
    is_combined = market.get("is_combined", True)
    # L10 is ordered most-recent-first, so [:5] gives the 5 most recent matches
    a_vals = market.get("team_a_l5") or market.get("team_a_l10", [])[:5]
    b_vals = market.get("team_b_l5") or market.get("team_b_l10", [])[:5]

    if is_combined:
        min_len = min(len(a_vals), len(b_vals))
        return [a_vals[i] + b_vals[i] for i in range(min_len)]
    else:
        return list(a_vals)


def compute_hit_rate(values: list[float], line: float, direction: str) -> tuple[int, int, int]:
    """Count how many values are over/under the line, tracking pushes.

    Args:
        values: list of stat values
        line: the betting line (e.g., 9.5)
        direction: "OVER" or "UNDER"

    Returns: (hits, total, pushes)
        pushes = values exactly on the line (relevant for whole-number lines)
    """
    if not values:
        return 0, 0, 0

    hits = 0
    pushes = 0
    for v in values:
        if v == line:
            pushes += 1
        elif direction == "OVER" and v > line:
            hits += 1
        elif direction == "UNDER" and v < line:
            hits += 1

    return hits, len(values), pushes


def infer_direction(avg: float, line: float) -> str:
    """Infer whether OVER or UNDER is the natural bet direction."""
    return "OVER" if avg > line else "UNDER"


def compute_margin(avg: float, line: float, direction: str) -> float:
    """Compute margin: how much the average exceeds the line.

    OVER: avg/line (>1 = margin exists)
    UNDER: line/avg (>1 = margin exists)
    """
    if line == 0:
        return 0.0
    if avg == 0:
        # avg=0 with line>0: infinite UNDER margin, cap at 1.50
        return 1.50 if direction == "UNDER" else 0.0
    if direction == "OVER":
        return min(round(avg / line, 3), 1.50)
    else:
        return min(round(line / avg, 3), 1.50)


def compute_safety_score(hit_rate_l10: float, hit_rate_h2h: float) -> float:
    """Safety = min(hit_rate_L10, hit_rate_H2H). Higher = safer."""
    return round(min(hit_rate_l10, hit_rate_h2h), 2)


def compute_three_way_check(
    l10_avg: float, h2h_avg: float, l5_avg: float, line: float
) -> dict:
    """Compute three-way cross-check alignment."""
    l10_dir = infer_direction(l10_avg, line)
    h2h_dir = infer_direction(h2h_avg, line) if h2h_avg > 0 else "N/A"
    l5_dir = infer_direction(l5_avg, line)

    # Determine trend from L5 vs L10
    if l5_avg > 0 and l10_avg > 0:
        pct_change = (l5_avg - l10_avg) / l10_avg * 100
        if pct_change > 5:
            trend = "UP"
        elif pct_change < -5:
            trend = "DOWN"
        else:
            trend = "STABLE"
    else:
        trend = "N/A"

    # Count support
    primary_dir = l10_dir
    support_count = 1  # L10 always supports itself
    h2h_missing = h2h_dir == "N/A"

    directions = [l10_dir]
    if h2h_dir != "N/A":
        directions.append(h2h_dir)
        if h2h_dir == primary_dir:
            support_count += 1
    if l5_dir == primary_dir:
        support_count += 1
    directions.append(l5_dir)

    total = len([d for d in [l10_dir, h2h_dir, l5_dir] if d != "N/A"])
    if total == 0:
        alignment = "N/A"
    elif support_count == total:
        alignment = f"{total}/{total} SUPPORT"
    elif support_count >= 2:
        alignment = f"{support_count}/{total} SUPPORT"
    else:
        conflicts = total - support_count
        if conflicts >= total:
            alignment = f"{total}/{total} CONFLICT → REJECT"
        else:
            alignment = f"{support_count}/{total} CONFLICT → DOWNGRADE"

    # Mark when H2H is missing so alignment doesn't mask incomplete data
    if h2h_missing:
        alignment += " (H2H N/A)"

    return {
        "l10_avg": round(l10_avg, 2),
        "h2h_avg": round(h2h_avg, 2) if h2h_avg > 0 else None,
        "l5_avg": round(l5_avg, 2),
        "line": line,
        "l10_direction": l10_dir,
        "h2h_direction": h2h_dir,
        "l5_trend": trend,
        "alignment": alignment,
    }


def rank_markets(data: dict) -> dict:
    """Compute safety scores and rank all markets for a candidate."""
    sport = data["sport"].lower()
    team_a = data["team_a"]
    team_b = data["team_b"]
    competition = data.get("competition", "")
    markets = data.get("markets", [])

    results = []

    for market in markets:
        name = market["name"]
        line = market["line"]
        source = market.get("source", "")

        # Compute combined L10 values
        l10_values = compute_combined_values(market)

        # Tennis data validation: reject markets with impossible averages
        # A completed tennis match has min 12 total games (6-0 6-0) and
        # a player wins min 6 games. Lower values = walkover/retirement data.
        if sport == "tennis" and l10_values:
            name_lower = name.lower()
            if "total games" in name_lower:
                l10_values = [v for v in l10_values if v >= 12]
            elif "games" in name_lower and ("player" in name_lower or team_a.lower() in name_lower or team_b.lower() in name_lower):
                l10_values = [v for v in l10_values if v >= 6]
            if not l10_values:
                continue  # All values were invalid — skip this market

        l10_avg = statistics.mean(l10_values) if l10_values else 0.0

        # Compute team averages
        team_a_avg = statistics.mean(market.get("team_a_l10", [])) if market.get("team_a_l10") else 0.0
        team_b_avg = statistics.mean(market.get("team_b_l10", [])) if market.get("team_b_l10") else 0.0

        # Swap display labels for Team B-only markets
        team_swapped = market.get("team_swapped", False)
        display_a_avg = team_b_avg if team_swapped else team_a_avg
        display_b_avg = team_a_avg if team_swapped else team_b_avg

        # H2H values
        h2h_values = market.get("h2h_values", [])
        h2h_avg = statistics.mean(h2h_values) if h2h_values else 0.0

        # L5 values
        l5_values = compute_combined_l5(market)
        l5_avg = statistics.mean(l5_values) if l5_values else 0.0

        # Infer direction
        direction = infer_direction(l10_avg, line)

        # Compute hit rates
        hits_l10, total_l10, pushes_l10 = compute_hit_rate(l10_values, line, direction)
        hits_h2h, total_h2h, pushes_h2h = compute_hit_rate(h2h_values, line, direction)
        hits_l5, total_l5, pushes_l5 = compute_hit_rate(l5_values, line, direction)

        # Hit rates as fractions (Half-Win model for pushes)
        rate_l10 = (hits_l10 + (0.5 * pushes_l10)) / total_l10 if total_l10 > 0 else 0.0
        rate_h2h = (hits_h2h + (0.5 * pushes_h2h)) / total_h2h if total_h2h > 0 else 0.0

        # Sample Size Penalty (L10) - hard scale down if under 8 matches
        if total_l10 > 0 and total_l10 < 8:
            rate_l10 = round(rate_l10 * (total_l10 / 10.0), 3)

        # Safety score
        if total_h2h > 0:
            safety = compute_safety_score(rate_l10, rate_h2h)
        else:
            penalty = H2H_MISSING_PENALTY.get(sport, 0.75)
            safety = round(rate_l10 * penalty, 2)

        # ONE-SIDED penalty: when one team has zero data in a combined market,
        # the combined average is unreliable — hard cap at 0.40.
        # Post-mortem 2026-05-13: 0.70 multiplier was too weak (allowed 0.56
        # for Lens corners when PSG data was missing → lost bet).
        one_sided = market.get("one_sided", False)
        if one_sided:
            ONE_SIDED_SAFETY_CAP = 0.40
            safety = min(round(safety * 0.70, 2), ONE_SIDED_SAFETY_CAP)

        # LINE REASONABLENESS CHECK: flag when line is far from data average.
        # If line < 50% of avg or line > 200% of avg, cap safety at 0.50.
        # This catches misconfigured standard lines (e.g., per-team lines used as combined).
        line_suspicious = False
        if l10_avg > 0 and line > 0:
            ratio = line / l10_avg
            if ratio < 0.50 or ratio > 2.0:
                line_suspicious = True
                safety = min(safety, 0.50)

        # Margin
        margin = compute_margin(l10_avg, line, direction)

        # Compute three-way check per market
        tw_l10_a = statistics.mean(l10_values) if l10_values else 0.0
        tw_h2h_a = statistics.mean(h2h_values) if h2h_values else 0.0
        tw_l5_a = statistics.mean(l5_values) if l5_values else 0.0
        per_market_three_way = compute_three_way_check(tw_l10_a, tw_h2h_a, tw_l5_a, line)

        results.append({
            "name": name,
            "team_a_avg": round(display_a_avg, 2),
            "team_b_avg": round(display_b_avg, 2),
            "combined_avg": round(l10_avg, 2),
            "h2h_avg": round(h2h_avg, 2) if h2h_values else None,
            "line": line,
            "direction": direction,
            "hit_rate_l10": f"{hits_l10}/{total_l10}",
            "hit_rate_h2h": f"{hits_h2h}/{total_h2h}" if total_h2h > 0 else "N/A",
            "hit_rate_l5": f"{hits_l5}/{total_l5}" if total_l5 > 0 else "N/A",
            "safety_score": safety,
            "margin": margin,
            "source": source,
            "h2h_blind": total_h2h == 0,
            "one_sided": one_sided,
            "line_suspicious": line_suspicious,
            "three_way_check": per_market_three_way,
        })

    # --- Multi-line optimization (Task 7.1) ---
    # If a market has available_lines data, optimize to find best line
    for r in results:
        mkt = next((m for m in markets if m["name"] == r["name"]), None)
        available_lines = mkt.get("available_lines") if mkt else None
        if available_lines and optimize_line is not None:
            combined_vals = compute_combined_values(mkt) if mkt else []
            avg_val = statistics.mean(combined_vals) if combined_vals else r["combined_avg"]
            std_val = statistics.stdev(combined_vals) if len(combined_vals) >= 2 else 0.0
            # Infer model: goals/corners/cards → poisson; points/totals → normal
            name_lower = r["name"].lower()
            if any(kw in name_lower for kw in ("point", "total", "score")):
                mdl = "normal"
            else:
                mdl = "poisson"
            opt = optimize_line(
                base_stat=name_lower,
                avg_value=avg_val,
                std_dev=std_val,
                available_lines=available_lines,
                model=mdl,
            )
            if opt.get("best_line") is not None:
                r["optimized_line"] = opt["best_line"]
                r["optimized_direction"] = opt["direction"]
                r["optimized_prob"] = opt["prob"]
                r["optimized_ev"] = opt["ev"]
                r["optimized_safety"] = opt["safety_score"]
                # Use optimized safety if it's better than the hit-rate safety
                if opt["ev"] is not None and opt["ev"] > 0 and opt["safety_score"] > r["safety_score"]:
                    r["safety_score"] = opt["safety_score"]
                    r["line"] = opt["best_line"]
                    r["direction"] = opt["direction"].upper()

    # --- Pattern F: Synthetic data cap (May 2026 post-mortem) ---
    # db-synthetic source = fabricated L10 values from aggregates, NOT real per-match data.
    # Safety MUST be capped at 0.50 — cannot trust synthetic distributions for probability.
    SYNTHETIC_SAFETY_CAP = 0.50
    for r in results:
        if r.get("source") == "db-synthetic" and r["safety_score"] > SYNTHETIC_SAFETY_CAP:
            r.setdefault("original_safety", r["safety_score"])
            r["safety_score"] = SYNTHETIC_SAFETY_CAP
            r["synthetic_capped"] = True
            r["synthetic_cap_reason"] = (
                f"db-synthetic source: safety capped {r['original_safety']:.2f} → {SYNTHETIC_SAFETY_CAP}"
            )

    # --- Pattern C: Sport-specific volatility caps ---
    # Baseball, hockey, etc. have high single-game variance that inflates safety
    for r in results:
        cap = SPORT_VOLATILITY_CAPS.get(sport, {}).get(_market_category(r["name"]))
        if cap is not None and r["safety_score"] > cap:
            r.setdefault("original_safety", r["safety_score"])
            r["safety_score"] = cap
            r["volatility_capped"] = True

    # --- Pattern E: Data tier caps (youth, state leagues, women's) ---
    competition_lower = competition.lower()
    tier_cap = _compute_data_tier_cap(competition_lower)
    if tier_cap < 1.0:
        for r in results:
            if r["safety_score"] > tier_cap:
                r.setdefault("original_safety", r["safety_score"])
                r["safety_score"] = round(tier_cap, 2)
                r["data_tier_capped"] = True
                r["data_tier_cap_reason"] = f"competition tier cap: {tier_cap}"

    # --- Pattern G: Evidence requirements ---
    # Safety ≥0.80 requires ≥10 L10 values AND H2H data AND 0 one-sided flags
    for r in results:
        if r["safety_score"] >= 0.80:
            l10_str = r.get("hit_rate_l10", "0/0")
            try:
                total_l10 = int(l10_str.split("/")[1]) if "/" in str(l10_str) else 0
            except (ValueError, IndexError):
                total_l10 = 0
            has_h2h = not r.get("h2h_blind", True)
            is_one_sided = r.get("one_sided", False)

            if total_l10 < 10 or not has_h2h or is_one_sided:
                r.setdefault("original_safety", r["safety_score"])
                r["safety_score"] = min(r["safety_score"], 0.70)
                r["evidence_capped"] = True
                reasons = []
                if total_l10 < 10:
                    reasons.append(f"only {total_l10} L10 games (need 10)")
                if not has_h2h:
                    reasons.append("no H2H data")
                if is_one_sided:
                    reasons.append("one-sided data")
                r["evidence_cap_reason"] = "; ".join(reasons)

    # --- Pattern I: Small sample cap (May 2026 post-mortem, bug #4) ---
    # When L10 has < 8 data points, safety is unreliable regardless of computed
    # value. WNBA Toronto Tempo had 7 games treated as reliable → lost bet.
    SMALL_SAMPLE_THRESHOLD = 8
    SMALL_SAMPLE_SAFETY_CAP = 0.50
    for r in results:
        l10_str = r.get("hit_rate_l10", "0/0")
        try:
            total_l10 = int(l10_str.split("/")[1]) if "/" in str(l10_str) else 0
        except (ValueError, IndexError):
            total_l10 = 0
        if 0 < total_l10 < SMALL_SAMPLE_THRESHOLD and r["safety_score"] > SMALL_SAMPLE_SAFETY_CAP:
            r.setdefault("original_safety", r["safety_score"])
            r["safety_score"] = SMALL_SAMPLE_SAFETY_CAP
            r["small_sample_capped"] = True
            r["small_sample_reason"] = (
                f"only {total_l10} L10 games (need ≥{SMALL_SAMPLE_THRESHOLD}) — "
                f"safety capped {r.get('original_safety', '?'):.2f} → {SMALL_SAMPLE_SAFETY_CAP}"
            )

    # --- Pattern J: Opponent Style Blocker (team-specific OVER markets) ---
    # For team-specific markets (is_combined=False, direction=OVER):
    # Check if the match's combined total suggests the team needs an outsized
    # share of activity to hit the line. If team_avg / combined_avg > 0.60,
    # the opponent's style may suppress this stat.
    # Also penalize when L5 trend is declining (below L10 by >15%).
    OPPONENT_BLOCKER_SHARE_THRESHOLD = 0.60
    OPPONENT_BLOCKER_SAFETY_CAP = 0.50
    L5_DECLINE_THRESHOLD = 0.85  # L5 < 85% of L10 → declining

    # Build lookup: stat_category → combined market's combined_avg
    combined_market_avgs: dict[str, float] = {}
    for mkt in markets:
        if mkt.get("is_combined", True):
            cat = _market_category(mkt["name"])
            a_vals = mkt.get("team_a_l10", [])
            b_vals = mkt.get("team_b_l10", [])
            if a_vals and b_vals:
                min_len = min(len(a_vals), len(b_vals))
                combo_avg = statistics.mean(
                    [a_vals[i] + b_vals[i] for i in range(min_len)]
                )
                # Also store by stat keyword for flexible matching
                name_lower = mkt["name"].lower()
                for kw in ("corner", "foul", "card", "shot", "goal", "point",
                           "rebound", "assist", "ace", "game", "set", "hit",
                           "block", "steal", "turnover", "pim"):
                    if kw in name_lower:
                        combined_market_avgs[kw] = combo_avg
                        break
                if cat:
                    combined_market_avgs[cat] = combo_avg

    for r in results:
        mkt = next((m for m in markets if m["name"] == r["name"]), None)
        if not mkt:
            continue
        is_combined = mkt.get("is_combined", True)
        if is_combined:
            continue  # Only applies to team-specific markets
        if r["direction"].upper() != "OVER":
            continue  # Only OVER lines can be blocked by defensive opponents

        # Identify stat keyword
        name_lower = r["name"].lower()
        stat_kw = None
        for kw in ("corner", "foul", "card", "shot", "goal", "point",
                   "rebound", "assist", "ace", "game", "set", "hit",
                   "block", "steal", "turnover", "pim"):
            if kw in name_lower:
                stat_kw = kw
                break

        if not stat_kw or stat_kw not in combined_market_avgs:
            continue  # No combined reference available

        combined_avg_ref = combined_market_avgs[stat_kw]
        team_avg = r["combined_avg"]  # For team-specific, this is the team's own avg

        if combined_avg_ref <= 0:
            continue

        share = team_avg / combined_avg_ref
        # Check L5 declining trend
        l5_vals = compute_combined_l5(mkt)
        l5_avg = statistics.mean(l5_vals) if l5_vals else team_avg
        l5_declining = (l5_avg < team_avg * L5_DECLINE_THRESHOLD) if team_avg > 0 else False

        # Blocker triggers: high share requirement OR declining trend with tight margin
        blocker_detected = False
        blocker_reasons = []

        if share > OPPONENT_BLOCKER_SHARE_THRESHOLD:
            blocker_detected = True
            blocker_reasons.append(
                f"needs {share:.0%} of match total ({team_avg:.1f}/{combined_avg_ref:.1f})"
            )

        if l5_declining and r["margin"] < 0.5:
            blocker_detected = True
            blocker_reasons.append(
                f"L5 declining ({l5_avg:.1f} vs L10 {team_avg:.1f})"
            )

        if blocker_detected:
            r["opponent_blocker"] = True
            r["opponent_blocker_reason"] = "; ".join(blocker_reasons)
            if r["safety_score"] > OPPONENT_BLOCKER_SAFETY_CAP:
                r.setdefault("original_safety", r["safety_score"])
                r["safety_score"] = OPPONENT_BLOCKER_SAFETY_CAP
        else:
            r["opponent_blocker"] = False

    # Sort by safety score (desc), margin as tiebreaker (desc)
    results.sort(key=lambda x: (x["safety_score"], x["margin"]), reverse=True)

    # Add rank
    for i, r in enumerate(results, 1):
        r["rank"] = i

    # Best market
    best = results[0] if results else None

    # Three-way cross-check for best market
    three_way = None
    if best:
        best_market = next(
            (m for m in markets if m["name"] == best["name"]), None
        )
        if best_market:
            l10_vals = compute_combined_values(best_market)
            l5_vals = compute_combined_l5(best_market)
            h2h_vals = best_market.get("h2h_values", [])

            l10_a = statistics.mean(l10_vals) if l10_vals else 0.0
            h2h_a = statistics.mean(h2h_vals) if h2h_vals else 0.0
            l5_a = statistics.mean(l5_vals) if l5_vals else 0.0

            three_way = compute_three_way_check(l10_a, h2h_a, l5_a, best["line"])
            three_way["market"] = best["name"]

    # Check minimum markets
    min_required = MIN_MARKETS.get(sport, 3)
    warnings = []
    if len(results) < min_required:
        warnings.append(
            f"INSUFFICIENT_MARKETS: {len(results)} markets evaluated, "
            f"minimum {min_required} required for {sport}"
        )

    # --- Pattern H: High-stakes context warning ---
    high_stakes = _detect_high_stakes_context(competition)
    if high_stakes:
        warnings.append(high_stakes["message"])
        # Apply safety discount to ALL markets for this fixture
        discount = high_stakes["safety_discount"]
        for r in results:
            r.setdefault("original_safety", r["safety_score"])
            r["safety_score"] = round(r["safety_score"] * discount, 2)
            r["high_stakes_discounted"] = True

    return {
        "candidate": f"{team_a} vs {team_b}",
        "sport": sport,
        "competition": competition,
        "markets_evaluated": len(results),
        "min_required": min_required,
        "ranking": results,
        "three_way_check": three_way,
        "recommended_market": (
            f"{best['name']} {best['line']} ({best['direction']})"
            if best
            else None
        ),
        "recommended_safety": best["safety_score"] if best else None,
        "warnings": warnings,
        "high_stakes_context": high_stakes,
        "markdown_ranking_table": generate_ranking_markdown(results),
        "markdown_three_way_table": generate_three_way_markdown(three_way) if three_way else "",
    }


def generate_ranking_markdown(ranking: list[dict]) -> str:
    """Generate §S3.3-compatible markdown ranking table."""
    lines = []
    lines.append(
        "| # | Market | TeamA avg | TeamB avg | H2H avg | Line | "
        "Hit L10 | Hit H2H | Safety | Source |"
    )
    lines.append(
        "|---|--------|-----------|-----------|---------|------|"
        "---------|---------|--------|--------|"
    )

    for r in ranking:
        h2h = f"{r['h2h_avg']}" if r["h2h_avg"] is not None else "N/A (H2H-BLIND)"
        lines.append(
            f"| {r['rank']} | {r['name']} | {r['team_a_avg']} | {r['team_b_avg']} | "
            f"{h2h} | {r['line']} | {r['hit_rate_l10']} | {r['hit_rate_h2h']} | "
            f"{r['safety_score']:.2f} | {r['source']} |"
        )

    if ranking:
        best = ranking[0]
        lines.append(
            f"SELECTED MARKET: Row {best['rank']} — {best['name']} "
            f"(highest safety score: {best['safety_score']:.2f})"
        )

    return "\n".join(lines)


def generate_three_way_markdown(tw: dict) -> str:
    """Generate §S3.4-compatible three-way cross-check table."""
    lines = []
    lines.append(
        "| Check | Value | vs Line | Hit Rate | Direction |"
    )
    lines.append(
        "|-------|-------|---------|----------|-----------|"
    )

    lines.append(
        f"| L10 avg | {tw['l10_avg']} | {tw['l10_direction']} {tw['line']} | — | "
        f"{'SUPPORTS' if 'SUPPORT' in tw['alignment'] else 'CONFLICTS'} |"
    )

    h2h_val = tw["h2h_avg"] if tw["h2h_avg"] is not None else "N/A"
    h2h_dir = tw["h2h_direction"]
    lines.append(
        f"| H2H avg | {h2h_val} | {h2h_dir} {tw['line']} | — | "
        f"{'SUPPORTS' if h2h_dir == tw['l10_direction'] else 'CONFLICTS'} |"
    )

    lines.append(
        f"| L5 trend | {tw['l5_avg']} | {tw['l5_trend']} | — | "
        f"{tw['l5_trend']} |"
    )

    lines.append(f"ALIGNMENT: {tw['alignment']}")

    return "\n".join(lines)


def lookup_tennis_elo(player_name: str, surface: str = "") -> dict | None:
    """Look up Elo rating from tennis_elo cache.

    Returns dict with keys: elo, hard_elo, clay_elo, grass_elo, peak_elo,
    official_rank, tour — or None if not found.
    """
    cache_dir = Path(__file__).parent.parent / "betting" / "data" / "stats_cache" / "tennis_elo"
    if not cache_dir.exists():
        return None

    for tour_file in cache_dir.glob("*_elo.json"):
        try:
            data = json.loads(tour_file.read_text(encoding="utf-8"))
            players = data.get("players", [])
            for entry in players:
                if _fuzzy_player_match(player_name, entry.get("home", "")):
                    result = {"elo": entry.get("elo_rating"), "tour": entry.get("tour")}
                    for key in ("hard_elo", "clay_elo", "grass_elo", "peak_elo", "official_rank"):
                        if key in entry:
                            result[key] = entry[key]
                    if surface:
                        result["surface_elo"] = entry.get(f"{surface}_elo")
                    return result
        except (json.JSONDecodeError, OSError):
            continue

    return None


def _fuzzy_player_match(query: str, candidate: str) -> bool:
    """Fuzzy match for player names (last name + first initial)."""
    if not query or not candidate:
        return False
    q = query.strip().lower()
    c = candidate.strip().lower()
    if q == c:
        return True
    q_parts = q.split()
    c_parts = c.split()
    if not q_parts or not c_parts:
        return False
    # Last name must match
    if q_parts[-1] != c_parts[-1]:
        return False
    # If both have first name/initial, check first letter matches
    if len(q_parts) >= 2 and len(c_parts) >= 2:
        return q_parts[0][0] == c_parts[0][0]
    return True  # single-name fallback


def main():
    parser = argparse.ArgumentParser(
        description="Compute §3.0 safety score ranking from structured stats data.",
        epilog=INPUT_SCHEMA,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to JSON file with structured stats data",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Output markdown tables only (for pasting into S3 output)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate input structure only, don't compute",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(json.dumps({"error": f"File not found: {args.input}"}), file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        sys.exit(1)

    # Validate input
    errors = validate_input(data)
    if errors:
        print(json.dumps({"validation_errors": errors}, indent=2), file=sys.stderr)
        sys.exit(1)

    if args.validate_only:
        print(json.dumps({"status": "VALID", "markets": len(data.get("markets", []))}))
        sys.exit(0)

    # Compute rankings
    result = rank_markets(data)

    if args.markdown:
        print(result["markdown_ranking_table"])
        if result["markdown_three_way_table"]:
            print()
            print(result["markdown_three_way_table"])
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))

    # Exit with warning if insufficient markets
    if result["warnings"]:
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
