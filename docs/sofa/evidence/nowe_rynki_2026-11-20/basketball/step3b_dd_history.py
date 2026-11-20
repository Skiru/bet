"""Step 3b: how wrong is independence for the double-double on history?

Teams = every Sofascore team of the candidate DD events (NBA / EuroLeague /
other, from SHADOW's settled.json). Their last 60 listed games' appearances
(player_model.load_appearances, team by side, both list kinds - as the model
reads). Per player with >= 20 appearances (in-sample marginals, so only the
dependence is tested): independence P(>= 2 of pts/reb/ast/stl/blk >= 10) vs
the realised double-double rate; and the same with the player_model-style
marginals is in step4. Read-only, keyed queries.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from itertools import combinations

sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import player_model  # noqa: E402

S = os.path.join(os.path.dirname(__file__), "out")
DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
KEYS = ("points", "rebounds", "assists", "steals", "blocks")

cand_ev = {json.loads(x)["superbet_event_id"] for x in open(f"{S}/candidates.jsonl")
           if json.loads(x)["kind"] == "double_double"}
teams: dict[str, set[int]] = defaultdict(set)
for path in glob.glob("/Users/mkoziol/projects/bet/runs/sofa/shadow/basketball/2026-11-*/settled.json"):
    for eid, e in json.load(open(path))["events"].items():
        if eid in cand_ev and e.get("sofascore_home_id"):
            lg = "NBA" if e["tournament"] == "USA - NBA" else ("EL" if e["tournament"] == "Euroliga" else "inne")
            teams[lg].update({int(e["sofascore_home_id"]), int(e["sofascore_away_id"])})
conn = sqlite3.connect(DB, uri=True, timeout=60)
now = int(time.time())
res = {}
rows_out = []
for lg, ts in teams.items():
    apps = player_model.load_appearances(conn, "basketball", sorted(ts), now, None,
                                         team_from_side=True, kinds=("last", "last_side"))
    by_pl: dict[int, dict[int, dict]] = defaultdict(dict)
    for a in apps:
        st = a.stats
        if not all(isinstance(st.get(k), int | float) for k in KEYS):
            continue
        by_pl[a.player_id][a.event_id] = st  # one per game
    n_pg = 0
    pred = obs = 0.0
    pred_pra = 0.0
    pairs = 0
    tot_tak = []
    for pid, games in by_pl.items():
        if len(games) < 20:
            continue
        g = list(games.values())
        n = len(g)
        m = {k: sum(1 for s in g if s[k] >= 10) / n for k in KEYS}
        # P(at least 2 of 5 independent events)
        p0 = 1.0
        for k in KEYS:
            p0 *= 1 - m[k]
        p1 = sum(m[k] * __import__("math").prod(1 - m[j] for j in KEYS if j != k) for k in KEYS)
        p_ind = 1 - p0 - p1
        dd = sum(1 for s in g if sum(1 for k in KEYS if s[k] >= 10) >= 2) / n
        n_pg += n
        pred += p_ind * n
        obs += dd * n
        rows_out.append({"lg": lg, "pid": pid, "n": n, "p_ind": p_ind, "dd": dd, **{f"m_{k}": m[k] for k in KEYS}})
    res[lg] = {"teams": len(ts), "players>=20": sum(1 for r in rows_out if r["lg"] == lg),
               "player_games": n_pg, "dd_rate_obs": obs / n_pg if n_pg else None,
               "dd_rate_indep": pred / n_pg if n_pg else None}
    del apps, by_pl
print(json.dumps(res, indent=1))
# by band of p_ind among DD-relevant players (p_ind >= 0.05)
bands = [(0, 0.05), (0.05, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 1.01)]
for lg in res:
    for lo, hi in bands:
        sel = [r for r in rows_out if r["lg"] == lg and lo <= r["p_ind"] < hi]
        if not sel:
            continue
        w = sum(r["n"] for r in sel)
        print(lg, f"p_ind {lo}-{hi}", "players", len(sel), "games", w,
              "indep %.3f" % (sum(r["p_ind"] * r["n"] for r in sel) / w),
              "obs %.3f" % (sum(r["dd"] * r["n"] for r in sel) / w))
json.dump(rows_out, open(f"{S}/dd_history_players.json", "w"))
