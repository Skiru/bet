"""Probability Engine (S3) — Poisson / hit rate modeling for sport events."""
from __future__ import annotations

import math
from typing import Any

def poisson_pmf(k: int, lam: float) -> float:
    """Calculate Poisson Probability Mass Function (PMF)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    try:
        return (math.pow(lam, k) * math.exp(-lam)) / math.factorial(k)
    except OverflowError:
        return 0.0


def poisson_cdf(k: int, lam: float) -> float:
    """Calculate Poisson Cumulative Distribution Function (CDF): P(X <= k)."""
    if lam <= 0:
        return 1.0
    total = 0.0
    for i in range(k + 1):
        total += poisson_pmf(i, lam)
    return min(total, 1.0)


def _parse_hit_rate(val: Any) -> float | None:
    if val in (None, "", "N/A"):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip()
    if "/" in val_str:
        try:
            parts = val_str.split("/")
            if len(parts) == 2:
                num = float(parts[0])
                den = float(parts[1])
                if den > 0:
                    return num / den
        except (ValueError, ZeroDivisionError):
            pass
    else:
        try:
            return float(val_str)
        except ValueError:
            pass
    return None


def enrich_ranking_with_probabilities(ranking_result: dict[str, Any]) -> dict[str, Any]:
    """Enrich the ranked markets in ranking_result with real statistical probability data."""
    ranking = ranking_result.get("ranking") or []
    markets_input = ranking_result.get("_markets_input") or []

    # Map input markets by (name, line, direction) for easy lookup
    input_map = {}
    for m in markets_input:
        key = (
            str(m.get("name")).lower(),
            float(m.get("line") or 0.0),
            str(m.get("direction")).upper(),
        )
        input_map[key] = m

    for r in ranking:
        name = r.get("name") or ""
        line_val = float(r.get("line") or 0.0)
        direction = str(r.get("direction") or "OVER").upper()

        m_key = (name.lower(), line_val, direction)
        m_input = input_map.get(m_key)

        # Initialize defaults
        prob = None
        lam = 0.0
        model_used = "S3_HIT_RATE_PROXY"

        if m_input:
            team_a_l10 = m_input.get("team_a_l10") or []
            team_b_l10 = m_input.get("team_b_l10") or []
            is_combined = m_input.get("is_combined", True)

            # Determine average stats for Poisson modeling if enough sample points exist
            has_enough_data = False
            if is_combined:
                has_enough_data = len(team_a_l10) >= 5 and len(team_b_l10) >= 5
            else:
                has_enough_data = len(team_a_l10) >= 5

            if has_enough_data:
                avg_a = sum(team_a_l10) / len(team_a_l10)
                avg_b = sum(team_b_l10) / len(team_b_l10) if team_b_l10 else 0.0

                name_lower = name.lower()
                is_goal = any(kw in name_lower for kw in ("goal", "total", "over", "under"))
                is_corner = "corner" in name_lower
                is_card = any(kw in name_lower for kw in ("card", "booking"))
                is_shot = "shot" in name_lower

                if is_goal or is_corner or is_card or is_shot:
                    # Let's use Poisson modeling
                    model_used = "S3_TEAM_FORM_CONTEXTUAL_PROXY"
                    lam = avg_a + avg_b  # combined Poisson rate
                    if lam > 0:
                        # Find nearest integer for the line to compute Poisson CDF/SF
                        k = int(math.floor(line_val))
                        if direction == "OVER":
                            prob = 1.0 - poisson_cdf(k, lam)
                        else:  # UNDER
                            prob = poisson_cdf(k, lam)

                elif any(kw in name_lower for kw in ("moneyline", "match winner", "winner", "ml", "draw_no_bet", "double_chance")):
                    # RESULT match winner Poisson goal model
                    model_used = "S3_TEAM_FORM_CONTEXTUAL_PROXY"
                    # We compute probabilities of home_goals X_A ~ Poisson(avg_a), away_goals X_B ~ Poisson(avg_b)
                    # Let's evaluate outcomes up to 10 goals
                    p_home = 0.0
                    p_draw = 0.0
                    p_away = 0.0
                    for g_a in range(11):
                        for g_b in range(11):
                            p_joint = poisson_pmf(g_a, avg_a) * poisson_pmf(g_b, avg_b)
                            if g_a > g_b:
                                p_home += p_joint
                            elif g_a == g_b:
                                p_draw += p_joint
                            else:
                                p_away += p_joint

                    # Normalize
                    tot = p_home + p_draw + p_away
                    if tot > 0:
                        p_home /= tot
                        p_draw /= tot
                        p_away /= tot

                    # Map probability to specific pick
                    outcome = str(r.get("outcome") or r.get("pick") or "home").lower()
                    if "home" in outcome or outcome == "1":
                        prob = p_home
                    elif "away" in outcome or outcome == "2":
                        prob = p_away
                    else:
                        prob = p_draw

        # Fallback to hit rate if Poisson cannot be computed
        if prob is None:
            model_used = "S3_HIT_RATE_PROXY"
            hit_l10 = _parse_hit_rate(r.get("hit_rate_l10"))
            hit_h2h = _parse_hit_rate(r.get("hit_rate_h2h"))
            if hit_l10 is not None and hit_h2h is not None:
                prob = (hit_l10 + hit_h2h) / 2.0
            elif hit_l10 is not None:
                prob = hit_l10
            else:
                prob = None  # Insufficient sample / missing fields - do not fake

        if prob is not None:
            # Guarantee bounds [0.01, 0.99]
            prob = max(0.01, min(0.99, prob))
            r["probability"] = round(prob, 4)
            r["fair_odds"] = round(1.0 / prob, 2)
            r["lambda"] = round(lam, 4)
            r["model_used"] = model_used
        else:
            r["probability"] = None
            r["fair_odds"] = None
            r["lambda"] = round(lam, 4)
            r["model_used"] = None

    return ranking_result
