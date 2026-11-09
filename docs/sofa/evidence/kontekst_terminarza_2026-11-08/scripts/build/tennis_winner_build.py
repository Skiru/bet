"""Tennis winner arms, day-gated (r3 D5 / D14; pre-registration 4.2 / 5).

Both arms: tennis_rating history (score_winner, as SHEET), RatingBook with the
tier start fitted before 2026-01-01; every match of UTC day D gets its
features from the book as of D 00:00Z (no update of D seen). Base arm =
installed V5 feature names; treatment = dmin78 / drest / dn7 replaced by the
player differences of schedule_features (as of D 00:00Z).

Writes OUT/tw_dev.pkl (rows with y, ts < 2026-01-01) and, for the exam
period, OUT/tw_exam_X.pkl (features, no outcome) and OUT/tw_exam_y.pkl
(event_id -> y), G2.
"""
from __future__ import annotations

import pickle
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.schedule_features import (  # noqa: E402
    TENNIS_COLUMNS,
    calendar_from_events,
    iter_listed_events,
)

COPY = REPO / "data/refit_2026-11-08_schedule/sofa_copy.db"
OUT = REPO / "data/refit_2026-11-08_schedule/tennis"
OUT.mkdir(parents=True, exist_ok=True)
DEV_CUT = 1767225600  # 2026-01-01
EXAM_END = 1793491200  # 2026-11-01
FROM = 0 if "--all" in sys.argv else 1719792000  # 2024-07-01 (rows counted from)
PREFIX = "tw_all" if "--all" in sys.argv else "tw"
TREAT_REPLACES = ("dmin78", "drest", "dn7")
DIFF_COLS = tuple(c for c in TENNIS_COLUMNS if c != "qual")  # qual is per match

t0 = time.time()
history = tr.load_history(str(COPY), score_winner=True)
print("history", len(history), round(time.time() - t0), flush=True)
conn = sqlite3.connect(f"file:{COPY}?mode=ro", uri=True)
tour_of: dict[int, int | None] = {}


def stream():  # type: ignore[no-untyped-def]
    for e in iter_listed_events(conn, "tennis"):
        tour_of[e["id"]] = (e.get("tournament") or {}).get("id")
        yield e


cal = calendar_from_events(stream(), "tennis")
print("calendar", len(cal), round(time.time() - t0), flush=True)
tier_start = tr.fit_tier_start(history, DEV_CUT)

book = tr.RatingBook(tier_start)
by_day: dict[int, list[tr.TennisResult]] = defaultdict(list)
for r in history:
    if r.ts >= EXAM_END:
        break
    by_day[r.ts // 86400].append(r)

dev, exam_x, exam_y = [], [], {}
for day in sorted(by_day):
    start = day * 86400
    todays = by_day[day]
    for r in todays:
        if not (r.completed and book.rated(r.home_id) >= tr.MIN_RATED
                and book.rated(r.away_id) >= tr.MIN_RATED):
            continue
        if r.ts < FROM:
            continue
        base = book.features(r.home_id, r.away_id, r.surface, start)
        tour = tour_of.get(r.event_id)
        fh = cal.tennis_player(r.home_id, start, tour, r.surface)
        fa = cal.tennis_player(r.away_id, start, tour, r.surface)
        ch, ca = fh.columns(), fa.columns()
        sched = {f"d_{c}": ch[c] - ca[c] for c in DIFF_COLS}
        sched |= {f"s_{c}": ch[c] + ca[c] for c in DIFF_COLS}
        sched |= {f"max_{c}": max(ch[c], ca[c]) for c in DIFF_COLS}
        sched["coverage"] = float(fh.coverage and fa.coverage)
        rec = {
            "event_id": r.event_id, "ts": r.ts, "tier": r.tier, "female": r.female,
            "best_of": tr.best_of(r), "home_id": r.home_id, "away_id": r.away_id,
            "tournament_id": tour, "base": base, "sched": sched,
            "minutes_known": r.minutes is not None, "female_flag": r.female,
        }
        y = 1.0 if r.home_won else 0.0
        if r.ts >= DEV_CUT:
            exam_x.append(rec)
            exam_y[r.event_id] = y
        else:
            rec["y"] = y
            dev.append(rec)
    for r in todays:
        book.update(r)

for name, obj in ((f"{PREFIX}_dev.pkl", dev), (f"{PREFIX}_exam_X.pkl", exam_x),
                  (f"{PREFIX}_exam_y.pkl", exam_y)):
    (OUT / name).write_bytes(pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL))
print("dev", len(dev), "exam", len(exam_x), "secs", round(time.time() - t0), flush=True)
