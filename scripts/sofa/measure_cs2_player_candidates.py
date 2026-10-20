#!/usr/bin/env python3
"""CS2 player lines: candidate changes to the player-line estimator, measured
walk-forward on history at lines placed the way Superbet places them, then
audited on Superbet's own settled lines against its devigged price.
Read-only: the database is opened mode=ro, nothing in config/ or src/ is
touched; every candidate lives in this file.

1. Line emulation. A transparent rule for Superbet's line from pre-match
   observables that do not use our model (the player's mean / median of the
   stat over his last N maps, his team's Elo map-win p, the map number), fitted
   on the settled Superbet days ONLY to place lines - never to fit a
   probability. Chosen by its exact-match rate on the later half of those days
   (fitted on the earlier half), then refitted on all of them and applied to
   every history player-map.
2. Baseline = today's estimator (cs2_engine exposure for kills / deaths /
   assists, count_p for headshots and wherever the exposure has no number) at
   the emulated line; also at half(exp_mean) and +-1 as a sensitivity.
3. Candidates, each strictly walk-forward (every parameter, dispersion and
   multiplier from periods before the evaluated month): C0 the baseline with
   its dispersion re-estimated from the rows (control); C1 impossible values
   dropped + exposure for headshots; C2 K_SHARE grid; C2b K_SHARE by career
   maps; C3 map-name multiplier; C4 dispersion scale per family (no 0.5
   floor); C5 format / map-number multiplier; C6 share window 10 / 40 maps
   with its own K grid; COMBO the passing pieces together.
4. Audit at Superbet's real lines: AUC / log-loss vs the devigged price and the
   out-of-sample blend logit(price) + logit(model) vs the price alone.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_player_candidates.py \\
        --db-path <copy.db> --superbet <cs2_player_lines.jsonl.gz> --out <dir>
"""

from __future__ import annotations

import argparse
import dataclasses
import gzip
import json
import math
import sqlite3
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import cs2_engine as ce  # noqa: E402
from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.engine import P_CEILING, P_FLOOR  # noqa: E402

NDArr = np.ndarray[Any, np.dtype[Any]]

STATS = ("kills", "deaths", "assists", "headshots")
FAMILY = {s: f"player_{s}" for s in STATS}
WINDOWS = (10, 20, 40)
K_GRID = (0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0)
SCALE_GRID = (0.4, 0.55, 0.7, 0.85, 1.0, 1.2, 1.5)
EXP_EDGES = (20, 60)  # career maps buckets for C2b: <20, 20-59, >=60
MULT_PSEUDO = 200.0  # pseudo-rows behind a multiplier
AUDIT_FROM = "2026-09-28"
LINE_COLS = ("emu", "expm", "expm_m1", "expm_p1", "sb")


# --- data ---------------------------------------------------------------------


def connect(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def load_maps(conn: sqlite3.Connection, before_ts: int) -> list[ce.MapRow]:
    ce.LOOKBACK_DAYS = 400  # in-process only: take the whole stored history
    return ce.load_history(conn, before_ts, None)


def clean_maps(maps: list[ce.MapRow]) -> tuple[list[ce.MapRow], dict[str, int]]:
    """C1's data rules (each impossible as recorded):
    - headshots > kills: the row's headshots dropped (a missing stat);
    - a player's deaths or assists above the map's rounds: the map's rounds are
      wrong (13-0 with 21 deaths) - rounds set to None (rounds models skip it);
    - a side not of exactly five players, or |team kills - opponent deaths| >
      10 over the map: the map's player rows dropped."""
    out: list[ce.MapRow] = []
    n: Counter[str] = Counter()
    for m in maps:
        rows = []
        for t, pid, nick, st in m.players:
            d = dict(st)
            hs, k = d.get("headshots"), d.get("kills")
            if isinstance(hs, int) and isinstance(k, int) and hs > k:
                n["headshots_gt_kills"] += 1
                st = tuple((a, v) for a, v in st if a != "headshots")
            rows.append((t, pid, nick, st))
        hr, ar = m.home_rounds, m.away_rounds
        if hr is not None and ar is not None:
            tot = hr + ar
            if any(
                (isinstance(dict(st).get("deaths"), int) and dict(st)["deaths"] > tot)
                or (
                    isinstance(dict(st).get("assists"), int)
                    and dict(st)["assists"] > tot
                )
                for _, _, _, st in rows
            ):
                n["map_rounds_inconsistent"] += 1
                hr, ar = None, None
        sides = Counter(t for t, _, _, _ in rows)
        bad = bool(rows) and any(c != 5 for c in sides.values())
        if not bad and rows:
            kd: dict[int, list[int]] = defaultdict(lambda: [0, 0])
            for t, _, _, st in rows:
                d = dict(st)
                kd[t][0] += int(d.get("kills") or 0)
                kd[t][1] += int(d.get("deaths") or 0)
            if len(kd) == 2:
                (a, b) = list(kd.values())
                bad = abs(a[0] - b[1]) > 10 or abs(b[0] - a[1]) > 10
        if bad:
            n["map_players_dropped"] += 1
            rows = []
        out.append(
            dataclasses.replace(
                m, players=tuple(rows), home_rounds=hr, away_rounds=ar
            )
        )
    return out, dict(n)


# --- the walk -----------------------------------------------------------------

SCALAR = (
    "eid", "ts", "order", "bo", "map_id", "team", "opp", "pid", "stat",
    "actual", "W", "L", "p_team", "found", "pall", "n_sample",
    "cw", "cl", "phi_eng",
    "own10", "tot10", "n10", "own20", "tot20", "n20", "own40", "tot40", "n40",
)


def walk(
    maps: list[ce.MapRow], score_from: int
) -> tuple[dict[str, NDArr], list[str], list[tuple[int, float]]]:
    """One row per (player, map, stat) scored: the ingredients of the exposure
    (rates at won / lost rounds, the player's own and team sums over his last
    10 / 20 / 40 maps, the engine's phi), his last MAX_SAMPLE values for count_p,
    and the observables of the line emulation. State is updated after the
    series, exactly as cs2_engine / sport_confidence replay it."""
    book = ce.EloBook()
    players = ce.PlayerEloBook()
    points: list[tuple[float, float]] = []
    ppoints: list[tuple[float, float]] = []
    model = ce.RatingModel(book)
    next_refit = 0
    expo = ce.ExposureBook()
    pvals: dict[tuple[int, str], deque[int]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE)
    )
    pall: Counter[int] = Counter()
    pshare: dict[int, deque[tuple[dict[str, int], dict[str, int]]]] = defaultdict(
        lambda: deque(maxlen=max(WINDOWS))
    )
    team_recent: dict[int, deque[ce.MapRow]] = defaultdict(
        lambda: deque(maxlen=ce.MAX_SAMPLE)
    )
    map_ids: dict[str, int] = {}
    cols: dict[str, list[float]] = {k: [] for k in SCALAR}
    samples: list[list[int]] = []
    checks: list[tuple[int, float]] = []
    by_series: dict[int, list[ce.MapRow]] = {}
    for m in maps:
        by_series.setdefault(m.event_id, []).append(m)
    nan = float("nan")
    for eid, smaps in by_series.items():
        start = smaps[0].start_ts
        if start >= next_refit:
            model = scf._cs2_refit(book, players, points, ppoints)
            next_refit = start + scf.REFIT_DAYS_CS2 * 86400
        home, away = smaps[0].home_id, smaps[0].away_id
        p_home = model.p_map(home, away, True) if start >= score_from else None
        if p_home is not None:
            names: dict[int, dict[str, set[int]]] = {}
            for t in (home, away):
                nm: dict[str, set[int]] = defaultdict(set)
                for tm in team_recent[t]:
                    for tt, pid, nick, _ in tm.players:
                        if tt == t:
                            nm[nick].add(pid)
                names[t] = nm
            for m in smaps:
                mid = map_ids.setdefault(m.map_name or "?", len(map_ids))
                for team, opp, w, lost, _tot, prow in ce.map_sides(m):
                    p_team = p_home if team == home else 1.0 - p_home
                    nicks = {pid: nk for t, pid, nk, _ in m.players if t == team}
                    for pid, own in prow:
                        found = names[team].get(nicks.get(pid, ""), set()) == {pid}
                        hist = list(pshare[pid])
                        for si, stat in enumerate(STATS):
                            v = own.get(stat)
                            if not isinstance(v, int):
                                continue
                            sample = list(reversed(pvals[(pid, stat)]))
                            if len(sample) < ce.MIN_SAMPLE:
                                continue
                            r = expo.rates(team, opp, stat)
                            ph = expo.phi("player", stat)
                            vals = [
                                float(eid), float(start), float(m.order),
                                float(m.best_of or 0), float(mid), float(team),
                                float(opp), float(pid), float(si), float(v),
                                float(w), float(lost), p_team, float(found),
                                float(pall[pid]), float(len(sample)),
                                r[0] if r else nan, r[1] if r else nan,
                                ph if ph is not None else nan,
                            ]
                            for win in WINDOWS:
                                rec = [
                                    (o[stat], tt[stat])
                                    for o, tt in hist[-win:]
                                    if stat in o and stat in tt
                                ]
                                vals += [
                                    float(sum(o for o, _ in rec)),
                                    float(sum(t for _, t in rec)),
                                    float(len(rec)),
                                ]
                            for k, x in zip(SCALAR, vals, strict=True):
                                cols[k].append(x)
                            samples.append(sample)
                            if (
                                len(checks) < 400
                                and stat != "headshots"
                                and r is not None
                                and ph is not None
                            ):
                                mp = ce.exposure_p(
                                    expo, p_team, team, opp, stat, pid, 10.5, True
                                )
                                if mp is not None:
                                    checks.append((len(samples) - 1, mp.p))
        # --- state update after the series
        if book.rated(home, away):
            d = ce.logit_diff(book, home, away)
            points.extend((d, 1.0 if m.home_won else 0.0) for m in smaps)
            gap = players.gap(home, away)
            if gap is not None:
                ppoints.extend((gap, 1.0 if m.home_won else 0.0) for m in smaps)
        for m in smaps:
            winner, loser = (
                (m.home_id, m.away_id) if m.home_won else (m.away_id, m.home_id)
            )
            book.update(winner, loser)
            players.update(m)
            expo.update(m)
            for _t, _o, _w, _l, totals, prow2 in ce.map_sides(m):
                for pid, own in prow2:
                    vv = {k: v for k, v in own.items() if isinstance(v, int)}
                    pshare[pid].append((vv, totals))
            team_recent[m.home_id].append(m)
            team_recent[m.away_id].append(m)
            for _, pid, _, st in m.players:
                sd = dict(st)
                for stat in STATS:
                    if isinstance(sd.get(stat), int):
                        pvals[(pid, stat)].append(sd[stat])
                pall[pid] += 1
    arr: dict[str, NDArr] = {k: np.array(v, dtype=float) for k, v in cols.items()}
    smp = np.full((len(samples), ce.MAX_SAMPLE), -1, dtype=np.int16)
    for i, s in enumerate(samples):
        smp[i, : len(s)] = s
    arr["sample"] = smp
    names_by_id = [""] * len(map_ids)
    for k, i in map_ids.items():
        names_by_id[i] = k
    return arr, names_by_id, checks


# --- the exposure mixture, vectorised -----------------------------------------

_RACE: dict[float, tuple[NDArr, NDArr, NDArr]] = {}


def race_arrays(key: float) -> tuple[NDArr, NDArr, NDArr]:
    got = _RACE.get(key)
    if got is None:
        cells = ce.race_cells(key, 0)
        got = (
            np.array([c[0] for c in cells]),
            np.array([c[1] for c in cells], float),
            np.array([c[2] for c in cells], float),
        )
        _RACE[key] = got
    return got


def race_key(p_team: NDArr) -> NDArr:
    return np.round(np.clip(p_team, 0.05, 0.95), 3)


def norm_cdf(z: NDArr) -> NDArr:
    """Phi(z) via Numerical Recipes' erfc (fractional error < 1.2e-7)."""
    x = -z / math.sqrt(2.0)
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.5 * a)
    poly = -a * a - 1.26551223 + t * (
        1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (
            -0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (
                1.48851587 + t * (-0.82215223 + t * 0.17087277))))))))
    erfc = t * np.exp(poly)
    erfc = np.where(x >= 0, erfc, 2.0 - erfc)
    return np.asarray(0.5 * erfc)


def mix_p(
    key: NDArr, s: NDArr, cw: NDArr, cl: NDArr, phi: NDArr, lines: NDArr,
    floor: float,
) -> NDArr:
    """P(OVER) at each line column (rows x L) of the (W, L) race mixture with
    mu = s x (cw W + cl L): NB with variance phi mu when phi > 1, else the
    continuity-corrected normal with variance max(phi, floor) mu - exactly
    cs2_engine.exposure_sides (kept-mass normalised), clamped."""
    n, nl = lines.shape
    out = np.full((n, nl), np.nan)
    ks = np.floor(lines).astype(int)
    for kv in np.unique(key):
        g = np.nonzero(key == kv)[0]
        q, wa, la = race_arrays(float(kv))
        qs = q.sum()
        mu = s[g, None] * (cw[g, None] * wa[None, :] + cl[g, None] * la[None, :])
        ph = phi[g]
        kg = ks[g]
        nb = ph > 1.0
        if nb.any():
            gi = np.nonzero(nb)[0]
            m2 = mu[gi]
            p2 = ph[gi][:, None]
            r = m2 / (p2 - 1.0)
            qnb = 1.0 - 1.0 / p2
            pmf = np.exp(r * np.log(1.0 / p2))
            acc = pmf.copy()
            kk = kg[gi]
            kmax = int(kk.max())
            res = np.full(kk.shape, np.nan)
            for k in range(kmax + 1):
                if k > 0:
                    pmf = pmf * (k - 1 + r) / k * qnb
                    acc = np.minimum(acc + pmf, 1.0)
                hit = kk == k
                if hit.any():
                    c = (acc @ q) / qs
                    rr, cc = np.nonzero(hit)
                    res[rr, cc] = c[rr]
            out[g[gi]] = 1.0 - res
        if (~nb).any():
            gi = np.nonzero(~nb)[0]
            m2 = mu[gi]
            sd = np.sqrt(np.maximum(ph[gi], floor)[:, None] * np.maximum(m2, 1e-12))
            for j in range(nl):
                z = (kg[gi, j][:, None] + 0.5 - m2) / sd
                cdf = np.where(m2 > 0, norm_cdf(z), 1.0)
                out[g[gi], j] = 1.0 - (cdf @ q) / qs
    return np.asarray(np.clip(out, P_FLOOR, P_CEILING))


_EXPECT: dict[float, tuple[float, float]] = {}


def race_expect(key: NDArr) -> tuple[NDArr, NDArr]:
    ew = np.empty(len(key))
    el = np.empty(len(key))
    for kv in np.unique(key):
        got = _EXPECT.get(float(kv))
        if got is None:
            q, wa, la = race_arrays(float(kv))
            got = (float((q * wa).sum() / q.sum()), float((q * la).sum() / q.sum()))
            _EXPECT[float(kv)] = got
        sel = key == kv
        ew[sel], el[sel] = got
    return ew, el


def count_p_cols(sample: NDArr, n: NDArr, lines: NDArr) -> NDArr:
    out = np.full(lines.shape, np.nan)
    for i in range(len(n)):
        s = [int(x) for x in sample[i, : int(n[i])]]
        for j in range(lines.shape[1]):
            mp = ce.count_p(s, float(lines[i, j]), True)
            if mp is not None:
                out[i, j] = mp.p
    return out


# --- metrics ------------------------------------------------------------------


def ll_vec(p: NDArr, y: NDArr) -> NDArr:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.asarray(-(y * np.log(p) + (1 - y) * np.log(1 - p)))


def logit(p: NDArr) -> NDArr:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.asarray(np.log(p / (1 - p)))


def auc(s: NDArr, y: NDArr) -> float:
    npos = float(y.sum())
    nneg = float(len(y) - npos)
    if npos == 0 or nneg == 0:
        return float("nan")
    u, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    upper = np.cumsum(cnt)
    avg = upper - (cnt - 1) / 2.0
    ranks = avg[inv]
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def fit_logit(xm: NDArr, y: NDArr, ridge: float = 1e-3) -> NDArr:
    w = np.zeros(xm.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-(xm @ w)))
        g = xm.T @ (p - y) + ridge * w
        h = (xm * (p * (1 - p))[:, None]).T @ xm + ridge * np.eye(xm.shape[1])
        step = np.linalg.solve(h, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return np.asarray(w)


def slope(p: NDArr, y: NDArr) -> float:
    lp = logit(p)
    return float(fit_logit(np.column_stack([np.ones_like(lp), lp]), y)[1])


def boot_mean(
    vals: NDArr, groups: NDArr, reps: int, rng: np.random.Generator
) -> tuple[float, float, float]:
    ug, inv = np.unique(groups, return_inverse=True)
    sv = np.bincount(inv, weights=vals, minlength=len(ug))
    sw = np.bincount(inv, minlength=len(ug)).astype(float)
    point = sv.sum() / sw.sum()
    stats = np.empty(reps)
    for b in range(reps):
        idx = rng.integers(0, len(ug), size=len(ug))
        stats[b] = sv[idx].sum() / sw[idx].sum()
    return (
        round(float(point), 6),
        round(float(np.quantile(stats, 0.025)), 6),
        round(float(np.quantile(stats, 0.975)), 6),
    )


def coverage(p: NDArr, y: NDArr, thr: float = 0.70) -> dict[str, Any]:
    side = np.maximum(p, 1 - p)
    hit = np.where(p >= 0.5, y, 1 - y)
    sel = side >= thr
    n = int(sel.sum())
    return {
        "n": n,
        "share": round(n / max(len(p), 1), 4),
        "mean_p": round(float(side[sel].mean()), 4) if n else None,
        "realised": round(float(hit[sel].mean()), 4) if n else None,
    }


def summary(p: NDArr, y: NDArr) -> dict[str, Any]:
    return {
        "n": int(len(p)),
        "log_loss": round(float(ll_vec(p, y).mean()), 5),
        "brier": round(float(((p - y) ** 2).mean()), 5),
        "auc": round(auc(p, y), 4),
        "slope": round(slope(p, y), 3),
        "mean_p": round(float(p.mean()), 4),
        "realised": round(float(y.mean()), 4),
        "cov70": coverage(p, y),
    }


# --- line emulation -------------------------------------------------------------


def emu_features(a: dict[str, NDArr], rows: NDArr) -> dict[str, NDArr]:
    smp = a["sample"][rows].astype(float)
    n = a["n_sample"][rows]
    mask = np.arange(smp.shape[1])[None, :] < n[:, None]
    out: dict[str, NDArr] = {}
    for w in (5, 10, 20):
        mw = mask & (np.arange(smp.shape[1])[None, :] < w)
        out[f"m{w}"] = (smp * mw).sum(1) / mw.sum(1)
    med = np.where(mask, smp, np.nan)
    out["med20"] = np.nanmedian(med, axis=1)
    out["pt"] = a["p_team"][rows] - 0.5
    out["map2"] = (a["order"][rows] >= 2).astype(float)
    return out


EMU_RULES: dict[str, tuple[str, ...] | None] = {
    "half(m20)": None,
    "half(m10)": None,
    "half(m5)": None,
    "half(med20)": None,
    "ols(m20)": ("m20",),
    "ols(m10,m20)": ("m10", "m20"),
    "ols(m20,pt)": ("m20", "pt"),
    "ols(m10,m20,pt)": ("m10", "m20", "pt"),
    "ols(m5,m10,m20,pt,map2)": ("m5", "m10", "m20", "pt", "map2"),
}


def emu_design(f: dict[str, NDArr], feats: tuple[str, ...]) -> NDArr:
    return np.column_stack([np.ones(len(f["m20"]))] + [f[k] for k in feats])


def emu_predict(rule: str, f: dict[str, NDArr], coef: NDArr | None) -> NDArr:
    feats = EMU_RULES[rule]
    if feats is None:
        base = f[rule[5:-1]]
    else:
        assert coef is not None
        base = emu_design(f, feats) @ coef
    return np.asarray(np.floor(np.maximum(base, 0.0)) + 0.5)


# --- candidate predictions ------------------------------------------------------


@dataclasses.dataclass
class Fam:
    """One family's rows (all periods) and their fixed ingredients."""

    stat: int
    a: dict[str, NDArr]
    period: NDArr
    y: NDArr  # rows x L: actual > line
    lines: NDArr  # rows x L
    cp: NDArr  # count_p at each line (fallback)
    key: NDArr
    ew: NDArr
    el: NDArr
    exp_bucket: NDArr
    map_id: NDArr
    order_key: NDArr


@dataclasses.dataclass
class Cfg:
    name: str
    exposure: bool = True  # False: count_p (headshots today)
    window: int = 20
    k: float | str = ce.K_SHARE  # a value, "grid" or "grid_exp"
    phi: str = "engine"  # "engine" | "rows"
    scale: float | str = 1.0  # a value or "grid"
    floor: float = ce.MIN_VAR_RATIO
    mult: tuple[str, ...] = ()  # "map", "order"


def share_of(
    a: dict[str, NDArr], window: int, k_row: NDArr
) -> tuple[NDArr, NDArr]:
    own = a[f"own{window}"]
    tot = a[f"tot{window}"]
    n = a[f"n{window}"]
    mt = np.where(n > 0, tot / np.maximum(n, 1), 0.0)
    den = tot + k_row * mt
    ok = (n >= ce.MIN_SAMPLE) & (tot + mt > 0) & (den > 0)
    s = np.where(ok, (own + k_row * ce.SHARE_PRIOR * mt) / np.where(ok, den, 1), 0.0)
    return s, ok


def by_period_cum(
    period: NDArr, valid: NDArr, num: NDArr, den: NDArr, nper: int
) -> tuple[NDArr, NDArr]:
    """Sums over periods strictly before each period (cumulative)."""
    sn = np.bincount(period[valid], weights=num[valid], minlength=nper)
    sd = np.bincount(period[valid], weights=den[valid], minlength=nper)
    cn = np.concatenate([[0.0], np.cumsum(sn)[:-1]])
    cd = np.concatenate([[0.0], np.cumsum(sd)[:-1]])
    return cn, cd


def predict(
    f: Fam, cfg: Cfg, k_row: NDArr, scale_row: NDArr, nper: int
) -> tuple[NDArr, NDArr]:
    """(p rows x L, exposure-used mask)."""
    a = f.a
    cw, cl = a["cw"], a["cl"]
    s, ok = share_of(a, cfg.window, k_row)
    valid = ok & ~np.isnan(cw) & cfg.exposure
    if cfg.phi == "engine":
        valid &= ~np.isnan(a["phi_eng"])
    mult = np.ones(len(s))
    x = a["actual"]
    for mk in cfg.mult:
        grp = f.map_id if mk == "map" else f.order_key
        mu_mean = s * mult * (np.nan_to_num(cw) * f.ew + np.nan_to_num(cl) * f.el)
        mrow = np.ones(len(s))
        for gv in np.unique(grp):
            sel = grp == gv
            cn, cd = by_period_cum(
                f.period[sel], valid[sel], x[sel], mu_mean[sel], nper
            )
            cnt = np.bincount(f.period[sel][valid[sel]], minlength=nper).astype(float)
            cc = np.concatenate([[0.0], np.cumsum(cnt)[:-1]])
            mbar = np.where(cc > 0, cd / np.maximum(cc, 1), 1.0)
            m = (cn + MULT_PSEUDO * mbar) / np.maximum(cd + MULT_PSEUDO * mbar, 1e-9)
            mrow[sel] = m[f.period[sel]]
        mult = mult * mrow
    s2 = s * mult
    if cfg.phi == "engine":
        phi = a["phi_eng"].copy()
    else:
        mu_act = s2 * (np.nan_to_num(cw) * a["W"] + np.nan_to_num(cl) * a["L"])
        vv = valid & (mu_act > 0)
        num = np.where(vv, (x - mu_act) ** 2 / np.where(vv, mu_act, 1.0), 0.0)
        cn, cd = by_period_cum(f.period, vv, num, np.ones(len(x)), nper)
        ph = np.where(cd >= ce.MIN_FIT, cn / np.maximum(cd, 1), np.nan)
        phi = ph[f.period]
        valid &= ~np.isnan(phi)
    phi = phi * scale_row
    p = f.cp.copy()
    vi = np.nonzero(valid)[0]
    if len(vi):
        p[vi] = mix_p(
            f.key[vi], s2[vi], cw[vi], cl[vi], phi[vi], f.lines[vi], cfg.floor
        )
    return p, valid


def choose(
    f: Fam, pv: list[NDArr], groups: NDArr, nper: int, avail: NDArr
) -> NDArr:
    """Per row, the grid index chosen on periods before its own (per group),
    by log-loss at the emulated line; rows of the first period get index of
    the value nearest the default (passed as the middle of the list)."""
    ll = np.stack([ll_vec(p[:, 0], f.y[:, 0]) for p in pv])  # G x rows
    pick = np.zeros(len(f.period), dtype=int)
    for gv in np.unique(groups):
        sel = (groups == gv) & avail
        cum = np.zeros((len(pv), nper))
        for gi in range(len(pv)):
            cum[gi] = np.bincount(f.period[sel], weights=ll[gi][sel], minlength=nper)
        cc = np.concatenate([np.zeros((len(pv), 1)), np.cumsum(cum, 1)[:, :-1]], 1)
        best = np.argmin(cc, axis=0)  # per period
        best[cc.sum(0) == 0] = -1
        rows = groups == gv
        pick[rows] = best[f.period[rows]]
    return pick


def run_cfg(
    f: Fam, cfg: Cfg, nper: int, default_k: float = ce.K_SHARE
) -> tuple[NDArr, NDArr, dict[str, Any]]:
    info: dict[str, Any] = {}
    nrow = len(f.period)
    k_row = np.full(nrow, default_k if isinstance(cfg.k, str) else float(cfg.k))
    scale_row = np.full(nrow, 1.0 if isinstance(cfg.scale, str) else float(cfg.scale))
    if isinstance(cfg.k, str):
        pv, av = [], np.ones(nrow, bool)
        for kv in K_GRID:
            p, v = predict(f, cfg, np.full(nrow, kv), scale_row, nper)
            pv.append(p)
            av &= v
        groups = f.exp_bucket if cfg.k == "grid_exp" else np.zeros(nrow, int)
        pick = choose(f, pv, groups, nper, av)
        kg = np.array(K_GRID)
        k_row = np.where(pick >= 0, kg[np.maximum(pick, 0)], default_k)
        info["k_by_period"] = {
            f"{int(g)}:{int(per)}": float(k_row[(groups == g) & (f.period == per)][0])
            for g in np.unique(groups)
            for per in np.unique(f.period[groups == g])
        }
    if isinstance(cfg.scale, str):
        pv, av = [], np.ones(nrow, bool)
        for sv in SCALE_GRID:
            p, v = predict(f, cfg, k_row, np.full(nrow, sv), nper)
            pv.append(p)
            av &= v
        pick = choose(f, pv, np.zeros(nrow, int), nper, av)
        sg = np.array(SCALE_GRID)
        scale_row = np.where(pick >= 0, sg[np.maximum(pick, 0)], 1.0)
        info["scale_by_period"] = {
            int(per): float(scale_row[f.period == per][0])
            for per in np.unique(f.period)
        }
    p, v = predict(f, cfg, k_row, scale_row, nper)
    info["exposure_share"] = round(float(v.mean()), 4)
    return p, v, info


def row_keys(f: Fam) -> list[tuple[int, int, int]]:
    return list(zip(f.a["eid"].astype(int).tolist(), f.a["order"].astype(int).tolist(),
                    f.a["pid"].astype(int).tolist(), strict=True))


def row_pos(f: Fam) -> dict[tuple[int, int, int], int]:
    return {k: i for i, k in enumerate(row_keys(f))}


# --- audit ----------------------------------------------------------------------


def oos_blend(
    days: NDArr, lp: NDArr, lm: NDArr, y: NDArr, mode: str
) -> tuple[NDArr, NDArr, NDArr]:
    pa = np.full(len(y), np.nan)
    pb = np.full(len(y), np.nan)
    for d in sorted(set(days.tolist())):
        test = days == d
        train = days != d if mode == "lodo" else days < d
        if train.sum() < 200 or len(set(y[train].tolist())) < 2:
            continue
        xa = np.column_stack([np.ones(int(train.sum())), lp[train]])
        wa = fit_logit(xa, y[train])
        pa[test] = 1 / (1 + np.exp(-(np.column_stack(
            [np.ones(int(test.sum())), lp[test]]) @ wa)))
        xb = np.column_stack([np.ones(int(train.sum())), lp[train], lm[train]])
        wb = fit_logit(xb, y[train])
        pb[test] = 1 / (1 + np.exp(-(np.column_stack(
            [np.ones(int(test.sum())), lp[test], lm[test]]) @ wb)))
    return ~np.isnan(pa), pa, pb


# --- main ---------------------------------------------------------------------


def load_superbet(path: str) -> list[dict[str, Any]]:
    out = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("side") == "OVER":
                out.append(r)
    return out


def cache_walk(
    path: Path, maps: list[ce.MapRow], score_from: int, label: str
) -> tuple[dict[str, NDArr], list[str], list[tuple[int, float]]]:
    if path.exists():
        z = np.load(path, allow_pickle=False)
        arr = {k: z[k] for k in z.files if k not in ("map_names", "checks")}
        chk = [(int(i), float(p)) for i, p in z["checks"]]
        return arr, [str(x) for x in z["map_names"]], chk
    t0 = time.time()
    arr, names, chk = walk(maps, score_from)
    save: dict[str, Any] = {"map_names": np.array(names), "checks": np.array(chk)}
    save.update(arr)
    np.savez_compressed(path, **save)
    print(f"walk {label}: {len(arr['eid'])} rows ({time.time() - t0:.0f}s)", flush=True)
    return arr, names, chk


def _ci(t: Any) -> str:
    return f"{t[0]:+.5f} [{t[1]:+.5f}, {t[2]:+.5f}]"


def text_report(rep: dict[str, Any]) -> str:
    """The human summary of report.json."""
    out = [f"clean rules: {rep.get('clean_rules')}",
           f"superbet join: {rep.get('superbet_join')}", "", "LINE EMULATION"]
    for fam, e in rep.get("line_emulation", {}).items():
        r = e["rules"][e["chosen"]]
        out.append(f"  {fam}: {e['chosen']} coef {r.get('coef_all_days')} holdout "
                   f"exact {r['holdout_exact']} within1 {r['holdout_within1']}; "
                   f"all days exact {r['all_exact']} within1 {r['all_within1']}")
    for fam, fr in rep.get("results", {}).items():
        out += ["", f"== {fam} eval {fr['eval_n']}"]
        for col, b in fr["baseline"].items():
            out.append(f"  baseline@{col}: LL {b['log_loss']} Brier {b['brier']} "
                       f"AUC {b['auc']} slope {b['slope']} cov70 {b['cov70']}")
        for mon, b in fr["baseline_by_month"].items():
            out.append(f"    {mon}: n {b['n']} LL {b['log_loss']} AUC {b['auc']} "
                       f"slope {b['slope']}")
        for name, c in fr["candidates"].items():
            e = c["emu"]
            out.append(
                f"  {name:24s} @emu dLL {_ci(e['delta_ll'])} dAUC {e['delta_auc']:+.4f}"
                f" slope {e['cand']['slope']} (base {e['base']['slope']}) cov70 "
                f"{e['cand']['cov70']['n']}/{e['cand']['cov70']['realised']} (base "
                f"{e['base']['cov70']['n']}/{e['base']['cov70']['realised']}) "
                f"n {e['n']} m {e['matches']}")
            for col in ("expm", "expm_m1", "expm_p1"):
                x = c[col]
                out.append(f"      @{col}: dLL {_ci(x['delta_ll'])} "
                           f"dAUC {x['delta_auc']:+.4f} slope {x['cand']['slope']}")
    out += ["", "AUDIT at Superbet's lines (OVER side) vs devigged price"]
    for fam, fa in rep.get("audit", {}).items():
        for name, a in fa.items():
            k = "delta_ll_blend_minus_price_recal"
            bw = _ci(a["blend_walk"][k]) if "blend_walk" in a else "-"
            bl = _ci(a["blend_lodo"][k]) if "blend_lodo" in a else "-"
            out.append(
                f"  {fam} {name:24s} n {a['n']} AUC m {a['auc_model']} p "
                f"{a['auc_price']} LL m {a['ll_model']} p {a['ll_price']} "
                f"blend-walk {bw} lodo {bl}"
                f" cov70 {a['cov70_model']}")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--superbet", required=True, help="cs2_player_lines.jsonl.gz")
    ap.add_argument("--out", required=True)
    ap.add_argument("--from", dest="start", default="2025-11-15")
    ap.add_argument("--before", default="2026-10-20")
    ap.add_argument("--eval-from", default="2026-04-01")
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--text-only", action="store_true",
                    help="rewrite report.txt from an existing report.json")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.text_only:
        rep = json.loads((out / "report.json").read_text(encoding="utf-8"))
        (out / "report.txt").write_text(text_report(rep), encoding="utf-8")
        return 0
    t0 = time.time()
    conn = connect(args.db_path)
    try:
        maps = load_maps(conn, scf.day_ts(args.before))
    finally:
        conn.close()
    cmaps, clean_n = clean_maps(maps)
    print(f"maps {len(maps)}; clean {clean_n} ({time.time() - t0:.0f}s)", flush=True)
    score_from = scf.day_ts(args.start)
    raw, map_names, checks = cache_walk(out / "walk_raw.npz", maps, score_from, "raw")
    cln, _, _ = cache_walk(out / "walk_clean.npz", cmaps, score_from, "clean")
    rng = np.random.default_rng(args.seed)
    report: dict[str, Any] = {"clean_rules": clean_n, "n_rows_raw": len(raw["eid"]),
                              "n_rows_clean": len(cln["eid"])}

    # --- periods: calendar months before AUDIT_FROM, then one audit period
    audit_ts = scf.day_ts(AUDIT_FROM)
    eval_ts = scf.day_ts(args.eval_from)

    def periods(a: dict[str, NDArr]) -> tuple[NDArr, list[str]]:
        mon = np.array(
            [time.strftime("%Y-%m", time.gmtime(t)) for t in a["ts"].astype(int)]
        )
        mon = np.where(a["ts"] >= audit_ts, "audit", mon)
        labels = sorted(set(mon.tolist()) - {"audit"}) + ["audit"]
        idx = {m: i for i, m in enumerate(labels)}
        return np.array([idx[m] for m in mon]), labels

    # --- Superbet's lines joined to the raw walk
    sb = load_superbet(args.superbet)
    key_raw: dict[tuple[int, int, int, int], int] = {}
    for i in range(len(raw["eid"])):
        key_raw[(int(raw["eid"][i]), int(raw["order"][i]), int(raw["pid"][i]),
                 int(raw["stat"][i]))] = i
    fam_idx = {v: STATS.index(k) for k, v in FAMILY.items()}
    sb_line: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    miss: Counter[str] = Counter()
    for r in sb:
        pids = r.get("player_ids") or []
        if len(pids) != 1:
            miss["namesake_or_unmatched"] += 1
            continue
        k = (int(r["sofascore_event_id"]), int(r["map_nr"]), int(pids[0]),
             fam_idx[r["family"]])
        if k not in key_raw:
            miss["no_replay_row"] += 1
            continue
        if k in sb_line:
            miss["duplicate_line(first kept)"] += 1
            continue
        sb_line[k] = r
    report["superbet_join"] = {"joined": len(sb_line), "miss": dict(miss)}
    print(f"superbet lines joined {len(sb_line)} miss {dict(miss)}", flush=True)

    # --- 1. line emulation (lines only; no probability is fitted here)
    emu: dict[str, Any] = {}
    emu_coef: dict[int, tuple[str, NDArr | None]] = {}
    for si, stat in enumerate(STATS):
        ks = [k for k in sb_line if k[3] == si]
        rows = np.array([key_raw[k] for k in ks])
        line = np.array([float(sb_line[k]["line"]) for k in ks])
        day = np.array([sb_line[k]["date"] for k in ks])
        f = emu_features(raw, rows)
        udays = sorted(set(day.tolist()))
        fit_days = set(udays[: len(udays) // 2])
        tr = np.array([d in fit_days for d in day])
        res: dict[str, Any] = {}
        for rule, feats in EMU_RULES.items():
            coef = None
            if feats is not None:
                xd = emu_design(f, feats)
                coef = np.linalg.lstsq(xd[tr], line[tr], rcond=None)[0]
            pr = emu_predict(rule, f, coef)
            ho = ~tr
            res[rule] = {
                "holdout_exact": round(float((pr[ho] == line[ho]).mean()), 4),
                "holdout_within1": round(
                    float((np.abs(pr[ho] - line[ho]) <= 1).mean()), 4
                ),
                "holdout_mean_diff": round(float((pr[ho] - line[ho]).mean()), 3),
            }
            if feats is not None:
                full = np.linalg.lstsq(emu_design(f, feats), line, rcond=None)[0]
                pf = emu_predict(rule, f, full)
                res[rule]["coef_all_days"] = [round(float(c), 4) for c in full]
            else:
                pf = pr
            res[rule]["all_exact"] = round(float((pf == line).mean()), 4)
            res[rule]["all_within1"] = round(float((np.abs(pf - line) <= 1).mean()), 4)
        # context only (uses our model): half(exp_mean) of the baseline exposure
        best = max(EMU_RULES, key=lambda r: (res[r]["holdout_exact"],
                                             res[r]["holdout_within1"]))
        feats = EMU_RULES[best]
        coef_all = (None if feats is None else
                    np.linalg.lstsq(emu_design(f, feats), line, rcond=None)[0])
        emu_coef[si] = (best, coef_all)
        emu[FAMILY[stat]] = {"n": len(ks), "fit_days": sorted(fit_days),
                             "rules": res, "chosen": best}
        print(f"emu {stat}: chosen {best} {res[best]}", flush=True)
    report["line_emulation"] = emu

    # --- families
    def build_fam(a: dict[str, NDArr], si: int, sbmap: bool) -> tuple[Fam, NDArr]:
        per, labels = periods(a)
        sel = np.nonzero((a["stat"] == si) & (a["found"] == 1))[0]
        sub = {k: v[sel] for k, v in a.items()}
        fe = emu_features(a, sel)
        rule, coef = emu_coef[si]
        l_emu = emu_predict(rule, fe, coef)
        key = race_key(sub["p_team"])
        ew, el = race_expect(key)
        # half(exp_mean) of today's exposure (K 2, window 20), count mean else
        s20, ok20 = share_of(sub, 20, np.full(len(sel), ce.K_SHARE))
        em = s20 * (np.nan_to_num(sub["cw"]) * ew + np.nan_to_num(sub["cl"]) * el)
        em = np.where(ok20 & ~np.isnan(sub["cw"]), em, fe["m20"])
        l_exp = np.floor(em) + 0.5
        l_sb = l_emu.copy()
        has_sb = np.zeros(len(sel), bool)
        if sbmap:
            for j, i in enumerate(sel):
                k = (int(a["eid"][i]), int(a["order"][i]), int(a["pid"][i]), si)
                r = sb_line.get(k)
                if r is not None:
                    l_sb[j] = float(r["line"])
                    has_sb[j] = True
        lines = np.column_stack(
            [l_emu, l_exp, np.maximum(l_exp - 1, 0.5), l_exp + 1, l_sb])
        y = (sub["actual"][:, None] > lines).astype(float)
        cp = count_p_cols(sub["sample"], sub["n_sample"], lines)
        exp_b = np.digitize(sub["pall"], EXP_EDGES)
        okey = np.array([ce.MAP_ORDER_KEYS.index(ce.map_order_key(
            int(b) or None, int(o))) for b, o in zip(sub["bo"], sub["order"],
                                                     strict=True)])
        fam = Fam(si, sub, per[sel], y, lines, cp, key, ew, el, exp_b,
                  sub["map_id"].astype(int), okey)
        return fam, has_sb

    # baseline check: the vectorised mixture vs cs2_engine.exposure_p at 10.5
    if checks:
        ci = np.array([c[0] for c in checks])
        ref = np.array([c[1] for c in checks])
        aa = {k: v[ci] for k, v in raw.items()}
        s, _ = share_of(aa, 20, np.full(len(ci), ce.K_SHARE))
        mine = mix_p(race_key(aa["p_team"]), s, aa["cw"], aa["cl"], aa["phi_eng"],
                     np.full((len(ci), 1), 10.5), ce.MIN_VAR_RATIO)[:, 0]
        dmax = float(np.abs(mine - ref).max())
        report["engine_check"] = {"n": len(ci), "max_abs_diff": dmax}
        print(f"engine check n={len(ci)} max diff {dmax:.2e}", flush=True)
        if dmax > 1e-5:
            raise SystemExit("vectorised exposure differs from cs2_engine.exposure_p")

    cfgs: list[Cfg] = [
        Cfg("C0_rows_phi", phi="rows"),
        Cfg("C2_k_grid", phi="rows", k="grid"),
        Cfg("C2b_k_by_experience", phi="rows", k="grid_exp"),
        Cfg("C3_map_mult", phi="rows", mult=("map",)),
        Cfg("C4_phi_scale", phi="rows", scale="grid", floor=0.05),
        Cfg("C5_order_mult", phi="rows", mult=("order",)),
        Cfg("C6_window10", phi="rows", window=10, k="grid"),
        Cfg("C6_window40", phi="rows", window=40, k="grid"),
    ]
    combo = Cfg("COMBO_c2b_c3_c4_c5", phi="rows", k="grid_exp", scale="grid",
                floor=0.05, mult=("map", "order"))
    results: dict[str, Any] = {}
    audit: dict[str, Any] = {}
    fam_order = (0, 1, 2, 3)
    for si in fam_order:
        famname = FAMILY[STATS[si]]
        tf = time.time()
        f_raw, has_sb = build_fam(raw, si, True)
        f_cln, has_sb_c = build_fam(cln, si, True)
        nper = int(max(f_raw.period.max(), f_cln.period.max())) + 1
        _, labels = periods(raw)
        audit_p = labels.index("audit")
        is_eval = (f_raw.a["ts"] >= eval_ts) & (f_raw.period < audit_p)
        base_cfg = Cfg("BASELINE", exposure=si != 3)
        pb, vb, _ = run_cfg(f_raw, base_cfg, nper)
        famres: dict[str, Any] = {"baseline": {}, "candidates": {}}
        grp = f_raw.a["eid"]
        for j, col in enumerate(LINE_COLS[:4]):
            famres["baseline"][col] = summary(pb[is_eval, j], f_raw.y[is_eval, j])
        # walk-forward by month, baseline at the emulated line
        famres["baseline_by_month"] = {
            labels[per]: summary(pb[(f_raw.period == per), 0],
                                 f_raw.y[(f_raw.period == per), 0])
            for per in np.unique(f_raw.period) if per < audit_p
        }
        famres["eval_n"] = {
            "player_maps": int(is_eval.sum()),
            "matches": int(len(np.unique(grp[is_eval]))),
            "months": sorted({labels[p] for p in f_raw.period[is_eval]}),
        }
        print(f"{famname}: rows {len(pb)} eval {int(is_eval.sum())} "
              f"baseline emu {famres['baseline']['emu']} ({time.time() - tf:.0f}s)",
              flush=True)
        cand_p: dict[str, tuple[Fam, NDArr]] = {"BASELINE": (f_raw, pb)}
        # headshots: every candidate is C1 (clean data, exposure) plus its change
        todo: list[tuple[Cfg, Fam]] = [(c, f_cln if si == 3 else f_raw) for c in cfgs]
        todo.append((Cfg("C1_clean_hs_exposure", phi="engine"), f_cln))
        todo.append((Cfg("C1_clean_rows_phi", phi="rows"), f_cln))
        todo.append((dataclasses.replace(combo), f_cln))
        for cfg, fam in todo:
            pc, vc, info = run_cfg(fam, cfg, nper)
            cand_p[cfg.name] = (fam, pc)
            # align to the baseline's rows by (event, map, player)
            if fam is f_raw:
                ib = np.nonzero(is_eval)[0]
                ic = ib
            else:
                pos = row_pos(fam)
                kb = row_keys(f_raw)
                pairs = [(i, pos.get(kb[i])) for i in np.nonzero(is_eval)[0]]
                ib = np.array([i for i, c in pairs if c is not None])
                ic = np.array([c for _, c in pairs if c is not None])
            entry: dict[str, Any] = {"info": info, "n_aligned": int(len(ib))}
            for j, col in enumerate(LINE_COLS[:4]):
                yb = f_raw.y[ib, j]
                yc = fam.y[ic, j]
                same = yb == yc
                pbj, pcj, yy = pb[ib, j][same], pc[ic, j][same], yb[same]
                d = ll_vec(pcj, yy) - ll_vec(pbj, yy)
                sc = summary(pcj, yy)
                sb_ = summary(pbj, yy)
                entry[col] = {
                    "n": int(same.sum()),
                    "matches": int(len(np.unique(grp[ib][same]))),
                    "delta_ll": boot_mean(d, grp[ib][same], args.reps if col == "emu"
                                          else max(args.reps // 5, 100), rng),
                    "delta_brier": round(float(((pcj - yy) ** 2 - (pbj - yy) ** 2)
                                               .mean()), 6),
                    "delta_auc": round(sc["auc"] - sb_["auc"], 4),
                    "cand": sc,
                    "base": sb_,
                }
            entry["exposure_share"] = info.get("exposure_share")
            famres["candidates"][cfg.name] = entry
            e = entry["emu"]
            print(f"  {cfg.name}: dLL {e['delta_ll']} dAUC {e['delta_auc']} "
                  f"slope {e['cand']['slope']} cov70 {e['cand']['cov70']} "
                  f"({time.time() - tf:.0f}s)", flush=True)
        results[famname] = famres

        # --- audit on Superbet's real lines vs its devigged price
        fa: dict[str, Any] = {}
        for name, (fam, pc) in cand_p.items():
            hs = has_sb if fam is f_raw else has_sb_c
            sel = np.nonzero(hs & (fam.period == audit_p))[0]
            if len(sel) < 100:
                continue
            ks = [(int(fam.a["eid"][i]), int(fam.a["order"][i]), int(fam.a["pid"][i]),
                   si) for i in sel]
            pr = np.array([float(sb_line[k]["p_prop"]) for k in ks])
            yy = np.array([float(sb_line[k]["y"]) for k in ks])
            ev = np.array([str(sb_line[k]["superbet_event_id"]) for k in ks])
            days = np.array([sb_line[k]["date"] for k in ks])
            pm = pc[sel, 4]
            ent: dict[str, Any] = {
                "n": int(len(sel)),
                "series": int(len(set(ev.tolist()))),
                "y_mismatch_vs_history": int((fam.y[sel, 4] != yy).sum()),
                "auc_model": round(auc(pm, yy), 4),
                "auc_price": round(auc(pr, yy), 4),
                "ll_model": round(float(ll_vec(pm, yy).mean()), 5),
                "ll_price": round(float(ll_vec(pr, yy).mean()), 5),
                "delta_ll_model_minus_price": boot_mean(
                    ll_vec(pm, yy) - ll_vec(pr, yy), ev, args.reps, rng),
                "slope_model": round(slope(pm, yy), 3),
                "cov70_model": coverage(pm, yy),
            }
            for mode in ("walk", "lodo"):
                mask, pa, pbl = oos_blend(days, logit(pr), logit(pm), yy, mode)
                if mask.sum() < 100:
                    continue
                d = ll_vec(pbl[mask], yy[mask]) - ll_vec(pa[mask], yy[mask])
                ent[f"blend_{mode}"] = {
                    "n": int(mask.sum()),
                    "delta_ll_blend_minus_price_recal": boot_mean(
                        d, ev[mask], args.reps, rng),
                    "auc_blend": round(auc(pbl[mask], yy[mask]), 4),
                    "auc_price": round(auc(pr[mask], yy[mask]), 4),
                }
            fa[name] = ent
            bw = ent.get("blend_walk", {}).get("delta_ll_blend_minus_price_recal")
            print(f"  audit {name}: n {ent['n']} AUC m {ent['auc_model']} "
                  f"p {ent['auc_price']} dLL {ent['delta_ll_model_minus_price']} "
                  f"blend walk {bw}",
                  flush=True)
        audit[famname] = fa
        (out / "report.json").write_text(json.dumps(
            {**report, "results": results, "audit": audit}, indent=1, default=str))
    report["results"] = results
    report["audit"] = audit
    report["notes"] = {
        "line_emulation": "Superbet settled days place lines only; no probability "
        "curve or estimator parameter is fitted on them.",
        "selection": "every grid value / multiplier / dispersion from periods "
        "strictly before the evaluated month (audit period: before "
        f"{AUDIT_FROM}); chosen by log-loss at the emulated line.",
        "comparisons": f"{len(cfgs) + 3} candidates x 4 families",
    }
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
    (out / "report.txt").write_text(text_report(report), encoding="utf-8")
    print(f"report {out / 'report.json'} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
