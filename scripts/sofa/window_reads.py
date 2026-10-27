#!/usr/bin/env python3
"""The operator's kickoff window as read requests (bet.sofa.window_reads) -
`/sofa-analyze <day> okno 14-17`.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/window_reads.py \\
        --date 2026-10-27 --start-from 14:00 --start-to 17:00 [--top 20] [--dry-run]

The window's `--top` best-value matches (confidence.read_value of a match's
best unlocked printed single; every match when fewer) starting more than
30 min ahead (the coupon's 15-min kickoff margin + 15 min to read; a closer
match would come back unread) are appended to runs/sofa/<d>/read_requests.json
as whole-match requests - every market of the match. Run it on a fresh rebuild (prices
re-asked); then read_set.py --unread picks them up with the rest of C3.
--start-from / --start-to: local time (Europe/Warsaw), [from, to).

Exit 0: written (or nothing new to write); 1: no match in the window;
2: no 11_coupon.json or bad arguments.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import timeutil  # noqa: E402
from bet.sofa import window_reads as wr  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    COUPON_ARTIFACT,
    coupon_artifact,
    load_read_requests,
)
from bet.sofa.timeutil import now as utc_now  # noqa: E402
from scripts.sofa.build_slip import LOCAL, window  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--start-from", required=True, help="HH:MM local (Europe/Warsaw)")
    ap.add_argument("--start-to", required=True, help="HH:MM local, exclusive")
    ap.add_argument("--top", type=int, default=wr.TOP)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    args = ap.parse_args(argv)
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    if args.top < 1:
        ap.error("--top >= 1")
    now = utc_now()
    try:
        span = window(args.date, args.start_from, args.start_to, now)
    except ValueError as exc:
        ap.error(f"--start-from / --start-to: {exc}")
    assert span is not None  # both ends are required
    lo, hi = span

    run = Path(args.runs_dir) / args.date
    path = coupon_artifact(run)
    if path.name != COUPON_ARTIFACT or not path.exists():
        print(f"FAILED: no {COUPON_ARTIFACT} in {run}", file=sys.stderr)
        return 2
    coupon = json.loads(path.read_text(encoding="utf-8"))
    events = wr.window_events(coupon, lo, hi, now, args.top)
    label = (f"{lo.astimezone(LOCAL):%H:%M}-{hi.astimezone(LOCAL):%H:%M} "
             "Europe/Warsaw")
    print(f"window {label}: {len(events)} match(es) (top {args.top})")
    for g, v, leg in events:
        print(f"  {leg['kickoff_utc'][11:16]}Z x{v:.2f} {g} {leg.get('match', '')}")
    if not events:
        return 1
    req_path = run / "read_requests.json"
    existing = load_read_requests(req_path)
    new = wr.window_requests(events, existing, now, label)
    if args.dry_run:
        print(f"dry run: {len(new)} new request(s) not written")
        return 0
    if new:
        req_path.write_text(json.dumps(existing + new, indent=2, ensure_ascii=False)
                            + "\n", encoding="utf-8")
        load_read_requests(req_path)  # the build refuses a file it cannot read
    print(f"{len(new)} new request(s), {len(existing) + len(new)} in {req_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
