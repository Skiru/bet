#!/usr/bin/env python3
"""One shadow day (hockey, basketball, volleyball), unattended: snapshots
through the day, then settle and audit the next morning.

    PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/shadow_daily.py \\
        --date 2026-09-29 --chain >> runs/sofa/shadow/daily_2026-09-29.log 2>&1 &

1. SHADOW every --interval-min (default 30) until --snapshots-until (default
   04:30Z the NEXT day). Superbet only. Each snapshot also records the next
   day's games that start within its horizon, so the late North American
   games after 00:00Z are priced before the next day's loop is running.
2. Sleep until --settle-at (default 05:15Z the next day - after CS2_SETTLE
   starts at 05:00Z; that the two do not overlap is expected, not measured),
   then SHADOW_SETTLE for the day, and once more for the day before when it
   has snapshots (its pending games get a second attempt). A failed settle
   is logged and can be rerun by hand at any time
   (`run_pipeline.py --date <d> --only SHADOW_SETTLE`); it resumes.
3. settle_sport_coupon.py for each settled day and sport (the experimental
   coupons, offline), record_results.py for those days (the ledger), then
   audit_shadow.py for the day, into the log.
4. With --chain, start the NEXT day's loop (itself with --chain), detached,
   into runs/sofa/shadow/daily_<D+1>.log. This loop covers D+1's games only
   up to ~07:30Z (its 04:30Z snapshot plus the 3 h horizon); without a D+1
   loop running by then, D+1's morning games are never priced. A D+1 loop
   already running (started by hand or by /sofa-day) is left alone - the
   new one refuses to start (exit 2). Stop the chain by killing the pid in
   daily_<date>.pid.

Every step is its own process (cs2_daily.step), so one crashing never takes
the rest down. Nothing here feeds the coupon. Exit: the worst step's code.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from scripts.sofa.cs2_daily import (  # noqa: E402
    PYTHON,
    REPO,
    _at,
    _command_of,
    loop,
)
from scripts.sofa.cs2_daily import already_running as _already_running  # noqa: E402


def state_dir() -> Path:
    return REPO / os.environ.get("SOFA_RUNS_DIR", "runs/sofa") / "shadow"


def plan(
    date: str, retry_before: bool = True
) -> tuple[list[str], list[list[str]], list[str]]:
    """(snapshot step, morning steps, audit step) - separated for tests."""
    snapshot = ["scripts/sofa/run_pipeline.py", "--date", date, "--only", "SHADOW"]
    days = [date]
    if retry_before:
        # The day before once more: a game still pending or not yet listed on
        # Sofascore gets a second, unattended attempt.
        days.append(
            (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
        )
    morning = [
        ["scripts/sofa/run_pipeline.py", "--date", d, "--only", "SHADOW_SETTLE"]
        for d in days
    ]
    # Each settled day's experimental coupons, straight after the settle that
    # grades them (offline; a pending leg is exit 1, never a blocker).
    morning += [
        ["scripts/sofa/settle_sport_coupon.py", "--from", d, "--to", d, "--sport", sp]
        for d in days
        for sp in ("hockey", "basketball", "volleyball")
    ]
    # Then the ledger for every settled day (the 05:15Z step is the last
    # morning settle - CS2's runs at 05:00Z): a day's rows are rewritten
    # whole, so re-recording the day before closes its late legs.
    morning.append(
        ["scripts/sofa/record_results.py", "--from", min(days), "--to", max(days)]
    )
    audit = ["scripts/sofa/audit_shadow.py", "--from", date, "--to", date]
    return snapshot, morning, audit


def has_snapshots(date: str) -> bool:
    """Any sport of the day was snapshotted (settling it is not a no-op)."""
    return any(state_dir().glob(f"*/{date}/snapshots.jsonl"))


def already_running(
    pid_file: Path,
    date: str | None = None,
    command_of: Callable[[int], str] = _command_of,
) -> int | None:
    """The pid of a live shadow loop for this day (cs2_daily.already_running)."""
    return _already_running(pid_file, date, command_of, "shadow_daily.py")


def next_day(date: str) -> str:
    return (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )


def spawn_next_day(date: str) -> int:
    """Start D+1's loop detached (own session, own log); its pid."""
    nxt = next_day(date)
    log = state_dir() / f"daily_{nxt}.log"
    with log.open("a", encoding="utf-8") as fh:
        proc = subprocess.Popen(
            [PYTHON, "scripts/sofa/shadow_daily.py", "--date", nxt, "--chain"],
            cwd=REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return proc.pid


def main(spawn: Callable[[str], int] = spawn_next_day) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--date", required=True)
    ap.add_argument("--interval-min", type=int, default=30)
    ap.add_argument(
        "--snapshots-until",
        default="04:30",
        help="HH:MM UTC the day AFTER --date (each snapshot also takes the "
        "next day's games within its horizon)",
    )
    ap.add_argument("--settle-at", default="05:15", help="HH:MM UTC the next day")
    ap.add_argument(
        "--chain",
        action="store_true",
        help="when done, start the next day's loop (with --chain) detached",
    )
    args = ap.parse_args()
    before = (datetime.strptime(args.date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    snapshot, morning, audit = plan(args.date, retry_before=has_snapshots(before))
    state_dir().mkdir(parents=True, exist_ok=True)
    pid_file = state_dir() / f"daily_{args.date}.pid"
    running = already_running(pid_file, args.date)
    if running is not None:
        print(
            f"shadow_daily for {args.date} is already running (pid {running}); "
            "not starting a second loop",
            flush=True,
        )
        return 2
    pid_file.write_text(str(os.getpid()), encoding="utf-8")
    try:
        code = loop(
            snapshot,
            morning,
            audit,
            args.interval_min,
            _at(args.date, args.snapshots_until, day_offset=1),
            _at(args.date, args.settle_at, day_offset=1),
        )
    finally:
        # Gone when the loop is: a live pid file means a live loop.
        pid_file.unlink(missing_ok=True)
    (state_dir() / f"daily_{args.date}.done").write_text(
        json.dumps({"exit": code, "at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    if args.chain:
        try:
            pid = spawn(args.date)
            print(
                f"chained {next_day(args.date)}: started pid {pid} (it exits 2 at "
                f"once if a loop for that date is already running - see "
                f"daily_{next_day(args.date)}.log)",
                flush=True,
            )
        except Exception as exc:  # the day is done; a failed chain is logged
            print(f"chain to {next_day(args.date)} failed: {exc}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
