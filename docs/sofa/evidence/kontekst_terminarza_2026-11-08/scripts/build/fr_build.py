"""football_result: 90-minute goals of every finished football event,
split by the seal (G2): dev -> fr_dev_y.pkl, exam -> full/exam_y/fr_y.pkl.
{event_id: (home_goals, away_goals)} from homeScore / awayScore normaltime
(else current when no extra time was played)."""
from __future__ import annotations

import json
import pickle
import sqlite3
import sys
from pathlib import Path

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa.metrics import played_extra_time  # noqa: E402

D = REPO / "data/refit_2026-11-08_schedule"
EXAM_FROM, FROM, TO = 1767225600, 1719792000, 1793491200
conn = sqlite3.connect(f"file:{D / 'sofa_copy.db'}?mode=ro", uri=True)
dev, exam = {}, {}
for eid, ts, raw in conn.execute(
        "SELECT event_id, start_ts, event_json FROM sofa_listed_event WHERE sport='football' "
        "AND start_ts >= ? AND start_ts < ?", (FROM, TO)):
    e = json.loads(raw)
    if (e.get("status") or {}).get("type") != "finished":
        continue
    hs, as_ = e.get("homeScore") or {}, e.get("awayScore") or {}
    h, a = hs.get("normaltime"), as_.get("normaltime")
    if not (isinstance(h, int) and isinstance(a, int)):
        try:
            if played_extra_time(e):
                continue
        except Exception:  # noqa: BLE001
            continue
        h, a = hs.get("current"), as_.get("current")
    if not (isinstance(h, int) and isinstance(a, int)):
        continue
    (exam if ts >= EXAM_FROM else dev)[eid] = (h, a)
(D / "fr_dev_y.pkl").write_bytes(pickle.dumps(dev))
(D / "full/exam_y").mkdir(parents=True, exist_ok=True)
(D / "full/exam_y/fr_y.pkl").write_bytes(pickle.dumps(exam))
print("dev", len(dev), "exam", len(exam))
