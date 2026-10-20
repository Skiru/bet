#!/usr/bin/env python3
"""A chat slip (AKO) to a target price from the day's coupon
(bet.sofa.slip_builder) - outside the pipeline, read-only, no network.

Fewest legs that reach the target with the highest measured chance, one leg
per match, families on the plus first; the first line says how many of the
requested slips the day supports. No slip price, no stake.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/build_slip.py \\
        --date 2026-10-20 --target 5 [--slips 2] [--max-legs 5] [--allow-rest] \\
        [--min-odds 1.10] [--max-odds 2.00] [--start-from 10:00 --start-to 12:00] \\
        [--md-out f]

--start-from / --start-to: kickoff window in the operator's local time
(Europe/Warsaw), [from, to).

Exit 0: every requested slip is supported; 1: fewer (the answer says so);
2: no 11_coupon.json.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa import slip_builder as sb  # noqa: E402
from bet.sofa.confidence import COUPON_ARTIFACT, coupon_artifact  # noqa: E402
from bet.sofa.timeutil import now as utc_now  # noqa: E402

LOCAL = ZoneInfo("Europe/Warsaw")


def window(
    day: str, start_from: str | None, start_to: str | None
) -> tuple[datetime.datetime, datetime.datetime] | None:
    """The kickoff window [from, to) of `day` in local time, as UTC."""
    if start_from is None and start_to is None:
        return None
    d = datetime.date.fromisoformat(day)

    def at(hhmm: str) -> datetime.datetime:
        t = datetime.time.fromisoformat(hhmm)
        return datetime.datetime.combine(d, t, LOCAL).astimezone(datetime.UTC)

    lo = (
        at(start_from)
        if start_from
        else datetime.datetime.min.replace(tzinfo=datetime.UTC)
    )
    hi = (
        at(start_to) if start_to else datetime.datetime.max.replace(tzinfo=datetime.UTC)
    )
    return lo, hi


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--slips", type=int, default=1)
    ap.add_argument("--max-legs", type=int, default=sb.MAX_LEGS)
    ap.add_argument("--min-odds", type=float, default=sb.MIN_LEG_ODDS)
    ap.add_argument("--max-odds", type=float, default=sb.MAX_LEG_ODDS)
    ap.add_argument(
        "--allow-rest",
        action="store_true",
        help="fill missing slips from legs outside families on the plus",
    )
    ap.add_argument("--start-from", default=None, help="HH:MM local (Europe/Warsaw)")
    ap.add_argument("--start-to", default=None, help="HH:MM local, exclusive")
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    if args.target <= 1.0 or args.slips < 1 or args.max_legs < 1:
        ap.error("--target > 1, --slips >= 1, --max-legs >= 1")

    run = Path(args.runs_dir) / args.date
    path = coupon_artifact(run)
    if path.name != COUPON_ARTIFACT or not path.exists():
        print(f"FAILED: no {COUPON_ARTIFACT} in {run}", file=sys.stderr)
        return 2
    coupon = json.loads(path.read_text(encoding="utf-8"))
    record = fr.load(run, args.date)
    if record is None:
        print(
            f"WARN: no usable {fr.FILE} for {args.date} - no leg has a measured chance",
            file=sys.stderr,
        )
    now = utc_now()
    result = sb.build(
        coupon.get("singles") or [],
        record,
        now,
        args.target,
        args.slips,
        max_legs=args.max_legs,
        allow_rest=args.allow_rest,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        window=window(args.date, args.start_from, args.start_to),
    )
    text = sb.render(result, day=args.date, target=args.target, record=record, now=now)
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    print(text)
    return 0 if result.supported >= args.slips else 1


if __name__ == "__main__":
    sys.exit(main())
