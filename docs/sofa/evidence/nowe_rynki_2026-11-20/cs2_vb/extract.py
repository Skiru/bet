"""Extract CS2 / volleyball unmapped prices of candidate markets into one jsonl (read-only)."""
import glob, gzip, json, collections, sys
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
WANT = {"cs2": {231528, 231535, 231548, 231557, 235657, 235658, 231533},
        "volleyball": {230059, 786, 100080, 100081, 200849, 200852, 240723, 240724, 235045, 235046}}
names = collections.Counter()
out = open("unmapped_candidates.jsonl", "w")
n = 0
for sport in ("cs2", "volleyball"):
    for f in sorted(glob.glob(f"{ROOT}/2026-11-*/unmapped_prices/{sport}_*.jsonl.gz")):
        day = f.split("/")[-3]
        with gzip.open(f, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                mid = int(r["marketId"])
                names[(sport, mid, r["marketName"] if mid not in (235571,) else "")] += 0
                if mid in WANT[sport]:
                    out.write(json.dumps({"day": day, "file": f.split("/")[-1], "sport": sport,
                        "sb": r["superbet_event_id"], "ts": r["fetched_at_utc"], "mid": mid,
                        "mname": r["marketName"], "name": r["name"], "sbv": r.get("specialBetValue"),
                        "price": r["price"], "status": r.get("status"), "oid": r.get("outcomeId")}) + "\n")
                    n += 1
print("rows", n)
