#!/usr/bin/env python3
"""One CS2 day, unattended: snapshots through the day, then settle, backfill,
audit the next morning.

    PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py \\
        --date 2026-09-29 > runs/sofa/cs2/daily_2026-09-29.log 2>&1 &

1. CS2 every --interval-min (default 30) until --snapshots-until (default
   23:30Z on the day). Superbet only.
2. Sleep until --settle-at (default 05:00Z the next day), then CS2_SETTLE for
   the day - it needs the bridge; a failed settle is logged and can be rerun
   by hand at any time (`run_pipeline.py --date <d> --only CS2_SETTLE`).
3. A short CS2_BACKFILL (--backfill-minutes, default 6; 0 to skip). It honours
   the cooldown a Sofascore refusal leaves behind, so it never re-hammers.
4. audit_cs2.py for the day, into the log.

Every step is a separate process, so one crashing never takes the rest down,
and each step's own SOFA_SUMMARY line lands in the log. Nothing here feeds
the coupon. Exit: the worst step's code (0 OK, 1 PARTIAL, 2 FAILED).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable


def _at(date: str, hhmm: str, day_offset: int = 0) -> datetime:
    base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
    hh, mm = (int(x) for x in hhmm.split(":"))
    return base + timedelta(days=day_offset, hours=hh, minutes=mm)


def step(args: list[str]) -> int:
    """Run one step in its own process; its output goes straight to our log."""
    print(
        f"[{datetime.now(UTC).isoformat(timespec='seconds')}] $ {' '.join(args)}",
        flush=True,
    )
    env_cmd = [PYTHON, *args]
    return subprocess.call(env_cmd, cwd=REPO)


def plan(
    date: str,
    interval_min: int,
    until: datetime,
    settle_at: datetime,
    backfill_minutes: float,
) -> tuple[list[str], list[list[str]], list[str]]:
    """(snapshot step, morning steps, audit step) - separated for tests."""
    snapshot = ["scripts/sofa/run_pipeline.py", "--date", date, "--only", "CS2"]
    morning = [["scripts/sofa/run_pipeline.py", "--date", date, "--only", "CS2_SETTLE"]]
    if backfill_minutes > 0:
        morning.append(
            ["scripts/sofa/backfill_cs2.py", "--max-minutes", str(backfill_minutes)]
        )
    audit = ["scripts/sofa/audit_cs2.py", "--from", date, "--to", date, "--history"]
    return snapshot, morning, audit


def run(
    date: str,
    interval_min: int,
    until: datetime,
    settle_at: datetime,
    backfill_minutes: float,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    runner: Callable[[list[str]], int] = step,
) -> int:
    snapshot, morning, audit = plan(
        date, interval_min, until, settle_at, backfill_minutes
    )
    worst = 0
    while clock() < until:
        worst = max(worst, runner(snapshot))
        remaining = (until - clock()).total_seconds()
        if remaining <= 0:
            break
        sleep(min(interval_min * 60, remaining))
    wait = (settle_at - clock()).total_seconds()
    if wait > 0:
        sleep(wait)
    for cmd in morning:
        worst = max(worst, runner(cmd))
    runner(audit)  # a report; its exit code says nothing about the day
    return min(worst, 2)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--date", required=True)
    ap.add_argument("--interval-min", type=int, default=30)
    ap.add_argument("--snapshots-until", default="23:30", help="HH:MM UTC on --date")
    ap.add_argument("--settle-at", default="05:00", help="HH:MM UTC the next day")
    ap.add_argument("--backfill-minutes", type=float, default=6.0)
    args = ap.parse_args()
    until = _at(args.date, args.snapshots_until)
    settle_at = _at(args.date, args.settle_at, day_offset=1)
    return run(args.date, args.interval_min, until, settle_at, args.backfill_minutes)


if __name__ == "__main__":
    sys.exit(main())
