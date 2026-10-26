import pickle, numpy as np, collections
from datetime import datetime, UTC
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
rng = np.random.default_rng(5); B = 2000
CUT = int(datetime(2026,7,1,tzinfo=UTC).timestamp()); LATE = int(datetime(2026,10,1,tzinfo=UTC).timestamp())
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
rows, log = pickle.load(open(f"{S}/topup_rows.pkl","rb"))
eid = np.array([r[0] for r in rows], np.int64); ts = np.array([r[1] for r in rows], np.int64); pid = np.array([r[2] for r in rows], np.int64); fam = np.array([r[3] for r in rows])
p = np.array([r[5] for r in rows]); yo = np.array([r[6] for r in rows]); n_own = np.array([r[8] for r in rows]); nfo = np.array([r[9] for r in rows]); nfa = np.array([r[10] for r in rows])
tour = np.array([(r[11] or 0) for r in rows]); naive = np.array([np.nan if r[12] is None else r[12] for r in rows]); del rows
nba = tour == 132; thin = n_own < 5
ev_ts = {}; ev_nba = {}
for e, t, nb in zip(eid[::7], ts[::7], nba[::7]): ev_ts[e] = t; ev_nba[e] = nb
# fill all
u, idx = np.unique(eid, return_index=True)
ev_ts = dict(zip(u, ts[idx])); ev_nba = dict(zip(u, nba[idx]))
print("rows", len(eid), "thin(top-up) rows", thin.sum(), "normal rows", (~thin).sum())
# ---- (1) coverage from LOG
le = np.array([l[0] for l in log], np.int64); lp = np.array([l[1] for l in log], np.int64); lo = np.array([l[2] for l in log]); lf = np.array([len(l[3]) for l in log])
lts = np.array([ev_ts.get(e, -1) for e in le]); lnba = np.array([ev_nba.get(e, False) for e in le]); known = lts >= 0
print("LOG target player-games", len(le), "with event in rows", known.sum())
def cov(name, m):
    m = m & known; th = m & (lo < 5)
    print(f"\n-- coverage {name}: player-games {m.sum()}, thin today (own<5) {th.sum()} ({th.mean()*0 + th.sum()/max(m.sum(),1):.1%}), own=0: {(th&(lo==0)).sum()}")
    print(f"   thin with >=1 foreign game found {(th&(lf>0)).sum()}; own+foreign >=5 appearances: {(th&(lo+lf>=5)).sum()}; still <5 after top-up: {(th&(lo+lf<5)).sum()}")
    # per market: top-up rows for thin events
    keys = set(zip(le[th].tolist(), lp[th].tolist()))
    for f in FAMS:
        mm = thin & (fam == f) & np.isin(eid, le[th])
        # restrict to slice by ts/nba of events
        print(f"   {f.replace('player_',''):12s} thin player-games priced under top-up: {mm_count(f, th)}")
tk = None
def mm_count(f, th):
    return None
# simpler: build per slice sets of (eid,pid) thin
thin_keys = {}
for slice_name, sm in (("TEST>=07-01 all", lambda t, nb: t >= CUT), ("TEST NBA", lambda t, nb: (t >= CUT) & nb), ("TEST non-NBA", lambda t, nb: (t >= CUT) & ~nb), ("LATE>=10-01 all", lambda t, nb: t >= LATE), ("LATE NBA", lambda t, nb: (t >= LATE) & nb), ("LATE non-NBA", lambda t, nb: (t >= LATE) & ~nb), ("TRAIN <07-01", lambda t, nb: t < CUT)):
    m = known & sm(lts, lnba); th = m & (lo < 5)
    pri = thin & sm(ts, nba)
    print(f"\n-- {slice_name}: target player-games {m.sum()} | thin today {th.sum()} ({th.sum()/max(m.sum(),1):.1%}) own=0 {(th&(lo==0)).sum()} | foreign found {(th&(lf>0)).sum()} | own+foreign>=5 {(th&(lo+lf>=5)).sum()} | still <5 {(th&(lo+lf<5)).sum()}")
    print("   priced thin player-games per market (rows with a p under top-up): " + ", ".join(f"{f.replace('player_','')} {(pri&(fam==f)).sum()} ({(pri&(fam==f)).sum()/max(th.sum(),1):.0%} of thin)" for f in FAMS))
# ---- (2) quality
def ll(q, y): q = np.clip(q,1e-6,1-1e-6); return -(y*np.log(q)+(1-y)*np.log(1-q))
def ci(v, g):
    ug, inv = np.unique(g, return_inverse=True); G = len(ug); s = np.zeros((G,2)); np.add.at(s, inv, np.stack([v, np.ones_like(v)],1))
    pt = s[:,0].sum()/s[:,1].sum(); bs = np.empty(B)
    for i in range(B): t = np.bincount(rng.integers(0,G,G), minlength=G) @ s; bs[i] = t[0]/t[1]
    lo_, hi_ = np.percentile(bs, [2.5,97.5]); return pt, lo_, hi_
BK = [(.0,.3),(.3,.4),(.4,.5),(.5,.6),(.6,.7),(.7,.8),(.8,1.01)]
def both(q, y): return np.concatenate([ll(q,y), ll(1-q,1-y)]), np.concatenate([(q-y)**2, (1-q-(1-y))**2])
def ece(q, y):
    t = 0
    for a, b in zip(np.arange(0,.9,.1), np.arange(.1,1.01,.1)):
        m = (q>=a)&(q<b+1e-9 if b>=1 else q<b); t += abs(y[m].mean()-q[m].mean())*m.sum() if m.any() else 0
    return t/len(q)
def rel(q, y, tag):
    out = []
    for side, qq, yy in (("OVER", q, y), ("UNDER", 1-q, 1-y)):
        c = []
        for a, b in BK[3:]:
            m = (qq>=a)&(qq<b)
            if m.sum() >= 30: c.append(f"{a:.1f}-{min(b,1):.1f} n={m.sum()} p={qq[m].mean():.3f} hit={yy[m].mean():.3f}({yy[m].mean()-qq[m].mean():+.3f})")
        out.append(f"     {tag} {side}: " + " | ".join(c))
    return "\n".join(out)
thin_pids = set(pid[thin].tolist()); same = np.isin(pid, list(thin_pids)) & ~thin
def quality(name, sm):
    T = thin & sm; N = same & sm & (n_own >= 5) & (n_own < 10); NA = (~thin) & sm
    print(f"\n== QUALITY {name}: top-up rows {T.sum()} games {len(np.unique(eid[T]))} players {len(np.unique(pid[T]))}")
    if T.sum() < 300: return
    for lab, M in (("top-up p (thin players)", T), ("same players once own 5-9 games", N), ("all normal players", NA)):
        l, b = both(p[M], yo[M]); print(f"   {lab:34s} n={M.sum():7d} logloss {l.mean():.4f} Brier {b.mean():.4f} ECE {ece(p[M], yo[M]):.4f}")
    Tn = T & ~np.isnan(naive); l1, b1 = both(p[Tn], yo[Tn]); l2, b2 = both(naive[Tn], yo[Tn]); g2 = np.concatenate([eid[Tn], eid[Tn]])
    d1 = ci(l1-l2, g2); d2 = ci(b1-b2, g2)
    print(f"   top-up minus naive pool-mean p (n={Tn.sum()}): dLL {d1[0]:+.4f} [{d1[1]:+.4f},{d1[2]:+.4f}] dBrier {d2[0]:+.4f} [{d2[1]:+.4f},{d2[2]:+.4f}] (naive logloss {l2.mean():.4f}, Brier {b2.mean():.4f})")
    # CI of the top-up's own logloss minus the same-player normal logloss (unpaired)
    print(rel(p[T], yo[T], "top-up")); print(rel(p[N], yo[N], "same players normal")) if N.sum() > 300 else None
    # per market logloss of top-up vs naive
    for f in FAMS:
        M = Tn & (fam == f)
        if M.sum() < 300: continue
        a, bb = both(p[M], yo[M]); c, d = both(naive[M], yo[M]); g = np.concatenate([eid[M], eid[M]]); r = ci(a-c, g)
        print(f"     {f.replace('player_',''):12s} n={M.sum()} topup LL {a.mean():.4f} naive {c.mean():.4f} d {r[0]:+.4f} [{r[1]:+.4f},{r[2]:+.4f}]")
for nm, sm in (("TEST>=07-01 all", ts >= CUT), ("TEST NBA", (ts >= CUT) & nba), ("TEST non-NBA", (ts >= CUT) & ~nba), ("LATE>=10-01 all", ts >= LATE), ("LATE NBA", (ts >= LATE) & nba), ("TRAIN all", ts < CUT), ("TRAIN NBA", (ts < CUT) & nba)): quality(nm, sm)
# by own size
print("\n== top-up rows by own appearances (TEST all): n_own 0 / 1-2 / 3-4")
for lab, m in (("own=0", n_own == 0), ("own 1-2", (n_own >= 1) & (n_own <= 2)), ("own 3-4", (n_own >= 3) & (n_own <= 4))):
    M = thin & m & (ts >= CUT)
    if M.sum() > 300: l, b = both(p[M], yo[M]); print(f"   {lab}: n={M.sum()} logloss {l.mean():.4f} Brier {b.mean():.4f} over gap {yo[M].mean()-p[M].mean():+.3f}")
# ---- (3) settled lines
St = pickle.load(open(f"{S}/topup_settled.pkl","rb"))
print(f"\n== SETTLED Superbet THIN_SAMPLE lines 2026-10-03..10-25 (model_p null, THIN_SAMPLE, player id known): {len(St)}; priced under top-up {sum(1 for o in St if o['p'] is not None)}; NBA {sum(1 for o in St if o['nba'])} (priced {sum(1 for o in St if o['nba'] and o['p'] is not None)})")
Sp = [o for o in St if o["p"] is not None]
q = np.array([o["p"] for o in Sp]); w = np.array([o["win"] for o in Sp], float); od = np.array([o["odds"] for o in Sp]); sid = np.array([o["sid"] for o in Sp]); sf = np.array([o["fam"] for o in Sp]); sn = np.array([o["nba"] for o in Sp]); ss = np.array([o["side"] for o in Sp])
print("  games", len(np.unique(sid)), "NBA games", len(np.unique(sid[sn])), "other games", len(np.unique(sid[~sn])))
l = ll(q, w); b = (q-w)**2; print(f"  all priced: logloss {l.mean():.4f} Brier {b.mean():.4f} mean p {q.mean():.3f} hit {w.mean():.3f} | vs 0.5 baseline logloss 0.6931")
for lab, m in (("NBA", sn), ("non-NBA", ~sn)): 
    if m.sum(): print(f"  {lab}: n={m.sum()} logloss {ll(q[m],w[m]).mean():.4f} Brier {((q[m]-w[m])**2).mean():.4f} mean p {q[m].mean():.3f} hit {w[m].mean():.3f}")
for side in ("OVER","UNDER"):
    c = []
    for a, bb in BK:
        m = (ss == side) & (q >= a) & (q < bb)
        if m.sum() >= 20: c.append(f"{a:.1f}-{min(bb,1):.1f} n={m.sum()} p={q[m].mean():.3f} hit={w[m].mean():.3f} 1/odds={np.mean(1/od[m]):.3f}")
    print(f"  {side}: " + " | ".join(c))
for f in ["ALL"] + FAMS:
    m = (sf == f) if f != "ALL" else np.ones(len(q), bool); c = m & (q >= .7); pr = c & (q*od >= .9)
    u = np.where(w[pr] == 1, od[pr]-1, -1.0); r = ci(u, sid[pr]) if pr.sum() > 5 else (np.nan,)*3
    print(f"  {f.replace('player_',''):12s} priced {m.sum()} | p>=.70: {c.sum()} hit {w[c].mean() if c.sum() else float('nan'):.3f} p {q[c].mean() if c.sum() else float('nan'):.3f} 1/odds {np.mean(1/od[c]) if c.sum() else float('nan'):.3f} | p>=.70 & p*odds>=.90: {pr.sum()} units/line {r[0]:+.3f} [{r[1]:+.3f},{r[2]:+.3f}]")
