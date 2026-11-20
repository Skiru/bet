"""Step 5: history replay of the milestone ladder (no prices) - the basis an
own curve would be fitted on. Games of the NBA / EuroLeague teams of the
candidate events, kickoff 2026-10-10 .. 2026-11-05 (before the measured
window), stored box. Every player who played: the installed model's
P(X >= N) for Superbet's ladder rungs, his sample cut before the game
(player_model.load_appearances, team by side, both list kinds, game
excluded) - the settle-time path (player id from the box). Graded on the box.
Read-only, keyed queries, one game at a time.
"""
from __future__ import annotations

import glob
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, UTC

sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa import player_model, shadow  # noqa: E402

S = os.path.join(os.path.dirname(__file__), "out")
DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
LADDER = {
    233565: ("player_points", (5, 10, 15, 20, 25, 30)),
    233567: ("player_rebounds", (3, 5, 7, 10)),
    233566: ("player_assists", (3, 5, 7, 10)),
    233569: ("player_pts_reb_ast", (10, 15, 20, 25, 30, 35)),
    233568: ("player_threes", (1, 2, 3, 4)),
}
FROM = int(datetime(2026, 10, 10, tzinfo=UTC).timestamp())
TO = int(datetime(2026, 11, 6, tzinfo=UTC).timestamp())

cand_ev = {json.loads(x)["superbet_event_id"] for x in open(f"{S}/candidates.jsonl")
           if json.loads(x)["kind"] == "milestone"}
teams: dict[int, str] = {}
for path in glob.glob("/Users/mkoziol/projects/bet/runs/sofa/shadow/basketball/2026-11-*/settled.json"):
    for eid, e in json.load(open(path))["events"].items():
        if eid in cand_ev and e.get("sofascore_home_id") and e["tournament"] in ("USA - NBA", "Euroliga"):
            lg = "NBA" if e["tournament"] == "USA - NBA" else "EL"
            teams[int(e["sofascore_home_id"])] = lg
            teams[int(e["sofascore_away_id"])] = lg
conn = sqlite3.connect(DB, uri=True, timeout=60)
games: dict[int, int] = {}
for t in teams:
    for eid, ts in conn.execute(
            "SELECT event_id, start_ts FROM sofa_listing_event WHERE entity_id=? AND kind='last' "
            "AND start_ts>=? AND start_ts<?", (t, FROM, TO)):
        games[int(eid)] = int(ts)
print("teams", len(teams), "games", len(games), flush=True)
prm = player_model.sport_params("basketball")
out = open(f"{S}/history_ladder.jsonl", "w")
sport = shadow.SPORTS["basketball"]
for i, (eid, ts) in enumerate(sorted(games.items(), key=lambda x: x[1])):
    ev = conn.execute("SELECT event_json FROM sofa_listed_event WHERE event_id=?", (eid,)).fetchone()
    lr = conn.execute("SELECT lineups_json FROM sofa_event_stats WHERE sofascore_event_id=?", (eid,)).fetchone()
    if not ev or not lr or not lr[0]:
        continue
    evj = json.loads(ev[0])
    if (evj.get("status") or {}).get("type") != "finished":
        continue
    home, away = (evj.get("homeTeam") or {}).get("id"), (evj.get("awayTeam") or {}).get("id")
    if not home or not away:
        continue
    lineups = json.loads(lr[0])
    box = shadow.build_player_box(lineups, evj, sport)
    if box is None or not box.ok:
        continue
    ids = player_model.box_player_ids(lineups)
    before = player_model.history_cutoff(ts, None)
    apps = player_model.load_appearances(conn, "basketball", [home, away], before, eid,
                                         team_from_side=True, kinds=("last", "last_side"))
    lg = teams.get(home) or teams.get(away)
    for key, st in box.players.items():
        if not shadow.has_played(st):
            continue
        pid = (ids or {}).get(key)
        if pid is None:
            continue
        for mid, (fam, rungs) in LADDER.items():
            spec = shadow.PLAYER_MARKETS["basketball"][mid]
            v = shadow.player_stat_value(st, spec)
            if not isinstance(v, float):
                continue
            for n in rungs:
                ln = shadow.ShadowLine(str(eid), mid, fam, 0, key, n - 0.5, "OVER", 2.0)
                mp = player_model.line_probability(ln, "basketball", apps, prm, player_id=pid)
                if mp.p is None:
                    continue
                out.write(json.dumps({"eid": eid, "ts": ts, "lg": lg, "pid": pid, "family": fam,
                                      "N": n, "p": round(mp.p, 4), "n": mp.n, "y": int(v >= n)}) + "\n")
    if i % 25 == 0:
        print(i, len(games), flush=True)
out.close()
