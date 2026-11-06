"""SPORT_CONFIDENCE's reading of the volleyball rally-point model
(epochs.VB_POINT_MODEL_FROM_UTC; the model: bet.sofa.volleyball_point_model,
measured in docs/sofa/evidence/volleyball_point_model_2026-11-06.md).

For a volleyball line of ``epochs.VB_POINT_MODEL_MARKETS`` the p comes from
here instead of the score model. The forecast is *as of* the fixture's start,
exactly as the measurement read it (``volleyball_point_model.walk_forward``):
the cached history (sport_confidence.parse_history's games, the build clock's
cut) is fed in time order, a fixture is forecast from the beliefs before its
start (matches of the same second forecast before any of them teaches), and
the fixture itself teaches nothing - on a rebuild of a past day its own
finished match, already cached, is fed only after it is forecast.

A fixture enters with its Sofascore home / away ids and competition
(sport_fixtures.json), its gender as the history last saw either side (women
when either was). A fixture with an unknown side gives no forecast: such a
line has no p (never the score model's - these keys' curves describe this
model only).

Simulation: ``N_SIMS`` matches per fixture, seeded by the Sofascore event id
(the measurement's ``simulate(f, params, n=4000, seed=eid % 2**31)``), in
Sofascore's home-first orientation, swapped to Superbet's team1 when the
fixture says so.

``BACKFILL``: the rally model's p of every settled Superbet volleyball line of
the model's markets, keyed by ``backfill_key`` - written by
scripts/sofa/backfill_vb_point_p.py (as of each event's start) and read by
fit_line_evidence.py so these keys' line evidence is read at this model's p.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from bet.sofa import epochs
from bet.sofa import volleyball_point_model as vpm

N_SIMS = 4000
NOTE = "VB_POINT_MODEL"
# The constants tuned 2026-11-06 on the history before 2026-03-01 (one-step
# validation 2025-11-01 .. 2026-02-28, the exact set-score log-likelihood;
# data/refit_2026-11-06_point_handicap_models/volleyball_tune2.json, every
# constant inside its extended grid).
PARAMS = vpm.VbParams(prior_var=0.06, drift_per_day=0.0001, weight=1.0,
                      home=0.04, form_var=0.01, set_var=0.02,
                      sideout_men=0.68, sideout_women=0.60, min_league_teams=4)
BACKFILL = Path(__file__).resolve().parents[3] / "data" / "line_evidence" / (
    "volleyball_point_model_p.json.gz")


class _Game(Protocol):
    @property
    def rating(self) -> Any: ...

    @property
    def result(self) -> Any: ...


def in_scope(sport: object, market_id: object) -> bool:
    return sport == "volleyball" and market_id in epochs.VB_POINT_MODEL_MARKETS


def seed_of(event_id: int) -> int:
    return int(event_id) % (2 ** 31)


def history_matches(history: Iterable[_Game]) -> list[vpm.VbMatch]:
    """parse_history's graded games as the model's matches (home = team1),
    oldest first - the measurement's loader."""
    out: list[vpm.VbMatch] = []
    for g in history:
        r, res = g.rating, g.result
        if res is None or not res.t1_periods:
            continue
        out.append(vpm.VbMatch(
            int(r.event_id), int(r.ts), int(r.competition_id), int(r.home_id),
            int(r.away_id), bool(r.women),
            tuple(int(x) for x in res.t1_periods),
            tuple(int(x) for x in res.t2_periods)))
    out.sort(key=lambda m: (m.ts, m.event_id))
    return out


def women_by_team(history: Iterable[vpm.VbMatch]) -> dict[int, bool]:
    """Each team's gender as the newest history match records it."""
    out: dict[int, bool] = {}
    for m in history:
        out[m.home] = m.women
        out[m.away] = m.women
    return out


def fixture_match(event_id: int, kickoff: datetime, home_id: object,
                  away_id: object, competition_id: object,
                  women_of: Mapping[int, bool]) -> vpm.VbMatch | None:
    """The fixture as the model's forecast reads it; None = not priced."""
    if not isinstance(home_id, int) or not isinstance(away_id, int):
        return None
    comp = competition_id if isinstance(competition_id, int) else -1
    return vpm.VbMatch(int(event_id), int(kickoff.timestamp()), comp, home_id,
                       away_id, bool(women_of.get(home_id) or women_of.get(away_id)),
                       (), ())


def forecast_fixtures(history: Sequence[vpm.VbMatch],
                      fixtures: Sequence[vpm.VbMatch],
                      params: vpm.VbParams = PARAMS) -> dict[int, vpm.VbForecast]:
    """Each fixture forecast from the beliefs before its start (history in
    time order; a history match of the fixture's own second teaches only
    after it). A fixture whose own match is cached (a past day) is forecast
    as of the earlier of the two starts."""
    started = {m.event_id: m.ts for m in history}
    pending = sorted(
        (vpm.VbMatch(m.event_id, min(m.ts, started.get(m.event_id, m.ts)),
                     m.competition, m.home, m.away, m.women, (), ())
         for m in fixtures),
        key=lambda m: (m.ts, m.event_id))
    rating = vpm.VbRating(params)
    out: dict[int, vpm.VbForecast] = {}
    j = 0
    for m in history:
        while j < len(pending) and pending[j].ts <= m.ts:
            out[pending[j].event_id] = rating.forecast(pending[j])
            j += 1
        if j >= len(pending):
            return out
        rating.update(m)
    while j < len(pending):
        out[pending[j].event_id] = rating.forecast(pending[j])
        j += 1
    return out


@dataclass
class Walker:
    """forecast_fixtures one fixture at a time: the rating walked forward
    through the history up to (excluding) each requested start. Requests in
    start order cost one pass; an earlier start restarts the walk (exact
    either way)."""

    history: Sequence[vpm.VbMatch]
    params: vpm.VbParams = PARAMS
    _rating: vpm.VbRating | None = None
    _i: int = 0
    _started: dict[int, int] = field(default_factory=dict)
    _done: dict[int, vpm.VbForecast] = field(default_factory=dict)

    def forecast(self, m: vpm.VbMatch) -> vpm.VbForecast:
        if m.event_id in self._done:
            return self._done[m.event_id]
        if not self._started:
            self._started = {h.event_id: h.ts for h in self.history}
        ts = min(m.ts, self._started.get(m.event_id, m.ts))
        if self._rating is None or (self._i > 0 and self.history[self._i - 1].ts >= ts):
            self._rating, self._i = vpm.VbRating(self.params), 0
        while self._i < len(self.history) and self.history[self._i].ts < ts:
            self._rating.update(self.history[self._i])
            self._i += 1
        f = self._rating.forecast(vpm.VbMatch(
            m.event_id, ts, m.competition, m.home, m.away, m.women, (), ()))
        self._done[m.event_id] = f
        return f


@dataclass
class VbPricer:
    """The day's forecasts, simulated lazily per fixture."""

    forecasts: Mapping[int, vpm.VbForecast]
    params: vpm.VbParams = PARAMS
    sims: int = N_SIMS
    _cache: dict[int, vpm.VbSim] = field(default_factory=dict)

    def sim(self, event_id: int) -> vpm.VbSim | None:
        f = self.forecasts.get(event_id)
        if f is None:
            return None
        s = self._cache.get(event_id)
        if s is None:
            s = vpm.simulate(f, self.params, n=self.sims, seed=seed_of(event_id))
            self._cache[event_id] = s
        return s

    def p(self, event_id: int, home_is_team1: bool, market_id: int, period: int,
          subject: str, line: float | None, side: str) -> float | None:
        """P(the side wins | the line is decided), Superbet's orientation."""
        if not in_scope("volleyball", market_id):
            return None
        s = self.sim(event_id)
        if s is None:
            return None
        return vpm.line_p(s if home_is_team1 else s.swapped(), int(market_id),
                          int(period), subject or "", line, side)


def backfill_key(day: str, superbet_event_id: object, market_id: object,
                 period: object, subject: object, line: object, side: object) -> str:
    ln = "" if line is None else f"{float(str(line)):g}"
    return (f"{day}|{superbet_event_id}|{int(str(market_id))}|{int(str(period or 0))}|"
            f"{subject or ''}|{ln}|{side}")


def load_backfill(path: Path | None = None) -> dict[str, float]:
    """`BACKFILL` ({} when absent: the lines are then no evidence)."""
    p = path if path is not None else BACKFILL
    if not p.exists():
        return {}
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        doc: dict[str, float] = json.load(fh)
    return doc


def write_backfill(table: Mapping[str, float], path: Path | None = None) -> None:
    from bet.sofa.atomic import write_bytes_atomic

    p = path if path is not None else BACKFILL
    p.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_atomic(p, gzip.compress(json.dumps(dict(sorted(table.items())))
                                  .encode("utf-8")))


def describe(f: vpm.VbForecast | None) -> str:
    if f is None:
        return f"{NOTE}: no forecast"
    return (f"{NOTE}: d {f.mu:+.3f} (sd {f.var ** 0.5:.3f}), side-out "
            f"{f.sideout:.2f}, matches seen {f.rated[0]} / {f.rated[1]}")
