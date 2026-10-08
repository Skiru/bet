#!/usr/bin/env python3
"""measure_pooling.py - does partial pooling (team + league effects, variance
components from the data) beat today's fixed K_CENTRE + league prior for the
football counting markets?  READ-ONLY evidence, never a gate.

Subcommands
  extract   read the football history from the database (sqlite mode=ro, no
            network) into a compact pickle of matches
  run       replay time-ordered, score the estimators, write the JSON
  report    (not a stage) the Polish markdown is written by hand from the JSON

What is compared (all see exactly the same matches and the same sample):
  today    centre = (n*mean + K*prior) / (n + K), K = K_CENTRE football (15),
           prior = the league's mean of every value seen BEFORE the match
           (>= MIN_BASELINE_OBSERVATIONS 30 values, else the global mean) -
           fit_constants.fit_baselines made causal.  The shipped baselines
           file is fitted on the whole history and would leak.
  eb       a team effect + a league effect with variance components estimated
           from the data seen so far: the league mean is shrunk toward the
           global mean with weight m/(m + k_league), k_league = s2_team/s2_league
           (m = league observations, per team-slot of the league), and the team
           mean toward that with weight n/(n + k_team), k_team = s2_within/s2_team
           (n = the sample's matches).  k_team / k_league are per metric (and
           per league-size class for k_team).
  nopool   centre = sample mean (the floor)

The predictive distribution is SHEET's: engine.sheet_predictive_sd and
engine.sheet_count_p_raw at the same x.5 ladder (calibrate_from_cache.lines_for)
and the same sample mean / variance, only the centre differs.

Sample = the team's last SAMPLE_N (10) earlier REGULAR matches that have the
statistic (calibrate_from_cache.recent_for, so goals use the same-competition
rule), n >= MIN_SAMPLE (8) - the replay's rule.  A match never enters its own
sample: the history is appended after the match is scored.
"""

from __future__ import annotations

import argparse
import collections
import copy
import json
import math
import pickle
import sqlite3
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

Match = tuple[int, int, int, int, int | None, str, dict[str, tuple[float, float]]]
BASES = ("corners", "cards_points", "fouls", "shots", "shots_on_target", "goals")
MIN_BASELINE_OBSERVATIONS = 30  # fit_constants.MIN_BASELINE_OBSERVATIONS
K_TODAY = 15.0  # config/sofa_engine_constants.json K_CENTRE.by_sport.football
SAMPLE_N = 10
MIN_SAMPLE = 8


# ---------------------------------------------------------------------------
# extract (read-only)
# ---------------------------------------------------------------------------

def _lean(event: dict[str, Any], kind: str) -> dict[str, Any]:
    """Only the keys the football replay reads (memory: whole slim events of
    ~1M matches held 8+ GB), plus the precomputed match_kind."""
    def keep(d: Any, keys: Sequence[str]) -> dict[str, Any]:
        d = d if isinstance(d, dict) else {}
        return {k: d[k] for k in keys if k in d}

    tour = event.get("tournament") or {}
    cat = tour.get("category") or {}
    return {
        "id": event.get("id"),
        "startTimestamp": event.get("startTimestamp"),
        "status": keep(event.get("status"), ("type", "code", "description")),
        "homeTeam": keep(event.get("homeTeam"), ("id", "name")),
        "awayTeam": keep(event.get("awayTeam"), ("id", "name")),
        "homeScore": keep(event.get("homeScore"),
                          ("current", "normaltime", "period1", "period2")),
        "awayScore": keep(event.get("awayScore"),
                          ("current", "normaltime", "period1", "period2")),
        "_kind": kind,
        "tournament": {
            "name": tour.get("name"),
            "uniqueTournament": keep(tour.get("uniqueTournament"), ("id", "name")),
            "category": {"name": cat.get("name"),
                         "sport": keep(cat.get("sport"), ("slug",))},
        },
    }


def extract(db_path: Path, out: Path) -> int:
    """Football finished matches -> pickle of
    (matches, league_names): match = (ts, event_id, home, away, comp, kind,
    {base: (h, a)}).  Opens the database read-only."""
    from bet.sofa.comparability import match_kind
    from bet.sofa.listing_index import listed_events_by_id
    from bet.sofa.samples import one_listing_per_match
    from bet.sofa.settle import is_completed_event
    from scripts.sofa import calibrate_from_cache as cc

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    names: dict[int, str] = {}
    try:
        def finished_copy(event: dict[str, Any]) -> dict[str, Any] | None:
            if (event.get("status") or {}).get("type") != "finished":
                return None
            if cc._event_sport(event) != "football":
                return None
            return _lean(event, str(match_kind(event, "football")))

        identity = listed_events_by_id(conn, finished_copy, kinds=None)
        # the JSON is parsed and dropped row by row (it is the bulk of the RAM)
        values_by_event: dict[int, dict[str, tuple[float, float]]] = {}
        for event_id, st, inc in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE status_type = 'finished'"
        ):
            event = identity.get(event_id)
            if event is None:
                continue
            vals = cc.match_values(event, "football", st, inc)
            vals = {b: v for b, v in vals.items() if b in BASES}
            values_by_event[int(event_id)] = vals
    finally:
        conn.close()
    kept = one_listing_per_match(list(identity.values()))
    matches: list[Match] = []
    for event in kept:
        if not is_completed_event(event):
            continue
        home = (event.get("homeTeam") or {}).get("id")
        away = (event.get("awayTeam") or {}).get("id")
        started = event.get("startTimestamp")
        if not home or not away or not started:
            continue
        ut = ((event.get("tournament") or {}).get("uniqueTournament") or {})
        comp = ut.get("id")
        values = values_by_event.get(int(event["id"]))
        if values is None:  # no /statistics row: goals still come off the listing
            values = {b: v for b, v in
                      cc.match_values(event, "football", None, None).items()
                      if b in BASES}
        if not values:
            continue
        if comp:
            cat = ((event.get("tournament") or {}).get("category") or {}).get("name")
            names[int(comp)] = f"{ut.get('name')} ({cat})"
        matches.append((int(started), int(event["id"]), int(home), int(away),
                        int(comp) if comp else None,
                        str(event["_kind"]), values))
    matches.sort()
    out.write_bytes(pickle.dumps((matches, names)))
    return len(matches)



# ---------------------------------------------------------------------------
# variance components (one-way / nested random effects, method of moments)
# ---------------------------------------------------------------------------

# League size classes by the matches a league holds in the history so far.
CLASS_EDGES = (150, 700)
N_CLASSES = len(CLASS_EDGES) + 1
BIG = 1e9
# a flagged league is MATERIAL when even the near bound of its 95% interval is
# this far (relative) from the global mean
MATERIAL_REL = 0.05


def size_class(matches: float) -> int:
    for i, edge in enumerate(CLASS_EDGES):
        if matches < edge:
            return i
    return len(CLASS_EDGES)


# a cell = one (league, team): [n, sum, sum of squares]
Cells = dict[tuple[int, int], list[float]]


@dataclass
class Snap:
    """Everything one estimator reads of the history at a refit, one
    (base, kind).  Built by build_snap from the cells alone."""

    G: float = 0.0
    s2_w: float = 0.0
    s2_t: list[float] = None  # type: ignore[assignment]  # per size class
    s2_t_nolg: float = 0.0
    s2_l: float = 0.0
    today_prior: dict[int, float] = None  # type: ignore[assignment]
    P: dict[int, float] = None  # type: ignore[assignment]
    cls: dict[int, int] = None  # type: ignore[assignment]
    n_cells: int = 0

    def k_team(self, cls: int) -> float:
        s2 = self.s2_t[cls]
        return self.s2_w / s2 if s2 > 1e-12 else BIG

    def k_nolg(self) -> float:
        return self.s2_w / self.s2_t_nolg if self.s2_t_nolg > 1e-12 else BIG


def _anova_t(
    groups: Iterable[list[tuple[float, float]]], s2_w: float
) -> float:
    """Between-team variance within leagues, pooled over `groups` (each a
    league's [(n, mean)] cells) - unbalanced one-way ANOVA, method of moments:
    s2_t = (sum SSB - s2_w sum df) / sum(n0 df)."""
    ssb = df_sum = n0df = 0.0
    for cells in groups:
        t = len(cells)
        if t < 2:
            continue
        big_n = sum(n for n, _ in cells)
        if big_n <= 0:
            continue
        ybar = sum(n * m for n, m in cells) / big_n
        ssb += sum(n * (m - ybar) ** 2 for n, m in cells)
        df = t - 1
        df_sum += df
        n0df += big_n - sum(n * n for n, _ in cells) / big_n
    if n0df <= 0:
        return 0.0
    return max(0.0, (ssb - s2_w * df_sum) / n0df)


def build_snap(cells: Cells, kind: str) -> Snap:
    """Variance components and league priors from the history so far.

    `kind` only matters for the league sample size ('total' cells count each
    match twice - once per team - so a league's matches are N / 2 either way).
    """
    by_comp: dict[int, list[tuple[float, float, float]]] = collections.defaultdict(list)
    tot_n = tot_s = ss_within = df_within = 0.0
    for (comp, _team), (n, sm, sq) in cells.items():
        if n <= 0:
            continue
        mean = sm / n
        by_comp[comp].append((n, mean, sq))
        tot_n += n
        tot_s += sm
        if n >= 2:
            ss_within += max(0.0, sq - n * mean * mean)
            df_within += n - 1
    snap = Snap(s2_t=[0.0] * N_CLASSES, today_prior={}, P={}, cls={},
                n_cells=len(cells))
    if tot_n <= 0 or df_within <= 0:
        return snap
    snap.G = tot_s / tot_n
    snap.s2_w = ss_within / df_within

    lg_n: dict[int, float] = {}
    lg_mean: dict[int, float] = {}
    lg_sq: dict[int, float] = {}
    members: dict[int, list[tuple[float, float]]] = {}
    for comp, cl in by_comp.items():
        big_n = sum(n for n, _, _ in cl)
        lg_n[comp] = big_n
        lg_mean[comp] = sum(n * m for n, m, _ in cl) / big_n
        lg_sq[comp] = sum(n * n for n, _, _ in cl) / (big_n * big_n)
        members[comp] = [(n, m) for n, m, _ in cl]
        snap.cls[comp] = size_class(big_n / 2.0)
        # fit_constants.fit_baselines: MIN_BASELINE_OBSERVATIONS values, a
        # total once per match, a per-team count once per slot
        values = big_n / 2.0 if kind == "total" else big_n
        if values >= MIN_BASELINE_OBSERVATIONS:
            snap.today_prior[comp] = lg_mean[comp]

    # team variance, per class (pooled over all when a class has no league)
    pooled_t = _anova_t(members.values(), snap.s2_w)
    for c in range(N_CLASSES):
        group = [members[k] for k in members if snap.cls[k] == c]
        have = sum(1 for g in group if len(g) >= 2)
        snap.s2_t[c] = _anova_t(group, snap.s2_w) if have >= 5 else pooled_t
    # team variance with the league effect NOT modelled: all cells one group
    allc = [(n, m) for cl in members.values() for n, m in cl]
    snap.s2_t_nolg = _anova_t([allc], snap.s2_w)

    # league variance: var(league mean) = s2_l + s2_t sum n^2/N^2 + s2_w / N
    v_noise = {
        k: snap.s2_t[snap.cls[k]] * lg_sq[k] + snap.s2_w / lg_n[k] for k in members
    }
    comps = [k for k in members if len(members[k]) >= 2]
    s2_l = 0.0
    for _ in range(3):
        wts = {k: 1.0 / max(s2_l + v_noise[k], 1e-9) ** 2 for k in comps}
        wsum = sum(wts.values())
        if wsum <= 0:
            break
        s2_l = max(
            0.0,
            sum(wts[k] * ((lg_mean[k] - snap.G) ** 2 - v_noise[k]) for k in comps)
            / wsum,
        )
    snap.s2_l = s2_l
    for k in members:
        w = s2_l / (s2_l + v_noise[k]) if s2_l > 0 else 0.0  # s2_l>0 => denominator>0
        snap.P[k] = snap.G + w * (lg_mean[k] - snap.G)
    return snap


def team_centre(snap: Snap, comp: int, xbar: float, n: int) -> float:
    prior = snap.P.get(comp, snap.G)
    k = snap.k_team(snap.cls.get(comp, 0))
    return prior + n / (n + k) * (xbar - prior)


def today_centre(
    snap: Snap, comp: int, xbar: float, n: int, k: float = K_TODAY,
    *, eb_prior: bool = False,
) -> float:
    """Today's fixed-K shrink toward the league prior: the league's raw mean
    (30+ values) else the global mean; `eb_prior` swaps the raw league mean
    for the empirical-Bayes league estimate (shrunk toward the global mean)."""
    prior = (
        snap.P.get(comp, snap.G) if eb_prior
        else snap.today_prior.get(comp, snap.G)
    )
    return (n * xbar + k * prior) / (n + k)



# ---------------------------------------------------------------------------
# time-ordered replay
# ---------------------------------------------------------------------------

K_GRID = (0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 25.0, 40.0, 70.0, 1000.0)
VARIANTS = ("nopool", "today", "todayK", "todayP", "todayKP", "eb", "ebreg", "ebnl",
            "ebavg")
# E = refitted every week (expanding window), a subset is enough
E_VARIANTS = ("today", "todayK", "todayKP", "eb", "ebreg")
MODES = ("F", "E")  # F = parameters frozen at the cut, E = refitted weekly
# D = the same estimators on cells with an exponential memory (half-life
# HALF_LIFE_DAYS): the league prior and components of the recent regime
D_VARIANTS = ("today", "todayK", "ebreg")
HALF_LIFE_DAYS = 180.0
ALL_VARIANTS = (*VARIANTS, *[f"{v}D" for v in D_VARIANTS])
COLS = (
    tuple(f"{v}_F" for v in VARIANTS)
    + tuple(f"{v}_E" for v in E_VARIANTS)
    + tuple(f"{v}D_F" for v in D_VARIANTS)
)
WEEK = 7 * 86400
MIN_LOG = 3  # rows are logged from n >= 3; the replay population is n >= 8
KINDS = ("for", "total")
UNIT_NAMES = ("home_for", "away_for", "total")


@dataclass
class Acc:
    """What the data-driven variants learn from rows already scored: the K of
    `todayK` (squared error per grid K) and the slope of `ebreg` per league
    size class (sum (x-P)(y-P), sum (x-P)^2)."""

    kse: list[float]
    kse_p: list[float]
    kn: int
    reg_xy: list[float]
    reg_xx: list[float]
    reg_n: list[int]

    @staticmethod
    def new() -> Acc:
        return Acc([0.0] * len(K_GRID), [0.0] * len(K_GRID), 0, [0.0] * N_CLASSES,
                   [0.0] * N_CLASSES, [0] * N_CLASSES)

    def best_k(self, with_prior_p: bool = False) -> float:
        if self.kn < 500:
            return K_TODAY
        sums = self.kse_p if with_prior_p else self.kse
        return K_GRID[min(range(len(K_GRID)), key=lambda i: sums[i])]

    def beta(self, cls: int) -> float:
        if self.reg_n[cls] < 300 or self.reg_xx[cls] <= 0:
            return 0.5
        return max(0.0, min(1.5, self.reg_xy[cls] / self.reg_xx[cls]))


def _mean_var(sample: Sequence[float]) -> tuple[float, float]:
    n = len(sample)
    mean = sum(sample) / n
    if n < 2:
        return mean, 0.0
    return mean, sum((v - mean) ** 2 for v in sample) / (n - 1)


@dataclass
class Unit:
    """One scored quantity of one match: a side's own count or the match
    total, with the sample SHEET would hold and the centre inputs."""

    unit: int
    y: float
    comp: int
    n: int  # sample size the spread uses (total: the pooled sample)
    nmin: int  # smaller side's sample (own count: n)
    mean: float
    var: float
    # (xbar, n) of each team window: 'for' one entry, 'total' two
    windows: list[tuple[float, int]]


def centres_for(
    unit: Unit, snap: Snap, acc: Acc
) -> dict[str, float]:
    """Every variant's centre of one unit under one parameter set."""
    comp = unit.comp
    out: dict[str, float] = {"nopool": unit.mean}
    k_today = today_centre(snap, comp, unit.mean, unit.n)
    out["today"] = k_today
    out["todayK"] = today_centre(snap, comp, unit.mean, unit.n, acc.best_k())
    out["todayP"] = today_centre(snap, comp, unit.mean, unit.n, eb_prior=True)
    out["todayKP"] = today_centre(snap, comp, unit.mean, unit.n,
                                  acc.best_k(True), eb_prior=True)
    prior = snap.P.get(comp, snap.G)
    cls = snap.cls.get(comp, 0)
    k = snap.k_team(cls)
    if unit.unit < 2:
        xbar, n = unit.windows[0]
        out["eb"] = prior + n / (n + k) * (xbar - prior)
        out["ebreg"] = prior + acc.beta(cls) * (xbar - prior)
        out["ebnl"] = snap.G + n / (n + snap.k_nolg()) * (xbar - snap.G)
        out["ebavg"] = out["eb"]
    else:
        # additive: the match total is the league level plus both teams'
        # offsets, each shrunk on its own window
        dev = sum(n / (n + k) * (x - prior) for x, n in unit.windows)
        out["eb"] = prior + dev
        out["ebreg"] = prior + acc.beta(cls) * sum(x - prior for x, _ in unit.windows)
        # no league: the pooled mean shrunk toward the global mean (the
        # additive form would count the league level twice)
        out["ebnl"] = snap.G + unit.n / (unit.n + snap.k_nolg()) * (unit.mean - snap.G)
        out["ebavg"] = prior + unit.n / (unit.n + k) * (unit.mean - prior)
    return out


def learn(unit: Unit, snap: Snap, acc: Acc) -> None:
    """Update the accumulators with a scored unit (n >= MIN_SAMPLE only: the
    replay population)."""
    if unit.nmin < MIN_SAMPLE:
        return
    for i, kk in enumerate(K_GRID):
        c = today_centre(snap, unit.comp, unit.mean, unit.n, kk)
        acc.kse[i] += (c - unit.y) ** 2
        cp = today_centre(snap, unit.comp, unit.mean, unit.n, kk, eb_prior=True)
        acc.kse_p[i] += (cp - unit.y) ** 2
    acc.kn += 1
    prior = snap.P.get(unit.comp, snap.G)
    cls = snap.cls.get(unit.comp, 0)
    x = sum(xb - prior for xb, _ in unit.windows)
    yy = unit.y - prior
    acc.reg_xy[cls] += x * yy
    acc.reg_xx[cls] += x * x
    acc.reg_n[cls] += 1


def build_units(
    match: tuple[int, int, int, int, int | None, str, dict[str, tuple[float, float]]],
    base: str,
    history: dict[tuple[int, str], list[Any]],
) -> list[Unit]:
    from scripts.sofa import calibrate_from_cache as cc

    _ts, _eid, home, away, comp, kind, values = match
    hv, av = values[base]
    sample_comp = comp if kind == "REGULAR" else None
    cid = comp or 0
    hist_h = history[(home, base)]
    hist_a = history[(away, base)]
    units: list[Unit] = []
    for unit, own, hist in ((0, hv, hist_h), (1, av, hist_a)):
        recent = cc.recent_for(hist, f"{base}_for", sample_comp)
        n = len(recent)
        if n < MIN_LOG:
            continue
        sample = [p.own for p in recent]
        if all(v == 0.0 for v in sample):
            continue
        mean, var = _mean_var(sample)
        units.append(Unit(unit, own, cid, n, n, mean, var, [(mean, n)]))
    rh = cc.recent_for(hist_h, f"{base}_total", sample_comp)
    ra = cc.recent_for(hist_a, f"{base}_total", sample_comp)
    if len(rh) >= MIN_LOG and len(ra) >= MIN_LOG:
        pooled = cc.pooled_total_sample(rh, ra)
        if not all(v == 0.0 for v in pooled):
            mean, var = _mean_var(pooled)
            wins = [(sum(p.total for p in r) / len(r), len(r)) for r in (rh, ra)]
            units.append(Unit(2, hv + av, cid, len(pooled), min(len(rh), len(ra)),
                              mean, var, wins))
    return units


@dataclass
class Replay:
    cols: dict[str, list[float]]
    meta: dict[str, list[float]]
    snaps_final: dict[tuple[int, int], Snap]
    snaps_cut: dict[tuple[int, int], Snap]
    n_matches_scored: int
    n_matches_total: int
    first_ts: int
    cut_ts: int
    last_ts: int
    league_names: dict[int, str]
    cells_final: dict[tuple[int, int], Cells]
    acc_cut: dict[tuple[int, int], Acc]
    acc_cut_d: dict[tuple[int, int], Acc]
    snaps_cut_d: dict[tuple[int, int], Snap]


def replay(
    matches: list[Any],
    cut_ts: int,
    *,
    acc_from_ts: int | None = None,
    train_days: int = 240,
    half_life_days: float = HALF_LIFE_DAYS,
    log: Any = None,
) -> Replay:
    """Walk the matches in time order; score every unit of a match BEFORE the
    match enters any sample, cell or counter (a match is never in its own
    sample); log the rows from `cut_ts` on."""
    from scripts.sofa import calibrate_from_cache as cc

    pairs = [(bi, ki) for bi in range(len(BASES)) for ki in range(len(KINDS))]
    cells: dict[tuple[int, int], Cells] = {pk: {} for pk in pairs}
    history: dict[tuple[int, str], list[Any]] = collections.defaultdict(list)
    snaps_e: dict[tuple[int, int], Snap] | None = None
    snaps_f: dict[tuple[int, int], Snap] | None = None
    acc_e = {pk: Acc.new() for pk in pairs}
    acc_f: dict[tuple[int, int], Acc] | None = None
    cells_d: dict[tuple[int, int], Cells] = {pk: {} for pk in pairs}
    snaps_d: dict[tuple[int, int], Snap] | None = None
    snaps_df: dict[tuple[int, int], Snap] | None = None
    acc_d = {pk: Acc.new() for pk in pairs}
    acc_df: dict[tuple[int, int], Acc] | None = None
    last_refit_ts = 0
    first_ts = matches[0][0]
    log_from = cut_ts - train_days * 86400
    acc_from = acc_from_ts if acc_from_ts is not None else max(
        first_ts + 90 * 86400, cut_ts - 400 * 86400)
    cut_done = False
    last_week = -1
    meta_names = ("ev", "ts", "base", "unit", "comp", "n", "nmin", "cls", "y",
                  "mean", "var", "dl", "cls_e", "train")
    meta: dict[str, list[float]] = {k: [] for k in meta_names}
    cols: dict[str, list[float]] = {c: [] for c in COLS}
    scored_matches = 0
    snaps_cut: dict[tuple[int, int], Snap] = {}
    t0 = time.time()

    for idx, match in enumerate(matches):
        ts, eid, home, away, comp, kind, values = match
        if kind == "FRIENDLY":
            continue
        week = ts // WEEK
        due = week != last_week and ts >= acc_from
        if ts >= cut_ts and not cut_done:
            due = True
        if due:
            last_week = week
            snaps_e = {pk: build_snap(cells[pk], KINDS[pk[1]]) for pk in pairs}
            if last_refit_ts:
                decay = 0.5 ** ((ts - last_refit_ts) / (half_life_days * 86400))
                for pk in pairs:
                    for cell in cells_d[pk].values():
                        cell[0] *= decay
                        cell[1] *= decay
                        cell[2] *= decay
            last_refit_ts = ts
            snaps_d = {pk: build_snap(cells_d[pk], KINDS[pk[1]]) for pk in pairs}
            if ts < cut_ts:
                snaps_f = snaps_e
                snaps_df = snaps_d
            elif not cut_done:
                cut_done = True
                snaps_f = snaps_e
                snaps_cut = snaps_e
                snaps_df = snaps_d
                acc_f = copy.deepcopy(acc_e)
                acc_df = copy.deepcopy(acc_d)
            if log and idx % 1 == 0:
                log(f"refit week {week} idx {idx}/{len(matches)} "
                    f"{time.time() - t0:.0f}s")
        if (snaps_e is not None and snaps_f is not None
                and snaps_d is not None and snaps_df is not None):
            logged = False
            for base in values:
                if base not in BASES:
                    continue
                bi = BASES.index(base)
                units = build_units(match, base, history)
                for unit in units:
                    pk = (bi, 0 if unit.unit < 2 else 1)
                    if ts >= max(log_from, acc_from):
                        # before the cut F is E: nothing is frozen yet
                        cf = centres_for(unit, snaps_f[pk],
                                         acc_f[pk] if acc_f is not None else acc_e[pk])
                        ce = centres_for(unit, snaps_e[pk], acc_e[pk])
                        cd = centres_for(unit, snaps_df[pk],
                                         acc_df[pk] if acc_df is not None
                                         else acc_d[pk])
                        for v in D_VARIANTS:
                            cols[f"{v}D_F"].append(cd[v])
                        for v in VARIANTS:
                            cols[f"{v}_F"].append(cf[v])
                        for v in E_VARIANTS:
                            cols[f"{v}_E"].append(ce[v])
                        sf = snaps_f[pk]
                        meta["train"].append(0 if ts >= cut_ts else 1)
                        meta["ev"].append(eid)
                        meta["ts"].append(ts)
                        meta["base"].append(bi)
                        meta["unit"].append(unit.unit)
                        meta["comp"].append(unit.comp)
                        meta["n"].append(unit.n)
                        meta["nmin"].append(unit.nmin)
                        meta["cls"].append(sf.cls.get(unit.comp, 0))
                        meta["cls_e"].append(snaps_e[pk].cls.get(unit.comp, 0))
                        meta["y"].append(unit.y)
                        meta["mean"].append(unit.mean)
                        meta["var"].append(unit.var)
                        meta["dl"].append(sf.P.get(unit.comp, sf.G) - sf.G)
                        logged = True
                # learn only after every unit of the match has its centre: a
                # match's own outcome never tunes the estimator that scores it
                if ts >= acc_from:
                    for unit in units:
                        pk = (bi, 0 if unit.unit < 2 else 1)
                        learn(unit, snaps_e[pk], acc_e[pk])
                        learn(unit, snaps_d[pk], acc_d[pk])
            if logged:
                scored_matches += 1
        # only after scoring: the match enters the cells, counters, history
        regular = kind == "REGULAR"
        cid = comp or 0
        for base, (hv, av) in values.items():
            if base not in BASES:
                continue
            bi = BASES.index(base)
            total = hv + av
            for team, own in ((home, hv), (away, av)):
                for ki, val in ((0, own), (1, total)):
                    cell = cells[(bi, ki)].setdefault((cid, team), [0.0, 0.0, 0.0])
                    cell[0] += 1
                    cell[1] += val
                    cell[2] += val * val
                    celld = cells_d[(bi, ki)].setdefault((cid, team),
                                                         [0.0, 0.0, 0.0])
                    celld[0] += 1
                    celld[1] += val
                    celld[2] += val * val
            history[(home, base)].append(
                cc.Past(ts, eid, hv, total, comp, regular))
            history[(away, base)].append(
                cc.Past(ts, eid, av, total, comp, regular))
        if log and idx % 100_000 == 0:
            log(f"match {idx}/{len(matches)} ts {ts} "
                f"rows {len(meta['ev'])} {time.time() - t0:.0f}s")

    final = {pk: build_snap(cells[pk], KINDS[pk[1]]) for pk in pairs}
    return Replay(cols, meta, final, snaps_cut, scored_matches, len(matches),
                  first_ts, cut_ts, matches[-1][0], {}, cells,
                  acc_f or {}, acc_df or {}, snaps_df or {})



# ---------------------------------------------------------------------------
# pass 2: probabilities at the x.5 ladder, SHEET's own predictive family
# ---------------------------------------------------------------------------

P_CLIP = 0.02
HI_CONF = 0.70  # a rung "prints" at confidence >= 0.70: rungs where TODAY's p
# (F) is >= 0.70 or <= 0.30 are the printable ones, the same rungs for all


def market_of(base_i: int, unit: int) -> str:
    return f"{BASES[base_i]}_{'for' if unit < 2 else 'total'}"


def row_losses(
    market: str, mean: float, var: float, n: int, y: float,
    centres: Sequence[float], anchor: float,
) -> tuple[list[float], list[tuple[float, float, int, float, float, int]],
           list[list[float]], list[float], list[bool]]:
    """Per variant centre: the squared centre error, the loss sums
    (ll_all, br_all, n_all, ll_hi, br_hi, n_hi) over the ladder around
    `anchor` (the high-confidence rungs are chosen on the anchor centre), and
    the clipped P(OVER) of every rung; plus the rung outcomes and hi mask."""
    from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd
    from scripts.sofa import calibrate_from_cache as cc

    lines = cc.lines_for(anchor)
    sd_a = sheet_predictive_sd(market, "football", mean, var, n, anchor)
    hi = []
    for line in lines:
        pa = sheet_count_p_raw(market, anchor, sd_a, line, "OVER")
        hi.append(max(pa, 1.0 - pa) >= HI_CONF)
    outcomes = [1.0 if y > line else 0.0 for line in lines]
    se = [(c - y) ** 2 for c in centres]
    res: list[tuple[float, float, int, float, float, int]] = []
    ps: list[list[float]] = []
    for c in centres:
        sd = sheet_predictive_sd(market, "football", mean, var, n, c)
        la = ba = lh = bh = 0.0
        nh = 0
        pl: list[float] = []
        for line, o, h in zip(lines, outcomes, hi, strict=True):
            p = sheet_count_p_raw(market, c, sd, line, "OVER")
            p = min(1.0 - P_CLIP, max(P_CLIP, p))
            pl.append(p)
            ll = -(math.log(p) if o else math.log(1.0 - p))
            br = (p - o) ** 2
            la += ll
            ba += br
            if h:
                lh += ll
                bh += br
                nh += 1
        res.append((la, ba, len(lines), lh, bh, nh))
        ps.append(pl)
    return se, res, ps, outcomes, hi


def _chunk(args: tuple[Any, ...]) -> tuple[Any, Any, Any, Any, Any]:
    import numpy as np

    (rows,) = args
    k = len(rows)
    ncols = len(rows[0][5]) if k else 0
    se = np.zeros((k, ncols))
    lad = np.zeros((k, ncols, 6))
    pp = np.zeros((k, ncols, 9), dtype=np.float32)
    oo = np.zeros((k, 9), dtype=np.int8)
    hh = np.zeros((k, 9), dtype=bool)
    for i, (market, mean, var, n, y, centres, anchor) in enumerate(rows):
        s_, res, ps, outs, hi = row_losses(market, mean, var, n, y, centres, anchor)
        se[i] = s_
        lad[i] = res
        pp[i] = ps
        oo[i] = outs
        hh[i] = hi
    return se, lad, pp, oo, hh


def ladder_pass(rep: Replay, procs: int = 3, log: Any = None) -> dict[str, Any]:
    """Squared centre error, ladder losses and rung probabilities of every
    logged row and column (numpy; 'se' (rows, cols), 'ladder' (rows, cols, 6),
    'p' (rows, cols, 9) float32, 'o' and 'hi' (rows, 9))."""
    import multiprocessing as mp

    import numpy as np

    m = rep.meta
    nrows = len(m["ev"])
    anchor = rep.cols["today_F"]
    size = 2000

    def chunks() -> Iterable[tuple[Any, ...]]:
        for lo in range(0, nrows, size):
            rows = []
            for i in range(lo, min(lo + size, nrows)):
                rows.append((
                    market_of(int(m["base"][i]), int(m["unit"][i])), m["mean"][i],
                    m["var"][i], int(m["n"][i]), m["y"][i],
                    [rep.cols[c][i] for c in COLS], anchor[i],
                ))
            yield (rows,)

    parts: list[tuple[Any, ...]] = []
    done = 0
    with mp.Pool(procs) as pool:
        for k, part in enumerate(pool.imap(_chunk, chunks())):
            parts.append(part)
            done += len(part[0])
            if log and k % 40 == 0:
                log(f"ladder {done}/{nrows}")
    return {
        "se": np.concatenate([q[0] for q in parts]),
        "ladder": np.concatenate([q[1] for q in parts]),
        "p": np.concatenate([q[2] for q in parts]),
        "o": np.concatenate([q[3] for q in parts]),
        "hi": np.concatenate([q[4] for q in parts]),
    }


CAL_BINS = 40
CAL_SMOOTH = 30.0


def calibrated_losses(
    loss: dict[str, Any], train: Any, evalm: Any, group: Any
) -> tuple[Any, Any]:
    """Log-loss after the production step: a calibration map per
    (market group, column) FITTED ON THE TRAINING ROWS (matches before the
    cut) and applied to the evaluation rows - the way a curve is fitted on the
    replayed history and read on a new day.  The map is 40 equal bins of the
    rung's P(OVER), the bin's realised frequency smoothed toward the bin's
    mean p (30 pseudo-rungs).  Returns per-row sums over all rungs and over
    the high-confidence rungs, shape (rows, cols) each, for evaluation rows
    (zeros elsewhere)."""
    import numpy as np

    p_all, o_all, hi_all = loss["p"], loss["o"], loss["hi"]
    nrows, ncols, _ = p_all.shape
    out_all = np.zeros((nrows, ncols))
    out_hi = np.zeros((nrows, ncols))
    lo, width = P_CLIP, (1.0 - 2 * P_CLIP) / CAL_BINS
    for g in np.unique(group):
        tr = np.where(train & (group == g))[0]
        ev = np.where(evalm & (group == g))[0]
        if len(tr) == 0 or len(ev) == 0:
            continue
        for c in range(ncols):
            ptr = p_all[tr, c, :].astype(np.float64).ravel()
            otr = o_all[tr, :].astype(np.float64).ravel()
            b = np.clip(((ptr - lo) / width).astype(int), 0, CAL_BINS - 1)
            n_b = np.bincount(b, minlength=CAL_BINS).astype(np.float64)
            s_b = np.bincount(b, weights=otr, minlength=CAL_BINS)
            pm_b = np.bincount(b, weights=ptr, minlength=CAL_BINS)
            mid = lo + width * (np.arange(CAL_BINS) + 0.5)
            pbar = np.where(n_b > 0, pm_b / np.maximum(n_b, 1), mid)
            q_b = (s_b + CAL_SMOOTH * pbar) / (n_b + CAL_SMOOTH)
            q_b = np.clip(q_b, 1e-4, 1 - 1e-4)
            pe = p_all[ev, c, :].astype(np.float64)
            be = np.clip(((pe - lo) / width).astype(int), 0, CAL_BINS - 1)
            q = q_b[be]
            oe = o_all[ev, :]
            ll = -(oe * np.log(q) + (1 - oe) * np.log(1 - q))
            out_all[ev, c] = ll.sum(axis=1)
            out_hi[ev, c] = (ll * hi_all[ev, :]).sum(axis=1)
    return out_all, out_hi


# ---------------------------------------------------------------------------
# analysis: match-level bootstrap of paired differences
# ---------------------------------------------------------------------------

METRICS = ("se", "ll_all", "br_all", "ll_hi", "br_hi", "lc_all", "lc_hi")


class Boot:
    """Match-level (cluster) bootstrap: one weight matrix for every statistic,
    so a statistic is two matrix-vector products."""

    def __init__(self, event_ids: Any, reps: int = 300, seed: int = 7):
        import numpy as np

        self.np = np
        uniq, inv = np.unique(np.asarray(event_ids), return_inverse=True)
        self.inv = inv
        self.m = len(uniq)
        rng = np.random.default_rng(seed)
        self.w = rng.multinomial(self.m, np.full(self.m, 1.0 / self.m),
                                 size=reps).astype(np.float64)

    def ratio(self, num: Any, den: Any, mask: Any) -> dict[str, float]:
        """sum(num)/sum(den) over `mask` rows, with its 95% match bootstrap."""
        np = self.np
        d = np.bincount(self.inv[mask], weights=num[mask], minlength=self.m)
        c = np.bincount(self.inv[mask], weights=den[mask], minlength=self.m)
        tot_c = c.sum()
        if tot_c <= 0:
            return {"est": float("nan"), "lo": float("nan"), "hi": float("nan"),
                    "n": 0, "matches": 0}
        boots = (self.w @ d) / np.maximum(self.w @ c, 1e-12)
        return {
            "est": float(d.sum() / tot_c),
            "lo": float(np.percentile(boots, 2.5)),
            "hi": float(np.percentile(boots, 97.5)),
            "n": int(mask.sum()),
            "matches": int((c > 0).sum()),
        }


def metric_arrays(loss: dict[str, Any], col: int) -> dict[str, tuple[Any, Any]]:
    """(value per row, weight per row) for each of METRICS at one column."""
    import numpy as np

    lad = loss["ladder"][:, col, :]
    ones = np.ones(lad.shape[0])
    return {
        "se": (loss["se"][:, col], ones),
        "ll_all": (lad[:, 0], lad[:, 2]),
        "br_all": (lad[:, 1], lad[:, 2]),
        "ll_hi": (lad[:, 3], lad[:, 5]),
        "br_hi": (lad[:, 4], lad[:, 5]),
        "lc_all": (loss["lc_all"][:, col], lad[:, 2]),
        "lc_hi": (loss["lc_hi"][:, col], lad[:, 5]),
    }


def compare(
    boot: Boot, loss: dict[str, Any], mask: Any, mode: str,
    baseline: str = "today",
    variants: Sequence[str] = ALL_VARIANTS,
) -> dict[str, Any]:
    """For one stratum: the baseline's level and every variant's paired
    difference (variant - baseline) per metric, 95% match bootstrap."""
    base_arr = metric_arrays(loss, COLS.index(f"{baseline}_{mode}"))
    if mode == "E":
        variants = [v for v in variants if v in E_VARIANTS]
    out: dict[str, Any] = {"n_units": int(mask.sum())}
    out[baseline] = {
        m: boot.ratio(v, w, mask) for m, (v, w) in base_arr.items()
    }
    for var in variants:
        if var == baseline:
            continue
        arr = metric_arrays(loss, COLS.index(f"{var}_{mode}"))
        out[var] = {
            m: boot.ratio(arr[m][0] - base_arr[m][0], base_arr[m][1], mask)
            for m in METRICS
        }
    return out


def league_info_test(
    boot: Boot, rep_meta: dict[str, Any], cols: dict[str, Any], mask: Any,
    variant: str = "ebnl_F",
) -> dict[str, float]:
    """Does the league carry information beyond the team's own window?
    Slope of (y - centre_without_league) on the league's EB deviation
    dl = P_league - G, over `mask` units (cluster bootstrap)."""
    resid = rep_meta["y"] - cols[variant]
    dl = rep_meta["dl"]
    return boot.ratio(resid * dl, dl * dl, mask)


def league_table(
    cells: Cells, snap: Snap, names: dict[int, str], kind: str,
    min_matches: int = 20,
) -> list[dict[str, Any]]:
    """Per league: raw mean, EB-shrunk mean, 95% credible interval of the
    league effect, n, and whether the interval excludes the global mean."""
    by_comp: dict[int, list[tuple[float, float]]] = collections.defaultdict(list)
    for (comp, _team), (n, sm, _sq) in cells.items():
        if n > 0:
            by_comp[comp].append((n, sm / n))
    rows: list[dict[str, Any]] = []
    for comp, cl in by_comp.items():
        big_n = sum(n for n, _ in cl)
        matches = big_n / 2.0
        if comp == 0 or matches < min_matches:
            continue
        mean = sum(n * m for n, m in cl) / big_n
        sq = sum(n * n for n, _ in cl) / (big_n * big_n)
        cls = snap.cls.get(comp, 0)
        v = snap.s2_t[cls] * sq + snap.s2_w / big_n
        w = snap.s2_l / (snap.s2_l + v) if snap.s2_l > 0 else 0.0
        post_sd = math.sqrt(max(w * v, 0.0))
        shrunk = snap.G + w * (mean - snap.G)
        lo, hi = shrunk - 1.96 * post_sd, shrunk + 1.96 * post_sd
        flag = "HIGH" if lo > snap.G else ("LOW" if hi < snap.G else "")
        # distance of the credible interval's near bound from the global mean:
        # what is left of the deviation once the uncertainty is taken off
        bound = lo - snap.G if flag == "HIGH" else (
            hi - snap.G if flag == "LOW" else 0.0)
        rows.append({
            "comp": comp, "name": names.get(comp, str(comp)), "matches": matches,
            "teams": len(cl), "raw": mean, "shrunk": shrunk, "sd": post_sd,
            "lo": lo, "hi": hi, "dev": shrunk - snap.G,
            "raw_dev": mean - snap.G, "weight": w,
            "flag": flag, "bound_dev": bound,
            "material": bool(flag) and abs(bound) >= MATERIAL_REL * snap.G,
        })
    rows.sort(key=lambda r: -r["dev"])
    return rows



# ---------------------------------------------------------------------------
# assemble + CLI
# ---------------------------------------------------------------------------

def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")


def snap_summary(snap: Snap) -> dict[str, Any]:
    total = snap.s2_l + sum(snap.s2_t) / max(len(snap.s2_t), 1) + snap.s2_w
    return {
        "G": snap.G, "s2_within": snap.s2_w, "s2_team_by_class": list(snap.s2_t),
        "k_team_by_class": [snap.k_team(c) for c in range(N_CLASSES)],
        "s2_team_without_league": snap.s2_t_nolg, "k_without_league": snap.k_nolg(),
        "s2_league": snap.s2_l,
        "league_share_of_total_var": snap.s2_l / total if total > 0 else 0.0,
        "n_cells": snap.n_cells,
        "leagues_with_prior": len(snap.today_prior), "leagues": len(snap.P),
    }


def assemble(
    rep: Replay, loss: dict[str, Any], names: dict[int, str], reps: int = 300,
    log: Any = None,
) -> dict[str, Any]:
    import numpy as np

    m = {k: np.asarray(v) for k, v in rep.meta.items()}
    cols = {k: np.asarray(v) for k, v in rep.cols.items()}
    train = m["train"] == 1
    group = m["base"] * 2 + (m["unit"] == 2)
    loss["lc_all"], loss["lc_hi"] = calibrated_losses(loss, train, ~train, group)
    n_train_matches = int(len(np.unique(m["ev"][train])))
    sel = ~train
    m = {k: v[sel] for k, v in m.items()}
    cols = {k: v[sel] for k, v in cols.items()}
    loss = {k: v[sel] for k, v in loss.items()}
    boot = Boot(m["ev"].astype(np.int64), reps=reps)
    grp = (m["unit"] == 2).astype(int)  # 0 own count, 1 match total
    ok = m["nmin"] >= MIN_SAMPLE
    sd_l = np.zeros(len(m["ev"]))
    for (bi, ki), snap in rep.snaps_cut.items():
        sel = (m["base"] == bi) & (grp == ki)
        sd_l[sel] = math.sqrt(snap.s2_l)
    unusual = np.abs(m["dl"]) >= sd_l
    tuned = {
        f"{BASES[bi]}_{KINDS[ki]}": {
            "K_best_raw_prior": a.best_k(), "K_best_eb_prior": a.best_k(True),
            "K_best_decayed": rep.acc_cut_d[(bi, ki)].best_k() if rep.acc_cut_d
            else None,
            "slope_by_class": [a.beta(c) for c in range(N_CLASSES)],
            "rows_tuned_on": a.kn,
        }
        for (bi, ki), a in sorted(rep.acc_cut.items())
    }
    out: dict[str, Any] = {
        "tuned_at_cut": tuned,
        "meta": {
            "matches_total": rep.n_matches_total,
            "history_from": _iso(rep.first_ts), "cut": _iso(rep.cut_ts),
            "last_match": _iso(rep.last_ts),
            "eval_days": len({int(t) // 86400 for t in m["ts"]}),
            "eval_matches": int(len(np.unique(m["ev"]))),
            "eval_units": int(len(m["ev"])), "bootstrap_reps": reps,
            "train_matches_for_calibration": n_train_matches,
            "class_edges_matches": list(CLASS_EDGES),
            "K_TODAY": K_TODAY, "K_GRID": list(K_GRID),
        },
        "components_at_cut": {
            f"{BASES[bi]}_{KINDS[ki]}": snap_summary(sn)
            for (bi, ki), sn in sorted(rep.snaps_cut.items())
        },
    }
    strata: dict[str, Any] = {}
    gname = ("for", "total")

    def run(name: str, mask: Any, modes: Sequence[str] = ("F",)) -> None:
        if int(mask.sum()) < 200:
            return
        strata[name] = {md: compare(boot, loss, mask, md) for md in modes}
        if log:
            log(f"stratum {name} n={int(mask.sum())}")

    for g in (0, 1):
        for bi, base in enumerate(BASES):
            run(f"{base}_{gname[g]}", ok & (grp == g) & (m["base"] == bi),
                ("F", "E"))
        run(f"ALL_{gname[g]}", ok & (grp == g), ("F", "E"))
        for lo, hi in ((3, 4), (5, 7), (8, 9), (10, 99)):
            run(f"ALL_{gname[g]}|nmin {lo}-{hi}",
                (m["nmin"] >= lo) & (m["nmin"] <= hi) & (grp == g))
        for c in range(N_CLASSES):
            run(f"ALL_{gname[g]}|league_class {c}", ok & (grp == g) & (m["cls"] == c))
        run(f"ALL_{gname[g]}|unusual_league", ok & (grp == g) & unusual)
        run(f"ALL_{gname[g]}|typical_league", ok & (grp == g) & ~unusual)
        for bi, base in enumerate(BASES):
            run(f"{base}_{gname[g]}|unusual_league",
                ok & (grp == g) & (m["base"] == bi) & unusual)
            for lo, hi in ((3, 7),):
                run(f"{base}_{gname[g]}|nmin {lo}-{hi}",
                    (m["nmin"] >= lo) & (m["nmin"] <= hi) & (grp == g)
                    & (m["base"] == bi))
    out["strata"] = strata
    info: dict[str, Any] = {}
    for g in (0, 1):
        for bi, base in enumerate(BASES):
            info[f"{base}_{gname[g]}"] = league_info_test(
                boot, m, cols, ok & (grp == g) & (m["base"] == bi))
        info[f"ALL_{gname[g]}"] = league_info_test(boot, m, cols, ok & (grp == g))
        info[f"ALL_{gname[g]}|unusual_league"] = league_info_test(
            boot, m, cols, ok & (grp == g) & unusual)
        info[f"ALL_{gname[g]}|nmin 3-7"] = league_info_test(
            boot, m, cols, (m["nmin"] < MIN_SAMPLE) & (grp == g))
    out["league_info_slope"] = info
    leagues: dict[str, Any] = {}
    for (bi, ki), snap in sorted(rep.snaps_final.items()):
        key = f"{BASES[bi]}_{KINDS[ki]}"
        leagues[key] = {
            "global_mean": snap.G, "s2_league": snap.s2_l,
            "components": snap_summary(snap),
            "rows": league_table(rep.cells_final[(bi, ki)], snap, names, KINDS[ki]),
        }
    out["leagues"] = leagues
    return out


def _status(msg: str, path: Path | None) -> None:
    line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if path is not None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def cmd_run(args: argparse.Namespace) -> int:
    matches, names = pickle.loads(Path(args.pkl).read_bytes())
    status = Path(args.status) if args.status else None

    def log(msg: str) -> None:
        _status(msg, status)

    lo = int(datetime.fromisoformat(args.from_date).replace(tzinfo=UTC).timestamp())
    hi = int(datetime.fromisoformat(args.to_date).replace(tzinfo=UTC).timestamp())
    # a "finished" match dated in the future is a bad listing; statistics exist
    # from 2024-10 only, an older history is another regime
    matches = [x for x in matches if lo <= x[0] < hi]
    if args.max_matches:
        matches = matches[-args.max_matches:]
    cut_ts = matches[-1][0] - args.eval_days * 86400
    rep = replay(matches, cut_ts, log=log)
    log(f"replay done: {len(rep.meta['ev'])} rows")
    loss = ladder_pass(rep, procs=args.procs, log=log)
    log("ladder done")
    if args.scratch:
        sc = Path(args.scratch)
        sc.mkdir(parents=True, exist_ok=True)
        (sc / "rows.pkl").write_bytes(pickle.dumps((rep.meta, rep.cols)))
    results = assemble(rep, loss, names, reps=args.reps, log=log)
    Path(args.out).write_text(json.dumps(results, indent=1, default=float),
                              encoding="utf-8")
    log(f"wrote {args.out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("db")
    ex.add_argument("out")
    rn = sub.add_parser("run")
    rn.add_argument("--pkl", required=True)
    rn.add_argument("--out", required=True)
    rn.add_argument("--eval-days", type=int, default=120)
    rn.add_argument("--procs", type=int, default=3)
    rn.add_argument("--reps", type=int, default=300)
    rn.add_argument("--status")
    rn.add_argument("--scratch")
    rn.add_argument("--max-matches", type=int, default=0)
    rn.add_argument("--from-date", default="2024-09-01")
    rn.add_argument("--to-date", default="2026-10-08")
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        n = extract(Path(args.db), Path(args.out))
        print(f"extracted {n} matches")
        return 0
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
