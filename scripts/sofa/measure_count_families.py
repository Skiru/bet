#!/usr/bin/env python3
"""Track A2 - the predictive distribution family of football counting markets.

Read-only evidence (a ``measure_*`` script): nothing here writes a config, a
curve or the database (opened ``mode=ro``). Questions, all out of sample on a
time split, scored at SHEET's own x.5 ladder (``calibrate_from_cache.lines_for``)
by log-loss and Brier against the replayed current estimator:

  1. which family: negative binomial, Poisson, zero-inflated NB, Conway-Maxwell-
     Poisson, a kernel-smoothed empirical distribution, mixtures;
  2. where the dispersion comes from: today's ``centre / mean`` scaling of the
     sample variance (``engine.sheet_predictive_sd``) against one dispersion per
     market, per league, per team (partial pooling of the dispersion parameter);
  3. the referee effect on cards (coverage of ``sofa_event_detail`` reported
     first, the test only if the coverage allows one);
  4. the tails of the ladder: where the current family is wrong.

Only the family changes. The as-of centre, sample and variance of every case are
the replay's: ``calibrate_from_cache.iter_rows`` is run unchanged and its
``_settle_sample`` is replaced by a collector, so the history, the same-
competition goal samples, the K_CENTRE shrink and the friendly exclusion are the
ones SHEET ships with. Not replayed (as in the replay itself): the football
rating in the centre.

    collect   -> <dir>/cases_<market>.npz, <dir>/meta.json   (slow, one process)
    analyse   -> results JSON + markdown tables               (numpy only)
    referee   -> coverage and the (small) referee test

Verdict rule (a suggestion, the decision is the operator's): a family beats the
current one on a market when the match-bootstrap 95% interval of its log-loss
difference and of its Brier difference both exclude zero, both halves of the
test window agree in sign, and the claimed-minus-realised gap of its own
>= 0.70 rungs is not worse.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import pickle
import sqlite3
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.count_dispersion import pooled_alpha  # noqa: E402
from scripts.sofa.count_dispersion_estimation import (  # noqa: E402
    golden_min,
    group_sums,
    lgamma_np,
    mle_alpha,
    moment_stats,
    nb_loglik,
    nb_params,
)

Arr = npt.NDArray[Any]
IArr = npt.NDArray[Any]

GRID = 9  # rungs per case: calibrate_from_cache.lines_for
SAMPLE_PAD = 20  # a pooled total holds up to 2 x SAMPLE_N values
RES_LO, RES_HI = 0.05, 0.95  # engine.outside_model_resolution
PRINT_CONF = 0.70  # CLAUDE.md: a leg prints from confidence 0.70
P_EPS = 1e-6

FAMILIES: tuple[str, ...] = (
    "cur",  # the replayed current estimator (NB for listed metrics, else normal)
    "nb_cur",  # NB on SHEET's variance for every metric
    "poisson",
    "nb_pool",  # var = mu + alpha_m mu^2, alpha per metric
    "nb1_pool",  # var = phi_m mu (quasi-Poisson shape)
    "nb_lg",  # alpha per (metric, league), partial pooling
    "nb_team",  # alpha per (metric, team | league), partial pooling
    "nb_blend",  # var = w var_sample_scaled + (1-w) (mu + alpha_league mu^2)
    "nb_mu",  # alpha_m * shape(mu): dispersion that moves with the centre
    "nb_lgmu",  # alpha_league * shape(mu)
    "norm_pool",  # the engine's floored normal, var = mu + alpha_m mu^2
    "norm_lg",  # the same with the league's alpha
    "zinb",
    "cmp",
    "emp",
    "mix_disp",  # 0.5 nb_cur + 0.5 nb_lg
    "mix_emp",  # 0.5 nb_cur + 0.5 emp
)

TAIL_EDGES = (0.0, 0.02, 0.05, 0.10, 0.20, 0.35, 0.65, 0.80, 0.90, 0.95, 0.98, 1.0)


# ---------------------------------------------------------------------------
# distributions (numpy; no scipy in this project)
# ---------------------------------------------------------------------------

def _arr(x: Any) -> Arr:
    return np.asarray(x, dtype=np.float64)


def erf_fast(x: Arr) -> Arr:
    """Abramowitz-Stegun 7.1.26, |error| < 1.5e-7 (kernel family only)."""
    s = np.sign(x)
    ax = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * ax)
    poly = ((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t
            - 0.284496736) * t + 0.254829592
    return _arr(s * (1.0 - poly * t * np.exp(-ax * ax)))


def phi_fast(x: Arr) -> Arr:
    return 0.5 * (1.0 + erf_fast(x / math.sqrt(2.0)))


_erf_exact = np.frompyfunc(math.erf, 1, 1)


def phi_exact(x: Arr) -> Arr:
    """The engine's normal_cdf, vectorised through math.erf."""
    return np.asarray(
        0.5 * (1.0 + np.asarray(
            _erf_exact(np.asarray(x) / math.sqrt(2.0)), dtype=np.float64
        ))
    )


def nb_pmf(mu: Arr, var: Arr, kmax: int) -> Arr:
    """(N, kmax+1) pmf by the exact recursion (no gamma functions)."""
    mu = np.maximum(mu, 1e-12)
    r, q = nb_params(mu, var)
    pmf = np.empty((len(mu), kmax + 1))
    pmf[:, 0] = np.exp(-r * np.log1p(mu / r))
    for k in range(kmax):
        pmf[:, k + 1] = pmf[:, k] * (k + r) / (k + 1.0) * q
    return pmf


def over_from_pmf(pmf: Arr, thr: IArr) -> Arr:
    """P(X > thr) for thr an (N, G) integer matrix."""
    cdf = np.cumsum(pmf, axis=1)
    idx = np.clip(thr, 0, pmf.shape[1] - 1)
    return np.clip(1.0 - np.take_along_axis(cdf, idx, axis=1), 0.0, 1.0)


def kmax_for(mu: Arr, var: Arr) -> int:
    top = float(np.max(mu + 12.0 * np.sqrt(np.maximum(var, mu)) + 12.0))
    return int(min(600, max(60, math.ceil(top))))


def nb_over(mu: Arr, var: Arr, thr: IArr) -> Arr:
    return over_from_pmf(nb_pmf(mu, var, kmax_for(mu, var)), thr)


def normal_over(centre: Arr, sd: Arr, boundary: Arr, floor: float = -0.5) -> Arr:
    """engine.calc_p_central_raw (OVER, support floor) vectorised."""
    below = phi_exact((boundary - centre[:, None]) / sd[:, None])
    below_floor = phi_exact((floor - centre) / sd)[:, None]
    mass = 1.0 - below_floor
    below = np.maximum(0.0, below - below_floor) / np.maximum(mass, 1e-12)
    return _arr(np.clip(1.0 - below, 0.0, 1.0))


def zinb_loglik(y: Arr, mu: Arr, alpha: float, pi: float) -> Arr:
    mu_nb = mu / (1.0 - pi)
    ll = nb_loglik(y, mu_nb, mu_nb + alpha * mu_nb * mu_nb)
    return np.where(
        y == 0, np.log(pi + (1.0 - pi) * np.exp(ll)), math.log(1.0 - pi) + ll
    )


def zinb_over(mu: Arr, alpha: float, pi: float, thr: IArr) -> Arr:
    mu_nb = mu / (1.0 - pi)
    return (1.0 - pi) * nb_over(mu_nb, mu_nb + alpha * mu_nb * mu_nb, thr)


# Conway-Maxwell-Poisson, mean-matched: pmf(k) ~ lambda^k / (k!)^nu with lambda
# chosen per grid mean; a case reads the table by linear interpolation in log mu.
CMP_K = 400
CMP_GRID = np.exp(np.linspace(math.log(0.02), math.log(90.0), 220))


@dataclass
class CmpTable:
    nu: float
    pmf: Arr  # (G, K+1)
    cdf: Arr


def cmp_table(nu: float) -> CmpTable:
    k = np.arange(CMP_K + 1, dtype=np.float64)
    log_fact = lgamma_np(k + 1.0) * nu
    lo = np.full(len(CMP_GRID), -25.0)
    hi = np.full(len(CMP_GRID), 15.0)

    def mean_of(loglam: Arr) -> Arr:
        e = k[None, :] * loglam[:, None] - log_fact[None, :]
        e -= e.max(axis=1, keepdims=True)
        w = np.exp(e)
        return np.asarray((w * k[None, :]).sum(axis=1) / w.sum(axis=1))

    for _ in range(60):
        mid = 0.5 * (lo + hi)
        too_low = mean_of(mid) < CMP_GRID
        lo = np.where(too_low, mid, lo)
        hi = np.where(too_low, hi, mid)
    loglam = 0.5 * (lo + hi)
    e = k[None, :] * loglam[:, None] - log_fact[None, :]
    e -= e.max(axis=1, keepdims=True)
    w = np.exp(e)
    pmf = w / w.sum(axis=1, keepdims=True)
    return CmpTable(nu, pmf, np.cumsum(pmf, axis=1))


def _cmp_weights(mu: Arr) -> tuple[IArr, Arr]:
    pos = np.interp(
        np.log(np.clip(mu, CMP_GRID[0], CMP_GRID[-1])),
        np.log(CMP_GRID), np.arange(len(CMP_GRID), dtype=np.float64),
    )
    lo = np.minimum(pos.astype(np.int64), len(CMP_GRID) - 2)
    return lo, pos - lo


def cmp_over(table: CmpTable, mu: Arr, thr: IArr) -> Arr:
    lo, w = _cmp_weights(mu)
    idx = np.clip(thr, 0, CMP_K)
    c_lo = np.take_along_axis(table.cdf[lo], idx, axis=1)
    c_hi = np.take_along_axis(table.cdf[lo + 1], idx, axis=1)
    return _arr(
        np.clip(1.0 - ((1.0 - w)[:, None] * c_lo + w[:, None] * c_hi), 0.0, 1.0)
    )


def cmp_loglik(table: CmpTable, y: Arr, mu: Arr) -> Arr:
    lo, w = _cmp_weights(mu)
    yi = np.clip(y.astype(np.int64), 0, CMP_K)
    p = (1.0 - w) * table.pmf[lo, yi] + w * table.pmf[lo + 1, yi]
    return _arr(np.log(np.maximum(p, 1e-300)))


def emp_over(
    samp: Arr, n: Arr, centre: Arr, mean: Arr, sd: Arr, thr: IArr, c: float
) -> Arr:
    """Kernel-smoothed empirical: each sample value, moved by centre - mean, is a
    normal of bandwidth h = c 0.9 sd n^-0.2 (floor 0.35) discretised on the
    integers; mass below -0.5 is dropped and the rest renormalised (the engine's
    support floor)."""
    h = np.maximum(c * 0.9 * sd * n ** -0.2, 0.35)
    shifted = samp + (centre - mean)[:, None]
    valid = ~np.isnan(samp)
    cnt = valid.sum(axis=1).astype(np.float64)
    bound = thr.astype(np.float64) + 0.5  # P(X <= thr) = P(Z < thr + 0.5)
    z = (bound[:, :, None] - shifted[:, None, :]) / h[:, None, None]
    cdf = np.where(valid[:, None, :], phi_fast(z), 0.0).sum(axis=2) / cnt[:, None]
    zf = (-0.5 - shifted) / h[:, None]
    floor = np.where(valid, phi_fast(zf), 0.0).sum(axis=1) / cnt
    cdf = np.maximum(cdf - floor[:, None], 0.0) / np.maximum(1.0 - floor, 1e-12)[
        :, None
    ]
    return _arr(np.clip(1.0 - cdf, 0.0, 1.0))


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

@dataclass
class Cases:
    ts: Arr
    ev: IArr
    comp: IArr
    team: IArr
    y: Arr
    n: Arr
    mean: Arr
    var: Arr
    centre: Arr
    samp: Arr  # (N, SAMPLE_PAD), NaN padded

    def __len__(self) -> int:
        return int(len(self.y))

    def take(self, mask: npt.NDArray[np.bool_] | IArr) -> Cases:
        return Cases(
            self.ts[mask], self.ev[mask], self.comp[mask], self.team[mask],
            self.y[mask], self.n[mask], self.mean[mask], self.var[mask],
            self.centre[mask], self.samp[mask],
        )


def load_cases(path: Path) -> Cases:
    z = np.load(path)
    return Cases(
        z["ts"].astype(np.float64), z["ev"].astype(np.int64),
        z["comp"].astype(np.int64), z["team"].astype(np.int64),
        z["y"].astype(np.float64), z["n"].astype(np.float64),
        z["mean"].astype(np.float64), z["var"].astype(np.float64),
        z["centre"].astype(np.float64), z["samp"].astype(np.float64),
    )


def rung_grid(centre: Arr) -> tuple[Arr, IArr]:
    """calibrate_from_cache.lines_for, vectorised: (lines, floor(lines))."""
    lowest = np.maximum(0, np.floor(centre).astype(np.int64) - 4)
    thr = lowest[:, None] + np.arange(GRID, dtype=np.int64)[None, :]
    return thr + 0.5, thr


def current_var(c: Cases) -> Arr:
    """engine.sheet_predictive_sd squared, football: the sample's variance
    scaled by centre / mean, floored at the mean (Poisson), times (1 + 1/n)."""
    scale = c.centre / c.mean
    return np.maximum(c.var * scale, c.mean * scale) * (1.0 + 1.0 / c.n)


def current_over(market: str, c: Cases, thr: IArr, nb_listed: bool) -> Arr:
    var = current_var(c)
    if nb_listed:
        return nb_over(c.centre, var, thr)
    return normal_over(c.centre, np.sqrt(var), thr + 0.5)


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------

@dataclass
class Fit:
    alpha: float = 0.1
    phi: float = 1.5
    zi_pi: float = 0.0
    zi_alpha: float = 0.1
    cmp_nu: float = 1.0
    alpha_mom: float = 0.1
    bmean: float = 1.0
    comp_ab: dict[int, tuple[float, float]] = field(default_factory=dict)
    shape_x: Arr = field(default_factory=lambda: np.ones(1))
    shape_r: Arr = field(default_factory=lambda: np.ones(1))
    alpha_s: float = 0.1
    alpha_mom_s: float = 0.1
    bmean_s: float = 1.0
    comp_ab_s: dict[int, tuple[float, float]] = field(default_factory=dict)
    team_ab: dict[int, tuple[float, float]] = field(default_factory=dict)
    cmp: CmpTable | None = None


@dataclass
class Hyper:
    kc: float = 100.0
    kc_mu: float = 100.0
    kt: float = 100.0
    blend_w: float = 0.5
    emp_c: float = 1.0


def _sub(c: Cases, k: int, seed: int = 0) -> Cases:
    if len(c) <= k:
        return c
    idx = np.sort(np.random.default_rng(seed).choice(len(c), k, replace=False))
    return c.take(idx)


def fit_family_params(train: Cases, mle_cases: int = 60000) -> Fit:
    """Per-metric parameters from the training cases alone."""
    fit = Fit()
    mu = train.centre
    resid = (train.y - mu) ** 2 - mu
    b = mu * mu
    fit.alpha_mom, fit.bmean, fit.comp_ab = moment_stats(train.comp, mu, train.y)
    fit.team_ab = group_sums(train.team, resid, b, skip=0)

    # the dispersion's own dependence on the centre: moment alpha in 8 centre
    # quantile bins, as a ratio to the pooled one, interpolated at the bin means
    edges = np.quantile(mu, np.linspace(0.0, 1.0, 9))
    bins = np.clip(np.searchsorted(edges[1:-1], mu, side="right"), 0, 7)
    xs, rs = [], []
    for k in range(8):
        sel = bins == k
        if sel.sum() < 50:
            continue
        xs.append(float(mu[sel].mean()))
        rs.append(float(np.clip(
            resid[sel].sum() / b[sel].sum() / fit.alpha_mom, 0.2, 5.0)))
    if not xs:  # too few cases for bins: a flat shape
        xs, rs = [float(mu.mean())], [1.0]
    fit.shape_x, fit.shape_r = np.array(xs), np.array(rs)
    shape = np.interp(mu, fit.shape_x, fit.shape_r)
    b_s = b * shape
    fit.alpha_mom_s = max(1e-4, float(resid.sum() / b_s.sum()))
    fit.bmean_s = float(b_s.mean())
    fit.comp_ab_s = group_sums(train.comp, resid, b_s)

    s = _sub(train, mle_cases)
    y, m = s.y, s.centre
    sh = np.interp(m, fit.shape_x, fit.shape_r)

    def nll_alpha_s(la: float) -> float:
        a = math.exp(la)
        return -float(nb_loglik(y, m, m + a * sh * m * m).sum())

    fit.alpha_s = math.exp(golden_min(nll_alpha_s, math.log(1e-3), math.log(3.0)))

    fit.alpha = mle_alpha(y, m)

    def nll_phi(lp: float) -> float:
        ph = 1.0 + math.exp(lp)
        return -float(nb_loglik(y, m, m * ph).sum())

    fit.phi = 1.0 + math.exp(golden_min(nll_phi, math.log(1e-3), math.log(12.0)))

    best = (float("inf"), 0.0, fit.alpha)
    for pi in (0.005, 0.01, 0.02, 0.04, 0.07, 0.11, 0.16):
        def nll_zi(la: float, pi: float = pi) -> float:
            return -float(zinb_loglik(y, m, math.exp(la), pi).sum())

        la = golden_min(nll_zi, math.log(1e-3), math.log(3.0), it=18)
        v = nll_zi(la)
        if v < best[0]:
            best = (v, pi, math.exp(la))
    base = -float(nb_loglik(y, m, m + fit.alpha * m * m).sum())
    if best[0] < base:
        fit.zi_pi, fit.zi_alpha = best[1], best[2]
    else:  # zero inflation does not pay: the family degenerates to the NB
        fit.zi_pi, fit.zi_alpha = 0.0, fit.alpha

    bestn = (float("inf"), 1.0)
    for nu in (0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4):
        tab = cmp_table(nu)
        v = -float(cmp_loglik(tab, y, m).sum())
        if v < bestn[0]:
            bestn = (v, nu)
    fit.cmp_nu = bestn[1]
    fit.cmp = cmp_table(fit.cmp_nu)
    return fit


def alpha_league(c: Cases, fit: Fit, kc: float, shaped: bool = False) -> Arr:
    """alpha of (metric, league): the league's moment estimate pooled toward the
    metric's alpha with kc cases' worth of weight (additive sufficient
    statistics A = sum((y-mu)^2 - mu), B = sum mu^2; shaped: B = sum shape(mu)
    mu^2, the alpha then multiplies shape(mu))."""
    if shaped:
        ab, mom, mle, bmean = fit.comp_ab_s, fit.alpha_mom_s, fit.alpha_s, fit.bmean_s
    else:
        ab, mom, mle, bmean = fit.comp_ab, fit.alpha_mom, fit.alpha, fit.bmean
    uniq, inv = np.unique(c.comp, return_inverse=True)
    vals = np.empty(len(uniq))
    for i, u in enumerate(uniq):
        a, b = ab.get(int(u), (0.0, 0.0))
        vals[i] = pooled_alpha(a, b, mom=mom, mle=mle, bmean=bmean, kc=kc)
    return vals[inv]


def alpha_team(c: Cases, fit: Fit, kc: float, kt: float) -> Arr:
    """alpha of a team, pooled toward its league's alpha (totals: the league's)."""
    base = alpha_league(c, fit, kc)
    rho = fit.alpha / fit.alpha_mom
    kappa = kt * fit.bmean
    uniq, inv = np.unique(c.team, return_inverse=True)
    out = base.copy()
    for i, u in enumerate(uniq):
        if u == 0:
            continue
        a, b = fit.team_ab.get(int(u), (0.0, 0.0))
        rows = inv == i
        out[rows] = np.maximum(
            rho * (a + kappa * base[rows] / rho) / (b + kappa), 1e-4
        )
    return out


def family_over(
    name: str, market: str, nb_listed: bool, c: Cases, thr: IArr,
    fit: Fit, hyper: Hyper,
) -> Arr:
    """P(X > floor(line)) for one family, an (N, GRID) matrix."""
    mu = c.centre
    if name == "cur":
        return current_over(market, c, thr, nb_listed)
    if name == "nb_cur":
        return nb_over(mu, current_var(c), thr)
    if name == "poisson":
        return nb_over(mu, mu, thr)
    if name == "nb_pool":
        return nb_over(mu, mu + fit.alpha * mu * mu, thr)
    if name == "nb1_pool":
        return nb_over(mu, mu * fit.phi, thr)
    if name == "nb_lg":
        a = alpha_league(c, fit, hyper.kc)
        return nb_over(mu, mu + a * mu * mu, thr)
    if name == "nb_team":
        a = alpha_team(c, fit, hyper.kc, hyper.kt)
        return nb_over(mu, mu + a * mu * mu, thr)
    if name == "nb_blend":
        a = alpha_league(c, fit, hyper.kc)
        w = hyper.blend_w
        var = w * current_var(c) + (1.0 - w) * (mu + a * mu * mu)
        return nb_over(mu, var, thr)
    if name == "nb_mu":
        sh = np.interp(mu, fit.shape_x, fit.shape_r)
        return nb_over(mu, mu + fit.alpha_s * sh * mu * mu, thr)
    if name == "nb_lgmu":
        sh = np.interp(mu, fit.shape_x, fit.shape_r)
        a = alpha_league(c, fit, hyper.kc_mu, shaped=True)
        return nb_over(mu, mu + a * sh * mu * mu, thr)
    if name == "norm_pool":
        sd = np.sqrt(mu + fit.alpha * mu * mu)
        return normal_over(mu, sd, thr + 0.5)
    if name == "norm_lg":
        sd = np.sqrt(mu + alpha_league(c, fit, hyper.kc) * mu * mu)
        return normal_over(mu, sd, thr + 0.5)
    if name == "zinb":
        return zinb_over(mu, fit.zi_alpha, fit.zi_pi, thr)
    if name == "cmp":
        assert fit.cmp is not None
        return cmp_over(fit.cmp, mu, thr)
    if name == "emp":
        return emp_over(
            c.samp, c.n, c.centre, c.mean, np.sqrt(c.var), thr, hyper.emp_c
        )
    if name == "mix_disp":
        return 0.5 * (
            family_over("nb_cur", market, nb_listed, c, thr, fit, hyper)
            + family_over("nb_lg", market, nb_listed, c, thr, fit, hyper)
        )
    if name == "mix_emp":
        return 0.5 * (
            family_over("nb_cur", market, nb_listed, c, thr, fit, hyper)
            + family_over("emp", market, nb_listed, c, thr, fit, hyper)
        )
    raise ValueError(name)


def chunks(n: int, size: int) -> Iterator[slice]:
    for start in range(0, n, size):
        yield slice(start, min(n, start + size))


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def rung_losses(p_over: Arr, over_won: npt.NDArray[np.bool_]) -> tuple[Arr, Arr]:
    """(Brier, log-loss) of OVER probabilities per rung. UNDER is the mirror
    image of the same rung and scores identically, so it is not counted twice."""
    p = np.clip(p_over, P_EPS, 1.0 - P_EPS)
    y = over_won.astype(np.float64)
    return (p - y) ** 2, -(y * np.log(p) + (1.0 - y) * np.log(1.0 - p))


@dataclass
class Scored:
    """Per-case sums of one family over the rungs the CURRENT estimator may
    price (p inside [RES_LO, RES_HI]), plus the >= PRINT_CONF region of its own
    probabilities and the unconditional tail / offset tallies."""

    brier: Arr
    ll: Arr
    cnt: Arr
    pr_n: Arr
    pr_claim: Arr
    pr_won: Arr
    tail: Arr  # (len(TAIL_EDGES)-1, 3): n, sum p, sum won
    offset: Arr  # (GRID, 3)


def score_families(
    names: tuple[str, ...], market: str, nb_listed: bool, c: Cases,
    fit: Fit, hyper: Hyper, size: int = 30000,
) -> dict[str, Scored]:
    n = len(c)
    out = {
        f: Scored(
            np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n),
            np.zeros(n), np.zeros((len(TAIL_EDGES) - 1, 3)), np.zeros((GRID, 3)),
        )
        for f in names
    }
    edges = np.array(TAIL_EDGES)
    for sl in chunks(n, size):
        cc = c.take(np.arange(n)[sl])
        lines, thr = rung_grid(cc.centre)
        won = cc.y[:, None] > lines
        p_cur = current_over(market, cc, thr, nb_listed)
        valid = (p_cur >= RES_LO) & (p_cur <= RES_HI)
        for f in names:
            p = p_cur if f == "cur" else family_over(
                f, market, nb_listed, cc, thr, fit, hyper
            )
            br, ll = rung_losses(p, won)
            s = out[f]
            s.brier[sl] = (br * valid).sum(axis=1)
            s.ll[sl] = (ll * valid).sum(axis=1)
            s.cnt[sl] = valid.sum(axis=1)
            side_p = np.where(p >= 0.5, p, 1.0 - p)
            side_won = np.where(p >= 0.5, won, ~won)
            region = (side_p >= PRINT_CONF) & (side_p <= RES_HI)
            s.pr_n[sl] = region.sum(axis=1)
            s.pr_claim[sl] = (side_p * region).sum(axis=1)
            s.pr_won[sl] = (side_won * region).sum(axis=1)
            bins = np.clip(np.searchsorted(edges, p.ravel(), side="right") - 1,
                           0, len(edges) - 2)
            k = len(edges) - 1
            s.tail[:, 0] += np.bincount(bins, minlength=k)
            s.tail[:, 1] += np.bincount(bins, weights=p.ravel(), minlength=k)
            s.tail[:, 2] += np.bincount(bins, weights=won.ravel(), minlength=k)
            s.offset[:, 0] += p.shape[0]
            s.offset[:, 1] += p.sum(axis=0)
            s.offset[:, 2] += won.sum(axis=0)
    return out


def total_ll(scored: Scored) -> float:
    return float(scored.ll.sum() / max(1.0, scored.cnt.sum()))


# ---------------------------------------------------------------------------
# tuning on the validation slice, evaluation on the test slice
# ---------------------------------------------------------------------------

def tune_hyper(
    market: str, nb_listed: bool, train: Cases, val: Cases, fit: Fit
) -> Hyper:
    """Pick the hyper-parameters (pooling weights, blend, bandwidth) by the
    validation log-loss of the family they belong to. Never sees the test."""
    hyper = Hyper()
    val = _sub(val, 40000, seed=1)
    if len(val) == 0:
        return hyper

    def ll(fam: str, h: Hyper) -> float:
        return total_ll(score_families((fam,), market, nb_listed, val, fit, h)[fam])

    hyper.kc = min(
        (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0),
        key=lambda k: ll("nb_lg", Hyper(kc=k)),
    )
    hyper.kc_mu = min(
        (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0),
        key=lambda k: ll("nb_lgmu", Hyper(kc_mu=k)),
    )
    hyper.kt = min(
        (10.0, 30.0, 100.0, 300.0, 1000.0, 3000.0, 10000.0),
        key=lambda k: ll("nb_team", Hyper(kc=hyper.kc, kt=k)),
    )
    hyper.blend_w = min(
        (0.0, 0.25, 0.5, 0.75),
        key=lambda w: ll("nb_blend", Hyper(kc=hyper.kc, blend_w=w)),
    )
    hyper.emp_c = min(
        (0.5, 1.0, 1.5), key=lambda c: ll("emp", Hyper(emp_c=c))
    )
    return hyper


def bootstrap_deltas(
    ev: IArr, base: Scored, others: dict[str, Scored], reps: int, seed: int = 7
) -> dict[str, dict[str, list[float]]]:
    """Match-bootstrap (events resampled with Poisson(1) weights) of
    family - base: log-loss and Brier per rung, and the >= PRINT_CONF region's
    claimed - realised gap. Returns {family: {metric: [point, lo, hi]}}."""
    uniq, inv = np.unique(ev, return_inverse=True)
    e = len(uniq)

    def per_event(x: Arr) -> Arr:
        return np.asarray(np.bincount(inv, weights=x, minlength=e))

    cnt_b = per_event(base.cnt)
    cols: dict[str, Arr] = {"cnt": cnt_b}
    for name, s in others.items():
        cols[f"{name}:ll"] = per_event(s.ll)
        cols[f"{name}:br"] = per_event(s.brier)
        cols[f"{name}:cnt"] = per_event(s.cnt)
        cols[f"{name}:prn"] = per_event(s.pr_n)
        cols[f"{name}:prc"] = per_event(s.pr_claim)
        cols[f"{name}:prw"] = per_event(s.pr_won)
    cols["b:ll"] = per_event(base.ll)
    cols["b:br"] = per_event(base.brier)
    cols["b:prn"] = per_event(base.pr_n)
    cols["b:prc"] = per_event(base.pr_claim)
    cols["b:prw"] = per_event(base.pr_won)
    keys = list(cols)
    mat = np.stack([cols[k] for k in keys], axis=1)
    rng = np.random.default_rng(seed)
    point = np.concatenate([[1.0], np.zeros(0)])
    w_all = np.vstack([np.ones((1, e)), rng.poisson(1.0, size=(reps, e)).astype(float)])
    sums = w_all @ mat  # (reps+1, K)
    del point
    ix = {k: i for i, k in enumerate(keys)}
    res: dict[str, dict[str, list[float]]] = {}
    for name in others:
        d_ll = sums[:, ix[f"{name}:ll"]] / np.maximum(sums[:, ix[f"{name}:cnt"]], 1) \
            - sums[:, ix["b:ll"]] / np.maximum(sums[:, ix["cnt"]], 1)
        d_br = sums[:, ix[f"{name}:br"]] / np.maximum(sums[:, ix[f"{name}:cnt"]], 1) \
            - sums[:, ix["b:br"]] / np.maximum(sums[:, ix["cnt"]], 1)
        n = np.maximum(sums[:, ix[f"{name}:prn"]], 1)
        gap = (sums[:, ix[f"{name}:prc"]] - sums[:, ix[f"{name}:prw"]]) / n

        def ci(x: Arr) -> list[float]:
            return [float(x[0]), float(np.quantile(x[1:], 0.025)),
                    float(np.quantile(x[1:], 0.975))]

        res[name] = {"d_ll": ci(d_ll), "d_brier": ci(d_br), "gap_print": ci(gap)}
    nb = np.maximum(sums[:, ix["b:prn"]], 1)
    gap_b = (sums[:, ix["b:prc"]] - sums[:, ix["b:prw"]]) / nb
    res["cur"] = {"gap_print": [float(gap_b[0]), float(np.quantile(gap_b[1:], 0.025)),
                                float(np.quantile(gap_b[1:], 0.975))]}
    return res


def verdict(
    d: dict[str, list[float]], half_signs: tuple[float, float], gap_cur: float,
    gap_fam: float, n_events: int,
) -> str:
    if n_events < 300:
        return "INCONCLUSIVE"
    ll, br = d["d_ll"], d["d_brier"]
    better = ll[2] < 0 and br[2] < 0 and half_signs[0] < 0 and half_signs[1] < 0
    worse = ll[1] > 0 and br[1] > 0
    if better and abs(gap_fam) <= abs(gap_cur) + 0.005:
        return "BETTER"
    if worse:
        return "WORSE"
    return "NO_DIFFERENCE"


def run_market(
    market: str, c: Cases, test_ts: float, val_ts: float, reps: int,
    names: tuple[str, ...] = FAMILIES, nb_listed: bool = False,
) -> dict[str, Any]:
    train_all = c.take(c.ts < test_ts)
    train_fit = c.take(c.ts < val_ts)
    val = c.take((c.ts >= val_ts) & (c.ts < test_ts))
    test = c.take(c.ts >= test_ts)
    out: dict[str, Any] = {
        "market": market, "nb_listed": nb_listed,
        "n_train": len(train_all), "n_val": len(val), "n_test": len(test),
        "n_test_events": int(len(np.unique(test.ev))),
    }
    if len(test) < 500 or len(train_fit) < 2000:
        out["status"] = "TOO_THIN"
        return out
    fit1 = fit_family_params(train_fit)
    hyper = tune_hyper(market, nb_listed, train_fit, val, fit1) if len(val) else Hyper()
    fit = fit_family_params(train_all)
    scored = score_families(names, market, nb_listed, test, fit, hyper)
    others = {k: v for k, v in scored.items() if k != "cur"}
    boots = bootstrap_deltas(test.ev, scored["cur"], others, reps)
    vs_pool = bootstrap_deltas(
        test.ev, scored["nb_pool"],
        {k: scored[k] for k in ("nb_lg", "nb_team", "nb_mu", "nb_lgmu", "cmp",
                                "zinb", "nb1_pool", "norm_pool", "norm_lg")},
        reps, seed=11,
    )
    mid = float(np.median(test.ts))
    halves: dict[str, tuple[float, float]] = {}
    for f, s in others.items():
        pair = []
        for part in (test.ts < mid, test.ts >= mid):
            cnt_f = max(1.0, s.cnt[part].sum())
            cnt_b = max(1.0, scored["cur"].cnt[part].sum())
            pair.append(float(s.ll[part].sum() / cnt_f
                              - scored["cur"].ll[part].sum() / cnt_b))
        halves[f] = (pair[0], pair[1])
    fams: dict[str, Any] = {}
    for f, s in scored.items():
        entry: dict[str, Any] = {
            "ll": total_ll(s),
            "brier": float(s.brier.sum() / max(1.0, s.cnt.sum())),
            "print_n": int(s.pr_n.sum()),
            "print_claim": float(s.pr_claim.sum() / max(1.0, s.pr_n.sum())),
            "print_real": float(s.pr_won.sum() / max(1.0, s.pr_n.sum())),
            "tail": s.tail.tolist(),
            "offset": s.offset.tolist(),
        }
        if f != "cur":
            entry.update(boots[f])
            entry["half_d_ll"] = list(halves[f])
            entry["verdict"] = verdict(
                boots[f], halves[f], boots["cur"]["gap_print"][0],
                boots[f]["gap_print"][0], out["n_test_events"],
            )
        else:
            entry["gap_print"] = boots["cur"]["gap_print"]
        fams[f] = entry
    for f, e in vs_pool.items():
        if f != "cur":
            fams[f]["vs_pool"] = {"d_ll": e["d_ll"], "d_brier": e["d_brier"]}
    out["families"] = fams
    out["hyper"] = vars(hyper)
    out["fit"] = {
        "alpha": fit.alpha, "phi": fit.phi, "zinb_pi": fit.zi_pi,
        "zinb_alpha": fit.zi_alpha, "cmp_nu": fit.cmp_nu,
        "alpha_moment": fit.alpha_mom,
    }
    out["status"] = "OK"
    return out


# ---------------------------------------------------------------------------
# league heterogeneity of the dispersion
# ---------------------------------------------------------------------------

FOCUS_LEAGUES = (17, 188, 8, 35, 23, 202, 20, 40, 325)  # PL, Besta deild, ...


def alpha_with_ci(
    resid: Arr, b: Arr, ev: IArr, reps: int = 300, seed: int = 9
) -> list[float]:
    """Moment alpha of a league with a match-bootstrap interval."""
    uniq, inv = np.unique(ev, return_inverse=True)
    ra = np.bincount(inv, weights=resid, minlength=len(uniq))
    rb = np.bincount(inv, weights=b, minlength=len(uniq))
    w = np.random.default_rng(seed).poisson(1.0, size=(reps, len(uniq)))
    boot = (w @ ra) / np.maximum(w @ rb, 1e-12)
    return [float(ra.sum() / rb.sum()), float(np.quantile(boot, 0.025)),
            float(np.quantile(boot, 0.975))]


def league_dispersion(
    c: Cases, test_ts: float, names: dict[int, str], min_cases: int = 400
) -> dict[str, Any]:
    """Moment alpha per league on the training cases, with the split-half
    reliability across leagues (event-id parity): if the dispersion were one
    number the halves would not correlate beyond what the sampling noise says."""
    tr = c.take(c.ts < test_ts)
    resid = (tr.y - tr.centre) ** 2 - tr.centre
    b = tr.centre ** 2
    rows = []
    halves: list[tuple[float, float]] = []
    for comp in np.unique(tr.comp):
        m = tr.comp == comp
        if m.sum() < min_cases:
            continue
        even = m & (tr.ev % 2 == 0)
        odd = m & (tr.ev % 2 == 1)
        a_all = float(resid[m].sum() / b[m].sum())
        a_e = float(resid[even].sum() / max(b[even].sum(), 1e-9))
        a_o = float(resid[odd].sum() / max(b[odd].sum(), 1e-9))
        halves.append((a_e, a_o))
        rows.append({"comp": int(comp), "name": names.get(int(comp), str(comp)),
                     "cases": int(m.sum()), "alpha": a_all})
    arr = np.array(halves) if halves else np.zeros((0, 2))
    corr = float(np.corrcoef(arr[:, 0], arr[:, 1])[0, 1]) if len(arr) > 3 else None
    alphas = np.array([r["alpha"] for r in rows]) if rows else np.zeros(0)
    pooled = float(resid.sum() / b.sum())
    rows.sort(key=lambda r: -float(r["cases"]))  # type: ignore[arg-type]
    focus = []
    for comp in FOCUS_LEAGUES:
        m = tr.comp == comp
        if m.sum() >= 100:
            focus.append({
                "comp": comp, "name": names.get(comp, str(comp)),
                "cases": int(m.sum()), "mean_centre": float(tr.centre[m].mean()),
                "alpha": alpha_with_ci(resid[m], b[m], tr.ev[m]),
            })
    return {
        "leagues": len(rows), "pooled_alpha_moment": pooled,
        "split_half_corr": corr,
        "alpha_quantiles": (
            [float(x) for x in np.quantile(alphas, [0.05, 0.25, 0.5, 0.75, 0.95])]
            if len(alphas) else []
        ),
        "top": rows[:25], "focus": focus,
    }


# ---------------------------------------------------------------------------
# collect (slow; reads the database read-only)
# ---------------------------------------------------------------------------

def _lean(event: dict[str, Any], kind: Any) -> dict[str, Any]:
    """Only the keys the football replay reads; whole slim events of ~1M
    matches held 8+ GB (measure_pooling._lean, the same list)."""
    def keep(d: Any, keys: tuple[str, ...]) -> dict[str, Any]:
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


def extract_played(db_path: Path) -> tuple[list[Any], dict[int, str]]:
    """calibrate_from_cache.load_cache for football, with lean events and a
    read-only connection: the same finished-copy rule, one listing per match,
    completed matches only, the same match_values."""
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
            return _lean(event, match_kind(event, "football"))

        identity = listed_events_by_id(conn, finished_copy, kinds=None)
        values_by_event: dict[int, dict[str, tuple[float, float]]] = {}
        for event_id, st, inc in conn.execute(
            "SELECT sofascore_event_id, statistics_json, incidents_json "
            "FROM sofa_event_stats WHERE status_type = 'finished'"
        ):
            event = identity.get(event_id)
            if event is None:
                continue
            values_by_event[int(event_id)] = cc.match_values(
                event, "football", st, inc
            )
    finally:
        conn.close()
    played: list[Any] = []
    for event in one_listing_per_match(list(identity.values())):
        if not is_completed_event(event):
            continue
        home = (event.get("homeTeam") or {}).get("id")
        away = (event.get("awayTeam") or {}).get("id")
        started = event.get("startTimestamp")
        if not home or not away or not started:
            continue
        ut = (event.get("tournament") or {}).get("uniqueTournament") or {}
        values = values_by_event.get(int(event["id"]))
        if values is None:  # goals still come off the listing
            values = cc.match_values(event, "football", None, None)
        if not values:
            continue
        comp = ut.get("id")
        if comp:
            cat = ((event.get("tournament") or {}).get("category") or {}).get("name")
            names[int(comp)] = f"{ut.get('name')} ({cat})"
        played.append(cc.Played(
            event_id=int(event["id"]), timestamp=int(started), home_id=int(home),
            away_id=int(away), sport="football",
            competition_id=int(comp) if comp else None, values=values,
            kind=event["_kind"],
        ))
    played.sort(key=lambda p: p.timestamp)
    return played, names


class Collector:
    """Stands in for calibrate_from_cache._settle_sample: it is handed exactly
    what the replay settles with and keeps the case instead of rows."""

    FIELDS = ("ts", "ev", "comp", "team", "y", "n", "mean", "var", "centre")

    def __init__(self, cc: Any, baselines: dict[str, Any]) -> None:
        self.cc = cc
        self.cols: dict[str, dict[str, array.array[float]]] = {}
        self.samp: dict[str, array.array[float]] = {}

    def __call__(
        self, match: Any, market: str, subject: str, actual: float,
        sample: list[float], baselines: dict[str, Any],
        engine_constants: dict[str, Any], rating_p: Any = None,
    ) -> list[Any]:
        import statistics

        n = len(sample)
        if n < self.cc.MIN_SAMPLE or all(v == 0.0 for v in sample):
            return []
        mean = statistics.mean(sample)
        variance = statistics.variance(sample) if n > 1 else 0.0
        centre = self.cc.shrunk_centre(
            match, market, sample, baselines, engine_constants
        )
        if centre <= 0 or mean <= 0:
            return []
        cols = self.cols.setdefault(
            market, {f: array.array("d") for f in self.FIELDS}
        )
        row = (
            match.timestamp, match.event_id, match.competition_id or 0,
            int(subject) if subject else 0, actual, n, mean, variance, centre,
        )
        for f, v in zip(self.FIELDS, row, strict=True):
            cols[f].append(float(v))
        pad = list(sample[:SAMPLE_PAD]) + [math.nan] * (SAMPLE_PAD - n)
        self.samp.setdefault(market, array.array("f")).extend(pad)
        return []

    def save(self, out_dir: Path) -> dict[str, int]:
        sizes: dict[str, int] = {}
        for market, cols in self.cols.items():
            arrays = {f: np.frombuffer(cols[f], dtype=np.float64) for f in self.FIELDS}
            samp = np.frombuffer(self.samp[market], dtype=np.float32).reshape(
                -1, SAMPLE_PAD
            )
            np.savez(out_dir / f"cases_{market}.npz", samp=samp, **arrays)  # type: ignore[arg-type]
            sizes[market] = int(len(arrays["y"]))
        return sizes


def cmd_collect(args: argparse.Namespace) -> int:
    from scripts.sofa import calibrate_from_cache as cc

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pkl = out / "played.pkl"
    t0 = time.time()
    if pkl.exists() and not args.refresh:
        played, names = pickle.loads(pkl.read_bytes())
    else:
        played, names = extract_played(Path(args.db))
        pkl.write_bytes(pickle.dumps((played, names)))
    print(f"played {len(played)} matches ({time.time() - t0:.0f}s)", flush=True)
    baselines = cc.load_baselines()
    collector = Collector(cc, baselines)
    cc._settle_sample = collector
    count = 0
    for _ in cc.iter_rows(played, baselines):
        count += 1
    sizes = collector.save(out)
    (out / "meta.json").write_text(json.dumps(
        {"names": {str(k): v for k, v in names.items()}, "sizes": sizes,
         "matches": len(played),
         "first_ts": played[0].timestamp, "last_ts": played[-1].timestamp},
        ensure_ascii=False, indent=1))
    print(f"cases per market: {sizes} ({time.time() - t0:.0f}s)", flush=True)
    return 0


# ---------------------------------------------------------------------------
# analyse
# ---------------------------------------------------------------------------

def _ts(day: str) -> float:
    return datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp()


def validate_against_engine(
    market: str, c: Cases, nb_listed: bool, k: int = 400
) -> float:
    """Max |p| difference between this module's `cur` and the engine's
    sheet_predictive_sd / sheet_count_p_raw on a random subset of cases."""
    from bet.sofa.engine import (
        sheet_count_p_raw,
        sheet_predictive_sd,
        winning_boundary,
    )

    sub = _sub(c, k, seed=3)
    lines, thr = rung_grid(sub.centre)
    mine = current_over(market, sub, thr, nb_listed)
    worst = 0.0
    for i in range(len(sub)):
        sd = sheet_predictive_sd(
            market, "football", float(sub.mean[i]), float(sub.var[i]),
            int(sub.n[i]), float(sub.centre[i]),
        )
        for j in range(GRID):
            b = winning_boundary(float(lines[i, j]), "OVER")
            p = sheet_count_p_raw(market, float(sub.centre[i]), sd, b, "OVER")
            worst = max(worst, abs(p - float(mine[i, j])))
    return worst


def fmt_ci(x: list[float], scale: float = 1e3) -> str:
    return f"{x[0] * scale:+.2f} [{x[1] * scale:+.2f}; {x[2] * scale:+.2f}]"


def markdown_tables(results: dict[str, Any]) -> str:
    lines: list[str] = []
    for market, res in sorted(results["markets"].items()):
        if res.get("status") != "OK":
            lines.append(f"\n- `{market}`: {res.get('status')} "
                         f"(test {res.get('n_test')} cases)")
            continue
        fams = res["families"]
        lines.append(
            f"\n#### `{market}` (test {res['n_test']:,} przypadków, "
            f"{res['n_test_events']:,} meczów; obecny: "
            f"{'NB' if res['nb_listed'] else 'normalny'}; "
            f"log-loss obecnego {fams['cur']['ll']:.4f}, "
            f"Brier {fams['cur']['brier']:.4f})\n"
        )
        lines.append(
            "| rodzina | d log-loss x1000 [95%] | d Brier x1000 [95%] | "
            "połowy okna (d LL x1000) | >=0.70: n, deklar., realiz. | werdykt |"
        )
        lines.append("|---|---|---|---|---|---|")
        for f in FAMILIES:
            e = fams.get(f)
            if e is None:
                continue
            if f == "cur":
                lines.append(
                    f"| cur | - | - | - | {e['print_n']:,}, {e['print_claim']:.3f}, "
                    f"{e['print_real']:.3f} | - |"
                )
                continue
            h = e["half_d_ll"]
            lines.append(
                f"| {f} | {fmt_ci(e['d_ll'])} | {fmt_ci(e['d_brier'])} | "
                f"{h[0] * 1e3:+.2f} / {h[1] * 1e3:+.2f} | {e['print_n']:,}, "
                f"{e['print_claim']:.3f}, {e['print_real']:.3f} | {e['verdict']} |"
            )
    return "\n".join(lines)


def cmd_analyse(args: argparse.Namespace) -> int:
    d = Path(args.cases)
    meta = json.loads((d / "meta.json").read_text())
    names = {int(k): v for k, v in meta["names"].items()}
    test_ts, val_ts = _ts(args.test_start), _ts(args.val_start)
    from bet.sofa.engine import uses_negative_binomial

    results: dict[str, Any] = {
        "test_start": args.test_start, "val_start": args.val_start,
        "reps": args.reps, "markets": {}, "leagues": {}, "validation": {},
    }
    wanted = [m for m in sorted(meta["sizes"]) if not args.markets or m in args.markets]
    for market in wanted:
        t0 = time.time()
        c = load_cases(d / f"cases_{market}.npz")
        c = c.take(c.ts < _ts(args.end))  # a few listings carry a future start
        listed = uses_negative_binomial(market)
        worst = validate_against_engine(market, c.take(c.ts >= test_ts), listed) \
            if (c.ts >= test_ts).sum() > 100 else float("nan")
        results["validation"][market] = worst
        res = run_market(market, c, test_ts, val_ts, args.reps, nb_listed=listed)
        results["markets"][market] = res
        if market in ("corners_for", "corners_total", "cards_points_for",
                      "cards_points_total", "fouls_for", "fouls_total", "goals_for",
                      "goals_total", "shots_for", "shots_on_target_for",
                      "shots_on_target_total", "offsides_for"):
            results["leagues"][market] = league_dispersion(c, test_ts, names)
        Path(args.out_json).write_text(json.dumps(results, indent=1))
        print(f"{market}: {res.get('status')} engine diff {worst:.2e} "
              f"({time.time() - t0:.0f}s)", flush=True)
    Path(args.md_out).write_text(markdown_tables(results))
    return 0


# ---------------------------------------------------------------------------
# referee
# ---------------------------------------------------------------------------

def referee_coverage(
    db_path: Path,
) -> tuple[dict[int, dict[str, float]], dict[str, int]]:
    """event id -> referee career row, from sofa_event_detail.detail_json (the
    only place a referee is stored; neither sofa_listed_event nor the
    incidents carry one)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows: dict[int, dict[str, float]] = {}
    stats = {"detail_rows": 0, "football_finished": 0, "with_referee": 0}
    try:
        for eid, status, blob in conn.execute(
            "SELECT sofascore_event_id, status_type, detail_json FROM sofa_event_detail"
        ):
            stats["detail_rows"] += 1
            ev = json.loads(blob).get("event") or {}
            sport = (((ev.get("tournament") or {}).get("category") or {}).get("sport")
                     or {}).get("slug")
            if status != "finished" or sport != "football":
                continue
            stats["football_finished"] += 1
            ref = ev.get("referee")
            if isinstance(ref, dict) and ref.get("games"):
                stats["with_referee"] += 1
                rows[int(eid)] = {
                    "ref": float(ref.get("id") or 0),
                    "ypg": float(ref.get("yellowCards") or 0) / float(ref["games"]),
                    "games": float(ref["games"]),
                }
        finished = conn.execute(
            "SELECT count(*) FROM sofa_event_stats WHERE status_type='finished'"
        ).fetchone()[0]
        stats["stats_finished_football_and_other"] = int(finished)
    finally:
        conn.close()
    return rows, stats


def cmd_referee(args: argparse.Namespace) -> int:
    refs, stats = referee_coverage(Path(args.db))
    out: dict[str, Any] = {"coverage": stats}
    c = load_cases(Path(args.cases) / "cases_cards_points_total.npz")
    mask = np.array([int(e) in refs for e in c.ev])
    sub = c.take(mask)
    out["cases_total_cards_with_referee"] = len(sub)
    out["events_with_referee_and_case"] = int(len(np.unique(sub.ev)))
    per_ref: dict[int, int] = {}
    for e in np.unique(sub.ev):
        per_ref[int(refs[int(e)]["ref"])] = per_ref.get(int(refs[int(e)]["ref"]), 0) + 1
    out["matches_per_referee_max"] = max(per_ref.values()) if per_ref else 0
    out["referees"] = len(per_ref)
    if len(sub) >= 200:
        x = np.array([refs[int(e)]["ypg"] for e in sub.ev])
        x = (x - x.mean()) / (x.std() or 1.0)
        r = sub.y - sub.centre
        slope = float((x * (r - r.mean())).sum() / (x * x).sum())
        rng = np.random.default_rng(5)
        ev_u, inv = np.unique(sub.ev, return_inverse=True)
        boot = []
        for _ in range(500):
            w = rng.poisson(1.0, len(ev_u))[inv].astype(float)
            xm, rm = (w * x).sum() / w.sum(), (w * r).sum() / w.sum()
            boot.append(float(
                (w * (x - xm) * (r - rm)).sum() / (w * (x - xm) ** 2).sum()
            ))
        out["slope_points_per_sd_of_referee_yellow_per_game"] = [
            slope, float(np.quantile(boot, 0.025)), float(np.quantile(boot, 0.975))]
        out["residual_sd"] = float(r.std())
    Path(args.out_json).write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("collect")
    p.add_argument("--db", default=str(_REPO / "data" / "sofa.db"))
    p.add_argument("--out", required=True)
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(fn=cmd_collect)
    p = sub.add_parser("analyse")
    p.add_argument("--cases", required=True)
    p.add_argument("--test-start", required=True)
    p.add_argument("--val-start", required=True)
    p.add_argument("--end", default="2026-10-08")
    p.add_argument("--reps", type=int, default=300)
    p.add_argument("--markets", nargs="*", default=[])
    p.add_argument("--out-json", required=True)
    p.add_argument("--md-out", required=True)
    p.set_defaults(fn=cmd_analyse)
    p = sub.add_parser("referee")
    p.add_argument("--db", default=str(_REPO / "data" / "sofa.db"))
    p.add_argument("--cases", required=True)
    p.add_argument("--out-json", required=True)
    p.set_defaults(fn=cmd_referee)
    args = ap.parse_args()
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
