"""Volleyball history for the rally model, read-only: the LIVE listed-event index only
(sofa_listed_event by sport - indexed, no page scan), parsed as sport_confidence.parse_history(golden_set=True).
Pages-only events (not in the index) are missed - named in the report."""
import pickle, sqlite3, sys, time, resource
sys.path[:0] = ["/Users/mkoziol/projects/bet/src", "/Users/mkoziol/projects/bet"]
from bet.sofa.listing_index import iter_indexed_events
from bet.sofa.shadow import SPORTS
from bet.sofa.sport_confidence import parse_history
t = time.time(); sport = SPORTS["volleyball"]
live = sqlite3.connect("file:/Users/mkoziol/projects/bet/data/sofa.db?mode=ro", uri=True)
live.execute("PRAGMA busy_timeout = 60000")
events = {e["id"]: e for e in iter_indexed_events(live, {}, sport=sport.sofascore_slug)}
print("events", len(events), round(time.time() - t), flush=True)
hist = parse_history(events, sport, golden_set=True)
out = []
for g in hist:
    r, res = g.rating, g.result
    if res is None or not res.t1_periods: continue
    out.append((r.event_id, r.ts, r.competition_id, r.home_id, r.away_id, bool(r.women), tuple(res.t1_periods), tuple(res.t2_periods)))
print("games", len(out), "last", max(x[1] for x in out), round(time.time() - t), "maxrss MB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, flush=True)
pickle.dump(out, open("vb_history.pkl", "wb"))
