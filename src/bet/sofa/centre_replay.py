"""One-step-ahead reconstruction of SHEET's football centre on the cached
history - the common ground of the audit 2026-10-13 B1 / B2 measurements
(scripts/sofa/measure_game_state.py, measure_unrated_markets.py,
fit_game_state.py).

What it is, and what it is not. For every match of the history the rating
book is read strictly before the match (football_rating.RatingBook, updated
match by match after it is read) and a SHEET-like centre is rebuilt per row:

  * the sample: a side's last ``sample_n`` values of the metric (any
    competition; friendlies are not in the history), shrunk with
    w = n / (n + K) toward the match competition's per-side rate in the book
    (a ``_total`` pools both sides' last match totals, a shared match once,
    toward the sum of the home and away rates);
  * the rating: ``FootballForecast.centre`` with every market in scope
    (``rated_scope`` = UNRATED_MARKETS), the link and league strength as in
    SHEET;
  * the side's expected goal difference (``FootballForecast.supremacy``);
  * the venue multiplier (``FootballForecast.venue_multiplier``) from the
    venues the sample was earned at.

SHEET's prior is the fitted league baseline from config, not the book's
running rate, and SHEET's sample comes from SAMPLES, not from the history's
own listing - so this is an approximation of the centre, the same in every
variant compared. calibrate_from_cache.py does not replay the football rating
(audit A6); this is a centre-quality measurement, not a curve.

Read-only: writes nothing.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass

import numpy as np

from bet.sofa import football_rating as fr

SAMPLE_N = 10
MIN_VALUES = 5
SPORT_K = 15.0


@dataclass(frozen=True)
class CentreRow:
    event_id: int
    ts: int
    competition_id: int
    market: str
    side: str  # "side_a" (home) / "side_b" (away) / "" for a match total
    y: float
    sample: float  # the sample's shrunk centre (SHEET's centre without rating)
    rating: float | None  # the rating's expected value, None if not rated
    supremacy: float | None  # the side's expected goal difference (None: total)
    venue_mult: float | None  # league venue multiplier (None: total / unknown)


@dataclass(frozen=True)
class _Obs:
    event_id: int
    own: float
    opp: float
    venue: str


def walk(
    history: Iterable[fr.FootballResult],
    start_ts: int,
    end_ts: int,
    markets: Iterable[str],
    k_by_market: Mapping[str, float] | None = None,
    sample_n: int = SAMPLE_N,
    min_values: int = MIN_VALUES,
    shared_league_link: bool = True,
) -> Iterator[CentreRow]:
    """Yield one CentreRow per (match, market, side) in [start_ts, end_ts)."""
    wanted = sorted(set(markets))
    by_metric: dict[str, list[str]] = defaultdict(list)
    for m in wanted:
        metric = fr.base_metric(m)
        if metric is None:
            raise ValueError(f"{m}: not a rated base metric's market")
        by_metric[metric].append(m)
    k_by_market = k_by_market or {}
    book = fr.RatingBook(shared_league_link=shared_league_link)
    last: dict[tuple[int, str], deque[_Obs]] = defaultdict(
        lambda: deque(maxlen=sample_n))
    scope = frozenset(fr.UNRATED_MARKETS)
    for r in history:
        if r.ts >= end_ts:
            break
        if r.ts >= start_ts:
            fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id,
                                     rated_scope=scope)
            sup: dict[str, float | None] = {}
            for metric, ms in by_metric.items():
                if metric not in r.values:
                    continue
                vh, va = r.values[metric]
                rates = book.league_rates(r.competition_id, metric)
                if rates is None:
                    continue
                lh, la = last[(r.home_id, metric)], last[(r.away_id, metric)]
                if len(lh) < min_values or len(la) < min_values:
                    continue
                for m in ms:
                    k = float(k_by_market.get(m, SPORT_K))
                    if m.endswith("_total"):
                        rated = fc.centre(m, None)
                        pool = {o.event_id: o.own + o.opp for o in lh}
                        pool.update({o.event_id: o.own + o.opp for o in la})
                        vals = list(pool.values())
                        w = len(vals) / (len(vals) + k)
                        sample = w * sum(vals) / len(vals) + (1 - w) * (
                            rates[0] + rates[1])
                        yield CentreRow(
                            r.event_id, r.ts, r.competition_id, m, "", vh + va,
                            sample, rated[0] if rated else None, None, None)
                        continue
                    for side, own, y in (("side_a", lh, vh), ("side_b", la, va)):
                        if side not in sup:
                            sup[side] = fc.supremacy(side)
                        vals = [o.own for o in own]
                        w = len(vals) / (len(vals) + k)
                        sample = w * sum(vals) / len(vals) + (1 - w) * (
                            rates[0] + rates[1]) / 2
                        rated = fc.centre(m, side)
                        yield CentreRow(
                            r.event_id, r.ts, r.competition_id, m, side, y, sample,
                            rated[0] if rated else None, sup[side],
                            fc.venue_multiplier(m, side, (o.venue for o in own)))
        for metric, (vh, va) in r.values.items():
            if metric not in by_metric:
                continue
            last[(r.home_id, metric)].append(_Obs(r.event_id, vh, va, "home"))
            last[(r.away_id, metric)].append(_Obs(r.event_id, va, vh, "away"))
        book.update(r)


def nb_logloss(y: float, mu: float, alpha: float) -> float:
    """-log P(Y = y) under NB(mean mu, variance mu + alpha mu^2)."""
    mu = max(mu, 1e-9)
    if alpha <= 1e-9:
        return -(y * math.log(mu) - mu - math.lgamma(y + 1))
    r = 1.0 / alpha
    return -(math.lgamma(y + r) - math.lgamma(r) - math.lgamma(y + 1)
             + r * math.log(r / (r + mu)) + y * math.log(mu / (r + mu)))


def boot_by_group(
    groups: Mapping[int, list[float]], n_boot: int = 2000, seed: int = 0,
) -> tuple[float, float, float, int, int]:
    """(mean over items, 2.5%, 97.5%, items, groups), resampling groups."""
    keys = sorted(groups)
    if not keys:
        nan = float("nan")
        return nan, nan, nan, 0, 0
    sums = np.array([sum(groups[k]) for k in keys], dtype=float)
    counts = np.array([len(groups[k]) for k in keys], dtype=float)
    rng = np.random.default_rng(seed)
    stats = np.empty(n_boot)
    for b in range(n_boot):
        idx = rng.integers(0, len(keys), len(keys))
        stats[b] = sums[idx].sum() / counts[idx].sum()
    lo, hi = np.quantile(stats, [0.025, 0.975])
    return (float(sums.sum() / counts.sum()), float(lo), float(hi),
            int(counts.sum()), len(keys))
