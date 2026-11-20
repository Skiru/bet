"""CS2 'Liczba dogrywek' (231528): offered events, last pre-start price, pinned Sofascore id, format,
tournament, grade from cs2_map rounds. Read-only. Output cs2_ot_events.json."""
import json, glob, sqlite3, collections, statistics
from datetime import datetime
ROOT = "/Users/mkoziol/projects/bet/runs/sofa"
DB = "file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro"
def ts(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
# kickoff, names, tournament from CS2 snapshots
meta = {}
for f in glob.glob(f"{ROOT}/cs2/2026-11-*/snapshots.jsonl"):
    for line in open(f):
        s = json.loads(line)
        meta.setdefault(s["superbet_event_id"], {}).update(
            kickoff=s["kickoff_utc"], team1=s["team1"], team2=s["team2"], tournament=s["tournament"])
# pins
pins = {}
for f in sorted(glob.glob(f"{ROOT}/2026-1*/sport_fixtures.json")):
    for fx in json.load(open(f)).get("fixtures", []):
        if fx.get("sport") == "cs2":
            if fx.get("sofascore_event_id") or fx["superbet_event_id"] not in pins:
                pins[fx["superbet_event_id"]] = fx
quotes = collections.defaultdict(dict)  # sb -> ts -> {name: price}
for l in open("unmapped_candidates.jsonl"):
    r = json.loads(l)
    if r["mid"] == 231528:
        quotes[r["sb"]].setdefault(r["ts"], {})[r["name"]] = r["price"]
conn = sqlite3.connect(DB, uri=True)
out = []
for sb, byts in quotes.items():
    m = meta.get(sb, {})
    ko = m.get("kickoff")
    pre = [t for t in byts if ko is None or ts(t) < ts(ko)]
    if not pre: continue
    t = max(pre); q = byts[t]
    u, o = q.get("Poniżej 0.5"), q.get("Powyżej 0.5")
    fx = pins.get(sb, {})
    eid = fx.get("sofascore_event_id")
    row = dict(sb=sb, ts=t, kickoff=ko, under=u, over=o, n_snap=len(pre), tournament=m.get("tournament"),
               team1=m.get("team1"), team2=m.get("team2"), sofa=eid, pin_status=fx.get("status"),
               home_is_team1=fx.get("home_is_team1"), home_id=fx.get("home_id"), away_id=fx.get("away_id"))
    if eid:
        s = conn.execute("select best_of, status_type, status_description, home_maps, away_maps, start_ts from cs2_series where sofascore_event_id=?", (eid,)).fetchone()
        if s:
            row.update(best_of=s[0], s_status=s[1], s_desc=s[2], home_maps=s[3], away_maps=s[4])
            maps = conn.execute("select map_order, status_type, home_rounds, away_rounds, home_overtime, away_overtime from cs2_map where sofascore_event_id=? order by map_order", (eid,)).fetchall()
            fin = [mp for mp in maps if mp[1] == "finished"]
            row["maps"] = [[mp[2], mp[3]] for mp in fin]
            ok = (s[1] == "finished" and s[2] == "Ended" and s[3] is not None and len(fin) == (s[3] or 0) + (s[4] or 0)
                  and all(mp[2] is not None and mp[3] is not None for mp in fin))
            if ok:
                row["ot_maps"] = sum(1 for mp in fin if mp[2] + mp[3] >= 25)
                row["ot_maps_col"] = sum(1 for mp in fin if (mp[4] or 0) + (mp[5] or 0) > 0)
                row["graded"] = True
            else:
                row["graded"] = False
    out.append(row)
json.dump(out, open("cs2_ot_events.json", "w"), indent=0)
print("events", len(out), "pinned", sum(1 for r in out if r["sofa"]), "in cs2_series", sum(1 for r in out if "best_of" in r),
      "graded", sum(1 for r in out if r.get("graded")))
print("best_of", collections.Counter(r.get("best_of") for r in out))
print("tournaments", collections.Counter(r["tournament"] for r in out).most_common(15))
print("days", collections.Counter((r["kickoff"] or "")[:10] for r in out))
g = [r for r in out if r.get("graded")]
print("OT any map (rounds>=25):", sum(r["ot_maps"] > 0 for r in g), "/", len(g), " via overtime cols:", sum(r["ot_maps_col"] > 0 for r in g))
ov = [ (1/r["under"])+(1/r["over"])-1 for r in out if r["under"] and r["over"]]
print("overround mean %.3f min %.3f max %.3f" % (statistics.mean(ov), min(ov), max(ov)))
fu = sorted((1/r["under"])/((1/r["under"])+(1/r["over"])) for r in out if r["under"] and r["over"])
print("fair p(Under) quantiles", [round(fu[int(i*(len(fu)-1))],3) for i in (0,0.1,0.25,0.5,0.75,0.9,1)])
print("under price quantiles", sorted(r["under"] for r in out)[::6])
for r in out:
    if not r.get("graded"): print("NOT GRADED", r["sb"], r["tournament"], r["team1"], r["team2"], r.get("pin_status"), r.get("s_status"), r.get("s_desc"), r.get("maps"), r.get("home_maps"), r.get("away_maps"))
