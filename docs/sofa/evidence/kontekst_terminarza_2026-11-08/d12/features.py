"""D12 phase 2: schedule features of the fixtures of 10-13..11-07, exactly as
football_features.py (Calendar on the DB copy); compared with the pkl where it
covers the event."""
from __future__ import annotations
import json, pickle, sqlite3, sys, time
from pathlib import Path
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa.schedule_features import calendar_from_events, iter_listed_events  # noqa: E402

D12 = REPO / "data/refit_2026-11-08_schedule/d12"
COPY = REPO / "data/refit_2026-11-08_schedule/sofa_copy.db"
need = set()
for p in sorted((D12 / "days").glob("*.pkl")):
    need |= set(pickle.loads(p.read_bytes())["fixtures"])
print("events needed", len(need), flush=True)
continental = json.loads((REPO / "config/sofa_cup_strength.json").read_text())["competitions"]
t0 = time.time()
conn = sqlite3.connect(f"file:{COPY}?mode=ro", uri=True)
cal = calendar_from_events(iter_listed_events(conn, "football"), "football",
                           continental=[int(c) for c in continental])
print("calendar", len(cal), round(time.time() - t0), flush=True)
from bet.sofa.schedule_features import match_from_event  # noqa: E402
not_listed = [e for e in need if e not in cal._by_id]
added = 0
for eid in not_listed:
    r = conn.execute("SELECT detail_json FROM sofa_event_detail WHERE sofascore_event_id = ?", (eid,)).fetchone()
    if r is None:
        continue
    ev = json.loads(r[0]).get("event")
    m = match_from_event(ev, "football") if isinstance(ev, dict) else None
    if m is not None:
        cal.add(m)
        added += 1
print("fixtures not in sofa_listed_event", len(not_listed), "added from sofa_event_detail", added, flush=True)
out, missing = {}, []
for eid in need:
    m = cal._by_id.get(eid)
    if m is None:
        missing.append(eid)
        continue
    out[eid] = {"ts": m.ts, "comp": m.competition_id, "season": m.season_id,
                "national": m.national, "friendly": m.friendly,
                "home_id": m.home_id, "away_id": m.away_id,
                "home": cal.football_side(m.home_id, m.ts, m.competition_id, m.season_id),
                "away": cal.football_side(m.away_id, m.ts, m.competition_id, m.season_id)}
pk = pickle.loads((REPO / "data/refit_2026-11-08_schedule/football_features.pkl").read_bytes())
both = [e for e in out if e in pk]
diff = [e for e in both if (out[e]["home"], out[e]["away"], out[e]["national"]) != (pk[e]["home"], pk[e]["away"], pk[e]["national"])]
print("computed", len(out), "missing from calendar", len(missing), "in pkl", len(both), "differ from pkl", len(diff), flush=True)
(D12 / "features_d12.pkl").write_bytes(pickle.dumps({"features": out, "missing": missing,
    "pkl_overlap": len(both), "pkl_differ": diff}, protocol=pickle.HIGHEST_PROTOCOL))
