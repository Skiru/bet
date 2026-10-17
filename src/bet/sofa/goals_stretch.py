"""Goals stretch: the supremacy term of a football goals centre (switch
``epochs.FOOTBALL_GOALS_STRETCH_FROM_UTC``, off while None).

SHEET's goals centre is the rating blended with the shrunk sample - and both
halves pull a mismatch toward the middle: the favourite's own goals come out
too low and the outsider's too high (history replay 2025-08..2026-10, s >= 1:
y - centre +0.26 goals_for, -0.13 at s < -1), and a lopsided match's total
too low (+0.36 at |s| >= 1.5) while an even one's is a shade high. With the
switch on, the centre of a market of GOALS_STRETCH_MARKETS is

    side  (goals_for, goals_1h_for, goals_2h_for):
        centre x exp(beta_m x s),             s = the side's expected goal
                                              difference
    total (goals_total, goals_1h_total, goals_2h_total):
        centre x exp(g1_m x |s| + g2_m x s^2), s = the home side's

where s comes from the rating's own goals book as of the match
(``FootballForecast.supremacy``, the covariate of bet.sofa.game_state; the
opponent reads -s, a total's terms are even in s) clamped at
game_state.MAX_SUPREMACY, and the coefficients are fitted on the history
(``fit_terms``: Poisson pseudo-likelihood, log link, offset log centre) by
``scripts/sofa/fit_goals_stretch.py`` into config/sofa_goals_stretch.json.
A market absent from the file, or a fixture with no goals rating, keeps its
centre byte for byte. Measured 2026-10-17 on the history replay
(walk-forward, NB log-loss new - old, match bootstrap): goals_for -0.0010
[-0.0012, -0.0008], goals_1h_for -0.0074 [-0.0078, -0.0070], goals_2h_for
-0.0048 [-0.0052, -0.0045], goals_total -0.0011 [-0.0013, -0.0009],
goals_1h_total -0.0018 [-0.0021, -0.0016], goals_2h_total -0.0014 [-0.0017,
-0.0013] (the totals with |s| alone; the s^2 term's own figures are in the
evidence file). Evidence: EVIDENCE.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from bet.sofa.config import config_path
from bet.sofa.game_state import clamp_supremacy

CONFIG_FILE = "sofa_goals_stretch.json"
EVIDENCE = "docs/sofa/evidence/goals_stretch_2026-10-17.md"
SIDE_MARKETS: tuple[str, ...] = ("goals_for", "goals_1h_for", "goals_2h_for")
TOTAL_MARKETS: tuple[str, ...] = (
    "goals_total", "goals_1h_total", "goals_2h_total")
GOALS_STRETCH_MARKETS: tuple[str, ...] = SIDE_MARKETS + TOTAL_MARKETS
# s is capped as in game_state (chosen, not fitted).
GOALS_STRETCH_UNFITTED = ("MAX_SUPREMACY",)
# A coefficient at or beyond this is a broken fit, not a football effect: at
# MAX_SUPREMACY it would multiply a centre by e^3 (side) or more (total).
MAX_ABS_COEFFICIENT = 1.0


class _Supremacy(Protocol):
    def supremacy(self, side: str) -> float | None: ...


def is_total(market: str) -> bool:
    return market in TOTAL_MARKETS


def features(market: str, supremacy: float) -> tuple[float, ...]:
    """The market's covariates of the clamped s: (s,) for a side market,
    (|s|, s^2) for a total."""
    s = clamp_supremacy(supremacy)
    return (abs(s), s * s) if is_total(market) else (s,)


def stretch_supremacy(forecast: _Supremacy, market: str,
                      side: str | None) -> float | None:
    """The s a market's term reads: the side's own for a side market (None
    without a side), the home side's for a total; None when the goals rating
    gives no centre."""
    if is_total(market):
        return forecast.supremacy("side_a")
    if side not in ("side_a", "side_b"):
        return None
    return forecast.supremacy(side)


@dataclass(frozen=True)
class GoalsStretchTable:
    # market -> (beta,) for a side market, (g1, g2) for a total
    coefficients: Mapping[str, tuple[float, ...]] = field(default_factory=dict)
    path: str | None = None

    def multiplier(self, market: str, supremacy: float | None) -> float | None:
        """exp(coefficients . features) for the market, None when it has no
        coefficients or the fixture has no supremacy (the centre is then
        left as it is)."""
        coefs = self.coefficients.get(market)
        if coefs is None or supremacy is None:
            return None
        x = features(market, supremacy)
        return math.exp(sum(c * v for c, v in zip(coefs, x, strict=True)))

    def describe(self, market: str) -> str:
        coefs = self.coefficients[market]
        if is_total(market):
            return f"g1 {coefs[0]:+.4f}, g2 {coefs[1]:+.4f}"
        return f"beta {coefs[0]:+.4f}"


def _coefficient(path: str | None, market: str, name: str, raw: Any) -> float:
    if not isinstance(raw, int | float) or isinstance(raw, bool) or not (
            math.isfinite(raw) and abs(raw) < MAX_ABS_COEFFICIENT):
        raise ValueError(f"{path}: {market} {name} {raw!r} is not a sane number")
    return float(raw)


def parse_table(data: Mapping[str, Any], path: str | None = None) -> GoalsStretchTable:
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError(f"{path}: no 'markets' object")
    coefficients: dict[str, tuple[float, ...]] = {}
    for market, cell in markets.items():
        if market not in GOALS_STRETCH_MARKETS:
            raise ValueError(f"{path}: {market} is not a goals-stretch market")
        if not isinstance(cell, Mapping):
            raise ValueError(f"{path}: {market} is not an object")
        names = ("g1", "g2") if is_total(market) else ("beta",)
        coefficients[str(market)] = tuple(
            _coefficient(path, market, n, cell.get(n)) for n in names)
    return GoalsStretchTable(coefficients, path)


def load_table(path: Path | None = None) -> GoalsStretchTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    target = path if path is not None else config_path(CONFIG_FILE)
    return parse_table(json.loads(target.read_text()), str(target))


def fit_terms(
    market: str, centres: Sequence[float], supremacy: Sequence[float],
    y: Sequence[float], iterations: int = 60,
) -> tuple[float, ...]:
    """The coefficients maximising sum(y x b.x - c x exp(b.x)) (Poisson
    pseudo-likelihood with offset log c: consistent for the mean whatever the
    count's dispersion), x = features(market, s). Newton from 0, as
    game_state.fit_beta; zeros when the Hessian is singular."""
    c = np.asarray(centres, dtype=np.float64)
    yy = np.asarray(y, dtype=np.float64)
    x = np.asarray([features(market, s) for s in supremacy], dtype=np.float64)
    k = 2 if is_total(market) else 1
    b = np.zeros(k)
    if len(c) == 0:
        return tuple(float(v) for v in b)
    for _ in range(iterations):
        mu = c * np.exp(x @ b)
        grad = x.T @ (yy - mu)
        hess = (x * mu[:, None]).T @ x
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return tuple(0.0 for _ in range(k))
        b = b + step
        if float(np.abs(step).max()) < 1e-10:
            break
    return tuple(float(v) for v in b)
