#!/usr/bin/env python3
"""One CS2 day, unattended: snapshots through the day, then settle, backfill,
audit the next morning.

    PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_daily.py \\
        --date 2026-09-29 > runs/sofa/cs2/daily_2026-09-29.log 2>&1 &

1. CS2 every --interval-min (default 30) until --snapshots-until (default
   23:30Z on the day). Superbet only.
   With --chain, the NEXT day's loop (itself with --chain) is started
   detached right when this day's snapshots end, so D+1's night series are
   snapshotted from 23:30Z on; a loop already running for that date makes
   the new one refuse (exit 2).
2. Sleep until --settle-at (default 05:00Z the next day), then CS2_SETTLE for
   the day and once more for the day before (series held STATS_PENDING, and
   the day before's night series that settle into this day's file) - it
   needs the bridge; a failed settle is logged and can be rerun by hand at
   any time (`run_pipeline.py --date <d> --only CS2_SETTLE`).
2b. settle_sport_coupon.py for the experimental CS2 coupons of both days,
   and record_results.py for both days (the ledger; offline).
3. A short CS2_BACKFILL (--backfill-minutes, default 6; 0 to skip). It honours
   the cooldown a Sofascore refusal leaves behind, so it never re-hammers.
3b. A step that FAILED (exit >= 2) is retried every 30 min for up to 4 h,
   together with the settle_sport_coupon / record_results steps after the
   first failed one (run_morning); a backfill is never repeated.
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
# The morning sweep reaches back this far: settle_cs2's GIVE_UP_AFTER is 7
# days, so a waiting series is asked until it settles or is given up on.
SWEEP_DAYS = 7


def state_dir() -> Path:
    import os

    return REPO / os.environ.get("SOFA_RUNS_DIR", "runs/sofa") / "cs2"


def pid_file(date: str) -> Path:
    """Where a running day says it is alive; cs2_watchdog.py reads it."""
    return state_dir() / f"daily_{date}.pid"


def done_file(date: str) -> Path:
    """Written when the day's last step has run; the watchdog then only
    retries CS2_SETTLE, never the whole day again."""
    return state_dir() / f"daily_{date}.done"


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
    try:
        code = subprocess.call(env_cmd, cwd=REPO)
    except (OSError, subprocess.SubprocessError) as exc:
        # The step never started (fork / exec failed): FAILED, and the loop
        # goes on - it used to raise out of the loop and end the day.
        print(f"STEP_NOT_STARTED {' '.join(args)}: {exc}", flush=True)
        return 2
    return exit_code(code, args)


def exit_code(code: int, args: list[str]) -> int:
    """A step's exit as the loop reads it. A step killed by a signal returns
    a negative code, which `max(worst, code)` read as better than OK - an
    OOM-killed settle was a silent success, never retried (F6.1)."""
    if code < 0:
        print(f"STEP_KILLED by signal {-code}: {' '.join(args)}", flush=True)
        return 2
    return code


def _guarded(runner: Callable[[list[str]], int], cmd: list[str]) -> int:
    """One step through `runner`; an exception is that step FAILED (logged),
    never the end of an unattended loop."""
    try:
        return exit_code(runner(cmd), cmd)
    except Exception as exc:  # noqa: BLE001 - an unattended loop survives
        print(f"STEP_FAILED {' '.join(cmd)}: {type(exc).__name__}: {exc}",
              flush=True)
        return 2


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
    script: str = "cs2_daily.py",
) -> int | None:
    """The pid of a live `script` loop for this day, if one is running.

    Two loops for one day double every Superbet snapshot and run two settles
    over the same settled.json the next morning - the last writer wins. A
    live pid is only this loop when its command line says so: after a crash
    or a reboot the number can belong to anything, and a stale file must not
    block (or end a chain). Shared with shadow_daily.py.
    """
    import os

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
    if script not in command or (date and date not in command):
        return None
    return pid


def plan(
    date: str,
    interval_min: int,
    until: datetime,
    settle_at: datetime,
    backfill_minutes: float,
) -> tuple[list[str], list[list[str]], list[str]]:
    """(snapshot step, morning steps, audit step) - separated for tests."""
    snapshot = ["scripts/sofa/run_pipeline.py", "--date", date, "--only", "CS2"]
    before = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime(
        "%Y-%m-%d"
    )
    sweep_from, sweep_to = (
        (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")
        for n in (SWEEP_DAYS, 2)
    )
    morning = [
        ["scripts/sofa/run_pipeline.py", "--date", date, "--only", "CS2_SETTLE"],
        # the day before again: STATS_PENDING series (72 h grace) and the
        # night series its coupon printed from this day's file
        ["scripts/sofa/run_pipeline.py", "--date", before, "--only", "CS2_SETTLE"],
        # D-7..D-2: only the dates whose settled.json still has a waiting
        # series (decided at run time, from the files). Without it a series
        # still waiting on D-2 was never asked again, and never reached
        # GIVE_UP_AFTER either (audit 2026-10-01).
        ["scripts/sofa/settle_cs2.py", "--sweep-from", sweep_from,
         "--sweep-to", sweep_to],
        # the experimental coupons of every day those settles may have
        # changed, then the ledger for the same days (both offline)
        ["scripts/sofa/settle_sport_coupon.py", "--from", sweep_from, "--to", date,
         "--sport", "cs2"],
        ["scripts/sofa/record_results.py", "--from", sweep_from, "--to", date],
    ]
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
    after_snapshots: Callable[[], None] | None = None,
) -> int:
    snapshot, morning, audit = plan(
        date, interval_min, until, settle_at, backfill_minutes
    )
    return loop(
        snapshot,
        morning,
        audit,
        interval_min,
        until,
        settle_at,
        clock=clock,
        sleep=sleep,
        runner=runner,
        after_snapshots=after_snapshots,
    )


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
            [PYTHON, "scripts/sofa/cs2_daily.py", "--date", nxt, "--chain"],
            cwd=REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return proc.pid


def loop(
    snapshot: list[str],
    morning: list[list[str]],
    audit: list[str],
    interval_min: int,
    until: datetime,
    settle_at: datetime,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    runner: Callable[[list[str]], int] = step,
    after_snapshots: Callable[[], None] | None = None,
) -> int:
    """Snapshot every interval until `until`, then the morning steps, then
    the audit. Shared with shadow_daily.py. `after_snapshots` runs once, when
    the snapshots end (cs2_daily's --chain)."""
    worst = 0
    while clock() < until:
        worst = max(worst, _guarded(runner, snapshot))
        remaining = (until - clock()).total_seconds()
        if remaining <= 0:
            break
        sleep(min(interval_min * 60, remaining))
    if after_snapshots is not None:
        try:
            after_snapshots()
        except Exception as exc:  # the day goes on; a failed chain is logged
            print(f"after-snapshots step failed: {exc}", flush=True)
    wait = (settle_at - clock()).total_seconds()
    if wait > 0:
        sleep(wait)
    worst = max(
        worst, run_morning(morning, clock=clock, sleep=sleep, runner=runner)
    )
    _guarded(runner, audit)  # a report; its exit code says nothing about the day
    return min(worst, 2)


# A FAILED morning step is asked again every RETRY_EVERY_S for RETRY_FOR_S.
# On 2026-10-02 05:00Z CS2_SETTLE met 5 x 403 and FAILED for 10-01 and 09-30;
# a retry half an hour later would have settled both, and the loop had
# already ended its morning.
RETRY_EVERY_S = 30 * 60
RETRY_FOR_S = 4 * 3600
# Offline steps that read what a settle wrote: re-run after a retry when they
# come after the first failed step, whatever their own exit was.
RERUN_AFTER_RETRY = ("settle_sport_coupon.py", "record_results.py")
# A backfill is capped by time and resumes the next morning; never repeated.
NEVER_RETRY_PREFIX = "backfill_"


def run_morning(
    morning: list[list[str]],
    *,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
    runner: Callable[[list[str]], int],
    retry_every_s: float = RETRY_EVERY_S,
    retry_for_s: float = RETRY_FOR_S,
) -> int:
    """The morning steps once, then their retries; the worst final exit."""
    codes = [_guarded(runner, cmd) for cmd in morning]

    def name(i: int) -> str:
        return Path(morning[i][0]).name

    def retryable(i: int) -> bool:
        return codes[i] >= 2 and not name(i).startswith(NEVER_RETRY_PREFIX)

    # Fixed slots after the first pass, so slow steps do not thin the retries.
    start = clock()
    for k in range(1, int(retry_for_s // retry_every_s) + 1):
        if not any(retryable(i) for i in range(len(morning))):
            break
        wait = (start + timedelta(seconds=k * retry_every_s) - clock()).total_seconds()
        if wait > 0:
            sleep(wait)
        failed = [i for i in range(len(morning)) if retryable(i)]
        first = failed[0]
        print(
            f"[{clock().isoformat(timespec='seconds')}] RETRY {k} failed morning "
            f"steps: {[' '.join(morning[i]) for i in failed]}",
            flush=True,
        )
        for i in range(len(morning)):
            if retryable(i) or (i > first and name(i) in RERUN_AFTER_RETRY):
                codes[i] = _guarded(runner, morning[i])
    return max(codes, default=0)


def main(spawn: Callable[[str], int] = spawn_next_day) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--date", required=True)
    ap.add_argument("--interval-min", type=int, default=30)
    ap.add_argument("--snapshots-until", default="23:30", help="HH:MM UTC on --date")
    ap.add_argument("--settle-at", default="05:00", help="HH:MM UTC the next day")
    ap.add_argument("--backfill-minutes", type=float, default=6.0)
    ap.add_argument(
        "--chain",
        action="store_true",
        help="when the snapshots end, start the next day's loop (with --chain)",
    )
    args = ap.parse_args()
    import json
    import os

    until = _at(args.date, args.snapshots_until)
    settle_at = _at(args.date, args.settle_at, day_offset=1)
    pid_file(args.date).parent.mkdir(parents=True, exist_ok=True)
    running = already_running(pid_file(args.date), args.date)
    if running is not None:
        print(
            f"cs2_daily for {args.date} is already running (pid {running}); "
            "not starting a second loop",
            flush=True,
        )
        return 2
    pid_file(args.date).write_text(str(os.getpid()), encoding="utf-8")
    def chain() -> None:
        pid = spawn(args.date)
        print(
            f"chained {next_day(args.date)}: started pid {pid} (it exits 2 at once "
            f"if a loop for that date is already running - see "
            f"daily_{next_day(args.date)}.log)",
            flush=True,
        )

    try:
        code = run(
            args.date,
            args.interval_min,
            until,
            settle_at,
            args.backfill_minutes,
            after_snapshots=chain if args.chain else None,
        )
    finally:
        # Gone when the loop is (as shadow_daily): a live pid file means a
        # live loop. A loop that raised writes no .done, so the watchdog
        # relaunches it.
        pid_file(args.date).unlink(missing_ok=True)
    done_file(args.date).write_text(
        json.dumps({"exit": code, "at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
