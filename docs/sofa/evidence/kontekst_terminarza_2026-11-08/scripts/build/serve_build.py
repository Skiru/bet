"""tennis_serve group - X rows (pre-registration 2, 4.2, 5 tennis_serve; STAN 1-12).

usage: serve_build.py dev|exam|all

One walk-forward of the installed point model (tennis_point_model.walk_forward,
hyperparameters as installed - M10) over the cached singles history of the
schedule copy; every match starting 2025-05-01 .. 2026-10-31 (UTC) is forecast
from the beliefs before its start (as fit_tennis_point_curves.py /
tennis_point_sheet). Per match and player: the model's serve forecast (logit,
var, ace / df rates; the whole MatchForecast is kept so the simulation can be
re-run for both arms with the event-id seed) and the player's schedule
features (schedule_features.Calendar.tennis_player, state at 00:00Z of the
match day - exactly as tennis_winner_build.py; `qual` from the match's own
listing payload, outcome-free).

Best of three only. The live rule (tennis_point_sheet.fixture_match) reads the
fixture's defaultPeriodCount; the listing payloads of the history do not carry
it (checked: 0 of 20,000 rows), so the format is decided AS OF the start:
best of five when an earlier completed match of the same listing tournament id
(any earlier year) was won 3 sets to something, else best of three. Dev rows
additionally drop a match whose own score says best of five (dev outcomes are
allowed); exam rows are never filtered on anything of their own outcome.

Outputs (tennis/):
  serve_dev.pkl     rows with ts < 2026-01-01, with the PointMatch (outcomes)
  serve_exam_X.pkl  rows 2026-01-01 .. 2026-10-31: forecast + features only;
                    no score, no serve counts, no completion flag (G2)
"""
from __future__ import annotations

import datetime as dt
import pickle
import sqlite3
import sys
import time
from pathlib import Path

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa.schedule_features import (  # noqa: E402
    TENNIS_COLUMNS,
    calendar_from_events,
    iter_listed_events,
)
from bet.sofa.tennis_point_model import (  # noqa: E402
    PointMatch,
    PointModel,
    load_point_history,
)

D = REPO / "data/refit_2026-11-08_schedule"
T = D / "tennis"
T.mkdir(parents=True, exist_ok=True)
COPY = D / "sofa_copy.db"
HIST_CACHE = T / "serve_point_history.pkl"


def _ts(y: int, m: int, d: int) -> int:
    return int(dt.datetime(y, m, d, tzinfo=dt.UTC).timestamp())


FROM = _ts(2025, 5, 1)
DEV_CUT = _ts(2026, 1, 1)
EXAM_END = _ts(2026, 11, 1)

mode = sys.argv[1] if len(sys.argv) > 1 else "all"
assert mode in ("dev", "exam", "all"), mode
t0 = time.time()

if HIST_CACHE.exists():
    history: list[PointMatch] = pickle.loads(HIST_CACHE.read_bytes())
else:
    history = load_point_history(COPY)
    HIST_CACHE.write_bytes(pickle.dumps(history, protocol=pickle.HIGHEST_PROTOCOL))
print("history", len(history), round(time.time() - t0), flush=True)

conn = sqlite3.connect(f"file:{COPY}?mode=ro", uri=True)
tour_of: dict[int, int | None] = {}


def stream():  # type: ignore[no-untyped-def]
    for e in iter_listed_events(conn, "tennis"):
        tour_of[e["id"]] = (e.get("tournament") or {}).get("id")
        yield e


cal = calendar_from_events(stream(), "tennis")
print("calendar", len(cal), round(time.time() - t0), flush=True)


def best_of_score(m: PointMatch) -> int | None:
    hs = sum(1 for h, a in m.sets if h > a)
    as_ = sum(1 for h, a in m.sets if a > h)
    won = max(hs, as_)
    return 5 if won == 3 else 3 if won == 2 else None


def tour_key(m: PointMatch) -> tuple[str, int] | None:
    t = tour_of.get(m.event_id)
    if isinstance(t, int):
        return ("listing", t)
    return ("unique", m.tournament) if m.tournament is not None else None


def player_feats(pid: int, start: int, tour: int | None, surface: str,
                 qual: bool) -> dict[str, float]:
    f = cal.tennis_player(pid, start, tour, surface, qualifying=qual)
    cols = f.columns()
    out = {c: float(cols[c]) for c in TENNIS_COLUMNS}
    out["coverage"] = float(f.coverage)
    # dom_prev raw (None -> the column's 0.5) kept for the record
    out["dom_prev_known"] = float(f.dom_prev is not None)
    return out


model = PointModel()
bo5_tours: set[tuple[str, int]] = set()
dev, exam_x = [], []
counts = {"window": 0, "bo5_asof": 0, "bo5_score_dev": 0, "dev": 0, "exam": 0}
i = 0
n = len(history)
while i < n:
    j = i
    while j < n and history[j].ts == history[i].ts:
        j += 1
    group = history[i:j]
    for m in group:
        if not (FROM <= m.ts < EXAM_END):
            continue
        counts["window"] += 1
        tk = tour_key(m)
        if tk is not None and tk in bo5_tours:
            counts["bo5_asof"] += 1
            continue
        is_dev = m.ts < DEV_CUT
        if is_dev and best_of_score(m) == 5:
            counts["bo5_score_dev"] += 1
            continue
        if not is_dev and mode == "dev":
            continue
        if is_dev and mode == "exam":
            continue
        fc = model.forecast(m)
        start = (m.ts // 86400) * 86400
        lt = tour_of.get(m.event_id)
        cm = cal._by_id.get(m.event_id)
        qual = bool(cm.qualifying) if cm is not None else False
        rec = {
            "event_id": m.event_id, "ts": m.ts, "tier": m.tier, "female": m.female,
            "surface": m.surface, "tournament_unique": m.tournament,
            "tournament_id": lt if isinstance(lt, int) else m.tournament,
            "in_listing": cm is not None,
            "home_id": m.home_id, "away_id": m.away_id,
            "forecast": fc, "qual": qual,
            "feats": {
                "home": player_feats(m.home_id, start, lt, m.surface, qual),
                "away": player_feats(m.away_id, start, lt, m.surface, qual),
            },
        }
        if is_dev:
            rec["pm"] = m
            dev.append(rec)
            counts["dev"] += 1
        else:
            exam_x.append(rec)
            counts["exam"] += 1
    for m in group:
        model.update(m)
        if m.completed and best_of_score(m) == 5:
            tk = tour_key(m)
            if tk is not None:
                bo5_tours.add(tk)
    i = j
    if j and history[j - 1].ts >= EXAM_END:
        break

if mode in ("dev", "all"):
    (T / "serve_dev.pkl").write_bytes(pickle.dumps(dev, protocol=pickle.HIGHEST_PROTOCOL))
if mode in ("exam", "all"):
    (T / "serve_exam_X.pkl").write_bytes(
        pickle.dumps(exam_x, protocol=pickle.HIGHEST_PROTOCOL))
print("counts", counts, "secs", round(time.time() - t0), flush=True)
