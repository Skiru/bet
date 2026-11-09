"""S5 power for the football groups from the outcome-free exam X rows
(full/exam/rows - no y store is opened). n_req = 7.85 (1/mu + alpha) 1.75 / 0.03^2,
mu = mean base centre of the group's `_for` rows, alpha = mean recorded NB dispersion.
Exposed rows per column = exam `_for` rows (both sides covered) with the column = 1
(own or opp). Pass rule (doprecyzowanie 11): >= 1 kept column with exposed rows >= n_req."""
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
sys.path[:0] = [str(D)]
import fb_analysis as fb  # noqa: E402

feats = pickle.loads((D / "football_features.pkl").read_bytes())
cent = defaultdict(list)
alph = defaultdict(list)
exp_ = defaultdict(lambda: defaultdict(int))
nrows = defaultdict(int)
for r in fb.read_chunks("exam", "rows"):
    (eid, ts, comp, sport, market, subject, book, n, mean, var, shrunk, final,
     phase, disp, emp, rp, sample, home, away, nr) = r
    g = fb.METRIC_GROUP.get(market)
    if sport != "football" or g is None or book != fb.book_for(market):
        continue
    f = feats.get(eid)
    if f is None or f["national"] or not (f["home"].coverage and f["away"].coverage):
        continue
    side = "home" if int(subject) == home else "away" if int(subject) == away else None
    if side is None:
        continue
    own, opp = (f["home"], f["away"]) if side == "home" else (f["away"], f["home"])
    io, ip = own.indicators(), opp.indicators()
    cent[g].append(final)
    alph[g].append(disp[0] if disp else 0.0)
    nrows[g] += 1
    for c in fb.COLS:
        if io[c]:
            exp_[g][f"own_{c}"] += 1
        if ip[c]:
            exp_[g][f"opp_{c}"] += 1
out = {}
for g in fb.GROUPS:
    if not nrows[g]:
        continue
    mu, a = float(np.mean(cent[g])), float(np.mean(alph[g]))
    need = 7.85 * (1 / mu + a) * 1.75 / 0.03 ** 2
    out[g] = {"rows": nrows[g], "mu": mu, "alpha": a, "n_req": need, "exposed": dict(exp_[g])}
    print(g, "rows", nrows[g], "mu", round(mu, 3), "alpha", round(a, 3), "n_req", int(need),
          {k: v for k, v in sorted(exp_[g].items(), key=lambda t: -t[1])[:8]})
(D / "fb_power.json").write_text(json.dumps(out, indent=1))
