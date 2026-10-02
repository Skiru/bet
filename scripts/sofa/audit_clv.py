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
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa.clv import (  # noqa: E402
    MIN_CLUSTERS,
    ClvRow,
    is_close,
    sport_coupon_rows,
    summarize,
    two_way_close,
)

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


def _next_day(day: str) -> str:
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def sport_rows(runs: Path, day: str) -> list[ClvRow]:
    """A day's sport-coupon legs against their graded close. A leg that starts
    after midnight UTC (NHL, NBA, a night CS2 series) is graded into the next
    day's settled.json, so both files are read."""
    out: list[ClvRow] = []
    for sport, (sub, keys) in SPORT_DIRS.items():
        coupon = _json(runs / sub / day / "sport_coupon.json")
        if not coupon:
            continue
        graded: list[dict[str, Any]] = []
        for d in (day, _next_day(day)):
            settled = _json(runs / sub / d / "settled.json")
            if not settled:
                continue
            events = settled.get("events", {})
            graded += [g for e in (events.values() if isinstance(events, dict)
                                   else events)
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
        # The latest record that carries a price wins. A `missing` record (a
        # market Superbet pulled, or - with `error` - a fetch that failed)
        # only stands when no pass inside the window priced the leg: a failed
        # last pass used to erase an earlier good close (1 of 96 legs on
        # 2026-10-01).
        rank = (not rec.get("missing") and not rec.get("error"),
                rec["fetched_at_utc"])
        held = latest.get(key)
        if held is None or rank > (not held.get("missing") and not held.get("error"),
                                   held["fetched_at_utc"]):
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
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
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
        ci = (f"- (<{MIN_CLUSTERS} matches)" if s.ci95 is None
              else f"[{s.ci95[0]:+.2%}, {s.ci95[1]:+.2%}]")
        print(f"| {v} | {s.legs} | {s.games} | {s.mean_clv_ev:+.2%} | "
              f"{ci} | {s.beat_share:.0%} |")
    if not rows:
        print("no leg with a recorded close in the window")
    # An official / WARIANT day with no closing file prints no row above, and
    # a missing row reads like "nothing to measure". Name it (2026-10-01).
    for day in _days(args.date_from, args.date_to):
        for line in missing_closes(runs, day):
            print(line)
    return 0


def missing_closes(runs: Path, day: str) -> list[str]:
    """`NO_CLOSING_FILE` for a day whose official / WARIANT artifact exists
    but whose closing.jsonl does not: capture_closing.py never ran for it."""
    day_dir = runs / day
    if (day_dir / "closing.jsonl").exists():
        return []
    built = [
        name
        for name in ("08_confidence.json", "08_confidence_wariant.json")
        if (day_dir / name).exists()
    ]
    if not built:
        return []
    return [
        f"NO_CLOSING_FILE {day}: {', '.join(built)} printed, but "
        f"{day_dir / 'closing.jsonl'} does not exist - capture_closing.py "
        "--loop was not run for it, so its CLV is unmeasured, not zero"
    ]


if __name__ == "__main__":
    sys.exit(main())
