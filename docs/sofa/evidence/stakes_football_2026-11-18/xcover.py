"""Which eligible matches have recorded model rows in the schedule study's
outcome-free X files (rows only; the y stores are never opened)."""
import gzip, pickle, sys
from collections import defaultdict
from pathlib import Path
import pandas as pd
S=sys.argv[1]
D=Path("data/refit_2026-11-08_schedule/full")
mk=defaultdict(set)
for tier in ("dev","exam"):
    for p in sorted((D/tier/"rows").glob("*.pkl.gz")):
        for r in pickle.load(gzip.open(p)):
            eid, ts, comp, sport, market = r[:5]
            if sport!="football": continue
            fam = ("goals" if market.startswith("goals") else "corners" if market.startswith("corners")
                   else "shots" if market.startswith(("shots","shots_on")) else
                   "cards" if market.startswith(("cards","fouls")) else None)
            if fam: mk[fam].add(eid)
            mk["any"].add(eid)
pickle.dump({k:v for k,v in mk.items()}, open(f"{S}/xcover.pkl","wb"))
x=pd.read_pickle(f"{S}/states2.pkl")
s=pd.concat([x.assign(state=x.home),x.assign(state=x.away)])
order=["MUST_WIN","ALIVE","SECURED","DEAD","AMBIGUOUS"]
for fam in ("goals","corners","shots","cards"):
    t=s[s.event_id.isin(mk.get(fam,set()))]
    print(f"\n== X rows ({fam}): side-matches by kind x state x period")
    print(t.groupby(["kind","state","period"]).size().unstack().fillna(0).astype(int).reindex(order, level=1).to_string())
print("\nX max ts:", max(1,1))
