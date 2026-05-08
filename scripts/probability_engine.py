#!/usr/bin/env python3
"""Probability Engine — converts raw stats into true probability, fair odds, and real EV.

Methodology:
- Count markets (corners, fouls, cards, goals, games, frames, etc.) modeled via Poisson distribution
- λ (expected value) computed with recency weighting: 40% L5 + 35% L10 + 25% H2H
- P(Over X.5) = 1 - CDF(X, λ) = 1 - Σ(k=0..X) [e^(-λ) × λ^k / k!]
- Fair odds = 1 / probability (before bookmaker margin)
- True EV = (probability × betclic_odds) - 1
- Confidence interval via bootstrap resampling of match-level data

Academic grounding:
- Poisson model for football: Maher (1982), Dixon & Coles (1997)
- Generalized to all count-based sports markets
- Kelly criterion: Kelly (1956), applied at 1/4 for variance reduction
- Recency weighting: empirically determined, reflects squad/tactical changes

Usage:
    python3 scripts/probability_engine.py --input safety_input.json
    python3 scripts/probability_engine.py --test

    # As library:
    from probability_engine import compute_probability, compute_ev, enrich_market_with_probability
"""

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Optional scipy — used for normal-distribution line optimization
try:
    from scipy.stats import poisson as scipy_poisson, norm as scipy_norm
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

# ---------------------------------------------------------------------------
# Recency weights for λ estimation
# ---------------------------------------------------------------------------
# L5 (last 5 matches) captures current form, most predictive
# L10 (last 10 matches) captures season trend
# H2H captures specific matchup dynamics (e.g., pressing team = more corners vs low block)
WEIGHT_L5 = 0.40
WEIGHT_L10 = 0.35
WEIGHT_H2H = 0.25

# When H2H is missing, redistribute weight
WEIGHT_L5_NO_H2H = 0.55
WEIGHT_L10_NO_H2H = 0.45

# Overdispersion threshold — if variance/mean > this, use negative binomial
OVERDISPERSION_THRESHOLD = 1.5

# Bootstrap parameters for confidence intervals
BOOTSTRAP_SAMPLES = 1000
CONFIDENCE_LEVEL = 0.90  # 90% CI


# ---------------------------------------------------------------------------
# Poisson distribution functions
# ---------------------------------------------------------------------------

def poisson_pmf(k: int, lam: float) -> float:
    """Poisson probability mass function: P(X = k) = e^(-λ) × λ^k / k!

    Uses log-space computation to avoid overflow for large λ (e.g., basketball totals).
    """
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    # log(P) = k*log(λ) - λ - log(k!)
    log_p = k * math.log(lam) - lam - math.lgamma(k + 1)
    return math.exp(log_p)


def poisson_cdf(x: int, lam: float) -> float:
    """Poisson cumulative distribution: P(X ≤ x) = Σ(k=0..x) PMF(k, λ)"""
    if lam <= 0:
        return 1.0
    return sum(poisson_pmf(k, lam) for k in range(x + 1))


def poisson_over(line: float, lam: float) -> float:
    """P(Over line) where line has .5 (e.g., Over 9.5 corners).

    P(X > 9.5) = P(X ≥ 10) = 1 - P(X ≤ 9) = 1 - CDF(9, λ)
    """
    threshold = int(line)  # 9.5 → 9
    return 1.0 - poisson_cdf(threshold, lam)


def poisson_under(line: float, lam: float) -> float:
    """P(Under line) where line has .5 (e.g., Under 9.5 corners).

    P(X < 9.5) = P(X ≤ 9) = CDF(9, λ)
    """
    threshold = int(line)
    return poisson_cdf(threshold, lam)


# ---------------------------------------------------------------------------
# Negative binomial (for overdispersed data like goals)
# ---------------------------------------------------------------------------

def _negbin_pmf(k: int, r: float, p: float) -> float:
    """Negative binomial PMF using r (dispersion) and p (success probability).

    P(X=k) = C(k+r-1, k) × p^r × (1-p)^k
    Uses gamma function for non-integer r.
    """
    if r <= 0 or p <= 0 or p > 1:
        return 0.0
    try:
        log_coeff = (
            math.lgamma(k + r) - math.lgamma(k + 1) - math.lgamma(r)
        )
        log_prob = r * math.log(p) + k * math.log(1 - p)
        return math.exp(log_coeff + log_prob)
    except (ValueError, OverflowError):
        return 0.0


def negbin_cdf(x: int, r: float, p: float) -> float:
    """Negative binomial CDF: P(X ≤ x)."""
    return sum(_negbin_pmf(k, r, p) for k in range(x + 1))


def negbin_over(line: float, r: float, p: float) -> float:
    """P(Over line) using negative binomial."""
    threshold = int(line)
    return 1.0 - negbin_cdf(threshold, r, p)


def _fit_negbin_params(mean: float, var: float) -> tuple[float, float]:
    """Estimate negative binomial r, p from mean and variance.

    mean = r(1-p)/p → p = r/(r+mean)
    var = r(1-p)/p² → r = mean²/(var - mean)
    """
    if var <= mean or mean <= 0:
        # Not overdispersed or invalid — fallback to Poisson-like
        return mean, 0.5  # Won't be used
    r = (mean * mean) / (var - mean)
    p = r / (r + mean)
    return r, p


# ---------------------------------------------------------------------------
# λ estimation with recency weighting
# ---------------------------------------------------------------------------

def estimate_lambda(
    l10_values: list[float],
    l5_values: list[float] | None = None,
    h2h_values: list[float] | None = None,
) -> float:
    """Compute weighted λ from L10, L5, and H2H data.

    Weights: L5=0.40, L10=0.35, H2H=0.25
    When H2H is missing: L5=0.55, L10=0.45
    """
    if not l10_values:
        return 0.0

    l10_avg = statistics.mean(l10_values)
    l5_avg = statistics.mean(l5_values) if l5_values else statistics.mean(l10_values[-5:])

    if h2h_values and len(h2h_values) >= 2:
        h2h_avg = statistics.mean(h2h_values)
        lam = WEIGHT_L5 * l5_avg + WEIGHT_L10 * l10_avg + WEIGHT_H2H * h2h_avg
    else:
        lam = WEIGHT_L5_NO_H2H * l5_avg + WEIGHT_L10_NO_H2H * l10_avg

    return max(lam, 0.01)  # Prevent zero λ


def check_overdispersion(values: list[float]) -> bool:
    """Check if data is overdispersed (variance >> mean)."""
    if len(values) < 3:
        return False
    mean = statistics.mean(values)
    if mean <= 0:
        return False
    var = statistics.variance(values)
    return (var / mean) > OVERDISPERSION_THRESHOLD


# ---------------------------------------------------------------------------
# Core probability computation
# ---------------------------------------------------------------------------

def compute_probability(
    line: float,
    direction: str,
    l10_values: list[float],
    l5_values: list[float] | None = None,
    h2h_values: list[float] | None = None,
    use_negbin: bool | None = None,
    competition: str = "",
    stat_key: str = "",
) -> dict:
    """Compute probability for Over/Under a line.

    Args:
        line: betting line (e.g., 9.5, 22.5, 2.5)
        direction: "OVER" or "UNDER"
        l10_values: last 10 match values for this stat (combined if total market)
        l5_values: last 5 match values (optional, derived from l10 if missing)
        h2h_values: H2H match values (optional)
        use_negbin: force negative binomial (None = auto-detect)
        competition: league/competition name for league profile lookup
        stat_key: stat identifier (e.g. 'corners', 'goals') for league profile

    Returns:
        dict with probability, fair_odds, lambda, model_used, confidence_interval
    """
    if not l10_values:
        return {
            "probability": None,
            "fair_odds": None,
            "lambda": None,
            "model_used": "none",
            "confidence_interval": None,
            "error": "no_data",
        }

    lam = estimate_lambda(l10_values, l5_values, h2h_values)

    # Apply Bayesian shrinkage toward league average when sample is small
    if competition or stat_key:
        profile = load_league_profiles(competition=competition, stat_key=stat_key)
        if profile:
            league_avg = profile.get("avg_value", 0)
            league_std = profile.get("std_dev", 1)
            if league_avg > 0:
                team_games = len(l10_values)
                lam = bayesian_adjusted_average(
                    team_avg=lam,
                    team_games=team_games,
                    league_avg=league_avg,
                    league_std=league_std,
                )

    # Determine model
    all_values = list(l10_values)
    if h2h_values:
        all_values.extend(h2h_values)

    if use_negbin is None:
        use_negbin = check_overdispersion(all_values)

    if use_negbin and len(all_values) >= 3:
        # Use the recency-weighted λ as mean (consistent with Poisson path)
        # but variance from raw data (captures true dispersion)
        mean_val = lam
        var_val = statistics.variance(all_values)
        r, p = _fit_negbin_params(mean_val, var_val)
        if direction.upper() == "OVER":
            prob = negbin_over(line, r, p)
        else:
            prob = 1.0 - negbin_over(line, r, p)
        model = "negative_binomial"
    else:
        if direction.upper() == "OVER":
            prob = poisson_over(line, lam)
        else:
            prob = poisson_under(line, lam)
        model = "poisson"

    # Clamp probability to reasonable range
    prob = max(0.01, min(0.99, prob))
    fair_odds = round(1.0 / prob, 3)

    # Bootstrap confidence interval
    ci = _bootstrap_ci(l10_values, l5_values, h2h_values, line, direction, model)

    return {
        "probability": round(prob, 4),
        "fair_odds": fair_odds,
        "lambda": round(lam, 3),
        "model_used": model,
        "confidence_interval": ci,
    }


def _bootstrap_ci(
    l10_values: list[float],
    l5_values: list[float] | None,
    h2h_values: list[float] | None,
    line: float,
    direction: str,
    model: str,
) -> dict | None:
    """Bootstrap 90% confidence interval for probability estimate."""
    if len(l10_values) < 5:
        return None

    probs = []
    for _ in range(BOOTSTRAP_SAMPLES):
        # Resample with replacement
        boot_l10 = random.choices(l10_values, k=len(l10_values))
        boot_l5 = random.choices(l5_values, k=len(l5_values)) if l5_values else None
        boot_h2h = random.choices(h2h_values, k=len(h2h_values)) if h2h_values and len(h2h_values) >= 2 else None

        boot_lam = estimate_lambda(boot_l10, boot_l5, boot_h2h)

        if model == "negative_binomial":
            boot_all = boot_l10 + (boot_h2h or [])
            if len(boot_all) >= 3:
                boot_mean = statistics.mean(boot_all)
                boot_var = statistics.variance(boot_all)
                boot_r, boot_p = _fit_negbin_params(boot_mean, boot_var)
                if direction.upper() == "OVER":
                    p = negbin_over(line, boot_r, boot_p)
                else:
                    p = 1.0 - negbin_over(line, boot_r, boot_p)
            else:
                p = poisson_over(line, boot_lam) if direction.upper() == "OVER" else poisson_under(line, boot_lam)
        else:
            if direction.upper() == "OVER":
                p = poisson_over(line, boot_lam)
            else:
                p = poisson_under(line, boot_lam)
        probs.append(max(0.01, min(0.99, p)))

    probs.sort()
    lower_idx = int(BOOTSTRAP_SAMPLES * (1 - CONFIDENCE_LEVEL) / 2)
    upper_idx = int(BOOTSTRAP_SAMPLES * (1 + CONFIDENCE_LEVEL) / 2)

    return {
        "lower": round(probs[lower_idx], 4),
        "upper": round(probs[upper_idx], 4),
        "level": CONFIDENCE_LEVEL,
    }


# ---------------------------------------------------------------------------
# EV computation
# ---------------------------------------------------------------------------

def compute_ev(probability: float, bookmaker_odds: float) -> float:
    """True EV = (probability × odds) - 1.

    EV > 0 = positive expected value = worth betting.
    Example: P=0.60, odds=1.80 → EV = 0.60 × 1.80 - 1 = 0.08 (+8%)
    """
    return round(probability * bookmaker_odds - 1.0, 4)


def compute_kelly_fraction(probability: float, odds: float) -> float:
    """Full Kelly fraction: f = (b×p - q) / b where b=odds-1, p=probability, q=1-p.

    Returns fraction of bankroll (before 1/4 Kelly reduction).
    """
    b = odds - 1.0
    if b <= 0:
        return 0.0
    p = probability
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, round(f, 4))


def compute_kelly_quarter(probability: float, odds: float, bankroll: float) -> float:
    """1/4 Kelly stake in currency units."""
    f = compute_kelly_fraction(probability, odds)
    return round(bankroll * f / 4.0, 2)


# ---------------------------------------------------------------------------
# Market enrichment — integrates with compute_safety_scores.py output
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Weather impact quantification (Task 7.3)
# ---------------------------------------------------------------------------

WEATHER_MODIFIERS = {
    # (stat, condition) → multiplier
    ("corners", "rain"): 1.08,          # More corners in rain (slippery, more errors)
    ("corners", "heavy_rain"): 1.12,
    ("corners", "wind"): 1.05,           # Wind causes more wayward shots → corners
    ("goals", "rain"): 0.92,             # Fewer goals in rain
    ("goals", "heavy_rain"): 0.85,
    ("cards", "rain"): 1.10,             # More fouls on slippery pitch
    ("aces", "wind"): 0.88,              # Fewer aces in wind (tennis)
    ("aces", "indoor"): 1.05,            # Indoor = more aces (consistent bounce)
    ("totals_points", "altitude"): 1.03, # High altitude = faster ball (tennis)
}


def apply_weather_modifier(stat: str, base_value: float, weather: dict | None) -> float:
    """Apply weather-based modifier to a statistical average.

    Args:
        stat: stat key (e.g. "corners", "goals", "cards", "aces")
        base_value: the unmodified λ or average
        weather: dict from fetch_weather.py with 'conditions', 'wind_max_kmh', 'flags' etc.

    Returns:
        Modified base_value (unchanged if no weather data or no applicable modifier).
    """
    if not weather:
        return base_value

    condition = weather.get("conditions", "").lower()
    key = None

    # Map condition to our categories
    if "heavy rain" in condition or "thunderstorm" in condition:
        key = (stat, "heavy_rain")
    elif "rain" in condition or "drizzle" in condition:
        key = (stat, "rain")
    elif "wind" in condition:
        wind_speed = weather.get("wind_max_kmh", 0) or 0
        if wind_speed > 30:
            key = (stat, "wind")
    else:
        # Check flags for wind even if conditions text doesn't mention it
        flags = weather.get("flags", [])
        wind_speed = weather.get("wind_max_kmh", 0) or 0
        if wind_speed > 30 or "WIND_STRONG" in flags:
            key = (stat, "wind")

    if key and key in WEATHER_MODIFIERS:
        return base_value * WEATHER_MODIFIERS[key]

    return base_value


# ---------------------------------------------------------------------------
# Bayesian adjusted average (Task 7.2)
# ---------------------------------------------------------------------------

def bayesian_adjusted_average(
    team_avg: float,
    team_games: int,
    league_avg: float,
    league_std: float,
    prior_weight: int = 5,
) -> float:
    """Bayesian shrinkage: pull team average toward league average.

    With 0 team games: returns league_avg.
    With many team games: returns ~team_avg.
    Weight formula: adjusted = (team_games * team_avg + prior_weight * league_avg)
                               / (team_games + prior_weight)
    """
    return (team_games * team_avg + prior_weight * league_avg) / (team_games + prior_weight)


def load_league_profiles(competition: str = "", stat_key: str = "") -> dict | None:
    """Load league profile data from DB (preferred) or JSON fallback.

    Returns dict with 'avg_value', 'std_dev', 'sample_size' or None if unavailable.
    """
    # Try DB first
    db_path = ROOT_DIR / "betting" / "data" / "betting.db"
    if db_path.exists():
        try:
            from bet.db.connection import get_db

            with get_db(db_path) as conn:
                row = conn.execute(
                    "SELECT avg_value, std_dev, sample_size FROM league_profiles "
                    "WHERE stat_key = ? LIMIT 1",
                    (stat_key,),
                ).fetchone()
                if row:
                    return {
                        "avg_value": row["avg_value"],
                        "std_dev": row["std_dev"],
                        "sample_size": row["sample_size"],
                    }
        except Exception:
            pass

    # Fallback to JSON
    json_path = ROOT_DIR / "betting" / "data" / "league_profiles.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            # JSON keyed by competition→stat or flat by stat
            if competition and competition in data:
                entry = data[competition].get(stat_key)
            elif stat_key in data:
                entry = data[stat_key]
            else:
                entry = None
            if isinstance(entry, dict):
                return entry
        except (json.JSONDecodeError, OSError):
            pass

    return None


# ---------------------------------------------------------------------------
# Multi-line optimization (Task 7.1)
# ---------------------------------------------------------------------------

def _normal_sf(x: float, loc: float, scale: float) -> float:
    """Survival function P(X > x) for normal distribution. Uses scipy if available."""
    if HAS_SCIPY:
        return float(scipy_norm.sf(x, loc=loc, scale=scale))
    # Fallback: use error function approximation
    if scale <= 0:
        return 0.0 if x >= loc else 1.0
    z = (x - loc) / scale
    return 0.5 * math.erfc(z / math.sqrt(2))


def _poisson_sf(k: int, mu: float) -> float:
    """Survival function P(X > k) for Poisson distribution. Uses scipy if available."""
    if HAS_SCIPY:
        return float(scipy_poisson.sf(k, mu))
    # Fallback: use our existing functions
    return 1.0 - poisson_cdf(k, mu)


def optimize_line(
    base_stat: str,
    avg_value: float,
    std_dev: float,
    available_lines: list[dict],
    model: str = "poisson",
) -> dict:
    """Find the line with best safety×EV for a statistical market.

    Args:
        base_stat: stat key e.g. "corners", "goals", "points"
        avg_value: L10 average (e.g. 10.8)
        std_dev: standard deviation of the sample
        available_lines: list of dicts with keys 'line', 'odds_over', 'odds_under'
        model: "poisson" (goals, corners, cards) or "normal" (points, totals)

    Returns:
        dict with best_line, direction, prob, ev, safety_score, all_lines
    """
    all_results = []

    for entry in available_lines:
        line = entry.get("line")
        odds_over = entry.get("odds_over")
        odds_under = entry.get("odds_under")

        if line is None:
            continue

        for direction, odds in [("over", odds_over), ("under", odds_under)]:
            if not odds or odds <= 1.0:
                continue

            # Compute probability
            if model == "poisson":
                threshold = int(line)
                if direction == "over":
                    prob = _poisson_sf(threshold, avg_value)
                else:
                    prob = poisson_cdf(threshold, avg_value)
            else:  # normal
                if std_dev <= 0:
                    continue
                if direction == "over":
                    prob = _normal_sf(line, avg_value, std_dev)
                else:
                    prob = 1.0 - _normal_sf(line, avg_value, std_dev)

            prob = max(0.01, min(0.99, prob))
            ev = prob * odds - 1.0
            safety_contribution = min(prob * 10, 10.0)

            all_results.append({
                "line": line,
                "direction": direction,
                "odds": odds,
                "prob": round(prob, 4),
                "ev": round(ev, 4),
                "safety_score": round(safety_contribution, 2),
            })

    if not all_results:
        return {
            "best_line": None,
            "direction": None,
            "prob": None,
            "ev": None,
            "safety_score": None,
            "all_lines": [],
        }

    # Filter to EV > 0, then pick highest safety_contribution
    positive_ev = [r for r in all_results if r["ev"] > 0]

    if positive_ev:
        best = max(positive_ev, key=lambda r: r["safety_score"])
    else:
        # No +EV line — return the one closest to 0 EV with highest safety
        best = max(all_results, key=lambda r: (r["safety_score"], r["ev"]))

    return {
        "best_line": best["line"],
        "direction": best["direction"],
        "prob": best["prob"],
        "ev": best["ev"],
        "safety_score": best["safety_score"],
        "all_lines": all_results,
    }


# ---------------------------------------------------------------------------
# Tennis Elo integration (Task 7.4)
# ---------------------------------------------------------------------------

def elo_win_probability(elo_home: float, elo_away: float) -> float:
    """Expected win probability from Elo ratings.

    Standard Elo formula: E(A) = 1 / (1 + 10^((Rb - Ra) / 400))
    """
    return 1.0 / (1.0 + 10 ** ((elo_away - elo_home) / 400.0))


def elo_adjusted_lambda(
    base_lambda: float,
    player_elo: float,
    opponent_elo: float,
    stat: str = "games",
) -> float:
    """Adjust λ for a statistical market based on Elo difference.

    Higher Elo → more likely to win games/sets → adjust λ upward.
    ±100 Elo ≈ ±5% on λ. Clamped to ±15%.
    """
    elo_diff = player_elo - opponent_elo
    adjustment_factor = 1.0 + (elo_diff / 2000.0)
    adjustment_factor = max(0.85, min(1.15, adjustment_factor))
    return base_lambda * adjustment_factor


def load_tennis_elo(date: str) -> dict:
    """Load tennis Elo ratings from cache if available.

    Checks for date-specific file first, falls back to latest.
    Returns dict keyed by player name → Elo rating, or empty dict.
    """
    elo_path = ROOT_DIR / "betting" / "data" / f"tennis_elo_{date}.json"
    if not elo_path.exists():
        elo_path = ROOT_DIR / "betting" / "data" / "tennis_elo_latest.json"
    if elo_path.exists():
        try:
            return json.loads(elo_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Market enrichment — integrates with compute_safety_scores.py output
# ---------------------------------------------------------------------------

def enrich_market_with_probability(market: dict) -> dict:
    """Add probability fields to an existing market ranking entry.

    Expects market dict with: team_a_l10, team_b_l10, h2h_values, line,
    is_combined, team_a_l5, team_b_l5, direction.

    Adds: probability, fair_odds, lambda, model_used, true_ev, kelly_fraction.
    """
    is_combined = market.get("is_combined", True)
    a_l10 = market.get("team_a_l10", [])
    b_l10 = market.get("team_b_l10", [])
    a_l5 = market.get("team_a_l5", a_l10[-5:] if a_l10 else [])
    b_l5 = market.get("team_b_l5", b_l10[-5:] if b_l10 else [])
    h2h = market.get("h2h_values", [])
    line = market.get("line", 0)
    direction = market.get("direction", "OVER")

    if is_combined:
        min_len_l10 = min(len(a_l10), len(b_l10))
        combined_l10 = [a_l10[i] + b_l10[i] for i in range(min_len_l10)]
        min_len_l5 = min(len(a_l5), len(b_l5))
        combined_l5 = [a_l5[i] + b_l5[i] for i in range(min_len_l5)]
    else:
        combined_l10 = list(a_l10)
        combined_l5 = list(a_l5)

    result = compute_probability(
        line=line,
        direction=direction,
        l10_values=combined_l10,
        l5_values=combined_l5 if combined_l5 else None,
        h2h_values=h2h if h2h else None,
    )

    market["probability"] = result["probability"]
    market["fair_odds"] = result["fair_odds"]
    market["lambda"] = result["lambda"]
    market["model_used"] = result["model_used"]
    market["confidence_interval"] = result.get("confidence_interval")

    # Compute true EV if bookmaker odds available
    bk_odds = market.get("bookmaker_odds") or market.get("odds")
    if bk_odds and result["probability"]:
        market["true_ev"] = compute_ev(result["probability"], bk_odds)
        market["kelly_fraction"] = compute_kelly_fraction(result["probability"], bk_odds)
    else:
        market["true_ev"] = None
        market["kelly_fraction"] = None

    return market


def enrich_ranking_with_probabilities(ranking_result: dict) -> dict:
    """Enrich an entire rank_markets() output with probability data.

    Takes the output of compute_safety_scores.rank_markets() and adds
    probability columns to each ranked market.

    This is called from deep_stats_report.py after rank_markets().
    """
    markets_input = ranking_result.get("_markets_input", [])
    ranking = ranking_result.get("ranking", [])

    # Build lookup from market name to input data
    input_lookup = {}
    for m in markets_input:
        input_lookup[m.get("name", "")] = m

    for ranked_market in ranking:
        name = ranked_market.get("name", "")
        input_data = input_lookup.get(name, {})

        if input_data:
            # Compute probability from raw data
            is_combined = input_data.get("is_combined", True)
            a_l10 = input_data.get("team_a_l10", [])
            b_l10 = input_data.get("team_b_l10", [])
            a_l5 = input_data.get("team_a_l5", a_l10[-5:] if a_l10 else [])
            b_l5 = input_data.get("team_b_l5", b_l10[-5:] if b_l10 else [])
            h2h = input_data.get("h2h_values", [])

            if is_combined:
                min_len = min(len(a_l10), len(b_l10))
                l10 = [a_l10[i] + b_l10[i] for i in range(min_len)]
                min_l5 = min(len(a_l5), len(b_l5))
                l5 = [a_l5[i] + b_l5[i] for i in range(min_l5)]
            else:
                l10 = list(a_l10)
                l5 = list(a_l5)

            direction = ranked_market.get("direction", "OVER")
            line = ranked_market.get("line", 0)

            result = compute_probability(
                line=line,
                direction=direction,
                l10_values=l10,
                l5_values=l5 if l5 else None,
                h2h_values=h2h if h2h else None,
            )

            ranked_market["probability"] = result["probability"]
            ranked_market["fair_odds"] = result["fair_odds"]
            ranked_market["lambda"] = result["lambda"]
            ranked_market["model_used"] = result["model_used"]
            ranked_market["ci_lower"] = (
                result["confidence_interval"]["lower"]
                if result.get("confidence_interval")
                else None
            )
            ranked_market["ci_upper"] = (
                result["confidence_interval"]["upper"]
                if result.get("confidence_interval")
                else None
            )
            # Minimum odds for EV>0: fair_odds = 1/probability
            ranked_market["min_odds_ev0"] = result["fair_odds"]
        else:
            # No input data — can't compute probability
            ranked_market["probability"] = None
            ranked_market["fair_odds"] = None
            ranked_market["lambda"] = None
            ranked_market["model_used"] = "none"

    return ranking_result


# ---------------------------------------------------------------------------
# CLI and self-test
# ---------------------------------------------------------------------------

def _run_test():
    """Self-test with known football corner data."""
    print("=== Probability Engine Self-Test ===\n")

    # Liverpool vs Arsenal corner example
    # Liverpool L10 corners: avg ~9.5, Arsenal L10: ~5.0
    # Combined L10: avg ~14.5
    liverpool_corners = [11, 8, 13, 9, 10, 12, 7, 11, 9, 5]
    arsenal_corners = [6, 9, 8, 4, 3, 5, 7, 4, 5, 3]
    combined_l10 = [a + b for a, b in zip(liverpool_corners, arsenal_corners)]
    combined_l5 = combined_l10[-5:]
    h2h_corners = [12, 9, 14, 11, 15]  # 5 H2H meetings

    print(f"Combined L10: {combined_l10} (avg: {statistics.mean(combined_l10):.1f})")
    print(f"Combined L5:  {combined_l5} (avg: {statistics.mean(combined_l5):.1f})")
    print(f"H2H:          {h2h_corners} (avg: {statistics.mean(h2h_corners):.1f})")
    print()

    for line in [8.5, 9.5, 10.5, 11.5, 12.5]:
        for direction in ["OVER", "UNDER"]:
            result = compute_probability(
                line=line,
                direction=direction,
                l10_values=combined_l10,
                l5_values=combined_l5,
                h2h_values=h2h_corners,
            )
            prob = result["probability"]
            fair = result["fair_odds"]
            ci = result.get("confidence_interval")
            ci_str = f"[{ci['lower']:.2%}-{ci['upper']:.2%}]" if ci else "N/A"

            print(
                f"  {direction} {line}: P={prob:.2%}, fair_odds={fair:.2f}, "
                f"λ={result['lambda']:.2f}, CI={ci_str}, model={result['model_used']}"
            )

            # EV check with hypothetical Betclic odds
            if direction == "OVER" and line == 9.5:
                for bk_odds in [1.50, 1.70, 1.90, 2.10]:
                    ev = compute_ev(prob, bk_odds)
                    kelly = compute_kelly_quarter(prob, bk_odds, 100.0)
                    ev_label = "✅ +EV" if ev > 0 else "❌ -EV"
                    print(
                        f"    Betclic @{bk_odds:.2f}: EV={ev:+.2%} {ev_label}, "
                        f"Kelly 1/4 stake: {kelly:.2f} PLN (bankroll=100)"
                    )
        print()

    print("=== Tennis Games Example ===")
    # Djokovic vs Alcaraz total games
    djokovic_games = [24, 31, 22, 28, 35, 26, 22, 30, 27, 24]
    alcaraz_games = [26, 33, 24, 29, 36, 28, 25, 31, 28, 26]
    # These are already total games per match
    h2h_games = [38, 34, 42, 30, 36]

    for line in [21.5, 22.5, 23.5]:
        result = compute_probability(
            line=line,
            direction="OVER",
            l10_values=djokovic_games,  # Using player A as representative
            h2h_values=h2h_games,
        )
        print(
            f"  Over {line} games: P={result['probability']:.2%}, "
            f"fair={result['fair_odds']:.2f}, λ={result['lambda']:.2f}"
        )

    print("\n=== Self-test complete ===")


def main():
    parser = argparse.ArgumentParser(description="Probability Engine for betting markets")
    parser.add_argument("--input", help="Path to safety score input JSON")
    parser.add_argument("--test", action="store_true", help="Run self-test with sample data")
    parser.add_argument("--line", type=float, help="Betting line (e.g., 9.5)")
    parser.add_argument("--direction", choices=["OVER", "UNDER"], help="Bet direction")
    parser.add_argument("--values", help="Comma-separated L10 values")
    args = parser.parse_args()

    if args.test:
        _run_test()
        return

    if args.input:
        data = json.loads(Path(args.input).read_text(encoding="utf-8"))
        for market in data.get("markets", []):
            enrich_market_with_probability(market)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    if args.line and args.direction and args.values:
        values = [float(v) for v in args.values.split(",")]
        result = compute_probability(
            line=args.line,
            direction=args.direction,
            l10_values=values,
        )
        print(json.dumps(result, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
