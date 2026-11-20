"""CS2: 231535 'najwięcej wygranych rund w meczu' / 231548 'Podwójna szansa rundy' vs read
rounds_handicap +-0.5 on the same superbet event (snapshot with same fetched_at).
Also counts the selections in the coupon print zone (wide: odds >= 1.09) and the top unread CS2 markets."""
import gzip, json, glob, collections, os

ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
days = [f"2026-11-{d:02d}" for d in range(5, 22)]
unm = collections.defaultdict(lambda: collections.defaultdict(dict))  # ev -> (mid,fa) -> name->price
mk_names = collections.Counter()
mk_events = collections.defaultdict(set)
for d in days:
    for f in sorted(glob.glob(f"{ROOT}/{d}/unmapped_prices/cs2_*.jsonl.gz")):
        with gzip.open(f, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("status") != "active":
                    continue
                key = (r["marketId"], r["marketName"].split(" - ")[-1][:45] if r["marketId"] not in (231535, 231548) else r["marketName"][:45])
                mk_names[key] += 1
                mk_events[key].add(r["superbet_event_id"])
                if r["marketId"] in (231535, 231548):
                    unm[r["superbet_event_id"]][(r["marketId"], r["fetched_at_utc"])][r["name"]] = r["price"]

snap = collections.defaultdict(dict)
for d in days:
    p = f"{ROOT}/cs2/{d}/snapshots.jsonl"
    if not os.path.exists(p):
        continue
    with open(p) as fh:
        for line in fh:
            s = json.loads(line)
            ev = s["superbet_event_id"]
            if ev not in unm:
                continue
            st = {(l["line"], l["side"]): l["odds"] for l in s["lines"] if l["family"] == "rounds_handicap" and l["line"] in (-0.5, 0.5)}
            snap[ev][s["fetched_at_utc"]] = st

ev_any = sum(1 for e in unm if any(snap[e].values()))
print("events with 231535/231548:", len(unm), "; with rounds_handicap +-0.5 in some snapshot:", ev_any)
same = cmp = 0
dc12 = []
for ev, mk in unm.items():
    for (mid, fa), sel in mk.items():
        st = snap[ev].get(fa)
        if mid == 231548 and "12" in sel:
            dc12.append(sel["12"])
        if not st:
            continue
        if mid == 231535 and "1" in sel and (-0.5, "T1") in st:
            cmp += 1
            same += abs(sel["1"] - st[(-0.5, "T1")]) < 1e-9
print("231535 '1' vs rounds_handicap T1 -0.5 same snapshot: %d compared, %d identical price" % (cmp, same))
if dc12:
    dc12.sort()
    print("231548 '12' (rounds not equal = NEW event) quotes:", len(dc12), "price min/median/max", dc12[0], dc12[len(dc12)//2], dc12[-1],
          "; >=1.09:", sum(1 for x in dc12 if x >= 1.09))
print("\nTop unread CS2 markets by events:")
for k, c in sorted(mk_names.items(), key=lambda kv: -len(mk_events[kv[0]]))[:25]:
    print(k, "quotes", c, "events", len(mk_events[k]))
