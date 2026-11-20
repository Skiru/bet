import math
import numpy as np
EDGES = [0.0, 0.60, 0.70, 0.75, 0.80, 0.825, 0.85, 0.875, 0.90, 0.925, 0.95, 1.01]
RNG = np.random.default_rng(20261120)

def boot_ratio(eids, num, den=None, B=2000):
    """point, lo, hi of sum(num)/sum(den) with resampled matches (den None = mean of rows)."""
    eids = np.asarray(eids); num = np.asarray(num, float)
    den = np.ones_like(num) if den is None else np.asarray(den, float)
    u, inv = np.unique(eids, return_inverse=True)
    sn = np.bincount(inv, weights=num, minlength=len(u)); sd = np.bincount(inv, weights=den, minlength=len(u))
    pt = sn.sum() / sd.sum()
    idx = RNG.integers(0, len(u), size=(B, len(u)))
    cnt = np.zeros((B, len(u)))
    for b in range(B):
        cnt[b] = np.bincount(idx[b], minlength=len(u))
    est = (cnt @ sn) / (cnt @ sd)
    return float(pt), float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))

def wilson_lo(k, n, z=1.959964):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - r) / d

def bucket(p):
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2

def fmt(t, k=3, pct=False):
    m = 100 if pct else 1
    return f"{t[0]*m:+.{k}f} [{t[1]*m:+.{k}f}, {t[2]*m:+.{k}f}]"
