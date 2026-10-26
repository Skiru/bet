import pickle, json, numpy as np, collections
from datetime import datetime, UTC
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
rng = np.random.default_rng(11); B = 2000
CUT = int(datetime(2026,7,1,tzinfo=UTC).timestamp()); LATE = int(datetime(2026,10,1,tzinfo=UTC).timestamp())
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
R = pickle.load(open(f"{S}/rows.pkl","rb"))
R = [r for r in R if r[3] in FAMS]
eid = np.array([r[0] for r in R], np.int64); ts = np.array([r[1] for r in R], np.int64); fam = np.array([r[3] for r in R])
po = np.array([r[7] for r in R]); yo = np.array([r[8] for r in R]); nba = np.array([r[12] == 132 for r in R]); del R
print("rows", len(eid))
lg = lambda p: np.log(np.clip(p,1e-4,1-1e-4)/(1-np.clip(p,1e-4,1-1e-4))); sg = lambda z: 1/(1+np.exp(-z))
def fit_ab(p, y, intercept_only=False):
    x = lg(p); a, b = 0.0, 1.0
    for _ in range(30):
        q = sg(a + b*x); w = q*(1-q)
        if intercept_only:
            da = (y-q).sum()/max(w.sum(),1e-9); a += da
            if abs(da) < 1e-9: break
        else:
            g = np.array([(y-q).sum(), ((y-q)*x).sum()]); H = np.array([[w.sum(), (w*x).sum()],[(w*x).sum(), (w*x*x).sum()]])
            d = np.linalg.solve(H, g); a += d[0]; b += d[1]
            if np.abs(d).max() < 1e-9: break
    return float(a), float(b)
def fit_shrink(p, y):
    best = (1.0, 1e18)
    for s in np.arange(0.2, 1.0001, 0.05):
        q = np.where(p >= .7, .7 + s*(p-.7), p); q = np.clip(q, 1e-4, 1-1e-4)
        ll = -(y*np.log(q)+(1-y)*np.log(1-q)).sum()
        if ll < best[1]: best = (float(s), ll)
    return best[0]
tr = ts < CUT
PARAMS = {"A": {}, "B": {}, "C": {}}
def fit_all(mask, label=None):
    P = {"A": {}, "B": {}, "C": {}}
    for f in FAMS:
        for side in ("OVER", "UNDER"):
            m = mask & (fam == f); p = po[m] if side == "OVER" else 1-po[m]; y = yo[m] if side == "OVER" else 1-yo[m]
            aA, _ = fit_ab(p, y, True); aB, bB = fit_ab(p, y)
            pB = sg(aB + bB*lg(p)); hi = pB >= .7
            s = fit_shrink(pB, y) if hi.sum() >= 500 else 1.0
            P["A"][(f, side)] = (aA, 1.0, 1.0); P["B"][(f, side)] = (aB, bB, 1.0); P["C"][(f, side)] = (aB, bB, s)
    return P
def apply(P, v, f, side, p):
    a, b, s = P[v][(f, side)]; q = sg(a + b*lg(p))
    return np.where(q >= .7, .7 + s*(q-.7), q) if s != 1.0 else q
def newp(P, v, m_idx_fams, p_over):
    # returns (new_over, new_under) arrays for rows with given fam array
    no = np.empty_like(p_over); nu = np.empty_like(p_over)
    for f in FAMS:
        m = m_idx_fams == f
        if m.any():
            no[m] = apply(P, v, f, "OVER", p_over[m]); nu[m] = apply(P, v, f, "UNDER", 1-p_over[m])
    return no, nu
P = fit_all(tr)
js = {v: {f"{f.replace('player_','')}|{side}": {"a": round(a,4), "b": round(b,4), "shrink_above_0.70": round(s,2)} for (f, side), (a, b, s) in P[v].items()} for v in P}
json.dump({"fit_on": "all-basketball replay rows, ts < 2026-07-01 (line p = installed model p with calibration_b, at the replay line); p_new = sigmoid(a + b*logit p), then if >=0.70: 0.70 + shrink*(p-0.70); variant A: b=1; B: a,b; C: B + shrink", "n_train_rows_per_market": int(tr.sum()/5), "params": js}, open(f"{S}/calib_params.json","w"), indent=1)
for v in "AB": print(v, {k: (round(x[0],3), round(x[1],3)) for k, x in P[v].items()})
print("C shrink", {k: round(x[2],2) for k, x in P["C"].items()})
def ci(vals, g, B=B):
    ug, inv = np.unique(g, return_inverse=True); G = len(ug); s = np.zeros((G,2)); np.add.at(s, inv, np.stack([vals, np.ones_like(vals)],1))
    pt = s[:,0].sum()/s[:,1].sum(); bs = np.empty(B)
    for i in range(B):
        t = np.bincount(rng.integers(0,G,G), minlength=G) @ s; bs[i] = t[0]/t[1]
    lo, hi = np.percentile(bs, [2.5,97.5]); return pt, lo, hi
def ll(p, y): p = np.clip(p,1e-6,1-1e-6); return -(y*np.log(p)+(1-y)*np.log(1-p))
BK = [(.5,.6),(.6,.7),(.7,.8),(.8,1.01)]
def ece(p, y):
    t = 0
    for lo, hi in zip([0,.1,.2,.3,.4,.5,.6,.7,.8],[.1,.2,.3,.4,.5,.6,.7,.8,1.01]):
        m = (p>=lo)&(p<hi); t += abs(y[m].mean()-p[m].mean())*m.sum() if m.any() else 0
    return t/len(p)
def rel(p, y, tag):
    c = []
    for lo, hi in BK:
        m = (p>=lo)&(p<hi)
        if m.sum() >= 30: c.append(f"{lo:.1f}-{min(hi,1):.1f} n={m.sum()} p={p[m].mean():.3f} hit={y[m].mean():.3f}({y[m].mean()-p[m].mean():+.3f})")
    return f"      {tag}: " + " | ".join(c)
def evaluate(name, Pm, fam_a, po_a, yo_a, g, vars_="ABC", detail=True):
    n = len(g); print(f"\n== {name}: n={n} games={len(np.unique(g))}")
    no0, nu0 = po_a, 1-po_a; yu = 1-yo_a
    L0 = np.concatenate([ll(no0, yo_a), ll(nu0, yu)]); B0 = np.concatenate([(no0-yo_a)**2, (nu0-yu)**2]); G2 = np.concatenate([g, g])
    print(f"  old: logloss(both sides) {L0.mean():.5f} Brier {B0.mean():.5f} ECE over {ece(no0,yo_a):.4f} under {ece(nu0,yu):.4f}")
    for v in vars_:
        no, nu = newp(Pm, v, fam_a, po_a)
        L1 = np.concatenate([ll(no, yo_a), ll(nu, yu)]); B1 = np.concatenate([(no-yo_a)**2, (nu-yu)**2])
        d1 = ci(L1-L0, G2); d2 = ci(B1-B0, G2)
        print(f"  {v}: dLL {d1[0]:+.5f} [{d1[1]:+.5f},{d1[2]:+.5f}] dBrier {d2[0]:+.5f} [{d2[1]:+.5f},{d2[2]:+.5f}] ECE over {ece(no,yo_a):.4f} under {ece(nu,yu):.4f}")
        if detail and v in "BC":
            for side, p0, pn, y in (("OVER", no0, no, yo_a), ("UNDER", nu0, nu, yu)):
                print(rel(p0, y, f"{side} old")); print(rel(pn, y, f"{side} {v}  "))
    return
if __name__ == "__main__":
    te = ~tr; ev = {}
    for nm, m in (("TEST all", te), ("TEST non-NBA", te & ~nba), ("TEST NBA", te & nba), ("LATE>=10-01 all", ts >= LATE), ("LATE NBA", (ts >= LATE) & nba)):
        evaluate(nm, P, fam[m], po[m], yo[m], eid[m], detail=nm in ("TEST all", "TEST NBA", "LATE>=10-01 all"))
    print("\n== per-market dLL on TEST all, variant B and C (CI)")
    for f in FAMS:
        m = te & (fam == f); no, nu = newp(P, "B", fam[m], po[m]); nc, ncu = newp(P, "C", fam[m], po[m]); yu = 1-yo[m]
        L0 = ll(po[m], yo[m]) + ll(1-po[m], yu); LB = ll(no, yo[m]) + ll(nu, yu); LC = ll(nc, yo[m]) + ll(ncu, yu)
        print(f"  {f.replace('player_',''):12s} B {ci((LB-L0)/2, eid[m])[0]:+.5f} {tuple(round(x,5) for x in ci((LB-L0)/2, eid[m])[1:])} C {ci((LC-L0)/2, eid[m])[0]:+.5f} {tuple(round(x,5) for x in ci((LC-L0)/2, eid[m])[1:])}")
    # --- transfer to NBA train: fit on non-NBA train, eval NBA halves; NBA half-fit eval other half
    nt = tr & nba; mid = np.median(ts[nt]); h1 = nt & (ts < mid); h2 = nt & (ts >= mid)
    print(f"\n##### NBA train transfer: NBA train rows {nt.sum()} games {len(np.unique(eid[nt]))}; halves split at {datetime.fromtimestamp(mid, UTC).date()} (games {len(np.unique(eid[h1]))}/{len(np.unique(eid[h2]))})")
    Pn = fit_all(tr & ~nba)
    for nm, m in (("NBA train H1 (params fit on NON-NBA train)", h1), ("NBA train H2 (params fit on NON-NBA train)", h2)): evaluate(nm, Pn, fam[m], po[m], yo[m], eid[m], vars_="AB", detail=True)
    P1 = fit_all(h1); P2 = fit_all(h2)
    evaluate("NBA train H2 (params fit on NBA H1)", P1, fam[h2], po[h2], yo[h2], eid[h2], vars_="AB", detail=True)
    evaluate("NBA train H1 (params fit on NBA H2)", P2, fam[h1], po[h1], yo[h1], eid[h1], vars_="AB", detail=False)
    print("NBA-half-fit B params H1:", {k[0][7:]+k[1][:1]: (round(x[0],3), round(x[1],3)) for k, x in P1["B"].items()})
    # --- settled lines
    K, L = pickle.load(open(f"{S}/price_rows.pkl","rb"))
    L = [o for o in L if o["has_form"]]
    sid = np.array([o["sid"] for o in L]); pl = np.array([o["p_old"] for o in L]); wl = np.array([o["win"] for o in L], float); od = np.array([o["odds"] for o in L]); fl = np.array([o["fam"] for o in L]); sl = np.array([o["side"] for o in L]); nl = np.array([o["nba"] for o in L])
    def newl(v):
        out = np.empty_like(pl)
        for f in FAMS:
            for side in ("OVER","UNDER"):
                m = (fl == f) & (sl == side)
                if m.any():
                    a, b, s = P[v][(f, side)]; q = sg(a + b*lg(pl[m])); out[m] = np.where(q >= .7, .7 + s*(q-.7), q) if s != 1 else q
        return out
    for nm, m in (("SETTLED LINES all", np.ones(len(L), bool)), ("SETTLED NBA", nl), ("SETTLED non-NBA", ~nl)):
        print(f"\n== {nm}: n={m.sum()} games={len(np.unique(sid[m]))}")
        L0 = ll(pl[m], wl[m]); B0 = (pl[m]-wl[m])**2; print(f"  old: logloss {L0.mean():.5f} Brier {B0.mean():.5f}")
        for v in "ABC":
            pn = newl(v)[m]; L1 = ll(pn, wl[m]); B1 = (pn-wl[m])**2; d1 = ci(L1-L0, sid[m]); d2 = ci(B1-B0, sid[m])
            print(f"  {v}: dLL {d1[0]:+.5f} [{d1[1]:+.5f},{d1[2]:+.5f}] dBrier {d2[0]:+.5f} [{d2[1]:+.5f},{d2[2]:+.5f}]")
            if v in "BC" and m.all():
                for side in ("OVER","UNDER"):
                    s2 = sl[m] == side; print(rel(pl[m][s2], wl[m][s2], f"{side} old")); print(rel(pn[s2], wl[m][s2], f"{side} {v}  "))
    pnB, pnC = newl("B"), newl("C")
    print("\n== settled lines p>=0.70 (p*odds>=0.90 not applied) old -> B -> C, realised hit (old | B | C) per family, 1/odds in brackets")
    for f in ["ALL"] + FAMS:
        m = np.ones(len(L), bool) if f == "ALL" else fl == f
        def st(p): c = m & (p >= .7); return f"{c.sum()} hit={wl[c].mean():.3f} [{np.mean(1/od[c]):.3f}]" if c.sum() else "0"
        print(f"  {f.replace('player_',''):12s} {st(pl)} | {st(pnB)} | {st(pnC)}")
    ov = {}
    for nm, m in (("NBA", nl), ("non-NBA", ~nl)):
        print(f"  {nm}: p>=.70 old {(m&(pl>=.7)).sum()} B {(m&(pnB>=.7)).sum()} C {(m&(pnC>=.7)).sum()}")
