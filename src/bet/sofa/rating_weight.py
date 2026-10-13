"""The football rating's weight per market (audit 2026-10-13 B14; switch
``epochs.FOOTBALL_RATING_WEIGHT_FROM_UTC``, off while None).

SHEET's football centre is ``W x rating + (1 - W) x shrunk sample`` with one
W = football_rating.W_FOOTBALL_RATING (0.5) for every rated market, chosen by
Brier on five settled days (2026-09-18..22). With the switch on a market
listed in config/sofa_rating_weight.json reads its own W, fitted on the
history by ``scripts/sofa/fit_rating_weight.py`` (``fit_weight``: the grid W
of the lowest NB log-loss of the centre at the observed count); a market
absent from the file keeps W_FOOTBALL_RATING. Evidence:
docs/sofa/evidence/rating_weight_2026-10-13.md.

``blend`` is the one function SHEET and a history replay both call.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bet.sofa.centre_replay import nb_logloss
from bet.sofa.config import config_path
from bet.sofa.football_rating import W_FOOTBALL_RATING

CONFIG_FILE = "sofa_rating_weight.json"
# the grid the fit searches: 0.00, 0.05, .., 1.00
W_GRID: tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(21))


@dataclass(frozen=True)
class RatingWeightTable:
    weights: Mapping[str, float] = field(default_factory=dict)
    path: str | None = None

    def weight(self, market: str) -> float | None:
        """The market's fitted W; None when it has none (W_FOOTBALL_RATING)."""
        return self.weights.get(market)


def weight_for(market: str, table: RatingWeightTable | None) -> float:
    """W of the market: the table's when the switch is on and it has one,
    else W_FOOTBALL_RATING."""
    if table is None:
        return W_FOOTBALL_RATING
    w = table.weight(market)
    return W_FOOTBALL_RATING if w is None else w


def blend(rated: float, sample: float, market: str,
          table: RatingWeightTable | None) -> float:
    """SHEET's rated centre: W x rating + (1 - W) x the shrunk sample.
    Off (table None) it is the 0.5 blend, operation for operation."""
    w = weight_for(market, table)
    return w * rated + (1 - w) * sample


def parse_table(data: Mapping[str, Any], path: str | None = None) -> RatingWeightTable:
    markets = data.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError(f"{path}: no 'markets' object")
    out: dict[str, float] = {}
    for market, cell in markets.items():
        w = cell.get("w") if isinstance(cell, Mapping) else None
        if not isinstance(w, int | float) or isinstance(w, bool) or not (
                math.isfinite(w) and 0.0 <= w <= 1.0):
            raise ValueError(f"{path}: {market} w {w!r} is not in [0, 1]")
        out[str(market)] = float(w)
    return RatingWeightTable(out, path)


def load_table(path: Path | None = None) -> RatingWeightTable:
    """The fitted table. Missing or malformed raises: with the switch on a
    silent fallback would claim a rule the sheet did not use."""
    target = path if path is not None else config_path(CONFIG_FILE)
    return parse_table(json.loads(target.read_text()), str(target))


def fit_weight(
    rated: Sequence[float], sample: Sequence[float], y: Sequence[float],
    alpha: Sequence[float], grid: Sequence[float] = W_GRID,
) -> tuple[float, float]:
    """(W, mean loss) of the grid W minimising the mean NB log-loss of the
    observed count `y` at mean W x rated + (1 - W) x sample (alpha per row:
    the market x competition dispersion SHEET reads); ties go to the W
    nearest W_FOOTBALL_RATING."""
    if not rated:
        return W_FOOTBALL_RATING, math.nan
    best: tuple[float, float, float] | None = None
    n = len(rated)
    for w in grid:
        total = 0.0
        for r, s, yi, a in zip(rated, sample, y, alpha, strict=True):
            total += nb_logloss(yi, w * r + (1 - w) * s, a)
        mean = total / n
        key = (mean, abs(w - W_FOOTBALL_RATING), w)
        if best is None or key < best:
            best = key
    assert best is not None
    return best[2], best[0]
