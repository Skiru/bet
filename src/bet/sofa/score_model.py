"""A score model for hockey, basketball and volleyball - the measured sports.

Until 2026-10-01 these sports had no model: SHADOW recorded Superbet's lines,
SHADOW_SETTLE graded them, and the experimental sport coupons priced every
leg at Superbet's own devigged price. This module is the first model of the
score itself, built on what the pipeline already trusts:

  * the rating is football_rating.RatingBook - opponent-adjusted attack and
    defence ratios per competition, league strength learnt only across
    leagues, ratios shrunk toward 1 outside their league - replayed over the
    cached Sofascore listings, one metric per regulation period (hockey
    period, basketball quarter) or points per set (volleyball);
  * a game is SIMULATED from the per-period expectations, and every simulated
    game is graded by the same shadow.actual_value / shadow.grade that
    SHADOW_SETTLE uses, so a line's probability has exactly the settlement
    semantics of the line (regulation vs overtime, a hockey shootout's
    deciding goal, basketball's ambiguous last quarter, a push);
  * hockey goals per period are Poisson; basketball quarter points are normal
    with a spread measured on the replayed history; a volleyball set is won
    with a probability read off the two sides' points-per-set expectations.

It prices nothing by itself and gates nothing: sport_coupon decides what, if
anything, it is allowed to change, and only on measurement.
"""

from __future__ import annotations

import dataclasses
import json
import math
import random
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bet.sofa.football_rating import (
    ALPHA_BY_METRIC,
    LINKED,
    MIN_TEAM_MATCHES,
    FootballResult,
    RatingBook,
)
from bet.sofa.resolve import sofascore_gender
from bet.sofa.shadow import (
    MARKETS,
    SPORTS,
    GameResult,
    ShadowLine,
    ShadowSport,
    actual_value,
    grade,
    is_player_line,
)

# Simulated games per forecast. The Monte Carlo error of a probability is at
# most 0.5 / sqrt(N) = 0.008 at 4,000 - below every margin on the board.
N_SIMS = 4000
# The replayed window whose residuals set basketball's per-quarter spread.
SPREAD_WINDOW_S = 90 * 86400
# A volleyball set: target points, and the deciding set's.
SET_TARGET = 25
DECIDER_TARGET = 15


def period_metric(i: int) -> str:
    return f"p{i}_for"


VOLLEYBALL_METRIC = "setpts_for"
# Hockey and basketball are rated on the regulation score of the whole game
# and split into periods by the measured period shares: a single quarter or
# period is mostly noise. Chosen on one-step-ahead squared error of the
# match score (tune 2026-03-01..07-15, test 07-15..09-29, backfilled
# history): basketball full-game 121.19 at alpha 0.06 against 126.45 for the
# sum of per-quarter ratings at their best alpha; hockey flat, 0.02.
REG_METRIC = {"hockey": "hk_reg_for", "basketball": "bb_reg_for"}
SCORE_ALPHA = {"hk_reg_for": 0.02, "bb_reg_for": 0.06, VOLLEYBALL_METRIC: 0.04}
ALPHA_BY_METRIC.update(SCORE_ALPHA)


def _is_friendly(event: dict[str, Any]) -> bool:
    unique = (event.get("tournament") or {}).get("uniqueTournament") or {}
    return "friendly" in str(unique.get("name") or "").lower()


def parse_event(event: dict[str, Any], sport: ShadowSport) -> FootballResult | None:
    """One finished game as rating input, or None.

    Hockey / basketball: exactly the regulation periods, each a count >= 0.
    Volleyball: every set a clear win; the value is points per set played.
    Friendlies are left out, as in football.
    """
    try:
        if event["tournament"]["category"]["sport"]["slug"] != sport.sofascore_slug:
            return None
        status = event.get("status") or {}
        if status.get("type") != "finished":
            return None
        if status.get("description") not in sport.finished_descriptions:
            return None
        unique = event["tournament"].get("uniqueTournament") or {}
        competition = int(unique.get("id", event["tournament"]["id"]))
        home, away = int(event["homeTeam"]["id"]), int(event["awayTeam"]["id"])
        ts = event["startTimestamp"]
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(ts, int) or _is_friendly(event):
        return None
    hs, as_ = event.get("homeScore") or {}, event.get("awayScore") or {}
    hp: list[int] = []
    ap: list[int] = []
    for n in range(1, 10):
        h, a = hs.get(f"period{n}"), as_.get(f"period{n}")
        if h is None and a is None:
            break
        if not isinstance(h, int) or not isinstance(a, int) or h < 0 or a < 0:
            return None
        hp.append(h)
        ap.append(a)
    values: dict[str, tuple[float, float]] = {}
    if sport.regulation_periods is not None:
        if len(hp) != sport.regulation_periods:
            return None
        for i, (h, a) in enumerate(zip(hp, ap, strict=True), 1):
            values[period_metric(i)] = (float(h), float(a))
        values[REG_METRIC[sport.key]] = (float(sum(hp)), float(sum(ap)))
    else:
        if len(hp) < 3 or any(h == a for h, a in zip(hp, ap, strict=True)):
            return None
        n_sets = len(hp)
        values[VOLLEYBALL_METRIC] = (sum(hp) / n_sets, sum(ap) / n_sets)
    return FootballResult(
        event_id=int(event["id"]), ts=ts, competition_id=competition,
        home_id=home, away_id=away, values=values,
        women=sofascore_gender(event) == "W",
    )


def load_history(db_path: str | Path, sport: ShadowSport) -> list[FootballResult]:
    """Every distinct finished game of the sport in the cached listings."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.execute("PRAGMA busy_timeout = 60000")
    events: dict[int, dict[str, Any]] = {}
    try:
        for (events_json,) in con.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
            "AND events_json LIKE ?", (f'%"slug": "{sport.sofascore_slug}"%',)
        ):
            for event in json.loads(events_json).get("events", []):
                if isinstance(event.get("id"), int):
                    events[event["id"]] = event
    finally:
        con.close()
    out = [r for e in events.values() if (r := parse_event(e, sport)) is not None]
    return sorted(out, key=lambda r: (r.ts, r.event_id))


def _metrics(sport: ShadowSport) -> tuple[str, ...]:
    """The metrics the rating is kept on."""
    if sport.regulation_periods is None:
        return (VOLLEYBALL_METRIC,)
    return (REG_METRIC[sport.key],)


def _rated_values(r: FootballResult, sport: ShadowSport) -> FootballResult:
    keep = set(_metrics(sport))
    return FootballResult(r.event_id, r.ts, r.competition_id, r.home_id, r.away_id,
                          {m: v for m, v in r.values.items() if m in keep}, r.women)


@dataclass(frozen=True)
class SimParams:
    """The simulation's structure beyond the per-period means. Every default
    is the model as first built (2026-10-01); each field is switched on only
    by a measurement (scripts/sofa/measure_score_history.py)."""

    # rating separation: ratios raised to this power for LINKED pairs
    sep_power: float = 1.0
    # basketball: per-quarter points noise = shared game shock (both teams)
    # + team-game shock + independent quarter noise; sds in points/quarter.
    # None = the old independent quarters at ScoreModel.period_sd.
    bb_game_sd: float | None = None
    bb_team_sd: float = 0.0
    bb_quarter_sd: float = 0.0
    # points for a side that played the day before (basketball / hockey)
    b2b_delta: float = 0.0
    # hockey: common per-period Poisson shock (bivariate Poisson, X = A + C)
    hk_common: float = 0.0
    # hockey: an empty-net goal for the leader / a 6-on-5 goal for the
    # trailer, when regulation would end with a 1-2 goal lead
    # Measured 2026-10-01 (measure_score_history.py, mean threshold Brier,
    # tune 03-01..07-15 / test 07-15..09-29): base 0.20558 / 0.20373, with
    # these three 0.20514 / 0.20353 - small, but in both windows (lead 0.1,
    # best on tune, was worse on test and was not taken). The regulation
    # |margin| of 3 is commoner than 2 in the history (0.203 vs 0.188), the
    # empty-net signature a plain Poisson cannot make.
    hk_late_lead: float = 0.2
    hk_late_trail: float = 0.05
    # hockey: overtime winner pulled toward a coin by this factor (1 = none);
    # 467 overtime games: 0.2500 at 1.0 and 0.0, 0.2485 at 0.5
    hk_ot_strength: float = 0.5
    # volleyball: per-set noise on the point share. Measured 2026-10-01 and
    # NOT switched on: set_sd 0.02 tune 0.18357 / test 0.18499 against base
    # 0.18313 / 0.18499; the serve model (sideout 0.62) improved the sets
    # total but lost the winner (tune 0.18390, test 0.18630).
    vb_set_sd: float = 0.0
    # volleyball: the league side-out rate (P(receiving side wins a rally));
    # 0 = rallies independent of the serve. With it, the serving side keeps
    # serving after a point won, so points come in runs (Ferrante & Fonseca
    # 2014), the strength shift solved so the long-run point share is the
    # rating's.
    vb_sideout: float = 0.0
    # basketball: fit bb_game_sd / bb_team_sd / bb_quarter_sd by moments on
    # the build window's quarter residuals when bb_game_sd is None.
    # Measured 2026-10-01 (scripts/sofa/measure_score_history.py, mean
    # threshold Brier): tune 03-01..07-15 0.18038 -> 0.17972, test
    # 07-15..09-29 0.18450 -> 0.18368; the shared game shock is pace
    # (cross-team covariance 1.57 > within-team 0.73 per quarter).
    bb_fit_moments: bool = True


@dataclass
class ScoreModel:
    sport: ShadowSport
    book: RatingBook
    # basketball: the per-quarter residual spread; hockey/volleyball: unused
    period_sd: float
    # each regulation period's share of the regulation score, home and away
    shares: tuple[tuple[float, ...], tuple[float, ...]] = ((), ())
    params: SimParams = SimParams()
    # team -> start timestamp of its latest game in the history read
    last_played: dict[int, int] | None = None

    def expected(
        self, competition: int, home: int, away: int, at_ts: int | None = None,
    ) -> tuple[list[float], list[float]] | None:
        """Per-period (or per-set points) expectations, home and away."""
        metric = _metrics(self.sport)[0]
        if (self.book.team_matches(home, metric) < MIN_TEAM_MATCHES
                or self.book.team_matches(away, metric) < MIN_TEAM_MATCHES):
            return None
        status, lf = self.book.link(home, away, metric)
        exp = self.book.expected(
            competition, home, away, metric, lf, cross=status != LINKED)
        if exp is None:
            return None
        eh, ea = max(exp[0], 0.0), max(exp[1], 0.0)
        k = self.params.sep_power
        if k != 1.0 and status == LINKED:
            rates = self.book.league_rates(competition, metric)
            if rates is not None and rates[0] > 0 and rates[1] > 0:
                eh = rates[0] * (eh / rates[0]) ** k
                ea = rates[1] * (ea / rates[1]) ** k
        if at_ts is not None and self.params.b2b_delta and self.last_played:
            for team, is_home in ((home, True), (away, False)):
                last = self.last_played.get(team)
                if last is not None and 0 < at_ts - last <= 36 * 3600:
                    if is_home:
                        eh = max(eh + self.params.b2b_delta, 0.0)
                    else:
                        ea = max(ea + self.params.b2b_delta, 0.0)
        if self.sport.regulation_periods is None:
            return [eh], [ea]
        sh, sa = self.shares
        return [eh * x for x in sh], [ea * x for x in sa]

    def simulate(
        self, mu1: Sequence[float], mu2: Sequence[float], seed: int = 0,
        n: int = N_SIMS,
    ) -> list[GameResult]:
        """Games in team1 / team2 orientation (mu1 is team1's)."""
        rng = random.Random(seed)
        prm = self.params
        if self.sport.key == "hockey":
            return [_hockey(rng, mu1, mu2, prm) for _ in range(n)]
        if self.sport.key == "basketball":
            return [_basketball(rng, mu1, mu2, self.period_sd, prm) for _ in range(n)]
        return [_volleyball(rng, mu1[0], mu2[0], prm.vb_set_sd, prm.vb_sideout)
                for _ in range(n)]


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def _hockey(
    rng: random.Random, mu1: Sequence[float], mu2: Sequence[float],
    prm: SimParams = SimParams(),
) -> GameResult:
    c = prm.hk_common
    p1l: list[int] = []
    p2l: list[int] = []
    for m1, m2 in zip(mu1, mu2, strict=True):
        shared = _poisson(rng, c) if c > 0 else 0
        p1l.append(_poisson(rng, max(m1 - c, 0.0)) + shared)
        p2l.append(_poisson(rng, max(m2 - c, 0.0)) + shared)
    lead = sum(p1l) - sum(p2l)
    if 1 <= abs(lead) <= 2 and (prm.hk_late_lead or prm.hk_late_trail):
        u = rng.random()
        leader_is_1 = lead > 0
        if u < prm.hk_late_lead:
            (p1l if leader_is_1 else p2l)[-1] += 1
        elif u < prm.hk_late_lead + prm.hk_late_trail:
            (p2l if leader_is_1 else p1l)[-1] += 1
    p1, p2 = tuple(p1l), tuple(p2l)
    r1, r2 = sum(p1), sum(p2)
    if r1 != r2:
        return GameResult(p1, p2, r1, r2, "T1" if r1 > r2 else "T2", False)
    # Overtime / shootout: decided in proportion to the sides' scoring
    # rates, pulled toward a coin by hk_ot_strength; the winner's full score
    # counts the deciding goal (shadow.GameResult.t1_full).
    s1, s2 = sum(mu1), sum(mu2)
    p_ot = s1 / (s1 + s2) if s1 + s2 > 0 else 0.5
    p_ot = 0.5 + prm.hk_ot_strength * (p_ot - 0.5)
    t1_wins = rng.random() < p_ot
    return GameResult(p1, p2, r1 + t1_wins, r2 + (not t1_wins),
                      "T1" if t1_wins else "T2", True)


def _basketball(
    rng: random.Random, mu1: Sequence[float], mu2: Sequence[float], sd: float,
    prm: SimParams = SimParams(),
) -> GameResult:
    if prm.bb_game_sd is None:
        p1 = tuple(max(0, round(rng.gauss(m, sd))) for m in mu1)
        p2 = tuple(max(0, round(rng.gauss(m, sd))) for m in mu2)
        q_sd = sd
    else:
        g = rng.gauss(0.0, prm.bb_game_sd)
        u1 = rng.gauss(0.0, prm.bb_team_sd)
        u2 = rng.gauss(0.0, prm.bb_team_sd)
        q_sd = prm.bb_quarter_sd
        p1 = tuple(max(0, round(m + g + u1 + rng.gauss(0.0, q_sd))) for m in mu1)
        p2 = tuple(max(0, round(m + g + u2 + rng.gauss(0.0, q_sd))) for m in mu2)
    f1, f2 = sum(p1), sum(p2)
    overtime = False
    # A five-minute overtime is 5/40 or 5/48 of a game: scale one quarter.
    q_len = 10.0 if len(mu1) == 4 else 12.0
    ot_sd = max(q_sd, 1.0) * 0.6
    while f1 == f2:
        overtime = True
        f1 += max(0, round(rng.gauss(mu1[-1] * 5 / q_len, ot_sd)))
        f2 += max(0, round(rng.gauss(mu2[-1] * 5 / q_len, ot_sd)))
    return GameResult(p1, p2, f1, f2, "T1" if f1 > f2 else "T2", overtime)


def _logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def serve_probabilities(share: float, sideout: float) -> tuple[float, float]:
    """(P(team1 wins a rally | team1 serves), P(team1 wins | team2 serves))
    whose stationary point share is `share`, at the league side-out rate."""
    def stationary(d: float) -> float:
        pa = _sigmoid(_logit(1.0 - sideout) + d)
        pb = _sigmoid(_logit(sideout) + d)
        pi = pb / (1.0 - pa + pb)  # P(team1 is serving), stationary
        return pi * pa + (1.0 - pi) * pb
    lo, hi = -6.0, 6.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if stationary(mid) < share:
            lo = mid
        else:
            hi = mid
    d = (lo + hi) / 2
    return _sigmoid(_logit(1.0 - sideout) + d), _sigmoid(_logit(sideout) + d)


def _volleyball(
    rng: random.Random, pts1: float, pts2: float, set_sd: float = 0.0,
    sideout: float = 0.0,
) -> GameResult:
    """Best of five. A set goes to team1 with the share of the two sides'
    points-per-set expectations, sharpened by the set's length (a points
    share of 0.52 over ~45 points is a set won ~60% of the time); set_sd
    adds a per-set shock to the share."""
    base = pts1 / (pts1 + pts2) if pts1 + pts2 > 0 else 0.5
    s1: list[int] = []
    s2: list[int] = []
    w1 = w2 = 0
    while w1 < 3 and w2 < 3:
        share = base + (rng.gauss(0.0, set_sd) if set_sd > 0 else 0.0)
        share = min(max(share, 0.05), 0.95)
        target = DECIDER_TARGET if w1 == w2 == 2 else SET_TARGET
        pa, pb = serve_probabilities(share, sideout) if sideout else (share, share)
        serving1 = rng.random() < 0.5
        a = b = 0
        while True:
            if rng.random() < (pa if serving1 else pb):
                a += 1
                serving1 = True
            else:
                b += 1
                serving1 = False
            if (a >= target or b >= target) and abs(a - b) >= 2:
                break
        s1.append(a)
        s2.append(b)
        if a > b:
            w1 += 1
        else:
            w2 += 1
    return GameResult(tuple(s1), tuple(s2), w1, w2, "T1" if w1 > w2 else "T2", False)


def line_probability(
    line: ShadowLine, games: Iterable[GameResult], sport: ShadowSport
) -> float | None:
    """P(this side wins | the line is decided), graded exactly as settled.

    A push (VOID) is left out on both sides, which is also what the devigged
    two-way price describes. Player lines have no model: None.
    """
    if is_player_line(sport.key, line.market_id):
        return None
    spec = MARKETS[sport.key].get(line.market_id)
    if spec is None:
        return None
    three_way = spec.kind == "three_way"
    won = lost = 0
    for game in games:
        actual = actual_value(line, game, sport)
        if actual is None:
            continue
        outcome = grade(line, actual, three_way)
        if outcome == "WIN":
            won += 1
        elif outcome == "LOSS":
            lost += 1
    return won / (won + lost) if won + lost else None


def build_model(history: Sequence[FootballResult], sport: ShadowSport,
                cut_ts: int, params: SimParams | None = None) -> ScoreModel:
    """The rating before the cut; the period shares and, for basketball, the
    quarter spread (one step ahead, before each game updates the book) from
    the last SPREAD_WINDOW_S before it."""
    book = RatingBook()
    k = sport.regulation_periods or 0
    tot_h = [0.0] * k
    tot_a = [0.0] * k
    sq, n = 0.0, 0
    window: list[FootballResult] = []
    before = [r for r in history if r.ts < cut_ts]
    last_ts = before[-1].ts if before else cut_ts
    for r in before:
        if k and r.ts >= last_ts - 365 * 86400:
            for i in range(k):
                vh, va = r.values.get(period_metric(i + 1), (0.0, 0.0))
                tot_h[i] += vh
                tot_a[i] += va
        if sport.key == "basketball" and r.ts >= last_ts - SPREAD_WINDOW_S:
            window.append(r)
        book.update(_rated_values(r, sport))
    shares: tuple[tuple[float, ...], tuple[float, ...]] = ((), ())
    if k:
        th, ta = sum(tot_h) or 1.0, sum(tot_a) or 1.0
        shares = (tuple(x / th for x in tot_h), tuple(x / ta for x in tot_a))
    last: dict[int, int] = {}
    for r in before:
        last[r.home_id] = r.ts
        last[r.away_id] = r.ts
    model = ScoreModel(sport, book, 6.0, shares,
                       params if params is not None else SimParams(), last)
    if window:
        # the spread around today's expectation split by the shares - an
        # approximation (the book has moved on since), measured not assumed
        within = cross = 0.0
        n_within = n_cross = 0
        for r in window:
            exp = model.expected(r.competition_id, r.home_id, r.away_id)
            if exp is None:
                continue
            pairs = [r.values.get(period_metric(i + 1)) for i in range(k)]
            if any(pp is None for pp in pairs):
                continue
            res1 = [pp[0] - exp[0][i] for i, pp in enumerate(pairs) if pp]
            res2 = [pp[1] - exp[1][i] for i, pp in enumerate(pairs) if pp]
            for res in (res1, res2):
                sq += sum(x * x for x in res)
                n += len(res)
                for i in range(k):
                    for j in range(i + 1, k):
                        within += res[i] * res[j]
                        n_within += 1
            for a in res1:
                for b in res2:
                    cross += a * b
                    n_cross += 1
        if n:
            model.period_sd = math.sqrt(sq / n)
            prm = model.params
            if (sport.key == "basketball" and prm.bb_game_sd is None
                    and prm.bb_fit_moments and n_within and n_cross):
                v, cw, cx = sq / n, within / n_within, cross / n_cross
                g2, u2, e2 = max(cx, 0.0), max(cw - cx, 0.0), max(v - cw, 0.0)
                model.params = dataclasses.replace(
                    prm, bb_game_sd=math.sqrt(g2), bb_team_sd=math.sqrt(u2),
                    bb_quarter_sd=math.sqrt(e2))
    return model


SPORT_KEYS = tuple(SPORTS)
