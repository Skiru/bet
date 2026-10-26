"""Step 2: would a form shift of the player model's mean have beaten Superbet's price on settled shadow lines."""
import sys, glob, json, math, pickle, sqlite3, bisect, collections
from datetime import datetime, UTC
import numpy as np
sys.path.insert(0, "/Users/mkoziol/projects/bet/scripts/sofa")
import fit_player_model as fp
import bet.sofa.player_model as pm
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
CUT = int(datetime(2026,7,1,tzinfo=UTC).timestamp())
rows = pickle.load(open(f"{S}/rows.pkl","rb"))
# --- k per market, TRAIN only (ts < cut): OLS slope of raw residual on mean prev-5 residual
by = collections.defaultdict(list)
for r in rows: by[(r[2], r[3])].append(r)
hist_res = {}   # (pid,fam) -> (ts list, resid list)  all rows (pre-game residuals of each past game)
X = collections.defaultdict(list); Yv = collections.defaultdict(list)
for key, lst in by.items():
    lst.sort(key=lambda r: (r[1], r[0]))
    ts = [r[1] for r in lst]; res = [r[4]-r[5] for r in lst]
    hist_res[key] = (ts, res)
    for i in range(5, len(lst)):
        if lst[i][1] < CUT and lst[i][6] > 0:
            X[key[1]].append(np.mean(res[i-5:i])); Yv[key[1]].append(res[i])
K = {}
for f in FAMS:
    x = np.array(X[f]); y = np.array(Yv[f]); K[f] = float(((x-x.mean())*(y-y.mean())).sum()/((x-x.mean())**2).sum())
print("k per market (train only):", {k.replace('player_',''): round(v,4) for k,v in K.items()}, {k: len(v) for k,v in X.items()})
# --- settled lines
lines = {}
for fpath in sorted(glob.glob("/Users/mkoziol/projects/bet/runs/sofa/shadow/basketball/*/settled.json")):
    d = json.load(open(fpath))
    for seid, ev in d["events"].items():
        sid = ev.get("sofascore_event_id")
        if not sid: continue
        for g in ev.get("graded", []):
            fam = g.get("family")
            if fam not in FAMS or g.get("model_source") != "pregame" or g.get("model_p") is None or g.get("outcome") not in ("WIN","LOSS") or not g.get("odds") or g.get("model_player_id") is None: continue
            key = (seid, g["market_id"], g["subject"], g["line"], g["side"])
            lines[key] = dict(sid=int(sid), day=d["date"], fam=fam, pid=int(g["model_player_id"]), line=float(g["line"]), side=g["side"], odds=float(g["odds"]),
                              win=1 if g["outcome"]=="WIN" else 0, live_p=float(g["model_p"]), live_mean=g.get("model_mean"), actual=g.get("actual"),
                              nba=(ev.get("sofascore_tournament")=="NBA"), tour=ev.get("sofascore_tournament"), kick=ev.get("sofascore_start_utc"))
print("settled pregame lines", len(lines), "events", len({v['sid'] for v in lines.values()}))
# --- replay the records for those events
conn = sqlite3.connect(f"file:{S}/sofa_copy.db?mode=ro", uri=True, timeout=60)
hist = fp.History.from_db(conn, "basketball", team_from_side=True, any_team=False)
specs = fp.family_specs("basketball"); fidx = {s.family: i for i, s in enumerate(specs)}
prm = pm.load_params()["basketball"]
import math
def dist(rec, f, scale):
    own = fp.family_sample(rec, f, prm.max_sample); pool = rec.pools[prm.pool][f]
    # copy of pm.count_distribution with a mean scale on every mu
    n = len(own); seconds = sum(s for s,_ in own); total = sum(v for _,v in own); mean_s = seconds/n
    pool_rate = pool.sum_v/pool.sum_s if pool.sum_s > 0 else total/seconds
    k = prm.prior_games*mean_s; rate = (total+k*pool_rate)/(seconds+k)
    w = [0.5**(i/prm.hl_minutes) for i in range(n)]; wt = sum(w)
    es = sum(a*s for a,(s,_) in zip(w, own))/wt; sp = sum(a*(s-es)**2 for a,(s,_) in zip(w, own))/wt
    cv = math.sqrt(sp)/max(es,1.0); sigma = math.sqrt(prm.sig_a**2+cv**2)
    po = pm.pearson_dispersion(own); parts = [(float(n), po)] if po is not None else []
    if pool.phi is not None: parts.append((float(prm.k_phi), pool.phi))
    ww = sum(a for a,_ in parts); phi = max(sum(a*b for a,b in parts)/ww if ww > 0 else 1.0, 1.0)
    norm = sum(pm._GH_WEIGHTS)
    mus = [scale*rate*es*math.exp(sigma*math.sqrt(2.0)*x-0.5*sigma*sigma) for x in pm._GH_NODES]
    kmax = int(max(mus)+12.0*math.sqrt(max(phi*max(mus),1.0))+12); pmf = [0.0]*(kmax+1)
    for a, mu in zip(pm._GH_WEIGHTS, mus):
        for i, v in enumerate(pm.nb_pmf(mu, phi*mu, kmax)): pmf[i] += a/norm*v
    return pmf, sum(a/norm*mu for a, mu in zip(pm._GH_WEIGHTS, mus))
def p_side(pmf, line, side, scale_b=prm.calibration_b):
    over = min(max(sum(m for k, m in enumerate(pmf) if k > line), 1e-6), 1-1e-6)
    over_c = pm.calibrate_side(over, scale_b)
    return over_c if side == "OVER" else 1.0 - over_c, over
recs = {}
out = []; miss = collections.Counter()
for sid in sorted({v['sid'] for v in lines.values()}):
    for r in fp.replay_game(hist, sid, specs): recs[(sid, r.pid)] = r
for key, L in lines.items():
    r = recs.get((L['sid'], L['pid']))
    if r is None: miss['no_record'] += 1; continue
    f = fidx[L['fam']]
    if len(fp.family_sample(r, f, prm.max_sample)) < pm.MIN_APPEARANCES: miss['thin'] += 1; continue
    pmf0, m0 = dist(r, f, 1.0)
    ts, res = hist_res.get((L['pid'], L['fam']), ([], []))
    i = bisect.bisect_left(ts, r.ts)          # strictly earlier games only
    if i >= 5:
        r5 = float(np.mean(res[i-5:i])); shift = K[L['fam']]*r5
        scale = max(m0+shift, 0.05*m0 if m0 > 0 else 0.05)/m0 if m0 > 0 else 1.0
        has = True
    else: scale, has, r5 = 1.0, False, 0.0
    pmf1, m1 = dist(r, f, scale)
    p0, _ = p_side(pmf0, L['line'], L['side']); p1, _ = p_side(pmf1, L['line'], L['side'])
    out.append(dict(L, key=key, p_old=p0, p_new=p1, m0=m0, m1=m1, r5=r5, has_form=has))
print("usable", len(out), "dropped", dict(miss))
a = np.array([o['p_old'] for o in out]); b = np.array([o['live_p'] for o in out])
print("replayed old p vs live model_p: mean abs diff %.4f, corr %.4f, share |diff|<0.01: %.3f" % (np.abs(a-b).mean(), np.corrcoef(a,b)[0,1], (np.abs(a-b)<0.01).mean()))
mm = np.array([(o['m0'], o['live_mean']) for o in out if o['live_mean'] is not None]); print("mean replay vs live mean: mean abs diff %.4f" % np.abs(mm[:,0]-mm[:,1]).mean())
pickle.dump((K, out), open(f"{S}/price_rows.pkl","wb"))
