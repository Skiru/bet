"""OT share by tournament tier and on the offered events (walk-forward rows + cs2_series tournament)."""
import json, sqlite3, math, random, re
from collections import defaultdict
DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
R = [json.loads(l) for l in open("cs2_ot_wf_rows.jsonl")]
conn = sqlite3.connect(DB, uri=True)
tour = {}
ids = [r["eid"] for r in R]
for i in range(0, len(ids), 500):
    ch = ids[i:i+500]
    for eid, t, ut in conn.execute(f"select sofascore_event_id, tournament, unique_tournament_id from cs2_series where sofascore_event_id in ({','.join('?'*len(ch))})", ch):
        tour[eid] = (t or "", ut)
ev = json.load(open("cs2_ot_events.json"))
offered_ut = set()
for e in ev:
    if e.get("sofa"):
        x = conn.execute("select unique_tournament_id, tournament from cs2_series where sofascore_event_id=?", (e["sofa"],)).fetchone()
        if x: offered_ut.add(x[0])
print("offered unique tournaments", len(offered_ut))
def boot(v, reps=2000):
    rng = random.Random(1); n = len(v); s = sorted(sum(v[rng.randrange(n)] for _ in range(n)) / n for _ in range(reps))
    return sum(v)/n, s[50], s[1949]
groups = defaultdict(list)
TIER1 = re.compile(r"blast|iem|esl pro|pgl|starladder|major|perfect world|thunderpick|cct global|fissure|betboom|esports world cup", re.I)
for r in R:
    if r["bo"] != 3: continue
    t, ut = tour.get(r["eid"], ("", None))
    groups["same unique_tournament as offered" if ut in offered_ut else "other tournaments"].append(r)
    groups["name tier-1 regex" if TIER1.search(t) else "name other"].append(r)
for g, S in groups.items():
    m = boot([r["y_noot"] - r["p_race"] for r in S])
    print(f"BO3 {g:38s} n={len(S):5d} realised noOT {sum(r['y_noot'] for r in S)/len(S):.3f} p_race {sum(r['p_race'] for r in S)/len(S):.3f} gap %+.3f [%+.3f, %+.3f]" % m,
          " OT/map %.3f" % (sum(r['ot_maps'] for r in S)/sum(r['n_maps'] for r in S)), " maps/series %.2f" % (sum(r['n_maps'] for r in S)/len(S)))
# offered events in rows
off = {e["sofa"]: e for e in ev if e.get("sofa")}
S = [r for r in R if r["eid"] in off]
print("offered events with walk-forward row:", len(S))
