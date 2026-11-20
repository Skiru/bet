"""Shared: the simulator's joint (h1, a1, h2, a2) distribution of one match, exactly as SHEET's SimPricer
simulates it (4,000 paths, seed = event id, config/sofa_football_sim_params.json, pure rating centres)."""
import sys
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
import numpy as np
from bet.sofa import football_sim_sheet as fss
from scripts.sofa.fit_football_sim_curves import centres_of_values

PARAMS = fss.load_params()

def joint(eid, values):
    c = centres_of_values(values or {})
    if c is None:
        return None
    pricer = fss.SimPricer(PARAMS)
    g = pricer.market_sim(int(eid), c).res.goals  # [half, side, n]
    arr = np.stack([g[0, 0], g[0, 1], g[1, 0], g[1, 1]], axis=1)
    u, cnt = np.unique(arr, axis=0, return_counts=True)
    return [tuple(int(x) for x in row) for row in u], cnt.astype(float) / cnt.sum()

def p_of(j, held):
    """P(held) over the joint; a refund (held None) is conditioned out."""
    states, w = j
    num = den = 0.0
    for s, wi in zip(states, w):
        v = held(*s)
        if v is None:
            continue
        den += wi
        if v:
            num += wi
    return None if den <= 0 else num / den
