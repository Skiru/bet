#!/usr/bin/env python3
"""P14 (coverage audit 2026-10-23): what epochs.TENNIS_RATING_SCORE_WINNER
adds to the tennis rating and what it would move on a built day. Read-only.

    PYTHONPATH=src:. .venv/bin/python \\
        scripts/sofa/measure_audit1023_p14_tennis_rating.py \\
        --db-path data/refit_2026-10-23_allin/sofa_copy.db --date 2026-10-23

Counts the history matches load_history(score_winner=True) holds that the old
parser drops (by reason: winner from the set score, a type-0 player; within
the last 365 days of the cut; completed = rating updates), then builds the
day's rating model both ways (cut = the day's 00:00Z, the config SHEET reads,
the day's scoped rule) and forecasts every tennis fixture of 02_fixtures.json:
fixtures whose p_home moves, by how much, and how many 08_confidence /
11_coupon tennis legs sit on them. Writes nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs, tennis_rating
from bet.sofa.tennis_rating import (
    TennisResult,
    build_model,
    load_coefficients,
    load_history,
    start_for_rule,
)

RUNS = Path("runs/sofa")


def _legs(path: Path, key: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    doc = json.loads(path.read_text())
    rows = doc.get(key) if isinstance(doc, dict) else doc
    return [r for r in rows or [] if r.get("sport") == "tennis"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", required=True)
    ap.add_argument("--date", required=True)
    args = ap.parse_args(argv)

    cut_dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
    cut = int(cut_dt.timestamp())
    old = load_history(args.db_path)
    new = load_history(args.db_path, score_winner=True)
    old_ids = {r.event_id for r in old}
    added = [r for r in new if r.event_id not in old_ids]
    lost = old_ids - {r.event_id for r in new}
    year = cut - 365 * 86400

    def summary(rows: list[TennisResult]) -> dict[str, int]:
        return {
            "all": len(rows),
            "before_cut": sum(r.ts < cut for r in rows),
            "last_365d_before_cut": sum(year <= r.ts < cut for r in rows),
            "completed_before_cut": sum(r.completed and r.ts < cut for r in rows),
        }

    # by reason: re-parse the added ones' payload is not kept, so classify by
    # whether the old parser would have read them with a type-1 side forced
    by_type0 = [r for r in added if r.event_id in _type0_ids(args.db_path, added)]
    report: dict[str, Any] = {
        "db": args.db_path, "date": args.date,
        "history_old": len(old), "history_new": len(new),
        "added": summary(added),
        "added_type0_side": summary(by_type0),
        "lost": len(lost),
        "17362029_added": any(r.event_id == 17362029 for r in added),
    }

    loaded = load_coefficients()
    if loaded is None:
        print(json.dumps(report, indent=2))
        print("no config/tennis_rating.json", file=sys.stderr)
        return 1
    coefficients, meta = loaded
    scoped = (epochs.stats_only(args.date)
              and epochs.tennis_scoped_table_enabled(args.date))
    names = meta["features"]
    start = (meta.get("tier_start") if scoped
             else start_for_rule(names, meta.get("tier_start"), False))

    def model(history: list[TennisResult]) -> tennis_rating.TennisRatingModel:
        return build_model(history, coefficients, cut, names=names,
                           scoped=scoped, tier_start=start)

    m_old, m_new = model(old), model(new)
    run = RUNS / args.date
    fixtures = [f for f in json.loads((run / "02_fixtures.json").read_text())
                if f.get("sport") == "tennis"]
    moved: dict[int, float] = {}
    rated_old = rated_new = 0
    for f in fixtures:
        if f.get("default_period_count") not in (None, 3):
            continue
        ko = datetime.fromisoformat(f["kickoff_utc"].replace("Z", "+00:00"))
        args_ = (int(f["home_entity_id"]), int(f["away_entity_id"]),
                 str(f.get("category_name") or ""), f.get("ground_type"), ko)
        a, b = m_old.forecast(*args_), m_new.forecast(*args_)
        rated_old += a is not None
        rated_new += b is not None
        pa = a.p_home if a is not None else None
        pb = b.p_home if b is not None else None
        if pa != pb:
            moved[int(f["sofascore_event_id"])] = (
                abs(pb - pa) if pa is not None and pb is not None else float("nan"))
    conf = _legs(run / "08_confidence.json", "legs")
    coupon_doc = json.loads((run / "11_coupon.json").read_text())
    printed = [leg for leg in coupon_doc.get("singles", []) or []
               if leg.get("sport") == "tennis"]
    deltas = sorted((d for d in moved.values() if d == d), reverse=True)
    report.update({
        "scoped": scoped,
        "tennis_fixtures": len(fixtures),
        "rated_fixtures_old": rated_old, "rated_fixtures_new": rated_new,
        "fixtures_p_home_moved": len(moved),
        "newly_rated_or_unrated": sum(1 for d in moved.values() if d != d),
        "max_abs_dp_home": deltas[0] if deltas else 0.0,
        "dp_home_over_0_01": sum(d > 0.01 for d in deltas),
        "top_moves": sorted(((eid, round(d, 4)) for eid, d in moved.items()
                             if d == d), key=lambda x: -x[1])[:10],
        "confidence_legs_tennis": len(conf),
        "confidence_legs_on_moved_fixtures": sum(
            int(r["sofascore_event_id"]) in moved for r in conf),
        "rating_sourced_legs_on_moved_fixtures": sum(
            int(r["sofascore_event_id"]) in moved
            and r.get("forecast_source") == "tennis_rating" for r in conf),
        "coupon_tennis_singles": len(printed),
        "coupon_tennis_singles_on_moved_fixtures": sum(
            int(leg.get("sofascore_event_id") or 0) in moved for leg in printed),
    })
    print(json.dumps(report, indent=2))
    return 0


def _type0_ids(db_path: str, added: list[TennisResult]) -> set[int]:
    """The added events at least one of whose sides is type 0 in the cached
    page copy (the newest parsed one wins in load_history; any copy here)."""
    import sqlite3

    want = {r.event_id for r in added}
    out: set[int] = set()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for (events_json,) in conn.execute(
            "SELECT events_json FROM sofa_entity_events WHERE kind = 'last' "
            "AND events_json LIKE '%\"slug\": \"tennis\"%' "
            "AND events_json LIKE '%\"type\": 0%'"
        ):
            for e in json.loads(events_json).get("events", []):
                if isinstance(e, dict) and e.get("id") in want and 0 in (
                    (e.get("homeTeam") or {}).get("type"),
                    (e.get("awayTeam") or {}).get("type"),
                ):
                    out.add(int(e["id"]))
    finally:
        conn.close()
    return out


if __name__ == "__main__":
    raise SystemExit(main())
