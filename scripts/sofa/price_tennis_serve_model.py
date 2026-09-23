"""Price today's tennis from a serve/return model and set it against Superbet.

A separate analysis tool. It is NOT a pipeline stage, writes nothing the
pipeline reads, and its output is a candidate list for the operator to read -
never a coupon, never a stake, never a combined price.

What it does, in order:

  1. Fits a serve/return rating on cached Sofascore point counts strictly
     before the day being priced: ``P(point | i serves to j) = sigmoid(c[g,f] +
     s_i + s_i,f - r_j - r_j,f)``, where ``g`` is gender, ``f`` the surface
     family (hard / clay / grass / other) and the ``_f`` terms are per-player
     surface deviations under their own, heavier ridge. ``parse_serve``,
     ``load_serve``, ``sigmoid`` and ``hold_probability`` are the research
     harness's (``measure_tennis_serve_model.py``); the fitter is its
     ``fit_rating`` generalised to carry the surface and gender terms.
  2. Turns the two serve-point probabilities into ONE joint distribution over
     every way the match can go - set by set, game scores and tiebreaks
     included - by exact enumeration of the hold-level model (tiebreaks are
     played point by point). Every market is read off that one distribution,
     so "wins the match" can never exceed "wins a set". A point-by-point
     Monte Carlo (``simulate_match_points``) is kept as the independent check
     that the enumeration is right; the tests hold the two together.
  3. Joins each simulated probability to a Superbet two-way price for the same
     outcome, devigs the pair with ``bet.sofa.engine.devig`` and reports model
     p, market p, odds, model EV and margin. A one-sided quote is refused.
  4. Backtests all of it (``--backtest``) before anything is read as value.

Factors that were measured and left OUT (``--tune`` reprints the numbers):

  * per-player surface deviation - worse held-out point loss than none;
    surface enters as a gender x family intercept instead;
  * recent workload (matches in the previous 3 days) - on the tuning window's
    held-out points no bucket moved the serve-point residual beyond |z| 2.2,
    in no monotone direction, for server or returner;
  * a super-tiebreak decider - of ~11,700 completed ITF singles third sets in
    the cache 28 were recorded 1-0 (0.24%), none in Challenger/ATP/WTA, so a
    regular third set is priced; a category with < 50 cached third sets is
    flagged DECIDER_FORMAT_UNMEASURED instead of assumed.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/price_tennis_serve_model.py \\
        --date 2026-09-23 --raw-dir <saved Superbet payloads> \\
        [--refetch --save-raw <dir>] [--tune] [--backtest]
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import random
import re
import sqlite3
import statistics as st
import sys
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

for _p in ("src", "."):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from rapidfuzz import fuzz  # noqa: E402

from bet.sofa.engine import devig  # noqa: E402
from scripts.sofa.measure_tennis_serve_model import (  # noqa: E402
    SideServe,
    hold_probability,
    load_serve,
    sigmoid,
)

# --------------------------------------------------------------------------
# Constants. Each one is either measured (the number and where) or a decision
# (stated as one). Nothing here is re-fitted by this script at run time.
# --------------------------------------------------------------------------

# A player is priced only when the fit saw at least this many of their serve
# points AND this many of their return points (about four matches each; the
# median match is 66 serve points a side). Below it the ridge prior is doing
# the pricing, and a prior does not know the player - LOW_DATA, excluded.
MIN_RATED_POINTS = 250

# Ridge on the base serve/return strengths. The harness chose 35 on
# games_won_for Brier. `--tune` (fit before 2026-08-15, held-out points
# 08-15..09-01 of players with >= MIN_RATED_POINTS, 23,507 points; no decay,
# no surface term) measured per-point log loss 0.67397 / 0.67315 / 0.67308 at
# 35 / 100 / 300 - flat beyond 100, so 100.
LAM = 100.0

# Match-day form. A match does not play at the rated serve-point rates: on the
# same tuning window the logit residual of each side's realised serve-point
# rate had, beyond binomial noise, variance 0.105 (home) and 0.090 (away) and
# covariance -0.044 between the two sides (n = 160 matches, both rated). The
# negative covariance is dominance - the player having a good day serves AND
# returns better. Ignoring it makes the chain think every match is closer than
# it is (P(three sets) 0.459 modelled against 0.367 realised on 1,009 matches
# before this term existed). Integrated by Gauss-Hermite quadrature: a shared
# dominance term d ~ N(0, -cov) moving the two serve logits in opposite
# directions, plus an independent term per side ~ N(0, var + cov).
#
# The measured excess also contains rating error, and the full amount
# overcorrects: on the tuning window's 297 settled matches, summed Brier over
# the fifteen score-settled markets was 3.5790 / 3.4539 / 3.4527 / 3.4631 at
# 0 / 0.5 / 0.75 / 1.0 x the measured values, and the total-games bias was
# smallest at 0.5 (+3.3 pp on over 20.5, against -3.9 pp at 1.0). Half ships.
FORM_VAR = 0.0485
FORM_COV = -0.022
# Ridge on the per-player surface deviation. Same tuning window, lam 100,
# 120-day half-life: per-point log loss 0.67306 with the deviation off against
# 0.67312 / 0.67321 at ridge 300 / 150 - a per-player surface term adds noise
# at this depth of data. So surface enters as a gender x family INTERCEPT
# (fitted tour serve-point rate: women 0.522 clay / 0.554 hard, men 0.591 clay
# / 0.603 hard, on the full fit of 2026-09-23) and the per-player term is off;
# the code keeps it so the next measurement can switch it back on.
LAM_SURFACE = math.inf
# Observation half-life in days. Same window, lam 100: 0.67315 no decay,
# 0.67306 at 120 days, 0.67318 at 45. The differences are in the fourth
# decimal - noise-level; 120 is kept as the mildest setting that is not worse.
HALF_LIFE_DAYS: float | None = 120.0
FIT_ITERS = 300
FIT_LR = 1.0

# Kickoff margin: the same 15 minutes the pipeline's one-clock gate uses.
KICKOFF_MARGIN = timedelta(minutes=15)

# Surface families. Sofascore writes one surface several ways; a generic
# "Hard" or "Clay" is the family, and the family is what the rating keys on.
SURFACE_FAMILY = {
    "Hard": "hard",
    "Hardcourt outdoor": "hard",
    "Hardcourt indoor": "hard",
    "Clay": "clay",
    "Red clay": "clay",
    "Red clay indoor": "clay",
    "Green clay": "clay",
    "Grass": "grass",
    "Carpet indoor": "other",
    "Synthetic outdoor": "other",
}
UNKNOWN_FAMILY = "unknown"

NORMAL_FINISH = 100  # Sofascore status code "Ended" - the only settleable end.


def surface_family(ground_type: str | None) -> str:
    if not ground_type:
        return UNKNOWN_FAMILY
    return SURFACE_FAMILY.get(ground_type.strip(), UNKNOWN_FAMILY)


def gender_of(category: str | None, fallback: str | None = None) -> str:
    """'M' / 'F' from Sofascore's category name, else the player's own flag."""
    cat = (category or "").lower()
    if "women" in cat or cat.startswith("wta") or "billie jean" in cat:
        return "F"
    if "men" in cat or cat in ("atp", "challenger", "davis cup"):
        return "M"
    return fallback if fallback in ("M", "F") else "M"


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PastMatch:
    event_id: int
    start_ts: int
    home_id: int
    away_id: int
    home_name: str
    away_name: str
    gender: str
    ground_type: str | None
    category: str
    tournament: str
    status_code: int | None
    winner_code: int | None
    sets: tuple[tuple[int, int, bool], ...]  # (home games, away games, tiebreak)

    @property
    def family(self) -> str:
        return surface_family(self.ground_type)

    @property
    def completed(self) -> bool:
        return self.status_code == NORMAL_FINISH and len(self.sets) >= 2


def _sets_from_score(
    home: dict[str, Any], away: dict[str, Any]
) -> tuple[tuple[int, int, bool], ...]:
    out: list[tuple[int, int, bool]] = []
    for k in range(1, 6):
        key = f"period{k}"
        if key not in home or key not in away:
            break
        try:
            gh, ga = int(home[key]), int(away[key])
        except (TypeError, ValueError):
            break
        tb = f"period{k}TieBreak" in home or {gh, ga} == {7, 6}
        out.append((gh, ga, tb))
    return tuple(out)


def load_history(db: str) -> dict[int, PastMatch]:
    """Every cached singles tennis event, one row per event id."""
    con = sqlite3.connect(db)
    out: dict[int, PastMatch] = {}
    rows = con.execute(
        "select events_json from sofa_entity_events where events_json like '%tennis%'"
    )
    for (ej,) in rows:
        try:
            doc = json.loads(ej)
        except (TypeError, ValueError):
            continue
        events = doc.get("events") if isinstance(doc, dict) else doc
        if not isinstance(events, list):
            continue
        for e in events:
            t = e.get("tournament") or {}
            cat = t.get("category") or {}
            if (cat.get("sport") or {}).get("slug") != "tennis":
                continue
            home, away = e.get("homeTeam") or {}, e.get("awayTeam") or {}
            # type 1 is a singles player; doubles pairs are type 2.
            if home.get("type") != 1 or away.get("type") != 1:
                continue
            eid = e.get("id")
            if not isinstance(eid, int) or not e.get("startTimestamp"):
                continue
            status = e.get("status") or {}
            prev = out.get(eid)
            if prev is not None and prev.status_code == NORMAL_FINISH:
                continue
            out[eid] = PastMatch(
                event_id=eid,
                start_ts=int(e["startTimestamp"]),
                home_id=int(home["id"]),
                away_id=int(away["id"]),
                home_name=str(home.get("name") or ""),
                away_name=str(away.get("name") or ""),
                gender=gender_of(cat.get("name"), home.get("gender")),
                ground_type=e.get("groundType"),
                category=str(cat.get("name") or ""),
                tournament=str(t.get("name") or ""),
                status_code=status.get("code"),
                winner_code=e.get("winnerCode"),
                sets=_sets_from_score(
                    e.get("homeScore") or {}, e.get("awayScore") or {}
                ),
            )
    return out


@dataclass(frozen=True)
class Obs:
    server: int
    returner: int
    family: str
    gender: str
    won: int
    played: int
    weight: float
    start_ts: int


def build_observations(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    before_ts: int,
    half_life_days: float | None = None,
) -> list[Obs]:
    """Two serve observations per clean match that started before `before_ts`.

    A retirement still carries real points served, so it is kept for the
    rating; it is only excluded from settlement.
    """
    out: list[Obs] = []
    for eid, sides in serve.items():
        m = history.get(eid)
        if m is None or m.start_ts >= before_ts:
            continue
        age_days = (before_ts - m.start_ts) / 86400.0
        w = 1.0 if half_life_days is None else 0.5 ** (age_days / half_life_days)
        h, a = sides["home"], sides["away"]
        out.append(
            Obs(
                m.home_id,
                m.away_id,
                m.family,
                m.gender,
                h.serve_won,
                h.serve_played,
                w,
                m.start_ts,
            )
        )
        out.append(
            Obs(
                m.away_id,
                m.home_id,
                m.family,
                m.gender,
                a.serve_won,
                a.serve_played,
                w,
                m.start_ts,
            )
        )
    return out


# --------------------------------------------------------------------------
# Rating
# --------------------------------------------------------------------------


@dataclass
class Rating:
    s: dict[int, float]
    r: dict[int, float]
    ds: dict[tuple[int, str], float]
    dr: dict[tuple[int, str], float]
    c: dict[tuple[str, str], float]
    served: dict[int, float]
    returned: dict[int, float]
    c_global: float

    def intercept(self, gender: str, family: str) -> float:
        if (gender, family) in self.c:
            return self.c[(gender, family)]
        same = [v for (g, _f), v in self.c.items() if g == gender]
        return st.mean(same) if same else self.c_global

    def p_serve(self, server: int, returner: int, gender: str, family: str) -> float:
        x = (
            self.intercept(gender, family)
            + self.s.get(server, 0.0)
            + self.ds.get((server, family), 0.0)
            - self.r.get(returner, 0.0)
            - self.dr.get((returner, family), 0.0)
        )
        return sigmoid(x)

    def points(self, player: int) -> tuple[int, int]:
        """(serve points, return points) the fit saw for this player."""
        return int(self.served.get(player, 0.0)), int(self.returned.get(player, 0.0))


def fit_surface_rating(
    obs: list[Obs],
    lam: float = LAM,
    lam_surface: float = LAM_SURFACE,
    iters: int = FIT_ITERS,
    lr: float = FIT_LR,
) -> Rating:
    """The harness's `fit_rating`, carrying a gender x surface intercept and a
    per-player surface deviation.

    The step is the harness's: each parameter's gradient normalised by its own
    (weighted) point count plus its ridge. `lr = 1` is the largest that is
    safe: the base, surface and intercept terms are updated together and are
    partly redundant, so at `lr = 2` the fit overshoots (measured 2026-09-23 on
    11,106 observations: per-point log loss 0.9580 at lr 2 against 0.6697 at
    lr 1). At lr 1 the loss is flat to 1e-6 between 300 and 600 iterations.
    `lam_surface = inf` switches the deviation off.
    """
    players = sorted({o.server for o in obs} | {o.returner for o in obs})
    idx = {p: i for i, p in enumerate(players)}
    cells = sorted({(o.gender, o.family) for o in obs})
    cidx = {c: i for i, c in enumerate(cells)}
    fam_keys = sorted(
        {(o.server, o.family) for o in obs} | {(o.returner, o.family) for o in obs}
    )
    fidx = {k: i for i, k in enumerate(fam_keys)}
    n, nf, nc = len(players), len(fam_keys), len(cells)

    enc = [
        (
            idx[o.server],
            idx[o.returner],
            fidx[(o.server, o.family)],
            fidx[(o.returner, o.family)],
            cidx[(o.gender, o.family)],
            o.won * o.weight,
            o.played * o.weight,
        )
        for o in obs
    ]
    served, returned = [0.0] * n, [0.0] * n
    fserved, freturned = [0.0] * nf, [0.0] * nf
    cplayed, cwon = [0.0] * nc, [0.0] * nc
    for i, j, fi, fj, ci, w, p in enc:
        served[i] += p
        returned[j] += p
        fserved[fi] += p
        freturned[fj] += p
        cplayed[ci] += p
        cwon[ci] += w
    c = [
        math.log(max(cwon[k], 1.0) / max(cplayed[k] - cwon[k], 1.0)) for k in range(nc)
    ]
    s, r = [0.0] * n, [0.0] * n
    ds, dr = [0.0] * nf, [0.0] * nf
    use_surface = math.isfinite(lam_surface)
    for _ in range(iters):
        gs, gr = [0.0] * n, [0.0] * n
        gds, gdr = [0.0] * nf, [0.0] * nf
        gc = [0.0] * nc
        for i, j, fi, fj, ci, w, p in enc:
            resid = w - p * sigmoid(c[ci] + s[i] + ds[fi] - r[j] - dr[fj])
            gs[i] += resid
            gr[j] -= resid
            gds[fi] += resid
            gdr[fj] -= resid
            gc[ci] += resid
        for k in range(n):
            s[k] += lr * (gs[k] - lam * s[k]) / (served[k] + lam)
            r[k] += lr * (gr[k] - lam * r[k]) / (returned[k] + lam)
        if use_surface:
            for k in range(nf):
                ds[k] += (
                    lr * (gds[k] - lam_surface * ds[k]) / (fserved[k] + lam_surface)
                )
                dr[k] += (
                    lr * (gdr[k] - lam_surface * dr[k]) / (freturned[k] + lam_surface)
                )
        for k in range(nc):
            c[k] += lr * gc[k] / max(cplayed[k], 1.0)
    total_w = sum(cwon)
    total_p = sum(cplayed)
    raw_served: dict[int, float] = defaultdict(float)
    raw_returned: dict[int, float] = defaultdict(float)
    for o in obs:
        raw_served[o.server] += o.played
        raw_returned[o.returner] += o.played
    return Rating(
        s={players[k]: s[k] for k in range(n)},
        r={players[k]: r[k] for k in range(n)},
        ds={fam_keys[k]: ds[k] for k in range(nf)},
        dr={fam_keys[k]: dr[k] for k in range(nf)},
        c={cells[k]: c[k] for k in range(nc)},
        served=dict(raw_served),
        returned=dict(raw_returned),
        c_global=math.log(max(total_w, 1.0) / max(total_p - total_w, 1.0)),
    )


def point_log_loss(rating: Rating, obs: Iterable[Obs]) -> tuple[float, int]:
    """Mean per-point log loss of a fitted rating on held-out observations."""
    total, points = 0.0, 0
    for o in obs:
        p = rating.p_serve(o.server, o.returner, o.gender, o.family)
        total -= o.won * math.log(p) + (o.played - o.won) * math.log(1 - p)
        points += o.played
    return (total / points if points else float("nan")), points


# --------------------------------------------------------------------------
# Match model: exact enumeration of the hold-level chain
# --------------------------------------------------------------------------

SetScore = tuple[int, int, bool]  # games A, games B, decided by a tiebreak
MatchPath = tuple[SetScore, ...]


def tiebreak_win_prob(
    x: float, y: float, a_serves_first: bool, target: int = 7
) -> float:
    """P(A wins a tiebreak to `target`, win by two).

    x = P(A wins a point on A's serve), y = P(A wins a point on B's serve).
    Serve order: first point by the first server, then two each. From any tie
    at or beyond target-1 all, the next two points are one on each serve, so
    the rest is a closed form: P(A wins) = xy / (xy + (1-x)(1-y)).
    """
    xy = x * y
    nn = (1 - x) * (1 - y)
    from_tie = xy / (xy + nn) if xy + nn > 0 else 0.5
    probs: dict[tuple[int, int], float] = {(0, 0): 1.0}
    win = 0.0
    for total in range(0, 2 * target - 1):
        nxt: dict[tuple[int, int], float] = defaultdict(float)
        for (i, j), pr in probs.items():
            if i + j != total:
                continue
            if i == target - 1 and j == target - 1:
                win += pr * from_tie
                continue
            first_serving = ((total + 1) // 2) % 2 == 0
            a_serving = first_serving == a_serves_first
            pa = x if a_serving else y
            for di, dj, q in ((1, 0, pa), (0, 1, 1 - pa)):
                ni, nj = i + di, j + dj
                if ni >= target and ni - nj >= 2:
                    win += pr * q
                elif nj >= target and nj - ni >= 2:
                    pass
                else:
                    nxt[(ni, nj)] += pr * q
        probs = dict(nxt)
        if not probs:
            break
    return win


def set_distribution(
    pa: float, pb: float, a_serves_first: bool
) -> dict[SetScore, float]:
    """Final score of one standard set (tiebreak at 6-6), A serving first."""
    ha, hb = hold_probability(pa), hold_probability(pb)
    out: dict[SetScore, float] = defaultdict(float)
    probs: dict[tuple[int, int], float] = {(0, 0): 1.0}
    while probs:
        nxt: dict[tuple[int, int], float] = defaultdict(float)
        for (ga, gb), pr in probs.items():
            if ga == 6 and gb == 6:
                p_tb = tiebreak_win_prob(pa, 1 - pb, a_serves_first)
                out[(7, 6, True)] += pr * p_tb
                out[(6, 7, True)] += pr * (1 - p_tb)
                continue
            a_serving = ((ga + gb) % 2 == 0) == a_serves_first
            q = ha if a_serving else 1 - hb  # P(A wins this game)
            for na, nb, w in ((ga + 1, gb, q), (ga, gb + 1, 1 - q)):
                if (na >= 6 and na - nb >= 2) or (nb >= 6 and nb - na >= 2):
                    out[(na, nb, False)] += pr * w
                else:
                    nxt[(na, nb)] += pr * w
        probs = dict(nxt)
    return dict(out)


def match_tiebreak_distribution(
    pa: float, pb: float, a_serves_first: bool
) -> dict[SetScore, float]:
    """A deciding match tiebreak to ten, recorded 1-0 the way Sofascore does."""
    p = tiebreak_win_prob(pa, 1 - pb, a_serves_first, target=10)
    return {(1, 0, True): p, (0, 1, True): 1 - p}


@dataclass(frozen=True)
class MatchDistribution:
    """Every path a match can take, with its probability. One object, so every
    market read off it is consistent with every other."""

    paths: tuple[tuple[float, MatchPath], ...]
    pa: float
    pb: float
    best_of: int
    super_tb_decider: bool

    def prob(self, predicate: Callable[[MatchPath], bool]) -> float:
        return sum(p for p, path in self.paths if predicate(path))

    def expect(self, value: Callable[[MatchPath], float]) -> float:
        return sum(p * value(path) for p, path in self.paths)


def match_distribution(
    pa: float, pb: float, best_of: int = 3, super_tb_decider: bool = False
) -> MatchDistribution:
    """Exact joint distribution over set-by-set paths.

    The first server is unknown before the toss, so the result is the even
    mixture of both. Within a match the next set's first server follows from
    the parity of games played (a tiebreak counts as one game) - which is the
    rule, and it matters for set-2 game counts.
    """
    need = best_of // 2 + 1
    cache: dict[tuple[bool, bool], dict[SetScore, float]] = {}

    def dist(a_first: bool, decider: bool) -> dict[SetScore, float]:
        key = (a_first, decider and super_tb_decider)
        if key not in cache:
            cache[key] = (
                match_tiebreak_distribution(pa, pb, a_first)
                if key[1]
                else set_distribution(pa, pb, a_first)
            )
        return cache[key]

    acc: dict[MatchPath, float] = defaultdict(float)

    def walk(path: MatchPath, prob: float, wa: int, wb: int, a_first: bool) -> None:
        if wa == need or wb == need:
            acc[path] += prob
            return
        decider = wa == need - 1 and wb == need - 1
        for score, q in dist(a_first, decider).items():
            ga, gb, _tb = score
            nxt_first = a_first if (ga + gb) % 2 == 0 else not a_first
            walk(path + (score,), prob * q, wa + (ga > gb), wb + (gb > ga), nxt_first)

    walk((), 0.5, 0, 0, True)
    walk((), 0.5, 0, 0, False)
    return MatchDistribution(
        tuple(sorted(((p, k) for k, p in acc.items()), key=lambda t: t[1])),
        pa,
        pb,
        best_of,
        super_tb_decider,
    )


# Probabilists' Gauss-Hermite nodes and weights: E[f(Z)], Z ~ N(0, 1).
GH3 = ((-math.sqrt(3.0), 1 / 6), (0.0, 2 / 3), (math.sqrt(3.0), 1 / 6))
GH5 = (
    (-2.856970013872806, 0.011257411327721),
    (-1.355626179974266, 0.222075922005613),
    (0.0, 0.533333333333333),
    (1.355626179974266, 0.222075922005613),
    (2.856970013872806, 0.011257411327721),
)


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def form_mixture(
    pa: float,
    pb: float,
    var: float = FORM_VAR,
    cov: float = FORM_COV,
    best_of: int = 3,
    super_tb_decider: bool = False,
) -> MatchDistribution:
    """The match distribution integrated over match-day form.

    (u, v) are the logit shifts of A's and B's serve-point rate, with
    var(u) = var(v) = `var` and cov(u, v) = `cov`: u = d + e_a, v = -d + e_b.
    With var = cov = 0 this is exactly `match_distribution`.
    """
    var_d = max(-cov, 0.0)
    var_e = max(var - var_d, 0.0)
    sd_d, sd_e = math.sqrt(var_d), math.sqrt(var_e)
    nodes_d = GH5 if sd_d > 0 else ((0.0, 1.0),)
    nodes_e = GH3 if sd_e > 0 else ((0.0, 1.0),)
    la, lb = _logit(pa), _logit(pb)
    acc: dict[MatchPath, float] = defaultdict(float)
    for zd, wd in nodes_d:
        for za, wa in nodes_e:
            for zb, wb in nodes_e:
                w = wd * wa * wb
                qa = sigmoid(la + sd_d * zd + sd_e * za)
                qb = sigmoid(lb - sd_d * zd + sd_e * zb)
                for p, path in match_distribution(
                    qa, qb, best_of, super_tb_decider
                ).paths:
                    acc[path] += w * p
    return MatchDistribution(
        tuple(sorted(((p, k) for k, p in acc.items()), key=lambda t: t[1])),
        pa,
        pb,
        best_of,
        super_tb_decider,
    )


def simulate_match_points(
    pa: float, pb: float, sims: int, seed: int, best_of: int = 3
) -> list[MatchPath]:
    """Point-by-point Monte Carlo of the same match. Independent of the exact
    enumerator on purpose - it is the check that the enumerator is right."""
    rnd = random.Random(seed)
    need = best_of // 2 + 1
    out: list[MatchPath] = []
    for _ in range(sims):
        a_serving = rnd.random() < 0.5
        path: list[SetScore] = []
        wa = wb = 0
        while wa < need and wb < need:
            ga = gb = 0
            tb = False
            while True:
                if ga == 6 and gb == 6:
                    tb = True
                    ta = tbb = 0
                    k = 0
                    first = a_serving
                    while True:
                        srv_first = ((k + 1) // 2) % 2 == 0
                        a_srv = srv_first == first
                        p_point = pa if a_srv else 1 - pb
                        if rnd.random() < p_point:
                            ta += 1
                        else:
                            tbb += 1
                        k += 1
                        if (ta >= 7 or tbb >= 7) and abs(ta - tbb) >= 2:
                            break
                    if ta > tbb:
                        ga += 1
                    else:
                        gb += 1
                    a_serving = not a_serving
                    break
                # P(A wins the point), whoever serves; pw counts A's points.
                p_point = pa if a_serving else 1 - pb
                pw = qw = 0
                while True:
                    if rnd.random() < p_point:
                        pw += 1
                    else:
                        qw += 1
                    if pw >= 4 and pw - qw >= 2:
                        a_game = True
                        break
                    if qw >= 4 and qw - pw >= 2:
                        a_game = False
                        break
                if a_game:
                    ga += 1
                else:
                    gb += 1
                a_serving = not a_serving
                if (ga >= 6 and ga - gb >= 2) or (gb >= 6 and gb - ga >= 2):
                    break
            path.append((ga, gb, tb))
            wa += ga > gb
            wb += gb > ga
        out.append(tuple(path))
    return out


# --------------------------------------------------------------------------
# Markets: one key per outcome, one evaluator over the distribution
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """One selection, in the model's terms.

    kind      - winner | set_winner | wins_a_set | straight_sets | sets_total |
                games_total | player_games | set_games | set_player_games |
                handicap_games | set_handicap_games | tiebreaks
    player    - 0 for the Sofascore home side, 1 for away, None if n/a
    line      - total line, or the selection's OWN handicap
    over      - OVER / "yes" when True
    set_no    - 1-based set number where the market is per-set
    """

    kind: str
    player: int | None = None
    line: float | None = None
    over: bool = True
    set_no: int | None = None

    def pair_key(self) -> tuple[Any, ...]:
        """Identifies the two-way market this outcome belongs to."""
        if self.kind in ("winner", "set_winner"):
            return (self.kind, self.set_no)
        if self.kind in ("handicap_games", "set_handicap_games"):
            assert self.line is not None and self.player is not None
            home_line = self.line if self.player == 0 else -self.line
            return (self.kind, self.set_no, home_line)
        return (self.kind, self.player, self.line, self.set_no)


def _games(path: MatchPath, player: int) -> int:
    return sum(s[player] for s in path)


def _sets_won(path: MatchPath, player: int) -> int:
    return sum(1 for s in path if s[player] > s[1 - player])


def outcome_value(path: MatchPath, o: Outcome) -> float | None:
    """1 win, 0 loss, 0.5 push (a whole line hit exactly); None if undecided."""

    def over_under(v: float) -> float:
        assert o.line is not None
        if v == o.line:
            return 0.5
        return float((v > o.line) == o.over)

    if o.kind == "winner":
        assert o.player is not None
        return float(_sets_won(path, o.player) > _sets_won(path, 1 - o.player))
    if o.kind == "set_winner":
        assert o.player is not None and o.set_no is not None
        if len(path) < o.set_no:
            return None  # the set was not played: Superbet voids it
        s = path[o.set_no - 1]
        return float(s[o.player] > s[1 - o.player])
    if o.kind == "wins_a_set":
        assert o.player is not None
        return float((_sets_won(path, o.player) >= 1) == o.over)
    if o.kind == "straight_sets":
        assert o.player is not None
        straight = _sets_won(path, 1 - o.player) == 0
        return float(straight == o.over)
    if o.kind == "sets_total":
        return over_under(len(path))
    if o.kind == "games_total":
        return over_under(_games(path, 0) + _games(path, 1))
    if o.kind == "player_games":
        assert o.player is not None
        return over_under(_games(path, o.player))
    if o.kind == "tiebreaks":
        return over_under(sum(1 for s in path if s[2]))
    if o.kind in ("set_games", "set_player_games", "set_handicap_games"):
        assert o.set_no is not None
        if len(path) < o.set_no:
            return None
        s = path[o.set_no - 1]
        if o.kind == "set_games":
            return over_under(s[0] + s[1])
        assert o.player is not None
        if o.kind == "set_player_games":
            return over_under(s[o.player])
        margin = s[o.player] - s[1 - o.player] + (o.line or 0.0)
        return 0.5 if margin == 0 else float(margin > 0)
    if o.kind == "handicap_games":
        assert o.player is not None and o.line is not None
        margin = _games(path, o.player) - _games(path, 1 - o.player) + o.line
        return 0.5 if margin == 0 else float(margin > 0)
    raise ValueError(f"unknown outcome kind {o.kind}")


@dataclass(frozen=True)
class OutcomeProb:
    p_win: float
    p_push: float
    p_void: float

    @property
    def p_settled_win(self) -> float:
        """P(win | the bet is not voided) - what a devigged price estimates."""
        live = 1.0 - self.p_void
        return self.p_win / live if live > 0 else 0.0


def outcome_probability(dist: MatchDistribution, o: Outcome) -> OutcomeProb:
    win = push = void = 0.0
    for p, path in dist.paths:
        v = outcome_value(path, o)
        if v is None:
            void += p
        elif v == 0.5:
            push += p
        else:
            win += p * v
    return OutcomeProb(win, push, void)


def model_ev(prob: OutcomeProb, odds: float) -> float:
    """Expected return per unit staked. A push returns the stake, a void too."""
    return prob.p_win * odds + prob.p_push + prob.p_void - 1.0


# --------------------------------------------------------------------------
# Superbet: market name -> Outcome, then two-way pairs
# --------------------------------------------------------------------------


def fold(text: str | None) -> str:
    """Lower-case, strip diacritics (incl. the Polish l), squash spaces."""
    t = (text or "").lower().replace("ł", "l").replace("·", " ")
    t = "".join(
        c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", t).strip()


_NUM = r"[+-]?\d+(?:\.\d+)?"
_OVER = ("powyzej",)
_UNDER = ("ponizej",)
_YES = ("tak",)
_NO = ("nie",)


def _ou(name: str) -> tuple[bool, float] | None:
    m = re.match(rf"^(powyzej|ponizej)\s+({_NUM})$", fold(name))
    if not m:
        return None
    return m.group(1) in _OVER, float(m.group(2))


def _yes_no(name: str) -> bool | None:
    f = fold(name)
    if f in _YES:
        return True
    if f in _NO:
        return False
    return None


def _player_in(text: str, names: tuple[str, str]) -> tuple[int, str] | None:
    """Which of the two (Superbet) names `text` starts with, and the remainder.

    Longest name first, so "Anna Lee" never shadows "Anna Leeds".
    """
    f = fold(text)
    order = sorted(range(2), key=lambda k: -len(fold(names[k])))
    for k in order:
        nm = fold(names[k])
        if nm and f.startswith(nm):
            return k, f[len(nm) :].strip()
    return None


_SET_PREFIX = re.compile(r"^(\d)\.\s*set\s*-\s*(.+)$")
_HCP_SEL = re.compile(rf"^(.+?)\s*\(({_NUM})\)$")


def parse_outcome(odd: dict[str, Any], sb_names: tuple[str, str]) -> Outcome | None:
    """Map one Superbet odds item to an Outcome, in SUPERBET side order
    (player 0 = first name in matchName). None for any market this model does
    not price - multi-way, combinations, serve-game props, aces.

    `sb_names` are the names as Superbet writes them in this event; the
    market name carries them verbatim ("Jan Kowalski liczba gemow").
    """
    market = str(odd.get("marketName") or "")
    name = str(odd.get("name") or "")
    if ";" in market or "&" in market:
        return None  # a SUPERBETS combination - never priced here
    fm = fold(market)

    if fm == "zwyciezca":
        code = str(odd.get("code") or name)
        if code in ("1", "2"):
            return Outcome("winner", player=int(code) - 1)
        who = _player_in(str(odd.get("info") or ""), sb_names)
        return Outcome("winner", player=who[0]) if who else None
    if fm == "x. set - zwyciezca":
        m = _SET_PREFIX.match(fold(name))
        if not m:
            return None
        who = _player_in(m.group(2), sb_names)
        if not who or who[1]:
            return None
        return Outcome("set_winner", player=who[0], set_no=int(m.group(1)))
    if fm == "liczba setow":
        ou = _ou(name)
        return Outcome("sets_total", line=ou[1], over=ou[0]) if ou else None
    if fm == "liczba gemow":
        ou = _ou(name)
        return Outcome("games_total", line=ou[1], over=ou[0]) if ou else None
    if fm == "liczba tiebreakow":
        ou = _ou(name)
        return Outcome("tiebreaks", line=ou[1], over=ou[0]) if ou else None
    if fm == "handicap gemy":
        m = _HCP_SEL.match(fold(name))
        if not m:
            return None
        who = _player_in(m.group(1), sb_names)
        if not who or who[1]:
            return None
        return Outcome("handicap_games", player=who[0], line=float(m.group(2)))

    sm = _SET_PREFIX.match(fm)
    if sm:
        set_no, rest = int(sm.group(1)), sm.group(2)
        if rest == "liczba gemow":
            ou = _ou(name)
            return (
                Outcome("set_games", line=ou[1], over=ou[0], set_no=set_no)
                if ou
                else None
            )
        if rest == "handicap gemy":
            m = _HCP_SEL.match(fold(name))
            if not m:
                return None
            who = _player_in(m.group(1), sb_names)
            if not who or who[1]:
                return None
            return Outcome(
                "set_handicap_games",
                player=who[0],
                line=float(m.group(2)),
                set_no=set_no,
            )
        who = _player_in(rest, sb_names)
        if who and who[1] == "liczba gemow":
            ou = _ou(name)
            return (
                Outcome(
                    "set_player_games",
                    player=who[0],
                    line=ou[1],
                    over=ou[0],
                    set_no=set_no,
                )
                if ou
                else None
            )
        return None

    who = _player_in(market, sb_names)
    if who is None:
        return None
    player, rest = who
    if rest == "liczba gemow":
        ou = _ou(name)
        return (
            Outcome("player_games", player=player, line=ou[1], over=ou[0])
            if ou
            else None
        )
    if rest == "wygra seta":
        yn = _yes_no(name)
        return Outcome("wins_a_set", player=player, over=yn) if yn is not None else None
    if rest == "wygra bez straty seta":
        yn = _yes_no(name)
        return (
            Outcome("straight_sets", player=player, over=yn) if yn is not None else None
        )
    return None


def reorient(o: Outcome, swap: bool) -> Outcome:
    """Superbet side order -> Sofascore side order."""
    if not swap or o.player is None:
        return o
    return Outcome(o.kind, 1 - o.player, o.line, o.over, o.set_no)


@dataclass(frozen=True)
class Quote:
    outcome: Outcome
    odds: float
    label: str
    market_name: str


@dataclass(frozen=True)
class PricedPair:
    a: Quote
    b: Quote
    p_a: float  # devigged market probability of a
    p_b: float
    margin: float  # overround: 1/oa + 1/ob - 1


def pair_two_way(quotes: list[Quote]) -> tuple[list[PricedPair], list[Quote]]:
    """Group quotes into two-way markets and devig each complete pair.

    Returns (pairs, refused). A quote whose other side is missing, suspended or
    not a real price is refused - there is nothing to devig it against, and a
    one-sided price must never be read as a probability.
    """
    groups: dict[tuple[Any, ...], list[Quote]] = defaultdict(list)
    for q in quotes:
        groups[q.outcome.pair_key()].append(q)
    pairs: list[PricedPair] = []
    refused: list[Quote] = []
    for members in groups.values():
        if len(members) != 2:
            refused.extend(members)
            continue
        a, b = members
        if not _complements(a.outcome, b.outcome):
            refused.extend(members)
            continue
        pv = devig(a.odds, b.odds)
        if pv is None:
            refused.extend(members)
            continue
        pairs.append(PricedPair(a, b, pv[0], pv[1], 1 / a.odds + 1 / b.odds - 1))
    return pairs, refused


def _complements(x: Outcome, y: Outcome) -> bool:
    if x.kind != y.kind:
        return False
    if x.kind in ("winner", "set_winner", "handicap_games", "set_handicap_games"):
        return x.player is not None and y.player is not None and x.player != y.player
    return x.over != y.over


def quotes_from_payload(
    payload: dict[str, Any], swap: bool
) -> tuple[list[Quote], tuple[str, str]]:
    """Every active, parseable odds item of one Superbet event."""
    names_raw = str(payload.get("matchName") or "").split("·")
    if len(names_raw) != 2:
        return [], ("", "")
    sb_names = (names_raw[0].strip(), names_raw[1].strip())
    out: list[Quote] = []
    for odd in payload.get("odds") or []:
        if odd.get("status") != "active":
            continue
        try:
            price = float(odd.get("price"))
        except (TypeError, ValueError):
            continue
        if price <= 1.0:
            continue
        o = parse_outcome(odd, sb_names)
        if o is None:
            continue
        out.append(
            Quote(
                reorient(o, swap),
                price,
                str(odd.get("name")),
                str(odd.get("marketName")),
            )
        )
    return out, sb_names


def superbet_swapped(sb_names: tuple[str, str], home: str, away: str) -> bool | None:
    """Is Superbet's first name the Sofascore AWAY player? None if unclear."""

    def sim(a: str, b: str) -> float:
        return float(fuzz.token_set_ratio(fold(a), fold(b)))

    straight = sim(sb_names[0], home) + sim(sb_names[1], away)
    crossed = sim(sb_names[0], away) + sim(sb_names[1], home)
    if max(straight, crossed) < 140 or abs(straight - crossed) < 20:
        return None
    return crossed > straight


# --------------------------------------------------------------------------
# Kickoff
# --------------------------------------------------------------------------


def _ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def earliest_kickoff(fixture: dict[str, Any]) -> datetime | None:
    """The earlier of Sofascore's and Superbet's clocks - the one gate."""
    clocks = [
        c
        for c in (
            _ts(fixture.get("kickoff_utc")),
            _ts(fixture.get("superbet_kickoff_utc")),
        )
        if c is not None
    ]
    return min(clocks) if clocks else None


def is_pre_match(
    fixture: dict[str, Any], now: datetime, margin: timedelta = KICKOFF_MARGIN
) -> bool:
    ko = earliest_kickoff(fixture)
    return ko is not None and ko > now + margin


# --------------------------------------------------------------------------
# Pricing one match
# --------------------------------------------------------------------------


@dataclass
class PlayerRead:
    entity_id: int
    name: str
    serve_points: int
    return_points: int
    low_data: bool


@dataclass
class MatchRead:
    pa: float
    pb: float
    home: PlayerRead
    away: PlayerRead
    family: str
    gender: str
    flags: list[str] = field(default_factory=list)


def read_match(
    rating: Rating,
    home_id: int,
    away_id: int,
    home_name: str,
    away_name: str,
    gender: str,
    family: str,
    min_points: int = MIN_RATED_POINTS,
) -> MatchRead:
    def player(pid: int, name: str) -> PlayerRead:
        sp, rp = rating.points(pid)
        return PlayerRead(pid, name, sp, rp, min(sp, rp) < min_points)

    return MatchRead(
        pa=rating.p_serve(home_id, away_id, gender, family),
        pb=rating.p_serve(away_id, home_id, gender, family),
        home=player(home_id, home_name),
        away=player(away_id, away_name),
        family=family,
        gender=gender,
    )


_DIST_CACHE: dict[tuple[float, float, int, bool, float, float], MatchDistribution] = {}


def cached_distribution(
    pa: float,
    pb: float,
    best_of: int = 3,
    super_tb: bool = False,
    var: float = FORM_VAR,
    cov: float = FORM_COV,
) -> MatchDistribution:
    key = (round(pa, 4), round(pb, 4), best_of, super_tb, var, cov)
    if key not in _DIST_CACHE:
        _DIST_CACHE[key] = form_mixture(key[0], key[1], var, cov, best_of, super_tb)
    return _DIST_CACHE[key]


def describe(o: Outcome, home: str, away: str) -> str:
    who = {0: home, 1: away}.get(o.player if o.player is not None else -1, "")
    ou = "over" if o.over else "under"
    yn = "yes" if o.over else "no"
    sn = f"set {o.set_no} " if o.set_no else ""
    return {
        "winner": f"{who} wins match",
        "set_winner": f"{who} wins {sn}".strip(),
        "wins_a_set": f"{who} wins a set: {yn}",
        "straight_sets": f"{who} wins without dropping a set: {yn}",
        "sets_total": f"sets {ou} {o.line}",
        "games_total": f"total games {ou} {o.line}",
        "player_games": f"{who} games {ou} {o.line}",
        "set_games": f"{sn}games {ou} {o.line}",
        "set_player_games": f"{sn}{who} games {ou} {o.line}",
        "handicap_games": f"{who} games handicap {o.line:+}"
        if o.line is not None
        else "",
        "set_handicap_games": (
            f"{sn}{who} games handicap {o.line:+}" if o.line is not None else ""
        ),
        "tiebreaks": f"tiebreaks {ou} {o.line}",
    }[o.kind]


FAMILY_OF_KIND = {
    "winner": "winner",
    "set_winner": "set_winner",
    "wins_a_set": "wins_a_set",
    "straight_sets": "straight_sets",
    "sets_total": "sets_total",
    "games_total": "games_total",
    "player_games": "player_games",
    "set_games": "set_games",
    "set_player_games": "set_player_games",
    "handicap_games": "handicap_games",
    "set_handicap_games": "set_handicap_games",
    "tiebreaks": "tiebreaks",
}


def price_rows(
    dist: MatchDistribution, pairs: list[PricedPair], home: str, away: str
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair in pairs:
        for q, p_mkt in ((pair.a, pair.p_a), (pair.b, pair.p_b)):
            prob = outcome_probability(dist, q.outcome)
            rows.append(
                {
                    "family": FAMILY_OF_KIND[q.outcome.kind],
                    "market": q.market_name,
                    "selection": q.label,
                    "reads_as": describe(q.outcome, home, away),
                    "odds": q.odds,
                    "model_p": round(prob.p_settled_win, 4),
                    "model_p_push": round(prob.p_push, 4),
                    "model_p_void": round(prob.p_void, 4),
                    "market_p": round(p_mkt, 4),
                    "margin": round(pair.margin, 4),
                    "model_ev": round(model_ev(prob, q.odds), 4),
                    "disagreement_pp": round(100 * (prob.p_settled_win - p_mkt), 2),
                }
            )
    return rows


# --------------------------------------------------------------------------
# Backtest
# --------------------------------------------------------------------------


def brier(pairs: list[tuple[float, float]]) -> float:
    return st.mean((p - y) ** 2 for p, y in pairs) if pairs else float("nan")


# Fixed-line markets settled from the Sofascore score, in home-side terms.
SCORE_MARKETS: list[tuple[str, Outcome]] = [
    ("winner", Outcome("winner", player=0)),
    ("set_winner (set 1)", Outcome("set_winner", player=0, set_no=1)),
    ("sets_total over 2.5", Outcome("sets_total", line=2.5, over=True)),
    ("home wins a set", Outcome("wins_a_set", player=0, over=True)),
    ("home straight sets", Outcome("straight_sets", player=0, over=True)),
    ("games_total over 20.5", Outcome("games_total", line=20.5)),
    ("games_total over 22.5", Outcome("games_total", line=22.5)),
    ("home games over 10.5", Outcome("player_games", player=0, line=10.5)),
    ("home games over 12.5", Outcome("player_games", player=0, line=12.5)),
    ("home handicap -3.5", Outcome("handicap_games", player=0, line=-3.5)),
    ("home handicap +3.5", Outcome("handicap_games", player=0, line=3.5)),
    ("set 1 games over 8.5", Outcome("set_games", line=8.5, set_no=1)),
    ("set 1 games over 9.5", Outcome("set_games", line=9.5, set_no=1)),
    (
        "set 1 home games over 4.5",
        Outcome("set_player_games", player=0, line=4.5, set_no=1),
    ),
    ("tiebreaks over 0.5", Outcome("tiebreaks", line=0.5)),
]


def weekly_cuts(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    out = []
    t = start
    while t < end:
        out.append((t, min(t + timedelta(days=7), end)))
        t += timedelta(days=7)
    return out


def backtest_score(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    start: datetime,
    end: datetime,
    min_points: int,
    lam_surface: float,
    half_life: float | None,
) -> dict[str, Any]:
    """Rolling weekly cut: fit on everything before the week, score the week.

    Scores the model and a flat reference (the same match model with every
    player set to the gender x surface intercept - what the chain knows with
    no player information). A model that does not beat the flat reference
    knows nothing about the players.
    """
    scored: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    calib: list[tuple[float, float]] = []
    n_matches = 0
    for lo, hi in weekly_cuts(start, end):
        obs = build_observations(history, serve, int(lo.timestamp()), half_life)
        if not obs:
            continue
        rating = fit_surface_rating(obs, lam_surface=lam_surface)
        for m in history.values():
            if not (int(lo.timestamp()) <= m.start_ts < int(hi.timestamp())):
                continue
            if not m.completed or len(m.sets) > 3:
                continue
            read = read_match(
                rating,
                m.home_id,
                m.away_id,
                m.home_name,
                m.away_name,
                m.gender,
                m.family,
                min_points,
            )
            if read.home.low_data or read.away.low_data:
                continue
            n_matches += 1
            dist = cached_distribution(read.pa, read.pb)
            c0 = sigmoid(rating.intercept(m.gender, m.family))
            flat = cached_distribution(c0, c0)
            real: MatchPath = m.sets
            for label, o in SCORE_MARKETS:
                y = outcome_value(real, o)
                if y is None or y == 0.5:
                    continue
                pm = outcome_probability(dist, o).p_settled_win
                pf = outcome_probability(flat, o).p_settled_win
                scored[label].append((pm, pf, y))
                if label == "winner":
                    calib.append((pm, y))
    table = []
    for label, _o in SCORE_MARKETS:
        rows = scored[label]
        if not rows:
            continue
        table.append(
            {
                "market": label,
                "family": FAMILY_OF_KIND[_o.kind],
                "n": len(rows),
                "base_rate": round(st.mean(r[2] for r in rows), 4),
                "brier_model": round(brier([(r[0], r[2]) for r in rows]), 4),
                "brier_flat": round(brier([(r[1], r[2]) for r in rows]), 4),
                "mean_model_p": round(st.mean(r[0] for r in rows), 4),
            }
        )
    buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for p, y in calib:
        # Fold to the favourite so the table reads 0.5 -> 1.0.
        pf, yf = (p, y) if p >= 0.5 else (1 - p, 1 - y)
        buckets[min(int(pf * 10), 9)].append((pf, yf))
    calibration = [
        {
            "bucket": f"{b / 10:.1f}-{(b + 1) / 10:.1f}",
            "n": len(v),
            "mean_p": round(st.mean(x[0] for x in v), 4),
            "hit": round(st.mean(x[1] for x in v), 4),
        }
        for b, v in sorted(buckets.items())
    ]
    return {
        "window": [start.date().isoformat(), end.date().isoformat()],
        "matches": n_matches,
        "markets": table,
        "winner_calibration_favourite_side": calibration,
    }


# Pipeline market -> the Outcome builder, for the historical priced rungs.
def _priced_outcome(
    market: str, player: int | None, line: float, over: bool
) -> Outcome | None:
    if market == "games_total":
        return Outcome("games_total", line=line, over=over)
    if market == "sets_total":
        return Outcome("sets_total", line=line, over=over)
    if market == "tiebreaks_total":
        return Outcome("tiebreaks", line=line, over=over)
    if market == "games_won_for" and player is not None:
        return Outcome("player_games", player=player, line=line, over=over)
    if market == "handicap_games" and player is not None:
        return Outcome("handicap_games", player=player, line=line)
    return None


PRICED_FAMILY = {
    "games_total": "games_total",
    "sets_total": "sets_total",
    "tiebreaks_total": "tiebreaks",
    "games_won_for": "player_games",
    "handicap_games": "handicap_games",
}
DISAGREEMENT_BUCKETS = [(0.0, 3.0), (3.0, 6.0), (6.0, 10.0), (10.0, 100.0)]


def _side_of(subject: str, home: str, away: str) -> int | None:
    sh = fuzz.token_set_ratio(fold(subject), fold(home))
    sa = fuzz.token_set_ratio(fold(subject), fold(away))
    if max(sh, sa) < 70 or abs(sh - sa) < 10:
        return None
    return 0 if sh > sa else 1


def backtest_priced(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    runs_dir: Path,
    db: str,
    days: list[str],
    min_points: int,
    lam_surface: float,
    half_life: float | None,
) -> dict[str, Any]:
    """Model vs Superbet's own price, on the days sofa recorded one.

    Price: the day's 04_offer.json rung (both sides, or the paired opposite
    handicap), kept only if it was fetched BEFORE the earlier kickoff clock -
    an in-play price is not a pre-match price. Outcome: sofa_settled_row.
    Fit: everything before 00:00 UTC of that day.
    """
    con = sqlite3.connect(db)
    outcome: dict[tuple[int, str, str, float, str], str] = {}
    for eid, market, subject, line, direction, res in con.execute(
        "select sofascore_event_id, market, subject, line, direction, outcome "
        "from sofa_settled_row where sport='tennis' and run_date in "
        f"({','.join('?' * len(days))})",
        days,
    ):
        outcome[(eid, market, subject, float(line), direction)] = res
    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)
    for day in days:
        try:
            fixtures = {
                f["sofascore_event_id"]: f
                for f in json.loads((runs_dir / day / "02_fixtures.json").read_text())
            }
            offer = json.loads((runs_dir / day / "04_offer.json").read_text())
        except OSError:
            continue
        cut = int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())
        rating = fit_surface_rating(
            build_observations(history, serve, cut, half_life), lam_surface=lam_surface
        )
        for entry in offer:
            fx = fixtures.get(entry["sofascore_event_id"])
            if not fx or fx.get("sport") != "tennis":
                continue
            ko = earliest_kickoff(fx)
            eid = int(fx["sofascore_event_id"])
            m = history.get(eid)
            gender = m.gender if m else gender_of(fx.get("category_name"))
            family = surface_family(fx.get("ground_type"))
            read = read_match(
                rating,
                int(fx["home_entity_id"]),
                int(fx["away_entity_id"]),
                fx["home_name"],
                fx["away_name"],
                gender,
                family,
                min_points,
            )
            low = read.home.low_data or read.away.low_data
            dist = cached_distribution(read.pa, read.pb)
            handicaps: dict[tuple[int, float], tuple[float, str]] = {}
            plain: list[tuple[str, int | None, float, float, float, str]] = []
            for rung in entry.get("rungs") or []:
                market = rung["market"]
                if market not in PRICED_FAMILY:
                    continue
                fetched = _ts(rung.get("fetched_at_utc"))
                if ko is None or fetched is None or fetched >= ko:
                    skipped["in_play_or_unknown_clock"] += 1
                    continue
                subject = rung.get("subject") or ""
                player = (
                    _side_of(subject, fx["home_name"], fx["away_name"])
                    if subject
                    else None
                )
                if subject and player is None:
                    skipped["subject_unmapped"] += 1
                    continue
                if market == "handicap_games":
                    if rung.get("over_odds") and player is not None:
                        handicaps[(player, float(rung["line"]))] = (
                            float(rung["over_odds"]),
                            subject,
                        )
                    continue
                if rung.get("over_odds") and rung.get("under_odds"):
                    plain.append(
                        (
                            market,
                            player,
                            float(rung["line"]),
                            float(rung["over_odds"]),
                            float(rung["under_odds"]),
                            subject,
                        )
                    )
                else:
                    skipped["one_sided"] += 1
            legs: list[tuple[str, int | None, float, bool, float, float, str]] = []
            for market, player, line, oo, uo, subject in plain:
                pv = devig(oo, uo)
                if pv is None:
                    continue
                legs.append((market, player, line, True, oo, pv[0], subject))
                legs.append((market, player, line, False, uo, pv[1], subject))
            for (player, line), (odds, subject) in handicaps.items():
                other = handicaps.get((1 - player, -line))
                if other is None:
                    skipped["one_sided"] += 1
                    continue
                pv = devig(odds, other[0])
                if pv is None:
                    continue
                legs.append(
                    ("handicap_games", player, line, True, odds, pv[0], subject)
                )
            for market, player, line, over, odds, p_mkt, subject in legs:
                res = outcome.get(
                    (eid, market, subject, line, "OVER" if over else "UNDER")
                )
                if res not in ("WIN", "LOSS"):
                    skipped["no_settlement"] += 1
                    continue
                o = _priced_outcome(market, player, line, over)
                if o is None:
                    continue
                prob = outcome_probability(dist, o)
                y = 1.0 if res == "WIN" else 0.0
                rows.append(
                    {
                        "day": day,
                        "event": eid,
                        "family": PRICED_FAMILY[market],
                        "model_p": prob.p_settled_win,
                        "market_p": p_mkt,
                        "odds": odds,
                        "y": y,
                        "low_data": low,
                        "ev": model_ev(prob, odds),
                    }
                )
    return summarise_priced(rows, dict(skipped))


def summarise_priced(
    rows: list[dict[str, Any]], skipped: dict[str, int]
) -> dict[str, Any]:
    def block(sel: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(sel),
            "matches": len({r["event"] for r in sel}),
            "brier_model": round(brier([(r["model_p"], r["y"]) for r in sel]), 4),
            "brier_market": round(brier([(r["market_p"], r["y"]) for r in sel]), 4),
        }

    def roi(sel: list[dict[str, Any]]) -> dict[str, Any]:
        if not sel:
            return {"n": 0}
        ret = sum(r["odds"] * r["y"] - 1 for r in sel)
        mean = ret / len(sel)
        # Rungs of one match are not independent bets (a ladder settles
        # together), so the standard error is clustered on the match.
        per_match: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for r in sel:
            acc = per_match[r["event"]]
            acc[0] += r["odds"] * r["y"] - 1
            acc[1] += 1
        se = math.sqrt(
            sum((v[0] - mean * v[1]) ** 2 for v in per_match.values())
        ) / len(sel)
        return {
            "n": len(sel),
            "matches": len(per_match),
            "roi_se_clustered": round(se, 4),
            "hit": round(st.mean(r["y"] for r in sel), 4),
            "mean_model_p": round(st.mean(r["model_p"] for r in sel), 4),
            "mean_market_p": round(st.mean(r["market_p"] for r in sel), 4),
            "mean_odds": round(st.mean(r["odds"] for r in sel), 3),
            "roi": round(ret / len(sel), 4),
        }

    rated = [r for r in rows if not r["low_data"]]
    families = sorted({r["family"] for r in rows})
    out: dict[str, Any] = {
        "skipped": skipped,
        "all_rows": block(rows),
        "rated_rows": block(rated),
        "by_family": {},
        "ev_positive_by_disagreement": {},
        "ev_positive_by_family": {},
    }
    for fam in families:
        out["by_family"][fam] = block([r for r in rated if r["family"] == fam])
    pos = [r for r in rated if r["ev"] > 0]
    for lo, hi in DISAGREEMENT_BUCKETS:
        sel = [r for r in pos if lo <= 100 * (r["model_p"] - r["market_p"]) < hi]
        out["ev_positive_by_disagreement"][f"{lo:g}-{hi:g}pp"] = roi(sel)
    out["ev_positive_by_disagreement"]["all"] = roi(pos)
    for fam in families:
        out["ev_positive_by_family"][fam] = roi([r for r in pos if r["family"] == fam])
    out["all_rated_rows_flat_stake_roi"] = roi(rated)
    return out


# --------------------------------------------------------------------------
# Diagnostics that decide which factors ship
# --------------------------------------------------------------------------


def tune(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    cut: datetime,
    until: datetime,
) -> list[dict[str, Any]]:
    """Held-out per-point log loss for the few settings worth comparing.

    Run on a window that ENDS before the backtest window starts, so the
    settings the backtest scores were not chosen on the backtest.
    """
    lo, hi = int(cut.timestamp()), int(until.timestamp())
    held: list[Obs] = [
        o for o in build_observations(history, serve, hi) if o.start_ts >= lo
    ]
    out = []
    for lam in (35.0, 100.0, 300.0):
        for lam_s in (math.inf, 300.0, 150.0):
            for hl in (None, 120.0, 45.0):
                rating = fit_surface_rating(
                    build_observations(history, serve, lo, hl),
                    lam=lam,
                    lam_surface=lam_s,
                )
                known = [
                    o
                    for o in held
                    if min(rating.points(o.server)) >= MIN_RATED_POINTS
                    and min(rating.points(o.returner)) >= MIN_RATED_POINTS
                ]
                ll_all, n_all = point_log_loss(rating, held)
                ll_known, n_known = point_log_loss(rating, known)
                out.append(
                    {
                        "lam": lam,
                        "lam_surface": _finite(lam_s),
                        "half_life_days": hl,
                        "logloss_all": round(ll_all, 5),
                        "points_all": n_all,
                        "logloss_rated": round(ll_known, 5),
                        "points_rated": n_known,
                    }
                )
    return out


def _finite(x: float) -> float | str:
    return x if math.isfinite(x) else "inf"


def form_noise(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    cut: datetime,
    until: datetime,
    rating: Rating,
    min_points: int = MIN_RATED_POINTS,
) -> dict[str, Any]:
    """Excess (beyond binomial) variance and covariance of the two sides'
    serve-point logit residuals, on matches after `cut` - FORM_VAR / FORM_COV."""
    lo, hi = int(cut.timestamp()), int(until.timestamp())
    ea: list[float] = []
    eb: list[float] = []
    na: list[float] = []
    nb: list[float] = []
    for eid, sides in serve.items():
        m = history.get(eid)
        if m is None or not (lo <= m.start_ts < hi):
            continue
        if min(rating.points(m.home_id)) < min_points:
            continue
        if min(rating.points(m.away_id)) < min_points:
            continue
        pa = rating.p_serve(m.home_id, m.away_id, m.gender, m.family)
        pb = rating.p_serve(m.away_id, m.home_id, m.gender, m.family)
        a, b = sides["home"], sides["away"]
        ea.append(_logit((a.serve_won + 0.5) / (a.serve_played + 1)) - _logit(pa))
        eb.append(_logit((b.serve_won + 0.5) / (b.serve_played + 1)) - _logit(pb))
        na.append(1 / (a.serve_played * pa * (1 - pa)))
        nb.append(1 / (b.serve_played * pb * (1 - pb)))
    if len(ea) < 30:
        return {"n": len(ea)}
    return {
        "n": len(ea),
        "excess_var_home": round(st.pvariance(ea) - st.mean(na), 4),
        "excess_var_away": round(st.pvariance(eb) - st.mean(nb), 4),
        "cov": round(st.covariance(ea, eb), 4),
    }


def workload_check(
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    cut: datetime,
    until: datetime,
    rating: Rating,
) -> dict[str, Any]:
    """Does 'matches played in the previous 3 days' move serve-point results
    beyond what the rating already predicts? Residual per point by bucket,
    for the server's workload and the returner's, with a z-score."""
    lo, hi = int(cut.timestamp()), int(until.timestamp())
    by_player: dict[int, list[int]] = defaultdict(list)
    for m in history.values():
        if m.status_code in (NORMAL_FINISH, None) or m.sets:
            by_player[m.home_id].append(m.start_ts)
            by_player[m.away_id].append(m.start_ts)
    for v in by_player.values():
        v.sort()

    def load(pid: int, ts: int) -> int:
        v = by_player.get(pid, [])
        return bisect.bisect_left(v, ts) - bisect.bisect_left(v, ts - 3 * 86400)

    held = [o for o in build_observations(history, serve, hi) if o.start_ts >= lo]
    res: dict[str, dict[int, list[float]]] = {
        "server": defaultdict(lambda: [0.0, 0.0, 0.0]),
        "returner": defaultdict(lambda: [0.0, 0.0, 0.0]),
    }
    for o in held:
        p = rating.p_serve(o.server, o.returner, o.gender, o.family)
        for role, pid in (("server", o.server), ("returner", o.returner)):
            b = min(load(pid, o.start_ts), 3)
            acc = res[role][b]
            acc[0] += o.won - o.played * p
            acc[1] += o.played
            acc[2] += o.played * p * (1 - p)
    out: dict[str, Any] = {}
    for role, table in res.items():
        out[role] = {
            f"{b}{'+' if b == 3 else ''}_in_prior_3d": {
                "points": int(v[1]),
                "resid_pp": round(100 * v[0] / v[1], 3) if v[1] else None,
                "z": round(v[0] / math.sqrt(v[2]), 2) if v[2] else None,
            }
            for b, v in sorted(table.items())
        }
    return out


def super_tiebreak_rate(history: dict[int, PastMatch]) -> dict[str, list[int]]:
    """Per category: [third sets played, of which recorded as a 1-0 match tiebreak]."""
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for m in history.values():
        if m.status_code != NORMAL_FINISH or len(m.sets) < 3:
            continue
        acc = out[m.category]
        acc[0] += 1
        ga, gb, _ = m.sets[2]
        if max(ga, gb) == 1 and min(ga, gb) == 0:
            acc[1] += 1
    return dict(out)


def family_caveats(
    score_bt: dict[str, Any] | None, priced_bt: dict[str, Any] | None
) -> dict[str, str]:
    """One plain sentence per market family: what the backtest says about it."""
    out: dict[str, str] = {}
    score_by_fam: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in (score_bt or {}).get("markets", []):
        score_by_fam[row["family"]].append(row)
    priced = (priced_bt or {}).get("by_family", {})
    ev_pos = (priced_bt or {}).get("ev_positive_by_family", {})
    for fam in sorted(set(FAMILY_OF_KIND.values())):
        parts: list[str] = []
        if fam in priced and priced[fam].get("n"):
            b, e = priced[fam], ev_pos.get(fam, {})
            verdict = (
                "LOSES to the price"
                if b["brier_model"] > b["brier_market"]
                else "beats the price"
            )
            parts.append(
                f"vs Superbet: model Brier {b['brier_model']} vs devigged "
                f"{b['brier_market']} ({verdict}; n={b['n']} rungs, "
                f"{b['matches']} matches)"
            )
            if e.get("n"):
                parts.append(
                    f"EV>0 rows realised ROI {e['roi']:+.3f} "
                    f"(clustered se {e['roi_se_clustered']}, n={e['n']}, "
                    f"{e['matches']} matches)"
                )
        else:
            parts.append(
                "NO PRICE HISTORY - never compared with Superbet; EV here is untested"
            )
        for row in score_by_fam.get(fam, []):
            parts.append(
                f"score-only '{row['market']}': Brier {row['brier_model']} vs "
                f"flat {row['brier_flat']} (n={row['n']})"
            )
        if fam not in score_by_fam and fam not in priced:
            parts.append("not backtested at all")
        out[fam] = "; ".join(parts)
    for label, b in (priced_bt or {}).get("ev_positive_by_disagreement", {}).items():
        if label == "all":
            continue
        if not b.get("n"):
            out[BUCKET_KEY + label] = f"no backtested EV>0 row fell in {label}"
            continue
        out[BUCKET_KEY + label] = (
            f"EV>0 rows with disagreement {label} realised ROI {b['roi']:+.3f} "
            f"(clustered se {b['roi_se_clustered']}, n={b['n']}, "
            f"{b['matches']} matches; hit {b['hit']} vs model {b['mean_model_p']} "
            f"vs market {b['mean_market_p']})"
        )
    return out


BUCKET_KEY = "__disagreement__"


def bucket_label(disagreement_pp: float) -> str:
    for lo, hi in DISAGREEMENT_BUCKETS:
        if lo <= disagreement_pp < hi:
            return f"{lo:g}-{hi:g}pp"
    return "below 0pp"


# --------------------------------------------------------------------------
# Today
# --------------------------------------------------------------------------


def load_payloads(
    raw_dirs: list[Path],
    fixtures: list[dict[str, Any]],
    refetch: bool,
    sleep_s: float = 1.05,
    save_dir: Path | None = None,
) -> dict[str, tuple[dict[str, Any], str]]:
    """superbet id -> (payload, fetched_at). Saved payloads first; with
    --refetch, Superbet is asked again - sequentially, one request per second,
    under stage MARKET_SCOUT, and only for fixtures still before kickoff."""
    out: dict[str, tuple[dict[str, Any], str]] = {}
    for raw_dir in raw_dirs:  # a later directory overrides an earlier one
        if not raw_dir.is_dir():
            continue
        for fn in raw_dir.glob("*.json"):
            try:
                doc = json.loads(fn.read_text())
            except (OSError, ValueError):
                continue
            if isinstance(doc, dict) and isinstance(doc.get("payload"), dict):
                mtime = datetime.fromtimestamp(fn.stat().st_mtime, UTC).isoformat()
                out[fn.stem] = (doc["payload"], mtime)
    if refetch:
        from bet.sofa.stage import set_stage
        from bet.sofa.superbet import SuperbetClient

        set_stage("MARKET_SCOUT")
        client = SuperbetClient()
        for fx in fixtures:
            for sid in fx.get("superbet_event_ids") or []:
                t0 = time.monotonic()
                try:
                    payload = client.event_odds(sid)
                except Exception as exc:  # noqa: BLE001 - a scout keeps going
                    print(f"  refetch {sid}: {type(exc).__name__}", file=sys.stderr)
                    payload = None
                if isinstance(payload, dict) and payload.get("odds"):
                    out[str(sid)] = (payload, datetime.now(UTC).isoformat())
                    if save_dir is not None:
                        save_dir.mkdir(parents=True, exist_ok=True)
                        doc = {
                            "fixture": {"sid": fx["sofascore_event_id"]},
                            "payload": payload,
                        }
                        (save_dir / f"{sid}.json").write_text(json.dumps(doc))
                wait = sleep_s - (time.monotonic() - t0)
                if wait > 0:
                    time.sleep(wait)
    return out


def price_day(
    date: str,
    runs_dir: Path,
    history: dict[int, PastMatch],
    serve: dict[int, dict[str, SideServe]],
    payloads: dict[str, tuple[dict[str, Any], str]],
    now: datetime,
    min_points: int,
    lam_surface: float,
    half_life: float | None,
    stb_rates: dict[str, list[int]],
    caveats: dict[str, str] | None = None,
) -> dict[str, Any]:
    fixtures = [
        f
        for f in json.loads((runs_dir / date / "02_fixtures.json").read_text())
        if f.get("sport") == "tennis"
    ]
    cut = int(datetime.fromisoformat(date).replace(tzinfo=UTC).timestamp())
    obs = build_observations(history, serve, cut, half_life)
    rating = fit_surface_rating(obs, lam_surface=lam_surface)
    matches: list[dict[str, Any]] = []
    skipped: dict[str, int] = defaultdict(int)
    for fx in fixtures:
        ko = earliest_kickoff(fx)
        if not is_pre_match(fx, now):
            skipped["kickoff_within_15min_or_started"] += 1
            continue
        if "/" in fx["home_name"] or "/" in fx["away_name"]:
            skipped["doubles"] += 1
            continue
        found = [
            (sid, payloads[sid])
            for sid in fx.get("superbet_event_ids") or []
            if sid in payloads
        ]
        if not found:
            skipped["no_superbet_payload"] += 1
            continue
        sid, (payload, fetched_at) = found[0]
        names_raw = str(payload.get("matchName") or "").split("·")
        if len(names_raw) != 2:
            skipped["unreadable_match_name"] += 1
            continue
        swap = superbet_swapped(
            (names_raw[0].strip(), names_raw[1].strip()),
            fx["home_name"],
            fx["away_name"],
        )
        if swap is None:
            skipped["superbet_names_do_not_match_fixture"] += 1
            continue
        quotes, sb_names = quotes_from_payload(payload, swap)
        pairs, refused = pair_two_way(quotes)
        home_id, away_id = int(fx["home_entity_id"]), int(fx["away_entity_id"])
        gender = gender_of(fx.get("category_name"))
        family = surface_family(fx.get("ground_type"))
        read = read_match(
            rating,
            home_id,
            away_id,
            fx["home_name"],
            fx["away_name"],
            gender,
            family,
            min_points,
        )
        flags = []
        if family == UNKNOWN_FAMILY:
            flags.append("SURFACE_UNKNOWN")
        if family == "other":
            flags.append("SURFACE_OTHER_THIN")
        cat = fx.get("category_name") or ""
        third, stb = stb_rates.get(cat, [0, 0])
        if third < 50:
            flags.append("DECIDER_FORMAT_UNMEASURED")
        elif stb / third > 0.05:
            flags.append("DECIDER_MAY_BE_SUPER_TIEBREAK")
        best_of = int(fx.get("default_period_count") or 3)
        dist = cached_distribution(read.pa, read.pb, best_of)
        rows = price_rows(dist, pairs, fx["home_name"], fx["away_name"])
        low = read.home.low_data or read.away.low_data
        matches.append(
            {
                "sofascore_event_id": fx["sofascore_event_id"],
                "superbet_event_id": sid,
                "prices_fetched_at": fetched_at,
                "match": f"{fx['home_name']} - {fx['away_name']}",
                "competition": fx.get("competition_name"),
                "category": cat,
                "kickoff_utc": ko.isoformat() if ko else None,
                "ground_type": fx.get("ground_type"),
                "surface_family": family,
                "gender": gender,
                "best_of": best_of,
                "players": [vars(read.home), vars(read.away)],
                "low_data": low,
                "flags": flags,
                "p_serve_point": [round(read.pa, 4), round(read.pb, 4)],
                "p_hold": [
                    round(hold_probability(read.pa), 4),
                    round(hold_probability(read.pb), 4),
                ],
                "model_summary": {
                    "p_home_wins": round(
                        outcome_probability(dist, Outcome("winner", player=0)).p_win, 4
                    ),
                    "expected_games": round(
                        dist.expect(lambda p: _games(p, 0) + _games(p, 1)), 2
                    ),
                    "p_three_sets": round(dist.prob(lambda p: len(p) == 3), 4),
                },
                "refused_one_sided": len(refused),
                "rows": rows,
            }
        )
    candidates = []
    for m in matches:
        if m["low_data"]:
            continue
        for r in m["rows"]:
            if r["model_ev"] > 0:
                candidates.append(
                    {
                        "match": m["match"],
                        "kickoff_utc": m["kickoff_utc"],
                        "competition": m["competition"],
                        "surface": m["ground_type"],
                        "rated_points": [
                            (p["serve_points"], p["return_points"])
                            for p in m["players"]
                        ],
                        "flags": m["flags"],
                        **r,
                        "backtest": (caveats or {}).get(
                            r["family"], "backtest not run"
                        ),
                        "disagreement_backtest": (caveats or {}).get(
                            BUCKET_KEY + bucket_label(r["disagreement_pp"]),
                            "backtest not run",
                        ),
                    }
                )
    candidates.sort(key=lambda r: -r["model_ev"])
    return {
        "date": date,
        "now_utc": now.isoformat(),
        "fit": {
            "cut_utc": datetime.fromtimestamp(cut, UTC).isoformat(),
            "observations": len(obs),
            "points": sum(o.played for o in obs),
            "players": len(rating.s),
            "intercepts": {
                f"{g}/{f}": round(sigmoid(v), 4)
                for (g, f), v in sorted(rating.c.items())
            },
            "lam": LAM,
            "lam_surface": _finite(lam_surface),
            "half_life_days": half_life,
            "form_var": FORM_VAR,
            "form_cov": FORM_COV,
            "min_rated_points": min_points,
        },
        "skipped": dict(skipped),
        "matches_priced": len(matches),
        "matches_low_data": sum(1 for m in matches if m["low_data"]),
        "candidates": candidates,
        "matches": matches,
    }


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return out


def render_markdown(report: dict[str, Any], top: int = 40) -> str:
    """The short human read of the JSON. Everything here is in the JSON too."""
    t = report["today"]
    fit = t["fit"]
    lines = [
        f"# Tennis serve/return model vs Superbet - {t['date']}",
        "",
        "Analysis tool, not the coupon. No stake sizing, no combined prices. "
        "Model EV = model_p x odds - 1 at the quoted odds; market p is the "
        "power-devigged two-way price.",
        "",
        f"Run at {t['now_utc']}. Fit cut {fit['cut_utc']}: "
        f"{fit['observations']:,} serve observations, {fit['players']:,} players; "
        f"lam {fit['lam']}, per-player surface term {fit['lam_surface']}, "
        f"half-life {fit['half_life_days']} d, form var/cov {fit['form_var']}/"
        f"{fit['form_cov']}. LOW_DATA below {fit['min_rated_points']} rated serve "
        "AND return points.",
        "",
    ]
    bs = report.get("backtest_score")
    if bs:
        lines += [
            f"## Backtest 1 - score-settled, {bs['window'][0]}..{bs['window'][1]}, "
            f"weekly re-fit, {bs['matches']} matches (both players rated)",
            "",
            "`flat` = the same chain with every player at the tour intercept: "
            "what the model knows without player information. No price here.",
            "",
        ]
        lines += _table(
            ["market", "n", "base rate", "mean model p", "Brier model", "Brier flat"],
            [
                [
                    m["market"],
                    m["n"],
                    m["base_rate"],
                    m["mean_model_p"],
                    m["brier_model"],
                    m["brier_flat"],
                ]
                for m in bs["markets"]
            ],
        )
        lines += ["", "Winner calibration (favourite side):", ""]
        lines += _table(
            ["bucket", "n", "mean p", "hit"],
            [
                [c["bucket"], c["n"], c["mean_p"], c["hit"]]
                for c in bs["winner_calibration_favourite_side"]
            ],
        )
        lines.append("")
    bp = report.get("backtest_priced")
    if bp:
        lines += [
            "## Backtest 2 - against Superbet's own pre-match price",
            "",
            f"Skipped: {bp['skipped']}. All rows: {bp['all_rows']}. "
            f"Rated rows: {bp['rated_rows']}.",
            "",
        ]
        lines += _table(
            ["family", "n rungs", "matches", "Brier model", "Brier market"],
            [
                [f, b["n"], b["matches"], b["brier_model"], b["brier_market"]]
                for f, b in bp["by_family"].items()
            ],
        )
        lines += ["", "Rows with model EV > 0 at the offered odds, realised:", ""]
        rows: list[list[Any]] = []
        subsets = list(bp["ev_positive_by_disagreement"].items()) + [
            (f"family {f}", b) for f, b in bp["ev_positive_by_family"].items()
        ]
        for label, b in subsets:
            if not b.get("n"):
                rows.append([label, 0, "", "", "", "", "", ""])
                continue
            rows.append(
                [
                    label,
                    b["n"],
                    b["matches"],
                    b["hit"],
                    b["mean_model_p"],
                    b["mean_market_p"],
                    f"{b['roi']:+.3f}",
                    b["roi_se_clustered"],
                ]
            )
        lines += _table(
            [
                "subset",
                "n",
                "matches",
                "hit",
                "model p",
                "market p",
                "ROI",
                "se (clustered)",
            ],
            rows,
        )
        f = bp["all_rated_rows_flat_stake_roi"]
        lines += [
            "",
            f"Every rated row, both sides, flat: ROI {f['roi']:+.3f} (n={f['n']}) - "
            "that is the margin.",
            "",
        ]
    lines += [
        "## Today",
        "",
        f"Priced {t['matches_priced']} matches; {t['matches_low_data']} LOW_DATA "
        f"(excluded); skipped {t['skipped']}. {len(t['candidates'])} rows with "
        "model EV > 0 on rated matches.",
        "",
        f"Top {top} by model EV (all of them are in the JSON). Read the backtest "
        "lines below before the EV column.",
        "",
    ]
    cand_rows: list[list[Any]] = []
    for c in t["candidates"][:top]:
        cand_rows.append(
            [
                c["match"],
                (c["kickoff_utc"] or "")[11:16],
                c["surface"],
                c["reads_as"],
                c["odds"],
                c["model_p"],
                c["market_p"],
                f"{c['model_ev']:+.3f}",
                f"{c['disagreement_pp']:+.1f}",
                c["rated_points"],
                " ".join(c["flags"]) or "-",
            ]
        )
    lines += _table(
        [
            "match",
            "KO UTC",
            "surface",
            "selection",
            "odds",
            "model p",
            "market p",
            "EV",
            "diff pp",
            "rated pts (srv,ret)",
            "flags",
        ],
        cand_rows,
    )
    lines += ["", "### Backtest caveat per family and per disagreement bucket", ""]
    for fam, text in sorted(report.get("family_caveats", {}).items()):
        name = fam.replace(BUCKET_KEY, "disagreement ")
        lines.append(f"- **{name}** - {text}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--date", required=True)
    ap.add_argument("--db-path", default="data/sofa.db")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument(
        "--raw-dir",
        nargs="*",
        default=[],
        help="saved Superbet payloads {fixture, payload} per superbet id; "
        "a later directory overrides an earlier one",
    )
    ap.add_argument("--save-raw", default=None, help="write refetched payloads here")
    ap.add_argument(
        "--refetch",
        action="store_true",
        help="ask Superbet again (sequential, 1 req/s, MARKET_SCOUT)",
    )
    ap.add_argument("--now", default=None, help="ISO UTC; default: the clock")
    ap.add_argument("--min-points", type=int, default=MIN_RATED_POINTS)
    ap.add_argument("--lam-surface", type=float, default=LAM_SURFACE)
    ap.add_argument("--half-life", type=float, default=HALF_LIFE_DAYS)
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--tune", action="store_true")
    ap.add_argument(
        "--tune-start",
        default="2026-08-15",
        help="tuning window is [tune-start, backtest-start)",
    )
    ap.add_argument("--backtest-start", default="2026-09-01")
    ap.add_argument(
        "--priced-days",
        nargs="*",
        default=["2026-09-18", "2026-09-19", "2026-09-20", "2026-09-21", "2026-09-22"],
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    runs_dir = Path(args.runs_dir)
    now = _ts(args.now) if args.now else datetime.now(UTC)
    assert now is not None
    t0 = time.monotonic()
    history = load_history(args.db_path)
    serve = load_serve(args.db_path)
    print(
        f"history: {len(history):,} singles events, serve-clean {len(serve):,} "
        f"({time.monotonic() - t0:.0f}s)"
    )
    stb = super_tiebreak_rate(history)
    report: dict[str, Any] = {"super_tiebreak_third_sets_by_category": stb}

    day0 = datetime.fromisoformat(args.date).replace(tzinfo=UTC)
    if args.tune:
        cut = datetime.fromisoformat(args.tune_start).replace(tzinfo=UTC)
        until = datetime.fromisoformat(args.backtest_start).replace(tzinfo=UTC)
        report["tune"] = tune(history, serve, cut, until)
        rating = fit_surface_rating(
            build_observations(history, serve, int(cut.timestamp()), args.half_life),
            lam_surface=args.lam_surface,
        )
        report["form_noise"] = form_noise(history, serve, cut, until, rating)
        report["workload"] = workload_check(history, serve, cut, until, rating)
        print(
            json.dumps(
                {k: report[k] for k in ("tune", "form_noise", "workload")}, indent=1
            )
        )
    if args.backtest:
        start = datetime.fromisoformat(args.backtest_start).replace(tzinfo=UTC)
        report["backtest_score"] = backtest_score(
            history,
            serve,
            start,
            day0,
            args.min_points,
            args.lam_surface,
            args.half_life,
        )
        print(json.dumps(report["backtest_score"], indent=1))
        report["backtest_priced"] = backtest_priced(
            history,
            serve,
            runs_dir,
            args.db_path,
            args.priced_days,
            args.min_points,
            args.lam_surface,
            args.half_life,
        )
        print(json.dumps(report["backtest_priced"], indent=1))

    fixtures = [
        f
        for f in json.loads((runs_dir / args.date / "02_fixtures.json").read_text())
        if f.get("sport") == "tennis" and is_pre_match(f, now)
    ]
    # Only fixtures whose two players are both rated are worth a fresh price:
    # a LOW_DATA match never reaches the candidate list, so re-asking Superbet
    # for it would be traffic with no use.
    cut_ts = int(day0.timestamp())
    gate = fit_surface_rating(
        build_observations(history, serve, cut_ts, args.half_life),
        lam_surface=args.lam_surface,
    )
    fixtures = [
        f
        for f in fixtures
        if min(gate.points(int(f["home_entity_id"]))) >= args.min_points
        and min(gate.points(int(f["away_entity_id"]))) >= args.min_points
    ]
    print(f"fresh prices wanted for {len(fixtures)} rated pre-match fixtures")
    payloads = load_payloads(
        [Path(d) for d in args.raw_dir],
        fixtures,
        args.refetch,
        save_dir=Path(args.save_raw) if args.save_raw else None,
    )
    caveats = family_caveats(
        report.get("backtest_score"), report.get("backtest_priced")
    )
    report["family_caveats"] = caveats
    report["today"] = price_day(
        args.date,
        runs_dir,
        history,
        serve,
        payloads,
        now,
        args.min_points,
        args.lam_surface,
        args.half_life,
        stb,
        caveats,
    )
    out = (
        Path(args.out) if args.out else runs_dir / args.date / "tennis_serve_model.json"
    )
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str))
    out.with_suffix(".md").write_text(render_markdown(report))
    t = report["today"]
    print(
        f"priced {t['matches_priced']} matches ({t['matches_low_data']} LOW_DATA), "
        f"{len(t['candidates'])} EV>0 candidates -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
