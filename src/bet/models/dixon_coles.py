"""Time-weighted Dixon-Coles (1997) bivariate Poisson football model for Premier League (eng.1).

Literature reference: Dixon and Coles (1997), DOI 10.1111/1467-9876.00065.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Mapping


def tau_correction(x: int, y: int, lambda_param: float, mu_param: float, rho: float = -0.05) -> float:
    """Dixon-Coles low-score interdependence adjustment tau(x, y, lambda, mu, rho)."""
    if x == 0 and y == 0:
        return 1.0 - (lambda_param * mu_param * rho)
    elif x == 0 and y == 1:
        return 1.0 + (lambda_param * rho)
    elif x == 1 and y == 0:
        return 1.0 + (mu_param * rho)
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def poisson_pmf(k: int, mu: float) -> float:
    """Poisson probability mass function P(X = k) = exp(-mu) * mu^k / k!"""
    if mu <= 0 or k < 0:
        return 0.0
    return math.exp(-mu) * (mu ** k) / math.factorial(k)


def calculate_dixon_coles_outcomes(
    home_attack: float = 1.2,
    home_defence: float = 0.9,
    away_attack: float = 1.0,
    away_defence: float = 1.1,
    home_advantage: float = 1.25,
    rho: float = -0.05,
    max_goals: int = 8,
) -> dict[str, float]:
    """Calculate home/draw/away probabilities using Dixon-Coles goal grid."""
    lambda_param = max(0.1, home_attack * away_defence * home_advantage)
    mu_param = max(0.1, away_attack * home_defence)

    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0

    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            tau = tau_correction(x, y, lambda_param, mu_param, rho)
            prob = tau * poisson_pmf(x, lambda_param) * poisson_pmf(y, mu_param)
            if x > y:
                p_home += prob
            elif x == y:
                p_draw += prob
            else:
                p_away += prob

    total = p_home + p_draw + p_away
    if total > 0:
        p_home /= total
        p_draw /= total
        p_away /= total

    return {
        "home": p_home,
        "draw": p_draw,
        "away": p_away,
        "expected_home_goals": lambda_param,
        "expected_away_goals": mu_param,
    }
