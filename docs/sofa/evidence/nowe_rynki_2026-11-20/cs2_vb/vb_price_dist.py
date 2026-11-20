"""Volleyball candidate markets: de-vigged p distribution at the last pre-start snapshot per event (read-only).
Groups: 230059 the 4 selections; 786 / 100080 / 100081 two-way pairs (same sbv); 240723/240724/235046 whole group."""
import json, glob, collections, statistics
from datetime import datetime
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
ko = {}
for f in glob.glob(f"{ROOT}/shadow/volleyball/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line); ko[s["superbet_event_id"]] = s["kickoff_utc"]
groups = collections.defaultdict(dict)
for l in open("unmapped_candidates.jsonl"):
    r = json.loads(l)
    if r["sport"] != "volleyball" or r["mid"] in (200849, 200852): continue
    key = r["sbv"] if r["mid"] in (786, 100080, 100081, 235045, 235046) else ""
    groups[(r["mid"], r["sb"], key, r["mname"] if r["mid"] in (100080, 100081) else "")].setdefault(r["ts"], {})[r["name"]] = r["price"]
res = collections.defaultdict(list); nokick = 0; events = collections.defaultdict(set)
for (mid, sb, key, mn), byts in groups.items():
    k = ko.get(sb)
    if k is None: nokick += 1; continue
    pre = [t for t in byts if ts(t) < ts(k)]
    if not pre: continue
    sel = byts[max(pre)]
    if mid in (786, 100080, 100081) and len(sel) != 2: continue
    inv = {n: 1 / p for n, p in sel.items()}; tot = sum(inv.values())
    for n, p in sel.items():
        res[mid].append((inv[n] / tot, p, tot - 1, sb, n))
    events[mid].add(sb)
print("groups without kickoff", nokick)
for mid in sorted(res):
    R = res[mid]; fair = sorted(x[0] for x in R)
    q = [round(fair[int(i * (len(fair) - 1))], 3) for i in (0, .1, .25, .5, .75, .9, .99, 1)]
    ge70 = [x for x in R if x[0] >= 0.70]
    zone = [x for x in R if x[0] >= 0.70 and 1.09 <= x[1] <= 1.43]
    print(f"{mid}: events {len(events[mid])}, selections {len(R)}, overround mean {statistics.mean(x[2] for x in R)/1:.3f} (per group, repeated per selection)")
    print(f"   fair p quantiles 0/10/25/50/75/90/99/100%: {q}")
    print(f"   fair >= 0.70: {len(ge70)} selections on {len({x[3] for x in ge70})} events; zone 1.09-1.43: {len(zone)} on {len({x[3] for x in zone})} events")
    if mid == 230059:
        kinds = collections.Counter()
        for x in ge70:
            nm = x[4]; h = len(nm) // 2; kinds["same team (set1 & match)" if len(nm) % 2 == 1 and nm[h] == "/" and nm[:h] == nm[h+1:] else "split"] += 1
        print("   >=0.70 by kind:", dict(kinds))
        pr = sorted(x[1] for x in ge70); print("   their prices:", pr[:3], "median", pr[len(pr)//2] if pr else None, "max", pr[-1] if pr else None)
    if mid == 786:
        lines = collections.Counter(x[4].rsplit("(", 1)[-1].rstrip(")") for x in R)
        print("   lines offered:", dict(lines))
json.dump({str(k): v for k, v in res.items()}, open("vb_price_dist.json", "w"))
