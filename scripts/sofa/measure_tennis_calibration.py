#!/usr/bin/env python3
"""Track A4 - tennis engine, calibration method and uncertainty intervals.

Read-only evidence (a ``measure_*`` script): nothing here writes a config, a
curve or a database. Three questions, each out of sample on a time split with
match-bootstrap confidence intervals:

  (a) ``tennis``    - does a surface-specific rating with pooled fallback, a
      serve/return decomposition (hold / break -> Klaassen-Magnus point ->
      game -> set -> match) or a tier-hierarchical shrinkage beat the rating
      that ships (``bet.sofa.tennis_rating``), at Superbet-style lines of
      games_total / games_won_for / handicap_games / most_games / sets_total?
  (b) ``calib``     - on the replayed history rows (``calibrate_from_cache``;
      never our own settled days) does isotonic regression, beta calibration
      (Kull et al. 2017) or a smoothed monotone spline beat the bucket curve
      ``fit_confidence`` writes (11 fixed buckets, EDGES), out of sample?
  (c) ``interval``  - does a lower bound on p (the sample's standard error
      carried through the normal approximation of the replayed estimator),
      used only to LOWER a confidence, improve the calibration of the printed
      set (confidence >= 0.70) by sample-size class?

Stages (each writes into ``--work-dir``; ``report`` merges them)::

    extract   --sport tennis|football      rows of the replay DB -> npz
    tennis                                  (a)
    calib                                   (b)
    interval                                (c)
    report                                  results JSON

The rows come from a *copy* of the database (``data/refit_<d>/sofa_replay.db``)
opened ``mode=ro``; the live ``data/sofa.db`` is not touched.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

FloatArr = npt.NDArray[np.float64]
IntArr = npt.NDArray[np.int64]

# fit_confidence.EDGES, copied (a script that imports fit_confidence would
# import the whole pipeline); test_measure_tennis_calibration pins the copy.
EDGES: tuple[float, ...] = (
    0.0,
    0.60,
    0.70,
    0.75,
    0.80,
    0.825,
    0.85,
    0.875,
    0.90,
    0.925,
    0.95,
    1.01,
)
MIN_MARKET_BUCKET = 400
MIN_THIN_BUCKET = 100
PRINT_FLOOR = 0.70
P_MIN_EXTRACT = 0.60
EPS = 1e-6

DEFAULT_DB = "data/refit_2026-10-08/sofa_replay.db"
SPLIT_DEFAULT = 1775001600  # 2026-04-01T00:00:00Z
DEFAULT_WORK = (
    "/private/tmp/claude-501/-Users-mkoziol-projects-bet/"
    "8b9b285e-d060-410f-b561-ac2f6537b588/scratchpad/a4"
)


def log(work: Path, msg: str) -> None:
    line = f"{msg}"
    print(line, flush=True)
    with (work / "STATUS.txt").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------


def _bc(
    x: npt.NDArray[Any], weights: FloatArr | None = None, minlength: int = 0
) -> FloatArr:
    """np.bincount with a float64 result (the stubs type it as integer)."""
    return np.asarray(
        np.bincount(x, weights=weights, minlength=minlength), dtype=np.float64
    )


def log_loss_terms(p: FloatArr, y: FloatArr) -> FloatArr:
    q = np.clip(p, EPS, 1.0 - EPS)
    return -(y * np.log(q) + (1.0 - y) * np.log(1.0 - q))


def brier_terms(p: FloatArr, y: FloatArr) -> FloatArr:
    return (p - y) ** 2


def ece(p: FloatArr, y: FloatArr, edges: Sequence[float] = EDGES) -> float:
    """Expected calibration error over the fit's own buckets (weighted |gap|)."""
    if p.size == 0:
        return float("nan")
    idx = np.clip(
        np.searchsorted(np.asarray(edges), p, side="right") - 1, 0, len(edges) - 2
    )
    total = 0.0
    for b in range(len(edges) - 1):
        m = idx == b
        if m.any():
            total += m.sum() * abs(float(p[m].mean()) - float(y[m].mean()))
    return total / p.size


def wilson_lo(k: float, n: float, z: float = 1.959964) -> float:
    if n <= 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(max(p * (1 - p) / n + z * z / (4 * n * n), 0.0)) / d
    return max(0.0, c - m)


def cluster_bootstrap_mean(
    num: FloatArr,
    den: FloatArr,
    reps: int = 1000,
    seed: int = 7,
    chunk: int = 50,
) -> tuple[float, float, float]:
    """Mean of sum(num)/sum(den) over resampled clusters (Poisson bootstrap).

    ``num[i]`` / ``den[i]`` are one cluster's (match's) summed value and row
    count; the point estimate is sum(num)/sum(den), the interval is the
    2.5 / 97.5 percentile of the resampled ratios.
    """
    rng = np.random.default_rng(seed)
    point = float(num.sum() / den.sum()) if den.sum() > 0 else float("nan")
    out: list[float] = []
    n = num.size
    done = 0
    while done < reps:
        k = min(chunk, reps - done)
        w = rng.poisson(1.0, size=(k, n)).astype(np.float64)
        d = w @ den
        out.extend((w @ num / np.where(d > 0, d, np.nan)).tolist())
        done += k
    lo, hi = np.nanpercentile(np.asarray(out), [2.5, 97.5])
    return point, float(lo), float(hi)


def group_sums(keys: IntArr, values: FloatArr) -> tuple[IntArr, FloatArr, FloatArr]:
    """(unique keys, sum of values, count) - the per-match collapse."""
    uniq, inv = np.unique(keys, return_inverse=True)
    s = _bc(inv, weights=values, minlength=uniq.size)
    c = _bc(inv, minlength=uniq.size).astype(np.float64)
    return uniq, s, c


# --------------------------------------------------------------------------
# calibrators (fit on train p, y; predict on any p)
# --------------------------------------------------------------------------


def bucket_index(p: FloatArr) -> IntArr:
    return np.clip(
        np.searchsorted(np.asarray(EDGES), p, side="right") - 1, 0, len(EDGES) - 2
    ).astype(np.int64)


class BucketCurve:
    """The shipped method: realised rate per fixed bucket (fit_confidence.curve).

    ``lower`` selects what a leg is told: the bucket's realised rate (the
    estimate) or its Wilson 95% lower bound (what ``Calibration.realised``
    returns - the number CONFIDENCE actually prints).
    A bucket under ``min_rows`` is absent (nan): the pool serves it.
    """

    def __init__(self, min_rows: int = MIN_MARKET_BUCKET) -> None:
        self.min_rows = min_rows
        nb = len(EDGES) - 1
        self.n = np.zeros(nb)
        self.k = np.zeros(nb)

    def fit(self, p: FloatArr, y: FloatArr) -> BucketCurve:
        b = bucket_index(p)
        self.n = _bc(b, minlength=len(EDGES) - 1).astype(np.float64)
        self.k = _bc(b, weights=y, minlength=len(EDGES) - 1)
        return self

    def predict(self, p: FloatArr, lower: bool = False) -> FloatArr:
        b = bucket_index(p)
        with np.errstate(invalid="ignore", divide="ignore"):
            rate = np.where(self.n >= self.min_rows, self.k / self.n, np.nan)
        if lower:
            lo = np.array(
                [
                    wilson_lo(float(self.k[i]), float(self.n[i]))
                    if self.n[i] >= self.min_rows
                    else np.nan
                    for i in range(self.n.size)
                ]
            )
            return lo[b]
        return rate[b]


def pav(x_sorted_y: FloatArr, w: FloatArr) -> FloatArr:
    """Pool-adjacent-violators (non-decreasing) on values already ordered by x."""
    vals: list[float] = []
    wts: list[float] = []
    cnt: list[int] = []
    for v, ww in zip(x_sorted_y.tolist(), w.tolist(), strict=True):
        vals.append(v)
        wts.append(ww)
        cnt.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            tw = wts[-2] + wts[-1]
            vals[-2] = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / tw
            wts[-2] = tw
            cnt[-2] += cnt[-1]
            vals.pop()
            wts.pop()
            cnt.pop()
    return np.repeat(np.asarray(vals), np.asarray(cnt))


class Isotonic:
    """Isotonic regression on the fine p grid (weights = rows per grid cell).

    The training rows are first collapsed onto ``grid`` equal-count cells so
    the pool-adjacent-violators pass is O(grid), not O(rows); prediction is
    a step function through the cell midpoints (linear between them).
    """

    def __init__(self, grid: int = 400) -> None:
        self.grid = grid
        self.xs: FloatArr = np.zeros(0)
        self.ys: FloatArr = np.zeros(0)

    def fit(self, p: FloatArr, y: FloatArr) -> Isotonic:
        order = np.argsort(p, kind="stable")
        ps, ys = p[order], y[order]
        cells = np.array_split(np.arange(ps.size), min(self.grid, max(ps.size // 5, 1)))
        xm = np.array([ps[c].mean() for c in cells if c.size])
        ym = np.array([ys[c].mean() for c in cells if c.size])
        wm = np.array([c.size for c in cells if c.size], dtype=np.float64)
        self.xs = xm
        self.ys = pav(ym, wm)
        return self

    def predict(self, p: FloatArr) -> FloatArr:
        return np.interp(p, self.xs, self.ys)


def _logit(p: FloatArr) -> FloatArr:
    q = np.clip(p, 1e-4, 1.0 - 1e-4)
    return np.log(q / (1.0 - q))


def _sigmoid(z: FloatArr) -> FloatArr:
    return 1.0 / (1.0 + np.exp(-z))


def _newton_logistic(
    x: FloatArr,
    y: FloatArr,
    w: FloatArr | None = None,
    iters: int = 40,
    ridge: float = 1e-6,
) -> FloatArr:
    """Logistic regression with intercept; x is (n, d). Newton-Raphson."""
    n, d = x.shape
    xa = np.hstack([np.ones((n, 1)), x])
    wt = np.ones(n) if w is None else w
    beta = np.zeros(d + 1)
    for _ in range(iters):
        z = xa @ beta
        pr = _sigmoid(z)
        g = xa.T @ (wt * (y - pr)) - ridge * beta
        h = (xa * (wt * pr * (1 - pr))[:, None]).T @ xa + ridge * np.eye(d + 1)
        step = np.linalg.solve(h, g)
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return beta


class BetaCalibration:
    """Kull, Silva Filho, Flach (2017), the three-parameter family:

        logit(q) = c + a * ln(p) - b * ln(1 - p)

    fitted by logistic regression on (ln p, -ln(1-p)); ``a, b`` are not
    constrained (the paper's monotone case is a, b >= 0; a violated sign is
    reported, not forced).
    """

    def __init__(self) -> None:
        self.beta = np.zeros(3)

    def fit(self, p: FloatArr, y: FloatArr) -> BetaCalibration:
        q = np.clip(p, 1e-4, 1.0 - 1e-4)
        x = np.column_stack([np.log(q), -np.log(1.0 - q)])
        self.beta = _newton_logistic(x, y)
        return self

    def predict(self, p: FloatArr) -> FloatArr:
        q = np.clip(p, 1e-4, 1.0 - 1e-4)
        x = np.column_stack([np.ones(q.size), np.log(q), -np.log(1.0 - q)])
        return _sigmoid(x @ self.beta)


class MonotoneSpline:
    """Smoothed monotone calibration: isotonic knots, then a monotone cubic
    (Fritsch-Carlson / PCHIP) through the knot means, evaluated in logit(p).

    PAV removes the noise-driven dips, the PCHIP interpolant removes the
    isotonic staircase; both keep monotonicity, so the result is a smooth
    non-decreasing map p -> q.
    """

    def __init__(self, knots: int = 24) -> None:
        self.knots = knots
        self.xs: FloatArr = np.zeros(0)
        self.ys: FloatArr = np.zeros(0)
        self.d: FloatArr = np.zeros(0)

    def fit(self, p: FloatArr, y: FloatArr) -> MonotoneSpline:
        order = np.argsort(p, kind="stable")
        ps, ys = p[order], y[order]
        cells = np.array_split(
            np.arange(ps.size), min(self.knots, max(ps.size // 20, 2))
        )
        xm = _logit(np.array([ps[c].mean() for c in cells if c.size]))
        ym = np.array([ys[c].mean() for c in cells if c.size])
        wm = np.array([c.size for c in cells if c.size], dtype=np.float64)
        ym = pav(ym, wm)
        # strictly increasing x (ties collapse)
        keep = np.concatenate([[True], np.diff(xm) > 1e-9])
        self.xs, self.ys = xm[keep], ym[keep]
        self.d = _pchip_slopes(self.xs, self.ys)
        return self

    def predict(self, p: FloatArr) -> FloatArr:
        x = _logit(p)
        xs, ys, d = self.xs, self.ys, self.d
        if xs.size < 2:
            return np.full(p.shape, float(ys[0]) if ys.size else 0.5)
        i = np.clip(np.searchsorted(xs, x, side="right") - 1, 0, xs.size - 2)
        h = xs[i + 1] - xs[i]
        t = np.clip((x - xs[i]) / h, 0.0, 1.0)
        h00 = (1 + 2 * t) * (1 - t) ** 2
        h10 = t * (1 - t) ** 2
        h01 = t * t * (3 - 2 * t)
        h11 = t * t * (t - 1)
        out = h00 * ys[i] + h10 * h * d[i] + h01 * ys[i + 1] + h11 * h * d[i + 1]
        # beyond the knots: flat (a calibrator does not extrapolate a claim)
        out = np.where(x < xs[0], ys[0], out)
        out = np.where(x > xs[-1], ys[-1], out)
        return np.clip(out, 0.0, 1.0)


def _pchip_slopes(x: FloatArr, y: FloatArr) -> FloatArr:
    n = x.size
    if n < 2:
        return np.zeros(n)
    h = np.diff(x)
    delta = np.diff(y) / h
    d = np.zeros(n)
    if n == 2:
        d[:] = delta[0]
        return d
    for k in range(1, n - 1):
        if delta[k - 1] * delta[k] > 0:
            w1 = 2 * h[k] + h[k - 1]
            w2 = h[k] + 2 * h[k - 1]
            d[k] = (w1 + w2) / (w1 / delta[k - 1] + w2 / delta[k])
    d[0] = max(delta[0], 0.0) if delta[0] > 0 else 0.0
    d[-1] = max(delta[-1], 0.0) if delta[-1] > 0 else 0.0
    return d


# --------------------------------------------------------------------------
# interval (c)
# --------------------------------------------------------------------------

K_CENTRE = 10.0  # calibrate_from_cache / engine K_CENTRE: the centre's shrink weight


def _ndtri(p: FloatArr) -> FloatArr:
    """Inverse normal CDF (Acklam's rational approximation, |err| < 1.2e-9)."""
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    p = np.clip(p, 1e-12, 1 - 1e-12)
    out = np.zeros_like(p)
    lo = p < 0.02425
    hi = p > 1 - 0.02425
    mid = ~(lo | hi)
    q = np.sqrt(-2 * np.log(p[lo]))
    out[lo] = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )
    q = np.sqrt(-2 * np.log(1 - p[hi]))
    out[hi] = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
    )
    q = p[mid] - 0.5
    r = q * q
    out[mid] = (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )
    return out


def _ndtr(z: FloatArr) -> FloatArr:
    erf = np.vectorize(math.erf, otypes=[np.float64])
    return np.asarray(0.5 * (1.0 + erf(z / math.sqrt(2.0))), dtype=np.float64)


def p_lower(
    p: FloatArr, n: FloatArr, sd: FloatArr, z: float, k_centre: float = K_CENTRE
) -> FloatArr:
    """p with its centre moved ``z`` standard errors against the bet.

    The replayed estimator prices a rung as Phi((centre - line) / s) (the
    normal read; the NB is a close cousin). Writing zc = Phi^-1(p), a move of
    the centre by one standard error of the shrunk mean,
    se = sd / sqrt(n) * n / (n + K_CENTRE), changes the standardised distance
    by se / s_eff with s_eff the predictive sd. Only sample_sd is stored, so
    s_eff = max(sd, 0.5) is an APPROXIMATION (the live s is inflated for
    count markets); the result is a lower p in both directions (OVER loses
    when the centre falls, UNDER when it rises)::

        p_lo = Phi(zc - z * se / s_eff)
    """
    s_eff = np.maximum(sd, 0.5)
    se = s_eff / np.sqrt(np.maximum(n, 1.0)) * n / (n + k_centre)
    zc = _ndtri(np.clip(p, 1e-9, 1 - 1e-9))
    return _ndtr(zc - z * se / s_eff)


# --------------------------------------------------------------------------
# extraction of replay rows
# --------------------------------------------------------------------------


def extract_rows(db_path: str, sport: str, out: Path, p_min: float, work: Path) -> None:
    from bet.sofa.engine import has_calibratable_model
    from bet.sofa.market_mapper import is_derived

    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.execute(
        "select sofascore_event_id, competition_id, market, line, direction, "
        "sample_size, sample_mean, sample_sd, p_central, actual_value, outcome "
        "from sofa_settled_row where run_date = 'cache-calibration' and sport = ? "
        "and p_central >= ? and sample_mean is not null and sample_sd is not null "
        "and sample_size > 0 and actual_value is not null",
        (sport, p_min),
    )
    markets: dict[str, int] = {}
    cal_ok: dict[str, bool] = {}
    derived: dict[str, bool] = {}
    cols: dict[str, list[Any]] = {
        k: []
        for k in ("ev", "comp", "mk", "dir", "n", "mean", "sd", "p", "hit", "line")
    }
    total = kept = 0
    while True:
        batch = cur.fetchmany(400_000)
        if not batch:
            break
        ev, comp, mk, dr, nn, mean, sd, pp, hit, line = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        for eid, cid, market, ln, direction, n, m, s, p, actual, outcome in batch:
            total += 1
            if market not in cal_ok:
                derived[market] = bool(is_derived(market))
                cal_ok[market] = derived[market] or bool(has_calibratable_model(market))
            if not cal_ok[market]:
                continue
            if derived[market]:
                if outcome not in ("WIN", "LOSS"):
                    continue
                h = 1 if outcome == "WIN" else 0
            else:
                h = (
                    1
                    if ((actual > ln) if direction == "OVER" else (actual < ln))
                    else 0
                )
            code = markets.setdefault(market, len(markets))
            ev.append(eid)
            comp.append(cid if cid is not None else -1)
            mk.append(code)
            dr.append(1 if direction == "OVER" else 0)
            nn.append(n)
            mean.append(m)
            sd.append(s)
            pp.append(p)
            hit.append(h)
            line.append(ln)
        kept += len(ev)
        cols["ev"].append(np.asarray(ev, dtype=np.int64))
        cols["comp"].append(np.asarray(comp, dtype=np.int32))
        cols["mk"].append(np.asarray(mk, dtype=np.int16))
        cols["dir"].append(np.asarray(dr, dtype=np.int8))
        cols["n"].append(np.asarray(nn, dtype=np.int16))
        cols["mean"].append(np.asarray(mean, dtype=np.float32))
        cols["sd"].append(np.asarray(sd, dtype=np.float32))
        cols["p"].append(np.asarray(pp, dtype=np.float32))
        cols["hit"].append(np.asarray(hit, dtype=np.int8))
        cols["line"].append(np.asarray(line, dtype=np.float32))
        log(work, f"extract {sport}: read {total:,} kept {kept:,}")
    # event start timestamps
    ts_map: dict[int, int] = {}
    for sp in ("tennis",) if sport == "tennis" else ("football",):
        for eid, ts in con.execute(
            "select event_id, start_ts from sofa_listed_event where sport = ?", (sp,)
        ):
            if ts:
                ts_map[int(eid)] = int(ts)
    con.close()
    ev_all = np.concatenate(cols["ev"])
    uniq = np.unique(ev_all)
    ts_u = np.array([ts_map.get(int(e), 0) for e in uniq], dtype=np.int64)
    ts = ts_u[np.searchsorted(uniq, ev_all)]
    arrays: dict[str, Any] = {k: np.concatenate(v) for k, v in cols.items()}
    arrays["ts"] = ts
    arrays["markets"] = np.array(sorted(markets, key=lambda name: markets[name]))
    np.savez(out, **arrays)
    log(
        work,
        f"extract {sport}: saved {out} rows={kept:,} missing_ts="
        f"{float((ts == 0).mean()):.4f}",
    )


# --------------------------------------------------------------------------
# (b) calibration methods and (c) intervals on the replayed rows
# --------------------------------------------------------------------------

MIN_FAMILY_TRAIN = 3000
MIN_FAMILY_TEST = 200
METHODS = ("raw", "bucket", "bucket_lo95", "isotonic", "beta", "spline")


class Rows:
    """The replayed rows of one sport as float64 / int views."""

    def __init__(self, path: Path) -> None:
        d = np.load(path)
        self.markets: list[str] = [str(x) for x in d["markets"]]
        self.ts = d["ts"].astype(np.int64)
        self.ev = d["ev"].astype(np.int64)
        self.key = d["mk"].astype(np.int32) * 2 + d["dir"].astype(np.int32)
        self.p = d["p"].astype(np.float64)
        self.y = d["hit"].astype(np.float64)
        self.n = d["n"].astype(np.float64)
        self.sd = d["sd"].astype(np.float64)

    def key_name(self, k: int) -> str:
        return f"{self.markets[k // 2]}|{'OVER' if k % 2 else 'UNDER'}"

    def is_player(self, k: int) -> bool:
        return self.markets[k // 2].startswith("player_")


def fit_family_models(p: FloatArr, y: FloatArr) -> dict[str, Any]:
    return {
        "bucket": BucketCurve(MIN_MARKET_BUCKET).fit(p, y),
        "isotonic": Isotonic().fit(p, y),
        "beta": BetaCalibration().fit(p, y),
        "spline": MonotoneSpline().fit(p, y),
    }


def predict_methods(
    models: dict[str, Any], pool: dict[str, Any], p: FloatArr
) -> dict[str, FloatArr]:
    """Every method's calibrated p; the bucket methods fall back to the pool's
    bucket (>= 200 rows) and then to the raw p, as Calibration.realised does."""
    out: dict[str, FloatArr] = {"raw": p.copy()}
    for lower, name in ((False, "bucket"), (True, "bucket_lo95")):
        own = models["bucket"].predict(p, lower=lower)
        pooled = pool["bucket200"].predict(p, lower=lower)
        out[name] = np.where(np.isnan(own), np.where(np.isnan(pooled), p, pooled), own)
    for name in ("isotonic", "beta", "spline"):
        out[name] = models[name].predict(p)
    return out


def paired_ci(
    inv: IntArr, n_groups: int, diff: FloatArr, reps: int = 400, seed: int = 11
) -> tuple[float, float, float]:
    num = _bc(inv, weights=diff, minlength=n_groups)
    den = _bc(inv, minlength=n_groups).astype(np.float64)
    keep = den > 0
    return cluster_bootstrap_mean(num[keep], den[keep], reps=reps, seed=seed)


def reliability(
    conf: FloatArr, y: FloatArr, lo: float = 0.70, hi: float = 0.95, step: float = 0.05
) -> list[dict[str, float]]:
    out: list[dict[str, float]] = []
    edges = np.arange(lo, hi + 1e-9, step)
    for a, b in zip(edges[:-1], edges[1:], strict=True):
        m = (conf >= a) & (conf < b)
        if m.sum() == 0:
            continue
        out.append(
            {
                "lo": round(float(a), 3),
                "hi": round(float(b), 3),
                "n": int(m.sum()),
                "claimed": float(conf[m].mean()),
                "realised": float(y[m].mean()),
                "gap": float(y[m].mean() - conf[m].mean()),
            }
        )
    return out


def run_calib(rows_path: Path, sport: str, split_ts: int, work: Path) -> dict[str, Any]:
    r = Rows(rows_path)
    valid = r.ts > 0
    train = valid & (r.ts < split_ts)
    test = valid & (r.ts >= split_ts)
    log(work, f"calib {sport}: train {int(train.sum()):,} test {int(test.sum()):,}")
    players = np.array([r.is_player(k) for k in range(len(r.markets) * 2)])
    pool_mask = train & ~players[r.key]
    pool = {
        "bucket200": BucketCurve(200).fit(r.p[pool_mask], r.y[pool_mask]),
        **{k: v for k, v in fit_family_models(r.p[pool_mask], r.y[pool_mask]).items()},
    }
    keys, cnts = np.unique(r.key[train], return_counts=True)
    fam_train = dict(zip(keys.tolist(), cnts.tolist(), strict=True))
    keys_t, cnts_t = np.unique(r.key[test], return_counts=True)
    fam_test = dict(zip(keys_t.tolist(), cnts_t.tolist(), strict=True))
    eval_keys = [
        k
        for k in fam_test
        if fam_train.get(k, 0) >= MIN_FAMILY_TRAIN and fam_test[k] >= MIN_FAMILY_TEST
    ]
    log(work, f"calib {sport}: families fitted {len(eval_keys)} of {len(fam_test)}")
    # predictions on the test rows of fitted families
    sel_idx = np.flatnonzero(test & np.isin(r.key, eval_keys))
    preds = {m: np.zeros(sel_idx.size) for m in METHODS}
    kk = r.key[sel_idx]
    fam_models: dict[int, dict[str, Any]] = {}
    for k in eval_keys:
        tr = train & (r.key == k)
        fam_models[k] = fit_family_models(r.p[tr], r.y[tr])
        pos = np.flatnonzero(kk == k)
        out = predict_methods(fam_models[k], pool, r.p[sel_idx[pos]])
        for m in METHODS:
            preds[m][pos] = out[m]
    p0, y0, ev0 = r.p[sel_idx], r.y[sel_idx], r.ev[sel_idx]
    uniq_ev, inv = np.unique(ev0, return_inverse=True)
    res: dict[str, Any] = {
        "sport": sport,
        "split_ts": split_ts,
        "train_rows": int(train.sum()),
        "test_rows_fitted_families": int(sel_idx.size),
        "test_rows_all": int(test.sum()),
        "test_events": int(uniq_ev.size),
        "families": len(eval_keys),
        "beta_params_pool": [float(x) for x in pool["beta"].beta],
        "methods": {},
    }
    ll = {m: log_loss_terms(preds[m], y0) for m in METHODS}
    br = {m: brier_terms(preds[m], y0) for m in METHODS}
    regions = {
        "all_p>=0.60": np.ones(sel_idx.size, dtype=bool),
        "raw_p_0.70-0.95": (p0 >= 0.70) & (p0 < 0.95),
    }
    for m in METHODS:
        entry: dict[str, Any] = {}
        for rn, mask in regions.items():
            e: dict[str, Any] = {
                "n": float(mask.sum()),
                "logloss": float(ll[m][mask].mean()),
                "brier": float(br[m][mask].mean()),
                "ece": ece(preds[m][mask], y0[mask]),
            }
            if m not in ("bucket",):
                for base in ("bucket",):
                    d_ll = (ll[m] - ll[base])[mask]
                    d_br = (br[m] - br[base])[mask]
                    _, inv_m = np.unique(ev0[mask], return_inverse=True)
                    ng = int(inv_m.max()) + 1 if inv_m.size else 0
                    pt, lo, hi = paired_ci(inv_m, ng, d_ll)
                    e["d_logloss_vs_bucket"] = pt
                    e["d_logloss_ci"] = [lo, hi]
                    pt, lo, hi = paired_ci(inv_m, ng, d_br)
                    e["d_brier_vs_bucket"] = pt
                    e["d_brier_ci"] = [lo, hi]
            entry[rn] = e
        # printed set under this method's own confidence
        pm = preds[m] >= PRINT_FLOOR
        entry["printed"] = {
            "n": int(pm.sum()),
            "claimed": float(preds[m][pm].mean()) if pm.any() else None,
            "realised": float(y0[pm].mean()) if pm.any() else None,
            "gap": float(y0[pm].mean() - preds[m][pm].mean()) if pm.any() else None,
            "logloss": float(ll[m][pm].mean()) if pm.any() else None,
        }
        if pm.any():
            num = _bc(
                inv, weights=np.where(pm, y0 - preds[m], 0.0), minlength=uniq_ev.size
            )
            den = _bc(inv, weights=pm.astype(np.float64), minlength=uniq_ev.size)
            keep = den > 0
            _, glo, ghi = cluster_bootstrap_mean(num[keep], den[keep], reps=400)
            entry["printed"]["gap_ci"] = [glo, ghi]
        entry["reliability_0.70-0.95"] = reliability(preds[m], y0)
        res["methods"][m] = entry
    # per family (largest first)
    fam_rows: list[dict[str, Any]] = []
    order = sorted(eval_keys, key=lambda k: -fam_test[k])
    for k in order[:40]:
        pos = np.flatnonzero(kk == k)
        _, inv_f = np.unique(ev0[pos], return_inverse=True)
        ng = int(inv_f.max()) + 1
        item: dict[str, Any] = {
            "family": r.key_name(k),
            "train": fam_train[k],
            "test": int(pos.size),
        }
        for m in ("isotonic", "beta", "spline"):
            pt, lo, hi = paired_ci(inv_f, ng, (ll[m] - ll["bucket"])[pos], reps=200)
            item[f"d_logloss_{m}"] = [pt, lo, hi]
        item["logloss_bucket"] = float(ll["bucket"][pos].mean())
        fam_rows.append(item)
    res["per_family"] = fam_rows
    # win / loss counts of the families
    wins = {
        m: sum(1 for f in fam_rows if f[f"d_logloss_{m}"][2] < 0)
        for m in ("isotonic", "beta", "spline")
    }
    loses = {
        m: sum(1 for f in fam_rows if f[f"d_logloss_{m}"][1] > 0)
        for m in ("isotonic", "beta", "spline")
    }
    res["family_better_than_bucket_ci"] = wins
    res["family_worse_than_bucket_ci"] = loses
    # time-split stability: test halves
    mid = int(np.median(r.ts[test]))
    halves: dict[str, Any] = {}
    for nm, hm in (
        ("first_half", r.ts[sel_idx] < mid),
        ("second_half", r.ts[sel_idx] >= mid),
    ):
        halves[nm] = {m: float(ll[m][hm].mean()) for m in METHODS}
    res["halves_logloss"] = halves
    return res


def run_calib_thin(
    rows_path: Path,
    sport: str,
    split_ts: int,
    work: Path,
    fractions: Sequence[float] = (0.005, 0.02),
) -> dict[str, Any]:
    """The data-poor regime: each family is fitted on a hash-sample of its
    train EVENTS (a stand-in for a market the history barely covers), the pool
    on the full train; the bucket method falls to the pool where its own
    bucket holds < 400 rows, as ``Calibration.realised`` does. Scored on the
    family's full test rows."""
    r = Rows(rows_path)
    valid = r.ts > 0
    train = valid & (r.ts < split_ts)
    test = valid & (r.ts >= split_ts)
    players = np.array([r.is_player(k) for k in range(len(r.markets) * 2)])
    pool_mask = train & ~players[r.key]
    pool = {"bucket200": BucketCurve(200).fit(r.p[pool_mask], r.y[pool_mask])}
    keys, cnts = np.unique(r.key[train], return_counts=True)
    fam_train = dict(zip(keys.tolist(), cnts.tolist(), strict=True))
    eval_keys = [
        k
        for k in fam_train
        if fam_train[k] >= MIN_FAMILY_TRAIN and (test & (r.key == k)).sum() >= 200
    ]
    out: dict[str, Any] = {"sport": sport, "families": len(eval_keys), "fractions": {}}
    for frac in fractions:
        thr = int(frac * 1000)
        sums: dict[str, list[FloatArr]] = {
            m: [] for m in ("bucket", "isotonic", "beta", "spline")
        }
        evs: list[IntArr] = []
        used = 0
        sampled_rows: list[int] = []
        for k in eval_keys:
            tr = train & (r.key == k) & ((r.ev % 1000) < thr)
            if tr.sum() < 300 or r.y[tr].sum() < 20 or (1 - r.y[tr]).sum() < 20:
                continue
            used += 1
            sampled_rows.append(int(tr.sum()))
            models = fit_family_models(r.p[tr], r.y[tr])
            te = np.flatnonzero(test & (r.key == k))
            pr = predict_methods(models, pool, r.p[te])
            evs.append(r.ev[te])
            for m in sums:
                sums[m].append(log_loss_terms(pr[m], r.y[te]))
        ev_all = np.concatenate(evs)
        inv = np.unique(ev_all, return_inverse=True)[1]
        n_g = int(inv.max()) + 1
        ll = {m: np.concatenate(v) for m, v in sums.items()}
        entry: dict[str, Any] = {
            "families_fitted": used,
            "median_sampled_train_rows": float(np.median(sampled_rows)),
            "test_rows": int(ev_all.size),
            "logloss": {m: float(v.mean()) for m, v in ll.items()},
        }
        for m in ("isotonic", "beta", "spline"):
            entry[f"d_logloss_{m}_vs_bucket"] = list(
                paired_ci(inv, n_g, ll[m] - ll["bucket"], reps=300)
            )
        out["fractions"][str(frac)] = entry
        log(work, f"calibthin {sport} frac {frac}: {entry['logloss']}")
    return out


def classify_n(n: FloatArr) -> IntArr:
    """Sample-size class: 0 <= 7, 1 = 8-9, 2 = 10, 3 = 11-19, 4 = 20+."""
    return np.select([n <= 7, n <= 9, n == 10, n < 20], [0, 1, 2, 3], 4).astype(
        np.int64
    )


N_CLASS_NAMES = ["n<=7", "n8-9", "n10", "n11-19", "n>=20"]


def current_confidence(
    p: FloatArr,
    key_arr: IntArr,
    fam: dict[int, BucketCurve],
    pool: BucketCurve,
    thin: dict[int, BucketCurve],
) -> FloatArr:
    """The shipped lookup for a leg, reduced to its three mechanisms:

    1. the family's own bucket at >= MIN_MARKET_BUCKET rows -> its lo95;
    2. else the pool's lo95, capped (K13) by the family's thin bucket
       (MIN_THIN_BUCKET..MIN_MARKET_BUCKET rows) lo95 if lower;
    3. else (no own bucket at all, K13b) the pool's lo95, capped by the
       family's nearest own bucket below (lo95).
    Both directions pooled (the market curve) is not modelled separately.
    """
    out = pool.predict(p, lower=True)
    out = np.where(np.isnan(out), p, out)
    b = bucket_index(p)
    for k in np.unique(key_arr):
        m = key_arr == k
        cur = fam.get(int(k))
        if cur is None:
            continue
        own = cur.predict(p[m], lower=True)
        # thin bucket: rows between MIN_THIN_BUCKET and MIN_MARKET_BUCKET
        n_b = cur.n[b[m]]
        k_b = cur.k[b[m]]
        thin_lo = np.array(
            [
                wilson_lo(float(kk), float(nn)) if nn >= MIN_THIN_BUCKET else np.nan
                for kk, nn in zip(k_b, n_b, strict=True)
            ]
        )
        pooled = out[m]
        capped = np.where(~np.isnan(thin_lo) & (thin_lo < pooled), thin_lo, pooled)
        # K13b: nothing at p, a measured bucket below p caps the pool
        lo_arr = np.array(
            [
                wilson_lo(float(cur.k[i]), float(cur.n[i]))
                if cur.n[i] >= MIN_THIN_BUCKET
                else np.nan
                for i in range(cur.n.size)
            ]
        )
        # nearest bucket below = the largest i < b with a bucket
        nearest = np.full(pooled.shape, np.nan)
        for i in range(2, cur.n.size):
            sel = (b[m] > i) & ~np.isnan(lo_arr[i])
            nearest = np.where(sel, lo_arr[i], nearest)
        no_own = np.isnan(thin_lo) & np.isnan(own)
        capped = np.where(
            no_own & ~np.isnan(nearest) & (nearest < capped), nearest, capped
        )
        out[m] = np.where(~np.isnan(own), own, capped)
    return out


def run_interval(
    rows_path: Path,
    sport: str,
    split_ts: int,
    work: Path,
    zs: Sequence[float] = (0.5, 1.0, 1.645),
) -> dict[str, Any]:
    r = Rows(rows_path)
    valid = r.ts > 0
    train = valid & (r.ts < split_ts)
    test = valid & (r.ts >= split_ts)
    players = np.array([r.is_player(k) for k in range(len(r.markets) * 2)])
    pool_mask = train & ~players[r.key]
    pool = BucketCurve(200).fit(r.p[pool_mask], r.y[pool_mask])
    keys, cnts = np.unique(r.key[train], return_counts=True)
    fam: dict[int, BucketCurve] = {}
    fam_size: dict[int, int] = {}
    for k, c in zip(keys.tolist(), cnts.tolist(), strict=True):
        if c >= 1000 and not players[k]:
            tr = train & (r.key == k)
            fam[k] = BucketCurve(MIN_MARKET_BUCKET).fit(r.p[tr], r.y[tr])
            fam_size[k] = c
    sel = np.flatnonzero(test & ~players[r.key] & np.isin(r.key, list(fam)))
    p, y, n, sd, ev, kk = r.p[sel], r.y[sel], r.n[sel], r.sd[sel], r.ev[sel], r.key[sel]
    log(work, f"interval {sport}: test rows {sel.size:,} families {len(fam)}")
    conf_a = current_confidence(p, kk, fam, pool, {})
    confs: dict[str, FloatArr] = {"A_current": conf_a}
    pl: dict[float, FloatArr] = {}
    for z in zs:
        pl[z] = p_lower(p, n, sd, z)
        conf_z = current_confidence(pl[z], kk, fam, pool, {})
        confs[f"B_current+interval_z{z}"] = np.minimum(conf_a, conf_z)
    # the interval alone, no thin caps: family bucket else pool, both lo95
    nocap = pool.predict(p, lower=True)
    nocap = np.where(np.isnan(nocap), p, nocap)
    for k in fam:
        m = kk == k
        own = fam[k].predict(p[m], lower=True)
        nocap[m] = np.where(np.isnan(own), nocap[m], own)
    confs["C_nocaps"] = nocap
    uniq_ev, inv = np.unique(ev, return_inverse=True)
    nc = classify_n(n)
    res: dict[str, Any] = {
        "sport": sport,
        "test_rows": int(sel.size),
        "rows_in_thin_or_pool": float(np.mean(conf_a != nocap)),
        "rules": {},
    }
    for name, conf in confs.items():
        pm = conf >= PRINT_FLOOR
        entry: dict[str, Any] = {
            "printed_n": int(pm.sum()),
            "gap": float((y[pm] - conf[pm]).mean()) if pm.any() else None,
            "brier": float(((conf - y)[pm] ** 2).mean()) if pm.any() else None,
            "by_n_class": {},
        }
        for ci, cn in enumerate(N_CLASS_NAMES):
            mm = pm & (nc == ci)
            if mm.sum() < 50:
                continue
            num = _bc(inv, weights=np.where(mm, y - conf, 0.0), minlength=uniq_ev.size)
            den = _bc(inv, weights=mm.astype(np.float64), minlength=uniq_ev.size)
            keep = den > 0
            pt, lo, hi = cluster_bootstrap_mean(num[keep], den[keep], reps=300)
            entry["by_n_class"][cn] = {
                "n": int(mm.sum()),
                "claimed": float(conf[mm].mean()),
                "realised": float(y[mm].mean()),
                "gap": pt,
                "gap_ci": [lo, hi],
            }
        res["rules"][name] = entry
    # information test: within the printed set of A, does se/s predict the gap?
    z_unit = (
        np.maximum(sd, 0.5) / np.sqrt(np.maximum(n, 1)) * n / (n + K_CENTRE)
    ) / np.maximum(sd, 0.5)
    pm = conf_a >= PRINT_FLOOR
    qs = np.quantile(z_unit[pm], [1 / 3, 2 / 3]) if pm.any() else [0, 0]
    info: list[dict[str, Any]] = []
    for nm, mm in (
        ("low_se", pm & (z_unit <= qs[0])),
        ("mid_se", pm & (z_unit > qs[0]) & (z_unit <= qs[1])),
        ("high_se", pm & (z_unit > qs[1])),
    ):
        num = _bc(inv, weights=np.where(mm, y - conf_a, 0.0), minlength=uniq_ev.size)
        den = _bc(inv, weights=mm.astype(np.float64), minlength=uniq_ev.size)
        keep = den > 0
        pt, lo, hi = cluster_bootstrap_mean(num[keep], den[keep], reps=300)
        info.append(
            {
                "tercile": nm,
                "n": int(mm.sum()),
                "se_over_s": float(z_unit[mm].mean()),
                "gap": pt,
                "gap_ci": [lo, hi],
            }
        )
    res["se_tercile_gap_under_A"] = info
    # removed legs: realised of what B removes from A's printed set
    for name in confs:
        if name.startswith("B_"):
            removed = (conf_a >= PRINT_FLOOR) & (confs[name] < PRINT_FLOOR)
            kept = confs[name] >= PRINT_FLOOR
            res["rules"][name]["removed_vs_A"] = {
                "n": int(removed.sum()),
                "realised_removed": float(y[removed].mean()) if removed.any() else None,
                "claimed_removed_by_A": float(conf_a[removed].mean())
                if removed.any()
                else None,
                "realised_kept": float(y[kept].mean()) if kept.any() else None,
            }
    return res


# --------------------------------------------------------------------------
# (a) tennis engine: history, panel of features, variants, Klaassen-Magnus
# --------------------------------------------------------------------------

LN10_400 = math.log(10.0) / 400.0
TENNIS_CUT_TS = 1775001600  # train: matches before 2026-04-01; test: from it
MIN_RATED_ = 10
W_NEIGHBOURS = 600
GT_LINES = [x + 0.5 for x in range(16, 26)]  # 16.5 .. 25.5
GW_LINES = [x + 0.5 for x in range(6, 14)]  # 6.5 .. 13.5
HC_LINES = [x + 0.5 for x in range(-7, 7)]  # margin > t, t -6.5 .. 6.5
FAMILIES = (
    "games_total",
    "games_won_for",
    "handicap_games",
    "most_games",
    "sets_total",
)
EVENT_FAMILY = (
    ["games_total"] * len(GT_LINES)
    + ["games_won_for"] * (2 * len(GW_LINES))
    + ["handicap_games"] * len(HC_LINES)
    + ["most_games"]
    + ["sets_total"]
)
N_EVENTS = len(EVENT_FAMILY)
TIER_ITF, TIER_CH, TIER_TOUR = 0, 1, 2
TIER_NAMES = ("ITF", "CH", "TOUR")


def surface4(ground: str | None) -> int:
    g = (ground or "").lower()
    if "clay" in g:
        return 2
    if "grass" in g:
        return 3
    if "indoor" in g or "carpet" in g:
        return 1
    return 0


def tier_code(category: str) -> int:
    name = category.strip()
    if name.startswith("ITF") or name.startswith("UTR") or name == "Juniors":
        return TIER_ITF
    if name in ("Challenger", "WTA 125"):
        return TIER_CH
    return TIER_TOUR


def build_history(db_path: str, out: Path, work: Path) -> list[Any]:
    """Every finished singles match with the extra fields the variants need
    (ground type, gender, category) - tennis_rating.load_history's logic."""
    import pickle

    from bet.sofa.listing_index import iter_indexed_events
    from bet.sofa.tennis_rating import parse_event

    if out.exists():
        return list(pickle.loads(out.read_bytes()))
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    seen: dict[int, tuple[Any, ...]] = {}
    fetched: dict[int, str] = {}

    def pack(ev: dict[str, Any]) -> tuple[Any, ...] | None:
        res = parse_event(ev)
        if res is None:
            return None
        return (
            res,
            ev.get("groundType"),
            ev["homeTeam"].get("gender"),
            ev["tournament"]["category"].get("name"),
        )

    for events_json, fetched_at in conn.execute(
        "SELECT events_json, fetched_at FROM sofa_entity_events WHERE kind = 'last' "
        'AND events_json LIKE \'%"slug": "tennis"%\''
    ):
        for ev in json.loads(events_json).get("events", []):
            eid = ev.get("id") if isinstance(ev, dict) else None
            packed = pack(ev)
            if packed is not None:
                seen[packed[0].event_id] = packed
            if isinstance(eid, int):
                fetched[eid] = str(fetched_at)
    for ev in iter_indexed_events(conn, fetched, sport="tennis"):
        packed = pack(ev)
        if packed is not None:
            seen[packed[0].event_id] = packed
        else:
            seen.pop(ev["id"], None)
    conn.close()
    hist = sorted(seen.values(), key=lambda v: (v[0].ts, v[0].event_id))
    out.write_bytes(pickle.dumps(hist))
    log(work, f"history: {len(hist):,} matches")
    return hist


FRAC = None


def _frac(value: object) -> tuple[int, int] | None:
    import re

    global FRAC
    if FRAC is None:
        FRAC = re.compile(r"^\s*(\d+)\s*/\s*(\d+)")
    if value is None:
        return None
    m = FRAC.match(str(value))
    return (int(m.group(1)), int(m.group(2))) if m else None


def parse_serve_points(stats_json: str) -> tuple[int, int, int, int] | None:
    """(home serve won, home served, away serve won, away served) or None.

    Same identities as measure_tennis_serve_model.parse_serve: the serve and
    return counts of the two sides must close on each other, else the payload
    is dropped (a misread payload is not a thin one)."""
    try:
        doc = json.loads(stats_json)
    except (TypeError, ValueError):
        return None
    items: dict[str, tuple[object, object]] = {}
    for period in doc.get("statistics") or []:
        if period.get("period") not in (None, "ALL"):
            continue
        for group in period.get("groups") or []:
            for item in group.get("statisticsItems") or []:
                items[str(item.get("name"))] = (item.get("home"), item.get("away"))
    need = (
        "First serve points",
        "Second serve points",
        "First serve return points",
        "Second serve return points",
    )
    if not all(k in items for k in need):
        return None
    sides = []
    for i in (0, 1):
        f1, f2 = _frac(items[need[0]][i]), _frac(items[need[1]][i])
        r1, r2 = _frac(items[need[2]][i]), _frac(items[need[3]][i])
        if not (f1 and f2 and r1 and r2):
            return None
        sides.append((f1[0] + f2[0], f1[1] + f2[1], r1[0] + r2[0], r1[1] + r2[1]))
    (hw, hn, hrw, hrn), (aw, an, arw, arn) = sides
    if hn <= 0 or an <= 0 or hn != arn or an != hrn or hw + arw != hn or aw + hrw != an:
        return None
    return hw, hn, aw, an


def load_serve_stats(db_path: str, work: Path) -> dict[int, tuple[int, int, int, int]]:
    out: dict[int, tuple[int, int, int, int]] = {}
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    for eid, sj in con.execute(
        "select sofascore_event_id, statistics_json from sofa_event_stats "
        "where statistics_json like '%First serve return points%'"
    ):
        parsed = parse_serve_points(sj)
        if parsed:
            out[int(eid)] = parsed
    con.close()
    log(work, f"serve stats: {len(out):,} events")
    return out


def _k_sched(n: int) -> float:
    return 250.0 / float((n + 5) ** 0.4)


def _sig(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _lg(p: float) -> float:
    p = min(max(p, 1e-3), 1 - 1e-3)
    return math.log(p / (1 - p))


PANEL_FLOAT = (
    (
        "lp",
        "lps",
        "dmin78",
        "drest",
        "dn7",
        "dform",
        "dhigh",
        "dtour",
        "lp_t",
        "lp_thin",
        "dserve",
        "sserve",
        "mu",
        "s_h",
        "r_h",
        "s_a",
        "r_a",
        "m_h",
        "m_a",
        "nmin",
    )
    + tuple(f"d3_{i}" for i in range(3))
    + tuple(f"d4_{i}" for i in range(3))
)
KAPPAS = (0.25, 0.5, 1.0)


def build_panel(
    hist: Sequence[Any],
    stats: dict[int, tuple[int, int, int, int]],
    tier_offsets: dict[int, float],
    m0: float,
    eta_floor: float,
    work: Path,
) -> dict[str, Any]:
    """One pass in time order. Every match is rated and its features recorded
    BEFORE it updates anything; recorded rows are the completed best-of-three
    matches of two players with >= MIN_RATED completed matches (the
    production forecast's own condition)."""
    from bet.sofa.tennis_rating import RatingBook

    book = RatingBook()
    ot: dict[int, float] = {}
    n_t: dict[int, int] = {}
    d3: list[dict[tuple[int, int], float]] = [{} for _ in KAPPAS]
    d4: list[dict[tuple[int, int], float]] = [{} for _ in KAPPAS]
    nd3: dict[tuple[int, int], int] = {}
    nd4: dict[tuple[int, int], int] = {}
    sv: dict[int, float] = {}
    rv: dict[int, float] = {}
    ms: dict[int, int] = {}
    mu_ctx: dict[tuple[int, int], float] = {}
    rows: dict[str, list[float]] = {k: [] for k in PANEL_FLOAT}
    meta: dict[str, list[int]] = {
        k: []
        for k in (
            "ts",
            "ev",
            "tier",
            "gender",
            "s3",
            "s4",
            "won",
            "ns",
            "gh",
            "ga",
            "mtb",
            "bo3",
            "pid_h",
            "pid_a",
        )
    }
    cover: dict[tuple[int, int, int], list[int]] = {}
    first_tier: dict[int, int] = {}
    for idx, (r, ground, gender, category) in enumerate(hist):
        tier = tier_code(str(category or ""))
        g = 1 if gender == "F" else 0
        s3 = {"clay": 2, "grass": 3}.get(r.surface, 0)
        s4 = surface4(ground)
        h, a = r.home_id, r.away_id
        for pid in (h, a):
            if pid not in ot:
                ot[pid] = 1500.0 + tier_offsets.get(tier, 0.0)
                n_t[pid] = 0
        nh, na = book.rated(h), book.rated(a)
        is_row = (
            r.completed and nh >= MIN_RATED_ and na >= MIN_RATED_ and len(r.sets) <= 3
        )
        post = 1 if r.ts >= TENNIS_CUT_TS else 0
        key = (tier, g, post)
        cov = cover.setdefault(key, [0, 0])
        if r.completed and len(r.sets) <= 3:
            cov[0] += 1
            cov[1] += int(is_row)
        mu = mu_ctx.get((g, s3), -0.35)  # logit(0.587)
        if is_row:
            f = book.features(h, a, r.surface, r.ts)
            for k in ("lp", "lps", "dmin78", "drest", "dn7", "dform", "dhigh", "dtour"):
                rows[k].append(f[k])
            rows["lp_t"].append((ot[h] - ot[a]) * LN10_400)
            nmin = min(nh, na)
            rows["lp_thin"].append(f["lp"] / (1.0 + 15.0 / nmin))
            rows["nmin"].append(float(nmin))
            for ki in range(len(KAPPAS)):
                rows[f"d3_{ki}"].append(
                    (d3[ki].get((h, s3), 0.0) - d3[ki].get((a, s3), 0.0)) * LN10_400
                )
                rows[f"d4_{ki}"].append(
                    (d4[ki].get((h, s4), 0.0) - d4[ki].get((a, s4), 0.0)) * LN10_400
                )
            mh, ma = ms.get(h, 0), ms.get(a, 0)
            sh, rh_, sa, ra = (
                sv.get(h, 0.0),
                rv.get(h, 0.0),
                sv.get(a, 0.0),
                rv.get(a, 0.0),
            )
            rows["s_h"].append(sh)
            rows["r_h"].append(rh_)
            rows["s_a"].append(sa)
            rows["r_a"].append(ra)
            rows["m_h"].append(float(mh))
            rows["m_a"].append(float(ma))
            rows["mu"].append(mu)
            rows["dserve"].append((sh - ra) - (sa - rh_))
            rows["sserve"].append((sh - ra) + (sa - rh_))
            hs = sum(1 for x, y in r.sets if x > y)
            meta["ts"].append(r.ts)
            meta["ev"].append(r.event_id)
            meta["tier"].append(tier)
            meta["gender"].append(g)
            meta["s3"].append(s3)
            meta["s4"].append(s4)
            meta["won"].append(1 if r.home_won else 0)
            meta["ns"].append(len(r.sets))
            meta["gh"].append(sum(x for x, _ in r.sets))
            meta["ga"].append(sum(y for _, y in r.sets))
            meta["mtb"].append(
                1 if (len(r.sets) == 3 and sorted(r.sets[2]) == [0, 1]) else 0
            )
            meta["bo3"].append(1 if max(hs, len(r.sets) - hs) == 2 else 0)
            meta["pid_h"].append(h)
            meta["pid_a"].append(a)
        # ---- updates (after the row is recorded) ----
        for pid in (h, a):
            first_tier.setdefault(pid, tier)
        if r.completed:
            o_h, o_a = book.overall[h], book.overall[a]
            y = 1.0 if r.home_won else 0.0
            # tier-initialised overall
            p_t = _sig((ot[h] - ot[a]) * LN10_400)
            ot[h] += _k_sched(n_t[h]) * (y - p_t)
            ot[a] -= _k_sched(n_t[a]) * (y - p_t)
            n_t[h] += 1
            n_t[a] += 1
            # hierarchical surface deviations (shrunk to the pooled rating)
            for ki, kappa in enumerate(KAPPAS):
                for dd, nd, sf in ((d3[ki], nd3, s3), (d4[ki], nd4, s4)):
                    dh, da = dd.get((h, sf), 0.0), dd.get((a, sf), 0.0)
                    pf = _sig((o_h + dh - o_a - da) * LN10_400)
                    kh = kappa * _k_sched(nd.get((h, sf), 0))
                    ka = kappa * _k_sched(nd.get((a, sf), 0))
                    dd[(h, sf)] = dh + kh * (y - pf)
                    dd[(a, sf)] = da - ka * (y - pf)
                    if ki == 0:
                        nd[(h, sf)] = nd.get((h, sf), 0) + 1
                        nd[(a, sf)] = nd.get((a, sf), 0) + 1
        st = stats.get(r.event_id)
        if st is not None and r.completed:
            hw, hn, aw, an = st
            for srv, ret, won, n_pts in ((h, a, hw, hn), (a, h, aw, an)):
                pi = _sig(mu + sv.get(srv, 0.0) - rv.get(ret, 0.0))
                obs = won / n_pts
                delta = max(-2.0, min(2.0, (obs - pi) / max(pi * (1 - pi), 0.05)))
                sv[srv] = (
                    sv.get(srv, 0.0)
                    + max(eta_floor, 1.0 / (ms.get(srv, 0) + m0)) * delta
                )
                rv[ret] = (
                    rv.get(ret, 0.0)
                    - max(eta_floor, 1.0 / (ms.get(ret, 0) + m0)) * delta
                )
            ms[h] = ms.get(h, 0) + 1
            ms[a] = ms.get(a, 0) + 1
            tot = (hw + aw) / (hn + an)
            mu_ctx[(g, s3)] = mu + 0.002 * (_lg(tot) - mu)
        book.update(r)
        if idx % 50000 == 0:
            log(work, f"panel: {idx:,}/{len(hist):,}")
    panel: dict[str, Any] = {
        k: np.asarray(v, dtype=np.float64) for k, v in rows.items()
    }
    panel.update({k: np.asarray(v, dtype=np.int64) for k, v in meta.items()})
    panel["cover"] = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in cover.items()}
    return panel


def tier_init_offsets(hist: Sequence[Any]) -> dict[int, float]:
    """Mean production Elo (after >= 30 completed matches) of the players who
    entered the data at each tier, minus the pool mean - fitted on matches
    BEFORE the cut only. The tier-initialised book starts a newcomer there."""
    from bet.sofa.tennis_rating import RatingBook

    book = RatingBook()
    first: dict[int, int] = {}
    for r, _g, _gender, category in hist:
        if r.ts >= TENNIS_CUT_TS:
            break
        tc = tier_code(str(category or ""))
        first.setdefault(r.home_id, tc)
        first.setdefault(r.away_id, tc)
        book.update(r)
    by: dict[int, list[float]] = {0: [], 1: [], 2: []}
    for pid, tc in first.items():
        if book.n[pid] >= 30:
            by[tc].append(book.overall[pid])
    allv = [x for v in by.values() for x in v]
    mean_all = sum(allv) / len(allv)
    return {tc: (sum(v) / len(v) - mean_all) if v else 0.0 for tc, v in by.items()}


def fit_logit(x: FloatArr, y: FloatArr) -> FloatArr:
    return _newton_logistic(x, y, iters=30, ridge=1e-6)


def predict_logit(beta: FloatArr, x: FloatArr) -> FloatArr:
    return _sigmoid(beta[0] + x @ beta[1:])


CONTEXT = ("dmin78", "drest", "dn7", "dform", "dhigh", "dtour")
VARIANTS: dict[str, tuple[str, ...]] = {
    "V0_production": ("lp", "lps") + CONTEXT,
    "V1_no_surface": ("lp",) + CONTEXT,
    "V2_surface3_hier_k0.25": ("lp", "d3_0") + CONTEXT,
    "V2_surface3_hier_k0.5": ("lp", "d3_1") + CONTEXT,
    "V2_surface3_hier_k1.0": ("lp", "d3_2") + CONTEXT,
    "V3_surface4_hier_k0.25": ("lp", "d4_0") + CONTEXT,
    "V3_surface4_hier_k0.5": ("lp", "d4_1") + CONTEXT,
    "V3_surface4_hier_k1.0": ("lp", "d4_2") + CONTEXT,
    "V4_prod_plus_surface4": ("lp", "lps", "d4_1") + CONTEXT,
    "V5_tier_init": ("lp_t", "lps") + CONTEXT,
    "V6_thin_shrink": ("lp", "lp_thin", "lps") + CONTEXT,
    "V7_serve_in_winprob": ("lp", "lps", "dserve") + CONTEXT,
}
GENDER_VARIANT = "V8_tier_x_gender"


def fit_variants(panel: dict[str, Any]) -> dict[str, FloatArr]:
    """p_home of every row under every variant: one logistic per tier (per
    tier x gender for V8), fitted on the rows BEFORE the cut."""
    ts = panel["ts"]
    train = ts < TENNIS_CUT_TS
    out: dict[str, FloatArr] = {}
    names_all = dict(VARIANTS)
    names_all[GENDER_VARIANT] = VARIANTS["V0_production"]
    for vname, cols in names_all.items():
        x = np.column_stack([panel[c] for c in cols])
        p = np.zeros(ts.size)
        groups = (
            [(t, None) for t in (0, 1, 2)]
            if vname != GENDER_VARIANT
            else [(t, g) for t in (0, 1, 2) for g in (0, 1)]
        )
        for tier, g in groups:
            m = panel["tier"] == tier
            if g is not None:
                m = m & (panel["gender"] == g)
            tr = m & train & (panel["ns"] <= 3)
            if tr.sum() < 200:
                continue
            beta = fit_logit(x[tr], panel["won"][tr].astype(np.float64))
            p[m] = predict_logit(beta, x[m])
        out[vname] = p
    return out


def window_lo(keys: FloatArr, p: FloatArr, w: int) -> IntArr:
    """Start of the ``w`` nearest table entries to each p in a sorted table -
    the production ``_neighbours`` greedy expansion, vectorised."""
    t = keys.size
    i = np.searchsorted(keys, p)
    lo = np.clip(i - w, 0, max(t - w, 0))
    hi = np.clip(i, 0, max(t - w, 0))
    for _ in range(int(math.ceil(math.log2(w + 2))) + 1):
        mid = (lo + hi) // 2
        right = keys[np.minimum(mid + w - 1, t - 1)] - p
        left = p - keys[mid]
        cond = right >= left  # window already reaches as far right as left
        hi = np.where(cond, mid, hi)
        lo = np.where(cond, lo, np.minimum(mid + 1, hi))
    cand = np.stack([np.clip(lo - 1, 0, t - w), np.clip(lo, 0, t - w)])
    cost = np.maximum(p[None, :] - keys[cand], keys[cand + w - 1] - p[None, :])
    return np.asarray(np.where(cost[0] <= cost[1], cand[0], cand[1]), dtype=np.int64)


class NeighbourTable:
    """The production neighbour table, in arrays: one row per match per
    perspective, sorted by the calibrated p."""

    def __init__(self, p: FloatArr, gf: IntArr, ga: IntArr, ns: IntArr) -> None:
        order = np.argsort(p, kind="stable")
        self.p, self.gf, self.ga, self.ns = p[order], gf[order], ga[order], ns[order]
        margin = self.gf - self.ga
        cols = [self.gf + self.ga > t for t in GT_LINES]
        cols += [self.gf > t for t in GW_LINES]
        cols += [margin > t for t in HC_LINES]
        cols += [margin > 0, self.ns == 3]
        self.ind = np.cumsum(
            np.vstack(
                [np.zeros(self.p.size, dtype=np.int64)]
                + [c.astype(np.int64) for c in cols]
            ),
            axis=1,
        )
        # columns: 0 pad; 1.. = GT(10), GW_home(8), HC(14), MG, SETS - the GW_away
        # events reuse the GW block read from the away window.

    def probs(self, p_home: FloatArr, w: int = W_NEIGHBOURS) -> FloatArr:
        n_gt, n_gw, n_hc = len(GT_LINES), len(GW_LINES), len(HC_LINES)
        lo_h = window_lo(self.p, p_home, w)
        lo_a = window_lo(self.p, 1.0 - p_home, w)
        cs = self.ind  # shape (1 + E, T)... first row zeros; rows are events

        def cnt(ev_row: int, lo: IntArr) -> FloatArr:
            c = cs[ev_row + 1]
            return np.asarray(
                (c[lo + w - 1] - np.where(lo > 0, c[np.maximum(lo - 1, 0)], 0)) / w,
                dtype=np.float64,
            )

        out = np.zeros((p_home.size, N_EVENTS))
        col = 0
        for e in range(n_gt):
            out[:, col] = cnt(e, lo_h)
            col += 1
        for e in range(n_gw):
            out[:, col] = cnt(n_gt + e, lo_h)
            col += 1
        for e in range(n_gw):
            out[:, col] = cnt(n_gt + e, lo_a)
            col += 1
        for e in range(n_hc):
            out[:, col] = cnt(n_gt + n_gw + e, lo_h)
            col += 1
        out[:, col] = cnt(n_gt + n_gw + n_hc, lo_h)
        out[:, col + 1] = cnt(n_gt + n_gw + n_hc + 1, lo_h)
        return out


def truth_matrix(gh: IntArr, ga: IntArr, ns: IntArr) -> FloatArr:
    m = gh - ga
    cols = [(gh + ga > t) for t in GT_LINES]
    cols += [gh > t for t in GW_LINES]
    cols += [ga > t for t in GW_LINES]
    cols += [m > t for t in HC_LINES]
    cols += [m > 0, ns == 3]
    return np.column_stack(cols).astype(np.float64)


# ---- Klaassen-Magnus style point -> game -> set -> match ------------------


def game_win(p: FloatArr) -> FloatArr:
    q = 1.0 - p
    return p**4 * (1 + 4 * q + 10 * q * q) + 20 * p**3 * q**3 * p * p / (p * p + q * q)


def tiebreak_win(p: FloatArr) -> FloatArr:
    q = 1.0 - p
    s = np.zeros_like(p)
    for k in range(6):
        s += math.comb(6 + k, k) * p**7 * q**k
    return s + math.comb(12, 6) * p**6 * q**6 * p * p / (p * p + q * q)


SET_OUTCOMES: list[tuple[int, int]] = (
    [(6, j) for j in range(5)]
    + [(7, 5), (7, 6)]
    + [(j, 6) for j in range(5)]
    + [(5, 7), (6, 7)]
)  # home games, away games; first 7 = home wins the set


def set_distribution(
    hold_h: FloatArr, hold_a: FloatArr, t_h: FloatArr
) -> list[FloatArr]:
    """P of each SET_OUTCOMES entry, the first server of the set averaged
    over both players (the first server of a later set depends on the games
    played, which an independent-sets model ignores)."""
    total = [np.zeros_like(hold_h) for _ in SET_OUTCOMES]
    for first_home in (True, False):
        prob: dict[tuple[int, int], FloatArr] = {(0, 0): np.ones_like(hold_h)}
        for tot in range(0, 14):
            for i in range(0, min(tot, 7) + 1):
                j = tot - i
                if j > 7 or (i, j) not in prob:
                    continue
                pr = prob[(i, j)]
                terminal = (
                    (i == 6 and j <= 4)
                    or (j == 6 and i <= 4)
                    or (i == 7 and j == 5)
                    or (j == 7 and i == 5)
                )
                if terminal:
                    total[SET_OUTCOMES.index((i, j))] = (
                        total[SET_OUTCOMES.index((i, j))] + 0.5 * pr
                    )
                    continue
                if i == 6 and j == 6:
                    total[SET_OUTCOMES.index((7, 6))] += 0.5 * pr * t_h
                    total[SET_OUTCOMES.index((6, 7))] += 0.5 * pr * (1 - t_h)
                    continue
                home_serves = ((i + j) % 2 == 0) == first_home
                w = hold_h if home_serves else 1.0 - hold_a
                prob[(i + 1, j)] = prob.get((i + 1, j), 0.0) + pr * w
                prob[(i, j + 1)] = prob.get((i, j + 1), 0.0) + pr * (1 - w)
    return total


def point_to_set(p_h_serve: FloatArr, p_a_serve: FloatArr) -> list[FloatArr]:
    hold_h = game_win(p_h_serve)
    hold_a = game_win(p_a_serve)
    q_tb = 0.5 * (p_h_serve + (1.0 - p_a_serve))
    return set_distribution(hold_h, hold_a, tiebreak_win(q_tb))


def match_win_from_sets(sd: list[FloatArr]) -> FloatArr:
    w: FloatArr = np.sum(np.stack(sd[:7]), axis=0)
    return np.asarray(w * w * (1.0 + 2.0 * (1.0 - w)), dtype=np.float64)


def km_match_events(sd: list[FloatArr]) -> FloatArr:
    """The 42 events of ``truth_matrix`` from a set distribution, best of
    three, independent identical sets. Returns (N, N_EVENTS)."""
    n = sd[0].size
    pmf = np.zeros((n, 22, 22, 2))
    home = list(range(7))
    away = list(range(7, 14))
    o = SET_OUTCOMES
    for grp in (home, away):
        for a_ in grp:
            for b_ in grp:
                pmf[:, o[a_][0] + o[b_][0], o[a_][1] + o[b_][1], 0] += sd[a_] * sd[b_]
    for g1, g2 in ((home, away), (away, home)):
        for a_ in g1:
            for b_ in g2:
                pr = sd[a_] * sd[b_]
                for c_ in range(14):
                    pmf[
                        :,
                        o[a_][0] + o[b_][0] + o[c_][0],
                        o[a_][1] + o[b_][1] + o[c_][1],
                        1,
                    ] += pr * sd[c_]
    pg = pmf.sum(axis=3)  # (n, gh, ga)
    tot = np.zeros((n, 44))
    mar = np.zeros((n, 44))
    for gh in range(22):
        tot[:, gh : gh + 22] += pg[:, gh, :]
    for ga in range(22):
        mar[:, 21 - ga : 21 - ga + 22] += pg[:, :, ga]
    gh_d = pg.sum(axis=2)
    ga_d = pg.sum(axis=1)
    out = np.zeros((n, N_EVENTS))
    col = 0
    for t in GT_LINES:
        out[:, col] = tot[:, int(t + 0.5) :].sum(axis=1)
        col += 1
    for t in GW_LINES:
        out[:, col] = gh_d[:, int(t + 0.5) :].sum(axis=1)
        col += 1
    for t in GW_LINES:
        out[:, col] = ga_d[:, int(t + 0.5) :].sum(axis=1)
        col += 1
    for t in HC_LINES:
        out[:, col] = mar[:, 21 + int(math.floor(t)) + 1 :].sum(axis=1)
        col += 1
    out[:, col] = mar[:, 22:].sum(axis=1)
    out[:, col + 1] = pmf[:, :, :, 1].sum(axis=(1, 2))
    return out


def km_events(
    s_h: FloatArr,
    r_h: FloatArr,
    s_a: FloatArr,
    r_a: FloatArr,
    mu: FloatArr,
    p_target: FloatArr | None = None,
    chunk: int = 4000,
) -> FloatArr:
    """Klaassen-Magnus events. Pure (``p_target`` None): the serve / return
    ratings alone. Hybrid: the serve-vs-return edge ``d`` is solved per match
    so that P(home wins) equals ``p_target`` (the calibrated Elo)."""
    n = s_h.size
    out = np.zeros((n, N_EVENTS))
    for a in range(0, n, chunk):
        sl = slice(a, min(a + chunk, n))
        base_h = mu[sl] + s_h[sl] - r_a[sl]
        base_a = mu[sl] + s_a[sl] - r_h[sl]
        if p_target is None:
            d = np.zeros(base_h.size)
        else:
            lo = np.full(base_h.size, -2.0)
            hi = np.full(base_h.size, 2.0)
            tgt = np.clip(p_target[sl], 0.02, 0.98)
            for _ in range(16):
                mid = 0.5 * (lo + hi)
                pm = match_win_from_sets(
                    point_to_set(_sigmoid(base_h + mid), _sigmoid(base_a - mid))
                )
                up = pm < tgt
                lo = np.where(up, mid, lo)
                hi = np.where(up, hi, mid)
            d = 0.5 * (lo + hi)
        sd = point_to_set(_sigmoid(base_h + d), _sigmoid(base_a - d))
        out[sl] = km_match_events(sd)
    return out


def event_loss_by_family(
    probs: FloatArr, truth: FloatArr, keep: FloatArr
) -> dict[str, tuple[FloatArr, FloatArr]]:
    """Per-match (sum of log loss, count of kept events) by market family."""
    q = np.clip(probs, 1e-4, 1 - 1e-4)
    ll = -(truth * np.log(q) + (1 - truth) * np.log(1 - q))
    out: dict[str, tuple[FloatArr, FloatArr]] = {}
    fam = np.array(EVENT_FAMILY)
    for f in FAMILIES:
        m = fam == f
        out[f] = ((ll[:, m] * keep[:, m]).sum(axis=1), keep[:, m].sum(axis=1))
    return out


def tune_serve(
    hist: Sequence[Any], stats: dict[int, tuple[int, int, int, int]], work: Path
) -> tuple[float, float, list[dict[str, float]]]:
    """Pick (m0, eta_floor) of the online serve / return ratings on the
    binomial log-likelihood of serve points in the three months BEFORE the
    cut (so never on the test window)."""
    grid = [
        (4.0, 0.02),
        (8.0, 0.03),
        (8.0, 0.06),
        (15.0, 0.03),
        (15.0, 0.06),
        (30.0, 0.05),
    ]
    window_lo_ts = TENNIS_CUT_TS - 90 * 86400
    results: list[dict[str, float]] = []
    for m0, floor in grid:
        sv: dict[int, float] = {}
        rv: dict[int, float] = {}
        ms: dict[int, int] = {}
        mu_ctx: dict[tuple[int, int], float] = {}
        ll = 0.0
        npts = 0
        for r, _g, gender, _c in hist:
            if r.ts >= TENNIS_CUT_TS:
                break
            st = stats.get(r.event_id)
            if st is None or not r.completed:
                continue
            h, a = r.home_id, r.away_id
            g = 1 if gender == "F" else 0
            s3 = {"clay": 2, "grass": 3}.get(r.surface, 0)
            mu = mu_ctx.get((g, s3), -0.35)
            hw, hn, aw, an = st
            for srv, ret, won, n_pts in ((h, a, hw, hn), (a, h, aw, an)):
                pi = _sig(mu + sv.get(srv, 0.0) - rv.get(ret, 0.0))
                if r.ts >= window_lo_ts and ms.get(srv, 0) >= 5 and ms.get(ret, 0) >= 5:
                    pi_c = min(max(pi, 1e-4), 1 - 1e-4)
                    ll += won * math.log(pi_c) + (n_pts - won) * math.log(1 - pi_c)
                    npts += n_pts
                obs = won / n_pts
                delta = max(-2.0, min(2.0, (obs - pi) / max(pi * (1 - pi), 0.05)))
                sv[srv] = (
                    sv.get(srv, 0.0) + max(floor, 1.0 / (ms.get(srv, 0) + m0)) * delta
                )
                rv[ret] = (
                    rv.get(ret, 0.0) - max(floor, 1.0 / (ms.get(ret, 0) + m0)) * delta
                )
            ms[h] = ms.get(h, 0) + 1
            ms[a] = ms.get(a, 0) + 1
            tot = (hw + aw) / (hn + an)
            mu_ctx[(g, s3)] = mu + 0.002 * (_lg(tot) - mu)
        results.append(
            {
                "m0": m0,
                "eta_floor": floor,
                "mean_point_loglik": ll / max(npts, 1),
                "points": float(npts),
            }
        )
        log(work, f"tune_serve m0={m0} floor={floor}: ll/pt {ll / max(npts, 1):.5f}")
    best = max(results, key=lambda x: x["mean_point_loglik"])
    return best["m0"], best["eta_floor"], results


def outcomes_arrays(
    panel: dict[str, Any], p: FloatArr, mask: npt.NDArray[np.bool_]
) -> tuple[FloatArr, IntArr, IntArr, IntArr]:
    ok = mask & (panel["bo3"] == 1) & (panel["ns"] <= 3)
    gh, ga, ns = panel["gh"][ok], panel["ga"][ok], panel["ns"][ok]
    pp = p[ok]
    return (
        np.concatenate([pp, 1.0 - pp]),
        np.concatenate([gh, ga]),
        np.concatenate([ga, gh]),
        np.concatenate([ns, ns]),
    )


def run_tennis(db_path: str, work: Path, reuse_panel: bool = False) -> dict[str, Any]:
    import pickle

    if reuse_panel and (work / "panel.pkl").exists():
        prev = (
            json.loads((work / "tennis.json").read_text())
            if (work / "tennis.json").exists()
            else {}
        )
        keep = {
            k: prev[k]
            for k in ("serve_tuning", "tier_offsets", "serve_m0", "serve_eta_floor")
            if k in prev
        }
        return evaluate_tennis(
            pickle.loads((work / "panel.pkl").read_bytes()), work, keep
        )
    hist = build_history(db_path, work / "hist_raw.pkl", work)
    stats = load_serve_stats(db_path, work)
    m0, floor, tune = tune_serve(hist, stats, work)
    offsets = tier_init_offsets(hist)
    log(work, f"tier init offsets {offsets}; serve m0={m0} floor={floor}")
    panel = build_panel(hist, stats, offsets, m0, floor, work)
    (work / "panel.pkl").write_bytes(pickle.dumps(panel))
    log(work, f"panel rows {panel['ts'].size:,}")
    return evaluate_tennis(
        panel,
        work,
        {
            "serve_tuning": tune,
            "tier_offsets": offsets,
            "serve_m0": m0,
            "serve_eta_floor": floor,
        },
    )


def post_calibration(
    probs: dict[str, FloatArr],
    truth: FloatArr,
    match_ids: IntArr,
    ts_test: FloatArr,
    names: Sequence[str],
    min_rows: int = 200,
) -> dict[str, Any]:
    """Does a variant's gain survive the shipped calibration method?

    Per variant, per (market family, direction) a bucket curve (the fit's own
    buckets) is fitted on the legs (p >= 0.60) of the first half of the test
    window and scores the second half, on the legs the production estimator
    (V0) makes there. The legs of one match are one cluster.
    """
    fam_arr = np.array(EVENT_FAMILY)
    mid = float(np.median(ts_test))
    h1 = ts_test < mid
    h2 = ~h1
    out: dict[str, Any] = {"split_ts": mid}
    base = probs["V0_production"]
    inv = np.unique(match_ids, return_inverse=True)[1]
    n_m = int(inv.max()) + 1
    losses: dict[str, dict[str, tuple[FloatArr, FloatArr]]] = {}
    for vname in names:
        pv_ = probs[vname]
        losses[vname] = {}
        gaps: dict[str, Any] = {}
        for fam in FAMILIES:
            cols = np.flatnonzero(fam_arr == fam)
            num = np.zeros(n_m)
            den = np.zeros(n_m)
            claimed = 0.0
            hit = 0.0
            cnt = 0
            for direction in (1, 0):
                p_leg = pv_[:, cols] if direction else 1.0 - pv_[:, cols]
                y_leg = truth[:, cols] if direction else 1.0 - truth[:, cols]
                b_leg = base[:, cols] if direction else 1.0 - base[:, cols]
                fit_m = (p_leg >= P_MIN_EXTRACT) & h1[:, None]
                curve = BucketCurve(min_rows).fit(p_leg[fit_m], y_leg[fit_m])
                ev_m = (b_leg >= P_MIN_EXTRACT) & h2[:, None]
                conf = curve.predict(p_leg)
                conf = np.where(np.isnan(conf), p_leg, conf)
                ll = log_loss_terms(conf, y_leg)
                num += (ll * ev_m).sum(axis=1)
                den += ev_m.sum(axis=1)
                printed = ev_m & (conf >= PRINT_FLOOR)
                claimed += float((conf * printed).sum())
                hit += float((y_leg * printed).sum())
                cnt += int(printed.sum())
            losses[vname][fam] = (num, den)
            gaps[fam] = {
                "legs": int(den.sum()),
                "printed_legs": cnt,
                "claimed": claimed / cnt if cnt else None,
                "realised": hit / cnt if cnt else None,
                "gap": (hit - claimed) / cnt if cnt else None,
                "logloss": float(num.sum() / max(den.sum(), 1.0)),
            }
        out[vname] = gaps
    for vname in names:
        if vname == "V0_production":
            continue
        for fam in FAMILIES:
            d_num = losses[vname][fam][0] - losses["V0_production"][fam][0]
            den = losses["V0_production"][fam][1]
            ok = den > 0
            pt, lo, hi = cluster_bootstrap_mean(d_num[ok], den[ok], reps=300)
            out[vname][fam]["d_logloss_vs_V0"] = [pt, lo, hi]
    return out


def evaluate_tennis(
    panel: dict[str, Any], work: Path, extra: dict[str, Any]
) -> dict[str, Any]:
    ts = panel["ts"]
    train = ts < TENNIS_CUT_TS
    test = (ts >= TENNIS_CUT_TS) & (panel["bo3"] == 1) & (panel["ns"] <= 3)
    won = panel["won"].astype(np.float64)
    pv = fit_variants(panel)
    res: dict[str, Any] = {
        "cut_ts": TENNIS_CUT_TS,
        "train_rows": int(train.sum()),
        "test_rows": int(test.sum()),
        **extra,
    }
    # ---- coverage and thinness ----
    cover = {}
    for key, (tot, rated) in panel["cover"].items():
        t, g, post = (int(x) for x in key.split("|"))
        if post == 1:
            cover[f"{TIER_NAMES[t]}|{'W' if g else 'M'}"] = {
                "matches": tot,
                "rated_both": rated,
                "share": rated / tot if tot else None,
            }
    res["coverage_test_window"] = cover
    thin: dict[str, Any] = {}
    for t in (0, 1, 2):
        for g in (0, 1):
            m = test & (panel["tier"] == t) & (panel["gender"] == g)
            if m.sum() < 50:
                continue
            nm = panel["nmin"][m]
            classes = {
                "10-19": (nm >= 10) & (nm < 20),
                "20-39": (nm >= 20) & (nm < 40),
                "40+": nm >= 40,
            }
            entry: dict[str, Any] = {
                "rows": int(m.sum()),
                "median_min_n": float(np.median(nm)),
                "share_min_n_lt20": float((nm < 20).mean()),
            }
            p0 = pv["V0_production"][m]
            y = won[m]
            entry["logloss_V0"] = float(log_loss_terms(p0, y).mean())
            entry["by_min_n"] = {
                cn: {
                    "rows": int(cm.sum()),
                    "logloss_V0": float(log_loss_terms(p0[cm], y[cm]).mean())
                    if cm.any()
                    else None,
                }
                for cn, cm in classes.items()
            }
            thin[f"{TIER_NAMES[t]}|{'W' if g else 'M'}"] = entry
    res["thin"] = thin
    # ---- win probability by variant ----
    base = pv["V0_production"]
    wp: dict[str, Any] = {}
    for vname, p in pv.items():
        e: dict[str, Any] = {
            "logloss": float(log_loss_terms(p[test], won[test]).mean()),
            "brier": float(brier_terms(p[test], won[test]).mean()),
        }
        if vname != "V0_production":
            d = (log_loss_terms(p, won) - log_loss_terms(base, won))[test]
            _, inv = np.unique(panel["ev"][test], return_inverse=True)
            e["d_logloss_vs_V0"] = list(paired_ci(inv, int(inv.max()) + 1, d))
            for t in (0, 1, 2):
                mt = test & (panel["tier"] == t)
                dd = (log_loss_terms(p, won) - log_loss_terms(base, won))[mt]
                _, inv_t = np.unique(panel["ev"][mt], return_inverse=True)
                e[f"d_logloss_vs_V0_{TIER_NAMES[t]}"] = list(
                    paired_ci(inv_t, int(inv_t.max()) + 1, dd, reps=300)
                )
        wp[vname] = e
    res["win_probability"] = wp
    log(work, "tennis: win-probability table done")
    # ---- market events through the neighbour table ----
    tr_mask = train
    idx_test = np.flatnonzero(test)
    truth = truth_matrix(
        panel["gh"][idx_test], panel["ga"][idx_test], panel["ns"][idx_test]
    )
    mtb_tr = panel["mtb"] == 1
    probs: dict[str, FloatArr] = {}
    for vname, p in pv.items():
        probs[vname] = np.zeros((idx_test.size, N_EVENTS))
        full = NeighbourTable(*outcomes_arrays(panel, p, tr_mask))
        nomtb = NeighbourTable(*outcomes_arrays(panel, p, tr_mask & ~mtb_tr))
        itf = panel["tier"][idx_test] == TIER_ITF
        if itf.any():
            probs[vname][itf] = full.probs(p[idx_test][itf])
        if (~itf).any():
            probs[vname][~itf] = nomtb.probs(p[idx_test][~itf])
        log(work, f"tennis: neighbour events {vname}")
    base_pr = probs["V0_production"]
    # neighbour-scope variants: the SAME production p, the table cut by group
    p0_all = pv["V0_production"]
    scope_defs: dict[str, npt.NDArray[np.int64]] = {
        "S_tier": panel["tier"].astype(np.int64),
        "S_chtour_vs_itf": (panel["tier"] >= TIER_CH).astype(np.int64),
        "S_tier_gender": (panel["tier"] * 2 + panel["gender"]).astype(np.int64),
        "S_tier_surface3": (panel["tier"] * 4 + panel["s3"]).astype(np.int64),
    }
    for sname, grp in scope_defs.items():
        out_s = np.zeros((idx_test.size, N_EVENTS))
        for gid in np.unique(grp[idx_test]):
            in_g_test = grp[idx_test] == gid
            in_g_train = tr_mask & (grp == gid)
            tier_g = panel["tier"][idx_test][in_g_test]
            for itf_flag in (True, False):
                sel_t = in_g_test & ((panel["tier"][idx_test] == TIER_ITF) == itf_flag)
                if not sel_t.any():
                    continue
                trm = in_g_train & (True if itf_flag else ~mtb_tr)
                table_g = outcomes_arrays(panel, p0_all, trm)
                if table_g[0].size < 2 * W_NEIGHBOURS:
                    out_s[sel_t] = base_pr[sel_t]  # group too thin: the global table
                    continue
                out_s[sel_t] = NeighbourTable(*table_g).probs(p0_all[idx_test][sel_t])
            del tier_g
        probs[sname] = out_s
        log(work, f"tennis: scoped neighbours {sname}")
    keep = ((base_pr > 0.05) & (base_pr < 0.95)).astype(np.float64)
    region70 = (np.maximum(base_pr, 1 - base_pr) >= 0.70).astype(np.float64) * keep
    _, inv = np.unique(panel["ev"][idx_test], return_inverse=True)
    n_match = int(inv.max()) + 1
    res["events"] = {
        "matches": n_match,
        "kept_events": int(keep.sum()),
        "kept_events_p70_side": int(region70.sum()),
    }
    base_ll = event_loss_by_family(base_pr, truth, keep)
    base_ll70 = event_loss_by_family(base_pr, truth, region70)
    mk: dict[str, Any] = {}

    def compare(
        prob: FloatArr, sel: npt.NDArray[np.bool_] | None = None
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        ll_v = event_loss_by_family(prob, truth, keep)
        ll_v70 = event_loss_by_family(prob, truth, region70)
        for f in FAMILIES:
            row: dict[str, Any] = {
                "logloss": float(ll_v[f][0].sum() / ll_v[f][1].sum())
            }
            for tag, a_, b_ in (("all", ll_v, base_ll), ("p70", ll_v70, base_ll70)):
                num = a_[f][0] - b_[f][0]
                den = b_[f][1]
                ok = den > 0
                pt, lo, hi = cluster_bootstrap_mean(num[ok], den[ok], reps=300)
                row[f"d_logloss_vs_V0_{tag}"] = [pt, lo, hi]
            out[f] = row
        return out

    for vname in probs:
        mk[vname] = compare(probs[vname])
        log(work, f"tennis: market compare {vname}")
    res["markets"] = mk
    # games_total ladder bias (mean predicted - realised over the kept events)
    bias_rows: dict[str, Any] = {}
    gt_n = len(GT_LINES)
    for vname in (
        "V0_production",
        "S_tier",
        "S_chtour_vs_itf",
        "S_tier_gender",
        "S_tier_surface3",
    ):
        entry_b: dict[str, Any] = {}
        for tn, tm in (
            ("ITF", panel["tier"][idx_test] == 0),
            ("CH", panel["tier"][idx_test] == 1),
            ("TOUR", panel["tier"][idx_test] == 2),
        ):
            kp = keep[tm][:, :gt_n]
            entry_b[tn] = float(
                ((probs[vname][tm][:, :gt_n] - truth[tm][:, :gt_n]) * kp).sum()
                / max(kp.sum(), 1)
            )
        bias_rows[vname] = entry_b
    res["games_total_bias_by_tier"] = bias_rows
    res["post_calibration_H2"] = post_calibration(
        probs,
        truth,
        panel["ev"][idx_test],
        panel["ts"][idx_test].astype(np.float64),
        [
            "V0_production",
            "S_tier",
            "S_tier_gender",
            "V5_tier_init",
            "V4_prod_plus_surface4",
        ],
    )
    log(work, "tennis: post-calibration done")
    mid_ts = float(np.median(panel["ts"][idx_test]))
    halves: dict[str, Any] = {}
    for hn, hmask in (
        ("H1", panel["ts"][idx_test] < mid_ts),
        ("H2", panel["ts"][idx_test] >= mid_ts),
    ):
        halves[hn] = {}
        for vname in (
            "V4_prod_plus_surface4",
            "V5_tier_init",
            "V8_tier_x_gender",
            "V3_surface4_hier_k1.0",
            "S_tier",
            "S_chtour_vs_itf",
            "S_tier_gender",
            "S_tier_surface3",
        ):
            hk = hmask[:, None] * keep
            ll_h = event_loss_by_family(probs[vname], truth, hk)
            b_h = event_loss_by_family(base_pr, truth, hk)
            halves[hn][vname] = {
                f: float((ll_h[f][0].sum() - b_h[f][0].sum()) / b_h[f][1].sum())
                for f in FAMILIES
            }
    res["halves_d_logloss_vs_V0"] = halves
    # ---- serve / return decomposition (Klaassen-Magnus) on TOUR + CH ----
    sel = (
        (panel["tier"][idx_test] >= TIER_CH)
        & (panel["mtb"][idx_test] == 0)
        & (panel["m_h"][idx_test] >= 6)
        & (panel["m_a"][idx_test] >= 6)
    )
    pos = np.flatnonzero(sel)
    res["km_rows"] = int(pos.size)
    if pos.size > 100:
        gi = idx_test[pos]
        a_sh, a_rh, a_sa, a_ra, a_mu = (
            panel[k][gi] for k in ("s_h", "r_h", "s_a", "r_a", "mu")
        )
        p_elo = pv["V0_production"][gi]
        km_pure = km_events(a_sh, a_rh, a_sa, a_ra, a_mu)
        km_hyb = km_events(a_sh, a_rh, a_sa, a_ra, a_mu, p_target=p_elo)
        z0 = np.zeros(pos.size)
        km_zero = km_events(z0, z0, z0, z0, a_mu, p_target=p_elo)
        km_half = km_events(
            0.5 * a_sh, 0.5 * a_rh, 0.5 * a_sa, 0.5 * a_ra, a_mu, p_target=p_elo
        )
        prob_sub = {
            "V0_production": base_pr[pos],
            "KM_pure": km_pure,
            "KM_hybrid_elo": km_hyb,
            "KM_hybrid_no_player_ratings": km_zero,
            "KM_hybrid_half_ratings": km_half,
            "mix_V0_KMhybrid": 0.5 * base_pr[pos] + 0.5 * km_hyb,
            "mix_V0_KMpure": 0.5 * base_pr[pos] + 0.5 * km_pure,
            "mix_V0_KMhybrid_no_player_ratings": 0.5 * base_pr[pos] + 0.5 * km_zero,
            "mix_V0_KMhybrid_half_ratings": 0.5 * base_pr[pos] + 0.5 * km_half,
        }
        # bias of the games_total ladder: mean(pred - truth) per line, kept events
        bias: dict[str, list[float]] = {}
        for nm_b in ("V0_production", "KM_hybrid_no_player_ratings", "KM_hybrid_elo"):
            pr_b = prob_sub[nm_b][:, : len(GT_LINES)]
            tr_b = truth[pos][:, : len(GT_LINES)]
            kp = keep[pos][:, : len(GT_LINES)]
            bias[nm_b] = [
                float(
                    ((pr_b[:, i] - tr_b[:, i]) * kp[:, i]).sum()
                    / max(kp[:, i].sum(), 1)
                )
                for i in range(len(GT_LINES))
            ]
        res["km_games_total_bias_by_line"] = {"lines": GT_LINES, **bias}
        truth_s, keep_s, r70_s = truth[pos], keep[pos], region70[pos]
        kmres: dict[str, Any] = {}
        b_all = event_loss_by_family(prob_sub["V0_production"], truth_s, keep_s)
        b_70 = event_loss_by_family(prob_sub["V0_production"], truth_s, r70_s)
        for nm, pr in prob_sub.items():
            a_all = event_loss_by_family(pr, truth_s, keep_s)
            a_70 = event_loss_by_family(pr, truth_s, r70_s)
            row_f: dict[str, Any] = {}
            for f in FAMILIES:
                item: dict[str, Any] = {
                    "logloss": float(a_all[f][0].sum() / a_all[f][1].sum())
                }
                for tag, aa, bb in (("all", a_all, b_all), ("p70", a_70, b_70)):
                    num = aa[f][0] - bb[f][0]
                    den = bb[f][1]
                    okk = den > 0
                    item[f"d_logloss_vs_V0_{tag}"] = list(
                        cluster_bootstrap_mean(num[okk], den[okk], reps=300)
                    )
                row_f[f] = item
            kmres[nm] = row_f
        res["km"] = kmres
        # the same question on top of the tier x gender scoped neighbours: does
        # the serve / return decomposition add information once the table's
        # tier bias is gone?
        stg = probs["S_tier_gender"][pos]
        sub2 = {
            "S_tier_gender": stg,
            "mix_Stg_KMhybrid": 0.5 * stg + 0.5 * km_hyb,
            "mix_Stg_KM_no_player_ratings": 0.5 * stg + 0.5 * km_zero,
            "mix_Stg_KMhybrid_w0.25": 0.75 * stg + 0.25 * km_hyb,
            "mix_Stg_KM_no_player_ratings_w0.25": 0.75 * stg + 0.25 * km_zero,
        }
        b2_all = event_loss_by_family(stg, truth_s, keep_s)
        b2_70 = event_loss_by_family(stg, truth_s, r70_s)
        km2: dict[str, Any] = {}
        for nm, pr in sub2.items():
            a_all = event_loss_by_family(pr, truth_s, keep_s)
            a_70 = event_loss_by_family(pr, truth_s, r70_s)
            row2: dict[str, Any] = {}
            for f in FAMILIES:
                item2: dict[str, Any] = {
                    "logloss": float(a_all[f][0].sum() / a_all[f][1].sum())
                }
                for tag, aa, bb in (("all", a_all, b2_all), ("p70", a_70, b2_70)):
                    num = aa[f][0] - bb[f][0]
                    den = bb[f][1]
                    okk = den > 0
                    item2[f"d_logloss_vs_Stg_{tag}"] = list(
                        cluster_bootstrap_mean(num[okk], den[okk], reps=300)
                    )
                row2[f] = item2
            km2[nm] = row2
        res["km_on_top_of_S_tier_gender"] = km2
        # does the serve strength carry information the Elo p does not? - games_total
        # residual regression on sserve within the p-neighbour window
        ss = panel["sserve"][gi]
        gt = (panel["gh"][gi] + panel["ga"][gi]).astype(np.float64)
        exp_gt = (
            (1.0 - prob_sub["V0_production"][:, : len(GT_LINES)]).sum(axis=1)
            + GT_LINES[0]
            - 0.5
        )
        resid = gt - (
            np.sum(prob_sub["V0_production"][:, : len(GT_LINES)], axis=1)
            + GT_LINES[0]
            - 0.5
        )
        res["km_serve_strength_vs_games_resid"] = {
            "corr": float(np.corrcoef(ss, resid)[0, 1]),
            "n": int(pos.size),
        }
        del exp_gt
    return res


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "stage",
        choices=["extract", "tennis", "calib", "calibthin", "interval", "report"],
    )
    ap.add_argument("--db-path", default=DEFAULT_DB)
    ap.add_argument("--work-dir", default=DEFAULT_WORK)
    ap.add_argument("--sport", default="tennis", choices=["tennis", "football"])
    ap.add_argument(
        "--reuse-panel",
        action="store_true",
        help="tennis: skip the history / panel pass, reuse panel.pkl",
    )
    ap.add_argument(
        "--out-json", default="docs/sofa/evidence/tennis_calibration_2026-10-08.json"
    )
    ap.add_argument(
        "--split-ts",
        type=int,
        default=0,
        help="unix ts of the train/test cut (0 = per-stage default)",
    )
    args = ap.parse_args()
    work = Path(args.work_dir)
    work.mkdir(parents=True, exist_ok=True)
    if args.stage == "extract":
        extract_rows(
            args.db_path,
            args.sport,
            work / f"rows_{args.sport}.npz",
            P_MIN_EXTRACT,
            work,
        )
        return 0
    if args.stage == "tennis":
        out_t = run_tennis(args.db_path, work, args.reuse_panel)
        (work / "tennis.json").write_text(json.dumps(out_t, indent=1, default=float))
        return 0
    split = args.split_ts or SPLIT_DEFAULT
    rows_path = work / f"rows_{args.sport}.npz"
    if args.stage == "calib":
        out = run_calib(rows_path, args.sport, split, work)
        (work / f"calib_{args.sport}.json").write_text(json.dumps(out, indent=1))
        return 0
    if args.stage == "calibthin":
        out_c = run_calib_thin(rows_path, args.sport, split, work)
        (work / f"calibthin_{args.sport}.json").write_text(json.dumps(out_c, indent=1))
        return 0
    if args.stage == "interval":
        out = run_interval(rows_path, args.sport, split, work)
        (work / f"interval_{args.sport}.json").write_text(json.dumps(out, indent=1))
        return 0
    if args.stage == "report":
        merged: dict[str, Any] = {
            "generated_by": "scripts/sofa/measure_tennis_calibration.py",
            "source_db": args.db_path,
            "train_test_cut_utc": "2026-04-01T00:00:00Z",
            "note": "read-only evidence; no config, curve or constant was written",
        }
        for part in (
            "calib_tennis",
            "calib_football",
            "interval_tennis",
            "interval_football",
            "tennis",
        ):
            f = work / f"{part}.json"
            if f.exists():
                merged[part] = json.loads(f.read_text())
        out_path = Path(args.out_json)
        out_path.write_text(json.dumps(merged, indent=1, default=float) + "\n")
        print(f"wrote {out_path}")
        return 0
    raise SystemExit(f"stage {args.stage} not implemented")


if __name__ == "__main__":
    raise SystemExit(main())
