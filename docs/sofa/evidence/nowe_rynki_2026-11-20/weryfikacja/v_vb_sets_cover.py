"""Volleyball: for events with 'Czy będzie 4./5. set?' (200852/200849) in unmapped files,
does SHADOW's snapshot carry sets_total 3.5 / 4.5 for the same superbet event?
Also: compare fair p at the last common snapshot; list other unread vb markets in a wide price zone."""
import gzip, json, glob, collections, os, sys

ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
days = [f"2026-11-{d:02d}" for d in range(5, 21)]

# unmapped: event -> {market: {fetched: {name: price}}}
unm = collections.defaultdict(lambda: collections.defaultdict(dict))
names = collections.Counter()
for d in days:
    for f in sorted(glob.glob(f"{ROOT}/{d}/unmapped_prices/volleyball_*.jsonl.gz")):
        with gzip.open(f, "rt") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("status") != "active":
                    continue
                mid = r["marketId"]
                names[(mid, r["marketName"][:40])] += 1
                if mid in (200849, 200852):
                    unm[r["superbet_event_id"]][(mid, r["fetched_at_utc"])][r["name"]] = r["price"]

# snapshots: event -> {fetched: {(line, side): odds}}
snap = collections.defaultdict(dict)
kick = {}
for d in days:
    p = f"{ROOT}/shadow/volleyball/{d}/snapshots.jsonl"
    if not os.path.exists(p):
        continue
    with open(p) as fh:
        for line in fh:
            s = json.loads(line)
            ev = s["superbet_event_id"]
            if ev not in unm:
                continue
            kick[ev] = s.get("kickoff_utc")
            st = {(l["line"], l["side"]): l["odds"] for l in s["lines"] if l["family"] == "sets_total"}
            snap[ev][s["fetched_at_utc"]] = st

ev_with = len(unm)
has35 = has45 = 0
diffs = {200852: [], 200849: []}
for ev, mk in unm.items():
    sn = snap.get(ev, {})
    lines = set()
    for st in sn.values():
        lines |= {k[0] for k in st}
    has35 += 3.5 in lines
    has45 += 4.5 in lines
    # compare at identical fetched_at (pre-start only)
    for (mid, fa), sel in mk.items():
        if kick.get(ev) and fa >= kick[ev]:
            continue
        st = sn.get(fa)
        if not st:
            continue
        L = 3.5 if mid == 200852 else 4.5
        if (L, "OVER") not in st or (L, "UNDER") not in st:
            continue
        yes = [v for k, v in sel.items() if k.lower().startswith("tak")]
        no = [v for k, v in sel.items() if k.lower().startswith("nie")]
        if not yes or not no:
            continue
        fy = (1 / yes[0]) / (1 / yes[0] + 1 / no[0])
        fo = (1 / st[(L, "OVER")]) / (1 / st[(L, "OVER")] + 1 / st[(L, "UNDER")])
        diffs[mid].append(fy - fo)

print("events with 4th/5th-set market:", ev_with, "with any snapshot:", sum(1 for e in unm if snap.get(e)))
print("events whose snapshots carry sets_total 3.5:", has35, " 4.5:", has45)
for mid, ds in diffs.items():
    if ds:
        ds.sort()
        print(mid, "n quotes same fetched_at", len(ds), "mean diff fair(yes)-fair(over) %.4f" % (sum(ds) / len(ds)),
              "min %.3f max %.3f" % (ds[0], ds[-1]))
print("\nTop unread volleyball markets (active quotes):")
for (mid, n), c in names.most_common(25):
    print(mid, n, c)
