"""Estimation of the football count dispersion (numpy), shared by the A2
measurement (`measure_count_families.py`) and `fit_count_dispersion.py`.

The runtime half (config, lookup, variance, pooling formula) is
`bet.sofa.count_dispersion` and needs no numpy; src/ does not depend on it, so
the vectorised likelihood lives here.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np
import numpy.typing as npt

Arr = npt.NDArray[Any]
IArr = npt.NDArray[Any]

_LANCZOS = (
    0.99999999999980993, 676.5203681218851, -1259.1392167224028,
    771.32342877765313, -176.61502916214059, 12.507343278686905,
    -0.13857109526572012, 9.9843695780195716e-6, 1.5056327351493116e-7,
)


def lgamma_np(x: Arr) -> Arr:
    """log Gamma(x) for x > 0 (Lanczos g=7, ~1e-14), vectorised."""
    x = np.asarray(x, dtype=np.float64)
    small = x < 0.5
    xs = np.where(small, x + 1.0, x)
    z = xs - 1.0
    a = np.full_like(z, _LANCZOS[0])
    for i in range(1, 9):
        a = a + _LANCZOS[i] / (z + i)
    t = z + 7.5
    out = 0.5 * math.log(2.0 * math.pi) + (z + 0.5) * np.log(t) - t + np.log(a)
    return np.where(small, out - np.log(np.where(small, x, 1.0)), out)


def nb_params(mu: Arr, var: Arr) -> tuple[Arr, Arr]:
    """(r, q) of the NB with this mean and variance; Poisson as r -> infinity,
    exactly the switch engine.nb_survival makes (variance <= mean)."""
    mu = np.maximum(mu, 1e-12)
    excess = var - mu
    r = np.where(
        excess > mu * 1e-9, mu * mu / np.maximum(excess, 1e-300), mu * 1e9
    )
    return r, mu / (r + mu)


def nb_loglik(y: Arr, mu: Arr, var: Arr) -> Arr:
    r, _ = nb_params(mu, var)
    mu = np.maximum(mu, 1e-12)
    return np.asarray(
        lgamma_np(y + r) - lgamma_np(r) - lgamma_np(y + 1.0)
        + r * (np.log(r) - np.log(r + mu)) + y * (np.log(mu) - np.log(r + mu)),
        dtype=np.float64,
    )


def golden_min(
    f: Callable[[float], float], lo: float, hi: float, it: int = 28
) -> float:
    g = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = lo, hi
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(it):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return 0.5 * (a + b)


def group_sums(
    keys: IArr, a: Arr, b: Arr, skip: int | None = None
) -> dict[int, tuple[float, float]]:
    uniq, inv = np.unique(keys, return_inverse=True)
    sa = np.bincount(inv, weights=a, minlength=len(uniq))
    sb = np.bincount(inv, weights=b, minlength=len(uniq))
    return {
        int(u): (float(x), float(y))
        for u, x, y in zip(uniq, sa, sb, strict=True) if skip is None or u != skip
    }


def moment_stats(
    comp: IArr, mu: Arr, y: Arr
) -> tuple[float, float, dict[int, tuple[float, float]]]:
    """(moment alpha, mean mu^2, {competition: (A, B)}) of cases (centre mu,
    count y): A = sum((y-mu)^2 - mu), B = sum mu^2; alpha_mom = sum A / sum B."""
    resid = (y - mu) ** 2 - mu
    b = mu * mu
    return (
        max(1e-4, float(resid.sum() / b.sum())), float(b.mean()),
        group_sums(comp, resid, b),
    )


def mle_alpha(y: Arr, mu: Arr) -> float:
    """The NB dispersion maximising the likelihood of y around mu."""
    def nll(la: float) -> float:
        a = math.exp(la)
        return -float(nb_loglik(y, mu, mu + a * mu * mu).sum())

    return math.exp(golden_min(nll, math.log(1e-3), math.log(3.0)))
