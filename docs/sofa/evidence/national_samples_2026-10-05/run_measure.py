import sys, numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-mkoziol-projects-bet/326c21e7-29e6-43a0-88f5-09a4e6cdf26e/scratchpad/nations')
import measure_nations as M
from datetime import datetime, UTC
h, targets, meta = M.load()
pops = {"all_national": lambda e: True, "senior_men": lambda e: meta[e]["senior_men"]}
metrics = sys.argv[1:] or ["goals_for", "goals_total"]
start = int(datetime(2015, 1, 1, tzinfo=UTC).timestamp())
rng = np.random.default_rng(20261005)
def ci(diff, ids):
    return M.paired_interval(diff, ids, rng, 1000)
for metric in metrics:
    names, S, ids, ages, hard = M.evaluate(h, targets, metric, start_ts=start)
    if len(ids) == 0:
        print(f"## {metric}: no cases"); continue
    for pop, f in pops.items():
        mask = np.array([f(int(e)) for e in ids])
        if mask.sum() < 30: continue
        s, i, a = S[mask], ids[mask], ages[mask]
        hd = [hard[k] for k in np.nonzero(mask)[0]]
        print(f"\n## {metric} [{pop}] {len(i)} cases, {len(set(i.tolist()))} matches; R0 oldest-age median {np.median(a):.0f} d")
        print("| rule | logloss | brier(mean over lines) | d logloss vs a_all10 [95%] |")
        for r, nm in enumerate(names):
            d = s[:, r, 0] - s[:, 0, 0]
            lo, hi = ci(d, i) if r else (0, 0)
            print(f"| {nm} | {s[:, r, 0].mean():.5f} | {s[:, r, 2:].mean():.5f} | {d.mean():+.5f} [{lo:+.5f}; {hi:+.5f}] |")
        for X in (180, 365, 540, 730):
            sel = np.array([X in x for x in hd])
            if sel.sum() < 30: 
                print(f"| hard_window_{X}d | coverage {sel.mean():.1%} (too few) |"); continue
            hv = np.array([x[X][0] for x, k in zip(hd, sel) if k])
            d = hv - s[sel, 0, 0]
            lo, hi = ci(d, i[sel])
            print(f"| d_hard{X} (sample kept only if >=5 inside; coverage {sel.mean():.1%}) | {hv.mean():.5f} | | {d.mean():+.5f} [{lo:+.5f}; {hi:+.5f}] |")
        # age buckets: skill vs constant, and trimming old obs
        base = s[:, 0, 0]
        # constant baseline: mean outcome of the population is not stored; use logloss of newest5 vs all10 and win180 vs all10
        print("| R0 oldest age | cases | logloss a_all10 | d(newest5 - all10) [95%] | d(c_win180 - all10) [95%] | d(b_same - all10) [95%] |")
        r5 = names.index("n5_newest5"); r180 = names.index("c_win180"); rb = names.index("b_same_comp")
        for lo_, hi_ in ((0, 180), (180, 400), (400, 730), (730, 1e9)):
            sel = (a > lo_) & (a <= hi_)
            if sel.sum() < 30:
                print(f"| {lo_}-{hi_} | {sel.sum()} | too few |"); continue
            out = []
            for r in (r5, r180, rb):
                d = s[sel, r, 0] - s[sel, 0, 0]
                l, u = ci(d, i[sel]); out.append(f"{d.mean():+.5f} [{l:+.5f}; {u:+.5f}]")
            print(f"| {lo_:.0f}-{hi_:.0f} | {sel.sum()} | {s[sel,0,0].mean():.5f} | " + " | ".join(out) + " |")
