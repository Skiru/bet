"""A bottom-up tennis model: points -> games -> sets -> match, and the serve
counts read off the same simulated match (plan B of
docs/sofa/evidence/tennis_serve_markets_plan_2026-10-26.md; measured in
docs/sofa/evidence/tennis_point_model_2026-11-05.md).

SHEET reads this module only under ``epochs.TENNIS_POINT_MODEL_FROM_UTC``
(operator 2026-11-05), through bet.sofa.tennis_point_sheet, for the per-set
games and serve-count rows (``epochs.TENNIS_POINT_MODEL_MARKETS``); a test
holds that no other stage imports it. The model itself is unchanged from the
frozen measurement.

What it is, in order:

  1. **Serve / return rating per player, as of each match.** For a server i
     and a returner j the logit of the probability that i wins a point on his
     own serve is ``c[gender, tier, surface] + S_i - R_j`` (the
     Klaassen-Magnus / Barnett-Clarke combination: the server's serve
     strength against the returner's return strength, around the tour mean
     of the cell, here on the logit scale so that it never leaves [0, 1]).
     S and R are Gaussian beliefs updated online, match by match in time
     order, by an assumed-density (extended Kalman) step on the binomial
     count of serve points won - a Glicko-like rating at point level. That
     choice is what makes the model *as of* for free: a match is forecast
     from the beliefs before it and only then updated, so the walk-forward
     on 100k+ matches is one pass, and the shrinkage to the prior (a new
     player starts at the cell mean with ``prior_var``) and the loss of
     certainty over time (``drift_per_day``) are explicit. A match-day
     "form" variance (``form_var``) tempers each update (a player's points
     in one match are not independent draws) and widens the forecast.
  2. **Ace and double-fault rates per own serve point**, the same online
     step on (aces, serve points) and (double faults, serve points): logit
     rate = ``cell + server + returner + tournament`` for aces (the
     returner's "aces conceded" and the tournament's courts / balls),
     ``cell + server + tournament`` for double faults.
  3. **The match, simulated point by point** (``simulate``): the two serve
     point probabilities are drawn per simulation from the rating's
     uncertainty plus the form noise (a shared dominance component - the
     player having a good day serves AND returns better), then the match is
     played with tiebreaks at 6-6 and best of three (a 10-point match
     tiebreak as the decider where the tournament's own past three-setters
     say so; counted as one game, the pipeline's convention). Games total,
     sets, per-set games, games won and each player's serve points per set
     all come off the same simulated matches, so the markets of one match
     can never contradict each other.
  4. **Serve counts** given the simulated serve points: negative binomial
     with mean ``rate x serve points`` and a shape measured on the history
     (``count_sf``) - not Poisson by default.

Pure: no I/O except ``load_point_history`` (read-only SQLite).
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from bet.sofa.listing_index import iter_indexed_events
from bet.sofa.tennis_rating import best_of, parse_event
from bet.sofa.tennis_score import match_tiebreak_sets

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]

# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

_FRAC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)")
# Sofascore's per-set statistics periods (tennis periods carry aces and
# double faults only - metrics.TENNIS_METRICS).
SET_PERIODS = ("1ST", "2ND", "3RD")


@dataclass(frozen=True)
class SideServe:
    """One side's serve counts in one match (Sofascore /statistics)."""

    played: int  # serve points played (first + second serve points)
    won: int  # serve points won
    aces: int | None
    dfs: int | None
    # Aces / double faults per set (1ST, 2ND, 3RD); None where not reported.
    set_aces: tuple[int | None, ...] = ()
    set_dfs: tuple[int | None, ...] = ()


@dataclass(frozen=True)
class PointMatch:
    """One finished singles match the model can learn from and forecast."""

    event_id: int
    ts: int
    tier: str  # tennis_rating.tier_group: ITF / CH / TOUR
    surface: str  # hard / clay / grass
    female: bool
    tournament: int | None  # Sofascore unique tournament id
    home_id: int
    away_id: int
    home_won: bool
    sets: tuple[tuple[int, int], ...]  # games per set, a match TB = 1-0
    completed: bool  # Ended with >= 2 sets (not retired)
    best_of: int | None
    match_tiebreak_decider: bool  # the third set was a 10-point match TB
    home: SideServe | None = None
    away: SideServe | None = None

    @property
    def gender(self) -> str:
        return "F" if self.female else "M"


def _frac(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    m = _FRAC.match(str(value))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _period_items(doc: Mapping[str, Any]) -> dict[str, dict[str, tuple[Any, Any]]]:
    out: dict[str, dict[str, tuple[Any, Any]]] = {}
    for period in doc.get("statistics") or []:
        if not isinstance(period, Mapping):
            continue
        name = str(period.get("period") or "ALL")
        items = out.setdefault(name, {})
        for group in period.get("groups") or []:
            for item in (group or {}).get("statisticsItems") or []:
                key = item.get("key") or item.get("name")
                items[str(key)] = (item.get("home"), item.get("away"))
    return out


def parse_serve_stats(
    statistics: Mapping[str, Any] | str | None,
) -> tuple[SideServe, SideServe] | None:
    """(home, away) serve counts, or None when the payload is unusable.

    Serve points come from the first / second serve points splits, the only
    items that carry a denominator; the identities between the two sides
    (one side's serve points are the other's return points, won + won by the
    returner = played) must hold or the match is dropped as misread."""
    if statistics is None:
        return None
    if isinstance(statistics, str):
        try:
            doc = json.loads(statistics)
        except ValueError:
            return None
    else:
        doc = statistics
    if not isinstance(doc, Mapping):
        return None
    periods = _period_items(doc)
    items = periods.get("ALL")
    if not items:
        return None
    need = ("firstServePointsAccuracy", "secondServePointsAccuracy",
            "firstReturnPoints", "secondReturnPoints")
    if not all(k in items for k in need):
        return None
    sides: list[tuple[int, int, int, int]] = []
    for i in (0, 1):
        f1, f2 = _frac(items[need[0]][i]), _frac(items[need[1]][i])
        r1, r2 = _frac(items[need[2]][i]), _frac(items[need[3]][i])
        if not (f1 and f2 and r1 and r2):
            return None
        played, returned = f1[1] + f2[1], r1[1] + r2[1]
        if played <= 0 or returned <= 0:
            return None
        sides.append((f1[0] + f2[0], played, r1[0] + r2[0], returned))
    (hw, hp, hrw, hrp), (aw, ap, arw, arp) = sides
    if hp != arp or ap != hrp or hw + arw != hp or aw + hrw != ap:
        return None

    def count(period: str, key: str, i: int) -> int | None:
        pair = periods.get(period, {}).get(key)
        return None if pair is None else _int(pair[i])

    out: list[SideServe] = []
    for i, (won, played) in enumerate(((hw, hp), (aw, ap))):
        out.append(SideServe(
            played=played, won=won,
            aces=count("ALL", "aces", i), dfs=count("ALL", "doubleFaults", i),
            set_aces=tuple(count(p, "aces", i) for p in SET_PERIODS),
            set_dfs=tuple(count(p, "doubleFaults", i) for p in SET_PERIODS),
        ))
    return out[0], out[1]


def point_match_from_event(event: Mapping[str, Any]) -> PointMatch | None:
    """A listing event -> PointMatch (no serve counts yet), through the
    rating's own reader (``tennis_rating.parse_event`` with the
    TENNIS_RATING_SCORE_WINNER rule): friendlies / exhibitions, walkovers,
    doubles and unreadable scores are out. Retired matches come back with
    ``completed=False``."""
    result = parse_event(event, score_winner=True)
    if result is None:
        return None
    tournament = event.get("tournament") or {}
    unique = tournament.get("uniqueTournament") or {}
    tid = unique.get("id") if isinstance(unique, Mapping) else None
    if not isinstance(tid, int):
        tid = tournament.get("id") if isinstance(tournament.get("id"), int) else None
    hs, as_ = event.get("homeScore") or {}, event.get("awayScore") or {}
    return PointMatch(
        event_id=result.event_id, ts=result.ts, tier=result.tier,
        surface=result.surface, female=result.female, tournament=tid,
        home_id=result.home_id, away_id=result.away_id,
        home_won=result.home_won, sets=result.sets, completed=result.completed,
        best_of=best_of(result),
        match_tiebreak_decider=3 in match_tiebreak_sets(hs, as_),
    )


def load_point_history(db_path: str | Path) -> list[PointMatch]:
    """Every distinct finished singles match of the cached player listings
    (the rating's sources: ``kind = 'last'`` pages and the listing index,
    the newer copy winning), with its serve counts where the cache holds
    them, in time order. Read-only."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        seen: dict[int, PointMatch] = {}
        fetched: dict[int, str] = {}
        for events_json, fetched_at in conn.execute(
            "SELECT events_json, fetched_at FROM sofa_entity_events "
            "WHERE kind = 'last' AND events_json LIKE '%\"slug\": \"tennis\"%'"
        ):
            for event in json.loads(events_json).get("events", []):
                eid = event.get("id") if isinstance(event, dict) else None
                match = point_match_from_event(event)
                if match is not None:
                    seen[match.event_id] = match
                if isinstance(eid, int):
                    fetched[eid] = str(fetched_at)
        for event in iter_indexed_events(conn, fetched, sport="tennis"):
            match = point_match_from_event(event)
            if match is not None:
                seen[match.event_id] = match
            else:
                seen.pop(event["id"], None)
        ids = sorted(seen)
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            marks = ",".join("?" * len(chunk))
            for eid, stats_json in conn.execute(
                "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats "
                f"WHERE sofascore_event_id IN ({marks}) "
                "AND statistics_json IS NOT NULL", chunk,
            ):
                parsed = parse_serve_stats(stats_json)
                if parsed is not None:
                    m = seen[int(eid)]
                    seen[int(eid)] = _with_serve(m, parsed)
    finally:
        conn.close()
    return sorted(seen.values(), key=lambda m: (m.ts, m.event_id))


def _with_serve(m: PointMatch, serve: tuple[SideServe, SideServe]) -> PointMatch:
    return PointMatch(
        event_id=m.event_id, ts=m.ts, tier=m.tier, surface=m.surface,
        female=m.female, tournament=m.tournament, home_id=m.home_id,
        away_id=m.away_id, home_won=m.home_won, sets=m.sets,
        completed=m.completed, best_of=m.best_of,
        match_tiebreak_decider=m.match_tiebreak_decider,
        home=serve[0], away=serve[1],
    )


# --------------------------------------------------------------------------
# Online rating (assumed-density Gaussian beliefs on a binomial logit)
# --------------------------------------------------------------------------

DAY = 86400.0


@dataclass
class _Belief:
    mean: float
    var: float
    ts: int


@dataclass(frozen=True)
class RatingParams:
    """Constants of one online binomial-logit rating. The defaults are the
    values chosen on the history before 2026-01-01 (report section 2)."""

    prior_var: float
    drift_per_day: float
    form_var: float
    # Prior variance of the tournament effect (0 = no tournament term).
    tournament_var: float = 0.0
    # Prior variance of the returner term (0 = no returner term).
    returner_var: float = 0.0


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


@dataclass
class _Cell:
    hits: float = 0.0
    trials: float = 0.0


@dataclass
class LogitRating:
    """logit P(success per trial) = cell + server - returner + tournament,
    every term but the cell a Gaussian belief.

    For the serve-point rating the server term is S (serve strength) and the
    returner term R (return strength, subtracted). For aces the returner term
    is "aces conceded" and is ADDED (``returner_sign = +1``).
    """

    params: RatingParams
    returner_sign: float = -1.0
    servers: dict[int, _Belief] = field(default_factory=dict)
    returners: dict[int, _Belief] = field(default_factory=dict)
    tournaments: dict[int, _Belief] = field(default_factory=dict)
    cells: dict[tuple[str, str, str], _Cell] = field(default_factory=dict)
    trials: dict[int, float] = field(default_factory=dict)

    def _belief(self, table: dict[int, _Belief], key: int, prior_var: float,
                ts: int) -> _Belief:
        b = table.get(key)
        if b is None:
            return _Belief(0.0, prior_var, ts)
        days = max(0.0, (ts - b.ts) / DAY)
        var = min(prior_var, b.var + self.params.drift_per_day * days)
        return _Belief(b.mean, var, ts)

    def cell_logit(self, cell: tuple[str, str, str]) -> float:
        c = self.cells.get(cell)
        if c is None or c.trials < 500:
            # The gender's pooled rate, then the whole pool's.
            hits = sum(v.hits for k, v in self.cells.items() if k[0] == cell[0])
            trials = sum(v.trials for k, v in self.cells.items() if k[0] == cell[0])
            if trials < 500:
                hits = sum(v.hits for v in self.cells.values())
                trials = sum(v.trials for v in self.cells.values())
            if trials <= 0:
                return 0.0
            return _logit(hits / trials)
        return _logit(c.hits / c.trials)

    def _terms(self, server: int, returner: int, tournament: int | None,
               ts: int) -> list[tuple[dict[int, _Belief], int, _Belief, float]]:
        p = self.params
        terms = [(self.servers, server,
                  self._belief(self.servers, server, p.prior_var, ts), 1.0)]
        if p.returner_var > 0:
            terms.append((self.returners, returner,
                          self._belief(self.returners, returner, p.returner_var, ts),
                          self.returner_sign))
        if p.tournament_var > 0 and tournament is not None:
            terms.append((self.tournaments, tournament,
                          self._belief(self.tournaments, tournament,
                                       p.tournament_var, ts), 1.0))
        return terms

    def predict(self, server: int, returner: int, cell: tuple[str, str, str],
                tournament: int | None, ts: int) -> tuple[float, float]:
        """(logit mean, variance of the rating's belief) for one side."""
        terms = self._terms(server, returner, tournament, ts)
        mean = self.cell_logit(cell) + sum(s * b.mean for _, _, b, s in terms)
        var = sum(b.var for _, _, b, _ in terms)
        return mean, var

    def update(self, server: int, returner: int, cell: tuple[str, str, str],
               tournament: int | None, ts: int, hits: float, trials: float,
               real: bool = True) -> None:
        """One observation; ``real=False`` (score pseudo-points) moves the
        beliefs only, never the cell rate or the player's point count."""
        if trials <= 0:
            return
        terms = self._terms(server, returner, tournament, ts)
        eta = self.cell_logit(cell) + sum(s * b.mean for _, _, b, s in terms)
        prob = _sigmoid(eta)
        info = trials * prob * (1.0 - prob)
        damp = 1.0 + self.params.form_var * info
        grad = (hits - trials * prob) / damp
        info_eff = info / damp
        v_par = sum(b.var for _, _, b, _ in terms)
        denom = 1.0 + v_par * info_eff
        for table, key, b, sign in terms:
            mean = b.mean + sign * b.var * grad / denom
            var = max(1e-6, b.var - b.var * b.var * info_eff / denom)
            table[key] = _Belief(mean, var, ts)
        if not real:
            return
        c = self.cells.setdefault(cell, _Cell())
        c.hits += hits
        c.trials += trials
        self.trials[server] = self.trials.get(server, 0.0) + trials


# Constants chosen on the history before 2026-01-01 (report section 2;
# scripts/sofa/measure_tennis_point_model.py --tune). Never fitted on
# Superbet lines.
SERVE_PARAMS = RatingParams(prior_var=0.1, drift_per_day=0.0001,
                            form_var=0.1, returner_var=0.1)
ACE_PARAMS = RatingParams(prior_var=0.3, drift_per_day=0.0005,
                          form_var=0.2, returner_var=0.05,
                          tournament_var=0.05)
DF_PARAMS = RatingParams(prior_var=0.15, drift_per_day=0.0005,
                         form_var=0.05, tournament_var=0.03)
# Match-day form on the serve logit (beyond binomial noise and the rating's
# own uncertainty): variance per side and the covariance between the two
# sides (negative: dominance). Measured on the history before 2026-01-01
# (2025-09..12, 7,621 matches with both sides rated: 0.081 / -0.048); half
# of it ships - on 3,000 validation matches the games-total log likelihood
# was 2.9638 / 2.9496 / 2.9490 / 2.9683 at 0 / 0.25 / 0.5 / 1 x the measured
# values (sets log loss 0.5879 / 0.5804 / 0.5780 / 0.5792): the measured
# excess also holds rating error the belief variance already carries.
FORM_VAR = 0.04
FORM_COV = -0.0225
# Negative binomial shapes of the serve counts given the simulated serve
# points (match and per set), measured on the history before 2026-01-01.
NB_SHAPE = {"aces": 4.0, "dfs": 10.0, "aces_set": 5.0, "dfs_set": 10.0}
# Same window, form x 0.5: games log likelihood 2.9977 / 2.9572 / 2.9490 and
# sets log loss 0.5912 / 0.5801 / 0.5780 at SCORE_WEIGHT 0 / 0.3 / 0.7.
# A match with no serve counts (most ITF matches before and after 2025-05)
# teaches the serve rating from its score: the games share is inverted into
# a logit shift of the two serve probabilities (``score_shift``) and observed
# as ``SCORE_WEIGHT x POINTS_PER_GAME_PER_SIDE x games`` pseudo-points per
# side - a score carries less than its points, so the weight is < 1 and was
# chosen on the history before 2026-01-01. Never written into cell rates.
SCORE_WEIGHT = 0.7
POINTS_PER_GAME_PER_SIDE = 3.15


def cell_of(m: PointMatch) -> tuple[str, str, str]:
    return (m.gender, m.tier, m.surface)


@dataclass
class DeciderBook:
    """Per tournament, as of each match: is the deciding set a 10-point
    match tiebreak? (ITF / UTR formats; Superbet's markets assume the
    format Sofascore then records.)"""

    three_set: dict[int, int] = field(default_factory=dict)
    match_tb: dict[int, int] = field(default_factory=dict)

    def decider_is_tiebreak(self, tournament: int | None) -> bool:
        if tournament is None:
            return False
        n = self.three_set.get(tournament, 0)
        return n >= 3 and self.match_tb.get(tournament, 0) * 2 > n

    def update(self, m: PointMatch) -> None:
        if m.tournament is None or not m.completed or len(m.sets) != 3:
            return
        self.three_set[m.tournament] = self.three_set.get(m.tournament, 0) + 1
        if m.match_tiebreak_decider:
            self.match_tb[m.tournament] = self.match_tb.get(m.tournament, 0) + 1


@dataclass(frozen=True)
class SideForecast:
    serve_logit: float  # logit P(win a point on own serve)
    serve_var: float  # rating uncertainty of that logit
    ace_rate: float  # aces per own serve point
    df_rate: float  # double faults per own serve point
    serve_points_seen: float  # serve points the rating has seen for him


@dataclass(frozen=True)
class MatchForecast:
    home: SideForecast
    away: SideForecast
    decider_tiebreak: bool


@dataclass
class PointModel:
    """The three online ratings and the decider book, fed in time order."""

    serve: LogitRating = field(
        default_factory=lambda: LogitRating(SERVE_PARAMS, returner_sign=-1.0))
    aces: LogitRating = field(
        default_factory=lambda: LogitRating(ACE_PARAMS, returner_sign=1.0))
    dfs: LogitRating = field(
        default_factory=lambda: LogitRating(DF_PARAMS, returner_sign=1.0))
    deciders: DeciderBook = field(default_factory=DeciderBook)

    def forecast(self, m: PointMatch) -> MatchForecast:
        cell = cell_of(m)
        sides = []
        for server, returner in ((m.home_id, m.away_id), (m.away_id, m.home_id)):
            mu, var = self.serve.predict(server, returner, cell, m.tournament, m.ts)
            a_mu, _ = self.aces.predict(server, returner, cell, m.tournament, m.ts)
            d_mu, _ = self.dfs.predict(server, returner, cell, m.tournament, m.ts)
            sides.append(SideForecast(
                serve_logit=mu, serve_var=var, ace_rate=_sigmoid(a_mu),
                df_rate=_sigmoid(d_mu),
                serve_points_seen=self.serve.trials.get(server, 0.0)))
        return MatchForecast(sides[0], sides[1],
                             self.deciders.decider_is_tiebreak(m.tournament))

    score_weight: float = SCORE_WEIGHT

    def update(self, m: PointMatch) -> None:
        """Learn from one finished match (after its forecast). Only a
        completed match teaches the ratings: from its serve counts, or -
        when the cache has none (most ITF matches) - from its score alone
        (``score_update``)."""
        self.deciders.update(m)
        if not m.completed:
            return
        if m.home is None or m.away is None:
            self.score_update(m)
            return
        cell = cell_of(m)
        for side, server, returner in ((m.home, m.home_id, m.away_id),
                                       (m.away, m.away_id, m.home_id)):
            self.serve.update(server, returner, cell, m.tournament, m.ts,
                              side.won, side.played)
            if side.aces is not None:
                self.aces.update(server, returner, cell, m.tournament, m.ts,
                                 side.aces, side.played)
            if side.dfs is not None:
                self.dfs.update(server, returner, cell, m.tournament, m.ts,
                                side.dfs, side.played)

    def score_update(self, m: PointMatch) -> None:
        _score_update(self, m)


# --------------------------------------------------------------------------
# Exact pieces (the simulator is tested against them)
# --------------------------------------------------------------------------


def hold_probability(p: float) -> float:
    """P(the server wins a game) when he wins each point with p."""
    q = 1.0 - p
    deuce = p * p / (1.0 - 2.0 * p * q) if 2.0 * p * q < 1.0 else 0.5
    return p ** 4 * (1.0 + 4.0 * q + 10.0 * q * q) + 20.0 * p ** 3 * q ** 3 * deuce


def tiebreak_probability(pa: float, pb: float, target: int = 7) -> float:
    """P(A wins a tiebreak to ``target`` (two clear) that A starts serving;
    pa / pb = each player's serve-point win probability."""
    memo: dict[tuple[int, int], float] = {}

    def a_serves(k: int) -> bool:
        # Point k (0-based): A serves 0, B 1-2, A 3-4, ...
        return ((k + 1) // 2) % 2 == 0

    def win(a: int, b: int) -> float:
        if a >= target and a - b >= 2:
            return 1.0
        if b >= target and b - a >= 2:
            return 0.0
        if a == b and a >= target - 1:
            # Two points from deuce: one served by each player.
            x = pa * (1.0 - pb)  # A wins both
            y = (1.0 - pa) * pb  # B wins both
            return x / (x + y) if x + y > 0 else 0.5
        key = (a, b)
        if key not in memo:
            k = a + b
            p = pa if a_serves(k) else 1.0 - pb
            memo[key] = p * win(a + 1, b) + (1.0 - p) * win(a, b + 1)
        return memo[key]

    return win(0, 0)


def set_win_probability(pa: float, pb: float) -> float:
    """P(A wins a set that A starts serving, tiebreak at 6-6)."""
    ha, hb = hold_probability(pa), hold_probability(pb)
    memo: dict[tuple[int, int], float] = {}

    def win(a: int, b: int) -> float:
        if (a >= 6 and a - b >= 2) or a == 7:
            return 1.0
        if (b >= 6 and b - a >= 2) or b == 7:
            return 0.0
        if a == 6 and b == 6:
            return tiebreak_probability(pa, pb)
        key = (a, b)
        if key not in memo:
            a_serving = (a + b) % 2 == 0
            p = ha if a_serving else 1.0 - hb
            memo[key] = p * win(a + 1, b) + (1.0 - p) * win(a, b + 1)
        return memo[key]

    return win(0, 0)


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SimResult:
    """Per simulated match: games per set per player, sets played, serve
    points per set per player, and who won."""

    games: IntArray  # [S, 3, 2] games won in set k by player 0 (home) / 1
    sets_played: IntArray  # [S]
    serve_points: IntArray  # [S, 3, 2] serve points of player i in set k
    home_won: npt.NDArray[np.bool_]  # [S]


def draw_serve_probabilities(
    f: MatchForecast, n: int, rng: np.random.Generator,
    form_var: float = FORM_VAR, form_cov: float = FORM_COV,
) -> tuple[FloatArray, FloatArray]:
    """Per simulation, each side's serve-point probability: the rating's
    belief plus match-day form (a shared dominance term moving the two
    logits apart, cov = form_cov < 0, plus an independent part)."""
    dom_var = max(0.0, -form_cov)
    ind_var = max(0.0, form_var - dom_var)
    dom = rng.normal(0.0, math.sqrt(dom_var), n) if dom_var > 0 else np.zeros(n)
    za = rng.normal(0.0, math.sqrt(ind_var + f.home.serve_var), n)
    zb = rng.normal(0.0, math.sqrt(ind_var + f.away.serve_var), n)
    la = f.home.serve_logit + za + dom
    lb = f.away.serve_logit + zb - dom
    return 1.0 / (1.0 + np.exp(-la)), 1.0 / (1.0 + np.exp(-lb))


def simulate(
    pa: FloatArray, pb: FloatArray, rng: np.random.Generator,
    decider_tiebreak: bool = False,
) -> SimResult:
    """Play len(pa) best-of-three matches point by point, vectorised.
    pa[s] / pb[s]: home's / away's serve-point win probability in sim s.
    The first server is a coin toss; the server alternates every game, the
    tiebreak counting as a game served first by the player due to serve
    (so the other one opens the next set)."""
    n = len(pa)
    idx = np.arange(n)
    games = np.zeros((n, 3, 2), dtype=np.int64)
    serve_points = np.zeros((n, 3, 2), dtype=np.int64)
    sets_won = np.zeros((n, 2), dtype=np.int64)
    set_no = np.zeros(n, dtype=np.int64)
    server = rng.integers(0, 2, n).astype(np.int64)  # who serves this game
    pts = np.zeros((n, 2), dtype=np.int64)
    in_tb = np.zeros(n, dtype=bool)
    tb_target = np.full(n, 7, dtype=np.int64)
    tb_first = np.zeros(n, dtype=np.int64)
    done = np.zeros(n, dtype=bool)
    p_serve = np.stack([pa, pb], axis=1)
    guard = 0
    while not done.all():
        guard += 1
        if guard > 2000:
            raise RuntimeError("simulation did not terminate")
        live = idx[~done]
        tb = in_tb[live]
        k = pts[live, 0] + pts[live, 1]
        tb_server = np.where(((k + 1) // 2) % 2 == 0, tb_first[live],
                             1 - tb_first[live])
        srv = np.where(tb, tb_server, server[live])
        s_set = set_no[live]
        serve_points[live, s_set, srv] += 1
        win_srv = rng.random(len(live)) < p_serve[live, srv]
        winner = np.where(win_srv, srv, 1 - srv)
        pts[live, winner] += 1
        pw = pts[live, winner]
        pl = pts[live, 1 - winner]
        target = np.where(tb, tb_target[live], 4)
        game_over = (pw >= target) & (pw - pl >= 2)
        if not game_over.any():
            continue
        g = live[game_over]
        gw = winner[game_over]
        was_tb = in_tb[g]
        pts[g] = 0
        in_tb[g] = False
        sg = set_no[g]
        games[g, sg, gw] += 1
        server[g] = np.where(was_tb, 1 - tb_first[g], 1 - server[g])
        ga = games[g, sg, 0]
        gb = games[g, sg, 1]
        hi = np.maximum(ga, gb)
        lo = np.minimum(ga, gb)
        set_over = was_tb | ((hi >= 6) & (hi - lo >= 2)) | (hi == 7)
        to_tb = (~set_over) & (ga == 6) & (gb == 6)
        if to_tb.any():
            t = g[to_tb]
            in_tb[t] = True
            tb_target[t] = 7
            tb_first[t] = server[t]
        if set_over.any():
            e = g[set_over]
            ew = np.where(games[e, set_no[e], 0] > games[e, set_no[e], 1], 0, 1)
            sets_won[e, ew] += 1
            fin = sets_won[e].max(axis=1) >= 2
            done[e[fin]] = True
            nxt = e[~fin]
            set_no[nxt] += 1
            if decider_tiebreak and len(nxt):
                # A 10-point match tiebreak as the deciding "set" - only at
                # one set all (set_no is now 2), never as the second set.
                dec = nxt[set_no[nxt] == 2]
                in_tb[dec] = True
                tb_target[dec] = 10
                tb_first[dec] = server[dec]
    return SimResult(
        games=games, sets_played=set_no + 1, serve_points=serve_points,
        home_won=sets_won[:, 0] > sets_won[:, 1])


def nb_sf(line: float, mean: FloatArray, shape: float) -> FloatArray:
    """P(X > line) per element, X ~ NegBin(mean, shape) (variance mean +
    mean^2 / shape); shape = inf is Poisson."""
    m = int(math.floor(line))
    mean = np.maximum(mean, 1e-9)
    if math.isinf(shape):
        pmf = np.exp(-mean)
        cdf = pmf.copy()
        for x in range(m):
            pmf = pmf * mean / (x + 1)
            cdf = cdf + pmf
    else:
        q = mean / (shape + mean)
        pmf = np.power(shape / (shape + mean), shape)
        cdf = pmf.copy()
        for x in range(m):
            pmf = pmf * (x + shape) / (x + 1) * q
            cdf = cdf + pmf
    return np.clip(1.0 - cdf, 0.0, 1.0)


def sum_shape(mean_a: FloatArray, mean_b: FloatArray, shape: float) -> FloatArray:
    """Moment-matched NB shape of the sum of two independent NB counts."""
    extra = (mean_a ** 2 + mean_b ** 2) / shape
    return np.asarray(((mean_a + mean_b) ** 2) / np.maximum(extra, 1e-12),
                      dtype=np.float64)


def _nb_sf_shapes(line: float, mean: FloatArray, shapes: FloatArray) -> FloatArray:
    m = int(math.floor(line))
    mean = np.maximum(mean, 1e-9)
    q = mean / (shapes + mean)
    pmf = np.power(shapes / (shapes + mean), shapes)
    cdf = pmf.copy()
    for x in range(m):
        pmf = pmf * (x + shapes) / (x + 1) * q
        cdf = cdf + pmf
    return np.clip(1.0 - cdf, 0.0, 1.0)


@dataclass(frozen=True)
class MarketSim:
    """A forecast turned into simulated matches; every market is read here."""

    forecast: MatchForecast
    sim: SimResult

    # ---- score markets -------------------------------------------------
    def total_games(self) -> IntArray:
        return np.asarray(self.sim.games.sum(axis=(1, 2)), dtype=np.int64)

    def p_over(self, market: str, side: int | None, line: float) -> float | None:
        """P(value > line) of a pipeline market; side 0 home / 1 away for a
        per-player market (``*_for``). None = a market this model does not
        read. Per-set serve and set-3 markets are conditional on the set
        being played (Superbet voids it otherwise)."""
        sim = self.sim
        if market == "games_total":
            return float((self.total_games() > line).mean())
        if market == "sets_total":
            return float((sim.sets_played > line).mean())
        if market in ("games_set1_total", "games_set2_total"):
            k = 0 if market.endswith("set1_total") else 1
            played = sim.sets_played > k
            v = sim.games[:, k, :].sum(axis=1)
            return _cond_mean(v > line, played)
        if market == "games_won_for" and side is not None:
            return float((sim.games[:, :, side].sum(axis=1) > line).mean())
        parsed = _serve_market(market)
        if parsed is None:
            return None
        stat, scope, per_player = parsed
        if per_player and side is None:
            return None
        if scope == 0:
            sp = sim.serve_points.sum(axis=1).astype(np.float64)  # [S, 2]
            mask = np.ones(len(sp), dtype=bool)
            shape_a, shape_d = NB_SHAPE["aces"], NB_SHAPE["dfs"]
        else:
            sp = sim.serve_points[:, scope - 1, :].astype(np.float64)
            mask = sim.sets_played >= scope
            shape_a, shape_d = NB_SHAPE["aces_set"], NB_SHAPE["dfs_set"]
        f = self.forecast
        rates_a = np.array([f.home.ace_rate, f.away.ace_rate])
        rates_d = np.array([f.home.df_rate, f.away.df_rate])
        mean_a = sp * rates_a  # [S, 2]
        mean_d = sp * rates_d
        players = [side] if per_player and side is not None else [0, 1]
        if stat == "aces":
            ma = mean_a[:, players].sum(axis=1)
            if len(players) == 1:
                return _cond_mean(nb_sf(line, ma, shape_a), mask)
            shapes = sum_shape(mean_a[:, 0], mean_a[:, 1], shape_a)
            return _cond_mean(_nb_sf_shapes(line, ma, shapes), mask)
        if stat == "dfs":
            md = mean_d[:, players].sum(axis=1)
            if len(players) == 1:
                return _cond_mean(nb_sf(line, md, shape_d), mask)
            shapes = sum_shape(mean_d[:, 0], mean_d[:, 1], shape_d)
            return _cond_mean(_nb_sf_shapes(line, md, shapes), mask)
        # aces + double faults: one NB moment-matched to the sum.
        means = [mean_a[:, i] for i in players] + [mean_d[:, i] for i in players]
        shp = [shape_a] * len(players) + [shape_d] * len(players)
        total = np.sum(means, axis=0)
        extra = np.sum([m ** 2 / s for m, s in zip(means, shp, strict=True)], axis=0)
        shapes = np.asarray(total ** 2 / np.maximum(extra, 1e-12), dtype=np.float64)
        return _cond_mean(_nb_sf_shapes(line, total, shapes), mask)


def _cond_mean(values: npt.NDArray[Any], mask: npt.NDArray[np.bool_]) -> float | None:
    if not mask.any():
        return None
    return float(np.asarray(values, dtype=np.float64)[mask].mean())


_SERVE_MARKET = re.compile(
    r"^(aces|double_faults|serve_points)(?:_set([12]))?_(for|total)$")


def _serve_market(market: str) -> tuple[str, int, bool] | None:
    """market -> (stat 'aces' / 'dfs' / 'both', set 0 = match, per player)."""
    m = _SERVE_MARKET.match(market)
    if m is None:
        return None
    stat = {"aces": "aces", "double_faults": "dfs", "serve_points": "both"}[m.group(1)]
    return stat, int(m.group(2) or 0), m.group(3) == "for"


SERVE_MARKETS = frozenset(
    f"{s}{scope}_{x}" for s in ("aces", "double_faults", "serve_points")
    for scope in ("", "_set1", "_set2") for x in ("for", "total"))
SCORE_MARKETS = frozenset({"games_total", "sets_total", "games_set1_total",
                           "games_set2_total", "games_won_for"})
MARKETS = SERVE_MARKETS | SCORE_MARKETS


def market_sim(f: MatchForecast, n: int = 4000, seed: int = 0) -> MarketSim:
    """Simulate ``n`` matches of one forecast (seeded: reproducible)."""
    rng = np.random.default_rng(seed)
    pa, pb = draw_serve_probabilities(f, n, rng)
    return MarketSim(f, simulate(pa, pb, rng, f.decider_tiebreak))


def walk_forward(
    matches: Sequence[PointMatch],
    wanted: Iterable[int],
    model: PointModel | None = None,
) -> dict[int, MatchForecast]:
    """Forecast every wanted match from the state before its start, feeding
    the history in time order (matches starting at the same second are all
    forecast before any of them teaches the ratings)."""
    model = model or PointModel()
    want = set(wanted)
    out: dict[int, MatchForecast] = {}
    i = 0
    while i < len(matches):
        j = i
        while j < len(matches) and matches[j].ts == matches[i].ts:
            j += 1
        for m in matches[i:j]:
            if m.event_id in want:
                out[m.event_id] = model.forecast(m)
        for m in matches[i:j]:
            model.update(m)
        i = j
    return out


def _games_share(eta_a: float, eta_b: float, x: float) -> float:
    """Expected share of games won by A when A's serve logit moves by +x and
    B's by -x (each serves about half the games)."""
    return 0.5 * (hold_probability(_sigmoid(eta_a + x))
                  + 1.0 - hold_probability(_sigmoid(eta_b - x)))


def score_shift(eta_a: float, eta_b: float, share: float) -> float:
    """The logit shift x that makes the expected games share equal the
    observed one (bisection; the share is monotone in x)."""
    share = min(max(share, 0.05), 0.95)
    lo, hi = -4.0, 4.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        if _games_share(eta_a, eta_b, mid) < share:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _score_update(model: PointModel, m: PointMatch) -> None:
    if model.score_weight <= 0:
        return
    ga = sum(a for a, _ in m.sets)
    gb = sum(b for _, b in m.sets)
    if ga + gb <= 0:
        return
    cell = cell_of(m)
    eta_a, _ = model.serve.predict(m.home_id, m.away_id, cell, m.tournament, m.ts)
    eta_b, _ = model.serve.predict(m.away_id, m.home_id, cell, m.tournament, m.ts)
    x = score_shift(eta_a, eta_b, ga / (ga + gb))
    n = model.score_weight * POINTS_PER_GAME_PER_SIDE * (ga + gb)
    model.serve.update(m.home_id, m.away_id, cell, m.tournament, m.ts,
                       n * _sigmoid(eta_a + x), n, real=False)
    model.serve.update(m.away_id, m.home_id, cell, m.tournament, m.ts,
                       n * _sigmoid(eta_b - x), n, real=False)
