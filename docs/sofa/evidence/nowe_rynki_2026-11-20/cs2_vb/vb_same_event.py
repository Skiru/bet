"""Volleyball 'Czy będzie 4./5. set?' vs SHADOW's sets_total 3.5 / 4.5: same snapshot price comparison."""
import json, glob, collections
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
yn = collections.defaultdict(dict)  # (sb, ts[:16]) -> {(mid, name): price}
for l in open("unmapped_candidates.jsonl"):
    r = json.loads(l)
    if r["mid"] in (200849, 200852):
        yn[(r["sb"], r["ts"][:19])][(r["mid"], r["name"])] = r["price"]
st = {}
for f in glob.glob(f"{ROOT}/shadow/volleyball/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line)
        k = (s["superbet_event_id"], s["fetched_at_utc"][:19])
        if k not in yn: continue
        d = {}
        for ln in s["lines"]:
            if ln["family"] == "sets_total": d[(ln["line"], ln["side"])] = ln["odds"]
            if ln["family"] == "exact_sets": d[("ex", ln["side"])] = ln["odds"]
        st[k] = d
both = 0; same = collections.Counter(); diffs = []
for k, v in yn.items():
    if k not in st: continue
    both += 1
    d = st[k]
    for mid, line in ((200849, 4.5), (200852, 3.5)):
        y, n = v.get((mid, "tak")), v.get((mid, "nie"))
        o, u = d.get((line, "OVER")), d.get((line, "UNDER"))
        if None in (y, n, o, u): same[(mid, "missing")] += 1; continue
        if (y, n) == (o, u): same[(mid, "identical")] += 1
        else:
            same[(mid, "differs")] += 1; diffs.append((k, mid, y, n, o, u))
print("joined snapshots", both, "of", len(yn), dict(same))
for x in diffs[:15]: print(x)

# fair-p difference and which side's price is higher, per event (last pre-start snapshot pair)
import statistics
last = {}
for k in yn:
    if k in st: last.setdefault(k[0], []).append(k)
gaps = collections.defaultdict(list); better = collections.Counter(); mov = collections.defaultdict(list)
for sb, ks in last.items():
    k = max(ks, key=lambda x: x[1]); v, d = yn[k], st[k]
    for mid, line in ((200849, 4.5), (200852, 3.5)):
        y, n = v.get((mid, "tak")), v.get((mid, "nie")); o, u = d.get((line, "OVER")), d.get((line, "UNDER"))
        if None in (y, n, o, u): continue
        fy = (1/y)/(1/y+1/n); fo = (1/o)/(1/o+1/u)
        gaps[mid].append(fy - fo)
        mov[mid].append((1/y+1/n-1, 1/o+1/u-1))
        for side, a, b in (("tak/OVER", y, o), ("nie/UNDER", n, u)):
            better[(mid, side, "yn>st" if a > b else "yn<st" if a < b else "eq")] += 1
for mid in gaps:
    g = gaps[mid]; m = mov[mid]
    print(mid, "events", len(g), "fair p(yes) - p(OVER): mean %+.4f median %+.4f |max| %.3f" % (statistics.mean(g), statistics.median(g), max(abs(x) for x in g)),
          "overround yn %.3f st %.3f" % (statistics.mean(a for a, b in m), statistics.mean(b for a, b in m)))
for k, c in sorted(better.items()): print(k, c)
