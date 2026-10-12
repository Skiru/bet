#!/usr/bin/env python3
"""Read-only measurement: football OUTCOME markets priced from the statistics.

Goal C2 of docs/sofa/history/PLAN_NOC_2026-10-12.md. Nothing here is wired
into the pipeline, nothing is written to the database or to config/: the
football history is the parsed pickle SHEET's `football_rating.load_history`
keeps (`data/cache/football_history.pkl`, opened read-only; friendlies are
already out - `parse_event` drops `FRIENDLY_COMPETITION_IDS`, the
`bet.sofa.comparability` list). With `--db` the pickle's fingerprint is
checked against that database (opened `mode=ro`) and the match is reported.

Walk-forward, as of each match: the football rating book and every team's own
sample are updated only with matches strictly before the one being priced
(the same time-ordered replay `measure_dependence_goals.rating_centres` and
`calibrate_from_cache` use).

Centres per side, goals_for and goals_1h_for:
  rating   `FootballForecast.centre(metric, side)` - the as-of rating SHEET
           blends in (needs MIN_TEAM_MATCHES per side);
  sheet    SHEET's centre shape: the side's newest SAMPLE_N matches (the same
           competition first, `comparability.pick_same_competition`), its mean
           shrunk toward the league prior with K_CENTRE (football 15; goals
           stay at the sport's K), then W_FOOTBALL_RATING x rating. The prior
           is the AS-OF league mean (venue-blind; global when the league has
           < MIN_LEAGUE_PRIOR matches), not config/sofa_league_baselines.json,
           which was fitted on rows inside the test window.

Models (independent goals per side; Dixon-Coles / bivariate Poisson were
measured and declined 2026-10-08 - only the independence check is reported):
  pois_rating     Poisson on the rating centres
  nb_rating       NB on the rating centres, one r fitted on TRAIN
  nb_sheet_train  NB on the sheet centres, one r fitted on TRAIN
  nb_sheet_cfg    NB on the sheet centres, alpha per competition from
                  config/sofa_count_dispersion.json (fitted up to 2026-10-07:
                  a dispersion parameter that saw the test window)

Base rate: the competition's own frequency of each outcome as of the match,
shrunk toward the gender's global frequency with BASE_M matches' weight.

Markets scored on TEST: 1X2, double chance, draw-no-bet (draws dropped),
both teams to score, goals parity, half-time result, exact score (cells 0..3
x 0..3 plus "other"). Per market: log-loss of the model minus the base rate
(match bootstrap 95% CI; negative = the model is better), the calibration by
p bucket of every selection, and the share of selections at p >= 0.70. Split
by the fixture's goals link (LINKED / LINKED_BY_STRENGTH / UNLINKED), gender
and month.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_result_model.py \
        --db data/refit_2026-10-12/sofa_replay.db \
        --out data/refit_2026-10-12/c2/football_result_model.json \
        --md-out data/refit_2026-10-12/c2/football_result_model.md
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bet.sofa import football_rating as fr
from bet.sofa.comparability import SAME_COMPETITION_METRICS, pick_same_competition
from bet.sofa.count_dispersion import DispersionTable, load_table
from bet.sofa.samples import INDEXED_HISTORY_LIMIT
from scripts.sofa.measure_dependence_goals import (
    bootstrap_ratio,
    fit_scalar,
    load_pickle,
    note,
    ts_of,
)

F64 = NDArray[np.float64]

DEFAULT_HISTORY = Path("data/cache/football_history.pkl")
TRAIN_FROM = "2025-10-01"
TEST_FROM = "2026-06-09"
TEST_TO = "2026-10-07"
METRICS = ("goals_for", "goals_1h_for")
SAMPLE_N = 10
MIN_SAMPLE = 5  # config.min_sample (SHEET's THIN_SAMPLE bar)
K_CENTRE_GOALS = 15.0  # K_CENTRE.by_sport.football; goals keep the sport's K
MIN_LEAGUE_PRIOR = 30
BASE_M = 30.0
KMAX = 12
PRINTABLE = 0.70
BUCKETS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0001)
CS_CELLS = tuple((i, j) for i in range(4) for j in range(4))
N_CS = len(CS_CELLS) + 1  # + "other"
LINKS = (fr.LINKED, fr.LINKED_BY_STRENGTH, fr.UNLINKED)
MODELS = ("pois_rating", "nb_rating", "nb_sheet_train", "nb_sheet_cfg")
PRIMARY = "nb_sheet_cfg"


# --------------------------------------------------------------------------
# distributions
# --------------------------------------------------------------------------


def count_pmf(lam: F64, r: F64 | None, kmax: int = KMAX) -> F64:
    """(N, kmax+1) pmf of a count with mean `lam`: Poisson when `r` is None,
    else NB with variance lam + lam^2 / r (r per row). By the recursion
    p(k+1) = p(k) (k + r) / (k + 1) * lam / (r + lam), renormalised over
    0..kmax (the truncated tail is below 1e-6 at football means)."""
    lam = np.maximum(np.asarray(lam, dtype=np.float64), 1e-9)
    out = np.empty((len(lam), kmax + 1))
    if r is None:
        out[:, 0] = np.exp(-lam)
        for k in range(kmax):
            out[:, k + 1] = out[:, k] * lam / (k + 1)
    else:
        rr = np.asarray(r, dtype=np.float64)
        q = lam / (rr + lam)
        out[:, 0] = np.exp(rr * np.log(rr / (rr + lam)))
        for k in range(kmax):
            out[:, k + 1] = out[:, k] * (k + rr) / (k + 1) * q
    return out / out.sum(axis=1, keepdims=True)  # type: ignore[no-any-return]


def score_grid(pa: F64, pb: F64) -> F64:
    """(N, K, K) joint of independent home / away goals."""
    return pa[:, :, None] * pb[:, None, :]


@dataclass(frozen=True)
class MarketProbs:
    res: F64  # (N, 3) home / draw / away
    btts: F64  # (N,)
    odd: F64  # (N,)
    cs: F64  # (N, N_CS)


def market_probs(grid: F64) -> MarketProbs:
    k = grid.shape[1]
    i = np.arange(k)[:, None]
    j = np.arange(k)[None, :]
    home = grid[:, i > j].sum(axis=1)
    away = grid[:, i < j].sum(axis=1)
    draw = grid[:, (i == j)].sum(axis=1)
    btts = grid[:, (i >= 1) & (j >= 1)].sum(axis=1)
    odd = grid[:, ((i + j) % 2) == 1].sum(axis=1)
    cells = np.stack([grid[:, a, b] for a, b in CS_CELLS], axis=1)
    other = np.clip(1.0 - cells.sum(axis=1), 0.0, 1.0)
    return MarketProbs(
        res=np.stack([home, draw, away], axis=1),
        btts=btts,
        odd=odd,
        cs=np.concatenate([cells, other[:, None]], axis=1),
    )


def cs_index(x: int, y: int) -> int:
    for n, (a, b) in enumerate(CS_CELLS):
        if (a, b) == (x, y):
            return n
    return len(CS_CELLS)


def res_index(x: float, y: float) -> int:
    return 0 if x > y else (1 if x == y else 2)


# --------------------------------------------------------------------------
# as-of state: base rates, priors, own samples
# --------------------------------------------------------------------------


@dataclass
class _Freq:
    res: F64 = field(default_factory=lambda: np.zeros(3))
    btts: float = 0.0
    odd: float = 0.0
    cs: F64 = field(default_factory=lambda: np.zeros(N_CS))
    n: int = 0
    ht: F64 = field(default_factory=lambda: np.zeros(3))
    n_ht: int = 0

    def add(self, x: int, y: int, ht: tuple[int, int] | None) -> None:
        self.res[res_index(x, y)] += 1
        self.btts += float(x >= 1 and y >= 1)
        self.odd += float((x + y) % 2 == 1)
        self.cs[cs_index(x, y)] += 1
        self.n += 1
        if ht is not None:
            self.ht[res_index(*ht)] += 1
            self.n_ht += 1


def shrunk(count: F64 | float, n: int, glob: F64 | float, m: float = BASE_M) -> Any:
    """(count + m * global) / (n + m): the league's frequency, pulled toward the
    global one by m matches' weight."""
    return (np.asarray(count) + m * np.asarray(glob)) / (n + m)


def base_probs(league: _Freq | None, glob: _Freq) -> dict[str, Any]:
    """The base-rate model's probabilities for one match, as of it."""
    gn = max(glob.n, 1)
    gh = max(glob.n_ht, 1)
    g_res, g_cs = glob.res / gn, glob.cs / gn
    g_btts, g_odd = glob.btts / gn, glob.odd / gn
    g_ht = glob.ht / gh if glob.n_ht else np.full(3, 1.0 / 3.0)
    lg = league if league is not None else _Freq()
    return {
        "res": shrunk(lg.res, lg.n, g_res),
        "btts": float(shrunk(lg.btts, lg.n, g_btts)),
        "odd": float(shrunk(lg.odd, lg.n, g_odd)),
        "cs": shrunk(lg.cs, lg.n, g_cs),
        "ht": shrunk(lg.ht, lg.n_ht, g_ht),
    }


@dataclass
class _Mean:
    total: float = 0.0
    n: int = 0

    def add(self, v: float) -> None:
        self.total += v
        self.n += 1

    @property
    def mean(self) -> float | None:
        return self.total / self.n if self.n else None


def sheet_centre(
    sample: Sequence[float],
    prior: float | None,
    rated: float,
    k: float = K_CENTRE_GOALS,
) -> float:
    """SHEET's centre: sample mean shrunk to the prior with K, then the rating
    blend at W_FOOTBALL_RATING (run_sheet: centre = W*rated + (1-W)*sample)."""
    n = len(sample)
    mean = statistics.mean(sample)
    centre = mean if prior is None else n / (n + k) * mean + k / (n + k) * prior
    w = fr.W_FOOTBALL_RATING
    return w * rated + (1.0 - w) * centre


# --------------------------------------------------------------------------
# the walk-forward pass
# --------------------------------------------------------------------------

ROW_KEYS = (
    "ts",
    "comp",
    "women",
    "link",
    "x",
    "y",
    "x1",
    "y1",
    "lh",
    "la",
    "sh",
    "sa",
    "lh1",
    "la1",
    "sh1",
    "sa1",
    "b_btts",
    "b_odd",
)


def collect_rows(
    history: Sequence[fr.FootballResult], from_ts: int, to_ts: int
) -> dict[str, F64]:
    """One row per match in [from_ts, to_ts) whose two sides both have a
    rating centre and a sample of MIN_SAMPLE for goals_for. Every state read
    for a row (rating book, samples, priors, base frequencies) holds only
    matches strictly before it in time order."""
    book = fr.RatingBook()
    hist: dict[tuple[int, str], list[tuple[float, int]]] = defaultdict(list)
    lg_mean: dict[tuple[int, str], _Mean] = defaultdict(_Mean)
    gl_mean: dict[tuple[bool, str], _Mean] = defaultdict(_Mean)
    lg_freq: dict[int, _Freq] = {}
    gl_freq: dict[bool, _Freq] = defaultdict(_Freq)
    cols: dict[str, list[float]] = {k: [] for k in ROW_KEYS}
    vec: dict[str, list[F64]] = {"b_res": [], "b_cs": [], "b_ht": []}

    def sample(team: int, comp: int, metric: str) -> list[float]:
        past = hist[(team, metric)]
        if metric in SAME_COMPETITION_METRICS:
            picked = pick_same_competition(
                past[: -INDEXED_HISTORY_LIMIT - 1 : -1],
                comp,
                SAMPLE_N,
                lambda p: p[1],
                lambda p: True,
            )
            if picked is not None:
                return [p[0] for p in picked]
        return [p[0] for p in past[-SAMPLE_N:]]

    def prior(comp: int, women: bool, metric: str) -> float | None:
        lm = lg_mean.get((comp, metric))
        if lm is not None and lm.n >= MIN_LEAGUE_PRIOR:
            return lm.mean
        return gl_mean[(women, metric)].mean

    for r in history:
        if r.ts >= to_ts:
            break
        vals = {m: r.values[m] for m in METRICS if m in r.values}
        if "goals_for" not in vals:
            continue
        x, y = (int(v) for v in vals["goals_for"])
        ht = vals.get("goals_1h_for")
        ht_i = (int(ht[0]), int(ht[1])) if ht is not None else None
        if ht_i is not None and (ht_i[0] > x or ht_i[1] > y):
            ht_i = None  # an inconsistent half is no half
        if r.ts >= from_ts:
            fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
            row = _price_row(fc, r, x, y, ht_i, sample, prior)
            if row is not None:
                for k, v in row.items():
                    cols[k].append(v)
                b = base_probs(lg_freq.get(r.competition_id), gl_freq[r.women])
                cols["b_btts"].append(b["btts"])
                cols["b_odd"].append(b["odd"])
                vec["b_res"].append(b["res"])
                vec["b_cs"].append(b["cs"])
                vec["b_ht"].append(b["ht"])
        # --- update, after the row was priced ---
        book.update(replace(r, values=vals))
        for metric, (vh, va) in vals.items():
            hist[(r.home_id, metric)].append((vh, r.competition_id))
            hist[(r.away_id, metric)].append((va, r.competition_id))
            for v in (vh, va):
                lg_mean[(r.competition_id, metric)].add(v)
                gl_mean[(r.women, metric)].add(v)
            for team in (r.home_id, r.away_id):
                h = hist[(team, metric)]
                if len(h) > 2 * INDEXED_HISTORY_LIMIT:
                    del h[:INDEXED_HISTORY_LIMIT]
        lg_freq.setdefault(r.competition_id, _Freq()).add(x, y, ht_i)
        gl_freq[r.women].add(x, y, ht_i)
    out = {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}
    n = len(out["ts"])
    out["b_res"] = np.asarray(vec["b_res"]).reshape(n, 3)
    out["b_cs"] = np.asarray(vec["b_cs"]).reshape(n, N_CS)
    out["b_ht"] = np.asarray(vec["b_ht"]).reshape(n, 3)
    return out


def _price_row(
    fc: fr.FootballForecast,
    r: fr.FootballResult,
    x: int,
    y: int,
    ht: tuple[int, int] | None,
    sample: Callable[[int, int, str], list[float]],
    prior: Callable[[int, bool, str], float | None],
) -> dict[str, float] | None:
    nan = math.nan
    row: dict[str, float] = {}
    for metric, suffix in (("goals_for", ""), ("goals_1h_for", "1")):
        ch = fc.centre(metric, "side_a")
        ca = fc.centre(metric, "side_b")
        sa_s = sample(r.home_id, r.competition_id, metric)
        sb_s = sample(r.away_id, r.competition_id, metric)
        ok = (
            ch is not None
            and ca is not None
            and len(sa_s) >= MIN_SAMPLE
            and len(sb_s) >= MIN_SAMPLE
        )
        if not ok:
            if metric == "goals_for":
                return None
            row.update(
                {
                    f"lh{suffix}": nan,
                    f"la{suffix}": nan,
                    f"sh{suffix}": nan,
                    f"sa{suffix}": nan,
                }
            )
            continue
        assert ch is not None and ca is not None
        pr = prior(r.competition_id, r.women, metric)
        row[f"lh{suffix}"] = ch[0]
        row[f"la{suffix}"] = ca[0]
        row[f"sh{suffix}"] = sheet_centre(sa_s, pr, ch[0])
        row[f"sa{suffix}"] = sheet_centre(sb_s, pr, ca[0])
    link = fc.fixture_link()
    row.update(
        {
            "ts": float(r.ts),
            "comp": float(r.competition_id),
            "women": float(r.women),
            "link": float(LINKS.index(link)),
            "x": float(x),
            "y": float(y),
            "x1": float(ht[0]) if ht is not None else nan,
            "y1": float(ht[1]) if ht is not None else nan,
        }
    )
    return row


def subset(d: dict[str, F64], mask: NDArray[np.bool_]) -> dict[str, F64]:
    return {k: v[mask] for k, v in d.items()}


# --------------------------------------------------------------------------
# models
# --------------------------------------------------------------------------


def fit_r(lh: F64, la: F64, x: F64, y: F64) -> float:
    """ML NB r (one scalar) of independent sides around fixed centres."""
    xi = np.minimum(x, KMAX).astype(np.int64)
    yi = np.minimum(y, KMAX).astype(np.int64)
    idx = np.arange(len(xi))

    def ll(log_r: float) -> float:
        r = np.full(len(lh), math.exp(log_r))
        pa, pb = count_pmf(lh, r), count_pmf(la, r)
        return float(
            np.log(np.maximum(pa[idx, xi], 1e-300)).sum()
            + np.log(np.maximum(pb[idx, yi], 1e-300)).sum()
        )

    return math.exp(fit_scalar(ll, math.log(1.0), math.log(2000.0)))


def cfg_r(table: DispersionTable, metric: str, comps: F64) -> F64:
    out = np.empty(len(comps))
    cache: dict[int, float] = {}
    for n, c in enumerate(comps.astype(np.int64)):
        cid = int(c)
        if cid not in cache:
            disp = table.read("football", metric, cid)
            cache[cid] = math.inf if disp is None else 1.0 / disp.alpha
        out[n] = cache[cid]
    return out


def model_pmfs(
    d: dict[str, F64],
    model: str,
    par: dict[str, float],
    table: DispersionTable,
    half: bool,
) -> tuple[F64, F64]:
    s = "1" if half else ""
    metric = "goals_1h_for" if half else "goals_for"
    if model == "pois_rating":
        return count_pmf(d[f"lh{s}"], None), count_pmf(d[f"la{s}"], None)
    if model == "nb_rating":
        r = np.full(len(d["ts"]), par[f"r_rating{s}"])
        return count_pmf(d[f"lh{s}"], r), count_pmf(d[f"la{s}"], r)
    if model == "nb_sheet_train":
        r = np.full(len(d["ts"]), par[f"r_sheet{s}"])
        return count_pmf(d[f"sh{s}"], r), count_pmf(d[f"sa{s}"], r)
    if model == "nb_sheet_cfg":
        r = cfg_r(table, metric, d["comp"])
        r = np.where(np.isfinite(r), r, 1e6)
        return count_pmf(d[f"sh{s}"], r), count_pmf(d[f"sa{s}"], r)
    raise ValueError(model)


def fit_params(train: dict[str, F64]) -> dict[str, float]:
    par: dict[str, float] = {"train_matches": float(len(train["ts"]))}
    par["r_rating"] = fit_r(train["lh"], train["la"], train["x"], train["y"])
    par["r_sheet"] = fit_r(train["sh"], train["sa"], train["x"], train["y"])
    h = np.isfinite(train["lh1"]) & np.isfinite(train["x1"])
    t1 = subset(train, h)
    par["train_ht_matches"] = float(h.sum())
    par["r_rating1"] = fit_r(t1["lh1"], t1["la1"], t1["x1"], t1["y1"])
    par["r_sheet1"] = fit_r(t1["sh1"], t1["sa1"], t1["x1"], t1["y1"])
    return par


# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------


def _ll(p: F64) -> F64:
    return -np.log(np.clip(p, 1e-12, 1.0))


def _bin_ll(p: F64, o: F64) -> F64:
    q = np.clip(p, 1e-12, 1.0 - 1e-12)
    return -(o * np.log(q) + (1.0 - o) * np.log(1.0 - q))


@dataclass(frozen=True)
class Selection:
    market: str
    name: str
    p: F64
    o: F64
    match: NDArray[np.int64]  # index of the match, for the bootstrap


def selections(
    mp: MarketProbs,
    ht: MarketProbs | None,
    x: F64,
    y: F64,
    x1: F64 | None,
    y1: F64 | None,
    ht_rows: NDArray[np.int64] | None,
) -> list[Selection]:
    n = len(x)
    rows = np.arange(n)
    h, d, a = mp.res[:, 0], mp.res[:, 1], mp.res[:, 2]
    oh, od, oa = (x > y).astype(float), (x == y).astype(float), (x < y).astype(float)
    nd = od == 0
    sel = [
        Selection("1x2", "home", h, oh, rows),
        Selection("1x2", "draw", d, od, rows),
        Selection("1x2", "away", a, oa, rows),
        Selection("double_chance", "1X", h + d, oh + od, rows),
        Selection("double_chance", "X2", d + a, od + oa, rows),
        Selection("double_chance", "12", h + a, oh + oa, rows),
        Selection("dnb", "home", (h / (h + a))[nd], oh[nd], rows[nd]),
        Selection("dnb", "away", (a / (h + a))[nd], oa[nd], rows[nd]),
        Selection("btts", "yes", mp.btts, ((x >= 1) & (y >= 1)).astype(float), rows),
        Selection(
            "btts", "no", 1 - mp.btts, 1 - ((x >= 1) & (y >= 1)).astype(float), rows
        ),
        Selection("parity", "odd", mp.odd, ((x + y) % 2 == 1).astype(float), rows),
        Selection("parity", "even", 1 - mp.odd, ((x + y) % 2 == 0).astype(float), rows),
    ]
    xi, yi = x.astype(np.int64), y.astype(np.int64)
    cs_o = np.array([cs_index(int(u), int(v)) for u, v in zip(xi, yi, strict=True)])
    for c in range(len(CS_CELLS)):  # "other" is a bucket, not a selection
        name = f"{CS_CELLS[c][0]}-{CS_CELLS[c][1]}"
        sel.append(
            Selection("exact_score", name, mp.cs[:, c], (cs_o == c).astype(float), rows)
        )
    if ht is not None and x1 is not None and y1 is not None and ht_rows is not None:
        for k, (name, o) in enumerate(
            (
                ("home", (x1 > y1)),
                ("draw", (x1 == y1)),
                ("away", (x1 < y1)),
            )
        ):
            sel.append(
                Selection("ht_result", name, ht.res[:, k], o.astype(float), ht_rows)
            )
    return sel


def _boot_mean(v: F64, reps: int) -> list[float]:
    return list(bootstrap_ratio(v, np.ones(len(v)), reps))


def match_loglosses(
    mp: MarketProbs,
    ht: MarketProbs | None,
    base: dict[str, F64],
    x: F64,
    y: F64,
    x1: F64,
    y1: F64,
    ht_mask: NDArray[np.bool_],
) -> dict[str, tuple[F64, F64]]:
    """Per-match log-loss (model, base) of each market."""
    n = len(x)
    rows = np.arange(n)
    ri = np.where(x > y, 0, np.where(x == y, 1, 2))
    out: dict[str, tuple[F64, F64]] = {}
    out["1x2"] = (_ll(mp.res[rows, ri]), _ll(base["b_res"][rows, ri]))
    oh, od, oa = (
        (ri == 0).astype(float),
        (ri == 1).astype(float),
        (ri == 2).astype(float),
    )

    def dc(res: F64) -> F64:
        h, d, a = res[:, 0], res[:, 1], res[:, 2]
        return (
            _bin_ll(h + d, oh + od)
            + _bin_ll(d + a, od + oa)
            + _bin_ll(h + a, oh + oa)
        ) / 3.0

    out["double_chance"] = (dc(mp.res), dc(base["b_res"]))
    nd = ri != 1
    out["dnb"] = (
        _bin_ll((mp.res[:, 0] / (mp.res[:, 0] + mp.res[:, 2]))[nd], oh[nd]),
        _bin_ll(
            (base["b_res"][:, 0] / (base["b_res"][:, 0] + base["b_res"][:, 2]))[nd],
            oh[nd],
        ),
    )
    ob = ((x >= 1) & (y >= 1)).astype(float)
    out["btts"] = (_bin_ll(mp.btts, ob), _bin_ll(base["b_btts"], ob))
    oo = ((x + y) % 2 == 1).astype(float)
    out["parity"] = (_bin_ll(mp.odd, oo), _bin_ll(base["b_odd"], oo))
    ci = np.array([cs_index(int(u), int(v)) for u, v in zip(x, y, strict=True)])
    out["exact_score"] = (_ll(mp.cs[rows, ci]), _ll(base["b_cs"][rows, ci]))
    if ht is not None and ht_mask.any():
        hx, hy = x1[ht_mask], y1[ht_mask]
        hi = np.where(hx > hy, 0, np.where(hx == hy, 1, 2))
        hr = np.arange(len(hx))
        out["ht_result"] = (_ll(ht.res[hr, hi]), _ll(base["b_ht"][ht_mask][hr, hi]))
    return out


def calibration(
    sels: Sequence[Selection], reps: int, buckets: Sequence[float] = BUCKETS
) -> list[dict[str, Any]]:
    """Every selection with p in each bucket: n, mean p, realised, realised
    minus p with a match-bootstrap 95% CI (clustered on the match)."""
    p = np.concatenate([s.p for s in sels])
    o = np.concatenate([s.o for s in sels])
    m = np.concatenate([s.match for s in sels])
    out: list[dict[str, Any]] = []
    for lo, hi in zip(buckets[:-1], buckets[1:], strict=True):
        sel = (p >= lo) & (p < hi)
        if not sel.any():
            out.append({"bucket": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": 0})
            continue
        mm, inv = np.unique(m[sel], return_inverse=True)
        num = np.bincount(inv, weights=o[sel] - p[sel]).astype(np.float64)
        den = np.bincount(inv).astype(np.float64)
        gap = bootstrap_ratio(num, den, reps)
        out.append(
            {
                "bucket": f"{lo:.1f}-{min(hi, 1.0):.1f}",
                "n": int(sel.sum()),
                "matches": int(len(mm)),
                "mean_p": float(p[sel].mean()),
                "realised": float(o[sel].mean()),
                "gap": list(gap),
            }
        )
    return out


def printable(sels: Sequence[Selection], n_matches: int, reps: int) -> dict[str, Any]:
    p = np.concatenate([s.p for s in sels])
    m = np.concatenate([s.match for s in sels])
    pr = p >= PRINTABLE
    cal = calibration(sels, reps, (PRINTABLE, 1.0001))[0]
    return {
        "selections": int(len(p)),
        "share_selections_printable": float(pr.mean()) if len(p) else math.nan,
        "share_matches_with_printable": (
            float(len(np.unique(m[pr])) / n_matches) if n_matches else math.nan
        ),
        "printable": cal,
    }


MARKETS = ("1x2", "double_chance", "dnb", "btts", "parity", "ht_result", "exact_score")


@dataclass(frozen=True)
class Priced:
    mp: MarketProbs
    ht: MarketProbs | None
    ht_mask: NDArray[np.bool_]
    sels: list[Selection]


def price(
    d: dict[str, F64], model: str, par: dict[str, float], table: DispersionTable
) -> Priced:
    pa, pb = model_pmfs(d, model, par, table, half=False)
    mp = market_probs(score_grid(pa, pb))
    ht_mask = np.isfinite(d["x1"]) & np.isfinite(d["lh1"])
    ht: MarketProbs | None = None
    if ht_mask.any():
        dh = subset(d, ht_mask)
        qa, qb = model_pmfs(dh, model, par, table, half=True)
        ht = market_probs(score_grid(qa, qb))
    sels = selections(
        mp,
        ht,
        d["x"],
        d["y"],
        d["x1"][ht_mask],
        d["y1"][ht_mask],
        np.flatnonzero(ht_mask),
    )
    return Priced(mp, ht, ht_mask, sels)


CURVE_STEP = 0.05
CURVE_MIN_N = 200
Curve = dict[tuple[str, str], F64]


def fit_curves(sels: Sequence[Selection]) -> Curve:
    """A bucket curve per (market, selection) fitted on TRAIN: the realised
    rate of each CURVE_STEP-wide p bucket holding CURVE_MIN_N selections (NaN
    = keep p), the shape of the pipeline's calibration buckets."""
    edges = np.arange(0.0, 1.0 + 1e-9, CURVE_STEP)
    acc: dict[tuple[str, str], F64] = {}
    for s in sels:
        key = (s.market, "*" if s.market == "exact_score" else s.name)
        a = acc.setdefault(key, np.zeros((2, len(edges) - 1)))
        b = np.clip(np.digitize(s.p, edges) - 1, 0, len(edges) - 2)
        a[0] += np.bincount(b, weights=s.o, minlength=len(edges) - 1)
        a[1] += np.bincount(b, minlength=len(edges) - 1)
    return {
        k: np.where(v[1] >= CURVE_MIN_N, v[0] / np.maximum(v[1], 1), np.nan)
        for k, v in acc.items()
    }


def apply_curves(sels: Sequence[Selection], curves: Curve) -> list[Selection]:
    edges = np.arange(0.0, 1.0 + 1e-9, CURVE_STEP)
    out: list[Selection] = []
    for s in sels:
        rates = curves.get((s.market, "*" if s.market == "exact_score" else s.name))
        if rates is None:
            out.append(s)
            continue
        b = np.clip(np.digitize(s.p, edges) - 1, 0, len(edges) - 2)
        q = rates[b]
        out.append(replace(s, p=np.where(np.isfinite(q), q, s.p)))
    return out


def score(
    d: dict[str, F64],
    model: str,
    par: dict[str, float],
    table: DispersionTable,
    reps: int,
    detail: bool = True,
    curves: Curve | None = None,
) -> dict[str, Any]:
    pr = price(d, model, par, table)
    mp, ht, ht_mask, sels = pr.mp, pr.ht, pr.ht_mask, pr.sels
    curved = apply_curves(sels, curves) if curves is not None else None
    lls = match_loglosses(mp, ht, d, d["x"], d["y"], d["x1"], d["y1"], ht_mask)
    out: dict[str, Any] = {
        "matches": int(len(d["ts"])),
        "ht_matches": int(ht_mask.sum()),
    }
    for market in MARKETS:
        if market not in lls:
            continue
        lm, lb = lls[market]
        ms = [s for s in sels if s.market == market]
        n_m = len(np.unique(np.concatenate([s.match for s in ms])))
        entry: dict[str, Any] = {
            "n": int(len(lm)),
            "logloss_model": float(lm.mean()),
            "logloss_base": float(lb.mean()),
            "d_logloss": _boot_mean(lm - lb, reps),
            "skill_pct": float(100.0 * (1.0 - lm.mean() / lb.mean())),
            "print": printable(ms, n_m, reps),
        }
        if curved is not None:
            mc = [s for s in curved if s.market == market]
            entry["print_after_curve"] = printable(mc, n_m, reps)
            if detail:
                entry["calibration_after_curve"] = calibration(mc, reps)
        if detail:
            entry["calibration"] = calibration(ms, reps)
            if market == "exact_score":
                entry["calibration_low"] = calibration(
                    ms, reps, (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 1.0001)
                )
        out[market] = entry
    # independence check: draw and 0-0, model mean vs observed
    od = (d["x"] == d["y"]).astype(float)
    o00 = ((d["x"] == 0) & (d["y"] == 0)).astype(float)
    out["independence"] = {
        "draw_mean_p": float(mp.res[:, 1].mean()),
        "draw_obs": float(od.mean()),
        "draw_gap": _boot_mean(od - mp.res[:, 1], reps),
        "nil_nil_mean_p": float(mp.cs[:, 0].mean()),
        "nil_nil_obs": float(o00.mean()),
        "nil_nil_gap": _boot_mean(o00 - mp.cs[:, 0], reps),
    }
    return out


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


def run(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {
        "windows": {
            "train_from": args.train_from,
            "test_from": args.test_from,
            "test_to": args.test_to,
        },
        "constants": {
            "SAMPLE_N": SAMPLE_N,
            "MIN_SAMPLE": MIN_SAMPLE,
            "K_CENTRE_GOALS": K_CENTRE_GOALS,
            "BASE_M": BASE_M,
            "MIN_LEAGUE_PRIOR": MIN_LEAGUE_PRIOR,
            "KMAX": KMAX,
            "W_FOOTBALL_RATING": fr.W_FOOTBALL_RATING,
            "shared_league_link": fr.RatingBook().shared_league_link,
        },
        "unfitted_constants": ["BASE_M", "MIN_LEAGUE_PRIOR"],
    }
    if args.db:
        import pickle

        stored_fp, _ = pickle.loads(Path(args.history).read_bytes())
        fp = fr.history_fingerprint(args.db)
        out["history_fingerprint_matches_db"] = stored_fp == fp
        out["history_db"] = str(args.db)
        note(f"pickle fingerprint matches {args.db}: {stored_fp == fp}")
    history = load_pickle(Path(args.history))
    note(f"history {len(history)} matches")
    ts_a, ts_b, ts_c = (
        ts_of(args.train_from),
        ts_of(args.test_from),
        ts_of(args.test_to),
    )
    rows = collect_rows(history, ts_a, ts_c)
    del history
    note(f"rows {len(rows['ts'])}")
    train = subset(rows, rows["ts"] < ts_b)
    test = subset(rows, rows["ts"] >= ts_b)
    par = fit_params(train)
    note(f"params {par}")
    out["params"] = par
    table = load_table(Path(args.dispersion)) if args.dispersion else load_table()
    out["test_matches"] = int(len(test["ts"]))
    out["models"] = {}
    curves: dict[str, Curve] = {}
    for model in MODELS:
        note(f"score {model}")
        curves[model] = fit_curves(price(train, model, par, table).sels)
        out["models"][model] = score(
            test, model, par, table, args.boot_reps, curves=curves[model]
        )
    splits: dict[str, Any] = {}
    for k, name in enumerate(LINKS):
        splits[f"link={name}"] = test["link"] == k
    splits["women"] = test["women"] > 0
    splits["men"] = test["women"] == 0
    months = np.array(
        [datetime.fromtimestamp(t, UTC).strftime("%Y-%m") for t in test["ts"]]
    )
    for mo in sorted(set(months.tolist())):
        splits[f"month={mo}"] = months == mo
    out["splits"] = {}
    for name, mask in splits.items():
        if mask.sum() < 200:
            out["splits"][name] = {"matches": int(mask.sum())}
            continue
        note(f"split {name}")
        out["splits"][name] = {
            m: score(
                subset(test, mask),
                m,
                par,
                table,
                args.boot_reps,
                detail=False,
                curves=curves[m],
            )
            for m in (PRIMARY, "nb_rating")
        }
    return out


# --------------------------------------------------------------------------
# markdown summary
# --------------------------------------------------------------------------


def _ci(v: Sequence[float], scale: float = 1.0, fmt: str = "{:+.4f}") -> str:
    return (
        f"{fmt.format(v[0] * scale)} [{fmt.format(v[1] * scale)}, "
        f"{fmt.format(v[2] * scale)}]"
    )


def _curve_cells(e: dict[str, Any]) -> str:
    c = e.get("print_after_curve")
    if c is None:
        return "- | - | -"
    pc = c["printable"]
    gap = _ci(pc["gap"], 100, "{:+.1f}") if pc.get("n") else "-"
    return f"{100 * c['share_selections_printable']:.1f}% | {pc.get('n', 0)} | {gap}"


def markdown(res: dict[str, Any]) -> str:
    lines = [
        "# Football outcome markets from the statistics (C2)\n",
        f"windows {res['windows']}, test matches {res['test_matches']}",
        f"params {json.dumps(res['params'])}\n",
    ]
    for model, r in res["models"].items():
        lines.append(f"## {model} (matches {r['matches']}, HT {r['ht_matches']})\n")
        lines.append(
            "| market | n | LL model | LL base | d LL [95%] | skill % | "
            "share p>=0.70 | printable n | mean p | realised | gap [95%] | "
            "curve: share | curve: n | curve: gap [95%] |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for market in MARKETS:
            e = r.get(market)
            if e is None:
                continue
            pc = e["print"]["printable"]
            gap = _ci(pc["gap"], 100, "{:+.1f}") if pc.get("n") else "-"
            lines.append(
                f"| {market} | {e['n']} | {e['logloss_model']:.4f} | "
                f"{e['logloss_base']:.4f} | {_ci(e['d_logloss'])} | "
                f"{e['skill_pct']:.2f} | "
                f"{100 * e['print']['share_selections_printable']:.1f}% | "
                f"{pc.get('n', 0)} | {pc.get('mean_p', math.nan):.3f} | "
                f"{pc.get('realised', math.nan):.3f} | {gap} | {_curve_cells(e)} |"
            )
        ind = r["independence"]
        lines.append(
            f"\nindependence: draw p {ind['draw_mean_p']:.4f} "
            f"obs {ind['draw_obs']:.4f} "
            f"gap {_ci(ind['draw_gap'], 100, '{:+.2f}')} pp; 0-0 p "
            f"{ind['nil_nil_mean_p']:.4f} obs {ind['nil_nil_obs']:.4f} gap "
            f"{_ci(ind['nil_nil_gap'], 100, '{:+.2f}')} pp\n"
        )
        lines.append(
            "calibration (selections p >= 0.5): market | bucket | n | mean p | "
            "realised | gap pp [95%]\n"
        )
        lines.append("| market | bucket | n | mean p | realised | gap pp |")
        lines.append("|---|---|---|---|---|---|")
        for market in MARKETS:
            e = r.get(market)
            if e is None:
                continue
            for b in e["calibration"]:
                if not b.get("n"):
                    continue
                lines.append(
                    f"| {market} | {b['bucket']} | {b['n']} | "
                    f"{b['mean_p']:.3f} | {b['realised']:.3f} | "
                    f"{_ci(b['gap'], 100, '{:+.1f}')} |"
                )
        lines.append("")
    lines.append("## splits (d LL [95%]; printable n, gap pp)\n")
    lines.append("| split | model | " + " | ".join(MARKETS) + " |")
    lines.append("|---|---|" + "---|" * len(MARKETS))
    for name, s in res["splits"].items():
        for model, r in s.items():
            if not isinstance(r, dict):
                continue
            cells = []
            for market in MARKETS:
                e = r.get(market)
                if e is None:
                    cells.append("-")
                    continue
                pc = e["print"]["printable"]
                pg = (
                    f"{pc['n']}, {_ci(pc['gap'], 100, '{:+.1f}')}"
                    if pc.get("n")
                    else "0"
                )
                pcc = e.get("print_after_curve", {}).get("printable", {})
                pgc = (
                    f"{pcc['n']}, {_ci(pcc['gap'], 100, '{:+.1f}')}"
                    if pcc.get("n")
                    else "0"
                )
                cells.append(
                    f"{_ci(e['d_logloss'])} ({r['matches']}); pr {pg}; curved pr {pgc}"
                )
            lines.append(f"| {name} | {model} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument(
        "--db",
        default=None,
        help="database to check the pickle's fingerprint against (opened read-only)",
    )
    parser.add_argument(
        "--dispersion",
        default=None,
        help="count dispersion file (default: the config's)",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--md-out", default=None)
    parser.add_argument("--train-from", default=TRAIN_FROM)
    parser.add_argument("--test-from", default=TEST_FROM)
    parser.add_argument("--test-to", default=TEST_TO)
    parser.add_argument("--boot-reps", type=int, default=500)
    args = parser.parse_args(argv)
    res = run(args)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(res, indent=1, default=float), encoding="utf-8"
    )
    note(f"written {args.out}")
    if args.md_out:
        Path(args.md_out).write_text(markdown(res), encoding="utf-8")
        note(f"written {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
