"""Step 1: extract candidate unread basketball markets (milestones N+, double /
triple double) from runs/sofa/<d>/unmapped_prices/basketball_*.jsonl.gz,
keep the last pre-kickoff quote per selection (and the first), join events to
SHADOW's settled.json (kickoff, tournament, sofascore id, state) and dump the
two-sided player rows SHADOW graded on the same events.

Read-only. Output: out/candidates.jsonl, out/events.json, out/twosided.jsonl
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import re
from collections import Counter

ROOT = "/Users/mkoziol/projects/bet"
OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

MILESTONE = {
    235311: "player_points", 235312: "player_rebounds", 235313: "player_assists",
    235314: "player_pts_reb_ast", 235315: "player_threes",
    238440: "player_points", 238441: "?238441", 238442: "player_rebounds",
    238443: "?238443", 238444: "player_assists", 238445: "?238445",
    238446: "player_threes",
}
DD = {233573: "double_double", 233574: "triple_double"}

# events from every shadow settled.json and snapshots (event-level only)
events: dict[str, dict] = {}
for path in sorted(glob.glob(f"{ROOT}/runs/sofa/shadow/basketball/2026-11-*/settled.json")):
    day = path.split("/")[-2]
    d = json.load(open(path))
    for eid, e in d["events"].items():
        keep = {k: e.get(k) for k in (
            "match_name", "team1", "team2", "kickoff_utc", "tournament", "state",
            "status", "sofascore_event_id", "home_is_team1", "t1_full", "t2_full",
            "overtime", "player_box", "sofascore_tournament", "pinned_id")}
        keep["shadow_day"] = day
        events[eid] = keep
for path in sorted(glob.glob(f"{ROOT}/runs/sofa/shadow/basketball/2026-11-*/snapshots.jsonl")):
    day = path.split("/")[-2]
    with open(path) as fh:
        for line in fh:
            # event-level fields sit before "lines"; avoid parsing the lines
            head = line.split('"lines":', 1)[0].rstrip().rstrip(",") + "}"
            try:
                r = json.loads(head)
            except ValueError:
                r = json.loads(line)
            eid = str(r["superbet_event_id"])
            if eid not in events:
                events[eid] = {k: r.get(k) for k in (
                    "match_name", "team1", "team2", "kickoff_utc", "tournament")}
                events[eid]["state"] = "NOT_SETTLED"
                events[eid]["shadow_day"] = day

best: dict[tuple, dict] = {}
first: dict[tuple, dict] = {}
n_rec = Counter()
for path in sorted(glob.glob(f"{ROOT}/runs/sofa/2026-11-*/unmapped_prices/basketball_*.jsonl.gz")):
    with gzip.open(path, "rt") as fh:
        for line in fh:
            r = json.loads(line)
            m = int(r["marketId"])
            if m not in MILESTONE and m not in DD:
                continue
            eid = str(r["superbet_event_id"])
            ev = events.get(eid)
            n_rec[m] += 1
            if ev is None or not ev.get("kickoff_utc"):
                continue
            ko = ev["kickoff_utc"].replace("Z", "")
            fetched = r["fetched_at_utc"].replace("Z", "")
            if fetched >= ko:
                continue
            key = (eid, m, r["name"])
            if key not in first or fetched < first[key]["fetched_at_utc"]:
                first[key] = r
            if key not in best or fetched > best[key]["fetched_at_utc"]:
                best[key] = r

rows = []
pat = re.compile(r"^(\d+)-(.*)$")
for key, r in best.items():
    eid, m, name = key
    out = {
        "superbet_event_id": eid, "market_id": m, "name": name,
        "price": r["price"], "status": r.get("status"),
        "offerStateId": r.get("offerStateId"), "fetched_at_utc": r["fetched_at_utc"],
        "first_price": first[key]["price"], "first_fetched": first[key]["fetched_at_utc"],
        "marketName": r["marketName"],
    }
    if m in MILESTONE:
        mm = pat.match(str(r["specialBetValue"]))
        out["kind"] = "milestone"
        out["family"] = MILESTONE[m]
        out["N"] = int(mm.group(1)) if mm else None
        out["subject"] = mm.group(2) if mm else None
    else:
        out["kind"] = DD[m]
        out["subject"] = r["specialBetValue"]
        out["side"] = "Tak" if name.endswith("- Tak") else ("Nie" if name.endswith("- Nie") else "?")
    ev = events[eid]
    out.update({"tournament": ev.get("tournament"), "kickoff_utc": ev.get("kickoff_utc"),
                "state": ev.get("state"), "sofascore_event_id": ev.get("sofascore_event_id"),
                "shadow_day": ev.get("shadow_day")})
    rows.append(out)

with open(f"{OUT}/candidates.jsonl", "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")

cand_events = {r["superbet_event_id"] for r in rows}
json.dump({e: events[e] for e in cand_events}, open(f"{OUT}/events.json", "w"))

# two-sided player rows SHADOW graded on the candidate events
n2 = 0
with open(f"{OUT}/twosided.jsonl", "w") as fh:
    for path in sorted(glob.glob(f"{ROOT}/runs/sofa/shadow/basketball/2026-11-*/settled.json")):
        d = json.load(open(path))
        for eid, e in d["events"].items():
            if eid not in cand_events:
                continue
            for g in e.get("graded") or []:
                if str(g.get("family", "")).startswith("player_"):
                    g = {k: g.get(k) for k in (
                        "superbet_event_id", "market_id", "family", "subject", "line",
                        "side", "odds", "partner_odds", "fair_p", "overround", "outcome",
                        "actual", "model_p", "model_n", "model_reason", "model_source",
                        "fetched_at_utc")}
                    g["tournament"] = e.get("tournament")
                    fh.write(json.dumps(g) + "\n")
                    n2 += 1

print("records per market (all quotes):", dict(n_rec))
print("selections (last pre-ko):", len(rows), "events:", len(cand_events), "twosided rows:", n2)
c = Counter((r["market_id"], r["tournament"]) for r in rows)
for k, v in sorted(c.items()):
    print(k, v)
