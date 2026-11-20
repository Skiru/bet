"""Walk-forward pure-rating centres (as of each start, BOOK_DAY flags of the sim fit) for the football
fixtures of 11-06..11-19 - the same machinery as measure_football_sim.load_live_forecasts / live_history
(the backfill of data/line_evidence/football_sim_lines.jsonl.gz), extended past 11-05. Read-only DB."""
import json, pickle, sqlite3, sys, time
from pathlib import Path
sys.path[:0] = ["src", "."]
from bet.sofa import epochs
from bet.sofa.football_rating import assign_league_units, mark_second_squads, parse_event, without_awarded
from bet.sofa.football_sim import walk_forward_centres
from scripts.sofa.measure_football_sim import BOOK_DAY, fresh_book, load_football_history

OUT = Path(sys.argv[1])
DAYS = [f"2026-11-{d:02d}" for d in range(6, 20)]
t0 = time.time()
history = load_football_history(Path("data/cache/football_history.pkl"))
print("history", len(history), f"{time.time()-t0:.0f}s", flush=True)
want = set()
for day in DAYS:
    for f in json.load(open(f"runs/sofa/{day}/02_fixtures.json")):
        if f.get("sport") == "football":
            want.add(int(f["sofascore_event_id"]))
have = {int(r.event_id) for r in history}
missing = sorted(want - have)
print("wanted", len(want), "missing from history", len(missing), flush=True)
conn = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
conn.execute("PRAGMA busy_timeout = 60000")
added = []
for i in range(0, len(missing), 500):
    chunk = missing[i:i + 500]
    q = ",".join("?" * len(chunk))
    details = dict(conn.execute(f"SELECT sofascore_event_id, detail_json FROM sofa_event_detail WHERE sofascore_event_id IN ({q})", chunk).fetchall())
    stats = {int(e): (s, inc) for e, s, inc in conn.execute(f"SELECT sofascore_event_id, statistics_json, incidents_json FROM sofa_event_stats WHERE sofascore_event_id IN ({q})", chunk)}
    for eid in chunk:
        d = details.get(eid)
        if not d:
            continue
        event = (json.loads(d) or {}).get("event")
        if not isinstance(event, dict):
            continue
        s_json, i_json = stats.get(eid, (None, None))
        r = parse_event(event, json.loads(s_json) if s_json else None, json.loads(i_json) if i_json else None)
        if r is not None:
            added.append(r)
conn.close()
print("parsed from /event", len(added), flush=True)
merged = assign_league_units(mark_second_squads(sorted([*history, *added], key=lambda r: (r.ts, r.event_id))))
del history
hist = without_awarded(merged) if epochs.awarded_excluded(BOOK_DAY) else merged
out = walk_forward_centres(hist, want, fresh_book())
print("forecasts", len(out), "with goals", sum(1 for v in out.values() if "goals_for" in v), f"{time.time()-t0:.0f}s", flush=True)
(OUT / "centres_live_1106_1119.pkl").write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
