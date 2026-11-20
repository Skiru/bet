"""Adversarial checks 2 and 3:
 (2) my ht/ft reading vs SETTLE's own settled rows of the sim keys (sofa_settled_row actual_value), 11-06..11-19;
 (3) my p of draw_both_halves 'tak' (= htft X/X) vs the live SHEET's htft X/X p_central (07_settled / DB), 11-07..11-08
     (before the schedule term) and after."""
import gzip, json, sqlite3, sys
from collections import Counter
from pathlib import Path
sys.path[:0] = ["src", "."]
import numpy as np
from bet.sofa import football_sim_markets as fsm
S = Path(sys.argv[1])
grades = json.load(open(S / "live_grades.json"))
con = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
q = ("SELECT run_date, sofascore_event_id, market, subject, direction, actual_value, p_central FROM sofa_settled_row "
     "WHERE run_date BETWEEN '2026-11-06' AND '2026-11-19' AND sport='football' AND market IN ('htft','result_1h','result_2h','team_scores_both_halves','btts_halves')")
agree = Counter(); xx = []
for run_date, eid, market, subject, direction, actual, pc in con.execute(q):
    g = grades.get(str(eid))
    if not isinstance(g, dict):
        agree["mine_ungraded:" + str(g)[:25]] += 1
        continue
    held = fsm.path_holds(market, subject, tuple(g["ht"]), tuple(g["ft"]), None)
    if held is None:
        continue
    agree["agree" if float(held) == float(actual) else "DISAGREE"] += 1
    if market == "htft" and subject == "X/X":
        xx.append((run_date, eid, pc))
print("grade agreement vs SETTLE rows:", dict(agree))
mine = {}
for line in gzip.open(S / "live_eval.jsonl.gz", "rt"):
    r = json.loads(line)
    if r["cand"] == "draw_both_halves" and r["label"] == "tak" and r["p_sim"] is not None:
        mine[r["eid"]] = r["p_sim"]
for lo, hi in (("2026-11-06", "2026-11-08"), ("2026-11-09", "2026-11-19")):
    d = [(mine[e], pc) for rd, e, pc in xx if lo <= rd <= hi and e in mine]
    if d:
        a = np.array(d)
        print(f"htft X/X live p_central vs my draw_both_halves tak p, {lo}..{hi}: n {len(a)}, mean mine {a[:,0].mean():.4f} live {a[:,1].mean():.4f}, "
              f"median |diff| {np.median(np.abs(a[:,0]-a[:,1])):.4f}, p90 {np.percentile(np.abs(a[:,0]-a[:,1]),90):.4f}, corr {np.corrcoef(a.T)[0,1]:.3f}")
