#!/usr/bin/env python3
"""Closing line value of every printed variant, per variant, never pooled.

  * sport coupons (CS2, hockey, basketball, volleyball): each printed leg
    against the price its line was graded at - the latest pre-start
    snapshot (bet.sofa.clv.sport_coupon_rows);
  * the official PDF and the WARIANT: each printed leg against the closing
    price capture_closing.py recorded in runs/sofa/<d>/closing.jsonl.

Mean CLV = odds_taken x devigged closing probability - 1, with a 95%
interval from resampling whole matches, and the share of legs priced above
the close. A soft book's close (see bet.sofa.clv); an analysis tool, it
writes nothing the pipeline reads.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/audit_clv.py --from <d> --to <d>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.clv import ClvRow, is_close, sport_coupon_rows, summarize, two_way_close

SPORT_DIRS = {
    "cs2": ("cs2", ("superbet_event_id", "family", "map_nr", "subject", "line",
                    "side")),
    "hockey": ("shadow/hockey", ("superbet_event_id", "market_id", "period",
                                 "subject", "line", "side")),
    "basketball": ("shadow/basketball", ("superbet_event_id", "market_id", "period",
                                         "subject", "line", "side")),
    "volleyball": ("shadow/volleyball", ("superbet_event_id", "market_id", "period",
                                         "subject", "line", "side")),
}


def _days(a: str, b: str) -> list[str]:
    d0 = datetime.strptime(a, "%Y-%m-%d").replace(tzinfo=UTC)
    d1 = datetime.strptime(b, "%Y-%m-%d").replace(tzinfo=UTC)
    return [(d0 + timedelta(days=i)).strftime("%Y-%m-%d")
            for i in range((d1 - d0).days + 1)]


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sport_rows(runs: Path, day: str) -> list[ClvRow]:
    out: list[ClvRow] = []
    for sport, (sub, keys) in SPORT_DIRS.items():
        coupon = _json(runs / sub / day / "sport_coupon.json")
        settled = _json(runs / sub / day / "settled.json")
        if not coupon or not settled:
            continue
        events = settled.get("events", {})
        graded = [g for e in (events.values() if isinstance(events, dict) else events)
                  if isinstance(e, dict) for g in e.get("graded", [])]
        out += sport_coupon_rows(coupon, graded, f"sport:{sport}", keys)
    return out


def closing_rows(runs: Path, day: str) -> list[ClvRow]:
    """Rows from capture_closing.py's closing.jsonl, one per printed leg."""
    path = runs / day / "closing.jsonl"
    if not path.exists():
        return []
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not is_close(rec.get("minutes_before")):
            continue
        key = (rec["variant"], rec["leg_key"])
        if key not in latest or rec["fetched_at_utc"] > latest[key]["fetched_at_utc"]:
            latest[key] = rec
    out: list[ClvRow] = []
    for rec in latest.values():
        p = two_way_close(rec.get("odds_close"), rec.get("partner_close"))
        if p is None:
            continue
        out.append(ClvRow(rec["variant"], str(rec["sofascore_event_id"]),
                          rec["leg_key"], float(rec["odds_taken"]),
                          float(rec["odds_close"]), p))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--runs-dir", default="runs/sofa")
    args = ap.parse_args()
    runs = Path(args.runs_dir)
    rows: list[ClvRow] = []
    for day in _days(args.date_from, args.date_to):
        rows += sport_rows(runs, day) + closing_rows(runs, day)
    variants = sorted({r.variant for r in rows})
    print(f"# CLV {args.date_from}..{args.date_to} - Superbet's own close, power devig")
    print("| variant | legs | matches | mean CLV | 95% (by match) | above close |")
    print("|---|---|---|---|---|---|")
    for v in variants:
        s = summarize(rows, v)
        if s is None:
            continue
        print(f"| {v} | {s.legs} | {s.games} | {s.mean_clv_ev:+.2%} | "
              f"[{s.ci95[0]:+.2%}, {s.ci95[1]:+.2%}] | {s.beat_share:.0%} |")
    if not rows:
        print("no leg with a recorded close in the window")
    return 0


if __name__ == "__main__":
    sys.exit(main())
