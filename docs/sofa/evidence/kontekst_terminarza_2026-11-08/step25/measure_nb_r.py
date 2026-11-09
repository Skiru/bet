"""Step 25 re-check: the dispersion constants path (ii) reads with the
corrected goals centres - nb_r (config/sofa_football_result.json, 7.586,
measured on the PURE rating centres) and the simulator's goal frailty
(config/sofa_football_sim_params.json, 0.03 = NB alpha). Read-only: reads the
recorder outputs of data/refit_2026-11-08_schedule (full/, fr_*), writes
step25/nb_r.json. Choice of r on dev (2024-07..2025-12, in-sample for the
term's coefficients), evaluation on 2026-01..10 (out of sample)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from math import lgamma
_lg = np.vectorize(lgamma)


def gammaln(x):
    return _lg(np.asarray(x, float))

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
sys.path[:0] = [str(D / "exam"), str(D)]
import exam_groups as eg  # noqa: E402
from bet.sofa.football_result import result_probs  # noqa: E402

R_INSTALLED = 7.586
GRID = [2, 3, 4, 5, 6, 7, 7.586, 8, 9, 10, 12, 15, 20, 25, 33.33, 50, 100, 1e6]


def nb_logpmf(y, mu, r):
    return (gammaln(y + r) - gammaln(r) - gammaln(y + 1)
            + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def arrays(rows):
    lh = np.array([r[5] for r in rows]); la = np.array([r[6] for r in rows])
    th = np.array([r[7] for r in rows]); ta = np.array([r[8] for r in rows])
    hg = np.array([r[10][0] for r in rows], float); ag = np.array([r[10][1] for r in rows], float)
    res = np.array([r[9] for r in rows])
    return lh, la, th, ta, hg, ag, res


def per_match(lh, la, hg, ag, res, r):
    g = nb_logpmf(hg, lh, r) + nb_logpmf(ag, la, r)
    x = np.array([math.log(result_probs(a, b, r)[s]) for a, b, s in zip(lh, la, res)])
    return g, x


def tier(rows, label):
    lh, la, th, ta, hg, ag, res = arrays(rows)
    out = {"matches": len(rows), "t_moves_share": float(np.mean((th != 0) | (ta != 0))),
           "t_abs_mean": float(np.mean(np.abs(np.r_[th, ta]))),
           "t_p95_abs": float(np.quantile(np.abs(np.r_[th, ta]), 0.95))}
    cen = {"base": (lh, la), "corrected": (lh * np.exp(th), la * np.exp(ta))}
    tot = hg.sum() + ag.sum()
    for k, (a, b) in cen.items():
        out[f"goals_over_centre_{k}"] = float(tot / (a.sum() + b.sum()))
        gl, xl = {}, {}
        for r in GRID:
            g, x = per_match(a, b, hg, ag, res, r)
            gl[r], xl[r] = g, x
        out[f"goals_ll_{k}"] = {str(r): float(gl[r].mean()) for r in GRID}
        out[f"x12_ll_{k}"] = {str(r): float(xl[r].mean()) for r in GRID}
        out[f"argmax_goals_{k}"] = max(GRID, key=lambda r: gl[r].mean())
        out[f"argmax_1x2_{k}"] = max(GRID, key=lambda r: xl[r].mean())
        out[f"_per_match_{k}"] = (gl, xl)
    return out


def boot(d, n=2000, seed=7):
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), (n, len(d)))
    m = d[idx].mean(1)
    return [float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))]


def main():
    dev = eg.fr_rows("dev", "dev")
    ex = eg.fr_rows("exam", "exam")
    rd, rx = tier(dev, "dev"), tier(ex, "exam")
    res = {"dev": {k: v for k, v in rd.items() if not k.startswith("_")},
           "exam": {k: v for k, v in rx.items() if not k.startswith("_")}}
    # out of sample: r chosen on dev under corrected centres, scored on exam
    for metric, i in (("goals", 0), ("1x2", 1)):
        r_dev = rd[f"argmax_{metric}_corrected"]
        gl = rx["_per_match_corrected"][i]
        d = gl[r_dev] - gl[R_INSTALLED]
        res[f"oos_{metric}"] = {"r_chosen_on_dev_corrected": r_dev,
                                "exam_ll_gain_vs_7586_per_match": float(d.mean()),
                                "ci95": boot(d)}
        # same check on the base centres (the installed constant's own baseline)
        r_dev_b = rd[f"argmax_{metric}_base"]
        glb = rx["_per_match_base"][i]
        db = glb[r_dev_b] - glb[R_INSTALLED]
        res[f"oos_{metric}_base"] = {"r_chosen_on_dev_base": r_dev_b,
                                     "exam_ll_gain_vs_7586_per_match": float(db.mean()),
                                     "ci95": boot(db)}
    # sim frailty 0.03 (r 33.33) vs best, corrected, exam goals
    gl = rx["_per_match_corrected"][0]; glb = rx["_per_match_base"][0]
    res["sim_frailty_r33"] = {"exam_goals_ll_r33_corrected_minus_base": float((gl[33.33] - glb[33.33]).mean()),
                              "ci95": boot(gl[33.33] - glb[33.33])}
    # the term's own effect at the installed r (exam, 1X2 and goals)
    for metric, i in (("goals", 0), ("1x2", 1)):
        d = rx["_per_match_corrected"][i][R_INSTALLED] - rx["_per_match_base"][i][R_INSTALLED]
        res[f"term_effect_exam_{metric}_ll_at_7586"] = {"mean": float(d.mean()), "ci95": boot(d)}
    (D / "step25/nb_r.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps(res, indent=1, default=float))


main()
