import pickle, sys, numpy as np, collections
from datetime import datetime, UTC
rows = pickle.load(open(sys.argv[1], "rb"))
CUT = int(datetime(2026,7,1,tzinfo=UTC).timestamp()); LATE = int(datetime(2026,10,1,tzinfo=UTC).timestamp())
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
NBA = 132
rng = np.random.default_rng(1)
B = 2000
# per (pid,fam) chronological features
by = collections.defaultdict(list)
for r in rows: by[(r[2], r[3])].append(r)
feats = []  # eid ts fam y exp sd p yo line tour  f3 f5 z3 z5 r5
excl = collections.Counter(); tot = collections.Counter()
for (pid, fam), lst in by.items():
    if fam not in FAMS: continue
    lst.sort(key=lambda r: (r[1], r[0]))
    res = []; zs = []
    for r in lst:
        eid, ts, _, _, y, mu, sd, p, yo, line, raw5, nown, tour = r
        tot[fam] += 1
        if len(res) >= 5 and raw5 is not None and sd > 0:
            feats.append((eid, ts, fam, y, mu, sd, p, yo, line, tour,
                          np.mean(res[-3:]), np.mean(res[-5:]), np.mean(zs[-3:]), np.mean(zs[-5:]), raw5 - mu))
        else: excl[fam] += 1
        res.append(y - mu); zs.append((y - mu) / sd if sd > 0 else 0.0)
F = np.array([(f[0], f[1], f[3], f[4], f[5], f[6], f[7], f[8], f[9] or 0, f[10], f[11], f[12], f[13], f[14]) for f in feats], float)
fam = np.array([f[2] for f in feats])
EID, TS, Y, MU, SD, P, YO, LINE, TOUR, R3, R5, Z3, Z5, RAW = F.T
RES = Y - MU; Z = RES / SD
def boot_slope(x, y, g, B=B):
    ug, inv = np.unique(g, return_inverse=True); G = len(ug)
    s = np.stack([np.ones_like(x), x, y, x*x, x*y], 1)
    gs = np.zeros((G, 5)); np.add.at(gs, inv, s)
    def sl(t):
        n, sx, sy, sxx, sxy = t; v = n*sxx - sx*sx
        return (n*sxy - sx*sy)/v if v > 0 else np.nan
    pt = sl(gs.sum(0)); bs = []
    for _ in range(B):
        w = np.bincount(rng.integers(0, G, G), minlength=G)
        bs.append(sl(w @ gs))
    lo, hi = np.nanpercentile(bs, [2.5, 97.5]); return pt, lo, hi, G
def block(name, m):
    print(f"\n=== {name}: n_pg={m.sum()} games={len(np.unique(EID[m]))}")
    for lab, X, Yv in (("resid~mean prev3 resid (raw)", R3, RES), ("resid~mean prev5 resid (raw)", R5, RES),
                       ("z~mean prev3 z", Z3, Z), ("z~mean prev5 z", Z5, Z), ("resid~(raw last5 - exp)", RAW, RES), ("z~(raw5-exp)/sd", RAW/SD, Z)):
        out = []
        for fm in ["POOLED"] + FAMS:
            mm = m & ((fam == fm) if fm != "POOLED" else True)
            if mm.sum() < 200: continue
            if fm == "POOLED" and "raw" in lab and "z" not in lab: continue  # raw units not poolable
            pt, lo, hi, G = boot_slope(X[mm], Yv[mm], EID[mm])
            out.append(f"  {fm.replace('player_',''):12s} n={mm.sum():6d} g={G:5d} slope={pt:+.4f} [{lo:+.4f},{hi:+.4f}]")
        print(lab); print("\n".join(out))
def decile(name, m):
    print(f"\n--- decile check {name} (feature = z-mean prev5; deciles within market)")
    for fm in ["POOLED"] + FAMS:
        mm = m & ((fam == fm) if fm != "POOLED" else True)
        if mm.sum() < 500: continue
        x = Z5.copy(); idx = np.where(mm)[0]
        # decile within each family
        dec = np.zeros(len(x), int)
        for f2 in set(fam[idx]):
            ii = idx[fam[idx] == f2]; q = np.quantile(x[ii], [.1, .9])
            dec[ii[x[ii] <= q[0]]] = -1; dec[ii[x[ii] >= q[1]]] = 1
        res = []
        for lab, sel in (("bottom", dec == -1), ("top", dec == 1)):
            s = idx[dec[idx] == (-1 if lab == "bottom" else 1)]
            d = YO[s] - P[s]; g = EID[s]
            ug, inv = np.unique(g, return_inverse=True); gs = np.zeros((len(ug), 2)); np.add.at(gs, inv, np.stack([d, np.ones_like(d)], 1))
            bs = [ (w @ gs)[0]/(w @ gs)[1] for w in (np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug)) for _ in range(B))]
            lo, hi = np.percentile(bs, [2.5, 97.5])
            res.append(f"{lab}: n={len(s)} g={len(ug)} hit={YO[s].mean():.3f} p={P[s].mean():.3f} gap={d.mean():+.3f} [{lo:+.3f},{hi:+.3f}]")
        print(f"  {fm.replace('player_',''):12s} " + " | ".join(res))
print("rows", len(rows), "players with feature rows", len(feats))
print("excluded (<5 prior own games or <5 prior records, or sd=0) per family:", dict(excl), "of", dict(tot))
nba = TOUR == NBA
for name, m in (("TEST split (>=2026-07-01), all basketball", TS >= CUT),
                ("TEST split, NBA only (tournament 132)", (TS >= CUT) & nba),
                ("LATE holdout (>=2026-10-01), all", TS >= LATE),
                ("LATE holdout NBA", (TS >= LATE) & nba),
                ("TRAIN (<2026-07-01; constants fitted here) all", TS < CUT),
                ("TRAIN NBA", (TS < CUT) & nba)):
    if m.sum() < 300: print("\n", name, "n too small:", m.sum()); continue
    block(name, m); decile(name, m)
