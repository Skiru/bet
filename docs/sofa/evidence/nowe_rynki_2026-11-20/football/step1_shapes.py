"""Step 1: per candidate - events, days, selections, groups with a complete same-snapshot partition,
overround, zone (price 1.09-1.43 and de-vigged p >= 0.70), and same-event check vs read markets
(leg_identity's path vectors)."""
import gzip, json, sys, itertools
from collections import Counter, defaultdict
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
import numpy as np
from cands import parse
from bet.sofa import leg_identity as li
from bet.sofa import football_score_markets as fsm
from bet.sofa import football_sim_markets as sim

S = Path(sys.argv[1])
recs = [json.loads(l) for l in gzip.open(S / "cand_prices.jsonl.gz", "rt")]
rows = []
unparsed = Counter()
for r in recs:
    got = parse(r)
    if got is None:
        unparsed[r["template"]] += 1
        continue
    cand, gk, label, held = got
    if r.get("status") not in (None, "active") or not isinstance(r.get("price"), (int, float)) or r["price"] <= 1.0:
        unparsed["inactive:" + cand] += 1
        continue
    rows.append({**r, "cand": cand, "gkey": (r["eid"], cand, gk), "label": label})
print("unparsed", unparsed.most_common(12))
groups = defaultdict(list)
for r in rows:
    groups[r["gkey"]].append(r)
SIZE = {"match_handicap_3way": 3}
out = []
for g, rs in groups.items():
    cand = g[1]
    need = SIZE.get(cand, 2)
    fetched = {r["fetched_at_utc"] for r in rs}
    ok = len(rs) == need and len(fetched) == 1 and len({r["label"] for r in rs}) == need
    over = sum(1 / r["price"] for r in rs) if ok else None
    for r in rs:
        fair = (1 / r["price"]) / over if ok else None
        out.append({k: r[k] for k in ("day", "eid", "cand", "label", "price", "marketName", "name", "sbv", "kickoff_utc", "competition_id", "fetched_at_utc", "side_a", "side_b")}
                   | {"gk": g[2], "overround": over, "fair": fair, "complete": ok})
with gzip.open(S / "cand_rows.jsonl.gz", "wt") as fh:
    for r in out:
        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
# summary per candidate
summ = {}
for cand in sorted({r["cand"] for r in out}):
    rs = [r for r in out if r["cand"] == cand]
    comp = [r for r in rs if r["complete"]]
    ovs = [r["overround"] for r in comp]
    zone = [r for r in comp if 1.09 <= r["price"] <= 1.43 and r["fair"] >= 0.70]
    days = Counter(r["day"] for r in rs)
    summ[cand] = {"selections": len(rs), "events": len({r["eid"] for r in rs}), "groups": len({(r["eid"], r["gk"]) for r in rs}),
                  "complete_sel": len(comp), "overround_median": round(float(np.median(ovs)), 4) if ovs else None,
                  "overround_p10_p90": [round(float(np.percentile(ovs, 10)), 4), round(float(np.percentile(ovs, 90)), 4)] if ovs else None,
                  "zone_sel": len(zone), "zone_events": len({r["eid"] for r in zone}),
                  "zone_by_label": Counter(r["label"].split(":")[-1] if ":" in r["label"] else r["label"] for r in zone).most_common(8),
                  "zone_by_gk": Counter(r["gk"] for r in zone).most_common(8),
                  "events_per_day_min_max": [min(Counter((r["day"]) for r in {(x["day"], x["eid"]): x for x in rs}.values()).values()), max(Counter((r["day"]) for r in {(x["day"], x["eid"]): x for x in rs}.values()).values())],
                  "days": len(days)}
json.dump(summ, open(S / "step1_summary.json", "w"), indent=1, ensure_ascii=False)
for k, v in summ.items():
    print(k, json.dumps(v, ensure_ascii=False))

# ---- same-event check: vectors over leg_identity's paths ----
states = li._STATES
read_vecs = {}
def addv(name, market, subject, side, line):
    v = li._football_vector(market, subject, side, line)
    if v is None:
        return
    read_vecs.setdefault(v, name + "|OVER")
    read_vecs.setdefault(tuple(None if x is None else not x for x in v), name + "|UNDER")
for s in ("1", "X", "2"):
    addv(f"result_1x2@{s}", "result_1x2", s, None, 0.5)
for s in ("1X", "X2", "12"):
    addv(f"double_chance@{s}", "double_chance", s, None, 0.5)
for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
    for m in ("goals_total", "goals_1h_total", "goals_2h_total", "both_over_goals", "both_over_goals_1h", "both_over_goals_2h"):
        addv(f"{m}@{L}", m, "", None, L)
    for m in ("goals_for", "goals_1h_for", "goals_2h_for"):
        for side in (0, 1):
            addv(f"{m}[{side + 1}]@{L}", m, "", side, L)
for market in fsm.MARKETS:
    for subj in ("1", "X", "2", "", "12", "1X", "X2"):
        for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
            try:
                addv(f"{market}@{subj}@{L}", market, subj, None, L)
            except Exception:
                pass
for market in sim.MARKETS:
    subs = {sim.HTFT: sim.HTFT_SUBJECTS, sim.RESULT_1H: sim.RESULT_SUBJECTS, sim.RESULT_2H: sim.RESULT_SUBJECTS,
            sim.HIGHER_HALF: sim.HALF_SUBJECTS, sim.TEAM_BOTH_HALVES: sim.SIDE_SUBJECTS, sim.BTTS_HALVES: sim.BTTS_HALVES_SUBJECTS,
            sim.BTTS_ANY_HALF: ("",), sim.FIRST_GOAL_1H: sim.FG1H_SUBJECTS,
            sim.HALF_GOALS_COMBO: [f"{a}{l1:g}/{b}{l2:g}" for a in "OU" for b in "OU" for l1 in sim.COMBO_LINES for l2 in sim.COMBO_LINES]}[market]
    for subj in subs:
        addv(f"{market}@{subj}", market, subj, None, 0.5)
print("read vectors", len(read_vecs))
dup = {}
seen = {}
for r in rs if False else []:
    pass
for rec in recs:
    got = parse(rec)
    if got is None:
        continue
    cand, gk, label, held = got
    k = (cand, gk, label)
    if k in seen:
        continue
    vec = tuple(held(s[0], s[1], s[2], s[3]) for s in states)
    seen[k] = read_vecs.get(vec) if None not in vec else "conditional (refund on a drawn half) - no key"
res = defaultdict(list)
for (cand, gk, label), d in sorted(seen.items(), key=lambda x: str(x)):
    res[cand].append({"gk": gk, "label": label, "same_event_as": d})
json.dump(res, open(S / "step1_same_event.json", "w"), indent=1)
for cand, items in res.items():
    d = [i for i in items if i["same_event_as"]]
    print("SAME-EVENT", cand, f"{len(d)}/{len(items)} labels duplicate:", [(i["gk"], i["label"], i["same_event_as"]) for i in d][:14])
