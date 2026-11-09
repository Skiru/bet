"""Vectorised engine.nb_survival / calc_p_central_nb_raw for NB-dispersed rows:
sd^2 = centre + alpha centre^2 (engine.sheet_predictive_sd with a Dispersion)."""
from __future__ import annotations

import numpy as np

KMAX = 40


def survival_table(mean: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """S[i, k] = P(X > k) for k = 0..KMAX-1, as engine.nb_survival."""
    var = mean + alpha * mean * mean
    pois = var <= mean * (1.0 + 1e-9)
    out = np.empty((len(mean), KMAX))
    # NB branch
    r = np.where(pois, 1.0, mean * mean / np.where(pois, 1.0, var - mean))
    p = r / (r + mean)
    pmf = np.exp(r * np.log(p))
    acc = pmf.copy()
    q = 1.0 - p
    pm = np.exp(-mean)
    acc_p = pm.copy()
    for k in range(KMAX):
        if k > 0:
            pmf = pmf * (k - 1 + r) / k * q
            acc = acc + pmf
            pm = pm * mean / k
            acc_p = acc_p + pm
        a = np.where(pois, acc_p, acc)
        out[:, k] = np.maximum(0.0, 1.0 - np.minimum(a, 1.0))
    out[mean <= 0.0] = 0.0
    return out


def p_lines(mean: np.ndarray, alpha: np.ndarray, lowest: np.ndarray) -> np.ndarray:
    """p OVER for the 9 lines lowest+0.5 .. lowest+8.5 (cfc.lines_for):
    OVER line L wins on X > floor(L) = lowest + j."""
    s = survival_table(mean, alpha)
    idx = lowest[:, None].astype(int) + np.arange(9)[None, :]
    return np.take_along_axis(s, np.minimum(idx, KMAX - 1), axis=1)
