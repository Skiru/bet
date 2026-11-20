"""CS2: which rounds_handicap lines does the read snapshot carry on events quoting 231535/231548; names of 231548."""
import gzip, json, glob, collections, os
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
days = [f"2026-11-{d:02d}" for d in range(5, 22)]
evs = set(); n48 = collections.Counter(); zone = collections.Counter()
for d in days:
    for f in glob.glob(f"{ROOT}/{d}/unmapped_prices/cs2_*.jsonl.gz"):
        for line in gzip.open(f, "rt"):
            r = json.loads(line)
            if r["marketId"] in (231535, 231548) and r.get("status") == "active":
                evs.add(r["superbet_event_id"])
                if r["marketId"] == 231548: n48[r["name"][:30]] += 1
                if 1.09 <= r["price"] <= 1.43: zone[(r["marketId"], r["name"][:3])] += 1
lines = collections.defaultdict(set); fams = collections.Counter()
for d in days:
    p = f"{ROOT}/cs2/{d}/snapshots.jsonl"
    if not os.path.exists(p): continue
    for line in open(p):
        s = json.loads(line)
        if s["superbet_event_id"] in evs:
            for l in s["lines"]:
                if l["family"] == "rounds_handicap": lines[s["superbet_event_id"]].add(l["line"])
                fams[l["family"]] += 0
            fams["_snap"] += 1
print("events", len(evs), "with any rounds_handicap", len(lines))
c = collections.Counter(tuple(sorted(v)) for v in lines.values())
for k, v in c.most_common(10): print(k, v)
print("231548 names", n48.most_common(8))
print("quotes 1.09-1.43:", zone.most_common(10))
