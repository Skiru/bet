"""tennis_games_sets S4 (validate tier; one LOGGED look): Bernoulli log loss of
each recorded line (OVER; UNDER is its complement) per arm, summed per match,
Delta = mean over matches (treat - base); two-way bootstrap player x
tournament-week (tw_analysis.cluster_boot). Outcomes: the dev y store only."""
import datetime as dt
import gzip
import hashlib
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
sys.path[:0] = [str(D)]
import tw_analysis as twa  # noqa: E402

X = pickle.loads((D / "tennis/tg_validate_X.pkl").read_bytes())
want = {(r[0], r[5], str(r[6])) for r in X}
ys = {}
for p in sorted((D / "full/dev/y").glob("*.pkl.gz")):
    for e, m, s, b, a in pickle.load(gzip.open(p)):
        if (e, m, str(s)) in want:
            ys[(e, m, str(s))] = a
per = defaultdict(float)
meta = {}
miss = 0
for eid, ts, home, away, tour, market, subject, side, line, p0, p1 in X:
    a = ys.get((eid, market, str(subject)))
    if a is None:
        miss += 1
        continue
    y = 1.0 if a > line else 0.0
    q0, q1 = min(max(p0, 1e-12), 1 - 1e-12), min(max(p1, 1e-12), 1 - 1e-12)
    l0 = -(y * np.log(q0) + (1 - y) * np.log(1 - q0))
    l1 = -(y * np.log(q1) + (1 - y) * np.log(1 - q1))
    per[eid] += l1 - l0
    meta[eid] = {"home_id": home, "away_id": away, "tournament_id": tour, "ts": ts}
eids = sorted(per)
diff = np.array([per[e] for e in eids])
boot = twa.cluster_boot(diff, [meta[e] for e in eids])
spec = hashlib.sha256(json.dumps({"BASE": twa.BASE, "TREAT": twa.TREAT,
                                  "markets": "games_won_for,set1/2/3 OVER"}).encode()).hexdigest()[:12]
line = (f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | tennis_games_sets | validate | spec {spec} | "
        f"matches {len(diff)} (lines {len(X) - miss}, no y {miss}) | Delta {diff.mean():+.6f} "
        f"[{np.quantile(boot, .025):+.6f}, {np.quantile(boot, .975):+.6f}] | "
        f"S4 {'pass' if diff.mean() < 0 else 'fail'} |\n")
with twa.LOOKS.open("a") as f:
    f.write(line)
print(line, end="")
