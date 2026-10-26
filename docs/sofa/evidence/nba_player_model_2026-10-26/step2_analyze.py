import pickle, numpy as np, collections
from datetime import datetime, UTC
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
rng = np.random.default_rng(7); B = 2000
LATE = int(datetime(2026,10,1,tzinfo=UTC).timestamp())
def cluster_ci(val, g, B=B, ratio=None):
    ug, inv = np.unique(g, return_inverse=True); G = len(ug)
    s = np.zeros((G, 2)); np.add.at(s, inv, np.stack([val, np.ones_like(val)], 1))
    pt = s[:,0].sum()/s[:,1].sum(); bs = np.empty(B)
    for i in range(B):
        w = np.bincount(rng.integers(0, G, G), minlength=G); t = w @ s; bs[i] = t[0]/t[1]
    return pt, *np.percentile(bs, [2.5, 97.5]), G
def fmt(t): return f"{t[0]:+.5f} [{t[1]:+.5f},{t[2]:+.5f}] g={t[3]}"
BUCK = [0, .3, .4, .5, .6, .7, .8, 1.0001]
def reliab(p_o, y_o, g, tag):
    # over side buckets on p; under side = mirrored (p_u=1-p, y_u=1-y); report old vs new hit minus p
    lines = []
    for side, p, y in (("OVER", p_o, y_o), ("UNDER", 1-p_o, 1-y_o)):
        cells = []
        for lo, hi in zip(BUCK[:-1], BUCK[1:]):
            m = (p >= lo) & (p < hi)
            if m.sum() < 200: continue
            cells.append(f"[{lo:.1f},{min(hi,1):.1f}) n={m.sum()} p={p[m].mean():.3f} hit={y[m].mean():.3f} gap={y[m].mean()-p[m].mean():+.3f}")
        lines.append(f"    {tag} {side}: " + " | ".join(cells))
    return "\n".join(lines)
def ece(p, y):
    t = 0.0
    for lo, hi in zip(BUCK[:-1], BUCK[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum(): t += m.sum()*abs(y[m].mean()-p[m].mean())
    return t/len(p)
print("##### (1) TEST-split replay (>=2026-07-01), the pmf of the actual count + p at replay line")
R = pickle.load(open(f"{S}/oos_rows.pkl","rb"))
eid = np.array([r[0] for r in R], float); ts = np.array([r[1] for r in R], float); fam = np.array([r[2] for r in R])
ll0 = np.array([r[6] for r in R]); ll1 = np.array([r[7] for r in R]); p0 = np.array([r[8] for r in R]); p1 = np.array([r[9] for r in R]); y = np.array([r[10] for r in R])
nba = np.array([r[12] == 132 for r in R]); y_c = np.array([r[3] for r in R]); m0 = np.array([r[4] for r in R]); m1 = np.array([r[5] for r in R])
def section(name, m):
    print(f"\n== {name}: n={m.sum()} games={len(np.unique(eid[m]))}")
    for fm in ["ALL"] + sorted(set(fam)):
        mm = m & ((fam == fm) if fm != "ALL" else True)
        if mm.sum() < 300: continue
        b0 = (p0[mm]-y[mm])**2; b1 = (p1[mm]-y[mm])**2
        l0 = -(y[mm]*np.log(np.clip(p0[mm],1e-6,1))+(1-y[mm])*np.log(np.clip(1-p0[mm],1e-6,1))); l1 = -(y[mm]*np.log(np.clip(p1[mm],1e-6,1))+(1-y[mm])*np.log(np.clip(1-p1[mm],1e-6,1)))
        print(f"  {fm.replace('player_',''):11s} n={mm.sum():6d} | count logloss old {ll0[mm].mean():.4f} new {ll1[mm].mean():.4f} d(new-old) {fmt(cluster_ci(ll1[mm]-ll0[mm], eid[mm]))}")
        print(f"  {'':11s} line-p Brier old {b0.mean():.5f} new {b1.mean():.5f} d {fmt(cluster_ci(b1-b0, eid[mm]))} | line-p logloss d {fmt(cluster_ci(l1-l0, eid[mm]))} | ECE old {ece(p0[mm],y[mm]):.4f} new {ece(p1[mm],y[mm]):.4f} | MSE of mean old {((y_c[mm]-m0[mm])**2).mean():.3f} new {((y_c[mm]-m1[mm])**2).mean():.3f}")
    mm = m
    print(reliab(p0[mm], y[mm], eid[mm], "old")); print(reliab(p1[mm], y[mm], eid[mm], "new"))
section("TEST all basketball", ts >= 0); section("TEST NBA (id 132)", nba); section("TEST non-NBA", ~nba)
section("LATE holdout >=2026-10-01 all", ts >= LATE); section("LATE holdout NBA", (ts >= LATE) & nba)
print("\n##### (2) settled Superbet lines with live-model pre-game p (p recomputed by replay as of kickoff; both sides of each line)")
K, L = pickle.load(open(f"{S}/price_rows.pkl","rb"))
print("k:", {k.replace('player_',''): round(v,4) for k, v in K.items()})
L = [o for o in L if o['has_form']]
g = np.array([o['sid'] for o in L], float); po = np.array([o['p_old'] for o in L]); pn = np.array([o['p_new'] for o in L]); yy = np.array([o['win'] for o in L], float)
od = np.array([o['odds'] for o in L]); fm = np.array([o['fam'] for o in L]); nb = np.array([o['nba'] for o in L]); sd = np.array([o['side'] for o in L]); day = np.array([o['day'] for o in L])
print("lines with form (>=5 prior games):", len(L), "games", len(np.unique(g)), "| NBA lines", nb.sum(), "games", len(np.unique(g[nb])), "| other", (~nb).sum(), "games", len(np.unique(g[~nb])), "| days", min(day), max(day))
def sec2(name, m):
    print(f"\n== {name}: n={m.sum()} games={len(np.unique(g[m]))}")
    for f2 in ["ALL"] + sorted(set(fm)):
        mm = m & ((fm == f2) if f2 != "ALL" else True)
        if mm.sum() < 200: continue
        b0 = (po[mm]-yy[mm])**2; b1 = (pn[mm]-yy[mm])**2
        l0 = -(yy[mm]*np.log(np.clip(po[mm],1e-6,1))+(1-yy[mm])*np.log(np.clip(1-po[mm],1e-6,1))); l1 = -(yy[mm]*np.log(np.clip(pn[mm],1e-6,1))+(1-yy[mm])*np.log(np.clip(1-pn[mm],1e-6,1)))
        print(f"  {f2.replace('player_',''):11s} n={mm.sum():5d} Brier old {b0.mean():.5f} new {b1.mean():.5f} d {fmt(cluster_ci(b1-b0, g[mm]))} | logloss old {l0.mean():.4f} new {l1.mean():.4f} d {fmt(cluster_ci(l1-l0, g[mm]))}")
    mm = m
    for sidev in ("OVER", "UNDER"):
        s2 = mm & (sd == sidev)
        for tag, p in (("old", po), ("new", pn)):
            cells = []
            for lo, hi in zip(BUCK[:-1], BUCK[1:]):
                c = s2 & (p >= lo) & (p < hi)
                if c.sum() < 30: continue
                cells.append(f"[{lo:.1f},{min(hi,1):.1f}) n={c.sum()} p={p[c].mean():.3f} hit={yy[c].mean():.3f} 1/odds={np.mean(1/od[c]):.3f}")
            print(f"    {tag} {sidev}: " + " | ".join(cells))
    print("  threshold crossing (secondary): p>=0.70 and p*odds>=0.90")
    for f2 in ["ALL"] + sorted(set(fm)):
        mm2 = m & ((fm == f2) if f2 != "ALL" else True)
        o70 = mm2 & (po >= .7); n70 = mm2 & (pn >= .7); oP = o70 & (po*od >= .9); nP = n70 & (pn*od >= .9)
        def stat(c):
            if c.sum() < 5: return f"n={c.sum()}"
            u = np.where(yy[c] == 1, od[c]-1, -1.0)
            t = cluster_ci(u, g[c]); return f"n={c.sum()} hit={yy[c].mean():.3f} 1/odds={np.mean(1/od[c]):.3f} units/line={t[0]:+.3f} [{t[1]:+.3f},{t[2]:+.3f}]"
        print(f"   {f2.replace('player_',''):11s} p>=.70 old {o70.sum()} new {n70.sum()} (newly {(n70&~o70).sum()}, lost {(o70&~n70).sum()}) | print old {stat(oP)} | print new {stat(nP)} | newly printed {stat(nP&~oP)}")
sec2("settled lines ALL basketball", np.ones(len(L), bool)); sec2("settled NBA", nb); sec2("settled non-NBA", ~nb)
