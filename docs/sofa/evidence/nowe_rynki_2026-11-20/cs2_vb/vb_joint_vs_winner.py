"""Re-derive the 1.Set/Mecz favourite gap a second way: Superbet's own winner (745) and set-1 winner (744 p1)
from the SAME snapshot (SHADOW snapshots.jsonl, same fetched_at), vs the 4-way's favourite 'same' selection."""
import json, glob, collections, random
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
R = [json.loads(l) for l in open("vb_rows.jsonl") if json.loads(l)["mid"] == 230059]
want = {(r["sb"], r["ts"][:19]) for r in R}
snap = {}
for f in glob.glob(f"{ROOT}/shadow/volleyball/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line); k = (s["superbet_event_id"], s["fetched_at_utc"][:19])
        if k in want:
            d = {}
            for ln in s["lines"]:
                if ln["market_id"] == 745: d[("w", ln["side"])] = ln["odds"]
                if ln["market_id"] == 744 and ln["period"] == 1: d[("s1", ln["side"])] = ln["odds"]
            snap[k] = (s["team1"], d)
fav = {}
for r in R:
    if r["kind"] == "same" and (r["sid"] not in fav or r["fair"] > fav[r["sid"]]["fair"]): fav[r["sid"]] = r
rows = []
for r in fav.values():
    k = (r["sb"], r["ts"][:19])
    if k not in snap: continue
    t1, d = snap[k]
    side = "T1" if r["sel"].startswith(t1 + "/") else "T2"
    oth = "T2" if side == "T1" else "T1"
    if not all(x in d for x in (("w", side), ("w", oth), ("s1", side), ("s1", oth))): continue
    fw = (1/d[("w", side)]) / (1/d[("w", side)] + 1/d[("w", oth)])
    fs = (1/d[("s1", side)]) / (1/d[("s1", side)] + 1/d[("s1", oth)])
    rows.append(dict(r, fw=fw, fs=fs, inv=1/r["odds"]))
n = len(rows); print("favourite 'same' rows joined to winner + set-1 markets:", n)
m = lambda k: sum(x[k] for x in rows) / n
print("4-way fair %.3f | 4-way raw 1/odds %.3f | model %.3f | realised %.3f" % (m("fair"), m("inv"), m("p"), m("y")))
print("winner fair %.3f, set-1 fair %.3f, independence product %.3f" % (m("fw"), m("fs"), sum(x["fw"] * x["fs"] for x in rows) / n))
# realised favourite match win and set-1 win: need results - y_same only; recompute from vb_rows split rows
for lo in (0.0, 0.65, 0.70):
    K = [x for x in rows if x["fair"] >= lo or (lo == 0.0)]
    K = [x for x in rows if x["fair"] >= lo]
    if K: print(f"4-way fair>={lo}: n {len(K)} fair {sum(x['fair'] for x in K)/len(K):.3f} 1/odds {sum(x['inv'] for x in K)/len(K):.3f} winner fair {sum(x['fw'] for x in K)/len(K):.3f} set1 fair {sum(x['fs'] for x in K)/len(K):.3f} realised {sum(x['y'] for x in K)/len(K):.3f}")

# realised favourite set-1 and match wins in the same events (from the 4 selections' outcomes)
by = collections.defaultdict(dict)
for r in R: by[r["sid"]][r["sel"]] = r["y"]
s1 = mw = 0; w_fair = s_fair = 0.0
for x in rows:
    t1, _ = snap[(x["sb"], x["ts"][:19])]
    sels = by[x["sid"]]; fav_name = x["sel"].split("/")[0] if x["sel"].count("/") == 1 else x["sel"][: len(x["sel"]) // 2]
    fs1 = sum(y for nm, y in sels.items() if nm.startswith(fav_name + "/"))
    fmw = sum(y for nm, y in sels.items() if nm.endswith("/" + fav_name))
    s1 += fs1; mw += fmw
print("realised favourite set-1 %.3f (fair %.3f), match %.3f (fair %.3f), n %d" % (s1 / n, m("fs"), mw / n, m("fw"), n))
