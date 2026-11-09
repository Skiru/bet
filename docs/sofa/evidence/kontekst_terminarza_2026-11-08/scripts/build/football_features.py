"""Football schedule features of every finished football event from
2024-07-01 to 2026-11-01 (both sides), as of its kick-off, from the union
calendar on the DB copy (bet.sofa.schedule_features; pre-registration 4.1).
Outcome-free (no score is written). -> OUT/football_features.pkl:
{event_id: {"ts", "comp", "season", "national", "home": {...}, "away": {...}}}.
"""
from __future__ import annotations

import json
import pickle
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa.schedule_features import (  # noqa: E402
    calendar_from_events,
    iter_listed_events,
)

COPY = REPO / "data/refit_2026-11-08_schedule/sofa_copy.db"
OUT = REPO / "data/refit_2026-11-08_schedule/football_features.pkl"
FROM, TO = 1719792000, 1793491200
continental = json.loads((REPO / "config/sofa_cup_strength.json").read_text())["competitions"]
t0 = time.time()
conn = sqlite3.connect(f"file:{COPY}?mode=ro", uri=True)
cal = calendar_from_events(iter_listed_events(conn, "football"), "football",
                           continental=[int(c) for c in continental])
print("calendar", len(cal), round(time.time() - t0), flush=True)
out = {}
for m in list(cal._by_id.values()):
    if not (FROM <= m.ts < TO) or not m.finished:
        continue
    h = cal.football_side(m.home_id, m.ts, m.competition_id, m.season_id)
    a = cal.football_side(m.away_id, m.ts, m.competition_id, m.season_id)
    out[m.event_id] = {
        "ts": m.ts, "comp": m.competition_id, "season": m.season_id,
        "national": m.national, "friendly": m.friendly,
        "home_id": m.home_id, "away_id": m.away_id,
        "home": h, "away": a,
    }
OUT.write_bytes(pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
print("events", len(out), "secs", round(time.time() - t0), flush=True)
