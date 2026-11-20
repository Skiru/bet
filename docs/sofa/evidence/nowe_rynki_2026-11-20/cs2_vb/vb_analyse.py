"""Analyse vb_rows.jsonl: model vs de-vigged price per market (event bootstrap), p>=0.70 calibration, gates, ROI."""
import json, math, random, collections
R = [json.loads(l) for l in open("vb_rows.jsonl")]
def ll(p, y): p = min(max(p, 1e-4), 1 - 1e-4); return -math.log(p if y else 1 - p)
def boot(groups, reps=3000):
    keys = list(groups); rng = random.Random(3); flat = [v for k in keys for v in groups[k]]; st = []
    for _ in range(reps):
        t = n = 0
        for _k in keys:
            g = groups[keys[rng.randrange(len(keys))]]; t += sum(g); n += len(g)
        st.append(t / n)
    st.sort(); return sum(flat) / len(flat), st[int(.025 * reps)], st[int(.975 * reps) - 1]
def fmt(t): return "%+.4f [%+.4f, %+.4f]" % t
for mid in (230059, 786, 100080, 100081):
    S = [r for r in R if r["mid"] == mid]
    ev = {r["sid"] for r in S}
    print(f"== {mid}: rows {len(S)}, events {len(ev)}, mean margin {sum(r['margin'] for r in S)/len(S):.3f}")
    gb, gl = collections.defaultdict(list), collections.defaultdict(list)
    for r in S:
        gb[r["sid"]].append((r["p"] - r["y"]) ** 2 - (r["fair"] - r["y"]) ** 2); gl[r["sid"]].append(ll(r["p"], r["y"]) - ll(r["fair"], r["y"]))
    print("   Brier model - fair", fmt(boot(gb)), " logloss model - fair", fmt(boot(gl)))
    for lab, key in (("model", "p"), ("fair", "fair")):
        hi = [r for r in S if r[key] >= 0.70]
        if hi:
            g = collections.defaultdict(list)
            for r in hi: g[r["sid"]].append(r["y"] - r[key])
            print(f"   {lab} p>=0.70: n {len(hi)} claimed {sum(r[key] for r in hi)/len(hi):.3f} realised {sum(r['y'] for r in hi)/len(hi):.3f} gap", fmt(boot(g)))
    P = [r for r in S if r["p"] >= 0.70 and r["p"] * r["odds"] >= 0.90 and r["margin"] <= 0.15]
    if P:
        g = collections.defaultdict(list)
        for r in P: g[r["sid"]].append(r["odds"] * r["y"] - 1)
        print(f"   gates on raw model p: {len(P)} legs / {len({r['sid'] for r in P})} events, hit {sum(r['y'] for r in P)/len(P):.3f}, mean 1/odds {sum(1/r['odds'] for r in P)/len(P):.3f}, mean p {sum(r['p'] for r in P)/len(P):.3f}, ROI", fmt(boot(g)),
              " after 12%% tax %+.3f" % (sum(0.88 * r['odds'] * r['y'] for r in P) / len(P) - 1))
    else:
        print("   gates on raw model p: 0 legs")
    mp = sorted(r["p"] for r in S); print("   model p quantiles 50/90/99/max:", [round(mp[int(q * (len(mp) - 1))], 3) for q in (.5, .9, .99, 1)])
    if mid == 230059:
        for kind in ("same", "split"):
            K = [r for r in S if r["kind"] == kind]
            print(f"   {kind}: mean p {sum(r['p'] for r in K)/len(K):.3f} fair {sum(r['fair'] for r in K)/len(K):.3f} realised {sum(r['y'] for r in K)/len(K):.3f}")
        # the favourite's 'same' selection (highest fair) per event
        fav = {}
        for r in S:
            if r["kind"] == "same" and (r["sid"] not in fav or r["fair"] > fav[r["sid"]]["fair"]): fav[r["sid"]] = r
        F = list(fav.values()); g = collections.defaultdict(list)
        for r in F: g[r["sid"]].append((r["p"] - r["y"]) ** 2 - (r["fair"] - r["y"]) ** 2)
        print(f"   favourite set1&match: n {len(F)} mean p {sum(r['p'] for r in F)/len(F):.3f} fair {sum(r['fair'] for r in F)/len(F):.3f} realised {sum(r['y'] for r in F)/len(F):.3f}  Brier model-fair", fmt(boot(g)))
        for lo in (0.6, 0.65, 0.7, 0.75):
            K = [r for r in F if r["p"] >= lo]
            if K: print(f"     model p>={lo}: n {len(K)} p {sum(r['p'] for r in K)/len(K):.3f} fair {sum(r['fair'] for r in K)/len(K):.3f} realised {sum(r['y'] for r in K)/len(K):.3f} 1/odds {sum(1/r['odds'] for r in K)/len(K):.3f}")
