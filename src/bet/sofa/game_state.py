"""Game state: the favourite / outsider term of a football side's centre
(audit 2026-10-13 B1; switch ``epochs.GAME_STATE_FROM_UTC``, off while None).

A side's corners, shots, fouls and bookings depend on who is expected to lead:
a favourite ahead concedes the ball, an outsider chases it and fouls
(Buraimo, Forrest & Simmons 2010 for bookings; Wheatcroft 2020 rates shots and
corners by attack x defence). Neither half of SHEET's centre has the term -
the rating's Maher product and the shrunk sample both describe what the side
does on average. With the switch on, the centre of a market of
GAME_STATE_MARKETS is

    centre x exp(beta_m x s),   s = the side's expected goal difference

where s comes from the rating's own goals book as of the match
(``FootballForecast.supremacy``; the opponent reads -s) and beta_m is fitted
on the history (``fit_beta``: Poisson pseudo-likelihood, log link, offset log
centre) by ``scripts/sofa/fit_game_state.py`` into config/sofa_game_state.json.
A market absent from the file, or a side with no goals rating, keeps its
centre byte for byte. Evidence: docs/sofa/evidence/game_state_2026-10-13.md.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.config import config_path

CONFIG_FILE = "sofa_game_state.json"
GAME_STATE_MARKETS: tuple[str, ...] = (
    "corners_for", "shots_for", "cards_points_for", "fouls_for")
# A side's expected goal difference is capped here before it enters the
# exponent: an Aktobe-style rating mismatch (20-0 wins in a weak league) must
# not multiply a centre without bound. Chosen, not fitted.
MAX_SUPREMACY = 3.0
GAME_STATE_UNFITTED = ("MAX_SUPREMACY",)


def clamp_supremacy(s: float) -> float:
    return min(max(s, -MAX_SUPREMACY), MAX_SUPREMACY)


@dataclass(frozen=True)
class GameStateTable:
    betas: Mapping[str, float] = field(default_factory=dict)
    path: str | None = None

    def multiplier(self, market: str, supremacy: float | None) -> float | None:
        """exp(beta x s) for the market, None when it has no beta or the side
        has no supremacy (the centre is then left as it is)."""
        beta = self.betas.get(market)
        if beta is None or supremacy is None:
            return None
        return math.exp(beta * clamp_supremacy(supremacy))


def parse_table(data: Mapping[str, Any], path: str | None = None) -> GameStateTable:
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError(f"{path}: no 'markets' object")
    betas: dict[str, float] = {}
    for market, cell in markets.items():
        if market not in GAME_STATE_MARKETS:
            raise ValueError(f"{path}: {market} is not a game-state market")
        beta = cell.get("beta") if isinstance(cell, Mapping) else None
        if not isinstance(beta, int | float) or isinstance(beta, bool) or not (
                math.isfinite(beta) and abs(beta) < 1.0):
            raise ValueError(f"{path}: {market} beta {beta!r} is not a sane number")
        betas[str(market)] = float(beta)
    return GameStateTable(betas, path)


def load_table(path: Path | None = None) -> GameStateTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent identity would claim a rule the sheet did not use."""
    target = path if path is not None else config_path(CONFIG_FILE)
    return parse_table(json.loads(target.read_text()), str(target))


def fit_beta(
    centres: Sequence[float], supremacy: Sequence[float], y: Sequence[float],
    iterations: int = 50,
) -> float:
    """beta maximising sum(y x beta s - c x exp(beta s)) (Poisson
    pseudo-likelihood with offset log c: consistent for the mean whatever the
    count's dispersion). Newton from 0; s is clamped as in `multiplier`."""
    s = [clamp_supremacy(v) for v in supremacy]
    beta = 0.0
    for _ in range(iterations):
        grad = 0.0
        hess = 0.0
        for c, si, yi in zip(centres, s, y, strict=True):
            mu = c * math.exp(beta * si)
            grad += si * (yi - mu)
            hess += si * si * mu
        if hess <= 0:
            return 0.0
        step = grad / hess
        beta += step
        if abs(step) < 1e-10:
            break
    return beta
