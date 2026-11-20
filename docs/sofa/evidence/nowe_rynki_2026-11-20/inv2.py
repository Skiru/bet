import gzip, json, glob, os, sys, collections
S = sys.argv[1]
agg = collections.defaultdict(lambda: {"ev": set(), "lines": set(), "ex": collections.Counter(), "sel": collections.Counter()})
for f in glob.glob(f"runs/sofa/2026-11-*/unmapped_prices/{S}_*.jsonl.gz"):
    day = f.split("/")[2]
    if not ("2026-11-06" <= day <= "2026-11-19"): continue
    with gzip.open(f, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            k = r.get("marketId")
            a = agg[k]
            a["ev"].add(r["superbet_event_id"]); a["lines"].add((r["superbet_event_id"], r.get("specialBetValue")))
            a["ex"][r.get("marketName")] += 1
            if len(a["sel"]) < 12: a["sel"][r.get("name")] += 1
rows = sorted(agg.items(), key=lambda kv: -len(kv[1]["ev"]))
for k, a in rows[:int(sys.argv[2])]:
    print(len(a["ev"]), len(a["lines"]), k, "|", a["ex"].most_common(1)[0][0][:80], "|", [s for s, _ in a["sel"].most_common(5)])
