"""CS2 engine: a model probability for each CS2 line, from pre-match history.

The measurement's second half. CS2_SETTLE grades Superbet's price; this puts
a number of our own beside it, computed only from the cs2_* history that
existed before the series started, so the audit can ask the question every
sofa sport has to answer before it may reach a coupon: does the history beat
the devigged price, or only add noise to it? (In football it does not; see
the memory note sofa-model-loses-to-the-price.)

Leakage is the failure mode that would make the answer worthless, so it is
closed twice: history is cut at the EARLIER of Superbet's kickoff and
Sofascore's start (Sofascore routinely lists a series minutes before
Superbet's time), and the series being graded is excluded by id as well.

Models, by family (anything else returns None - never a guessed number):

- map_winner, match_winner: a map-level Elo (K = ELO_K), calibrated by a
  logistic fit with a home term on its own walk-forward predictions
  (RatingModel); the series from p(map) held constant, exact for best-of-
  1/2/3/5. Beats a constant only barely (match_winner 0.2423 vs 0.2462).
- maps_total, maps_handicap, team_maps: NO number - the constant-p series
  overpredicts three-map series (see ELO_FAMILIES).
- player_kills / _deaths / _assists / _headshots, team_kills: the player's
  (team's) last MAX_SAMPLE maps; a negative binomial (`engine.nb_survival`)
  when the predictive variance exceeds the mean, a continuity-corrected normal
  when it does not.
- map_rounds_total: the history's own base rate at the line - the teams'
  samples carried nothing about the next map's length.
- map_team_rounds: the team's frequency above the line, shrunk toward the
  base rate with K_ROUNDS pseudo-maps (beat a constant: 0.2380 vs 0.2417).
  Round totals are bounded and lumpy (13-x, then 16-14 / 19-17 in overtime).

An integer line's push is voided by grade(), so every family reports
P(side | no push). Every probability is clamped to engine's
[P_FLOOR, P_CEILING]. The constants in UNFITTED are chosen, not fitted, and
are reported as such beside every number they produce.

Measured on the stored history at review (2026-09-28, 2,084 series): raw Elo
per-map Brier 0.2446 (0.25 is a coin), favourites 7-10 pp overrated - which
the calibration exists to take out; kills near the player's own mean
calibrated but nearly uninformative (Brier 0.2485). The model is expected to
lose to the price; the audit is where that is measured, not assumed.
"""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict, deque
from dataclasses import dataclass, field
from functools import cache, lru_cache
from typing import Any

from bet.sofa.comparability import is_non_competitive_name
from bet.sofa.cs2 import Cs2Line, esports_name, exact_score
from bet.sofa.engine import (
    P_CEILING,
    P_FLOOR,
    nb_survival,
    normal_cdf,
    predictive_sd,
)

ELO_START = 1500.0
ELO_K = 24.0
MIN_MAPS_RATED = 10  # both teams, before a winner-family number is given
MIN_SAMPLE = 8  # maps, for a count or round model
MAX_SAMPLE = 20  # most recent maps used for counts and rounds
MIN_FIT = 200  # walk-forward predictions (or maps) before a fit or base rate
K_ROUNDS = 20  # pseudo-maps of base rate behind a team's rounds frequency
MIN_VAR_RATIO = 0.5  # floor on predictive variance / mean for the normal branch
LOOKBACK_DAYS = 365
UNFITTED = (
    "ELO_K",
    "ELO_START",
    "MIN_MAPS_RATED",
    "MIN_SAMPLE",
    "MAX_SAMPLE",
    "MIN_FIT",
    "K_ROUNDS",
    "MIN_VAR_RATIO",
)

# Only the winner families. maps_total, team_maps and maps_handicap were
# modelled from the same p held constant through the series, and on the stored
# history that overpredicted a three-map series (0.482 against 0.424 on 876
# best-of-threes, 0.376 against 0.222 in the 0.3 band) - real series are more
# lopsided than any constant p allows, and the per-map calibration pushed it
# further the wrong way. Losing to a constant (0.2479 vs 0.2442) is a guess,
# not a model, so those families get no number until a series-level term
# earns one (review 2026-09-28, round 2).
ELO_FAMILIES = {"map_winner", "match_winner"}
# The series families come back with a series-level term (operator,
# 2026-10-07): the maps of one series are correlated (the day's form), so the
# series' own p is drawn from Beta(p * K, (1 - p) * K) around the map p and
# the maps are independent given it (series_distribution_mixed). Walk-forward
# on the stored history (60 days' warm-up, 8,065 best-of-threes, the last 40%
# held out, 3,226 series): Brier of "three maps" 0.2427 against the constant
# 0.2436 (-0.0009 [-0.0020, +0.0001]) and the independent maps 0.2453
# (-0.0026 [-0.0048, -0.0002]); the exact-score log loss 1.3154 against
# 1.3220. K fitted on the first 60% (grid 1..1e4, best 6). They print only
# through their curves and settled lines (bet.sofa.line_evidence).
SERIES_FAMILIES = {"maps_total", "maps_handicap", "team_maps", "exact_maps"}
SERIES_KAPPA = 6.0
COUNT_FAMILIES = {
    "player_kills",
    "player_deaths",
    "player_assists",
    "player_headshots",
    "team_kills",
}
ROUND_FAMILIES = {"map_rounds_total", "map_team_rounds", "map_rounds_handicap"}
MODELLED = ELO_FAMILIES | COUNT_FAMILIES | ROUND_FAMILIES | SERIES_FAMILIES


def clamp(p: float) -> float:
    return max(P_FLOOR, min(P_CEILING, p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


# --- the series -------------------------------------------------------------------


@cache
def series_distribution(p_map: float, best_of: int) -> dict[tuple[int, int], float]:
    """Exact final-score distribution of a best-of-n with constant p per map.

    Keys are (team1 maps, team2 maps). Best-of-2 is not a race: both maps are
    played and 1-1 is a result. Anything else must be odd.
    """
    if not 0.0 <= p_map <= 1.0:
        raise ValueError(f"p_map {p_map} outside [0, 1]")
    q = 1.0 - p_map
    if best_of == 2:
        return {(2, 0): p_map * p_map, (1, 1): 2 * p_map * q, (0, 2): q * q}
    if best_of < 1 or best_of % 2 == 0:
        raise ValueError(f"best_of {best_of} is not 1, 2, 3 or 5")
    need = best_of // 2 + 1
    out: dict[tuple[int, int], float] = {}
    for losses in range(need):
        # The winner takes the last map: C(need - 1 + losses, losses) orders.
        orders = math.comb(need - 1 + losses, losses)
        out[(need, losses)] = orders * p_map**need * q**losses
        out[(losses, need)] = orders * q**need * p_map**losses
    return out


def _beta_moment(alpha: float, beta: float, a: int, b: int) -> float:
    """E[q^a (1-q)^b] for q ~ Beta(alpha, beta)."""
    return math.exp(math.lgamma(alpha + a) + math.lgamma(beta + b)
                    - math.lgamma(alpha + beta + a + b) + math.lgamma(alpha + beta)
                    - math.lgamma(alpha) - math.lgamma(beta))


def series_distribution_mixed(p_map: float, best_of: int,
                              kappa: float = SERIES_KAPPA
                              ) -> dict[tuple[int, int], float]:
    """series_distribution with the series' own p ~ Beta(p K, (1 - p) K): the
    same keys, each probability the Beta mixture of the constant-p one."""
    if not 0.0 < p_map < 1.0:
        raise ValueError(f"p_map {p_map} outside (0, 1)")
    alpha, beta = p_map * kappa, (1.0 - p_map) * kappa
    if best_of == 2:
        return {(2, 0): _beta_moment(alpha, beta, 2, 0),
                (1, 1): 2 * _beta_moment(alpha, beta, 1, 1),
                (0, 2): _beta_moment(alpha, beta, 0, 2)}
    if best_of < 1 or best_of % 2 == 0:
        raise ValueError(f"best_of {best_of} is not 1, 2, 3 or 5")
    need = best_of // 2 + 1
    out: dict[tuple[int, int], float] = {}
    for losses in range(need):
        orders = math.comb(need - 1 + losses, losses)
        out[(need, losses)] = orders * _beta_moment(alpha, beta, need, losses)
        out[(losses, need)] = orders * _beta_moment(alpha, beta, losses, need)
    return out


def series_side_p(dist: dict[tuple[int, int], float], family: str,
                  line: float | None, side: str, team_idx: int | None
                  ) -> float | None:
    """One side of a series family from a final-score distribution (team1
    first), given that it does not push; None when it cannot be told."""
    if family == "exact_maps":
        score = exact_score(side)
        return None if score is None else dist.get(score, 0.0)
    if family == "maps_handicap":
        hcp = line or 0.0
        p_t1 = sum(q for (a, b), q in dist.items() if a - b + hcp > 0)
        p_t2 = sum(q for (a, b), q in dist.items() if a - b + hcp < 0)
        return side_given_no_push(p_t1, p_t2, side == "T1")
    if line is None or side not in ("OVER", "UNDER"):
        return None
    if family == "maps_total":
        count = {sc: sc[0] + sc[1] for sc in dist}
    elif family == "team_maps" and team_idx in (0, 1):
        count = {sc: sc[team_idx] for sc in dist}
    else:
        return None
    p_over = sum(q for sc, q in dist.items() if count[sc] > line)
    p_under = sum(q for sc, q in dist.items() if count[sc] < line)
    return side_given_no_push(p_over, p_under, side == "OVER")


# --- ratings ----------------------------------------------------------------------


def elo_expected(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + math.pow(10.0, (r_b - r_a) / 400.0))


@dataclass
class EloBook:
    """Raw map-level Elo, replayed in time order."""

    ratings: dict[int, float] = field(default_factory=dict)
    played: dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def rating(self, team: int) -> float:
        return self.ratings.get(team, ELO_START)

    def rated(self, *teams: int) -> bool:
        return all(self.played[t] >= MIN_MAPS_RATED for t in teams)

    def update(self, winner: int, loser: int) -> None:
        r_w, r_l = self.rating(winner), self.rating(loser)
        delta = ELO_K * (1.0 - elo_expected(r_w, r_l))
        self.ratings[winner] = r_w + delta
        self.ratings[loser] = r_l - delta
        self.played[winner] += 1
        self.played[loser] += 1


def logit_diff(book: EloBook, home: int, away: int) -> float:
    """The rating gap on the logit scale: raw Elo is exactly sigmoid of it."""
    return (book.rating(home) - book.rating(away)) * math.log(10.0) / 400.0


def fit_logistic(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """(a, b) of P(y = 1) = sigmoid(a + b x), by Newton's method, ridged
    lightly toward raw Elo (a = 0, b = 1) so a short history cannot run away."""
    a, b, ridge = 0.0, 1.0, 1.0
    for _ in range(50):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys, strict=True):
            p = _sigmoid(a + b * x)
            w = p * (1.0 - p)
            ga += p - y
            gb += (p - y) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        ga += ridge * a
        gb += ridge * (b - 1.0)
        haa += ridge
        hbb += ridge
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da = (hbb * ga - hab * gb) / det
        db = (haa * gb - hab * ga) / det
        a, b = a - da, b - db
        if abs(da) + abs(db) < 1e-10:
            break
    return a, b


# A team is its players. A player-level Elo (each player moved by K x the map
# result's surprise, the expectation from the two lineups' mean ratings)
# predicts a series from the lineup each team fielded last. Measured
# 2026-10-01 on the backfilled history (16,586 series), each series from the
# ratings at its start, calibration fitted on the first 70%: held out 6,588
# maps, team Elo 0.2382, player Elo 0.2368; paired bootstrap over 2,897
# series -0.00148 [-0.00268, -0.00025]. Roster churn is the variable a
# team-name Elo cannot see.
MIN_LINEUP = 4  # players of a team on a map, for the lineup to count
MIN_PLAYER_MAPS = 3  # maps every player of both lineups has been rated on


@dataclass
class PlayerEloBook:
    ratings: dict[int, float] = field(default_factory=dict)
    played: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    lineup: dict[int, tuple[int, ...]] = field(default_factory=dict)

    def mean(self, players: tuple[int, ...]) -> float:
        return sum(self.ratings.get(p, ELO_START) for p in players) / len(players)

    def gap(self, home: int, away: int) -> float | None:
        """The last lineups' mean-rating gap in logits, or None."""
        lh, la = self.lineup.get(home), self.lineup.get(away)
        if not lh or not la:
            return None
        if min(self.played[p] for p in lh + la) < MIN_PLAYER_MAPS:
            return None
        return (self.mean(lh) - self.mean(la)) * math.log(10.0) / 400.0

    def update(self, m: MapRow) -> None:
        ph = tuple(pid for t, pid, _, _ in m.players if t == m.home_id)
        pa = tuple(pid for t, pid, _, _ in m.players if t == m.away_id)
        if len(ph) < MIN_LINEUP or len(pa) < MIN_LINEUP:
            return
        expected = elo_expected(self.mean(ph), self.mean(pa))
        surprise = (1.0 if m.home_won else 0.0) - expected
        for pid in ph:
            self.ratings[pid] = self.ratings.get(pid, ELO_START) + ELO_K * surprise
            self.played[pid] += 1
        for pid in pa:
            self.ratings[pid] = self.ratings.get(pid, ELO_START) - ELO_K * surprise
            self.played[pid] += 1
        self.lineup[m.home_id] = ph
        self.lineup[m.away_id] = pa


@dataclass
class RatingModel:
    """Map-level Elo, calibrated on its own pre-match history.

    Raw Elo overrated favourites on the stored history (predicted 0.743 for
    maps that went 0.673) and knew nothing of Sofascore's home side, which
    wins 54.0% of 3,591 maps. So P(home wins the map) = sigmoid(a + b d), d
    the rating gap in logits, with (a, b) fitted on walk-forward predictions -
    each series predicted from the ratings frozen at its start, as production
    uses them - and only on maps before the cut. Under MIN_FIT predictions it
    stays raw Elo (a = 0, b = 1).
    """

    book: EloBook
    a: float = 0.0
    b: float = 1.0
    n_fit: int = 0
    players: PlayerEloBook | None = None
    # the player model's own calibration; used only when it was fitted
    pa: float = 0.0
    pb: float = 1.0
    p_fit: int = 0
    # audit B11 (epochs.CS2_MAP_IDENTITY): terms on the home logit, fitted
    # with the base calibration as the offset (fit_map_terms); zero = off
    order_delta: dict[str, float] = field(default_factory=dict)
    pool_c: float = 0.0
    pool: MapPoolBook | None = None
    map_fit: int = 0

    def base_logit(self, d: float, g: float | None) -> float:
        """The calibrated home logit from the team gap d and the lineup gap
        g, as p_map reads them."""
        if g is not None and self.p_fit >= MIN_FIT:
            return self.pa + self.pb * g
        return self.a + self.b * d

    def home_logit(self, home: int, away: int) -> float | None:
        if not self.book.rated(home, away):
            return None
        gap = self.players.gap(home, away) if self.players is not None else None
        return self.base_logit(logit_diff(self.book, home, away), gap)

    def p_map(self, team1: int, team2: int, team1_is_home: bool) -> float | None:
        home, away = (team1, team2) if team1_is_home else (team2, team1)
        z = self.home_logit(home, away)
        if z is None:
            return None
        p_home = _sigmoid(z)
        return p_home if team1_is_home else 1.0 - p_home

    def p_map_nr(self, team1: int, team2: int, team1_is_home: bool,
                 best_of: int | None, map_nr: int) -> float | None:
        """p_map for map `map_nr` of the series (audit B11): the base logit
        plus the (format, map number) term and the pool term. Equal to p_map
        when the terms were not fitted (build_ratings without map_terms)."""
        home, away = (team1, team2) if team1_is_home else (team2, team1)
        z = self.home_logit(home, away)
        if z is None:
            return None
        z += self.order_delta.get(map_order_key(best_of, map_nr), 0.0)
        if self.pool is not None and self.pool_c:
            z += self.pool_c * self.pool.delta(home, away)
        p_home = _sigmoid(z)
        return p_home if team1_is_home else 1.0 - p_home


# --- audit B11: the map's number and the teams' map pools --------------------------

# What is known before a CS2 series: the map's number on the line, the format
# and the teams' past maps. The map itself is chosen in the veto minutes
# before the start (Superbet's line names only the number; Sofascore names the
# map afterwards), the starting side after it - so a per-map rating enters only
# as a mixture over the two teams' recent map pools.
K_MAP = 16.0  # Elo points a map result moves a team's deviation on that map
POOL_MAPS = 30  # a team's recent maps that make up its pool
POOL_ALPHA = 0.5  # pseudo-count of a pool map the other team has not played
UNFITTED_MAP = ("K_MAP", "POOL_MAPS", "POOL_ALPHA")
MAP_ORDER_KEYS = ("bo1", "bo3m1", "bo3m2", "bo3m3", "other")
MAP_TERMS: tuple[str, ...] = ("order", "pool")  # what the switch fits


def map_order_key(best_of: int | None, map_nr: int) -> str:
    """The (format, map number) cell of the order term."""
    if best_of == 1:
        return "bo1"
    if best_of == 3 and 1 <= map_nr <= 3:
        return f"bo3m{map_nr}"
    return "other"


@dataclass
class MapPoolBook:
    """Each team's Elo deviation per map (from the team's own Elo plus the
    deviations, moved by K_MAP x the surprise) and its last POOL_MAPS map
    names."""

    dev: dict[tuple[int, str], float] = field(default_factory=dict)
    recent: dict[int, deque[str]] = field(default_factory=dict)

    def known(self, home: int, away: int, name: str) -> float:
        """The deviation gap on map `name`, in logits (diagnostic oracle)."""
        return ((self.dev.get((home, name), 0.0) - self.dev.get((away, name), 0.0))
                * math.log(10.0) / 400.0)

    def delta(self, home: int, away: int) -> float:
        """The deviation gap mixed over the two pools: weight of map M
        (n_home(M) + POOL_ALPHA) x (n_away(M) + POOL_ALPHA) over every map
        either team played in its last POOL_MAPS maps."""
        nh: dict[str, int] = defaultdict(int)
        na: dict[str, int] = defaultdict(int)
        for n in self.recent.get(home, ()):
            nh[n] += 1
        for n in self.recent.get(away, ()):
            na[n] += 1
        names = set(nh) | set(na)
        if not names:
            return 0.0
        tot = acc = 0.0
        for n in sorted(names):
            w = (nh[n] + POOL_ALPHA) * (na[n] + POOL_ALPHA)
            tot += w
            acc += w * self.known(home, away, n)
        return acc / tot

    def update(self, m: MapRow, book: EloBook) -> None:
        """Before book.update for the same map."""
        if not m.map_name:
            return
        name = m.map_name
        dh = self.dev.get((m.home_id, name), 0.0)
        da = self.dev.get((m.away_id, name), 0.0)
        exp = elo_expected(book.rating(m.home_id) + dh, book.rating(m.away_id) + da)
        s = (1.0 if m.home_won else 0.0) - exp
        self.dev[(m.home_id, name)] = dh + K_MAP * s
        self.dev[(m.away_id, name)] = da - K_MAP * s
        for team in (m.home_id, m.away_id):
            self.recent.setdefault(team, deque(maxlen=POOL_MAPS)).append(name)


@dataclass(frozen=True)
class MapPoint:
    """One map predicted at its series' start: team gap d, lineup gap g,
    order cell, pool term, oracle term (None without a map name), outcome."""

    d: float
    g: float | None
    key: str
    pool: float
    known: float | None
    y: float


def series_map_points(maps: list[MapRow], book: EloBook, players: PlayerEloBook,
                      pool: MapPoolBook) -> list[MapPoint]:
    """The MapPoints of one series from the books at its start (both teams
    rated), before any of its maps is played into them."""
    home, away = maps[0].home_id, maps[0].away_id
    if not book.rated(home, away):
        return []
    d = logit_diff(book, home, away)
    g = players.gap(home, away)
    dl = pool.delta(home, away)
    return [MapPoint(d, g, map_order_key(m.best_of, m.order), dl,
                     pool.known(home, away, m.map_name) if m.map_name else None,
                     1.0 if m.home_won else 0.0) for m in maps]


def _solve(a: list[list[float]], b: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None when singular."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            return None
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def fit_offsets(rows: list[tuple[float, list[float], float]], k: int,
                ridge: float = 1.0) -> list[float]:
    """beta of P(y = 1) = sigmoid(z + beta . x), z a fixed offset, by Newton,
    ridged toward 0."""
    beta = [0.0] * k
    for _ in range(30):
        grad = [ridge * bj for bj in beta]
        hess = [[ridge if i == j else 0.0 for j in range(k)] for i in range(k)]
        for z, x, y in rows:
            p = _sigmoid(z + sum(bj * xj for bj, xj in zip(beta, x, strict=True)))
            w = p * (1.0 - p)
            nz = [i for i in range(k) if x[i] != 0.0]
            for i in nz:
                grad[i] += (p - y) * x[i]
                for j in nz:
                    hess[i][j] += w * x[i] * x[j]
        step = _solve(hess, grad)
        if step is None:
            break
        beta = [bj - sj for bj, sj in zip(beta, step, strict=True)]
        if sum(abs(sj) for sj in step) < 1e-9:
            break
    return beta


def map_term_features(pt: MapPoint, terms: tuple[str, ...],
                      known: bool = False) -> list[float]:
    """The order one-hot and / or the pool term of a point (`known`: the
    actual map's term instead, the diagnostic oracle)."""
    x: list[float] = []
    if "order" in terms:
        x += [1.0 if pt.key == k else 0.0 for k in MAP_ORDER_KEYS]
    if "pool" in terms:
        x.append(pt.known if known and pt.known is not None else pt.pool)
    return x


def fit_map_terms(model: RatingModel, points: list[MapPoint],
                  terms: tuple[str, ...], pool: MapPoolBook | None) -> None:
    """Fit the order / pool terms on `points` with the model's base
    calibration as the offset; under MIN_FIT points they stay zero."""
    model.pool = pool
    if not terms or len(points) < MIN_FIT:
        return
    rows = [(model.base_logit(pt.d, pt.g), map_term_features(pt, terms), pt.y)
            for pt in points]
    beta = fit_offsets(rows, len(rows[0][1]))
    i = 0
    if "order" in terms:
        model.order_delta = dict(zip(MAP_ORDER_KEYS, beta[:len(MAP_ORDER_KEYS)],
                                     strict=True))
        i = len(MAP_ORDER_KEYS)
    if "pool" in terms:
        model.pool_c = beta[i]
    model.map_fit = len(points)


# --- the history ------------------------------------------------------------------


StatRow = tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class MapRow:
    event_id: int
    start_ts: int
    order: int
    home_id: int
    away_id: int
    home_rounds: int | None  # None when Sofascore has the winner but no rounds
    away_rounds: int | None
    home_won: bool
    # (team id, player id, folded name, stat -> value)
    players: tuple[tuple[int, int, str, StatRow], ...]
    map_name: str | None = None  # Sofascore's, after the veto (audit B11)
    best_of: int | None = None  # the series' format (audit B11)


def load_history(
    conn: sqlite3.Connection, before_ts: int, exclude_event: int | None
) -> list[MapRow]:
    """Every finished map of a finished series that started before `before_ts`
    (and within LOOKBACK_DAYS), oldest first. `exclude_event` is dropped even
    if its start is earlier - it is the series being graded.

    A map with a winner but no rounds - 19% of the stored maps at review -
    is kept for the ratings and skipped by the rounds models.
    """
    since = before_ts - LOOKBACK_DAYS * 86400
    rows = conn.execute(
        """SELECT m.game_id, s.sofascore_event_id, s.start_ts, m.map_order,
                  s.home_id, s.away_id, m.home_rounds, m.away_rounds, m.winner_code,
                  s.tournament, m.map_name, s.best_of
           FROM cs2_map m JOIN cs2_series s USING (sofascore_event_id)
           WHERE s.status_type = 'finished' AND m.status_type = 'finished'
             AND s.start_ts < ? AND s.start_ts >= ?
             AND ((m.home_rounds IS NOT NULL AND m.away_rounds IS NOT NULL
                   AND m.home_rounds != m.away_rounds)
                  OR m.winner_code IN (1, 2))
           ORDER BY s.start_ts, s.sofascore_event_id, m.map_order""",
        (before_ts, since),
    ).fetchall()
    # A show match / exhibition is not a series the ratings may learn from
    # (comparability; none in the store when this was added, 2026-10-04).
    rows = [r[:9] + r[10:] for r in rows if not is_non_competitive_name(r[9])]
    players: dict[int, list[tuple[str, int, str, StatRow]]] = defaultdict(list)
    ids = [r[0] for r in rows]
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        marks = ",".join("?" * len(chunk))
        for gid, side, pid, name, k, d, a, h in conn.execute(
            f"SELECT game_id, side, player_id, player_name, kills, deaths, assists, "
            f"headshots FROM cs2_player_map WHERE game_id IN ({marks})",
            chunk,
        ):
            stats = tuple(
                (stat, v)
                for stat, v in (
                    ("kills", k),
                    ("deaths", d),
                    ("assists", a),
                    ("headshots", h),
                )
                if isinstance(v, int)
            )
            players[gid].append((str(side), int(pid), esports_name(str(name)), stats))
    out: list[MapRow] = []
    for gid, eid, ts, order, home_id, away_id, hr, ar, winner, name, bo in rows:
        if exclude_event is not None and eid == exclude_event:
            continue
        has_rounds = hr is not None and ar is not None and hr != ar
        home_won = bool(hr > ar) if has_rounds else winner == 1
        rows_for_map = tuple(
            (home_id if side == "home" else away_id, pid, name, stats)
            for side, pid, name, stats in players.get(gid, [])
        )
        out.append(
            MapRow(
                eid,
                ts,
                order,
                home_id,
                away_id,
                hr if has_rounds else None,
                ar if has_rounds else None,
                home_won,
                rows_for_map,
                str(name) if name else None,
                int(bo) if bo else None,
            )
        )
    return out


def walk_forward(history: list[MapRow]) -> tuple[EloBook, list[tuple[float, float]]]:
    """Replay the history series by series: predict each series' maps from the
    ratings at its start as (logit gap home - away, home won), then update."""
    book, points, _, _ = walk_forward_players(history)
    return book, points


def walk_forward_players(
    history: list[MapRow],
    pool: MapPoolBook | None = None,
    mpoints: list[MapPoint] | None = None,
) -> tuple[EloBook, list[tuple[float, float]], PlayerEloBook,
           list[tuple[float, float]]]:
    """walk_forward, plus the player Elo and its (lineup gap, home won)
    points - each series from the ratings and lineups at its start. With a
    `pool` (audit B11) its map deviations are replayed too and each rated
    series' MapPoints appended to `mpoints`."""
    book = EloBook()
    players = PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    by_series: dict[int, list[MapRow]] = {}
    for m in history:
        by_series.setdefault(m.event_id, []).append(m)
    for maps in by_series.values():  # insertion order is chronological
        home, away = maps[0].home_id, maps[0].away_id
        if pool is not None and mpoints is not None:
            mpoints.extend(series_map_points(maps, book, players, pool))
        if book.rated(home, away):
            d = logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in maps)
            g = players.gap(home, away)
            if g is not None:
                ppoints.extend((g, 1.0 if m.home_won else 0.0) for m in maps)
        for m in maps:
            if pool is not None:
                pool.update(m, book)
            winner, loser = (
                (m.home_id, m.away_id) if m.home_won else (m.away_id, m.home_id)
            )
            book.update(winner, loser)
            players.update(m)
    return book, points, players, ppoints


def build_ratings(history: list[MapRow],
                  map_terms: tuple[str, ...] = ()) -> RatingModel:
    """The calibrated rating model; `map_terms` (audit B11, MAP_TERMS under
    epochs.CS2_MAP_IDENTITY) adds the order / pool terms for p_map_nr."""
    pool = MapPoolBook() if map_terms else None
    mpoints: list[MapPoint] = []
    book, points, players, ppoints = walk_forward_players(history, pool, mpoints)
    if len(points) < MIN_FIT:
        return RatingModel(book, n_fit=len(points))
    a, b = fit_logistic([x for x, _ in points], [y for _, y in points])
    model = RatingModel(book, a, max(0.0, min(2.0, b)), len(points), players)
    if len(ppoints) >= MIN_FIT:
        pa, pb = fit_logistic([x for x, _ in ppoints], [y for _, y in ppoints])
        model.pa, model.pb, model.p_fit = pa, max(0.0, min(2.0, pb)), len(ppoints)
    if map_terms:
        fit_map_terms(model, mpoints, map_terms, pool)
    return model


# --- rounds from a round-win probability ------------------------------------------

# A CS2 map is a race to 13 rounds (MR12); at 12-12, overtime is played in
# blocks of six, first to four, repeated at 3-3. Given team1's probability of
# winning a single round, the final-score distribution is exact (no
# simulation); the round probability is solved so that the map-win
# probability matches the rating's. Measured before use: see
# ROUND_MODEL_EVIDENCE below.
MAX_OVERTIMES = 6


@cache
def map_score_distribution(p_round: float) -> dict[tuple[int, int], float]:
    """(team1 rounds, team2 rounds) -> probability, for one map."""
    q = 1.0 - p_round
    out: dict[tuple[int, int], float] = defaultdict(float)
    # regulation: paths to 13-k for k <= 11
    for k in range(12):
        out[(13, k)] += math.comb(12 + k, k) * p_round ** 13 * q ** k
        out[(k, 13)] += math.comb(12 + k, k) * q ** 13 * p_round ** k
    level = math.comb(24, 12) * p_round ** 12 * q ** 12  # 12-12
    base1 = base2 = 12
    for _ in range(MAX_OVERTIMES):
        # one overtime block: first to 4 of up to 6; 3-3 goes on
        for k in range(3):
            ways = level * math.comb(3 + k, k)
            out[(base1 + 4, base2 + k)] += ways * p_round ** 4 * q ** k
            out[(base1 + k, base2 + 4)] += ways * q ** 4 * p_round ** k
        level *= math.comb(6, 3) * p_round ** 3 * q ** 3
        base1 += 3
        base2 += 3
    if level > 0:  # the tail past MAX_OVERTIMES: split by strength, ~1e-6
        out[(base1 + 4, base2)] += level * p_round
        out[(base1, base2 + 4)] += level * q
    return dict(out)


def map_win_probability(p_round: float) -> float:
    return sum(v for (a, b), v in map_score_distribution(p_round).items() if a > b)


# Rounds are not independent (economy, side swaps, a team's night on a map):
# a per-map shock on the round probability, sd ROUND_SHOCK_SD, makes the
# overtime share right and the margins wider. Chosen on the second half of
# the training maps (map_rounds margins, threshold Brier): 0.06 0.17812,
# 0.10 0.17576, 0.12 0.17518, 0.15 0.17535; held out (3,047 maps) 0.17348
# against the base rate's 0.17825, overtime share 0.110 against 0.119 in the
# history (0.155 with independent rounds). The total's length it does not
# help: 0.1924 against the base rate's 0.1918 - totals stay the base rate.
ROUND_SHOCK_SD = 0.12
_SHOCK_NODES = ((-1.5, 0.1), (-0.5, 0.4), (0.5, 0.4), (1.5, 0.1))


def mixed_score_distribution(
    p_round: float, sd: float = ROUND_SHOCK_SD
) -> dict[tuple[int, int], float]:
    """map_score_distribution averaged over the per-map shock."""
    if sd <= 0:
        return map_score_distribution(round(p_round, 4))
    out: dict[tuple[int, int], float] = defaultdict(float)
    for z, w in _SHOCK_NODES:
        q = min(max(p_round + z * sd, 0.05), 0.95)
        for k, v in map_score_distribution(round(q, 4)).items():
            out[k] += w * v
    return dict(out)


def map_distribution_for(p_map: float, sd: float = ROUND_SHOCK_SD
                         ) -> dict[tuple[int, int], float]:
    """The map's score distribution whose map-win probability is p_map."""
    lo, hi = 0.05, 0.95
    for _ in range(30):
        mid = (lo + hi) / 2
        dist = mixed_score_distribution(mid, sd)
        if sum(v for (a, b), v in dist.items() if a > b) < p_map:
            lo = mid
        else:
            hi = mid
    return mixed_score_distribution((lo + hi) / 2, sd)


@lru_cache(maxsize=4096)
def _race_dist(p_key: float) -> tuple[tuple[tuple[int, int], float], ...]:
    return tuple(sorted(map_distribution_for(p_key).items()))


def team_rounds_from_race(p_map: float, idx: int, line: float, over: bool
                          ) -> float | None:
    """P(team idx's rounds on one map OVER / UNDER `line` | no push), from the
    map's score distribution whose map-win probability (team 0's) is p_map -
    the round race map_rounds_handicap prices with (audit 2026-10-13 B10,
    epochs.CS2_TEAM_ROUNDS_RACE). p_map is rounded to 3 decimals (cache)."""
    dist = _race_dist(round(min(max(p_map, 0.05), 0.95), 3))
    p_over = sum(q for score, q in dist if score[idx] > line)
    p_under = sum(q for score, q in dist if score[idx] < line)
    return side_given_no_push(p_over, p_under, over)


def round_probability(p_map: float) -> float:
    """The single-round probability whose map-win probability is p_map."""
    lo, hi = 0.02, 0.98
    target = min(max(p_map, map_win_probability(lo)), map_win_probability(hi))
    for _ in range(40):
        mid = (lo + hi) / 2
        if map_win_probability(round(mid, 6)) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 6)


# --- the models ---------------------------------------------------------------------


@dataclass(frozen=True)
class ModelP:
    p: float  # for the line's own side, given no push
    n: int  # maps behind the number
    model: str


def side_given_no_push(p_over: float, p_under: float, over: bool) -> float | None:
    """P(side | not a push). grade() voids a push, so its mass belongs to
    neither side - an integer line would otherwise pour it all into UNDER."""
    total = p_over + p_under
    if total <= 1e-12:
        return None
    return (p_over if over else p_under) / total


def count_p(values: list[int], line: float, over: bool) -> ModelP | None:
    """P(OVER / UNDER the line) for a count, from a sample of it.

    Negative binomial when the predictive variance exceeds the mean; a
    continuity-corrected normal when it does not - deaths are bounded by the
    rounds played and were under-dispersed for a third of players, and a
    Poisson floor would widen them.
    """
    n = len(values)
    if n < MIN_SAMPLE:
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    var_pred = predictive_sd(var, mean, n, apply_poisson_floor=False) ** 2
    lo, hi = math.floor(line), math.ceil(line)  # equal on an integer line
    if var_pred > mean:
        # nb_survival(m, v, k) = P(X > k). OVER 19.5 and OVER 20 both ask for
        # X > floor(line); UNDER 20 asks for X <= 19, i.e. 1 - P(X > 19).
        p_over = nb_survival(mean, var_pred, lo)
        p_under = 1.0 - nb_survival(mean, var_pred, lo - 1) if lo == hi else 1 - p_over
        model = "negative_binomial"
    else:
        # Floored: a constant sample ([5] * 8) otherwise has sd ~ 0 and claims
        # the clamp at once (round 2 review) - eight maps prove less than that.
        sd = math.sqrt(max(var_pred, MIN_VAR_RATIO * mean, 1e-9))
        p_over = 1.0 - normal_cdf((math.floor(line) + 0.5 - mean) / sd)
        p_under = normal_cdf((lo - 0.5 - mean) / sd) if lo == hi else 1 - p_over
        model = "normal"
    side = side_given_no_push(p_over, p_under, over)
    return None if side is None else ModelP(clamp(side), n, model)


def base_rate(values: list[int], line: float) -> float | None:
    """The history's own share above the line, pushes left out."""
    decided = [v for v in values if v != line]
    if len(decided) < MIN_FIT:
        return None
    return sum(1 for v in decided if v > line) / len(decided)


def shrunk_frequency(
    values: list[int], line: float, over: bool, base: float | None
) -> ModelP | None:
    """The sample's share on this side, shrunk toward the base rate with
    K_ROUNDS pseudo-maps; pushes left out of both, as grade() leaves them out.

    At review the plain Laplace frequency scored Brier 0.2587 against 0.2485
    for a constant rate on 1,356 first maps: a team's last twenty maps carry
    little of the next map's length, so the base rate has to carry the rest.
    """
    decided = [v for v in values if v != line]
    n = len(decided)
    if n < MIN_SAMPLE or base is None:
        return None
    hits = sum(1 for v in decided if (v > line) == over)
    prior = base if over else 1.0 - base
    p = (hits + K_ROUNDS * prior) / (n + K_ROUNDS)
    return ModelP(clamp(p), n, "shrunk_frequency")


def _team_maps(history: list[MapRow], team: int) -> list[MapRow]:
    return [m for m in history if team in (m.home_id, m.away_id)][-MAX_SAMPLE:]


def _rounds_maps(history: list[MapRow], team: int) -> list[MapRow]:
    """The team's last MAX_SAMPLE maps that carry rounds."""
    with_rounds = [
        m
        for m in history
        if team in (m.home_id, m.away_id) and m.home_rounds is not None
    ]
    return with_rounds[-MAX_SAMPLE:]


def total_rounds(maps: list[MapRow]) -> list[int]:
    return [
        m.home_rounds + m.away_rounds
        for m in maps
        if m.home_rounds is not None and m.away_rounds is not None
    ]


def own_rounds(maps: list[MapRow], team: int) -> list[int]:
    out: list[int] = []
    for m in maps:
        own = m.home_rounds if m.home_id == team else m.away_rounds
        if own is not None:
            out.append(own)
    return out


def both_sides_rounds(maps: list[MapRow]) -> list[int]:
    out: list[int] = []
    for m in maps:
        if m.home_rounds is not None and m.away_rounds is not None:
            out += [m.home_rounds, m.away_rounds]
    return out


def player_id(history: list[MapRow], team: int, name: str) -> int | None:
    """The Sofascore id of the one player with this nickname on the team's
    recent maps, or None (none or a namesake)."""
    folded = esports_name(name)
    ids = {
        pid
        for m in _team_maps(history, team)
        for t, pid, nick, _ in m.players
        if t == team and nick == folded
    }
    return next(iter(ids)) if len(ids) == 1 else None


def player_values(history: list[MapRow], team: int, name: str, stat: str) -> list[int]:
    """The player's last maps: found by his nickname on this team's recent maps,
    then followed by his Sofascore player id - across teams, since players
    move - so the sample is his, not a namesake's."""
    pid = player_id(history, team, name)
    if pid is None:
        return []
    values: list[int] = []
    for m in reversed(history):
        for _, p, _, stats in m.players:
            if p == pid:
                value = dict(stats).get(stat)
                if value is not None:
                    values.append(value)
        if len(values) >= MAX_SAMPLE:
            break
    return values


def team_kills(history: list[MapRow], team: int) -> list[int]:
    out: list[int] = []
    for m in _team_maps(history, team):
        kills = [dict(s).get("kills") for t, _, _, s in m.players if t == team]
        if len(kills) >= 5 and all(k is not None for k in kills):
            out.append(sum(k for k in kills if k is not None))
    return out


# --- audit B12: counts from the rounds' exposure --------------------------------

# A team's kills on a map are mostly its rounds: c_w per round it wins, c_l
# per round it loses (kills correlate 0.592 with the map's rounds; 15.94 a
# player in a won map, 12.71 in a lost one). So a count line is priced from
# the round race's (W, L) distribution (B10's map_distribution_for, which
# carries the opponent through p_map) x per-round rates: global c_w / c_l
# (least squares, no intercept, every earlier map), the team's own multiplier
# and the opponent's on the stat against it (kills <-> deaths), each shrunk
# with K_TEAM_RATE maps, and a player's share of his team's stat shrunk to
# SHARE_PRIOR with K_SHARE maps. Given (W, L) the count is a negative binomial
# with variance phi x mean (a continuity-corrected normal when phi <= 1),
# phi the mean of (x - mu)^2 / mu over earlier predictions at the actual
# (W, L). epochs.CS2_COUNT_EXPOSURE_FROM_UTC.
EXPOSURE_STATS = ("kills", "deaths", "assists", "headshots")
AGAINST = {"kills": "deaths", "deaths": "kills"}
K_TEAM_RATE = 5.0
K_SHARE = 2.0
SHARE_PRIOR = 0.2
RACE_MIN_Q = 1e-4  # (W, L) cells under this mass are left out of the mixture
UNFITTED_EXPOSURE = ("K_TEAM_RATE", "K_SHARE", "SHARE_PRIOR", "RACE_MIN_Q")
# The families the switch covers (the pre-registered measurement, B12): headshots
# were worse than the sample (+0.188 log-loss) and stay on count_p.
EXPOSURE_FAMILIES: frozenset[str] = frozenset(COUNT_FAMILIES) - {"player_headshots"}

TeamMap = tuple[int, int, int, int, dict[str, int], list[tuple[int, dict[str, int]]]]


def map_sides(m: MapRow) -> list[TeamMap]:
    """(team, opponent, W, L, team totals, [(player, own stats)]) for each side
    of a map with rounds; a total only for a stat all >= 5 players carry."""
    if m.home_rounds is None or m.away_rounds is None:
        return []
    out: list[TeamMap] = []
    for team, opp, w, lost in ((m.home_id, m.away_id, m.home_rounds, m.away_rounds),
                               (m.away_id, m.home_id, m.away_rounds, m.home_rounds)):
        rows = [(pid, dict(s)) for t, pid, _, s in m.players if t == team]
        totals: dict[str, int] = {}
        if len(rows) >= 5:
            for stat in EXPOSURE_STATS:
                vals = [r.get(stat) for _, r in rows]
                if all(isinstance(v, int) for v in vals):
                    totals[stat] = sum(int(v) for v in vals if v is not None)
        out.append((team, opp, w, lost, totals, rows))
    return out


@dataclass
class ExposureBook:
    """Per-round rates replayed map by map (update), queried before a map."""

    sums: dict[str, list[float]] = field(default_factory=dict)  # WW WL LL WS LS n
    team_recent: dict[int, deque[tuple[int, int, dict[str, int]]]] = field(
        default_factory=dict)
    player_recent: dict[int, deque[tuple[dict[str, int], dict[str, int]]]] = field(
        default_factory=dict)
    phi_sums: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    def coef(self, stat: str) -> tuple[float, float] | None:
        s = self.sums.get(stat)
        if s is None or s[5] < MIN_FIT:
            return None
        sol = _solve([[s[0], s[1]], [s[1], s[2]]], [s[3], s[4]])
        if sol is None:
            return None
        return max(sol[0], 0.0), max(sol[1], 0.0)

    def team_mult(self, team: int, stat: str) -> float:
        cf = self.coef(stat)
        recent = [(w, lost, t[stat]) for w, lost, t in self.team_recent.get(team, ())
                  if stat in t]
        if cf is None or not recent:
            return 1.0
        exp = [cf[0] * w + cf[1] * lost for w, lost, _ in recent]
        mean_exp = sum(exp) / len(exp)
        if mean_exp <= 0:
            return 1.0
        obs = sum(x for _, _, x in recent)
        return (obs + K_TEAM_RATE * mean_exp) / (sum(exp) + K_TEAM_RATE * mean_exp)

    def rates(self, team: int, opp: int, stat: str) -> tuple[float, float] | None:
        """(per won round, per lost round) of the team's stat against `opp`."""
        cf = self.coef(stat)
        if cf is None:
            return None
        m = self.team_mult(team, stat)
        if stat in AGAINST:
            m *= self.team_mult(opp, AGAINST[stat])
        return cf[0] * m, cf[1] * m

    def share(self, pid: int, stat: str) -> float | None:
        """The player's share of his team's stat, >= MIN_SAMPLE maps."""
        recent = [(own[stat], tot[stat]) for own, tot in self.player_recent.get(pid, ())
                  if stat in own and stat in tot]
        if len(recent) < MIN_SAMPLE:
            return None
        team_sum = sum(t for _, t in recent)
        mean_t = team_sum / len(recent)
        return ((sum(o for o, _ in recent) + K_SHARE * SHARE_PRIOR * mean_t)
                / (team_sum + K_SHARE * mean_t)) if team_sum + mean_t > 0 else None

    def phi(self, level: str, stat: str) -> float | None:
        s = self.phi_sums.get((level, stat))
        if s is None or s[1] < MIN_FIT:
            return None
        return s[0] / s[1]

    def _phi_add(self, level: str, stat: str, x: int, mu: float) -> None:
        if mu <= 0:
            return
        s = self.phi_sums.setdefault((level, stat), [0.0, 0.0])
        s[0] += (x - mu) ** 2 / mu
        s[1] += 1

    def update(self, m: MapRow) -> None:
        """Score the map's counts at its actual (W, L) from the state before
        it (phi), then learn from it."""
        sides = map_sides(m)
        for team, opp, w, lost, totals, rows in sides:
            for stat, x in totals.items():
                r = self.rates(team, opp, stat)
                if r is None:
                    continue
                mu_t = r[0] * w + r[1] * lost
                self._phi_add("team", stat, x, mu_t)
                for pid, own in rows:
                    sh = self.share(pid, stat)
                    v = own.get(stat)
                    if sh is not None and isinstance(v, int):
                        self._phi_add("player", stat, v, sh * mu_t)
        for team, _, w, lost, totals, rows in sides:
            for stat, x in totals.items():
                s = self.sums.setdefault(stat, [0.0] * 6)
                s[0] += w * w
                s[1] += w * lost
                s[2] += lost * lost
                s[3] += w * x
                s[4] += lost * x
                s[5] += 1
            self.team_recent.setdefault(team, deque(maxlen=MAX_SAMPLE)).append(
                (w, lost, totals))
            for pid, own in rows:
                vals = {k: v for k, v in own.items() if isinstance(v, int)}
                self.player_recent.setdefault(pid, deque(maxlen=MAX_SAMPLE)).append(
                    (vals, totals))


def build_exposure(history: list[MapRow]) -> ExposureBook:
    book = ExposureBook()
    for m in history:
        book.update(m)
    return book


def race_cells(p_map: float, idx: int) -> list[tuple[float, int, int]]:
    """(q, W, L) of the round race for team idx (0 = the side p_map is for),
    cells under RACE_MIN_Q left out."""
    dist = _race_dist(round(min(max(p_map, 0.05), 0.95), 3))
    return [(q, sc[idx], sc[1 - idx]) for sc, q in dist if q >= RACE_MIN_Q]


def _count_cdf(mu: float, phi: float, kmax: int) -> list[float]:
    """P(X <= k), k = 0..kmax, NB with variance phi x mu (phi > 1)."""
    r = mu / (phi - 1.0)
    q = 1.0 - 1.0 / phi
    pmf = math.exp(r * math.log(1.0 / phi))
    acc = pmf
    out = [acc]
    for k in range(kmax):
        pmf *= (k + r) / (k + 1) * q
        acc += pmf
        out.append(min(acc, 1.0))
    return out


def exposure_sides(cells: list[tuple[float, float]], phi: float,
                   lines: list[float]) -> dict[float, tuple[float, float]]:
    """{line: (P(OVER), P(UNDER))} of the (q, mu) mixture; an integer line's
    push belongs to neither."""
    out = {ln: [0.0, 0.0] for ln in lines}
    kmax = max(math.floor(ln) for ln in lines) if lines else 0
    for q, mu in cells:
        if mu <= 0:
            for ln in lines:
                out[ln][1] += q
            continue
        if phi > 1.0:
            cdf = _count_cdf(mu, phi, max(kmax, 0))
            for ln in lines:
                lo = math.floor(ln)
                c_lo = cdf[lo] if lo >= 0 else 0.0
                out[ln][0] += q * (1.0 - c_lo)
                if lo == ln:
                    out[ln][1] += q * (cdf[lo - 1] if lo >= 1 else 0.0)
                else:
                    out[ln][1] += q * c_lo
        else:
            sd = math.sqrt(max(phi, MIN_VAR_RATIO) * mu)
            for ln in lines:
                lo = math.floor(ln)
                p_over = 1.0 - normal_cdf((lo + 0.5 - mu) / sd)
                out[ln][0] += q * p_over
                out[ln][1] += q * (normal_cdf((lo - 0.5 - mu) / sd) if lo == ln
                                   else 1.0 - p_over)
    return {ln: (v[0], v[1]) for ln, v in out.items()}


def exposure_cells(book: ExposureBook, p_team: float, team: int, opp: int,
                   stat: str, pid: int | None) -> list[tuple[float, float]] | None:
    """(q, mu) of the team's (pid None) or a player's stat, p_team the team's
    map-win probability; None without rates or a share."""
    r = book.rates(team, opp, stat)
    if r is None:
        return None
    share = 1.0
    if pid is not None:
        sh = book.share(pid, stat)
        if sh is None:
            return None
        share = sh
    return [(q, share * (r[0] * w + r[1] * lost))
            for q, w, lost in race_cells(p_team, 0)]


def exposure_p(book: ExposureBook, p_team: float, team: int, opp: int,
               stat: str, pid: int | None, line: float, over: bool
               ) -> ModelP | None:
    """One side of a count line from the rounds' exposure (audit B12)."""
    cells = exposure_cells(book, p_team, team, opp, stat, pid)
    phi = book.phi("team" if pid is None else "player", stat)
    if cells is None or phi is None:
        return None
    po, pu = exposure_sides(cells, phi, [line])[line]
    side = side_given_no_push(po, pu, over)
    n = len(book.team_recent.get(team, ()))
    return None if side is None else ModelP(clamp(side), n, "round_exposure")


def model_probability(
    line: Cs2Line,
    team1_id: int,
    team2_id: int,
    team1: str,
    team2: str,
    best_of: int,
    history: list[MapRow],
    ratings: RatingModel,
    team1_is_home: bool,
    team_rounds_race: bool = False,
    map_identity: bool = False,
    exposure: ExposureBook | None = None,
) -> ModelP | None:
    """The model's probability for this side of this line, or None.
    `team_rounds_race` (epochs.CS2_TEAM_ROUNDS_RACE_FROM_UTC): a team's
    rounds on a map from the round race, not its own shrunk frequency.
    `map_identity` (epochs.CS2_MAP_IDENTITY_FROM_UTC): a map-level line reads
    its own map's p (RatingModel.p_map_nr; ratings built with MAP_TERMS).
    `exposure` (epochs.CS2_COUNT_EXPOSURE_FROM_UTC, build_exposure of the
    same history): an EXPOSURE_FAMILIES line from the rounds' exposure, the
    old sample model where the exposure has no number."""
    fam = line.family
    if fam not in MODELLED:
        return None
    subject = line.subject.strip()
    side_team = team1_id if subject == team1 else team2_id if subject == team2 else None

    if fam in SERIES_FAMILIES:
        p = ratings.p_map(team1_id, team2_id, team1_is_home)
        if p is None:
            return None
        n = min(ratings.book.played[team1_id], ratings.book.played[team2_id])
        try:
            dist = series_distribution_mixed(clamp(p), best_of)
        except ValueError:
            return None
        idx = None if side_team is None else (0 if side_team == team1_id else 1)
        side = series_side_p(dist, fam, line.line, line.side, idx)
        return None if side is None else ModelP(clamp(side), n, "elo_series_mixed")

    if fam in ELO_FAMILIES:
        p = ratings.p_map(team1_id, team2_id, team1_is_home)
        if p is None:
            return None
        n = min(ratings.book.played[team1_id], ratings.book.played[team2_id])
        if fam == "map_winner":
            if map_identity and line.map_nr >= 1:
                pm = ratings.p_map_nr(team1_id, team2_id, team1_is_home, best_of,
                                      line.map_nr)
                if pm is not None:
                    return ModelP(clamp(pm if line.side == "T1" else 1.0 - pm), n,
                                  "elo_map")
            return ModelP(clamp(p if line.side == "T1" else 1.0 - p), n, "elo")
        try:
            dist = series_distribution(round(p, 6), best_of)
        except ValueError:
            return None
        if fam in ("match_winner", "maps_handicap"):
            hcp = line.line or 0.0
            p_t1 = sum(q for (a, b), q in dist.items() if a - b + hcp > 0)
            p_t2 = sum(q for (a, b), q in dist.items() if a - b + hcp < 0)
            side = side_given_no_push(p_t1, p_t2, line.side == "T1")
            return None if side is None else ModelP(clamp(side), n, "elo_series")
        if line.line is None or line.side not in ("OVER", "UNDER"):
            return None
        if fam == "maps_total":
            count = {score: score[0] + score[1] for score in dist}
        else:  # team_maps
            if side_team is None:
                return None
            idx = 0 if side_team == team1_id else 1
            count = {score: score[idx] for score in dist}
        p_over = sum(q for score, q in dist.items() if count[score] > line.line)
        p_under = sum(q for score, q in dist.items() if count[score] < line.line)
        side = side_given_no_push(p_over, p_under, line.side == "OVER")
        return None if side is None else ModelP(clamp(side), n, "elo_series")

    if fam == "map_rounds_handicap":
        # team1's round handicap on one map, graded on t1 - t2 rounds
        p = _p_for(ratings, team1_id, team2_id, team1_is_home, best_of,
                              line.map_nr, map_identity)
        if p is None or line.line is None or line.side not in ("T1", "T2"):
            return None
        dist = map_distribution_for(p)
        hcp = line.line
        p_t1 = sum(q for (a, b), q in dist.items() if a - b + hcp > 0)
        p_t2 = sum(q for (a, b), q in dist.items() if a - b + hcp < 0)
        side = side_given_no_push(p_t1, p_t2, line.side == "T1")
        n = min(ratings.book.played[team1_id], ratings.book.played[team2_id])
        return None if side is None else ModelP(clamp(side), n, "round_race")
    if line.line is None or line.side not in ("OVER", "UNDER"):
        return None
    over = line.side == "OVER"
    if fam == "map_rounds_total":
        # The history's base rate alone. With the two teams' own last maps
        # shrunk toward it, the score only ever approached the base rate as the
        # shrinkage grew (lines 19.5-23.5, K = 20/50/100, 1,326 first maps):
        # the teams' sample carried nothing about the next map's length.
        decided = [v for v in total_rounds(history) if v != line.line]
        base = base_rate(decided, line.line)
        if base is None:
            return None
        return ModelP(clamp(base if over else 1.0 - base), len(decided), "base_rate")
    if fam in ("map_team_rounds", "team_kills"):
        # A team line: its subject must be one of the two teams. A player
        # line's subject is a nickname - checking it here once returned None
        # for every player line (found live on GamerLegion - magic).
        if side_team is None:
            return None
        if fam == "map_team_rounds" and team_rounds_race:
            p = _p_for(ratings, team1_id, team2_id, team1_is_home, best_of,
                                  line.map_nr, map_identity)
            if p is None:
                return None
            idx = 0 if side_team == team1_id else 1
            side = team_rounds_from_race(p, idx, line.line, over)
            n = min(ratings.book.played[team1_id], ratings.book.played[team2_id])
            return None if side is None else ModelP(clamp(side), n, "round_race")
        if fam == "map_team_rounds":
            base = base_rate(both_sides_rounds(history), line.line)
            values = own_rounds(_rounds_maps(history, side_team), side_team)
            return shrunk_frequency(values, line.line, over, base)
        if exposure is not None and fam in EXPOSURE_FAMILIES:
            opp = team2_id if side_team == team1_id else team1_id
            mp = _exposure_line(exposure, ratings, team1_id, team2_id,
                                team1_is_home, best_of, line, map_identity,
                                side_team, opp, "kills", None, over)
            if mp is not None:
                return mp
        return count_p(team_kills(history, side_team), line.line, over)
    stat = fam.removeprefix("player_")
    for team in (team1_id, team2_id):
        values = player_values(history, team, line.subject, stat)
        if values:
            if exposure is not None and fam in EXPOSURE_FAMILIES:
                pid = player_id(history, team, line.subject)
                opp = team2_id if team == team1_id else team1_id
                mp = _exposure_line(exposure, ratings, team1_id, team2_id,
                                    team1_is_home, best_of, line, map_identity,
                                    team, opp, stat, pid, over)
                if mp is not None:
                    return mp
            return count_p(values, line.line, over)
    return None


def _p_for(ratings: RatingModel, team1: int, team2: int, team1_is_home: bool,
           best_of: int | None, map_nr: int, map_identity: bool) -> float | None:
    """p_map_nr under the switch on a numbered map, p_map otherwise."""
    if map_identity and map_nr >= 1:
        return ratings.p_map_nr(team1, team2, team1_is_home, best_of, map_nr)
    return ratings.p_map(team1, team2, team1_is_home)


def _exposure_line(book: ExposureBook, ratings: RatingModel, team1_id: int,
                   team2_id: int, team1_is_home: bool, best_of: int,
                   line: Cs2Line, map_identity: bool, team: int, opp: int,
                   stat: str, pid: int | None, over: bool) -> ModelP | None:
    """exposure_p for the line's team (pid None) or player, with the team's
    map-win probability from the ratings."""
    if line.line is None or (pid is None and stat != "kills"):
        return None
    p1 = _p_for(ratings, team1_id, team2_id, team1_is_home, best_of,
                           line.map_nr, map_identity)
    if p1 is None:
        return None
    p_team = p1 if team == team1_id else 1.0 - p1
    return exposure_p(book, p_team, team, opp, stat, pid, line.line, over)


# --- checking the engine against history --------------------------------------------


def _brier(ps: list[float], ys: list[float]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / len(ys)


def elo_backtest(history: list[MapRow], train_share: float = 0.7) -> dict[str, Any]:
    """Out-of-sample check of the rating model, the way production uses it.

    Each series is predicted from the ratings frozen at its start. The
    calibration is fitted on the first `train_share` of those predictions and
    scored on the rest; raw Elo is scored on the same held-out maps, so the two
    held-out figures are comparable. A sanity check on the engine, not a claim
    of edge - only CS2_SETTLE compares with the price.
    """
    _, points = walk_forward(history)
    cut = int(len(points) * train_share)
    train, test = points[:cut], points[cut:]
    result: dict[str, Any] = {
        "maps_predicted": len(points),
        "maps_held_out": len(test),
        "brier_raw_held_out": None,
        "brier_calibrated_held_out": None,
    }
    if not test:
        return result
    ys = [y for _, y in test]
    result["brier_raw_held_out"] = _brier([_sigmoid(x) for x, _ in test], ys)
    if len(train) >= MIN_FIT:
        a, b = fit_logistic([x for x, _ in train], [y for _, y in train])
        b = max(0.0, min(2.0, b))
        result["brier_calibrated_held_out"] = _brier(
            [_sigmoid(a + b * x) for x, _ in test], ys
        )
    return result


# --- model against price ---------------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    family: str
    series: int
    sides: int
    brier_price: float
    brier_model: float
    brier_blend: float  # the plain average of the two probabilities

    @property
    def model_beats_price(self) -> bool:
        return self.brier_model < self.brier_price


def compare_to_price(rows: list[dict[str, Any]], label: str) -> Comparison | None:
    """Brier of the devigged price, of the model and of their average, on the
    graded sides that carry both. Lower is better; the same sides for all
    three, so the three numbers are comparable and nothing else is."""
    rs = [
        r for r in rows if r.get("fair_p") is not None and r.get("model_p") is not None
    ]
    if not rs:
        return None
    ys = [1.0 if r["outcome"] == "WIN" else 0.0 for r in rs]
    price = [float(r["fair_p"]) for r in rs]
    model = [float(r["model_p"]) for r in rs]
    return Comparison(
        family=label,
        series=len({r.get("superbet_event_id") for r in rs}),
        sides=len(rs),
        brier_price=_brier(price, ys),
        brier_model=_brier(model, ys),
        brier_blend=_brier(
            [(a + b) / 2 for a, b in zip(price, model, strict=True)], ys
        ),
    )
