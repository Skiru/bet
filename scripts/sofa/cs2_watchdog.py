#!/usr/bin/env python3
"""Keep the CS2 days running while nobody watches.

    PYTHONPATH=src:. nohup .venv/bin/python scripts/sofa/cs2_watchdog.py \\
        --dates 2026-09-28,2026-09-29 --until 2026-10-01T06:00Z \\
        > runs/sofa/cs2/watchdog.log 2>&1 &

Every --interval-s (default 300) it looks at three things and acts:

- the bridge server (GET /health). Not listening -> it is restarted
  (RESTART_BRIDGE). Listening but no browser pull for BRIDGE_STALE_S ->
  ALERT, and nothing else: reopening the windows means quitting Chrome, which
  is the operator's to do (launch_bridge_browser.py).
- each date's cs2_daily.py. Its pid gone before it wrote its .done marker ->
  it is relaunched (RELAUNCH); a relaunch is safe - snapshots append, settle
  skips what it already graded, the backfill resumes and honours its cooldown.
- each finished date whose settled.json still has retryable series (or does
  not exist): CS2_SETTLE again, at most every SETTLE_RETRY, while the bridge
  is healthy and until SETTLE_WINDOW after the day (RESETTLE).

Every action and alert is one line starting "WATCHDOG", so a monitor can
follow the log. A heartbeat line is written every hour.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "src"))

from bet.sofa.shadow import RETRYABLE  # noqa: E402  (one set, plan B0)
from scripts.sofa.cs2_daily import done_file, pid_file, state_dir  # noqa: E402

BRIDGE_URL = "http://127.0.0.1:8787/health"
BRIDGE_STALE_S = 180.0
SETTLE_RETRY = timedelta(hours=1)
SETTLE_WINDOW = timedelta(days=3)
ALERT_EVERY = timedelta(minutes=30)


@dataclass(frozen=True)
class Seen:
    """What one look found."""

    bridge_up: bool
    pull_age_s: float | None
    alive: dict[str, bool]  # date -> its cs2_daily still running
    done: dict[str, bool]  # date -> its .done marker exists
    retryable: dict[str, int | None]  # date -> retryable series (None: no file)


def decide(
    seen: Seen,
    now: datetime,
    last_settle: dict[str, datetime],
    last_alert: datetime | None,
) -> list[tuple[str, str]]:
    """The actions for one look, as (action, date-or-'') pairs."""
    actions: list[tuple[str, str]] = []
    healthy = seen.bridge_up and (seen.pull_age_s or 0.0) <= BRIDGE_STALE_S
    if not seen.bridge_up:
        actions.append(("RESTART_BRIDGE", ""))
    elif not healthy and (last_alert is None or now - last_alert >= ALERT_EVERY):
        actions.append(("ALERT_TABS", ""))
    for date in sorted(seen.alive):
        if not seen.done[date] and not seen.alive[date]:
            actions.append(("RELAUNCH", date))
            continue
        if not seen.done[date] or not healthy:
            continue
        day_end = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        if now > day_end + timedelta(days=1) + SETTLE_WINDOW:
            continue
        pending = seen.retryable[date]
        if pending is None or pending > 0:
            last = last_settle.get(date)
            if last is None or now - last >= SETTLE_RETRY:
                actions.append(("RESETTLE", date))
    return actions


# --- looking -----------------------------------------------------------------------


def bridge_health() -> tuple[bool, float | None]:
    try:
        with urllib.request.urlopen(BRIDGE_URL, timeout=5) as resp:
            body = json.loads(resp.read().decode())
        age = body.get("last_pull_age_s")
        return bool(body.get("ok")), float(age) if age is not None else None
    except Exception:
        return False, None


def pid_alive(date: str) -> bool:
    try:
        pid = int(pid_file(date).read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def retryable_series(date: str) -> int | None:
    path = state_dir() / date / "settled.json"
    if not path.exists():
        return None
    try:
        events = json.loads(path.read_text(encoding="utf-8")).get("events", {})
    except (OSError, json.JSONDecodeError):
        return None
    return sum(1 for rec in events.values() if rec.get("state") in RETRYABLE)


def look(dates: list[str]) -> Seen:
    up, age = bridge_health()
    return Seen(
        bridge_up=up,
        pull_age_s=age,
        alive={d: pid_alive(d) for d in dates},
        done={d: done_file(d).exists() for d in dates},
        retryable={d: retryable_series(d) for d in dates},
    )


# --- acting -----------------------------------------------------------------------


def log(msg: str) -> None:
    print(
        f"WATCHDOG {datetime.now(UTC).isoformat(timespec='seconds')} {msg}", flush=True
    )


def spawn(args: list[str], logfile: Path) -> None:
    """Start a detached child whose output goes to its own log."""
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with logfile.open("a", encoding="utf-8") as out:
        subprocess.Popen(
            [sys.executable, *args],
            cwd=REPO,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONPATH": "src:."},
        )


def act(action: str, date: str) -> None:
    if action == "RESTART_BRIDGE":
        spawn(["scripts/sofa/bridge_server.py"], REPO / "runs/sofa/bridge_server.log")
        log("RESTART_BRIDGE the bridge server was not listening; restarted it")
    elif action == "ALERT_TABS":
        log(
            "ALERT_TABS bridge up but no browser pull - reopen the windows with "
            "launch_bridge_browser.py (needs Chrome quit first)"
        )
    elif action == "RELAUNCH":
        spawn(
            # --chain kept: a relaunched day that dropped it ended the chain
            # (D+1 refuses at once if its loop is already running).
            ["scripts/sofa/cs2_daily.py", "--date", date, "--chain"],
            state_dir() / f"daily_{date}.log",
        )
        log(f"RELAUNCH {date} cs2_daily was not running and had not finished")
    elif action == "RESETTLE":
        code = subprocess.call(
            [
                sys.executable,
                "scripts/sofa/run_pipeline.py",
                "--date",
                date,
                "--only",
                "CS2_SETTLE",
            ],
            cwd=REPO,
            env={**os.environ, "PYTHONPATH": "src:."},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        left = retryable_series(date)
        log(f"RESETTLE {date} exit {code}; retryable series left: {left}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dates", required=True, help="comma-separated YYYY-MM-DD")
    ap.add_argument("--until", required=True, help="stop watching at this UTC time")
    ap.add_argument("--interval-s", type=float, default=300.0)
    args = ap.parse_args()
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
    last_settle: dict[str, datetime] = {}
    last_alert: datetime | None = None
    last_beat = datetime.min.replace(tzinfo=UTC)
    log(f"START watching {dates} until {until.isoformat()}")
    while datetime.now(UTC) < until:
        now = datetime.now(UTC)
        seen = look(dates)
        for action, date in decide(seen, now, last_settle, last_alert):
            try:
                act(action, date)
            except Exception as exc:  # the watchdog itself must not die
                log(f"ERROR {action} {date}: {type(exc).__name__}: {exc}")
            if action == "RESETTLE":
                last_settle[date] = now
            if action == "ALERT_TABS":
                last_alert = now
        if now - last_beat >= timedelta(hours=1):
            state: dict[str, Any] = {
                d: ("done" if seen.done[d] else "running" if seen.alive[d] else "down")
                for d in dates
            }
            log(
                f"HEARTBEAT bridge_up={seen.bridge_up} pull_age_s={seen.pull_age_s} "
                f"days={state} retryable={seen.retryable}"
            )
            last_beat = now
        time.sleep(args.interval_s)
    log("STOP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
