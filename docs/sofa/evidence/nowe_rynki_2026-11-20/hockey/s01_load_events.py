"""Load every indexed hockey listing payload (keyed: sofa_listed_event by sport index), pickle."""
import json, pickle, sqlite3, sys, resource
OUT = sys.argv[1]
con = sqlite3.connect('file:data/sofa.db?mode=ro', uri=True)
con.execute("PRAGMA busy_timeout = 60000")
ids = [r[0] for r in con.execute("SELECT event_id FROM sofa_listed_event WHERE sport = ?", ('ice-hockey',))]
ids.sort()
events = {}
for i in range(0, len(ids), 500):
    chunk = ids[i:i+500]
    q = "SELECT event_json FROM sofa_listed_event WHERE event_id IN (%s)" % ",".join("?"*len(chunk))
    for (js,) in con.execute(q, chunk):
        e = json.loads(js)
        if isinstance(e.get('id'), int):
            events[e['id']] = e
print(len(ids), len(events), 'maxrss MB', resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e6)
pickle.dump(events, open(OUT, 'wb'))
