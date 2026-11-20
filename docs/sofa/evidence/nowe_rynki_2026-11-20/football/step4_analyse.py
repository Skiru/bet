"""Step 4 analysis: raw simulator p vs realised on the history walk-forward 2026-06-01..10-20, per curve key
(cand|tak/nie, cand|OVER pooled over lines and sides), bands with match bootstrap, and the would-be curve
(fit_confidence's EDGES, n >= 400 / thin >= 100, Wilson lo95)."""
import gzip, json, sys
from collections import defaultdict
from pathlib import Path
sys.path[:0] = [str(Path(__file__).parent)]
import numpy as np
from stats import boot_ratio, wilson_lo, bucket, EDGES, fmt
S = Path(sys.argv[1])
def key(cand, label):
    tail = label.split(":")[-1]
    return f"{cand}|{tail}" if tail in ("tak", "nie") else f"{cand}|OVER"
data = defaultdict(lambda: {"e": [], "p": [], "y": [], "lab": [], "w": []})
for line in gzip.open(S / "history_rows.jsonl.gz", "rt"):
    eid, ts, women, cand, gk, label, p, y = json.loads(line)
    # half handicaps: only the +L side would be a row (OVER = side given +L)
    if cand.startswith("half") and cand.endswith("handicap") and "(-" in label:
        continue
    d = data[key(cand, label)]
    d["e"].append(eid); d["p"].append(p); d["y"].append(y); d["lab"].append(label); d["w"].append(women)
out = {}
for k in sorted(data):
    d = data[k]
    e, p, y = np.array(d["e"]), np.array(d["p"]), np.array(d["y"])
    res = {"rows": int(len(p)), "matches": int(len(set(d["e"]))), "mean_p": round(float(p.mean()), 4), "hit": round(float(y.mean()), 4)}
    for lo, hi in ((0.60, 0.70), (0.70, 0.80), (0.80, 0.92), (0.92, 1.01)):
        m = (p >= lo) & (p < hi)
        if m.sum() < 30:
            res[f"{lo:.2f}-{hi:.2f}"] = {"n": int(m.sum())}
            continue
        t = boot_ratio(e[m], (y - p)[m], B=500)
        res[f"{lo:.2f}-{hi:.2f}"] = {"n": int(m.sum()), "claimed": round(float(p[m].mean()), 4), "realised": round(float(y[m].mean()), 4),
                                     "realised_minus_claimed_pp": fmt(t, 1, pct=True)}
    cur = {}
    for b in range(len(EDGES) - 1):
        m = np.array([bucket(x) == b for x in p])
        n = int(m.sum())
        if n >= 100:
            k1 = int(y[m].sum())
            cur[f"{EDGES[b]:.3f}-{EDGES[b+1]:.3f}"] = {"n": n, "realised": round(k1 / n, 4), "realised_lo95": round(wilson_lo(k1, n), 4),
                                                        "thin": n < 400}
    res["curve"] = cur
    # women apart (class curve), >= 0.70
    w = np.array(d["w"]) == 1
    m = w & (p >= 0.70)
    if m.sum() >= 30:
        res["women_ge_070"] = {"n": int(m.sum()), "claimed": round(float(p[m].mean()), 4), "realised": round(float(y[m].mean()), 4)}
    out[k] = res
json.dump(out, open(S / "step4_results.json", "w"), indent=1)
for k, v in out.items():
    print("==", k, {x: v[x] for x in ("rows", "matches", "mean_p", "hit")})
    for b in ("0.60-0.70", "0.70-0.80", "0.80-0.92", "0.92-1.01"):
        print("   ", b, v[b])
    if "women_ge_070" in v:
        print("    women >=0.70", v["women_ge_070"])
