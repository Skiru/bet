import sys, itertools
from collections import Counter
import pandas as pd
sys.path.insert(0, sys.argv[1])
from stakes_state import final_state, H2H
d = pd.read_pickle(sys.argv[1] + "/listed.pkl")
u = d[(d.ut == 10783) & (d.season == 89945) & (d.st != "canceled")]
cut = pd.Timestamp("2026-11-16").timestamp()
for tname, g in u.groupby("tname"):
    teams = sorted(set(g.hid) | set(g.aid)); name = {}
    for r in g.itertuples(): name[r.hid] = r.hname; name[r.aid] = r.aname
    pts = {t: 0 for t in teams}; pc = Counter()
    played = g[(g.st == "finished") & (g.start_ts < cut)]
    for r in played.itertuples():
        pts[r.hid] += 3 if r.hg > r.ag else 1 if r.hg == r.ag else 0
        pts[r.aid] += 3 if r.ag > r.hg else 1 if r.hg == r.ag else 0
    for r in g.itertuples(): pc[frozenset((r.hid, r.aid))] += 1
    m = 2
    rem = [r for r in g.itertuples() if not (r.st == "finished" and r.start_ts < cut)]
    remaining = [(r.hid, r.aid) for r in rem]
    for p in itertools.combinations(teams, 2):
        for _ in range(m - pc[frozenset(p)]): remaining.append(tuple(p))
    bounds = [1, 2, 3] if len(teams) == 4 else [1]
    print(f"\n{tname}  table: " + ", ".join(f"{name[t]} {pts[t]}" for t in sorted(teams, key=lambda t: -pts[t])))
    for i, mt in enumerate(remaining):
        others = remaining[:i] + remaining[i + 1:]
        out = []
        for s in mt:
            st, tb = final_state(pts, others, mt, s, bounds, H2H([(r.hid,r.aid,int(r.hg),int(r.ag)) for r in played.itertuples()], 2))
            out.append(f"{name[s]}={st}{'(tb)' if tb else ''}")
        print("   ", " vs ".join(out))
