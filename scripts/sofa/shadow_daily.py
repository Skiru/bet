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
3. audit_shadow.py for the day, into the log.
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

from scripts.sofa.cs2_daily import PYTHON, REPO, _at, loop  # noqa: E402


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
    audit = ["scripts/sofa/audit_shadow.py", "--from", date, "--to", date]
    return snapshot, morning, audit


def has_snapshots(date: str) -> bool:
    """Any sport of the day was snapshotted (settling it is not a no-op)."""
    return any(state_dir().glob(f"*/{date}/snapshots.jsonl"))


def _command_of(pid: int) -> str:
    try:
        return subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def already_running(
    pid_file: Path,
    date: str | None = None,
    command_of: Callable[[int], str] = _command_of,
) -> int | None:
    """The pid of a live loop for this day, if one is running.

    Two loops for one day double every Superbet snapshot and, at 05:15Z,
    run two SHADOW_SETTLE over the same settled.json - the last writer wins.
    A live pid is only this loop when its command line says so: after a
    crash or a reboot the number can belong to anything, and a stale file
    must not end the chain.
    """
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    if pid == os.getpid():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    command = command_of(pid)
    if "shadow_daily.py" not in command or (date and date not in command):
        return None
    return pid


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
