"""A minute-by-minute football match simulator - MEASUREMENT ONLY.

Operator 2026-11-06 ("ja bym widział właśnie taki symulator minuta po
minucie"); measured in docs/sofa/evidence/football_sim_2026-11-06.md by
scripts/sofa/measure_football_sim.py. Nothing in the pipeline imports this
module (test ``test_no_pipeline_stage_reads_the_simulator``), there is no
switch in bet.sofa.epochs and nothing is installed.

What it is, in order (the tennis point model of 11-05 is the template:
bet.sofa.tennis_point_model):

  1. **Goal intensities** (Dixon & Robinson 1998, a birth process with state
     dependence; Dixon & Coles 1997 / Maher 1982 for the pre-match strength).
     Side i's goal intensity in minute m of half h is

         lambda_i(m) = mu_i / 90 x profile[h, bin(m)] x exp(beta . state_i(m))

     ``mu_i`` is today's pure rating goals centre (bet.sofa.football_rating,
     read-only, the book SHEET prices from); ``profile`` a fitted time profile
     (four bins a half, the last one the half's added time); ``state_i`` the
     game state from side i's view: goal difference (trailing by 1 / by 2+,
     leading by 1 / by 2+), the same two directions again from the 70th
     minute, and a red card for / against. The multipliers are a Poisson
     regression (piecewise-exponential survival model) on the timed incident
     lists of the history before a date cut; the data are aggregated by
     covariate cell, so the fit is exact and quick.
  2. **Red cards** are a process of their own - side i's red intensity is the
     rating's card-points centre ratio x a fitted per-bin profile x a state
     multiplier - so that a simulated dismissal moves the goals (and a
     ``red_cards`` market reads it off the same path).
  3. **Added time** of each half is drawn from the history's own distribution
     of the minutes actually played past 45 / 90 (the announced
     ``injuryTime`` length, or the last incident's ``addedTime`` when it ran
     later).
  4. **Per-half counts** (corners, card points, fouls, shots, shots on
     target) are not timed in Sofascore's payloads (only half totals), so
     they are modelled per half: side i's mean in half h is the rating's half
     centre x exp(gamma . state fractions), the fractions being the share of
     that simulated half side i spent trailing / leading / with a red card
     for / against - a log-linear model fitted on the history's half totals
     against the real paths. Dispersion: negative binomial per side and half
     with a shared gamma frailty per side and metric across the two halves
     (the measured covariance of a side's 1H and 2H residuals).
  5. **Simulation** (``simulate``): N paths per match (seed = event id),
     minute by minute; every market of one match - path markets (HT/FT,
     result per half, a goal in both halves, first goal, the higher-scoring
     half), the singles SHEET already prices and any pair of legs (a builder)
     - is read off the same paths, so they can never contradict each other.

Pure: no I/O except ``load_minute_history`` (read-only SQLite).
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

from bet.sofa.metrics import (
    _is_staff_card,
    calculate_cards_points_by_half,
    extract_flat_statistics,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.int64]
BoolArray = npt.NDArray[np.bool_]

# --------------------------------------------------------------------------
# Data: one finished match's timed path
# --------------------------------------------------------------------------

REGULAR_MINUTES = 45  # per half
RED_CLASSES = frozenset({"red", "yellowRed"})
# The per-half count metrics the simulator reads (football_rating base metric
# of the half where it exists; the second half of fouls / shots / shots on
# target is the match value minus the first half's).
COUNT_METRICS: tuple[str, ...] = (
    "corners",
    "cards_points",
    "fouls",
    "shots",
    "shots_on_target",
)


@dataclass(frozen=True)
class MinuteMatch:
    """One finished match: its timed goals and red cards in regular time, the
    added time of each half and the half totals of the count metrics.

    Minutes are 0-based minutes of a half: Sofascore's ``time`` 1..45 is
    minute 0..44 of the first half, 46..90 minute 0..44 of the second; an
    added-time incident (``time`` 45 / 90, ``addedTime`` a >= 1) is minute
    44 + a. ``side`` 0 = home, 1 = away (the side whose score went up, read
    off the running score, so an own goal counts for the side credited)."""

    event_id: int
    ts: int
    competition_id: int
    home_id: int
    away_id: int
    women: bool
    ft: tuple[int, int]  # regular-time goals (the listing's 90-minute score)
    ht: tuple[int, int] | None  # first-half goals; None: not in the listing
    goals: tuple[tuple[int, int, int], ...] | None  # (half, minute, side)
    reds: tuple[tuple[int, int, int], ...] | None  # None: not a full feed
    # minutes played past 45 / 90: max(announced injuryTime, last addedTime);
    # None when the list announces nothing for that half
    added: tuple[int | None, int | None]
    # metric -> ((home 1H, away 1H), (home 2H, away 2H))
    halves: Mapping[str, tuple[tuple[float, float], tuple[float, float]]] = field(
        default_factory=dict
    )


def _num(x: Any) -> float | None:
    if isinstance(x, int | float) and not isinstance(x, bool):
        return float(x)
    return None


def incident_slot(inc: Mapping[str, Any]) -> tuple[int, int] | None:
    """(half, 0-based minute of the half) of a regular-time incident; None
    for extra time, a card outside play (``time`` < 1) or no time."""
    t = _num(inc.get("time"))
    if t is None or t < 1 or t > 90:
        return None
    added = _num(inc.get("addedTime")) or 0.0
    if added >= 900:  # the period marker's 999
        added = 0.0
    if t <= 45:
        half, base = 1, int(t) - 1
    else:
        half, base = 2, int(t) - 46
    if added > 0 and int(t) in (45, 90):
        base = REGULAR_MINUTES - 1 + int(added)
    return half, base


def _listed(incidents: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw = (incidents or {}).get("incidents")
    if not isinstance(raw, list):
        return []
    return [i for i in raw if isinstance(i, dict)]


def is_extra_time_list(incidents: Mapping[str, Any] | None) -> bool:
    """Did the incident list run past 90 minutes (extra time)?"""
    for inc in _listed(incidents):
        t = _num(inc.get("time"))
        if t is not None and t > 90:
            return True
        if inc.get("incidentType") == "period" and inc.get("text") in (
            "ET",
            "AET",
            "PEN",
        ):
            return True
    return False


def read_timed_goals(
    incidents: Mapping[str, Any] | None,
    ft: tuple[int, int],
) -> tuple[tuple[int, int, int], ...] | None:
    """Every regular-time goal as (half, minute, side), or None when the list
    does not add up to the 90-minute score ``ft`` (a goal without a time or a
    running score, a running score that skips, a list that ends elsewhere)."""
    listed = _listed(incidents)
    if not listed:
        return None
    raw: list[tuple[tuple[int, int], int, int]] = []
    for g in listed:
        if g.get("incidentType") != "goal" or g.get("rescinded", False):
            continue
        t = _num(g.get("time"))
        if t is not None and t > 90:
            continue  # extra time
        slot = incident_slot(g)
        hs, as_ = g.get("homeScore"), g.get("awayScore")
        if slot is None or not isinstance(hs, int) or not isinstance(as_, int):
            return None
        raw.append((slot, hs, as_))
    raw.sort(key=lambda x: (x[0], x[1] + x[2]))
    if len(raw) != ft[0] + ft[1]:
        return None
    out: list[tuple[int, int, int]] = []
    prev = (0, 0)
    for (half, minute), hs, as_ in raw:
        if (hs, as_) == (prev[0] + 1, prev[1]):
            side = 0
        elif (hs, as_) == (prev[0], prev[1] + 1):
            side = 1
        else:
            return None
        prev = (hs, as_)
        out.append((half, minute, side))
    if prev != ft:
        return None
    return tuple(out)


def read_timed_reds(
    incidents: Mapping[str, Any] | None,
) -> tuple[tuple[int, int, int], ...] | None:
    """Regular-time dismissals (straight red or second yellow) as (half,
    minute, side); None when the list is not a full feed (no substitution:
    the lower-league feeds carry goals and some dismissals only)."""
    listed = _listed(incidents)
    if not any(i.get("incidentType") == "substitution" for i in listed):
        return None
    out: list[tuple[int, int, int]] = []
    for inc in listed:
        if (
            inc.get("incidentType") != "card"
            or inc.get("incidentClass") not in RED_CLASSES
            or inc.get("rescinded", False)
            or _is_staff_card(inc)
        ):
            continue
        slot = incident_slot(inc)
        if slot is None:
            continue
        out.append((slot[0], slot[1], 0 if inc.get("isHome") else 1))
    return tuple(sorted(out))


def read_added_time(
    incidents: Mapping[str, Any] | None,
) -> tuple[int | None, int | None]:
    """Minutes played past 45 / 90 per half: the announced ``injuryTime``
    length, raised to the last incident's ``addedTime`` when play ran later;
    None for a half with no announcement."""
    announced: dict[int, int] = {}
    latest: dict[int, int] = {1: 0, 2: 0}
    for inc in _listed(incidents):
        t = _num(inc.get("time"))
        if inc.get("incidentType") == "injuryTime":
            length = _num(inc.get("length"))
            if t is not None and length is not None and length >= 0:
                half = 1 if t <= 45 else 2 if t <= 90 else 0
                if half:
                    announced[half] = max(announced.get(half, 0), int(length))
            continue
        if inc.get("incidentType") == "period":
            continue
        added = _num(inc.get("addedTime"))
        if t is None or added is None or added <= 0 or added >= 900:
            continue
        if int(t) == 45:
            latest[1] = max(latest[1], int(added))
        elif int(t) == 90:
            latest[2] = max(latest[2], int(added))
    return (
        max(announced[1], latest[1]) if 1 in announced else None,
        max(announced[2], latest[2]) if 2 in announced else None,
    )


def _pair(
    values: Mapping[str, tuple[float, float]], key: str
) -> tuple[float, float] | None:
    v = values.get(key)
    if v is None:
        return None
    return float(v[0]), float(v[1])


def half_values(
    values: Mapping[str, tuple[float, float]],
    cards_by_half: tuple[tuple[float, float], tuple[float, float]] | None,
) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    """metric -> ((home 1H, away 1H), (home 2H, away 2H)) from a parsed
    football_rating result's values; a negative second half (a provider
    correction) is no value."""
    out: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    c1, c2 = _pair(values, "corners_1h_for"), _pair(values, "corners_2h_for")
    if c1 is not None and c2 is not None:
        out["corners"] = (c1, c2)
    for metric in ("fouls", "shots", "shots_on_target"):
        first, whole = _pair(values, f"{metric}_1h_for"), _pair(values, f"{metric}_for")
        if first is None or whole is None:
            continue
        second = (whole[0] - first[0], whole[1] - first[1])
        if min(second) < 0:
            continue
        out[metric] = (first, second)
    if cards_by_half is not None:
        out["cards_points"] = cards_by_half
    return out


def read_minute_match(
    result: Any,
    statistics: Mapping[str, Any] | None,
    incidents: Mapping[str, Any] | None,
) -> MinuteMatch | None:
    """A football_rating.FootballResult plus its cached payloads as a timed
    path; None when the result has no 90-minute score."""
    values: Mapping[str, tuple[float, float]] = result.values
    goals = values.get("goals_for")
    if goals is None:
        return None
    ft = (int(goals[0]), int(goals[1]))
    first = values.get("goals_1h_for")
    ht = (int(first[0]), int(first[1])) if first is not None else None
    timed = read_timed_goals(incidents, ft)
    if (
        timed is not None
        and ht is not None
        and (
            sum(1 for g in timed if g[0] == 1 and g[2] == 0),
            sum(1 for g in timed if g[0] == 1 and g[2] == 1),
        )
        != ht
    ):
        timed = None  # the incident halves contradict the listing's period1
    extra = is_extra_time_list(incidents)
    cards = None
    if incidents and not extra:
        flat = extract_flat_statistics(dict(statistics) if statistics else None)
        by_half = calculate_cards_points_by_half(dict(incidents), flat.get("ALL"))
        if isinstance(by_half, tuple):
            cards = by_half
    return MinuteMatch(
        event_id=int(result.event_id),
        ts=int(result.ts),
        competition_id=int(result.competition_id),
        home_id=int(result.home_id),
        away_id=int(result.away_id),
        women=bool(result.women),
        ft=ft,
        ht=ht,
        goals=timed,
        reds=None if extra else read_timed_reds(incidents),
        added=(None, None) if extra else read_added_time(incidents),
        halves={} if extra else half_values(values, cards),
    )


def load_minute_history(
    db_path: str | Path,
    history: Sequence[Any],
    since_ts: int = 0,
) -> list[MinuteMatch]:
    """Timed paths of the football_rating history's matches from
    ``since_ts`` on that have a cached incident list (read-only)."""
    wanted = {int(r.event_id): r for r in history if r.ts >= since_ts}
    out: list[MinuteMatch] = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA busy_timeout = 60000")
    try:
        for eid, s_json, i_json in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE incidents_json IS NOT NULL"
        ):
            r = wanted.get(int(eid))
            if r is None or getattr(r, "awarded", False):
                continue
            try:
                inc = json.loads(i_json) if i_json else None
                stats = json.loads(s_json) if s_json else None
            except ValueError:
                continue
            if not isinstance(inc, dict) or not inc:
                continue
            m = read_minute_match(r, stats if isinstance(stats, dict) else None, inc)
            if m is not None:
                out.append(m)
    finally:
        conn.close()
    out.sort(key=lambda m: (m.ts, m.event_id))
    return out


# --------------------------------------------------------------------------
# Pre-match centres: the football rating, walk-forward (as of each match)
# --------------------------------------------------------------------------

# The rating's base metrics each simulated quantity reads: goals per side for
# the intensities (and the halves' goals for the "current" baseline), the
# corners of each half (rated, RATED_SCOPE_MARKETS) and the match centre of
# fouls / shots / shots on target / card points, split evenly between the
# halves - the per-half intercept of the count model learns the real split.
# (The first-half fouls / shots ratings exist only from 2025-10 and are too
# thin to read for a team before 2026.)
CENTRE_METRICS: tuple[str, ...] = (
    "goals_for",
    "goals_1h_for",
    "goals_2h_for",
    "corners_1h_for",
    "corners_2h_for",
    "fouls_for",
    "shots_for",
    "shots_on_target_for",
    "cards_points_for",
)


@dataclass(frozen=True)
class Centres:
    """The rating's pre-match expectations for one fixture (home, away)."""

    goals: tuple[float, float]
    # metric -> ((home 1H, away 1H), (home 2H, away 2H)); a metric the
    # rating gives no centre for is absent
    halves: Mapping[str, tuple[tuple[float, float], tuple[float, float]]]
    cards: tuple[float, float] | None  # cards_points_for (match), for reds


def centres_from(values: Mapping[str, tuple[float, float]]) -> Centres | None:
    """Centres from the rating's per-metric (home, away) expectations; None
    without a goals centre."""
    goals = values.get("goals_for")
    if goals is None:
        return None
    halves: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    c1, c2 = values.get("corners_1h_for"), values.get("corners_2h_for")
    if c1 is not None and c2 is not None and min(*c1, *c2) > 0:
        halves["corners"] = (c1, c2)
    for metric in ("fouls", "shots", "shots_on_target"):
        whole = values.get(f"{metric}_for")
        if whole is None or min(whole) <= 0:
            continue
        halves[metric] = ((whole[0] / 2, whole[1] / 2), (whole[0] / 2, whole[1] / 2))
    cards = values.get("cards_points_for")
    if cards is not None and min(cards) > 0:
        halves["cards_points"] = (
            (cards[0] / 2, cards[1] / 2),
            (cards[0] / 2, cards[1] / 2),
        )
    return Centres(
        goals=(float(goals[0]), float(goals[1])),
        halves=halves,
        cards=None if cards is None else (float(cards[0]), float(cards[1])),
    )


def walk_forward_centres(
    history: Sequence[Any],
    wanted: set[int],
    book: Any,
) -> dict[int, dict[str, tuple[float, float]]]:
    """Each wanted match's rating expectations (CENTRE_METRICS, home / away)
    from ``book`` (a fresh football_rating.RatingBook carrying the day's
    flags) BEFORE the match is learnt; matches sharing a kick-off second are
    all forecast before any of them is learnt. One pass over ``history``
    (time order)."""
    from bet.sofa.football_rating import RATED_SCOPE_MARKETS, FootballForecast

    out: dict[int, dict[str, tuple[float, float]]] = {}
    i, n = 0, len(history)
    while i < n:
        j = i
        ts = history[i].ts
        while j < n and history[j].ts == ts:
            j += 1
        for r in history[i:j]:
            if r.event_id not in wanted:
                continue
            # epochs.FOOTBALL_RATED_SCOPE (on since 2026-10-13): the
            # corners of a half and card points are rated as SHEET rates them
            fc = FootballForecast(
                book=book,
                competition_id=r.competition_id,
                home_id=r.home_id,
                away_id=r.away_id,
                rated_scope=RATED_SCOPE_MARKETS,
            )
            vals: dict[str, tuple[float, float]] = {}
            for metric in CENTRE_METRICS:
                h = fc.centre(metric, "side_a")
                a = fc.centre(metric, "side_b")
                if h is not None and a is not None:
                    vals[metric] = (float(h[0]), float(a[0]))
            out[int(r.event_id)] = vals
        for r in history[i:j]:
            book.update(r)
        i = j
    return out


# --------------------------------------------------------------------------
# Parameters (fitted by fit_params on the history before a date cut)
# --------------------------------------------------------------------------

N_BINS = 8  # four a half: minutes 0-14, 15-29, 30-44, added time
LATE_MINUTE = 25  # second-half minute 25 = the 71st minute of the match
# Goal-state covariates from the scoring side's own view.
GOAL_STATE = (
    "trail1",
    "trail2",
    "lead1",
    "lead2",
    "late_trail",
    "late_lead",
    "own_red",
    "opp_red",
)
RED_STATE = ("trail", "lead", "late")
# Per-half count covariates (fractions of the half / goals in the half).
COUNT_STATE = ("trail", "lead", "own_red", "opp_red", "goals_for", "goals_against")
MAX_ADDED = 15
# Superbet card points of a dismissal beyond the yellows already counted
# (metrics.calculate_cards_points: a straight red 2, a second-yellow
# dismissal the remainder to 3 after its first yellow, i.e. 2): card points
# are simulated as the count model's non-dismissal points + 2 per red.
RED_CARD_POINTS = 2


def minute_bin(half: int, minute: int) -> int:
    """The time-profile bin of a 0-based minute of a half."""
    within = 3 if minute >= REGULAR_MINUTES else minute // 15
    return (half - 1) * 4 + within


@dataclass(frozen=True)
class SimParams:
    """Everything the simulator reads beside the day's centres."""

    goal_profile: tuple[float, ...]  # N_BINS log multipliers of mu / 90
    goal_state: Mapping[str, float]  # GOAL_STATE -> log multiplier
    red_profile: tuple[float, ...]  # N_BINS log rates of cards centre / 90
    red_state: Mapping[str, float]  # RED_STATE -> log multiplier
    added_pmf: tuple[tuple[float, ...], tuple[float, ...]]  # P(added = k)
    # metric -> half (1 / 2) -> {"intercept", COUNT_STATE...}
    count_coef: Mapping[str, Mapping[int, Mapping[str, float]]]
    # metric -> half -> extra NB variance factor (Var = m + a m^2) left
    # after the shared frailty
    count_alpha: Mapping[str, Mapping[int, float]]
    # covariance of the log frailties, order FRAILTY_KEYS (metric, side)
    frailty_cov: tuple[tuple[float, ...], ...]
    goal_frailty: float = 0.0  # variance of a side's gamma goals frailty
    match_mean: bool = False  # rescale the intensities to mu (two passes)
    default_cards: float = 2.2  # a side's card points when no centre
    fitted_to: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "goal_profile": list(self.goal_profile),
            "goal_state": dict(self.goal_state),
            "red_profile": list(self.red_profile),
            "red_state": dict(self.red_state),
            "added_pmf": [list(self.added_pmf[0]), list(self.added_pmf[1])],
            "count_coef": {
                m: {str(h): dict(c) for h, c in v.items()}
                for m, v in self.count_coef.items()
            },
            "count_alpha": {
                m: {str(h): a for h, a in v.items()}
                for m, v in self.count_alpha.items()
            },
            "frailty_cov": [list(r) for r in self.frailty_cov],
            "goal_frailty": self.goal_frailty,
            "match_mean": self.match_mean,
            "default_cards": self.default_cards,
            "fitted_to": self.fitted_to,
        }

    @classmethod
    def from_json(cls, d: Mapping[str, Any]) -> SimParams:
        return cls(
            goal_profile=tuple(float(x) for x in d["goal_profile"]),
            goal_state={str(k): float(v) for k, v in d["goal_state"].items()},
            red_profile=tuple(float(x) for x in d["red_profile"]),
            red_state={str(k): float(v) for k, v in d["red_state"].items()},
            added_pmf=(
                tuple(float(x) for x in d["added_pmf"][0]),
                tuple(float(x) for x in d["added_pmf"][1]),
            ),
            count_coef={
                str(m): {
                    int(h): {str(k): float(x) for k, x in c.items()}
                    for h, c in v.items()
                }
                for m, v in d["count_coef"].items()
            },
            count_alpha={
                str(m): {int(h): float(a) for h, a in v.items()}
                for m, v in d["count_alpha"].items()
            },
            frailty_cov=tuple(tuple(float(x) for x in r) for r in d["frailty_cov"]),
            goal_frailty=float(d.get("goal_frailty", 0.0)),
            match_mean=bool(d.get("match_mean", False)),
            default_cards=float(d.get("default_cards", 2.2)),
            fitted_to=str(d.get("fitted_to", "")),
        )


FRAILTY_KEYS: tuple[tuple[str, int], ...] = tuple(
    (m, s) for m in COUNT_METRICS for s in (0, 1)
)


def neutral_params() -> SimParams:
    """No time profile, no state, no dispersion: independent Poisson goals at
    the centres (the reference the fitted model is measured against, and
    the tests' fixture)."""
    zero8 = tuple(0.0 for _ in range(N_BINS))
    pmf = tuple(1.0 if k == 0 else 0.0 for k in range(MAX_ADDED + 1))
    k = len(FRAILTY_KEYS)
    return SimParams(
        goal_profile=zero8,
        goal_state={s: 0.0 for s in GOAL_STATE},
        red_profile=tuple(math.log(0.01) for _ in range(N_BINS)),
        red_state={s: 0.0 for s in RED_STATE},
        added_pmf=(pmf, pmf),
        count_coef={m: {h: {"intercept": 0.0} for h in (1, 2)} for m in COUNT_METRICS},
        count_alpha={m: {1: 0.0, 2: 0.0} for m in COUNT_METRICS},
        frailty_cov=tuple(tuple(0.0 for _ in range(k)) for _ in range(k)),
    )


# --------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------


@dataclass
class SimResult:
    """N simulated matches; arrays of shape (N,) unless noted."""

    n: int
    goals: IntArray  # (2 halves, 2 sides, N)
    reds: IntArray  # (2 halves, 2 sides, N)
    first_goal: IntArray  # -1 none, 0 home, 1 away
    first_goal_minute: FloatArray  # match minute (0-based, added time inside
    #                                the half's last minute), nan if none
    last_goal: IntArray  # -1 none, 0 home, 1 away
    # metric -> (2 halves, 2 sides, N) counts; absent metric = no centre
    counts: dict[str, IntArray] = field(default_factory=dict)


def _poisson_from_uniform(u: FloatArray, lam: FloatArray) -> IntArray:
    """0 / 1 / 2 goals in one minute by inverse CDF (P(3+) < 1e-6 a minute
    at the rates football has)."""
    e = np.exp(-lam)
    c1 = e * (1.0 + lam)
    out = (u >= e).astype(np.int64)
    out += (u >= c1).astype(np.int64)
    return out


def _state_eta(
    state: Mapping[str, float],
    d: IntArray,
    late: bool,
    own_red: IntArray,
    opp_red: IntArray,
) -> FloatArray:
    eta = np.zeros(d.shape, dtype=np.float64)
    eta += state.get("trail1", 0.0) * (d == -1)
    eta += state.get("trail2", 0.0) * (d <= -2)
    eta += state.get("lead1", 0.0) * (d == 1)
    eta += state.get("lead2", 0.0) * (d >= 2)
    if late:
        eta += state.get("late_trail", 0.0) * (d < 0)
        eta += state.get("late_lead", 0.0) * (d > 0)
    eta += state.get("own_red", 0.0) * np.minimum(own_red, 2)
    eta += state.get("opp_red", 0.0) * np.minimum(opp_red, 2)
    return eta


def _red_eta(state: Mapping[str, float], d: IntArray, late: bool) -> FloatArray:
    eta = state.get("trail", 0.0) * (d < 0) + state.get("lead", 0.0) * (d > 0)
    if late:
        eta = eta + state.get("late", 0.0)
    return np.asarray(eta, dtype=np.float64)


def _draw_added(rng: np.random.Generator, pmf: Sequence[float], n: int) -> IntArray:
    p = np.asarray(pmf, dtype=np.float64)
    p = p / p.sum()
    return rng.choice(len(p), size=n, p=p).astype(np.int64)


def _goal_path(
    params: SimParams,
    base: tuple[FloatArray, FloatArray],
    red_base: tuple[float, float],
    rng: np.random.Generator,
    n: int,
) -> tuple[IntArray, IntArray, IntArray, IntArray, FloatArray, FloatArray]:
    """Goals and reds per (half, side, sim), first / last goal side, first
    goal minute, and the state fractions per (half, side, COUNT_STATE[:4],
    sim)."""
    goals = np.zeros((2, 2, n), dtype=np.int64)
    reds = np.zeros((2, 2, n), dtype=np.int64)
    first = np.full(n, -1, dtype=np.int64)
    last = np.full(n, -1, dtype=np.int64)
    first_min = np.full(n, np.nan)
    frac = np.zeros((2, 2, 4, n))
    gh = np.zeros(n, dtype=np.int64)
    ga = np.zeros(n, dtype=np.int64)
    rh = np.zeros(n, dtype=np.int64)
    ra = np.zeros(n, dtype=np.int64)
    gp = np.asarray(params.goal_profile)
    rp = np.asarray(params.red_profile)
    for half in (1, 2):
        added = _draw_added(rng, params.added_pmf[half - 1], n)
        length = REGULAR_MINUTES + added
        span = int(length.max())
        u = rng.random((span, 4, n))
        played = np.zeros(n)
        for m in range(span):
            active = m < length
            b = minute_bin(half, m)
            late = half == 2 and m >= LATE_MINUTE
            d = gh - ga
            eta_h = gp[b] + _state_eta(params.goal_state, d, late, rh, ra)
            eta_a = gp[b] + _state_eta(params.goal_state, -d, late, ra, rh)
            lam_h = base[0] * np.exp(eta_h)
            lam_a = base[1] * np.exp(eta_a)
            new_h = _poisson_from_uniform(u[m, 0], lam_h) * active
            new_a = _poisson_from_uniform(u[m, 1], lam_a) * active
            rl_h = red_base[0] * np.exp(rp[b] + _red_eta(params.red_state, d, late))
            rl_a = red_base[1] * np.exp(rp[b] + _red_eta(params.red_state, -d, late))
            red_h = ((u[m, 2] < 1.0 - np.exp(-rl_h)) & active).astype(np.int64)
            red_a = ((u[m, 3] < 1.0 - np.exp(-rl_a)) & active).astype(np.int64)
            act = active.astype(np.float64)
            played += act
            frac[half - 1, 0, 0] += act * (d < 0)
            frac[half - 1, 0, 1] += act * (d > 0)
            frac[half - 1, 0, 2] += act * (rh > 0)
            frac[half - 1, 0, 3] += act * (ra > 0)
            frac[half - 1, 1, 0] += act * (d > 0)
            frac[half - 1, 1, 1] += act * (d < 0)
            frac[half - 1, 1, 2] += act * (ra > 0)
            frac[half - 1, 1, 3] += act * (rh > 0)
            scored = (new_h + new_a) > 0
            if scored.any():
                # both in one minute: either order, half the time each
                both = (new_h > 0) & (new_a > 0)
                coin = u[m, 2] < 0.5
                who_first = np.where(new_h > 0, 0, 1)
                who_first = np.where(both & coin, 1, who_first)
                who_last = np.where(new_a > 0, 1, 0)
                who_last = np.where(both & coin, 0, who_last)
                fresh = scored & (first < 0)
                first = np.where(fresh, who_first, first)
                first_min = np.where(
                    fresh,
                    (half - 1) * REGULAR_MINUTES + min(m, REGULAR_MINUTES - 1),
                    first_min,
                )
                last = np.where(scored, who_last, last)
            gh += new_h
            ga += new_a
            rh += red_h
            ra += red_a
            goals[half - 1, 0] += new_h
            goals[half - 1, 1] += new_a
            reds[half - 1, 0] += red_h
            reds[half - 1, 1] += red_a
        frac[half - 1] /= played
    return goals, reds, first, last, first_min, frac


def _frailties(params: SimParams, rng: np.random.Generator, n: int) -> FloatArray:
    """Correlated log-normal multipliers of mean 1, shape (len(FRAILTY_KEYS), N)."""
    cov = np.asarray(params.frailty_cov, dtype=np.float64)
    k = len(FRAILTY_KEYS)
    if cov.shape != (k, k) or not np.any(cov):
        return np.ones((k, n))
    s = np.log1p(np.clip(cov, -0.5, None))
    w, v = np.linalg.eigh(s)
    w = np.clip(w, 0.0, None)
    root = v * np.sqrt(w)
    z = root @ rng.standard_normal((k, n))
    return np.asarray(np.exp(z - 0.5 * np.diag(s)[:, None]), dtype=np.float64)


def simulate(
    params: SimParams,
    centres: Centres,
    n: int = 4000,
    seed: int = 0,
) -> SimResult:
    """N paths of one match from the day's centres."""
    rng = np.random.default_rng(seed)
    mu = centres.goals
    scale = [1.0, 1.0]
    if params.match_mean:
        # one pilot pass: the intensities' mean under the fitted profile and
        # state, rescaled so each side's expected goals is its centre
        pilot_base = (np.full(1000, mu[0] / 90.0), np.full(1000, mu[1] / 90.0))
        pg, *_ = _goal_path(
            params,
            pilot_base,
            _red_base(params, centres),
            np.random.default_rng(seed + 1),
            1000,
        )
        for s in (0, 1):
            got = float(pg[:, s].sum(axis=0).mean())
            scale[s] = mu[s] / got if got > 0 else 1.0
    gf = params.goal_frailty
    base_h = np.full(n, mu[0] * scale[0] / 90.0)
    base_a = np.full(n, mu[1] * scale[1] / 90.0)
    if gf > 0:
        base_h = base_h * rng.gamma(1.0 / gf, gf, n)
        base_a = base_a * rng.gamma(1.0 / gf, gf, n)
    goals, reds, first, last, first_min, frac = _goal_path(
        params, (base_h, base_a), _red_base(params, centres), rng, n
    )
    res = SimResult(
        n=n,
        goals=goals,
        reds=reds,
        first_goal=first,
        first_goal_minute=first_min,
        last_goal=last,
    )
    frail = _frailties(params, rng, n)
    for metric, halves in centres.halves.items():
        coefs = params.count_coef.get(metric)
        if coefs is None:
            continue
        out = np.zeros((2, 2, n), dtype=np.int64)
        for h in (1, 2):
            c = coefs.get(h, {})
            alpha = params.count_alpha.get(metric, {}).get(h, 0.0)
            for s in (0, 1):
                eta = np.full(n, c.get("intercept", 0.0))
                eta += c.get("trail", 0.0) * frac[h - 1, s, 0]
                eta += c.get("lead", 0.0) * frac[h - 1, s, 1]
                eta += c.get("own_red", 0.0) * frac[h - 1, s, 2]
                eta += c.get("opp_red", 0.0) * frac[h - 1, s, 3]
                eta += c.get("goals_for", 0.0) * goals[h - 1, s]
                eta += c.get("goals_against", 0.0) * goals[h - 1, 1 - s]
                mean = halves[h - 1][s] * np.exp(eta)
                mean = mean * frail[FRAILTY_KEYS.index((metric, s))]
                if alpha > 0:
                    mean = mean * rng.gamma(1.0 / alpha, alpha, n)
                out[h - 1, s] = rng.poisson(mean)
                if metric == "cards_points":
                    out[h - 1, s] += RED_CARD_POINTS * reds[h - 1, s]
        res.counts[metric] = out
    return res


def _red_base(params: SimParams, centres: Centres) -> tuple[float, float]:
    cards = centres.cards or (params.default_cards, params.default_cards)
    return (max(cards[0], 0.1) / 90.0, max(cards[1], 0.1) / 90.0)


# --------------------------------------------------------------------------
# Fitting (history before a date cut)
# --------------------------------------------------------------------------


def poisson_irls(
    x: FloatArray,
    y: FloatArray,
    offset: FloatArray,
    ridge: float = 1e-6,
    iters: int = 50,
) -> tuple[FloatArray, FloatArray]:
    """Poisson regression with log link and an offset by Newton steps:
    (coefficients, standard errors). ``offset`` is log exposure x rate."""
    beta = np.zeros(x.shape[1])
    for _ in range(iters):
        eta = np.clip(offset + x @ beta, -30, 30)
        mu = np.exp(eta)
        grad = x.T @ (y - mu) - ridge * beta
        hess = (x * mu[:, None]).T @ x + ridge * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    eta = np.clip(offset + x @ beta, -30, 30)
    hess = (x * np.exp(eta)[:, None]).T @ x + ridge * np.eye(x.shape[1])
    se = np.sqrt(np.diag(np.linalg.inv(hess)))
    return beta, se


def _dcat(d: int) -> int:
    return max(-2, min(2, d))


@dataclass
class _Cells:
    """Exposure (sum of rate x minutes) and events per covariate cell."""

    exposure: dict[tuple[int, ...], float] = field(default_factory=dict)
    events: dict[tuple[int, ...], float] = field(default_factory=dict)

    def add(self, key: tuple[int, ...], exposure: float, events: float = 0.0) -> None:
        self.exposure[key] = self.exposure.get(key, 0.0) + exposure
        if events:
            self.events[key] = self.events.get(key, 0.0) + events


def _half_events(m: MinuteMatch, half: int) -> list[tuple[int, str, int]]:
    """(minute, "g" / "r", side) of one half in order of play (a red before
    a goal in the same minute)."""
    out = [(mi, "g", s) for h, mi, s in (m.goals or ()) if h == half]
    out += [(mi, "r", s) for h, mi, s in (m.reds or ()) if h == half]
    out.sort(key=lambda e: (e[0], 0 if e[1] == "r" else 1))
    return out


@dataclass
class PathSegment:
    """A stretch of one half with a constant state: minutes [start, end)."""

    half: int
    start: int
    end: int
    goals: tuple[int, int]  # running score at its start
    reds: tuple[int, int]


def path_segments(m: MinuteMatch, use_added: bool = True) -> list[PathSegment]:
    """The match's regular-time path cut into constant-state stretches; a
    half's added time is inside only when its length is known."""
    out: list[PathSegment] = []
    g = [0, 0]
    r = [0, 0]
    for half in (1, 2):
        known = m.added[half - 1]
        length = REGULAR_MINUTES + (known if (use_added and known is not None) else 0)
        start = 0
        for minute, kind, side in _half_events(m, half):
            cut = min(minute + 1, length)
            if cut > start:
                out.append(PathSegment(half, start, cut, (g[0], g[1]), (r[0], r[1])))
                start = cut
            if kind == "g":
                g[side] += 1
            else:
                r[side] += 1
        if length > start:
            out.append(PathSegment(half, start, length, (g[0], g[1]), (r[0], r[1])))
    return out


def _bin_pieces(half: int, start: int, end: int) -> list[tuple[int, bool, int]]:
    """(bin, late, minutes) pieces of [start, end) in one half."""
    cuts = sorted(
        {start, end, *(c for c in (15, 30, 45) if start < c < end)}
        | ({LATE_MINUTE} if half == 2 and start < LATE_MINUTE < end else set())
    )
    out = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        out.append((minute_bin(half, a), half == 2 and a >= LATE_MINUTE, b - a))
    return out


def goal_cells(
    matches: Iterable[tuple[MinuteMatch, tuple[float, float]]],
) -> _Cells:
    """Aggregated goal exposure / goals per (bin, d, late, own red, opp red)
    from side's view; exposure in units of mu / 90 x minutes."""
    cells = _Cells()
    for m, mu in matches:
        if m.goals is None or m.reds is None:
            continue
        segs = path_segments(m)
        ends = {(s.half): s.end for s in segs}
        for s in segs:
            for b, late, minutes in _bin_pieces(s.half, s.start, s.end):
                for side in (0, 1):
                    d = s.goals[side] - s.goals[1 - side]
                    key = (
                        b,
                        _dcat(d),
                        int(late),
                        min(s.reds[side], 2),
                        min(s.reds[1 - side], 2),
                    )
                    cells.add(key, mu[side] / 90.0 * minutes)
        # goals at the state before each goal
        g = [0, 0]
        r = [0, 0]
        for half in (1, 2):
            end = ends.get(half, REGULAR_MINUTES)
            for minute, kind, side in _half_events(m, half):
                if kind == "g":
                    if minute < end:
                        d = g[side] - g[1 - side]
                        late = half == 2 and minute >= LATE_MINUTE
                        key = (
                            minute_bin(half, minute),
                            _dcat(d),
                            int(late),
                            min(r[side], 2),
                            min(r[1 - side], 2),
                        )
                        cells.add(key, 0.0, 1.0)
                    g[side] += 1
                else:
                    r[side] += 1
    return cells


def _goal_design(key: tuple[int, ...]) -> list[float]:
    b, d, late, own, opp = key
    row = [0.0] * N_BINS
    row[b] = 1.0
    return row + [
        float(d == -1),
        float(d == -2),
        float(d == 1),
        float(d == 2),
        float(late and d < 0),
        float(late and d > 0),
        float(own),
        float(opp),
    ]


def fit_goal_model(
    cells: _Cells,
) -> tuple[tuple[float, ...], dict[str, float], dict[str, float]]:
    """(profile, state coefficients, their standard errors)."""
    keys = [k for k, e in cells.exposure.items() if e > 0]
    x = np.array([_goal_design(k) for k in keys])
    y = np.array([cells.events.get(k, 0.0) for k in keys])
    off = np.log(np.array([cells.exposure[k] for k in keys]))
    beta, se = poisson_irls(x, y, off)
    prof = tuple(float(v) for v in beta[:N_BINS])
    state = {name: float(v) for name, v in zip(GOAL_STATE, beta[N_BINS:], strict=True)}
    ses = {name: float(v) for name, v in zip(GOAL_STATE, se[N_BINS:], strict=True)}
    for i in range(N_BINS):
        ses[f"bin{i}"] = float(se[i])
    return prof, state, ses


def red_cells(
    matches: Iterable[tuple[MinuteMatch, tuple[float, float]]],
) -> _Cells:
    """Red-card exposure (cards centre / 90 x minutes) / reds per (bin, sign
    of the side's goal difference, late)."""
    cells = _Cells()
    for m, cards in matches:
        if m.goals is None or m.reds is None:
            continue
        segs = path_segments(m)
        ends = {s.half: s.end for s in segs}
        for s in segs:
            for b, late, minutes in _bin_pieces(s.half, s.start, s.end):
                for side in (0, 1):
                    d = s.goals[side] - s.goals[1 - side]
                    key = (b, int(np.sign(d)), int(late))
                    cells.add(key, cards[side] / 90.0 * minutes)
        g = [0, 0]
        for half in (1, 2):
            end = ends.get(half, REGULAR_MINUTES)
            for minute, kind, side in _half_events(m, half):
                if kind == "r":
                    if minute < end:
                        d = g[side] - g[1 - side]
                        late = half == 2 and minute >= LATE_MINUTE
                        cells.add(
                            (minute_bin(half, minute), int(np.sign(d)), int(late)),
                            0.0,
                            1.0,
                        )
                else:
                    g[side] += 1
    return cells


def fit_red_model(
    cells: _Cells,
) -> tuple[tuple[float, ...], dict[str, float], dict[str, float]]:
    keys = [k for k, e in cells.exposure.items() if e > 0]
    rows = []
    for b, sgn, late in keys:
        row = [0.0] * N_BINS
        row[b] = 1.0
        rows.append(row + [float(sgn < 0), float(sgn > 0), float(late)])
    x = np.array(rows)
    y = np.array([cells.events.get(k, 0.0) for k in keys])
    off = np.log(np.array([cells.exposure[k] for k in keys]))
    beta, se = poisson_irls(x, y, off, ridge=1e-3)
    prof = tuple(float(v) for v in beta[:N_BINS])
    state = {name: float(v) for name, v in zip(RED_STATE, beta[N_BINS:], strict=True)}
    ses = {name: float(v) for name, v in zip(RED_STATE, se[N_BINS:], strict=True)}
    return prof, state, ses


def half_state_features(m: MinuteMatch) -> FloatArray:
    """(2 halves, 2 sides, len(COUNT_STATE)) - the fractions of the half
    spent trailing / leading / with a red for / against, and the goals for /
    against in the half - off the real path (added time inside when known)."""
    out = np.zeros((2, 2, len(COUNT_STATE)))
    segs = path_segments(m)
    for half in (1, 2):
        hs = [s for s in segs if s.half == half]
        total = sum(s.end - s.start for s in hs)
        if total <= 0:
            continue
        for s in hs:
            w = (s.end - s.start) / total
            for side in (0, 1):
                d = s.goals[side] - s.goals[1 - side]
                out[half - 1, side, 0] += w * (d < 0)
                out[half - 1, side, 1] += w * (d > 0)
                out[half - 1, side, 2] += w * (s.reds[side] > 0)
                out[half - 1, side, 3] += w * (s.reds[1 - side] > 0)
    for h, _, side in m.goals or ():
        out[h - 1, side, 4] += 1
        out[h - 1, 1 - side, 5] += 1
    return out


def _reds_in(m: MinuteMatch, half: int, side: int) -> int:
    return sum(1 for h, _, s in (m.reds or ()) if h == half and s == side)


def fit_count_models(
    rows: Sequence[tuple[MinuteMatch, Centres]],
) -> tuple[
    dict[str, dict[int, dict[str, float]]],
    dict[str, dict[int, dict[str, float]]],
    dict[str, dict[int, float]],
    tuple[tuple[float, ...], ...],
    dict[str, int],
]:
    """Per metric and half: the log-linear state model (coefficients, their
    standard errors), the extra NB variance per half and the frailty
    covariance across (metric, side), by moments on the fitted means."""
    coef: dict[str, dict[int, dict[str, float]]] = {}
    ses: dict[str, dict[int, dict[str, float]]] = {}
    alpha: dict[str, dict[int, float]] = {}
    n_used: dict[str, int] = {}
    # per match: (metric, side, half) -> (y, fitted mean)
    fitted: dict[int, dict[tuple[str, int, int], tuple[float, float]]] = {}
    feats = {
        m.event_id: half_state_features(m)
        for m, _ in rows
        if m.goals is not None and m.reds is not None
    }
    for metric in COUNT_METRICS:
        coef[metric], ses[metric], alpha[metric] = {}, {}, {}
        for half in (1, 2):
            xs, ys, offs, keys = [], [], [], []
            for m, c in rows:
                f = feats.get(m.event_id)
                if f is None or metric not in m.halves or metric not in c.halves:
                    continue
                for side in (0, 1):
                    centre = c.halves[metric][half - 1][side]
                    if centre <= 0:
                        continue
                    y_obs = m.halves[metric][half - 1][side]
                    if metric == "cards_points":
                        # the dismissals are the red process's: model the
                        # rest (RED_CARD_POINTS each comes back in simulate)
                        y_obs = max(
                            y_obs - RED_CARD_POINTS * _reds_in(m, half, side), 0.0
                        )
                    xs.append([1.0, *f[half - 1, side]])
                    ys.append(y_obs)
                    offs.append(math.log(centre))
                    keys.append((m.event_id, side))
            if len(ys) < 200:
                continue
            x, y, off = np.array(xs), np.array(ys), np.array(offs)
            beta, se = poisson_irls(x, y, off, ridge=1e-3)
            names = ("intercept", *COUNT_STATE)
            coef[metric][half] = {k: float(v) for k, v in zip(names, beta, strict=True)}
            ses[metric][half] = {k: float(v) for k, v in zip(names, se, strict=True)}
            mu = np.exp(off + x @ beta)
            a = float(np.sum((y - mu) ** 2 - y) / np.sum(mu**2))
            alpha[metric][half] = a
            n_used[f"{metric}_{half}h"] = len(ys)
            for (eid, side), yy, mm in zip(keys, y, mu, strict=True):
                fitted.setdefault(eid, {})[(metric, side, half)] = (
                    float(yy),
                    float(mm),
                )
    # frailty: shared across the halves of one (metric, side), correlated
    # across (metric, side) pairs of one match
    k = len(FRAILTY_KEYS)
    num = np.zeros((k, k))
    den = np.zeros((k, k))
    for per in fitted.values():
        whole: dict[tuple[str, int], tuple[float, float]] = {}
        for i, (metric, side) in enumerate(FRAILTY_KEYS):
            h1, h2 = per.get((metric, side, 1)), per.get((metric, side, 2))
            if h1 is None or h2 is None:
                continue
            whole[(metric, side)] = (h1[0] + h2[0], h1[1] + h2[1])
            num[i, i] += (h1[0] - h1[1]) * (h2[0] - h2[1])
            den[i, i] += h1[1] * h2[1]
        for i, a_key in enumerate(FRAILTY_KEYS):
            for j, b_key in enumerate(FRAILTY_KEYS):
                if j <= i or a_key not in whole or b_key not in whole:
                    continue
                ya, ma = whole[a_key]
                yb, mb = whole[b_key]
                num[i, j] += (ya - ma) * (yb - mb)
                den[i, j] += ma * mb
    cov = np.zeros((k, k))
    for i in range(k):
        for j in range(i, k):
            if den[i, j] > 0:
                cov[i, j] = cov[j, i] = num[i, j] / den[i, j]
    for i in range(k):
        cov[i, i] = max(cov[i, i], 0.0)
    for metric in COUNT_METRICS:
        i = FRAILTY_KEYS.index((metric, 0))
        shared = (cov[i, i] + cov[i + 1, i + 1]) / 2
        for half, a in list(alpha[metric].items()):
            alpha[metric][half] = max((a - shared) / (1.0 + shared), 0.0)
    return (coef, ses, alpha, tuple(tuple(float(v) for v in r) for r in cov), n_used)


def added_pmf(
    matches: Iterable[MinuteMatch],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """The history's distribution of minutes played past 45 / 90 (capped at
    MAX_ADDED)."""
    counts = np.zeros((2, MAX_ADDED + 1))
    for m in matches:
        for h in (0, 1):
            a = m.added[h]
            if a is not None:
                counts[h, min(a, MAX_ADDED)] += 1
    out = []
    for h in (0, 1):
        tot = counts[h].sum()
        out.append(
            tuple(
                float(v / tot) if tot else (1.0 if i == 0 else 0.0)
                for i, v in enumerate(counts[h])
            )
        )
    return out[0], out[1]


# --------------------------------------------------------------------------
# Markets read off the simulated paths
# --------------------------------------------------------------------------

_SCOPES = {"": 2, "_1h": 0, "_2h": 1}  # 2 = the match
BASES = (
    "goals",
    "corners",
    "cards_points",
    "fouls",
    "shots",
    "shots_on_target",
    "red_cards",
)
_BASE_RE = "|".join(sorted(BASES, key=len, reverse=True))
_SIMPLE = re.compile(rf"^({_BASE_RE})(_1h|_2h)?_(for|total)$")
_PAIRED = re.compile(rf"^(both_over|most|handicap)_({_BASE_RE})(_1h|_2h)?$")


class MarketSim:
    """Every market of one match read off the same simulated paths. An
    event is a boolean array over the N paths; a probability is its mean.

    ``side`` is 0 / 1 (home / away, the fixture's orientation) for a market
    with a team subject."""

    def __init__(self, res: SimResult) -> None:
        self.res = res
        self.n = res.n

    def value(self, base: str, scope: int, side: int | None) -> IntArray | None:
        """A quantity per path: scope 0 / 1 = a half, 2 = the match; side
        None = both sides together."""
        if base == "goals":
            arr = self.res.goals
        elif base == "red_cards":
            arr = self.res.reds
        else:
            got = self.res.counts.get(base)
            if got is None:
                return None
            arr = got
        per = arr[0] + arr[1] if scope == 2 else arr[scope]
        out = per[0] + per[1] if side is None else per[side]
        return np.asarray(out, dtype=np.int64)

    def ft(self) -> tuple[IntArray, IntArray]:
        g = self.res.goals
        return g[0, 0] + g[1, 0], g[0, 1] + g[1, 1]

    def result(self, scope: int = 2) -> IntArray:
        """1 home win, 0 draw, -1 away win of the match or a half."""
        h = self.value("goals", scope, 0)
        a = self.value("goals", scope, 1)
        assert h is not None and a is not None
        return np.asarray(np.sign(h - a), dtype=np.int64)

    def p(self, event: BoolArray | None) -> float | None:
        return None if event is None else float(np.mean(event))

    # -- the SHEET markets (live sofa_settled_row conventions) ------------

    def selection(
        self, market: str, subject: str, line: float, direction: str, side: int | None
    ) -> BoolArray | None:
        """The event a settled row's selection wins on; None when the
        simulator does not read the market (or the subject's side is
        unknown). A push (an integer line) is never asked."""
        over = self._over(market, subject, line, side)
        if over is None:
            return None
        if direction == "OVER":
            return over
        if direction != "UNDER":
            return None
        under = self._under(market, subject, line, side)
        return under if under is not None else ~over

    def _under(
        self, market: str, subject: str, line: float, side: int | None
    ) -> BoolArray | None:
        m = _SIMPLE.match(market)
        if m:
            scope, who = _SCOPES[m.group(2) or ""], m.group(3)
            if who == "for" and side is None:
                return None
            v = self.value(m.group(1), scope, side if who == "for" else None)
            return None if v is None else v < line
        if market == "draw_no_bet":
            r = self.result()
            return np.asarray(r == -1)
        return None

    def _over(
        self, market: str, subject: str, line: float, side: int | None
    ) -> BoolArray | None:
        m = _SIMPLE.match(market)
        if m:
            scope, who = _SCOPES[m.group(2) or ""], m.group(3)
            if who == "for" and side is None:
                return None
            v = self.value(m.group(1), scope, side if who == "for" else None)
            return None if v is None else v > line
        m = _PAIRED.match(market)
        if m:
            kind, base, scope = m.group(1), m.group(2), _SCOPES[m.group(3) or ""]
            vh, va = self.value(base, scope, 0), self.value(base, scope, 1)
            if vh is None or va is None:
                return None
            if kind == "both_over":
                return (vh > line) & (va > line)
            if kind == "most":
                if subject == "__draw__":
                    return np.asarray(vh == va, dtype=np.bool_)
                if side is None:
                    return None
                return vh > va if side == 0 else va > vh
            if side is None:  # handicap: the subject side given +line
                return None
            own, other = (vh, va) if side == 0 else (va, vh)
            return own + line > other
        r = self.result()
        fh, fa = self.ft()
        total = fh + fa
        btts = (fh > 0) & (fa > 0)
        if market == "result_1x2":
            return {"1": r == 1, "X": r == 0, "2": r == -1}.get(subject)
        if market == "double_chance":
            return {"1X": r >= 0, "X2": r <= 0, "12": r != 0}.get(subject)
        if market == "draw_no_bet":
            # graded only without a draw: the probability is conditional
            return np.asarray(r == 1)
        if market == "first_goal":
            fg = self.res.first_goal
            if subject == "nikt":
                return np.asarray(fg < 0)
            # SHEET's first_goal rows name the side "1" / "2"
            who = {"1": 0, "2": 1}.get(subject, side)
            if who is None:
                return None
            return np.asarray(fg == who)
        res_of = {"1": r == 1, "X": r == 0, "2": r == -1}
        if market == "result_or_over":
            sel = res_of.get(subject)
            return None if sel is None else sel | (total > line)
        if market == "result_or_under":
            sel = res_of.get(subject)
            return None if sel is None else sel | (total < line)
        if market == "btts_or_over":
            return btts | (total > line)
        if market == "result_or_btts":
            sel = res_of.get(subject)
            return None if sel is None else sel | btts
        if market == "result_or_clean_sheet":
            sel = res_of.get(subject)
            return None if sel is None else sel | (fh == 0) | (fa == 0)
        if market == "result_handicap":
            if subject == "1":
                return fh + line > fa
            if subject == "2":
                return fa + line > fh
            return None
        if market == "dc_and_over":
            return (r != 0) & (total > line) if subject == "12" else None
        if market == "dc_and_under":
            return (r >= 0) & (total < line) if subject == "1X" else None
        return None

    def conditional_p(self, market: str, event: BoolArray) -> float | None:
        """P of a row's selection as it is graded: a draw-no-bet leg only
        when the match is not drawn (a draw refunds it)."""
        if market == "draw_no_bet":
            keep = self.result() != 0
            if not keep.any():
                return None
            return float(np.mean(event[keep]))
        return float(np.mean(event))


# --------------------------------------------------------------------------
# Path markets (SHEET does not price them): one set of mutually exclusive
# outcomes per kind, read off the paths and off a finished match alike
# --------------------------------------------------------------------------

PATH_KINDS = (
    "htft",
    "half_result",
    "higher_half",
    "team_both_halves",
    "btts_halves",
    "btts_any_half",
    "half_totals",
    "first_goal_band15",
    "first_goal_1h",
    "last_goal",
    "odd_even",
    "exact_goals",
    "correct_score",
)
_RES = {1: "1", 0: "X", -1: "2"}


def _band15(minute: float) -> int:
    return min(int(minute // 15), 5)


def path_outcomes(ms: MarketSim, kind: str, param: Any = None) -> dict[str, BoolArray]:
    """{outcome key: event over the paths} of one path market; the outcomes
    are mutually exclusive and exhaustive (correct score: the scores the
    paths reach)."""
    g = ms.res.goals
    h1, a1, h2, a2 = g[0, 0], g[0, 1], g[1, 0], g[1, 1]
    fh, fa = h1 + h2, a1 + a2
    if kind == "htft":
        r1, r = np.sign(h1 - a1), np.sign(fh - fa)
        return {
            f"{_RES[x]}/{_RES[y]}": (r1 == x) & (r == y)
            for x in (1, 0, -1)
            for y in (1, 0, -1)
        }
    if kind == "half_result":
        hh, aa = (h1, a1) if param == 1 else (h2, a2)
        rr = np.sign(hh - aa)
        return {_RES[x]: rr == x for x in (1, 0, -1)}
    if kind == "higher_half":
        t1, t2 = h1 + a1, h2 + a2
        return {"1H": t1 > t2, "X": t1 == t2, "2H": t2 > t1}
    if kind == "team_both_halves":
        first, second = (h1, h2) if param == 0 else (a1, a2)
        yes = (first > 0) & (second > 0)
        return {"tak": yes, "nie": ~yes}
    if kind == "btts_halves":
        b1, b2 = (h1 > 0) & (a1 > 0), (h2 > 0) & (a2 > 0)
        return {
            f"{'Tak' if x else 'Nie'}/{'Tak' if y else 'Nie'}": (b1 == x) & (b2 == y)
            for x in (True, False)
            for y in (True, False)
        }
    if kind == "btts_any_half":
        yes = ((h1 > 0) & (a1 > 0)) | ((h2 > 0) & (a2 > 0))
        return {"tak": yes, "nie": ~yes}
    if kind == "half_totals":
        l1, l2 = param
        o1, o2 = (h1 + a1) > l1, (h2 + a2) > l2
        return {
            f"{'O' if x else 'U'}/{'O' if y else 'U'}": (o1 == x) & (o2 == y)
            for x in (True, False)
            for y in (True, False)
        }
    if kind == "first_goal_band15":
        fm = ms.res.first_goal_minute
        none = np.isnan(fm)
        band = np.where(none, -1, np.floor(np.nan_to_num(fm) / 15)).astype(np.int64)
        band = np.minimum(band, 5)
        out = {str(b): band == b for b in range(6)}
        out["none"] = none
        return out
    if kind == "first_goal_1h":
        fg, fm = ms.res.first_goal, ms.res.first_goal_minute
        in1 = (fg >= 0) & (np.nan_to_num(fm, nan=99.0) < REGULAR_MINUTES)
        return {"1": in1 & (fg == 0), "2": in1 & (fg == 1), "none": ~in1}
    if kind == "last_goal":
        lg = ms.res.last_goal
        return {"1": lg == 0, "2": lg == 1, "none": lg < 0}
    if kind == "odd_even":
        odd = ((fh + fa) % 2) == 1
        return {"odd": odd, "even": ~odd}
    if kind == "exact_goals":
        t = fh + fa
        out = {str(k): t == k for k in range(6)}
        out["6+"] = t >= 6
        return out
    if kind == "correct_score":
        hh, aa = (fh, fa) if param == 2 else (h1, a1) if param == 0 else (h2, a2)
        keys = sorted(set(zip(hh.tolist(), aa.tolist(), strict=True)))
        return {f"{x}:{y}": (hh == x) & (aa == y) for x, y in keys}
    raise ValueError(f"unknown path market {kind}")


def path_actual(m: MinuteMatch, kind: str, param: Any = None) -> str | None:
    """The winning outcome key of a path market in a finished match; None
    when the match cannot grade it (no half-time score; no timed goals for
    the first / last goal kinds)."""
    if m.ht is None:
        return None
    h1, a1 = m.ht
    fh, fa = m.ft
    h2, a2 = fh - h1, fa - a1
    if min(h2, a2) < 0:
        return None

    def sg(x: int) -> int:
        return (x > 0) - (x < 0)

    if kind == "htft":
        return f"{_RES[sg(h1 - a1)]}/{_RES[sg(fh - fa)]}"
    if kind == "half_result":
        return _RES[sg(h1 - a1)] if param == 1 else _RES[sg(h2 - a2)]
    if kind == "higher_half":
        t1, t2 = h1 + a1, h2 + a2
        return "1H" if t1 > t2 else "2H" if t2 > t1 else "X"
    if kind == "team_both_halves":
        first, second = (h1, h2) if param == 0 else (a1, a2)
        return "tak" if first > 0 and second > 0 else "nie"
    if kind == "btts_halves":
        b1, b2 = h1 > 0 and a1 > 0, h2 > 0 and a2 > 0
        return f"{'Tak' if b1 else 'Nie'}/{'Tak' if b2 else 'Nie'}"
    if kind == "btts_any_half":
        return "tak" if (h1 > 0 and a1 > 0) or (h2 > 0 and a2 > 0) else "nie"
    if kind == "half_totals":
        l1, l2 = param
        return f"{'O' if h1 + a1 > l1 else 'U'}/{'O' if h2 + a2 > l2 else 'U'}"
    if kind == "odd_even":
        return "odd" if (fh + fa) % 2 else "even"
    if kind == "exact_goals":
        return str(fh + fa) if fh + fa < 6 else "6+"
    if kind == "correct_score":
        hh, aa = (fh, fa) if param == 2 else (h1, a1) if param == 0 else (h2, a2)
        return f"{hh}:{aa}"
    if m.goals is None:
        return None
    if kind == "first_goal_band15":
        if not m.goals:
            return "none"
        half, minute, _ = m.goals[0]
        return str(
            min(
                _band15(
                    (half - 1) * REGULAR_MINUTES + min(minute, REGULAR_MINUTES - 1)
                ),
                5,
            )
        )
    if kind == "first_goal_1h":
        if not m.goals or m.goals[0][0] != 1:
            return "none"
        return "1" if m.goals[0][2] == 0 else "2"
    if kind == "last_goal":
        if not m.goals:
            return "none"
        return "1" if m.goals[-1][2] == 0 else "2"
    raise ValueError(f"unknown path market {kind}")
