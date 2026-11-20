"""Step 5b: calibration of the installed model on the milestone ladder,
history 10-10..11-05 (out/history_ladder.jsonl), game bootstrap CI."""
from __future__ import annotations

import json
import os
import random
from collections import defaultdict

S = os.path.join(os.path.dirname(__file__), "out")
rows = [json.loads(x) for x in open(f"{S}/history_ladder.jsonl")]
print("rows", len(rows), "games", len({r["eid"] for r in rows}),
      "player-games", len({(r["eid"], r["pid"]) for r in rows}))


def boot_gap(rs, B=1000):
    by = defaultdict(list)
    for r in rs:
        by[r["eid"]].append(r)
    evs = list(by)
    rng = random.Random(3)
    v = []
    for _ in range(B):
        s = [r for e in (rng.choice(evs) for _ in evs) for r in by[e]]
        v.append(sum(r["y"] - r["p"] for r in s) / len(s))
    v.sort()
    return sum(r["y"] - r["p"] for r in rs) / len(rs), v[25], v[974]


bands = ((0.6, 0.7), (0.7, 0.8), (0.8, 0.92), (0.92, 1.0))
for scope in ("ALL", "NBA", "EL"):
    for lo, hi in bands:
        rs = [r for r in rows if lo <= r["p"] < hi and (scope == "ALL" or r["lg"] == scope)]
        if len(rs) < 30:
            continue
        g = boot_gap(rs)
        print(f"{scope} {lo:.2f}-{hi:.2f}: n {len(rs)} claimed {sum(r['p'] for r in rs)/len(rs):.3f} "
              f"hit {sum(r['y'] for r in rs)/len(rs):.3f} hit-claimed {g[0]*100:+.1f} pp [{g[1]*100:+.1f}; {g[2]*100:+.1f}]")
print("\nper family, p >= 0.70 rows (a curve's n) and calibration 0.70-0.92")
for fam in sorted({r["family"] for r in rows}):
    rs = [r for r in rows if r["family"] == fam and 0.70 <= r["p"] < 0.92]
    g = boot_gap(rs) if len(rs) >= 30 else (float("nan"),) * 3
    print(f"{fam}: rows {sum(1 for r in rows if r['family']==fam)} p>=0.70 {sum(1 for r in rows if r['family']==fam and r['p']>=0.70)} "
          f"0.70-0.92 n {len(rs)} claimed {sum(r['p'] for r in rs)/max(len(rs),1):.3f} hit {sum(r['y'] for r in rs)/max(len(rs),1):.3f} "
          f"gap {g[0]*100:+.1f} [{g[1]*100:+.1f}; {g[2]*100:+.1f}]")
