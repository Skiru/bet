import sqlite3, sys, pickle
import pandas as pd
S = sys.argv[1]
d = pd.read_pickle(f"{S}/listed.pkl")
ids = set(d.loc[(d.st == "finished") & (d.start_ts >= 1640995200), "event_id"].astype(int))
c = sqlite3.connect("file:data/sofa.db?mode=ro", uri=True)
out = {}
cur = c.execute("""select sofascore_event_id,
  statistics_json is not null and length(statistics_json) > 50,
  instr(statistics_json,'"cornerKicks"')>0,
  instr(statistics_json,'"totalShotsOnGoal"')>0,
  instr(statistics_json,'"yellowCards"')>0,
  instr(statistics_json,'"fouls"')>0
  from sofa_event_stats""")
for row in cur:
    if row[0] in ids:
        out[row[0]] = tuple(bool(x) for x in row[1:])
pickle.dump(out, open(f"{S}/stats_presence.pkl", "wb"))
print(len(out))
