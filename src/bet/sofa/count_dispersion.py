"""The dispersion of football counts, fitted on the history (switch
`epochs.COUNT_DISPERSION_FROM_UTC`, off while it is None).

Today SHEET prices a count's spread from the sample variance of 8-10 matches
(`engine.sheet_predictive_sd`). Measured out of sample (track A2,
docs/sofa/evidence/count_families_2026-10-08.md, test 2026-04-01..10-07) a
dispersion fitted on the history beats it on 52 of 52 football markets by
log-loss: variance = mu + alpha * mu^2 around SHEET's own centre mu, alpha per
(market, competition) with partial pooling toward the market's alpha
(`nb_lg`), the negative binomial as the family - except `shots_total`, where
the NB loses and the floored normal with the same variance wins (`norm_lg`).

This module is the pure-Python half both SHEET and the cache replay read
(no numpy at runtime): the config file, the lookup with its fallbacks, the
variance, and the pooling formula the fit uses. The numpy estimation lives in
`scripts/sofa/count_dispersion_estimation.py` (shared by the measurement and
`scripts/sofa/fit_count_dispersion.py`).

Fallbacks (a read returns None = today's estimator, byte for byte):
  * not football, or a market absent from the file (player props, the thin
    `fouls_1h_*` / `fouls_2h_*`, markets nobody measured): None;
  * a competition absent from the market's `by_competition`: the market's own
    `alpha`. That is the value partial pooling gives a league with no cases
    (A = B = 0 in `pooled_alpha`), and the pooling weights chosen on the
    validation slice (100 .. 10,000 cases) were measured with exactly such
    leagues in the test window.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from bet.sofa.config import config_path

CONFIG_FILE = "sofa_count_dispersion.json"
FAMILY_NB = "nb"
FAMILY_NORMAL = "normal"
FAMILIES = (FAMILY_NB, FAMILY_NORMAL)
# `family` of a market the measurement found NB-worse (shots_total): the
# engine's support-floored normal with the fitted variance.
NORMAL_MARKETS = frozenset({"shots_total"})
ALPHA_FLOOR = 1e-4  # measure_count_families.alpha_league's floor
# A sane upper bound for any alpha. The shipped fit's range is 1e-4 .. 1.59
# (a thin competition, pooled); 5.0 is three times that: a larger value is a
# typo or a unit slip (variance = mu + alpha mu^2 would be > 5 mu^2), never a
# fitted dispersion, so the file is refused rather than priced.
ALPHA_MAX = 5.0
# a competition's alpha is written only from this many training cases; below
# it the pooled value is within noise of the market's anyway
MIN_COMPETITION_CASES = 30
SPORT = "football"


@dataclass(frozen=True)
class Dispersion:
    """What one row reads: the alpha, the family and where the alpha came from
    ("competition" or "market" - the fallback)."""

    alpha: float
    family: str
    source: str

    def variance(self, centre: float) -> float:
        return variance_for(centre, self.alpha)


@dataclass(frozen=True)
class MarketCell:
    alpha: float
    family: str
    by_competition: Mapping[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DispersionTable:
    markets: Mapping[str, MarketCell]
    path: str | None = None

    def read(
        self, sport: str | None, market: str, competition_id: int | None
    ) -> Dispersion | None:
        if sport != SPORT:
            return None
        cell = self.markets.get(market)
        if cell is None:
            return None
        if competition_id is not None and competition_id in cell.by_competition:
            return Dispersion(
                cell.by_competition[competition_id], cell.family, "competition")
        return Dispersion(cell.alpha, cell.family, "market")


def variance_for(centre: float, alpha: float) -> float:
    """The NB variance around the centre: mu + alpha mu^2."""
    mu = max(centre, 1e-9)
    return mu + alpha * mu * mu


def pooled_alpha(
    a: float, b: float, *, mom: float, mle: float, bmean: float, kc: float
) -> float:
    """alpha of one competition: its moment estimate (A = sum((y-mu)^2 - mu),
    B = sum mu^2 over its cases) pooled toward the market's alpha with `kc`
    cases' worth of weight; `mom` / `mle` the market's moment and
    maximum-likelihood alpha, `bmean` the market's mean mu^2. The scale
    rho = mle / mom keeps the pooled value on the likelihood's scale.
    A = B = 0 (no cases) gives `mle`."""
    rho = mle / mom
    kappa = kc * bmean
    return max(rho * (a + kappa * mom) / (b + kappa), ALPHA_FLOOR)


def _valid_alpha(value: Any) -> bool:
    if isinstance(value, bool):  # True would read as 1.0
        return False
    try:
        alpha = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(alpha) and 0 < alpha <= ALPHA_MAX


def _competition_key(key: Any) -> int:
    text = str(key)
    if isinstance(key, bool) or not text.isascii() or not text.isdigit():
        raise ValueError(f"{CONFIG_FILE}: bad competition key {key!r}")
    return int(text)


def parse_table(data: Mapping[str, Any], path: str | None = None) -> DispersionTable:
    markets: dict[str, MarketCell] = {}
    for market, raw in (data.get("markets") or {}).items():
        family = str(raw.get("family", FAMILY_NB))
        if family not in FAMILIES or not _valid_alpha(raw.get("alpha")):
            raise ValueError(f"{CONFIG_FILE}: bad cell for {market}: {raw!r}")
        alpha = float(raw["alpha"])
        by_comp: dict[int, float] = {}
        for k, v in (raw.get("by_competition") or {}).items():
            key = _competition_key(k)
            raw_alpha = v.get("alpha") if isinstance(v, Mapping) else v
            if not _valid_alpha(raw_alpha):
                raise ValueError(
                    f"{CONFIG_FILE}: bad alpha for {market} / {k}: {v!r}")
            by_comp[key] = float(cast(Any, raw_alpha))
        markets[str(market)] = MarketCell(alpha, family, by_comp)
    return DispersionTable(markets, path)


def load_table(path: Path | None = None) -> DispersionTable:
    """The fitted table. A missing or malformed file raises: with the switch on
    a silent fall back to the sample variance would price a sheet under a rule
    its rows then claim (`dispersion_rule`) without having used it."""
    target = path if path is not None else config_path(CONFIG_FILE)
    return parse_table(json.loads(target.read_text()), str(target))
