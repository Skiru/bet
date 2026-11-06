"""SHEET's reading of the bottom-up tennis point model
(epochs.TENNIS_POINT_MODEL_FROM_UTC; the model: bet.sofa.tennis_point_model,
measured in docs/sofa/evidence/tennis_point_model_2026-11-05.md).

For a tennis row of ``epochs.TENNIS_POINT_MODEL_MARKETS`` SHEET takes its
p_central and centre from here. The forecast is *as of* the fixture's start,
exactly as the measurement read it (``walk_forward``): the history of cached
singles matches is fed in time order, the fixture is forecast from the
beliefs before its start time (matches starting at the same second are
forecast before any of them teaches the ratings), and the fixture itself
teaches nothing. On a build day the cache holds only finished matches, so the
forecast also never reads anything after the build clock.

The fixture enters as a ``PointMatch`` built from 02_fixtures.json - tier from
the category, surface from the ground type, the unique tournament
(``competition_id``) and the players' gender as the history last saw them (a
women's match when either side was) - the fields the model's cell, tournament
term and decider book read. A fixture the model cannot price (best of five,
no player ids) gives None: SHEET then refuses the row (NOT_RATED), never
falls back to the old estimator, because the curves of these keys describe
this model only.

Simulation: 4,000 matches per fixture, seeded by the event id (the
measurement's ``market_sim(f, n=4000, seed=eid % 2**31)``), so a re-run
prices the same.

``epochs.TENNIS_HANDICAP_POINT_MODEL`` widens the scope (``epochs.
tennis_point_markets``) to the per-set games handicap: "X (line)" read off the
same simulations by bet.sofa.tennis_handicap_point (X's games won minus lost
in that set, the set played; a win when the margin exceeds -line, a push no
win and out of the share; only the OVER side exists, each player's handicap
its own rung). The pricer's ``markets`` is the day's scope.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from bet.sofa import tennis_handicap_point as thp
from bet.sofa.epochs import (
    TENNIS_HANDICAP_POINT_MODEL_MARKETS,
    TENNIS_POINT_MODEL_MARKETS,
)
from bet.sofa.tennis_point_model import (
    NB_SHAPE,
    MarketSim,
    MatchForecast,
    PointMatch,
    PointModel,
    _serve_market,
    market_sim,
)
from bet.sofa.tennis_rating import surface_family, tier_group

SIMS = 4000
NOTE = "TENNIS_POINT_MODEL"
MARKETS = TENNIS_POINT_MODEL_MARKETS


def in_scope(sport: object, market: str,
             markets: frozenset[str] = MARKETS) -> bool:
    return sport == "tennis" and market in markets


def seed_of(event_id: int) -> int:
    return event_id % (2 ** 31)


def female_by_player(history: Iterable[PointMatch]) -> dict[int, bool]:
    """Each player's gender as the newest history match records it."""
    out: dict[int, bool] = {}
    for m in history:
        out[m.home_id] = m.female
        out[m.away_id] = m.female
    return out


def fixture_match(
    event_id: int, kickoff: datetime, home_id: int | None, away_id: int | None,
    category_name: str | None, ground_type: str | None,
    competition_id: int | None, default_period_count: int | None,
    female_of: Mapping[int, bool],
) -> PointMatch | None:
    """The fixture as the model's forecast reads it; None = not priced
    (best of five or unknown sides)."""
    if home_id is None or away_id is None:
        return None
    if default_period_count not in (None, 3):
        return None  # best of five is not modelled (measured bo3 only)
    return PointMatch(
        event_id=int(event_id), ts=int(kickoff.timestamp()),
        tier=tier_group(str(category_name or "")),
        surface=surface_family(ground_type),
        female=bool(female_of.get(home_id) or female_of.get(away_id)),
        tournament=competition_id if isinstance(competition_id, int) else None,
        home_id=int(home_id), away_id=int(away_id), home_won=False, sets=(),
        completed=False, best_of=None, match_tiebreak_decider=False,
    )


def forecast_fixtures(
    history: Sequence[PointMatch], fixtures: Sequence[PointMatch],
    model: PointModel | None = None,
) -> dict[int, MatchForecast]:
    """Each fixture forecast from the beliefs before its start: the history
    (time-ordered) is fed up to and excluding the fixture's start second,
    matches of that second only after it (tennis_point_model.walk_forward's
    order). The walk stops after the last fixture."""
    model = model or PointModel()
    # A fixture whose own match is already in the history (a rebuild of a
    # past day) is forecast as of the earlier of its two start times: a
    # match that started before its scheduled kickoff must not teach its own
    # forecast. On a build day the fixture is not finished, so not there.
    started = {m.event_id: m.ts for m in history}
    pending = sorted(
        (dataclasses.replace(m, ts=min(m.ts, started.get(m.event_id, m.ts)))
         for m in fixtures),
        key=lambda m: (m.ts, m.event_id))
    out: dict[int, MatchForecast] = {}
    j = 0
    for m in history:
        while j < len(pending) and pending[j].ts <= m.ts:
            out[pending[j].event_id] = model.forecast(pending[j])
            j += 1
        if j >= len(pending):
            return out
        model.update(m)
    while j < len(pending):
        out[pending[j].event_id] = model.forecast(pending[j])
        j += 1
    return out


def _grid(market: str, side: int | None, ms: MarketSim) -> np.ndarray | None:
    """Per simulation, the value of a score market (games), or None for a
    serve count (a mixture, read by ``mean_sd``)."""
    sim = ms.sim
    if market in TENNIS_HANDICAP_POINT_MODEL_MARKETS:
        return None  # read by thp.mean_sd (needs the side)
    if market in ("games_set1_total", "games_set2_total"):
        k = 0 if market == "games_set1_total" else 1
        played = sim.sets_played > k
        return np.asarray(sim.games[played, k, :].sum(axis=1), dtype=np.float64)
    return None


def mean_sd(ms: MarketSim, market: str, side: int | None) -> tuple[float, float] | None:
    """The model's mean and spread of the row's quantity (conditional on the
    set being played for a per-set market): the row's centre. A handicap
    row: the subject's game margin in that set."""
    if market in TENNIS_HANDICAP_POINT_MODEL_MARKETS:
        return None if side is None else thp.mean_sd(ms, market, side)
    grid = _grid(market, side, ms)
    if grid is not None:
        if not len(grid):
            return None
        return float(grid.mean()), float(grid.std())
    parsed = _serve_market(market)
    if parsed is None:
        return None
    stat, scope, per_player = parsed
    if per_player and side is None:
        return None
    sim = ms.sim
    if scope == 0:
        sp = sim.serve_points.sum(axis=1).astype(np.float64)
        mask = np.ones(len(sp), dtype=bool)
        shape_a, shape_d = NB_SHAPE["aces"], NB_SHAPE["dfs"]
    else:
        sp = sim.serve_points[:, scope - 1, :].astype(np.float64)
        mask = sim.sets_played >= scope
        shape_a, shape_d = NB_SHAPE["aces_set"], NB_SHAPE["dfs_set"]
    if not mask.any():
        return None
    f = ms.forecast
    players = [side] if per_player and side is not None else [0, 1]
    parts: list[tuple[np.ndarray, float]] = []
    for i in players:
        rates = (f.home, f.away)[i]
        if stat in ("aces", "both"):
            parts.append((sp[mask, i] * rates.ace_rate, shape_a))
        if stat in ("dfs", "both"):
            parts.append((sp[mask, i] * rates.df_rate, shape_d))
    means = np.sum([m for m, _ in parts], axis=0)
    # E[Var | sim] + Var[E | sim] of the NB mixture
    within = np.sum([m + m * m / s for m, s in parts], axis=0)
    mean = float(means.mean())
    var = float(within.mean() + means.var())
    return mean, float(np.sqrt(max(var, 0.0)))


@dataclass
class PointPricer:
    """The day's forecasts, simulated lazily per fixture."""

    forecasts: Mapping[int, MatchForecast]
    sims: int = SIMS
    # the day's scope (epochs.tennis_point_markets)
    markets: frozenset[str] = MARKETS
    _cache: dict[int, MarketSim] = field(default_factory=dict)

    def market_sim(self, event_id: int) -> MarketSim | None:
        f = self.forecasts.get(event_id)
        if f is None:
            return None
        ms = self._cache.get(event_id)
        if ms is None:
            ms = market_sim(f, n=self.sims, seed=seed_of(event_id))
            self._cache[event_id] = ms
        return ms

    def p(self, event_id: int, market: str, side: int | None, line: float,
          direction: str) -> float | None:
        """P(the row wins): OVER = value > line, UNDER = value < line (an
        integer line pushes on equality - neither side wins it)."""
        ms = self.market_sim(event_id)
        if ms is None or market not in self.markets:
            return None
        if market in TENNIS_HANDICAP_POINT_MODEL_MARKETS:
            # epochs.TENNIS_HANDICAP_POINT_MODEL: "X (line)", OVER only
            if direction != "OVER" or side is None:
                return None
            return thp.p_handicap(ms, market, side, line)
        p_over = ms.p_over(market, side, line)
        if p_over is None:
            return None
        if direction == "OVER":
            return p_over
        if float(line).is_integer():
            # P(X < L) = 1 - P(X > L - 1) for an integer-valued count
            at_or_above = ms.p_over(market, side, line - 1.0)
            return None if at_or_above is None else 1.0 - at_or_above
        return 1.0 - p_over

    def covers(self, sport: object, market: str) -> bool:
        return in_scope(sport, market, self.markets)

    def centre(self, event_id: int, market: str,
               side: int | None) -> tuple[float, float] | None:
        ms = self.market_sim(event_id)
        return None if ms is None else mean_sd(ms, market, side)


def describe(p: float, centre: tuple[float, float] | None,
             f: MatchForecast | None) -> str:
    """The row's note."""
    if f is None:
        return f"{NOTE}: p {p:.4f}"
    parts = [f"{NOTE}: p {p:.4f}"]
    if centre is not None:
        parts.append(f"model mean {centre[0]:.2f} (sd {centre[1]:.2f})")
    parts.append(
        f"serve logit {f.home.serve_logit:+.3f} / {f.away.serve_logit:+.3f}, "
        f"aces / pt {f.home.ace_rate:.3f} / {f.away.ace_rate:.3f}, "
        f"df / pt {f.home.df_rate:.3f} / {f.away.df_rate:.3f}, serve points "
        f"seen {f.home.serve_points_seen:.0f} / {f.away.serve_points_seen:.0f}"
        + (", decider = match tiebreak" if f.decider_tiebreak else ""))
    return "; ".join(parts) + " (epochs.TENNIS_POINT_MODEL)"
