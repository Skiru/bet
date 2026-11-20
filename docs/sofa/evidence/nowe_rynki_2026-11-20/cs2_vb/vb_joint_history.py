"""Rally-model walk-forward on the cached history: '1.Set/Mecz' joint (set-1 winner x match winner) and
1st-set points handicap, as of each match's start (vb_point_pricer.PARAMS, 4,000 sims seeded by id).
Window [FROM, TO); every STEP-th match (deterministic subsample) to bound time. Writes vb_joint_hist.jsonl."""
import sys, json, pickle, time
from datetime import datetime, timezone
sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import vb_point_pricer as vpp
from bet.sofa import volleyball_point_model as vpm
FROM, TO, STEP = sys.argv[1], sys.argv[2], int(sys.argv[3])
t0 = datetime.fromisoformat(FROM).replace(tzinfo=timezone.utc).timestamp(); t1 = datetime.fromisoformat(TO).replace(tzinfo=timezone.utc).timestamp()
raw = pickle.load(open("vb_history.pkl", "rb"))
H = sorted((vpm.VbMatch(int(e), int(ts), int(c), int(h), int(a), bool(w), tuple(hs), tuple(as_)) for e, ts, c, h, a, w, hs, as_ in raw), key=lambda m: (m.ts, m.event_id))
win = [m for m in H if t0 <= m.ts < t1 and len(m.home_sets) >= 3]
want = {m.event_id for m in win[::STEP]}
fc = vpm.walk_forward(H, want, vpp.PARAMS)
out = open("vb_joint_hist.jsonl", "w"); t = time.time(); n = 0
for m in win:
    if m.event_id not in fc: continue
    f = fc[m.event_id]
    if min(f.rated) < 5: continue  # a side the rating has not seen 5 times: skipped (reported)
    s = vpm.simulate(f, vpp.PARAMS, n=vpp.N_SIMS, seed=vpp.seed_of(m.event_id))
    P = s.points
    s1 = P[:, 0, 0] > P[:, 0, 1]; w1 = (P[:, :, 0] > P[:, :, 1]).sum(axis=1); w2 = (P[:, :, 1] > P[:, :, 0]).sum(axis=1); m1 = w1 > w2
    d1 = P[:, 0, 0] - P[:, 0, 1]
    hs, as_ = m.home_sets, m.away_sets
    a_s1 = hs[0] > as_[0]; a_m1 = sum(x > y for x, y in zip(hs, as_)) > sum(y > x for x, y in zip(hs, as_))
    joint = {f"{int(x)}{int(y)}": float(((s1 == x) & (m1 == y)).mean()) for x in (True, False) for y in (True, False)}
    hcp = {str(L): float((d1 + L > 0).mean()) for L in (-7.5, -6.5, -5.5, -4.5, -3.5, -2.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5)}
    out.write(json.dumps({"eid": m.event_id, "ts": m.ts, "women": m.women, "joint": joint, "y": f"{int(a_s1)}{int(a_m1)}",
                          "hcp": hcp, "d1": hs[0] - as_[0]}) + "\n"); n += 1
print("rows", n, "of window", len(win), "sec", round(time.time() - t))
