"""Step 6: adversarial checks, each number a second way.

(a) my recomputed pre-game p of a milestone N+ vs SHADOW's stored pre-game
    model_p of the two-sided OVER N-0.5 (same event / family / player):
    same function, should agree (differences = a later snapshot clock).
(b) my box grade of N+ vs SHADOW_SETTLE's graded `actual` of the same
    player / family (settled.json, out/twosided.jsonl).
(c) the headline Brier difference recomputed with plain sums over a
    differently built join (from scored.jsonl, not milestones_graded.json).
(d) the would-print gate counted from scored.jsonl directly.
"""
from __future__ import annotations

import json
import os
import statistics
from collections import Counter

S = os.path.join(os.path.dirname(__file__), "out")
sc = [json.loads(x) for x in open(f"{S}/scored.jsonl")]
tw = [json.loads(x) for x in open(f"{S}/twosided.jsonl")]
over = {(t["superbet_event_id"], t["family"], t["subject"], t["line"]): t
        for t in tw if t["side"] == "OVER"}
actual = {}
for t in tw:
    if t.get("actual") is not None:
        actual[(t["superbet_event_id"], t["family"], t["subject"])] = t["actual"]

# (a)
d = []
for r in sc:
    if r["kind"] != "milestone" or r["model_p"] is None:
        continue
    t = over.get((r["superbet_event_id"], r["family"], r["subject"], r["N"] - 0.5))
    if t is None or t.get("model_p") is None or t.get("model_source") != "pregame":
        continue
    d.append(r["model_p"] - t["model_p"])
print("(a) recomputed vs stored pre-game p at the same line: n", len(d),
      "exact (|d|<0.0005)", sum(abs(x) < 5e-4 for x in d),
      "median |d| %.4f p95 |d| %.4f" % (statistics.median(map(abs, d)), sorted(map(abs, d))[int(.95 * len(d))]) if d else "")

# (b)
agree = Counter()
for r in sc:
    if r["kind"] != "milestone" or r.get("outcome") not in ("WIN", "LOSS"):
        continue
    a = actual.get((r["superbet_event_id"], r["family"], r["subject"]))
    if a is None:
        continue
    agree[(a >= r["N"]) == (r["outcome"] == "WIN")] += 1
print("(b) my grade vs SHADOW_SETTLE actual:", dict(agree))

# (c)
num = n = 0
for r in sc:
    if r["kind"] == "milestone" and r.get("outcome") in ("WIN", "LOSS") and r["model_p"] is not None:
        y = r["outcome"] == "WIN"
        num += (r["model_p"] - y) ** 2 - (1 / r["price"] - y) ** 2
        n += 1
print("(c) Brier model - 1/price x1e3: %+.2f on %d" % (1000 * num / n, n))

# (d)
g = [r for r in sc if r["kind"] == "milestone" and r.get("outcome") in ("WIN", "LOSS")
     and r["model_p"] is not None and r["model_p"] >= 0.7 and r["model_p"] * r["price"] >= 0.9]
w = sum(r["outcome"] == "WIN" for r in g)
print("(d) gate n", len(g), "won", w, "stake-return", round(sum(r["price"] for r in g if r["outcome"] == "WIN") - len(g), 2))
