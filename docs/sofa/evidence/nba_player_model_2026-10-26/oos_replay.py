"""Step 2b: general OOS check on the TEST-split replay: old vs trend-corrected pmf (mean shifted by k*mean prev-5 residual; k from TRAIN only)."""
import sys, math, pickle, bisect, collections, sqlite3, multiprocessing
from datetime import datetime, UTC
import numpy as np
sys.path.insert(0, "/Users/mkoziol/projects/bet/scripts/sofa")
import fit_player_model as fp
import bet.sofa.player_model as pm
S = "/private/tmp/claude-501/-Users-mkoziol-projects-bet/701c2cc6-a874-47d8-924e-5ecfaf45df41/scratchpad"
FAMS = ["player_points","player_rebounds","player_assists","player_threes","player_pts_reb_ast"]
CUT = int(datetime(2026,7,1,tzinfo=UTC).timestamp())
rows = pickle.load(open(f"{S}/rows.pkl","rb"))
K, _ = pickle.load(open(f"{S}/price_rows.pkl","rb"))
by = collections.defaultdict(list); tour = {}
for r in rows: by[(r[2], r[3])].append(r); tour[r[0]] = r[12]
HR = {}
for key, lst in by.items():
    lst.sort(key=lambda r: (r[1], r[0])); HR[key] = ([r[1] for r in lst], [r[4]-r[5] for r in lst])
# replay line per (eid,pid,fam) as in step 1
LINE = {(r[0], r[2], r[3]): r[9] for r in rows if r[1] >= CUT}
del by
conn = sqlite3.connect(f"file:{S}/sofa_copy.db?mode=ro", uri=True, timeout=60)
hist = fp.History.from_db(conn, "basketball", team_from_side=True, any_team=False)
specs = fp.family_specs("basketball"); fidx = {s.family: i for i, s in enumerate(specs)}
prm = pm.load_params()["basketball"]

sys.path.insert(0, S)
from distlib import dist, p_side
test_eids = sorted(e for e, (ts, h, a) in hist.events.items() if ts >= CUT and e in hist.lineups)
def work(eids):
    out = []
    for eid in eids:
        for r in fp.replay_game(hist, eid, specs):
            for fam in FAMS:
                f = fidx[fam]; y = r.act[f]
                if y is None or len(fp.family_sample(r, f, prm.max_sample)) < pm.MIN_APPEARANCES: continue
                ts, res = HR.get((r.pid, fam), ([], []))
                i = bisect.bisect_left(ts, r.ts)
                if i < 5: continue
                pmf0, m0 = dist(r, f, 1.0)
                if m0 <= 0: continue
                shift = K[fam]*float(np.mean(res[i-5:i])); sc = max(m0+shift, 0.05*m0)/m0
                pmf1, m1 = dist(r, f, sc)
                yi = int(round(y)); ll0 = -math.log(max(pmf0[yi] if yi < len(pmf0) else 0, 1e-12)); ll1 = -math.log(max(pmf1[yi] if yi < len(pmf1) else 0, 1e-12))
                line = LINE.get((eid, r.pid, fam))
                if line is None: continue
                p0, _ = p_side(pmf0, line, "OVER"); p1, _ = p_side(pmf1, line, "OVER")
                out.append((eid, r.ts, fam, float(y), m0, m1, ll0, ll1, p0, p1, 1.0 if y > line else 0.0, line, tour.get(eid)))
    return out
if __name__ == "__main__":
    chunks = [test_eids[j::56] for j in range(56)]
    with multiprocessing.get_context("fork").Pool(7) as pool: parts = pool.map(work, chunks)
    res = [x for p in parts for x in p]
    pickle.dump(res, open(f"{S}/oos_rows.pkl", "wb")); print("rows", len(res), "games", len({x[0] for x in res}))
