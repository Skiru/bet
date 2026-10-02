#!/usr/bin/env python3
"""Fit bet.sofa.player_model's constants on the stored history - no prices.

The replay. For every basketball / hockey game with a stored box
(sofa_event_stats.lineups_json) and every player who appeared in it, the
model's sample is rebuilt strictly before the game exactly as
player_model.line_probability builds it - both teams' own `last` listings
(sofa_listing_event) before the earlier clock minus CUTOFF_MARGIN_S, the game
itself excluded by id, appearances_from_lineups, own_sample, the pool of the
other players - and the predicted distribution of every family's statistic
(player_model.count_distribution / signed_distribution) is scored on what the
player actually did:

  * log loss and ranked probability score of the count;
  * the binary P(over) at a realistic line: the line Superbet prints for
    that family (read from runs/sofa/shadow/<sport>/*/snapshots.jsonl) that
    is nearest the player's own sample median (the newest 20 values), or the
    median's half-integer when the snapshots print none for the family -
    the report says which (`line_source`). Brier, the logit calibration slope
    and calibration bands of that binary.

The replay is in memory (History) but reproduces load_appearances row for
row; tests/sofa/test_player_model.py checks it against line_probability on
a fixture database, and that no game after the cut, nor the game itself,
enters a sample.

The fit. A time split: train on games before --cut (default 2026-07-01),
test on the rest. Coordinate descent on the train split's mean (over
families) of the per-family mean log loss: first basketball over the shared
constants (hl_minutes, k_phi, max_sample) and its own (pool, sig_a,
prior_games); then hockey over its own (pool, sig_a, prior_games,
prior_games_signed) with the shared ones fixed. Last, per sport, the
calibration slope b of sigmoid(b logit p) by maximum likelihood on the train
split's binary rows of the count families (plus-minus is not mapped). Every
number is reported on train and test, and against player_rate_v1's frozen
constants on the same rows, so an overfit shows.

A fit, never a pipeline step: the database is opened read-only, and the
output goes only where --out names it (config/sofa_player_model.json is the
file the model reads; never rewrite it mid-day).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_player_model.py \\
        --out /tmp/sofa_player_model.json [--cut 2026-07-01] [--sport hockey]
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import multiprocessing
import os
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import bet.sofa.player_model as pm  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.joint import normal_cdf  # noqa: E402
from bet.sofa.shadow import (  # noqa: E402
    PLAYER_MARKETS,
    SPORTS,
    PlayerSpec,
    SportKey,
    player_stat_value,
)

DEFAULT_CUT = "2026-07-01"
# Own appearances stored per record: above every max_sample the grid tries,
# with room for games whose box lacks a family's statistic.
STORE = 70
LINE_SAMPLE = 20
BANDS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)
EPS = 1e-12

Vals = tuple[float | None, ...]
Agg = list[float]  # sum_v, sum_s, sum_sq, n


def family_specs(sport: SportKey) -> list[PlayerSpec]:
    """One spec per family, in PLAYER_MARKETS order."""
    out: list[PlayerSpec] = []
    seen: set[str] = set()
    for spec in PLAYER_MARKETS[sport].values():
        if spec.family not in seen:
            seen.add(spec.family)
            out.append(spec)
    return out


# --- the history, in memory ------------------------------------------------------


@dataclass
class History:
    """Listed games, team listings and stored boxes of one sport."""

    sport: SportKey
    events: dict[int, tuple[int, int, int]]  # eid -> (start_ts, home, away)
    listing: dict[int, tuple[list[int], list[int]]]  # team -> (ts asc, eids)
    lineups: dict[int, str]
    _cache: dict[tuple[int, int], list[pm.Appearance]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        sport: SportKey,
        events: dict[int, tuple[int, int, int]],
        listing_rows: Iterable[tuple[int, int, int]],
        lineups: dict[int, str],
    ) -> History:
        """`listing_rows`: (team, event id, start_ts) of kind 'last'."""
        by_team: dict[int, list[tuple[int, int]]] = defaultdict(list)
        for team, eid, ts in listing_rows:
            by_team[int(team)].append((int(ts), int(eid)))
        listing = {}
        for team, rows in by_team.items():
            rows.sort()
            listing[team] = ([ts for ts, _ in rows], [e for _, e in rows])
        return cls(sport, events, listing, lineups)

    @classmethod
    def from_db(cls, conn: sqlite3.Connection, sport: SportKey) -> History:
        slug = SPORTS[sport].sofascore_slug
        events: dict[int, tuple[int, int, int]] = {}
        for eid, ts, text in conn.execute(
            "SELECT event_id, start_ts, event_json FROM sofa_listed_event "
            "WHERE sport = ?",
            (slug,),
        ):
            ev = json.loads(text)
            home = (ev.get("homeTeam") or {}).get("id")
            away = (ev.get("awayTeam") or {}).get("id")
            start = ts if isinstance(ts, int) else ev.get("startTimestamp")
            if (
                isinstance(home, int)
                and isinstance(away, int)
                and isinstance(start, int)
            ):
                events[int(eid)] = (int(start), home, away)
        lineups: dict[int, str] = {}
        ids = list(events)
        for i in range(0, len(ids), 900):
            chunk = ids[i : i + 900]
            marks = ",".join("?" * len(chunk))
            for eid, text in conn.execute(
                "SELECT sofascore_event_id, lineups_json FROM sofa_event_stats "
                f"WHERE lineups_json IS NOT NULL AND sofascore_event_id IN ({marks})",
                chunk,
            ):
                lineups[int(eid)] = str(text)
        teams = {t for _, h, a in events.values() for t in (h, a)}
        rows: list[tuple[int, int, int]] = []
        for team in teams:
            rows.extend(
                (team, int(eid), int(ts))
                for eid, ts in conn.execute(
                    "SELECT event_id, start_ts FROM sofa_listing_event "
                    "WHERE entity_id = ? AND kind = 'last'",
                    (team,),
                )
            )
        return cls.build(sport, events, rows, lineups)

    def appearances_in(self, eid: int, team: int) -> list[pm.Appearance]:
        key = (eid, team)
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        out: list[pm.Appearance] = []
        text = self.lineups.get(eid)
        if text:
            try:
                payload = json.loads(text)
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                ts = self._ts(eid, team)
                out = pm.appearances_from_lineups(self.sport, payload, eid, ts, team)
        if len(self._cache) > 300_000:
            self._cache.clear()
        self._cache[key] = out
        return out

    def _ts(self, eid: int, team: int) -> int:
        tss, eids = self.listing.get(team, ([], []))
        for ts, e in zip(tss, eids, strict=True):
            if e == eid:
                return ts
        return self.events[eid][0]

    def games_before(
        self, team: int, before_ts: int, exclude: int | None
    ) -> list[tuple[int, int]]:
        """pm.listed_games, in memory."""
        tss, eids = self.listing.get(team, ([], []))
        i = bisect.bisect_left(tss, before_ts)
        lo = max(0, i - (pm.HISTORY_GAMES + 1))
        games = [(eids[j], tss[j]) for j in range(i - 1, lo - 1, -1)]
        return [g for g in games if exclude is None or g[0] != exclude][
            : pm.HISTORY_GAMES
        ]

    def appearances_before(
        self, teams: Sequence[int], before_ts: int, exclude: int | None
    ) -> list[pm.Appearance]:
        """pm.load_appearances, in memory (same games, same order)."""
        out: list[pm.Appearance] = []
        for team in teams:
            for eid, ts in self.games_before(team, before_ts, exclude):
                if eid not in self.lineups:
                    continue
                for a in self.appearances_in(eid, team):
                    out.append(a if a.ts == ts else replace(a, ts=ts))
        return out


# --- replay records ----------------------------------------------------------------


@dataclass(frozen=True)
class Record:
    """One player's game: what he did, and what the model knew before it."""

    eid: int
    ts: int
    team: int
    pid: int
    act_s: float
    act: Vals
    own: tuple[tuple[int, float, Vals], ...]  # (ts, seconds, values), newest first
    pools: dict[str, tuple[pm.Pool, ...]]  # kind -> one Pool per family
    # player_rate_v1's pool dispersion (median raw variance / mean of the
    # group's other players), for the before/after reference only.
    raw_phi: tuple[float | None, ...]


def _vals(a: pm.Appearance, specs: Sequence[PlayerSpec]) -> Vals:
    out: list[float | None] = []
    for spec in specs:
        v = player_stat_value(a.stats, spec)
        out.append(v if isinstance(v, float) else None)
    return tuple(out)


def replay_game(
    history: History, eid: int, specs: Sequence[PlayerSpec]
) -> list[Record]:
    """Every appearing player's Record for game `eid`."""
    if eid not in history.events or eid not in history.lineups:
        return []
    start, home, away = history.events[eid]
    teams = [home, away]
    before = pm.history_cutoff(start, start)
    apps = history.appearances_before(teams, before, eid)
    nf = len(specs)
    vals = [_vals(a, specs) for a in apps]
    # Per family: group sums, player x group pairs (for the pool's phi).
    by_group: dict[str, list[Agg]] = defaultdict(lambda: [[0.0] * 4 for _ in specs])
    pairs_g: dict[tuple[str, int], list[list[tuple[float, float]]]] = defaultdict(
        lambda: [[] for _ in specs]
    )
    pairs_all: dict[int, list[list[tuple[float, float]]]] = defaultdict(
        lambda: [[] for _ in specs]
    )
    mine: dict[int, list[int]] = defaultdict(list)
    for i, (a, vs) in enumerate(zip(apps, vals, strict=True)):
        mine[a.player_id].append(i)
        agg = by_group[a.group]
        for f, v in enumerate(vs):
            if v is None:
                continue
            x = agg[f]
            x[0] += v
            x[1] += a.seconds
            x[2] += v * v
            x[3] += 1
            pairs_g[(a.group, a.player_id)][f].append((a.seconds, v))
            pairs_all[a.player_id][f].append((a.seconds, v))
    phis_g: dict[str, list[list[tuple[float, int]]]] = defaultdict(
        lambda: [[] for _ in specs]
    )
    phis_all: list[list[tuple[float, int]]] = [[] for _ in specs]
    raw_g: dict[str, list[list[tuple[float, int]]]] = defaultdict(
        lambda: [[] for _ in specs]
    )
    for (g, pid), per in pairs_g.items():
        for f in range(nf):
            if len(per[f]) >= pm.MIN_APPEARANCES:
                phi = pm.pearson_dispersion(per[f])
                if phi is not None:
                    phis_g[g][f].append((phi, pid))
                xs = [v for _, v in per[f]]
                m = statistics.fmean(xs)
                if m > 0:
                    raw_g[g][f].append((statistics.variance(xs) / m, pid))
    for pid, per in pairs_all.items():
        for f in range(nf):
            if len(per[f]) >= pm.MIN_APPEARANCES:
                phi = pm.pearson_dispersion(per[f])
                if phi is not None:
                    phis_all[f].append((phi, pid))
    total_all = [
        [sum(by_group[g][f][k] for g in by_group) for k in range(4)] for f in range(nf)
    ]
    out: list[Record] = []
    for team in teams:
        for target in history.appearances_in(eid, team):
            pid = target.player_id
            idx = sorted(
                mine.get(pid, []), key=lambda i: (-apps[i].ts, apps[i].event_id)
            )
            seen: set[int] = set()
            uniq: list[int] = []
            for i in idx:
                if apps[i].event_id not in seen:
                    seen.add(apps[i].event_id)
                    uniq.append(i)
            if len(uniq) < pm.MIN_APPEARANCES:
                continue
            group_pools: list[pm.Pool] = []
            all_pools: list[pm.Pool] = []
            raw_phi: list[float | None] = []
            for f in range(nf):
                first = next((i for i in uniq if vals[i][f] is not None), None)
                g = apps[first].group if first is not None else apps[uniq[0]].group
                sub_g = [0.0, 0.0, 0.0, 0.0]
                sub_a = [0.0, 0.0, 0.0, 0.0]
                for i in mine[pid]:
                    v = vals[i][f]
                    if v is None:
                        continue
                    row = (v, apps[i].seconds, v * v, 1.0)
                    for k in range(4):
                        sub_a[k] += row[k]
                        if apps[i].group == g:
                            sub_g[k] += row[k]
                gg = by_group[g][f] if g in by_group else [0.0] * 4
                pg = [ph for ph, p in phis_g[g][f] if p != pid] if g in phis_g else []
                pa = [ph for ph, p in phis_all[f] if p != pid]
                pr = [ph for ph, p in raw_g[g][f] if p != pid] if g in raw_g else []
                raw_phi.append(statistics.median(pr) if pr else None)
                group_pools.append(
                    pm.Pool(
                        gg[0] - sub_g[0],
                        gg[1] - sub_g[1],
                        gg[2] - sub_g[2],
                        int(round(gg[3] - sub_g[3])),
                        statistics.median(pg) if pg else None,
                    )
                )
                ta = total_all[f]
                all_pools.append(
                    pm.Pool(
                        ta[0] - sub_a[0],
                        ta[1] - sub_a[1],
                        ta[2] - sub_a[2],
                        int(round(ta[3] - sub_a[3])),
                        statistics.median(pa) if pa else None,
                    )
                )
            out.append(
                Record(
                    eid,
                    start,
                    team,
                    pid,
                    target.seconds,
                    _vals(target, specs),
                    tuple((apps[i].ts, apps[i].seconds, vals[i]) for i in uniq[:STORE]),
                    {"group": tuple(group_pools), "all": tuple(all_pools)},
                    tuple(raw_phi),
                )
            )
    return out


# --- scoring -----------------------------------------------------------------------


def record_distribution(
    rec: Record, f: int, family: str, prm: pm.SportParams
) -> tuple[dict[int, float], float] | None:
    """The model's pmf and mean for family f of this record, or None (thin)."""
    own = family_sample(rec, f, prm.max_sample)
    if len(own) < pm.MIN_APPEARANCES:
        return None
    pool = rec.pools[prm.pool][f]
    if family in pm.SIGNED_FAMILIES:
        return pm.signed_distribution([v for _, v in own], pool, prm)
    counts, mean = pm.count_distribution(own, pool, prm)
    return dict(enumerate(counts)), mean


def family_sample(rec: Record, f: int, limit: int) -> list[tuple[float, float]]:
    """(seconds, value) of family f, newest first, at most `limit`."""
    return [(s, x) for _, s, v in rec.own if (x := v[f]) is not None][:limit]


# player_rate_v1's frozen constants and formulas: the before of before/after.
V1 = {"n_minutes": 5, "prior_games": 3.0, "k_phi": 5.0, "max_sample": 20}


def v1_distribution(
    rec: Record, f: int, family: str
) -> tuple[dict[int, float], float] | None:
    own = family_sample(rec, f, int(V1["max_sample"]))
    n = len(own)
    if n < pm.MIN_APPEARANCES:
        return None
    raw_phi = rec.raw_phi[f]
    pool = rec.pools["group"][f]
    xs = [v for _, v in own]
    k0 = float(V1["prior_games"])
    if family in pm.SIGNED_FAMILIES:
        pool_mean = pool.sum_v / pool.n if pool.n else 0.0
        pool_var = (
            (pool.sum_sq - pool.n * pool_mean**2) / (pool.n - 1)
            if pool.n >= 2
            else statistics.variance(xs)
        )
        mean = (sum(xs) + k0 * pool_mean) / (n + k0)
        var = (n * statistics.pvariance(xs) + k0 * pool_var) / (n + k0)
        sd = max(math.sqrt(max(var, 0.0)), pm.MIN_SD_SIGNED)
        lo, hi = math.floor(mean - 10 * sd) - 1, math.ceil(mean + 10 * sd) + 1
        return {
            k: normal_cdf((k + 0.5 - mean) / sd) - normal_cdf((k - 0.5 - mean) / sd)
            for k in range(lo, hi + 1)
        }, mean
    seconds = sum(s for s, _ in own)
    total = sum(xs)
    mean_s = seconds / n
    pool_rate = pool.sum_v / pool.sum_s if pool.sum_s > 0 else total / seconds
    k = k0 * mean_s
    rate = (total + k * pool_rate) / (seconds + k)
    exp_s = statistics.fmean(s for s, _ in own[: int(V1["n_minutes"])])
    mean = rate * exp_s
    phi_pool = raw_phi if raw_phi is not None else 1.0
    m = total / n
    phi_own = statistics.variance(xs) / m if m > 0 else None
    kp = float(V1["k_phi"])
    phi = (n * (phi_own if phi_own is not None else phi_pool) + kp * phi_pool) / (
        n + kp
    )
    variance = max(phi, 1.0) * mean
    kmax = int(mean + 12.0 * math.sqrt(max(variance, 1.0)) + 12)
    return dict(enumerate(pm.nb_pmf(mean, variance, kmax))), mean


def nearest_line(values: Sequence[float], printed: Sequence[float]) -> float:
    med = statistics.median(values)
    if not printed:
        return math.floor(med) + 0.5
    return min(printed, key=lambda x: (abs(x - med), x))


@dataclass
class Score:
    ll: float
    rps: float
    p_over: float
    y_over: float


def score_pmf(pmf: dict[int, float], y: float, line: float) -> Score:
    yi = int(round(y))
    keys = sorted(pmf)
    cdf = 0.0
    rps = 0.0
    for k in keys:
        cdf += pmf[k]
        rps += (cdf - (1.0 if yi <= k else 0.0)) ** 2
    p_over = sum(m for k, m in pmf.items() if k > line)
    return Score(
        -math.log(max(pmf.get(yi, 0.0), EPS)),
        rps,
        min(max(p_over, 1e-6), 1.0 - 1e-6),
        1.0 if y > line else 0.0,
    )


# Worker state (fork): set before the pool starts.
_STATE: dict[str, Any] = {}


def _score_chunk(
    args: tuple[list[int], pm.SportParams | None, bool],
) -> list[tuple[Any, ...]]:
    """Rows (record index, family, split, ll, rps, p_over, y_over)."""
    idxs, prm, use_calibration = args
    recs: list[Record] = _STATE["records"]
    specs: list[PlayerSpec] = _STATE["specs"]
    printed: dict[str, list[float]] = _STATE["printed"]
    cut: int = _STATE["cut"]
    out: list[tuple[Any, ...]] = []
    for i in idxs:
        rec = recs[i]
        split = "train" if rec.ts < cut else "test"
        for f, spec in enumerate(specs):
            y = rec.act[f]
            if y is None:
                continue
            if prm is None:
                got = v1_distribution(rec, f, spec.family)
            else:
                got = record_distribution(rec, f, spec.family, prm)
            if got is None:
                continue
            pmf, _ = got
            own = [v for _, v in family_sample(rec, f, LINE_SAMPLE)]
            line = nearest_line(own, printed.get(spec.family, []))
            s = score_pmf(pmf, y, line)
            p = s.p_over
            if (
                prm is not None
                and use_calibration
                and spec.family not in pm.SIGNED_FAMILIES
            ):
                p = pm.calibrate_side(p, prm.calibration_b)
            out.append((i, spec.family, split, s.ll, s.rps, p, s.y_over))
    return out


def score_all(
    prm: pm.SportParams | None, procs: int, use_calibration: bool = False
) -> list[tuple[Any, ...]]:
    n = len(_STATE["records"])
    chunks = [list(range(j, n, procs * 4)) for j in range(procs * 4)]
    if procs <= 1:
        return [r for c in chunks for r in _score_chunk((c, prm, use_calibration))]
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(procs) as pool:
        parts = pool.map(_score_chunk, [(c, prm, use_calibration) for c in chunks])
    return [r for part in parts for r in part]


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def fit_slope(
    rows: Sequence[tuple[float, float]], intercept: bool = False
) -> list[float]:
    """Logistic fit of y on logit(p): [b] or [a, b] by Newton's method."""
    w = [0.0, 1.0] if intercept else [1.0]
    for _ in range(50):
        g = [0.0] * len(w)
        h = [[0.0] * len(w) for _ in w]
        for p, y in rows:
            x = [1.0, logit(p)] if intercept else [logit(p)]
            z = sum(a * b for a, b in zip(w, x, strict=True))
            q = 1.0 / (1.0 + math.exp(-max(min(z, 30.0), -30.0)))
            for i in range(len(w)):
                g[i] += (q - y) * x[i]
                for j in range(len(w)):
                    h[i][j] += q * (1.0 - q) * x[i] * x[j]
        if len(w) == 1:
            step = [g[0] / (h[0][0] + 1e-9)]
        else:
            det = h[0][0] * h[1][1] - h[0][1] * h[1][0] + 1e-12
            step = [
                (h[1][1] * g[0] - h[0][1] * g[1]) / det,
                (h[0][0] * g[1] - h[1][0] * g[0]) / det,
            ]
        w = [a - b for a, b in zip(w, step, strict=True)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return w


def summarize(rows: Sequence[tuple[Any, ...]], split: str) -> dict[str, Any]:
    """Per family and the family-mean: n, ll, rps, binary Brier, slope, bands."""
    fams: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for r in rows:
        if r[2] == split:
            fams[r[1]].append(r)
    out: dict[str, Any] = {"families": {}}
    for fam, rs in sorted(fams.items()):
        n = len(rs)
        bands = []
        for lo, hi in zip(BANDS, BANDS[1:], strict=False):
            cell = [
                (max(r[5], 1 - r[5]), r[6] if r[5] >= 0.5 else 1 - r[6]) for r in rs
            ]
            cell = [c for c in cell if lo <= c[0] < hi]
            if len(cell) >= 30:
                bands.append(
                    {
                        "band": f"{lo:.1f}-{min(hi, 1.0):.1f}",
                        "n": len(cell),
                        "claimed": round(sum(c[0] for c in cell) / len(cell), 4),
                        "hit": round(sum(c[1] for c in cell) / len(cell), 4),
                    }
                )
        out["families"][fam] = {
            "n": n,
            "logloss": sum(r[3] for r in rs) / n,
            "rps": sum(r[4] for r in rs) / n,
            "brier_line": sum((r[5] - r[6]) ** 2 for r in rs) / n,
            "slope_line": fit_slope([(r[5], r[6]) for r in rs], intercept=True)[1]
            if n >= 200
            else None,
            "bands": bands,
        }
    fam_vals = list(out["families"].values())
    for key in ("logloss", "rps", "brier_line"):
        out[key] = sum(v[key] for v in fam_vals) / len(fam_vals) if fam_vals else None
    out["n"] = sum(v["n"] for v in fam_vals)
    return out


def objective(rows: Sequence[tuple[Any, ...]]) -> float:
    value = summarize(rows, "train")["logloss"]
    return float("inf") if value is None else float(value)


# --- the fit -----------------------------------------------------------------------

GRID: dict[str, list[Any]] = {
    "hl_minutes": [3.0, 5.0, 8.0, 12.0],
    # Extended 2026-10-03: the v2 fit chose 40 and 30, each the top of its
    # grid with the curve still falling (and hockey prior_games the bottom,
    # rising) - an optimum not bracketed is not a fitted value.
    "k_phi": [5.0, 10.0, 20.0, 40.0, 80.0, 160.0, 320.0],
    "max_sample": [20, 30, 40, 50, 60],
    "pool": ["group", "all"],
    "sig_a": [0.05, 0.1, 0.15, 0.2, 0.25, 0.3],
    "prior_games": [0.25, 0.5, 1.0, 2.0, 3.0, 4.0, 6.0],
    "prior_games_signed": [3.0, 10.0, 30.0, 100.0],
}
SHARED = ("hl_minutes", "k_phi", "max_sample")
OWN = {
    "basketball": ("pool", "sig_a", "prior_games"),
    "hockey": ("pool", "sig_a", "prior_games", "prior_games_signed"),
}
START = pm.SportParams(
    pool="group",
    max_sample=20,
    hl_minutes=5.0,
    k_phi=5.0,
    prior_games=3.0,
    sig_a=0.2,
    prior_games_signed=3.0,
    calibration_b=None,
)


def coordinate_descent(
    start: pm.SportParams,
    names: Sequence[str],
    procs: int,
    log: list[dict[str, Any]],
    sport: str,
    rounds: int = 2,
) -> tuple[pm.SportParams, dict[str, dict[str, float]]]:
    """Each name in turn over its grid, keeping the best train objective."""
    best = start
    best_obj = objective(score_all(best, procs))
    curves: dict[str, dict[str, float]] = {}
    for _ in range(rounds):
        moved = False
        for name in names:
            curve: dict[str, float] = {}
            for value in GRID[name]:
                trial = replace(best, **{name: value})
                obj = best_obj if trial == best else objective(score_all(trial, procs))
                curve[str(value)] = round(obj, 6)
                log.append(
                    {"sport": sport, "name": name, "value": value, "train_ll": obj}
                )
                print(f"  {sport} {name}={value}: train logloss {obj:.5f}", flush=True)
                if obj < best_obj - 1e-6:
                    best, best_obj, moved = trial, obj, True
            curves[name] = curve
        if not moved:
            break
    return best, curves


def printed_lines(runs_dir: str, sport: str) -> dict[str, list[float]]:
    """Every OVER line Superbet printed per player family in the snapshots."""
    out: dict[str, set[float]] = defaultdict(set)
    for path in sorted(Path(runs_dir, "shadow", sport).glob("*/snapshots.jsonl")):
        for text in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(text)
            except ValueError:
                continue
            for ln in rec.get("lines") or []:
                fam = str(ln.get("family", ""))
                if fam.startswith("player_") and ln.get("side") == "OVER":
                    if isinstance(ln.get("line"), int | float):
                        out[fam].add(float(ln["line"]))
    return {k: sorted(v) for k, v in out.items()}


def build_records(history: History, specs: Sequence[PlayerSpec]) -> list[Record]:
    eids = sorted(e for e in history.lineups if e in history.events)
    out: list[Record] = []
    for eid in eids:
        out.extend(replay_game(history, eid, specs))
    out.sort(key=lambda r: (r.ts, r.eid, r.pid))
    return out


def _records_chunk(eids: list[int]) -> list[Record]:
    history: History = _STATE["history"]
    specs: list[PlayerSpec] = _STATE["specs"]
    out: list[Record] = []
    for eid in eids:
        out.extend(replay_game(history, eid, specs))
    return out


def build_records_parallel(
    history: History, specs: Sequence[PlayerSpec], procs: int
) -> list[Record]:
    if procs <= 1:
        return build_records(history, specs)
    _STATE["history"], _STATE["specs"] = history, list(specs)
    eids = sorted(e for e in history.lineups if e in history.events)
    chunks = [eids[j :: procs * 4] for j in range(procs * 4)]
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(procs) as pool:
        parts = pool.map(_records_chunk, chunks)
    out = [r for part in parts for r in part]
    out.sort(key=lambda r: (r.ts, r.eid, r.pid))
    return out


def _params_json(prm: pm.SportParams) -> dict[str, Any]:
    return {
        "pool": prm.pool,
        "max_sample": prm.max_sample,
        "hl_minutes": prm.hl_minutes,
        "k_phi": prm.k_phi,
        "prior_games": prm.prior_games,
        "sig_a": prm.sig_a,
        "prior_games_signed": prm.prior_games_signed,
        "calibration_b": prm.calibration_b,
    }


def _date_range(records: Sequence[Record], cut: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for split, rs in (
        ("train", [r for r in records if r.ts < cut]),
        ("test", [r for r in records if r.ts >= cut]),
    ):
        if not rs:
            out[split] = {"player_games": 0}
            continue
        out[split] = {
            "from": datetime.fromtimestamp(min(r.ts for r in rs), UTC)
            .date()
            .isoformat(),
            "to": datetime.fromtimestamp(max(r.ts for r in rs), UTC).date().isoformat(),
            "games": len({r.eid for r in rs}),
            "player_games": len(rs),
        }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="the fitted JSON (config file shape)")
    ap.add_argument("--report", default=None, help="the full report, JSON")
    ap.add_argument("--cut", default=DEFAULT_CUT)
    ap.add_argument("--db", default=None, help="default: SofaConfig's db_path")
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--procs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--rounds", type=int, default=2)
    args = ap.parse_args(argv)
    started = time.monotonic()
    cut = int(datetime.fromisoformat(args.cut).replace(tzinfo=UTC).timestamp())
    db = args.db or SofaConfig.from_env().db_path
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    log: list[dict[str, Any]] = []
    report: dict[str, Any] = {"cut": args.cut, "sports": {}}
    fitted: dict[str, pm.SportParams] = {}
    curves: dict[str, dict[str, Any]] = {}
    provenance: dict[str, Any] = {}
    shared = START
    try:
        sports: tuple[SportKey, ...] = ("basketball", "hockey")
        for sport in sports:
            key: SportKey = sport
            t0 = time.monotonic()
            history = History.from_db(conn, key)
            specs = family_specs(key)
            records = build_records_parallel(history, specs, args.procs)
            printed = printed_lines(args.runs_dir, sport)
            line_source = {
                s.family: (
                    "superbet_printed" if printed.get(s.family) else "median_half"
                )
                for s in specs
            }
            n_games = len({r.eid for r in records})
            print(
                f"{sport}: {len(records)} player-games from {n_games} games "
                f"in {time.monotonic() - t0:.0f} s",
                flush=True,
            )
            _STATE.update(records=records, specs=specs, printed=printed, cut=cut)
            if sport == "basketball":
                best, c_shared = coordinate_descent(
                    START, SHARED + OWN[sport], args.procs, log, sport, args.rounds
                )
                shared = best
            else:
                best, c_shared = coordinate_descent(
                    replace(
                        START,
                        hl_minutes=shared.hl_minutes,
                        k_phi=shared.k_phi,
                        max_sample=shared.max_sample,
                    ),
                    OWN[sport],
                    args.procs,
                    log,
                    sport,
                    args.rounds,
                )
                # The shared constants' curve on this sport too (evidence only).
                for name in SHARED:
                    curve = {}
                    for value in GRID[name]:
                        rows = score_all(replace(best, **{name: value}), args.procs)
                        curve[str(value)] = round(objective(rows), 6)
                    c_shared[f"{name}@hockey(not chosen here)"] = curve
            raw = score_all(best, args.procs)
            binary = [
                (r[5], r[6])
                for r in raw
                if r[2] == "train" and r[1] not in pm.SIGNED_FAMILIES
            ]
            b = round(fit_slope(binary)[0], 4)
            best = replace(best, calibration_b=b)
            fitted[sport] = best
            curves[sport] = c_shared
            final = score_all(best, args.procs, use_calibration=True)
            v1 = score_all(None, args.procs)
            report["sports"][sport] = {
                "params": _params_json(best),
                "line_source": line_source,
                "printed_lines": printed,
                "v1": {s: summarize(v1, s) for s in ("train", "test")},
                "v2_uncalibrated": {s: summarize(raw, s) for s in ("train", "test")},
                "v2": {s: summarize(final, s) for s in ("train", "test")},
                "calibration_fit_n": len(binary),
            }
            provenance[sport] = _date_range(records, cut)
            print(f"{sport}: done in {time.monotonic() - t0:.0f} s", flush=True)
    finally:
        conn.close()
    doc = {
        "_doc": (
            "Fitted by scripts/sofa/fit_player_model.py on the stored history "
            "(no prices); read by bet.sofa.player_model. A measurement's "
            "constants: nothing here feeds or gates any coupon."
        ),
        "model": pm.MODEL_NAME,
        "fitted_from": {
            "source": (
                "sofa_event_stats.lineups_json + sofa_listing_event (kind=last) "
                "+ sofa_listed_event, replayed before each game"
            ),
            "db_path": str(db),
            "cut_utc": datetime.fromtimestamp(cut, UTC).isoformat(),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "splits": provenance,
        },
        "criterion": (
            "train split (kickoff before cut_utc): minimise the mean over "
            "families of the per-family mean log loss of the actual count, "
            "coordinate descent over the grids below; shared constants on "
            "basketball, then each sport's own. calibration_b: maximum "
            "likelihood of sigmoid(b logit p) for the over side at the replay "
            "line (the printed line nearest the sample median), train split, "
            "count families only."
        ),
        # Every grid the descent searched, so whether a value is bracketed
        # (not the end of its grid) can be read off the file.
        "grids": {name: list(values) for name, values in GRID.items()},
        "shared": {
            name: {
                "value": getattr(shared, name),
                "fitted_on": "basketball",
                "curve": curves["basketball"].get(name),
            }
            for name in SHARED
        },
        "sports": {
            sport: {
                **{
                    name: {
                        "value": getattr(prm, name),
                        "curve": curves[sport].get(name),
                    }
                    for name in OWN[sport]
                },
                **(
                    {}
                    if "prior_games_signed" in OWN[sport]
                    else {
                        "prior_games_signed": {
                            "value": prm.prior_games_signed,
                            "note": "no signed family in this sport; unused",
                        }
                    }
                ),
                "calibration_b": {
                    "value": prm.calibration_b,
                    "n": report["sports"][sport]["calibration_fit_n"],
                },
                "train_logloss": report["sports"][sport]["v2"]["train"]["logloss"],
                "test_logloss": report["sports"][sport]["v2"]["test"]["logloss"],
            }
            for sport, prm in fitted.items()
        },
    }
    Path(args.out).write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    report["runtime_s"] = round(time.monotonic() - started, 1)
    report["log"] = log
    if args.report:
        Path(args.report).write_text(
            json.dumps(report, indent=1) + "\n", encoding="utf-8"
        )
    for sport, rep in report["sports"].items():
        for name in ("v1", "v2_uncalibrated", "v2"):
            tr, te = rep[name]["train"], rep[name]["test"]
            print(
                f"{sport} {name:16s} train ll {tr['logloss']:.4f} rps {tr['rps']:.4f} "
                f"brier {tr['brier_line']:.4f} | test ll {te['logloss']:.4f} "
                f"rps {te['rps']:.4f} brier {te['brier_line']:.4f}"
            )
    print(f"runtime {report['runtime_s']} s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
