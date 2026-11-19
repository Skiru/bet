"""Score replayed slips: return after tax per arm and request, paired vs OLD, bootstrap by day.
usage: analyse.py <dir of day jsonl>"""
import json, random, sys
from collections import defaultdict
from pathlib import Path

rows = []
for f in sorted(Path(sys.argv[1]).glob("*.jsonl")):
    rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def grade(s):
    st = [l["status"] for l in s["legs"]]
    if "unknown" in st or not st:
        return None
    if "lost" in st:
        return -1.0
    prod = 1.0
    for l in s["legs"]:
        if l["status"] == "won":
            prod *= l["odds"]
    return 0.88 * prod - 1.0


slips = defaultdict(dict)  # (day, target, win, rank) -> arm -> row
for r in rows:
    r["ret"] = grade(r)
    slips[(r["day"], r["target"], r["win"], r["rank"])][r["arm"]] = r
arms = ["OLD", "FAIR", "FAIR_EV"]
days = sorted({k[0] for k in slips})
random.seed(11)


def boot(vals_by_day, n=1000):
    def stat(ds):
        v = [x for d in ds for x in vals_by_day.get(d, [])]
        return sum(v) / len(v) if v else float("nan")
    pt = stat(days)
    bs = sorted(stat(random.choices(days, k=len(days))) for _ in range(n))
    return pt, bs[25], bs[974]


for target in sorted({k[1] for k in slips}) + ["ALL"]:
    print(f"== target {target}")
    for arm in arms:
        by = defaultdict(list)
        hits = n = 0
        ch = []
        legs = []
        for k, a in slips.items():
            if target != "ALL" and k[1] != target:
                continue
            s = a.get(arm)
            if s is None or s["ret"] is None:
                continue
            by[k[0]].append(s["ret"]); n += 1; hits += s["ret"] > -1
            ch.append(s["chance"]); legs.append(len(s["legs"]))
        pt, lo, hi = boot(by)
        print(f"  {arm:8s} slips {n:5d}  won {hits / max(n, 1):.3f}  pred chance {sum(ch) / max(len(ch), 1):.3f}  "
              f"legs {sum(legs) / max(len(legs), 1):.2f}  return {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]")
    for arm in arms[1:]:
        by = defaultdict(list); same = tot = 0
        for k, a in slips.items():
            if target != "ALL" and k[1] != target:
                continue
            o, s = a.get("OLD"), a.get(arm)
            if not o or not s or o["ret"] is None or s["ret"] is None:
                continue
            tot += 1
            same += sorted(l["key"] for l in o["legs"]) == sorted(l["key"] for l in s["legs"])
            by[k[0]].append(s["ret"] - o["ret"])
        pt, lo, hi = boot(by)
        print(f"  {arm}-OLD paired {pt:+.4f} [{lo:+.4f}, {hi:+.4f}]  pairs {tot}  identical slips {same / max(tot, 1):.2f}")
