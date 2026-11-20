"""Step 1: shapes, volume, zone, and milestone N+ vs two-sided OVER N-0.5 on
the same (event, family, player). Read-only; reads out/*.jsonl."""
from __future__ import annotations

import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime

S = os.path.join(os.path.dirname(__file__), "out")
DAYS = ("2026-11-06", "2026-11-19")


def lg(t: str | None) -> str:
    t = t or ""
    if t == "USA - NBA":
        return "NBA"
    if t == "Euroliga":
        return "EL"
    return "inne"


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


cand = [json.loads(x) for x in open(f"{S}/candidates.jsonl")]
cand = [c for c in cand if DAYS[0] <= (c["shadow_day"] or "") <= DAYS[1]]
active = [c for c in cand if c["status"] == "active" and c["price"] > 1.0]
print("selections in window:", len(cand), "active & priced:", len(active))

# --- volume / zone per market and league ------------------------------
print("\n== milestones: per market x league: selections, events, players, zone(1.09-1.43)")
grp: dict = defaultdict(lambda: {"n": 0, "ev": set(), "pl": set(), "zone": 0, "Ns": Counter()})
for c in active:
    if c["kind"] != "milestone":
        continue
    g = grp[(c["market_id"], c["family"], lg(c["tournament"]))]
    g["n"] += 1
    g["ev"].add(c["superbet_event_id"])
    g["pl"].add((c["superbet_event_id"], c["subject"]))
    if 1.09 <= c["price"] <= 1.43:
        g["zone"] += 1
        g["Ns"][c["N"]] += 1
for k in sorted(grp):
    g = grp[k]
    print(k, g["n"], len(g["ev"]), len(g["pl"]), "zone", g["zone"], "zoneN", dict(sorted(g["Ns"].items())))

# --- milestone ladders ------------------------------------------------
print("\n== N values offered per family (all active)")
ns = defaultdict(Counter)
for c in active:
    if c["kind"] == "milestone":
        ns[c["family"]][c["N"]] += 1
for f, cnt in ns.items():
    print(f, dict(sorted(cnt.items())))

# --- double double ------------------------------------------------------
print("\n== double/triple double: per league, sides, overround")
dd = defaultdict(dict)
for c in active:
    if c["kind"] in ("double_double", "triple_double"):
        dd[(c["kind"], c["superbet_event_id"], c["subject"])][c["side"]] = c
cnt = Counter()
ovr = defaultdict(list)
zone = Counter()
for (kind, eid, subj), sides in dd.items():
    league = lg(next(iter(sides.values()))["tournament"])
    cnt[(kind, league, tuple(sorted(sides)))] += 1
    if "Tak" in sides and "Nie" in sides:
        o = 1 / sides["Tak"]["price"] + 1 / sides["Nie"]["price"] - 1
        ovr[(kind, league)].append(o)
        for s in ("Tak", "Nie"):
            fair = (1 / sides[s]["price"]) / (1 + o)
            if 1.09 <= sides[s]["price"] <= 1.43 and fair >= 0.70:
                zone[(kind, league, s)] += 1
for k, v in sorted(cnt.items()):
    print(k, v)
for k, v in ovr.items():
    print("overround", k, "n", len(v), "median %.3f" % statistics.median(v), "p90 %.3f" % sorted(v)[int(0.9 * len(v))])
print("zone (1.09-1.43, fair>=0.70)", dict(zone))

# --- milestone vs two-sided OVER N-0.5 --------------------------------
two = [json.loads(x) for x in open(f"{S}/twosided.jsonl")]
tw = {}
lines_by = defaultdict(set)
for t in two:
    k = (t["superbet_event_id"], t["family"], t["subject"])
    lines_by[k].add(t["line"])
    tw[(k, t["line"], t["side"])] = t
print("\n== milestone N+ vs two-sided OVER (N-0.5), same event / family / player")
cmp_rows = []
have_family_any = Counter()
for c in active:
    if c["kind"] != "milestone" or c["family"].startswith("?"):
        continue
    k = (c["superbet_event_id"], c["family"], c["subject"])
    has_any = k in lines_by
    have_family_any[(lg(c["tournament"]), has_any)] += 1
    t = tw.get((k, c["N"] - 0.5, "OVER"))
    if t is None:
        continue
    cmp_rows.append((c, t))
print("milestones with ANY two-sided line of the family for that player:", dict(have_family_any))
print("milestones with a two-sided OVER at exactly N-0.5:", len(cmp_rows))
better = worse = equal = 0
diffs = []
dt = []
for c, t in cmp_rows:
    dt.append((ts(t["fetched_at_utc"]) - ts(c["fetched_at_utc"])) / 60)
    d = c["price"] - t["odds"]
    diffs.append(d)
    if d > 1e-9:
        better += 1
    elif d < -1e-9:
        worse += 1
    else:
        equal += 1
print(f"milestone price > two-sided OVER: {better}, equal: {equal}, below: {worse}")
if diffs:
    print("median diff %.3f; minutes (two-sided quote - milestone quote) median %.1f" % (
        statistics.median(diffs), statistics.median(dt)))
# implied: milestone 1/price vs two-sided fair p and raw 1/odds
gap_fair = [1 / c["price"] - t["fair_p"] for c, t in cmp_rows if t["fair_p"]]
gap_raw = [1 / c["price"] - 1 / t["odds"] for c, t in cmp_rows]
if gap_fair:
    print("1/milestone - two-sided fair p: median %.4f mean %.4f" % (statistics.median(gap_fair), statistics.mean(gap_fair)))
    print("1/milestone - two-sided 1/odds: median %.4f mean %.4f" % (statistics.median(gap_raw), statistics.mean(gap_raw)))
# by league
byl = defaultdict(list)
for c, t in cmp_rows:
    byl[lg(c["tournament"])].append(c["price"] - t["odds"])
for k, v in byl.items():
    print(k, "n", len(v), "better", sum(x > 1e-9 for x in v), "median diff %.3f" % statistics.median(v))
# where is the two-sided line relative to the milestone ladder
print("\n== in-zone milestones: distance of N-0.5 below the player's two-sided main line")
dist = Counter()
for c in active:
    if c["kind"] != "milestone" or not (1.09 <= c["price"] <= 1.43):
        continue
    k = (c["superbet_event_id"], c["family"], c["subject"])
    ls = lines_by.get(k)
    if not ls:
        dist["no two-sided line"] += 1
        continue
    gap = min(ls) - (c["N"] - 0.5)
    dist["same line" if gap <= 0 and (c["N"] - 0.5) in ls else ("below lowest two-sided by %s" % ("<=2" if gap <= 2 else (">2-5" if gap <= 5 else ">5")) if gap > 0 else "inside/above two-sided range")] += 1
print(dict(dist))
json.dump([[c, t] for c, t in cmp_rows], open(f"{S}/milestone_vs_twosided.json", "w"))
