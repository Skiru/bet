"""A rally-point model of volleyball
(docs/sofa/evidence/volleyball_point_model_2026-11-06.md). SPORT_CONFIDENCE
reads it only through bet.sofa.vb_point_pricer, under epochs.VB_POINT_MODEL.

The rally as the unit (rally-point scoring: every rally scores a point and
the rally's winner serves next). Team i against team j:

    P(i wins a rally | i serves)    = sigmoid(logit(1 - so) + d)
    P(i wins a rally | j serves)    = sigmoid(logit(so) + d)
    d = theta_i - theta_j (+ home)

``so`` is the side-out rate of the match's cell (gender): the probability the
receiving side wins an even rally. With so > 0.5 points alternate and a set
is closer than independent rallies at the same point share would make it
(Ferrante & Fonseca 2014; the serve Markov chain of Lee & Chin 2004 and
Barnett et al.). ``so`` is fitted by maximum likelihood of exact set scores
(``set_score_table``: the set as a Markov chain over (score, server)).

The rating is as of each match: one logit strength per team, an extended
Kalman step on the match's point share (the chain's stationary share as the
expectation, the observation counted as ``weight`` x points), a new team's
prior centred on the mean of its competition's rated teams (shrinkage to the
league), variance growing with time (drift). Opponent adjustment is the
pairwise logit itself.

A match is simulated rally by rally (``simulate``): sets to 25, the fifth to
15, two clear; best of five; the rally's winner serves; set 1 and set 5 open
with a coin toss, sets 2-4 alternate. Each simulated match draws d from the
rating's uncertainty plus a match-day shock, each set adds its own shock.
Every market is read off the same simulations (``line_p``) with the
settlement semantics of SHADOW_SETTLE (shadow.actual_value / cs2.grade_side,
a push left out) - tested against score_model.line_probability.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
import numpy.typing as npt

from bet.sofa.cs2 import exact_score, sets_count_of
from bet.sofa.shadow import GameResult, spec_of

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
DAY = 86400.0
SET_TARGET = 25
DECIDER_TARGET = 15
N_SIMS = 4000
# Gauss-Hermite nodes (probabilists') for the predictive likelihood.
_GH_MATCH = np.polynomial.hermite_e.hermegauss(9)
_GH_SET = np.polynomial.hermite_e.hermegauss(5)
D_STEP = 0.02  # d is rounded to this for the cached set-score tables


@dataclass(frozen=True)
class VbMatch:
    """One finished best-of-five match with its set scores (home first)."""

    event_id: int
    ts: int
    competition: int
    home: int
    away: int
    women: bool
    home_sets: tuple[int, ...]
    away_sets: tuple[int, ...]

    @property
    def points(self) -> tuple[int, int]:
        return sum(self.home_sets), sum(self.away_sets)


@dataclass(frozen=True)
class VbParams:
    prior_var: float = 0.10
    drift_per_day: float = 0.0003
    weight: float = 0.5  # observed points counted at this weight
    home: float = 0.04  # home edge on d
    form_var: float = 0.01  # match-day shock on d
    set_var: float = 0.0  # per-set shock on d
    sideout_men: float = 0.64
    sideout_women: float = 0.60
    min_league_teams: int = 4

    def sideout(self, women: bool) -> float:
        return self.sideout_women if women else self.sideout_men


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def rally_probabilities(d: float, sideout: float) -> tuple[float, float]:
    """(P(A wins | A serves), P(A wins | B serves))."""
    return (_sigmoid(_logit(1.0 - sideout) + d), _sigmoid(_logit(sideout) + d))


def stationary_share(d: float, sideout: float) -> float:
    """A's long-run share of rallies: the serve chain's stationary mix."""
    pa, pb = rally_probabilities(d, sideout)
    pi = pb / (1.0 - pa + pb)  # P(A serves)
    return pi * pa + (1.0 - pi) * pb


# --------------------------------------------------------------------------
# The rating
# --------------------------------------------------------------------------


@dataclass
class _Belief:
    mu: float
    var: float
    ts: float


@dataclass(frozen=True)
class VbForecast:
    mu: float  # expected d (home minus away, incl. home edge)
    var: float  # rating uncertainty of d
    sideout: float
    women: bool
    rated: tuple[int, int] = (0, 0)  # matches the rating has seen per side


@dataclass
class VbRating:
    params: VbParams = field(default_factory=VbParams)
    beliefs: dict[int, _Belief] = field(default_factory=dict)
    seen: dict[int, int] = field(default_factory=dict)
    league: dict[int, set[int]] = field(default_factory=dict)

    def _prior_mean(self, competition: int) -> float:
        teams = [t for t in self.league.get(competition, ()) if t in self.beliefs]
        if len(teams) < self.params.min_league_teams:
            return 0.0
        return sum(self.beliefs[t].mu for t in teams) / len(teams)

    def _belief(self, team: int, competition: int, ts: float) -> _Belief:
        b = self.beliefs.get(team)
        if b is None:
            return _Belief(self._prior_mean(competition), self.params.prior_var, ts)
        days = max(0.0, (ts - b.ts) / DAY)
        return _Belief(b.mu, min(b.var + self.params.drift_per_day * days,
                                 self.params.prior_var), ts)

    def forecast(self, m: VbMatch) -> VbForecast:
        bh = self._belief(m.home, m.competition, m.ts)
        ba = self._belief(m.away, m.competition, m.ts)
        return VbForecast(bh.mu - ba.mu + self.params.home, bh.var + ba.var,
                          self.params.sideout(m.women), m.women,
                          (self.seen.get(m.home, 0), self.seen.get(m.away, 0)))

    def update(self, m: VbMatch) -> None:
        prm = self.params
        bh = self._belief(m.home, m.competition, m.ts)
        ba = self._belief(m.away, m.competition, m.ts)
        so = prm.sideout(m.women)
        d = bh.mu - ba.mu + prm.home
        s = stationary_share(d, so)
        eps = 1e-4
        h = (stationary_share(d + eps, so) - stationary_share(d - eps, so)) / (2 * eps)
        ph, pa = m.points
        n = ph + pa
        if n <= 0:
            return
        r = s * (1.0 - s) / (prm.weight * n) + h * h * prm.form_var
        innov = ph / n - s
        total = h * h * (bh.var + ba.var) + r
        kh, ka = bh.var * h / total, ba.var * h / total
        self.beliefs[m.home] = _Belief(bh.mu + kh * innov,
                                       bh.var - bh.var * bh.var * h * h / total, m.ts)
        self.beliefs[m.away] = _Belief(ba.mu - ka * innov,
                                       ba.var - ba.var * ba.var * h * h / total, m.ts)
        for t in (m.home, m.away):
            self.seen[t] = self.seen.get(t, 0) + 1
            self.league.setdefault(m.competition, set()).add(t)


def walk_forward(matches: Sequence[VbMatch], wanted: Iterable[int],
                 params: VbParams | None = None) -> dict[int, VbForecast]:
    """Forecast every wanted match from the state before its start (matches
    starting at the same second all forecast before any teaches)."""
    rating = VbRating(params or VbParams())
    want = set(wanted)
    out: dict[int, VbForecast] = {}
    i = 0
    while i < len(matches):
        j = i
        while j < len(matches) and matches[j].ts == matches[i].ts:
            j += 1
        for m in matches[i:j]:
            if m.event_id in want:
                out[m.event_id] = rating.forecast(m)
        for m in matches[i:j]:
            rating.update(m)
        i = j
    return out


# --------------------------------------------------------------------------
# Exact set scores (the likelihood)
# --------------------------------------------------------------------------


def set_over(a: int, b: int, target: int) -> bool:
    return (a >= target or b >= target) and abs(a - b) >= 2


@lru_cache(maxsize=200_000)
def set_score_table(d: float, sideout: float, target: int,
                    a_serves_first: bool | None = None) -> dict[tuple[int, int], float]:
    """P(the set ends a:b) for A at d; first server A / B, or None = a coin.
    Scores past target + 80 a side are dropped (mass < 1e-9 at any
    realistic d; past the target only the near-diagonal states live, so a
    long cap costs little)."""
    if a_serves_first is None:
        ta = set_score_table(d, sideout, target, True)
        tb = set_score_table(d, sideout, target, False)
        return {k: 0.5 * ta.get(k, 0.0) + 0.5 * tb.get(k, 0.0)
                for k in set(ta) | set(tb)}
    pa, pb = rally_probabilities(d, sideout)
    cap = target + 80
    # state (a, b) -> [P(A serves), P(B serves)]
    cur: dict[tuple[int, int], list[float]] = {
        (0, 0): [1.0, 0.0] if a_serves_first else [0.0, 1.0]}
    out: dict[tuple[int, int], float] = {}
    for _ in range(2 * cap):
        nxt: dict[tuple[int, int], list[float]] = {}
        for (a, b), (sa, sb) in cur.items():
            win = sa * pa + sb * pb
            lose = sa * (1.0 - pa) + sb * (1.0 - pb)
            steps = (((a + 1, b), win, True), ((a, b + 1), lose, False))
            for key, mass, a_srv in steps:
                if mass <= 0.0:
                    continue
                if set_over(key[0], key[1], target):
                    out[key] = out.get(key, 0.0) + mass
                elif key[0] <= cap and key[1] <= cap:
                    slot = nxt.setdefault(key, [0.0, 0.0])
                    slot[0 if a_srv else 1] += mass
        cur = nxt
        if not cur:
            break
    return out


def _q(d: float) -> float:
    return round(round(d / D_STEP) * D_STEP, 6)


def _set_prob(d: float, sideout: float, target: int, score: tuple[int, int],
              set_var: float) -> float:
    if set_var <= 0:
        return set_score_table(_q(d), sideout, target).get(score, 0.0)
    nodes, weights = _GH_SET
    sd = math.sqrt(set_var)
    tot = 0.0
    for z, w in zip(nodes, weights, strict=True):
        table = set_score_table(_q(d + sd * float(z)), sideout, target)
        tot += w * table.get(score, 0.0)
    return tot / math.sqrt(2.0 * math.pi)


def match_loglik(f: VbForecast, home_sets: Sequence[int], away_sets: Sequence[int],
                 params: VbParams) -> float:
    """log P(the exact sequence of set scores) under the forecast: one shock
    on d per match (rating variance + form), one per set."""
    nodes, weights = _GH_MATCH
    sd = math.sqrt(max(f.var + params.form_var, 1e-12))
    total = 0.0
    for z, w in zip(nodes, weights, strict=True):
        d = f.mu + sd * float(z)
        prob = 1.0
        for k, (a, b) in enumerate(zip(home_sets, away_sets, strict=True)):
            target = DECIDER_TARGET if k == 4 else SET_TARGET
            prob *= _set_prob(d, f.sideout, target, (a, b), params.set_var)
            if prob == 0.0:
                break
        total += w * prob
    total /= math.sqrt(2.0 * math.pi)
    return math.log(max(total, 1e-300))


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class VbSim:
    """Per simulated match: points per set [S, 5, 2] (0 = team1) and sets
    played [S]."""

    points: IntArray
    sets_played: IntArray

    def swapped(self) -> VbSim:
        return VbSim(self.points[:, :, ::-1].copy(), self.sets_played)

    def game(self, s: int) -> GameResult:
        """Simulation s as shadow's GameResult (team1 = column 0)."""
        k = int(self.sets_played[s])
        t1 = tuple(int(x) for x in self.points[s, :k, 0])
        t2 = tuple(int(x) for x in self.points[s, :k, 1])
        w1 = sum(1 for a, b in zip(t1, t2, strict=True) if a > b)
        w2 = k - w1
        return GameResult(t1, t2, w1, w2, "T1" if w1 > w2 else "T2", False)


def simulate(f: VbForecast, params: VbParams, n: int = N_SIMS, seed: int = 0) -> VbSim:
    rng = np.random.default_rng(seed)
    sd = math.sqrt(max(f.var + params.form_var, 0.0))
    d_match = f.mu + rng.normal(0.0, 1.0, n) * sd
    points = np.zeros((n, 5, 2), dtype=np.int64)
    wins = np.zeros((n, 2), dtype=np.int64)
    sets_played = np.zeros(n, dtype=np.int64)
    alive = np.ones(n, dtype=bool)
    first = rng.integers(0, 2, n).astype(bool)  # True: team1 serves set 1
    lo_a = _logit(1.0 - f.sideout)
    lo_b = _logit(f.sideout)
    for k in range(5):
        idx = np.flatnonzero(alive)
        if not len(idx):
            break
        target = DECIDER_TARGET if k == 4 else SET_TARGET
        d = d_match[idx]
        if params.set_var > 0:
            d = d + rng.normal(0.0, math.sqrt(params.set_var), len(idx))
        pa = 1.0 / (1.0 + np.exp(-(lo_a + d)))
        pb = 1.0 / (1.0 + np.exp(-(lo_b + d)))
        if k == 4:
            serve1 = rng.integers(0, 2, len(idx)).astype(bool)
        elif k % 2 == 0:
            serve1 = first[idx].copy()
        else:
            serve1 = ~first[idx]
        a = np.zeros(len(idx), dtype=np.int64)
        b = np.zeros(len(idx), dtype=np.int64)
        live = np.ones(len(idx), dtype=bool)
        guard = 0
        while live.any():
            guard += 1
            if guard > 400:
                raise RuntimeError("set did not end")
            li = np.flatnonzero(live)
            p = np.where(serve1[li], pa[li], pb[li])
            won = rng.random(len(li)) < p
            a[li] += won
            b[li] += ~won
            serve1[li] = won
            al, bl = a[li], b[li]
            done = ((al >= target) | (bl >= target)) & (np.abs(al - bl) >= 2)
            live[li[done]] = False
        points[idx, k, 0] = a
        points[idx, k, 1] = b
        sets_played[idx] += 1
        wins[idx, 0] += a > b
        wins[idx, 1] += b > a
        alive[idx] = (wins[idx, 0] < 3) & (wins[idx, 1] < 3)
    return VbSim(points, sets_played)


# --------------------------------------------------------------------------
# Markets (SHADOW_SETTLE semantics, vectorised)
# --------------------------------------------------------------------------


def _pair(sim: VbSim, scope: str, period: int
          ) -> tuple[IntArray, IntArray, npt.NDArray[np.bool_]] | None:
    p = sim.points
    if scope == "full":
        return (p[:, :, 0].sum(axis=1), p[:, :, 1].sum(axis=1),
                np.ones(len(p), dtype=bool))
    if scope == "sets":
        w1 = (p[:, :, 0] > p[:, :, 1]).sum(axis=1)
        w2 = (p[:, :, 1] > p[:, :, 0]).sum(axis=1)
        return w1, w2, np.ones(len(p), dtype=bool)
    if scope == "period":
        if not 1 <= period <= 5:
            return None
        return (p[:, period - 1, 0], p[:, period - 1, 1], sim.sets_played >= period)
    return None


def actual_values(sim: VbSim, market_id: int, period: int, subject: str,
                  line: float | None, side: str
                  ) -> tuple[FloatArray, npt.NDArray[np.bool_]] | None:
    """The quantity each simulation is graded on and where it is defined
    (shadow.actual_value, vectorised)."""
    spec = spec_of("volleyball", market_id)
    if spec is None:
        return None
    pair = _pair(sim, spec.scope, period)
    if pair is None:
        return None
    a, b, ok = pair
    af, bf = a.astype(np.float64), b.astype(np.float64)
    if spec.kind == "winner":
        return np.where(a > b, 1.0, -1.0), ok
    if spec.kind == "set_yes_no":
        own = af if spec.team == "T1" else bf
        if spec.family == "team_wins_set":
            return (own >= 1).astype(np.float64), ok
        if line is None:
            return None
        return (own == int(line)).astype(np.float64), ok
    if spec.kind == "sets_count":
        return af + bf, ok
    if spec.kind == "exact":
        score = exact_score(side)
        if score is None:
            return None
        return ((a == score[0]) & (b == score[1])).astype(np.float64), ok
    if spec.kind == "yes_no":
        target = DECIDER_TARGET if period == 5 else SET_TARGET
        return (np.maximum(af, bf) > target).astype(np.float64), ok
    if spec.kind == "odd_even":
        if spec.team is not None:
            return (af if spec.team == "T1" else bf), ok
        return af + bf, ok
    if spec.kind == "total":
        return af + bf, ok
    if spec.kind == "team_total":
        return (af if subject == "T1" else bf), ok
    return af - bf, ok


def win_loss(side: str, actual: FloatArray, line: float | None
             ) -> tuple[npt.NDArray[np.bool_], npt.NDArray[np.bool_]]:
    """(won, decided) per simulation - cs2.grade_side vectorised (two-way
    and the indicator sides; a push is not decided)."""
    ones = np.ones(len(actual), dtype=bool)
    if side in ("OVER", "UNDER"):
        if line is None:
            return np.zeros(len(actual), dtype=bool), np.zeros(len(actual), dtype=bool)
        dec = actual != line
        return ((actual > line) == (side == "OVER")) & dec, dec
    if side in ("ODD", "EVEN"):
        odd = actual.astype(np.int64) % 2 == 1
        return odd == (side == "ODD"), ones
    if side in ("YES", "NO"):
        return (actual == 1.0) == (side == "YES"), ones
    if exact_score(side) is not None:
        return actual == 1.0, ones
    count = sets_count_of(side)
    if count is not None:
        return actual == float(count), ones
    margin = actual + (line or 0.0)
    dec = margin != 0
    return ((margin > 0) == (side == "T1")) & dec, dec


def line_p(sim: VbSim, market_id: int, period: int, subject: str,
           line: float | None, side: str) -> float | None:
    """P(this side wins | the line is decided), as score_model.line_probability
    grades it; None when the market is not read or never decided."""
    found = actual_values(sim, market_id, period, subject, line, side)
    if found is None:
        return None
    actual, ok = found
    won, decided = win_loss(side, actual, line)
    mask = ok & decided
    if not mask.any():
        return None
    return float(won[mask].mean())


def quantile_lines(sim: VbSim, market_id: int, period: int,
                   quantiles: Sequence[float]) -> list[float]:
    """sport_confidence.synthetic_lines' cut points: floor of the game's own
    simulated quantity at each quantile, + 0.5 (totals; a handicap's line is
    then -cut)."""
    spec = spec_of("volleyball", market_id)
    if spec is None:
        return []
    found = actual_values(sim, market_id, period, spec.team or "", 0.5, "OVER")
    if found is None:
        return []
    actual, ok = found
    values = np.sort(actual[ok])
    if not len(values):
        return []
    return sorted({float(math.floor(values[int(q * (len(values) - 1))])) + 0.5
                   for q in quantiles})
