#!/usr/bin/env python3
"""Read-only measurement: dependence in football joints, and a goals model.

Track A3 (2026-10-08). Nothing here is wired into the pipeline and nothing is
written to the database; the football history comes from the parsed pickle
`data/cache/football_history.pkl` (what SHEET's `football_rating.load_history`
keeps), opened read-only.

(a) DEPENDENCE - `joint`
    The football joints (both_over_ / most_ / handicap_ of goals, corners,
    shots on target, cards) are a Gaussian copula over Poisson / NB marginals
    with one measured side correlation per metric (`joint.py`,
    `config/sofa_side_correlations.json`). Replayed here from the marginal
    rows' centres (`derived.marginal_centred_stats`, K_CENTRE shrink, exactly
    the inputs `calibrate_from_cache.football_joint_rows` builds), for every
    match of a TEST window, against matches strictly before it:

      cur      Gaussian copula, the shipped config correlation
      indep    independence
      g_all    Gaussian, correlation re-measured on a TRAIN window
      g_gap    Gaussian, correlation per tertile of the centres' strength gap
      g_women  Gaussian, correlation per women / men
      t4, t8   t copula (4 / 8 dof), the g_all latent parameter (same Kendall
               tau as the Gaussian: only the tails differ)

    Scored on the same events (both_over rungs, side handicaps, most_ win /
    draw) by log-loss and Brier, match bootstrap, paired against `cur`.

    `matrix` measures the cross-market dependence a Bet Builder meets: Pearson
    correlations (raw and residual to the as-of rating's expected count) of
    goals x corners x shots on target (and shots, cards) of one match and of
    one side, plus a few lifts of typical builder events, match bootstrap.

(b) GOALS - `goals`
    Centre = the as-of football rating's expected goals per side
    (`football_rating.FootballForecast.centre`), replayed in time order. Models
    on that centre: independent Poisson, independent NB, bivariate Poisson
    (Karlis-Ntzoufras, lambda3 = kappa * min(centres)), Dixon-Coles low-score
    correction (rho; on Poisson and on NB), and the rating with its smoothing
    constant x0.5 / x2 (the rating is an exponential time-decay already; this
    is the time-decay variant that exists in the code). Parameters fit on a
    TRAIN window, scored on a TEST window.

Usage:
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_dependence_goals.py \
        {joint --bases goals|corners|... | matrix | goals} --out <json>
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import statistics
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from bet.sofa import football_rating as fr
from bet.sofa.derived import SideStats, load_side_correlations, marginal_centred_stats
from bet.sofa.joint import _grid_size, count_pmf

F64 = NDArray[np.float64]

DEFAULT_HISTORY = Path("data/cache/football_history.pkl")
TRAIN_FROM = "2025-08-01"
TEST_FROM = "2026-06-01"
TEST_TO = "2026-10-08"
MIN_SAMPLE = 8
SAMPLE_N = 10
JOINT_REACH = 3
RES_LO, RES_HI = 0.05, 0.95

# --------------------------------------------------------------------------
# numerics (numpy only: no scipy in this project)
# --------------------------------------------------------------------------

_GRID = np.linspace(-9.0, 9.0, 36001)
_TABLE = np.array([0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0))) for x in _GRID])
_QX, _QW = np.polynomial.legendre.leggauss(32)


def norm_cdf(x: F64) -> F64:
    """Standard normal CDF by table interpolation (error ~1e-8)."""
    return np.interp(x, _GRID, _TABLE)  # type: ignore[no-any-return]


def norm_ppf(p: F64) -> F64:
    """Inverse normal CDF by interpolation of the table (+-9 sigma clip)."""
    q = np.clip(p, 1e-15, 1.0 - 1e-15)
    out = np.interp(q, _TABLE, _GRID)
    # refine once by Newton on the exact erf-free table-derivative
    dens = np.exp(-0.5 * out * out) / math.sqrt(2.0 * math.pi)
    out = out - (norm_cdf(out) - q) / np.maximum(dens, 1e-300)
    return np.clip(out, -9.0, 9.0)


def bvn_cdf_grid(h: F64, k: F64, rho: float) -> F64:
    """P(Z1 <= h_i, Z2 <= k_j) for a standard bivariate normal, as a matrix.

    Phi2(h, k) = int_{-inf}^{h} phi(z) Phi((k - rho z) / s) dz, s = sqrt(1-rho^2),
    by 32-point Gauss-Legendre on [-9, h_i]."""
    h = np.clip(h, -9.0, 9.0)
    k = np.clip(k, -9.0, 9.0)
    if rho == 0.0:
        return np.outer(norm_cdf(h), norm_cdf(k))
    s = math.sqrt(1.0 - rho * rho)
    lo = -9.0
    z = lo + (h[:, None] - lo) * (_QX[None, :] + 1.0) / 2.0  # (I, Q)
    w = (
        (h[:, None] - lo)
        / 2.0
        * _QW[None, :]
        * np.exp(-0.5 * z * z)
        / math.sqrt(2.0 * math.pi)
    )
    inner = norm_cdf((k[None, None, :] - rho * z[:, :, None]) / s)  # (I, Q, J)
    return np.einsum("iq,iqj->ij", w, inner)  # type: ignore[no-any-return]


def _chi2_nodes(nu: int, m: int = 24) -> F64:
    """Equal-probability midpoints of chi-square(nu), nu even (Erlang cdf)."""
    half = nu // 2
    probs = (np.arange(m) + 0.5) / m
    lo = np.zeros(m)
    hi = np.full(m, 200.0)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        x = mid / 2.0
        cdf = 1.0 - np.exp(-x) * sum(x**i / math.factorial(i) for i in range(half))
        too_low = cdf < probs
        lo = np.where(too_low, mid, lo)
        hi = np.where(too_low, hi, mid)
    return (lo + hi) / 2.0  # type: ignore[no-any-return]


def count_pmf_np(mean: float, variance: float, kmax: int) -> F64:
    """joint.count_pmf as an array (Poisson, or NB when overdispersed)."""
    return np.asarray(count_pmf(mean, variance, kmax), dtype=np.float64)


def copula_pmf(
    mean_a: float,
    var_a: float,
    mean_b: float,
    var_b: float,
    latent: float,
    family: str = "gauss",
    nu: int = 4,
) -> F64:
    """Joint pmf on the count grid of a Gaussian or t copula over the
    joint.py marginals. `latent` is the copula parameter."""
    mean_a, mean_b = max(1e-6, mean_a), max(1e-6, mean_b)
    kmax = _grid_size(mean_a, var_a, mean_b, var_b)
    cdf_a = np.minimum(1.0, np.cumsum(count_pmf_np(mean_a, max(0.0, var_a), kmax)))
    cdf_b = np.minimum(1.0, np.cumsum(count_pmf_np(mean_b, max(0.0, var_b), kmax)))
    cdf_a[-1] = cdf_b[-1] = 1.0
    if family == "gauss":
        corners = bvn_cdf_grid(norm_ppf(cdf_a), norm_ppf(cdf_b), latent)
    else:
        nodes = _chi2_nodes(nu)
        scale = np.sqrt(nodes / nu)

        def t_cdf(x: F64) -> F64:
            return np.mean(norm_cdf(x[None, :] * scale[:, None]), axis=0)  # type: ignore[no-any-return]

        def t_ppf(p: F64) -> F64:
            lo = np.full(p.shape, -60.0)
            hi = np.full(p.shape, 60.0)
            for _ in range(60):
                mid = (lo + hi) / 2.0
                below = t_cdf(mid) < p
                lo = np.where(below, mid, lo)
                hi = np.where(below, hi, mid)
            return (lo + hi) / 2.0  # type: ignore[no-any-return]

        ta = t_ppf(np.clip(cdf_a, 1e-12, 1 - 1e-12))
        tb = t_ppf(np.clip(cdf_b, 1e-12, 1 - 1e-12))
        corners = np.zeros((len(ta), len(tb)))
        for sc in scale:
            corners += bvn_cdf_grid(ta * sc, tb * sc, latent)
        corners /= len(scale)
        corners[-1, :] = cdf_b
        corners[:, -1] = cdf_a
    padded = np.zeros((corners.shape[0] + 1, corners.shape[1] + 1))
    padded[1:, 1:] = corners
    pmf = padded[1:, 1:] - padded[:-1, 1:] - padded[1:, :-1] + padded[:-1, :-1]
    pmf = np.maximum(pmf, 0.0)
    total = pmf.sum()
    return pmf / total if total > 0 else pmf  # type: ignore[no-any-return]


def observed_corr(pmf: F64) -> float:
    n = pmf.shape[0]
    i = np.arange(n, dtype=np.float64)
    j = np.arange(pmf.shape[1], dtype=np.float64)
    pa, pb = pmf.sum(axis=1), pmf.sum(axis=0)
    ma, mb = float(i @ pa), float(j @ pb)
    va = float(((i - ma) ** 2) @ pa)
    vb = float(((j - mb) ** 2) @ pb)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = float(((i - ma)[:, None] * (j - mb)[None, :] * pmf).sum())
    return cov / math.sqrt(va * vb)


def solve_latent(
    mean_a: float,
    var_a: float,
    mean_b: float,
    var_b: float,
    target: float,
) -> float:
    """Latent Gaussian rho whose joint has Pearson correlation `target`
    (the discrete margins attenuate it; joint._solve_latent_rho does the same
    by bisection)."""
    if abs(target) < 1e-9:
        return 0.0
    lo, hi = (-0.999, 0.0) if target < 0 else (0.0, 0.999)
    mid = 0.0
    for _ in range(14):
        mid = (lo + hi) / 2.0
        got = observed_corr(copula_pmf(mean_a, var_a, mean_b, var_b, mid))
        if abs(got - target) < 2e-3:
            return mid
        if got < target:
            lo = mid
        else:
            hi = mid
    return mid


def event_probs(
    pmf: F64, lines: Sequence[float], hcp_lines: Sequence[float]
) -> dict[str, F64]:
    """both_over (per line), handicap (home / away, per line), most (home, away,
    draw) of one joint pmf, in the order the callers index them."""
    n, m = pmf.shape
    i = np.arange(n)[:, None]
    j = np.arange(m)[None, :]
    out: dict[str, F64] = {}
    both = []
    for line in lines:
        thr = math.floor(line) + 1
        both.append(pmf[thr:, thr:].sum() if thr < min(n, m) else 0.0)
    out["both_over"] = np.asarray(both)
    diff = i - j
    out["handicap_home"] = np.asarray([pmf[diff > -line].sum() for line in hcp_lines])
    out["handicap_away"] = np.asarray(
        [pmf[(-diff) > -line].sum() for line in hcp_lines]
    )
    out["most"] = np.asarray(
        [pmf[diff > 0].sum(), pmf[diff < 0].sum(), pmf[diff == 0].sum()]
    )
    return {k: np.clip(v, 0.0, 1.0) for k, v in out.items()}


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------


def log_loss(p: F64, o: F64) -> F64:
    q = np.clip(p, 1e-9, 1.0 - 1e-9)
    return -(o * np.log(q) + (1.0 - o) * np.log(1.0 - q))


def brier(p: F64, o: F64) -> F64:
    return (p - o) ** 2


def bootstrap_ratio(
    num: F64,
    den: F64,
    reps: int = 1000,
    seed: int = 7,
) -> tuple[float, float, float]:
    """Match bootstrap of sum(num) / sum(den) over match-level sums:
    (estimate, lo95, hi95). `num[i]`, `den[i]` belong to match i."""
    n = len(num)
    if n == 0 or den.sum() == 0:
        return (math.nan, math.nan, math.nan)
    rng = np.random.default_rng(seed)
    est = float(num.sum() / den.sum())
    stats = np.empty(reps)
    for r in range(reps):
        idx = rng.integers(0, n, n)
        d = den[idx].sum()
        stats[r] = num[idx].sum() / d if d > 0 else math.nan
    return (
        est,
        float(np.nanpercentile(stats, 2.5)),
        float(np.nanpercentile(stats, 97.5)),
    )


def pearson(x: F64, y: F64) -> float:
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def corr_matrix_ci(
    data: F64,
    reps: int = 300,
    seed: int = 11,
) -> tuple[F64, F64, F64]:
    """Pearson matrix of the columns and its match-bootstrap 95% interval."""
    n = data.shape[0]
    est = np.asarray(np.corrcoef(data, rowvar=False), dtype=np.float64)
    rng = np.random.default_rng(seed)
    boots = np.empty((reps, data.shape[1], data.shape[1]))
    for r in range(reps):
        boots[r] = np.corrcoef(data[rng.integers(0, n, n)], rowvar=False)
    return est, np.percentile(boots, 2.5, axis=0), np.percentile(boots, 97.5, axis=0)


# --------------------------------------------------------------------------
# goals models (vectorised over matches)
# --------------------------------------------------------------------------


def poisson_pmf_matrix(lam: F64, kmax: int) -> F64:
    k = np.arange(kmax + 1)
    logfact = np.array([math.lgamma(v + 1) for v in k])
    lam = np.maximum(lam, 1e-9)
    return np.exp(-lam[:, None] + k[None, :] * np.log(lam)[:, None] - logfact[None, :])  # type: ignore[no-any-return]


def nb_pmf_matrix(lam: F64, r: float, kmax: int) -> F64:
    """NB with mean lam and var = lam + lam^2 / r."""
    k = np.arange(kmax + 1)
    lam = np.maximum(lam, 1e-9)
    p = r / (r + lam)
    lg = np.array([math.lgamma(v + r) - math.lgamma(r) - math.lgamma(v + 1) for v in k])
    return np.exp(
        lg[None, :] + r * np.log(p)[:, None] + k[None, :] * np.log1p(-p)[:, None]
    )


def independent_grid(pa: F64, pb: F64) -> F64:
    return pa[:, :, None] * pb[:, None, :]


def dc_tau_grid(lh: F64, la: F64, rho: float, shape: tuple[int, int, int]) -> F64:
    """Dixon-Coles multiplier tau on the 2x2 low-score cells (1 elsewhere)."""
    tau = np.ones(shape)
    tau[:, 0, 0] = 1.0 - lh * la * rho
    tau[:, 0, 1] = 1.0 + lh * rho
    tau[:, 1, 0] = 1.0 + la * rho
    tau[:, 1, 1] = 1.0 - rho
    return tau


def dc_grid(base: F64, lh: F64, la: F64, rho: float) -> F64:
    out = base * dc_tau_grid(lh, la, rho, base.shape)
    return np.maximum(out, 0.0)


def bivariate_poisson_grid(lh: F64, la: F64, kappa: float, kmax: int) -> F64:
    """X = Y1 + Y3, Y = Y2 + Y3, E X = lh, E Y = la; lambda3 = kappa * min."""
    l3 = np.minimum(kappa * np.minimum(lh, la), 0.999 * np.minimum(lh, la))
    p1 = poisson_pmf_matrix(lh - l3, kmax)
    p2 = poisson_pmf_matrix(la - l3, kmax)
    p3 = poisson_pmf_matrix(l3, kmax)
    grid = np.zeros((len(lh), kmax + 1, kmax + 1))
    for k in range(kmax + 1):
        grid[:, k:, k:] += (
            p3[:, k][:, None, None]
            * p1[:, : kmax + 1 - k, None]
            * p2[:, None, : kmax + 1 - k]
        )
    return grid


def grid_loglik(grid: F64, x: NDArray[np.int64], y: NDArray[np.int64]) -> float:
    idx = np.arange(len(x))
    return float(np.log(np.maximum(grid[idx, x, y], 1e-300)).sum())


def fit_dc_rho(
    lh: F64,
    la: F64,
    x: NDArray[np.int64],
    y: NDArray[np.int64],
    base_low: F64 | None = None,
) -> float:
    """ML rho of the Dixon-Coles correction, by grid + refinement on the four
    low cells (tau == 1 elsewhere and tau preserves the total, so only the
    observed low-score matches carry a rho term)."""
    low = (x <= 1) & (y <= 1)

    def ll(rho: float) -> float:
        tau = np.ones(len(lh))
        for cx, cy, f in (
            (0, 0, 1.0 - lh * la * rho),
            (0, 1, 1.0 + lh * rho),
            (1, 0, 1.0 + la * rho),
            (1, 1, 1.0 - rho + 0 * lh),
        ):
            sel = low & (x == cx) & (y == cy)
            tau[sel] = f[sel]
        if (tau <= 0).any():
            return -math.inf
        return float(np.log(tau[low]).sum())

    best = max((ll(r), r) for r in np.linspace(-0.3, 0.3, 61))
    step = 0.01
    rho = best[1]
    for _ in range(40):
        cand = [(ll(rho + d), rho + d) for d in (-step, 0.0, step)]
        nxt = max(cand)[1]
        if nxt == rho:
            step /= 2.0
        rho = nxt
    return float(rho)


def fit_scalar(f: Any, lo: float, hi: float, iters: int = 60) -> float:
    """Maximise a unimodal f on [lo, hi] by golden-section."""
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(iters):
        if fc > fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return (a + b) / 2.0


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------


def ts_of(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def load_pickle(path: Path) -> list[fr.FootballResult]:
    """The parsed football history, read-only (never rewritten here)."""
    _fp, history = pickle.loads(path.read_bytes())
    return list(history)


def note(msg: str) -> None:
    stamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{stamp}] {msg}", file=sys.stderr, flush=True)


# --------------------------------------------------------------------------
# (a) joints
# --------------------------------------------------------------------------


@dataclass
class JointInput:
    ts: int
    event_id: int
    comp: int
    women: bool
    mu_a: float
    var_a: float
    mu_b: float
    var_b: float
    x: float
    y: float
    gap: float  # |mu_a - mu_b| / (mu_a + mu_b)


def collect_joint_inputs(
    history: Sequence[fr.FootballResult],
    base: str,
    train_ts: int,
    baselines: dict[str, Any],
    k_centre: float,
) -> list[JointInput]:
    """One row per match from `train_ts` on whose two sides each have a sample
    of MIN_SAMPLE matches, with the centres and variances the football joint
    uses (marginal_centred_stats on the K_CENTRE-shrunk centre). Goals take the
    side's matches of the same competition when it has enough of them."""
    from bet.sofa.comparability import SAME_COMPETITION_METRICS, pick_same_competition
    from bet.sofa.samples import INDEXED_HISTORY_LIMIT
    from scripts.sofa.calibrate_from_cache import prior_for

    key = f"{base}_for"
    hist: dict[int, list[tuple[float, int]]] = defaultdict(list)  # (value, comp)
    rows: list[JointInput] = []

    def sample(team: int, comp: int) -> list[float]:
        past = hist[team]
        if key in SAME_COMPETITION_METRICS:
            picked = pick_same_competition(
                past[: -INDEXED_HISTORY_LIMIT - 1 : -1],
                comp,
                SAMPLE_N,
                lambda p: p[1],
                lambda p: True,
            )
            if picked is not None:
                return [p[0] for p in reversed(picked)]
        return [p[0] for p in past[-SAMPLE_N:]]

    for r in history:
        if key not in r.values:
            continue
        home_v, away_v = r.values[key]
        if r.ts >= train_ts:
            sa, sb = (
                sample(r.home_id, r.competition_id),
                sample(r.away_id, r.competition_id),
            )
            if (
                len(sa) >= MIN_SAMPLE
                and len(sb) >= MIN_SAMPLE
                and any(v for v in (*sa, *sb))
            ):
                prior = prior_for(baselines, key, r.competition_id)
                stats = []
                ok = True
                for s in (sa, sb):
                    n = len(s)
                    mean = statistics.mean(s)
                    var = statistics.variance(s) if n > 1 else 0.0
                    raw = SideStats(n=n, mean=mean, variance=var, sd=math.sqrt(var))
                    if not any(s):
                        ok = False
                        break
                    centre = (
                        mean
                        if prior is None
                        else (
                            n / (n + k_centre) * mean + (1 - n / (n + k_centre)) * prior
                        )
                    )
                    stats.append(marginal_centred_stats(raw, key, centre))
                if ok:
                    a, b = stats
                    rows.append(
                        JointInput(
                            r.ts,
                            r.event_id,
                            r.competition_id,
                            bool(r.women),
                            a.mean,
                            a.variance,
                            b.mean,
                            b.variance,
                            home_v,
                            away_v,
                            abs(a.mean - b.mean) / (a.mean + b.mean),
                        )
                    )
        hist[r.home_id].append((home_v, r.competition_id))
        hist[r.away_id].append((away_v, r.competition_id))
        for team in (r.home_id, r.away_id):
            if len(hist[team]) > 2 * INDEXED_HISTORY_LIMIT:
                del hist[team][:INDEXED_HISTORY_LIMIT]
    return rows


def residual_target(rows: Sequence[JointInput]) -> float | None:
    """The correlation of the two sides' standardised residuals (what the joint
    must carry: each marginal already holds its own mean and spread)."""
    if len(rows) < 200:
        return None
    za = np.array([(r.x - r.mu_a) / math.sqrt(max(r.var_a, 1e-9)) for r in rows])
    zb = np.array([(r.y - r.mu_b) / math.sqrt(max(r.var_b, 1e-9)) for r in rows])
    return float(np.mean(za * zb))


def joint_events(row: JointInput) -> tuple[list[float], list[float]]:
    low = max(0, math.floor(min(row.mu_a, row.mu_b)) - JOINT_REACH)
    lines = [low + 0.5 + k for k in range(2 * JOINT_REACH + 1)]
    first = math.floor(-(row.mu_a - row.mu_b)) - JOINT_REACH
    hl = [first + 0.5 + k for k in range(2 * JOINT_REACH + 1)]
    return lines, hl


def outcomes(
    row: JointInput, lines: Sequence[float], hl: Sequence[float]
) -> dict[str, F64]:
    both = min(row.x, row.y)
    d = row.x - row.y
    return {
        "both_over": np.array(
            [1.0 if both >= math.floor(L) + 1 else 0.0 for L in lines]
        ),
        "handicap_home": np.array([1.0 if d > -L else 0.0 for L in hl]),
        "handicap_away": np.array([1.0 if -d > -L else 0.0 for L in hl]),
        "most": np.array(
            [1.0 if d > 0 else 0.0, 1.0 if d < 0 else 0.0, 1.0 if d == 0 else 0.0]
        ),
    }


JOINT_MODELS = ("cur", "indep", "g_all", "g_gap", "g_women", "t4", "t8")
CLASSES = ("both_over", "handicap", "most")


def score_joints(
    test: Sequence[JointInput],
    targets: dict[str, Any],
    cfg_rho: float,
    gap_cuts: tuple[float, float],
) -> dict[str, Any]:
    """Per-match loss sums per (model, class), paired on the same events."""
    n = len(test)
    ll = {m: {c: np.zeros(n) for c in CLASSES} for m in JOINT_MODELS}
    br = {m: {c: np.zeros(n) for c in CLASSES} for m in JOINT_MODELS}
    cnt = {c: np.zeros(n) for c in CLASSES}
    month = [datetime.fromtimestamp(r.ts, UTC).strftime("%Y-%m") for r in test]
    t0 = time.time()
    for i, row in enumerate(test):
        if i and i % 2000 == 0:
            note(f"  scored {i}/{n} ({time.time() - t0:.0f}s)")
        lines, hl = joint_events(row)
        gb = 0 if row.gap < gap_cuts[0] else (1 if row.gap < gap_cuts[1] else 2)
        tg = {
            "cur": cfg_rho,
            "g_all": targets["all"],
            "g_gap": targets["gap"][gb]
            if targets["gap"][gb] is not None
            else targets["all"],
            "g_women": targets["women"][int(row.women)]
            if targets["women"][int(row.women)] is not None
            else targets["all"],
        }
        pm: dict[str, F64] = {}
        args = (row.mu_a, row.var_a, row.mu_b, row.var_b)
        pm["indep"] = copula_pmf(*args, 0.0)
        cache: dict[float, float] = {}
        lat = {}
        for name, t in tg.items():
            key = round(t, 4)
            if key not in cache:
                cache[key] = solve_latent(*args, t)
            lat[name] = cache[key]
            if name in ("cur", "g_all", "g_gap", "g_women"):
                pm[name] = copula_pmf(*args, lat[name])
        pm["t4"] = copula_pmf(*args, lat["g_all"], "t", 4)
        pm["t8"] = copula_pmf(*args, lat["g_all"], "t", 8)
        out = outcomes(row, lines, hl)
        ev = {m: event_probs(pm[m], lines, hl) for m in JOINT_MODELS}
        # events scored: those the shipped model leaves inside the resolution
        # band (the production refusal, outside_model_resolution)
        keep = {
            "both_over": (ev["cur"]["both_over"] >= RES_LO)
            & (ev["cur"]["both_over"] <= RES_HI),
            "handicap_home": (ev["cur"]["handicap_home"] >= RES_LO)
            & (ev["cur"]["handicap_home"] <= RES_HI),
            "handicap_away": (ev["cur"]["handicap_away"] >= RES_LO)
            & (ev["cur"]["handicap_away"] <= RES_HI),
            "most": (ev["cur"]["most"] >= RES_LO) & (ev["cur"]["most"] <= RES_HI),
        }
        for m in JOINT_MODELS:
            for part, cls in (
                ("both_over", "both_over"),
                ("handicap_home", "handicap"),
                ("handicap_away", "handicap"),
                ("most", "most"),
            ):
                p, o, k = ev[m][part], out[part], keep[part]
                ll[m][cls][i] += float(log_loss(p, o)[k].sum())
                br[m][cls][i] += float(brier(p, o)[k].sum())
                if m == "cur":
                    cnt[cls][i] += float(k.sum())
    res: dict[str, Any] = {"matches": n}
    months = sorted(set(month))
    marr = np.array(month)
    for cls in CLASSES:
        res[cls] = {"events": float(cnt[cls].sum())}
        for m in JOINT_MODELS:
            e, lo, hi = bootstrap_ratio(ll[m][cls], cnt[cls])
            eb, _, _ = bootstrap_ratio(br[m][cls], cnt[cls])
            entry: dict[str, Any] = {"logloss": e, "brier": eb}
            if m != "cur":
                d = ll["cur"][cls] - ll[m][cls]  # positive = model beats cur
                g, glo, ghi = bootstrap_ratio(d, cnt[cls])
                db = br["cur"][cls] - br[m][cls]
                gb_, blo, bhi = bootstrap_ratio(db, cnt[cls])
                entry["gain_vs_cur_logloss"] = [g, glo, ghi]
                entry["gain_vs_cur_brier"] = [gb_, blo, bhi]
                per_month = {}
                for mo in months:
                    sel = marr == mo
                    per_month[mo] = bootstrap_ratio(d[sel], cnt[cls][sel], reps=200)[0]
                entry["gain_logloss_by_month"] = per_month
            res[cls][m] = entry
    return res


def run_joint(args: argparse.Namespace) -> dict[str, Any]:
    from scripts.sofa.calibrate_from_cache import k_centre_for, load_baselines

    history = load_pickle(Path(args.history))
    note(f"history {len(history)} matches")
    baselines = load_baselines()
    k_centre = k_centre_for("football")
    out: dict[str, Any] = {
        "windows": {
            "train_from": args.train_from,
            "test_from": args.test_from,
            "test_to": args.test_to,
        },
        "k_centre": k_centre,
    }
    cfg = load_side_correlations()
    ts_a, ts_b, ts_c = (
        ts_of(args.train_from),
        ts_of(args.test_from),
        ts_of(args.test_to),
    )
    for base in args.bases:
        note(f"{base}: collecting inputs")
        rows = collect_joint_inputs(history, base, ts_a, baselines, k_centre)
        train = [r for r in rows if r.ts < ts_b]
        test_all = [r for r in rows if ts_b <= r.ts < ts_c]
        rng = np.random.default_rng(3)
        test = test_all
        if len(test) > args.max_test:
            keep = np.sort(rng.choice(len(test), args.max_test, replace=False))
            test = [test_all[i] for i in keep]
        note(f"{base}: train {len(train)} test {len(test)} of {len(test_all)}")
        gaps = np.array([r.gap for r in train])
        cuts = (float(np.quantile(gaps, 1 / 3)), float(np.quantile(gaps, 2 / 3)))
        targets: dict[str, Any] = {
            "all": residual_target(train) or 0.0,
            "gap": [
                residual_target(
                    [
                        r
                        for r in train
                        if (0 if r.gap < cuts[0] else (1 if r.gap < cuts[1] else 2))
                        == b
                    ]
                )
                for b in range(3)
            ],
            "women": [
                residual_target([r for r in train if r.women == bool(w)])
                for w in (0, 1)
            ],
        }
        cfg_rho = cfg.get(base) or 0.0
        res = score_joints(test, targets, cfg_rho, cuts)
        res["train_matches"] = len(train)
        res["test_matches_available"] = len(test_all)
        res["config_rho"] = cfg_rho
        res["train_rho"] = targets
        res["gap_cuts"] = list(cuts)
        out[base] = res
        Path(args.out).write_text(
            json.dumps(out, indent=1, default=float), encoding="utf-8"
        )
        note(f"{base}: done")
    return out


# --------------------------------------------------------------------------
# (b) goals
# --------------------------------------------------------------------------


def rating_centres(
    history: Sequence[fr.FootballResult],
    from_ts: int,
    to_ts: int,
    alpha_scale: float = 1.0,
) -> dict[str, F64]:
    """As-of rating centres (expected goals, home / away) for every match in
    [from_ts, to_ts), the book updated only with matches before it. Matches
    without a rating centre are skipped. `alpha_scale` scales the goals
    smoothing constant (patched in this process only)."""
    saved = fr.ALPHA_BY_METRIC["goals_for"]
    fr.ALPHA_BY_METRIC["goals_for"] = saved * alpha_scale
    try:
        book = fr.RatingBook()
        cols: dict[str, list[float]] = {
            k: [] for k in ("ts", "lh", "la", "x", "y", "linked", "comp")
        }
        for r in history:
            if "goals_for" not in r.values:
                continue
            if from_ts <= r.ts < to_ts:
                fc = fr.FootballForecast(book, r.competition_id, r.home_id, r.away_id)
                ch = fc.centre("goals_for", "side_a")
                ca = fc.centre("goals_for", "side_b")
                if ch is not None and ca is not None:
                    cols["ts"].append(r.ts)
                    cols["lh"].append(ch[0])
                    cols["la"].append(ca[0])
                    cols["x"].append(r.values["goals_for"][0])
                    cols["y"].append(r.values["goals_for"][1])
                    cols["linked"].append(
                        1.0
                        if book.link(r.home_id, r.away_id, "goals_for")[0] == fr.LINKED
                        else 0.0
                    )
                    cols["comp"].append(float(r.competition_id))
            slim = replace(r, values={"goals_for": r.values["goals_for"]})
            book.update(slim)
            if r.ts >= to_ts:
                break
        return {k: np.asarray(v, dtype=np.float64) for k, v in cols.items()}
    finally:
        fr.ALPHA_BY_METRIC["goals_for"] = saved


GOAL_KMAX = 14
TOTAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5)
TEAM_LINES = (0.5, 1.5, 2.5)
HCP_LINES = (-1.5, -0.5, 0.5, 1.5)  # home goals - away goals > -line

GOAL_MODELS = ("poisson", "nb", "bp", "dc", "dc_nb")


def goal_event_matrix(grid: F64) -> tuple[F64, list[tuple[str, str]]]:
    """(N, E) event probabilities of a goals grid and the (class, rung) labels."""
    n, k1, _ = grid.shape
    i = np.arange(k1)[:, None]
    j = np.arange(k1)[None, :]
    cols: list[F64] = []
    labels: list[tuple[str, str]] = []

    def add(mask: NDArray[np.bool_], cls: str, rung: str) -> None:
        cols.append(np.clip(grid[:, mask].sum(axis=1), 0.0, 1.0))
        labels.append((cls, rung))

    for line in TOTAL_LINES:
        add((i + j) > line, "total_goals", f"over {line}")
    for line in TEAM_LINES:
        add((i + 0 * j) > line, "team_goals_home", f"over {line}")
        add((0 * i + j) > line, "team_goals_away", f"over {line}")
    add((i >= 1) & (j >= 1), "btts", "yes (both over 0.5)")
    add((i >= 2) & (j >= 2), "btts", "both over 1.5")
    add(i > j, "x12", "home")
    add(i < j, "x12", "away")
    add(i == j, "x12", "draw")
    for line in HCP_LINES:
        add((i - j) > -line, "handicap", f"home > {-line}")
    return np.stack(cols, axis=1), labels


def goal_outcomes(x: F64, y: F64) -> F64:
    cols: list[F64] = []
    for line in TOTAL_LINES:
        cols.append(((x + y) > line).astype(np.float64))
    for line in TEAM_LINES:
        cols.append((x > line).astype(np.float64))
        cols.append((y > line).astype(np.float64))
    cols.append(((x >= 1) & (y >= 1)).astype(np.float64))
    cols.append(((x >= 2) & (y >= 2)).astype(np.float64))
    cols.append((x > y).astype(np.float64))
    cols.append((x < y).astype(np.float64))
    cols.append((x == y).astype(np.float64))
    for line in HCP_LINES:
        cols.append(((x - y) > -line).astype(np.float64))
    return np.stack(cols, axis=1)


def fit_goal_models(train: dict[str, F64]) -> dict[str, float]:
    lh, la = train["lh"], train["la"]
    x = train["x"].astype(np.int64)
    y = train["y"].astype(np.int64)
    kmax = GOAL_KMAX
    xc, yc = np.minimum(x, kmax), np.minimum(y, kmax)

    def nb_ll(r: float) -> float:
        a, b = nb_pmf_matrix(lh, r, kmax), nb_pmf_matrix(la, r, kmax)
        idx = np.arange(len(xc))
        return float(
            np.log(np.maximum(a[idx, xc], 1e-300)).sum()
            + np.log(np.maximum(b[idx, yc], 1e-300)).sum()
        )

    log_r = fit_scalar(lambda v: nb_ll(math.exp(v)), math.log(2.0), math.log(2000.0))
    r_nb = math.exp(log_r)

    def bp_ll(kappa: float) -> float:
        return grid_loglik(bivariate_poisson_grid(lh, la, kappa, kmax), xc, yc)

    # the loglik of the bivariate Poisson needs the 3-d grid: subsample for the fit
    sub = np.random.default_rng(5).choice(len(lh), min(len(lh), 40000), replace=False)
    lh_s, la_s, xs, ys = lh[sub], la[sub], xc[sub], yc[sub]
    kappa = fit_scalar(
        lambda v: grid_loglik(bivariate_poisson_grid(lh_s, la_s, v, kmax), xs, ys),
        0.0,
        0.6,
        iters=24,
    )
    rho_dc = fit_dc_rho(lh, la, xc, yc)
    # DC on NB marginals: tau is a function of the means, the low-cell mass
    # moves with the NB, so refit on the NB grid
    a_nb, b_nb = nb_pmf_matrix(lh_s, r_nb, kmax), nb_pmf_matrix(la_s, r_nb, kmax)
    base_nb = independent_grid(a_nb, b_nb)

    def dcnb_ll(rho: float) -> float:
        g = dc_grid(base_nb, lh_s, la_s, rho)
        return grid_loglik(g / g.sum(axis=(1, 2), keepdims=True), xs, ys)

    rho_dc_nb = fit_scalar(dcnb_ll, -0.3, 0.2, iters=24)
    return {
        "nb_r": r_nb,
        "bp_kappa": kappa,
        "dc_rho": rho_dc,
        "dc_nb_rho": rho_dc_nb,
        "train_matches": float(len(lh)),
    }


def goal_model_grids(test: dict[str, F64], par: dict[str, float]) -> dict[str, F64]:
    lh, la = test["lh"], test["la"]
    kmax = GOAL_KMAX
    pa, pb = poisson_pmf_matrix(lh, kmax), poisson_pmf_matrix(la, kmax)
    pois = independent_grid(pa, pb)
    nba = nb_pmf_matrix(lh, par["nb_r"], kmax)
    nbb = nb_pmf_matrix(la, par["nb_r"], kmax)
    nbg = independent_grid(nba, nbb)
    grids = {
        "poisson": pois,
        "nb": nbg,
        "bp": bivariate_poisson_grid(lh, la, par["bp_kappa"], kmax),
        "dc": dc_grid(pois, lh, la, par["dc_rho"]),
        "dc_nb": dc_grid(nbg, lh, la, par["dc_nb_rho"]),
    }
    return {k: v / v.sum(axis=(1, 2), keepdims=True) for k, v in grids.items()}


def score_goal_models(
    test: dict[str, F64],
    par: dict[str, float],
    reps: int = 1000,
) -> dict[str, Any]:
    grids = goal_model_grids(test, par)
    out_m = goal_outcomes(test["x"], test["y"])
    probs: dict[str, F64] = {}
    labels: list[tuple[str, str]] = []
    for name, g in grids.items():
        probs[name], labels = goal_event_matrix(g)
    ll = {m: log_loss(probs[m], out_m) for m in grids}
    res: dict[str, Any] = {"matches": int(len(out_m))}
    classes = sorted({c for c, _ in labels})
    for m in grids:
        res[m] = {}
    n = len(out_m)
    for m in grids:
        res[m]["logloss_all"] = float(ll[m].mean())
    for m in grids:
        if m == "poisson":
            continue
        d = ll["poisson"] - ll[m]  # positive = model beats independent Poisson
        entry: dict[str, Any] = {}
        for cls in classes:
            cols = [k for k, (c, _) in enumerate(labels) if c == cls]
            num = d[:, cols].sum(axis=1)
            den = np.full(n, float(len(cols)))
            entry[cls] = list(bootstrap_ratio(num, den, reps))
        rungs: dict[str, Any] = {}
        for k, (c, r) in enumerate(labels):
            rungs[f"{c} | {r}"] = list(bootstrap_ratio(d[:, k], np.ones(n), reps))
        entry["by_rung"] = rungs
        num = d.sum(axis=1)
        entry["all_events"] = list(
            bootstrap_ratio(num, np.full(n, float(d.shape[1])), reps)
        )
        res[m]["gain_vs_poisson"] = entry
    res["base_logloss_by_rung"] = {
        f"{c} | {r}": float(ll["poisson"][:, k].mean())
        for k, (c, r) in enumerate(labels)
    }
    res["observed_rate_by_rung"] = {
        f"{c} | {r}": float(out_m[:, k].mean()) for k, (c, r) in enumerate(labels)
    }
    return res


def subset(d: dict[str, F64], mask: NDArray[np.bool_]) -> dict[str, F64]:
    return {k: v[mask] for k, v in d.items()}


def run_goals(args: argparse.Namespace) -> dict[str, Any]:
    history = load_pickle(Path(args.history))
    ts_a, ts_b, ts_c = (
        ts_of(args.train_from),
        ts_of(args.test_from),
        ts_of(args.test_to),
    )
    out: dict[str, Any] = {
        "windows": {
            "train_from": args.train_from,
            "test_from": args.test_from,
            "test_to": args.test_to,
        }
    }
    centres: dict[float, dict[str, F64]] = {}
    for scale in (1.0, 0.5, 2.0):
        note(f"rating replay alpha x{scale}")
        centres[scale] = rating_centres(history, ts_a, ts_c, scale)
        note(f"  rows {len(centres[scale]['ts'])}")
    base = centres[1.0]
    train = subset(base, base["ts"] < ts_b)
    test = subset(base, base["ts"] >= ts_b)
    par = fit_goal_models(train)
    out["params"] = par
    out["test_matches"] = int(len(test["ts"]))
    note(f"params {par}")
    out["all_fixtures"] = score_goal_models(test, par)
    linked = test["linked"] > 0
    out["linked_only"] = score_goal_models(subset(test, linked), par)
    out["linked_only"]["share_linked"] = float(linked.mean())
    # women / men split is not in the replay rows; by month stability instead
    months = np.array(
        [datetime.fromtimestamp(t, UTC).strftime("%Y-%m") for t in test["ts"]]
    )
    out["by_month_dc_gain"] = {}
    for mo in sorted(set(months.tolist())):
        sel = months == mo
        if sel.sum() < 500:
            continue
        r = score_goal_models(subset(test, sel), par, reps=200)
        out["by_month_dc_gain"][mo] = {
            "matches": int(sel.sum()),
            "dc_all_events": r["dc"]["gain_vs_poisson"]["all_events"],
            "bp_all_events": r["bp"]["gain_vs_poisson"]["all_events"],
            "dc_nb_all_events": r["dc_nb"]["gain_vs_poisson"]["all_events"],
        }
    # time decay: Poisson on the same matches, centres from other smoothing
    td: dict[str, Any] = {}
    for scale in (0.5, 2.0):
        c = centres[scale]
        c_test = subset(c, c["ts"] >= ts_b)
        # score_decay keeps only the matches both replays rate
        td[f"x{scale}"] = score_decay(test, c_test)
    out["time_decay_smoothing"] = td
    return out


def score_decay(ref: dict[str, F64], alt: dict[str, F64]) -> dict[str, Any]:
    """Poisson log-loss gain of an alternative rating smoothing over the
    shipped one, on the matches both rate (matched by timestamp, goals, comp
    and order within the key)."""

    def keyed(d: dict[str, F64]) -> dict[tuple[int, int, int, int, int], int]:
        seen: dict[tuple[int, int, int, int], int] = defaultdict(int)
        out: dict[tuple[int, int, int, int, int], int] = {}
        for i in range(len(d["ts"])):
            base = (int(d["ts"][i]), int(d["comp"][i]), int(d["x"][i]), int(d["y"][i]))
            out[(*base, seen[base])] = i
            seen[base] += 1
        return out

    ka, kb = keyed(ref), keyed(alt)
    common = sorted(set(ka) & set(kb))
    ia = np.array([ka[k] for k in common])
    ib = np.array([kb[k] for k in common])
    a = {k: v[ia] for k, v in ref.items()}
    b = {k: v[ib] for k, v in alt.items()}
    ga = independent_grid(
        poisson_pmf_matrix(a["lh"], GOAL_KMAX), poisson_pmf_matrix(a["la"], GOAL_KMAX)
    )
    gb = independent_grid(
        poisson_pmf_matrix(b["lh"], GOAL_KMAX), poisson_pmf_matrix(b["la"], GOAL_KMAX)
    )
    pa, labels = goal_event_matrix(ga)
    pb, _ = goal_event_matrix(gb)
    o = goal_outcomes(a["x"], a["y"])
    d = log_loss(pa, o) - log_loss(pb, o)  # positive = alt better
    n = len(o)
    res: dict[str, Any] = {
        "matches": n,
        "all_events": list(
            bootstrap_ratio(d.sum(axis=1), np.full(n, float(d.shape[1])))
        ),
    }
    classes = sorted({c for c, _ in labels})
    for cls in classes:
        cols = [k for k, (c, _) in enumerate(labels) if c == cls]
        res[cls] = list(
            bootstrap_ratio(d[:, cols].sum(axis=1), np.full(n, float(len(cols))))
        )
    return res


# --------------------------------------------------------------------------
# cross-market dependence
# --------------------------------------------------------------------------

MATRIX_METRICS = ("goals", "corners", "shots_on_target", "shots", "cards_points")


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    history = load_pickle(Path(args.history))
    ts_a, ts_c = ts_of(args.train_from), ts_of(args.test_to)
    book = fr.RatingBook()
    rows: list[list[float]] = []
    resid: list[list[float]] = []
    names: list[str] = []
    for m in MATRIX_METRICS:
        names += [f"{m}_home", f"{m}_away"]
    need = [f"{m}_for" for m in MATRIX_METRICS]
    note("rating replay for the dependence matrix")
    for r in history:
        if r.ts >= ts_c:
            break
        if r.ts >= ts_a and all(k in r.values for k in need):
            row, res = [], []
            ok = True
            for m in MATRIX_METRICS:
                h, a = r.values[f"{m}_for"]
                # the book's own expectation, also for the metrics SHEET does
                # not blend (UNRATED_MARKETS): a residual needs a centre
                status, lf = book.link(r.home_id, r.away_id, f"{m}_for")
                exp = (
                    book.expected(
                        r.competition_id,
                        r.home_id,
                        r.away_id,
                        f"{m}_for",
                        lf,
                        cross=status != fr.LINKED,
                    )
                    if min(
                        book.team_matches(r.home_id, f"{m}_for"),
                        book.team_matches(r.away_id, f"{m}_for"),
                    )
                    >= fr.MIN_TEAM_MATCHES
                    else None
                )
                ch, ca = exp if exp is not None else (None, None)
                row += [h, a]
                if ch is None or ca is None:
                    ok = False
                    res += [math.nan, math.nan]
                else:
                    res += [h - ch, a - ca]
            rows.append(row)
            resid.append(res if ok else [math.nan] * len(res))
        book.update(r)
    raw = np.asarray(rows)
    res_arr = np.asarray(resid)
    n_res = int((~np.isnan(res_arr).any(axis=1)).sum())
    note(f"matrix rows {len(raw)}; residual rows {n_res}")
    out: dict[str, Any] = {"matches_raw": int(len(raw)), "columns": names}

    def pack(data: F64, cols: list[int], labels: list[str]) -> dict[str, Any]:
        est, lo, hi = corr_matrix_ci(data[:, cols])
        return {
            "labels": labels,
            "corr": est.round(3).tolist(),
            "lo": lo.round(3).tolist(),
            "hi": hi.round(3).tolist(),
            "n": int(len(data)),
        }

    idx = {n: i for i, n in enumerate(names)}
    # match totals
    tot = np.stack(
        [raw[:, 2 * k] + raw[:, 2 * k + 1] for k in range(len(MATRIX_METRICS))], axis=1
    )
    out["totals_raw"] = {
        "labels": list(MATRIX_METRICS),
        **{
            k: v
            for k, v in zip(
                ("corr", "lo", "hi"),
                (lambda e: [x.round(3).tolist() for x in e])(corr_matrix_ci(tot)),
                strict=True,
            )
        },
        "n": int(len(tot)),
    }
    ok_mask = ~np.isnan(res_arr).any(axis=1)
    rtot = np.stack(
        [
            res_arr[ok_mask, 2 * k] + res_arr[ok_mask, 2 * k + 1]
            for k in range(len(MATRIX_METRICS))
        ],
        axis=1,
    )
    out["totals_residual"] = {
        "labels": list(MATRIX_METRICS),
        **{
            k: v
            for k, v in zip(
                ("corr", "lo", "hi"),
                (lambda e: [x.round(3).tolist() for x in e])(corr_matrix_ci(rtot)),
                strict=True,
            )
        },
        "n": int(len(rtot)),
    }
    side_cols = [
        idx[f"{m}_{s}"]
        for m in ("goals", "corners", "shots_on_target")
        for s in ("home", "away")
    ]
    side_labels = [names[i] for i in side_cols]
    out["sides_raw"] = pack(raw, side_cols, side_labels)
    out["sides_residual"] = pack(res_arr[ok_mask], side_cols, side_labels)
    out["all_raw"] = pack(raw, list(range(len(names))), names)
    out["all_residual"] = pack(res_arr[ok_mask], list(range(len(names))), names)
    out["lifts"] = lift_table(raw, idx, args.boot_reps)
    return out


def lift_table(raw: F64, idx: dict[str, int], reps: int) -> list[dict[str, Any]]:
    gh, ga = raw[:, idx["goals_home"]], raw[:, idx["goals_away"]]
    ch, ca = raw[:, idx["corners_home"]], raw[:, idx["corners_away"]]
    sh, sa = raw[:, idx["shots_on_target_home"]], raw[:, idx["shots_on_target_away"]]
    cases: list[tuple[str, Any, Any]] = [
        (
            "total goals > 2.5 & total corners > 9.5",
            (gh + ga > 2.5) * 1.0,
            (ch + ca > 9.5) * 1.0,
        ),
        (
            "total goals > 2.5 & total SoT > 7.5",
            (gh + ga > 2.5) * 1.0,
            (sh + sa > 7.5) * 1.0,
        ),
        (
            "total corners > 9.5 & total SoT > 7.5",
            (ch + ca > 9.5) * 1.0,
            (sh + sa > 7.5) * 1.0,
        ),
        ("home goals > 1.5 & home corners > 5.5", (gh > 1.5) * 1.0, (ch > 5.5) * 1.0),
        ("home goals > 1.5 & home SoT > 4.5", (gh > 1.5) * 1.0, (sh > 4.5) * 1.0),
        ("home corners > 5.5 & home SoT > 4.5", (ch > 5.5) * 1.0, (sh > 4.5) * 1.0),
        (
            "home goals > 0.5 & away goals > 0.5 (BTTS) & total corners > 9.5",
            ((gh > 0.5) & (ga > 0.5)) * 1.0,
            (ch + ca > 9.5) * 1.0,
        ),
        ("home corners > 4.5 & away corners > 3.5", (ch > 4.5) * 1.0, (ca > 3.5) * 1.0),
        ("home goals > 0.5 & away goals > 0.5", (gh > 0.5) * 1.0, (ga > 0.5) * 1.0),
        ("home SoT > 3.5 & away SoT > 2.5", (sh > 3.5) * 1.0, (sa > 2.5) * 1.0),
    ]
    out = []
    n = len(raw)
    rng = np.random.default_rng(13)
    for label, a, b in cases:
        pa, pb, pab = a.mean(), b.mean(), (a * b).mean()
        lifts = np.empty(reps)
        for r in range(reps):
            i = rng.integers(0, n, n)
            lifts[r] = (a[i] * b[i]).mean() / max(a[i].mean() * b[i].mean(), 1e-12)
        out.append(
            {
                "event": label,
                "p_a": float(pa),
                "p_b": float(pb),
                "p_joint": float(pab),
                "lift": float(pab / (pa * pb)),
                "lift_ci": [
                    float(np.percentile(lifts, 2.5)),
                    float(np.percentile(lifts, 97.5)),
                ],
                "n": n,
            }
        )
    return out


# --------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("part", choices=("joint", "goals", "matrix"))
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--out", required=True)
    parser.add_argument("--train-from", default=TRAIN_FROM)
    parser.add_argument("--test-from", default=TEST_FROM)
    parser.add_argument("--test-to", default=TEST_TO)
    parser.add_argument("--bases", nargs="+", default=["corners"])
    parser.add_argument("--max-test", type=int, default=20000)
    parser.add_argument("--boot-reps", type=int, default=500)
    args = parser.parse_args(argv)
    if args.part == "joint":
        result = run_joint(args)
    elif args.part == "goals":
        result = run_goals(args)
    else:
        result = run_matrix(args)
    Path(args.out).write_text(
        json.dumps(result, indent=1, default=float), encoding="utf-8"
    )
    note(f"written {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
