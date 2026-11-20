"""Same-event check against PRINTABLE read rows only (direction a row can have), vs any read price."""
import gzip, json, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path[:0] = ["src", ".", str(Path(__file__).parent)]
from cands import parse
from bet.sofa import leg_identity as li
from bet.sofa import football_score_markets as fsm
from bet.sofa import football_sim_markets as sim
S = Path(sys.argv[1])
P = {}
def addv(name, market, subject, side, line, dirs):
    v = li._football_vector(market, subject, side, line)
    if v is None:
        return
    if "OVER" in dirs:
        P.setdefault(v, name + "|OVER")
    if "UNDER" in dirs:
        P.setdefault(tuple(None if x is None else not x for x in v), name + "|UNDER")
for s in ("1", "X", "2"):
    addv(f"result_1x2@{s}", "result_1x2", s, None, 0.5, ("OVER",))
for s in ("1X", "X2", "12"):
    addv(f"double_chance@{s}", "double_chance", s, None, 0.5, ("OVER",))
for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
    for m in ("goals_total", "goals_1h_total", "goals_2h_total", "both_over_goals", "both_over_goals_1h", "both_over_goals_2h"):
        addv(f"{m}@{L}", m, "", None, L, ("OVER", "UNDER"))
    for m in ("goals_for", "goals_1h_for", "goals_2h_for"):
        for side in (0, 1):
            addv(f"{m}[{side + 1}]@{L}", m, "", side, L, ("OVER", "UNDER"))
for market in fsm.MARKETS:
    for subj in ("1", "X", "2", "", "12", "1X", "X2"):
        for L in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5):
            if fsm.valid_rung(market, subj, L):
                addv(f"{market}@{subj}@{L}", market, subj, None, L, ("OVER",))
subs = {sim.HTFT: sim.HTFT_SUBJECTS, sim.RESULT_1H: sim.RESULT_SUBJECTS, sim.RESULT_2H: sim.RESULT_SUBJECTS,
        sim.HIGHER_HALF: sim.HALF_SUBJECTS, sim.TEAM_BOTH_HALVES: sim.SIDE_SUBJECTS, sim.BTTS_HALVES: sim.BTTS_HALVES_SUBJECTS,
        sim.BTTS_ANY_HALF: ("",), sim.FIRST_GOAL_1H: sim.FG1H_SUBJECTS,
        sim.HALF_GOALS_COMBO: [f"{a}{l1:g}/{b}{l2:g}" for a in "OU" for b in "OU" for l1 in sim.COMBO_LINES for l2 in sim.COMBO_LINES]}
for market, ss in subs.items():
    for subj in ss:
        addv(f"{market}@{subj}", market, subj, None, 0.5, ("OVER", "UNDER") if market in sim.TWO_SIDED else ("OVER",))
print("printable read vectors", len(P))
seen = {}
for line in gzip.open(S / "cand_prices.jsonl.gz", "rt"):
    rec = json.loads(line)
    got = parse(rec)
    if got is None:
        continue
    cand, gk, label, held = got
    if (cand, gk, label) in seen:
        continue
    vec = tuple(held(s[0], s[1], s[2], s[3]) for s in li._STATES)
    seen[(cand, gk, label)] = "conditional" if None in vec else P.get(vec)
# zone selections per label from cand_rows
zone = Counter()
for line in gzip.open(S / "cand_rows.jsonl.gz", "rt"):
    r = json.loads(line)
    if r["complete"] and 1.09 <= r["price"] <= 1.43 and r["fair"] >= 0.70:
        zone[(r["cand"], r["gk"], r["label"])] += 1
res = defaultdict(lambda: {"dup_zone": 0, "new_zone": 0, "cond_zone": 0, "dups": []})
for k, d in sorted(seen.items(), key=str):
    z = zone.get(k, 0)
    c = res[k[0]]
    if d == "conditional":
        c["cond_zone"] += z
    elif d:
        c["dup_zone"] += z
        c["dups"].append(f"{k[1]} {k[2]} = {d} (zone {z})")
    else:
        c["new_zone"] += z
json.dump(res, open(S / "step1_same_event_printable.json", "w"), indent=1)
for cand, c in res.items():
    print(cand, "zone: new", c["new_zone"], "dup", c["dup_zone"], "cond", c["cond_zone"])
    for d in c["dups"]:
        print("    ", d)
print("btts lines", Counter(k[1] for k in seen if k[0] == "btts_and_over"))
