#!/usr/bin/env python3
"""Bring the Sofascore bridge up if it is down, then grade it - step 0 of /sofa-day.

    .venv/bin/python scripts/sofa/ensure_bridge.py [--windows 5]

Idempotent, and it never touches a bridge that already works:

1. the server (bridge_server.py) not listening -> start it detached
   (start_new_session, so it outlives the terminal and the agent), logging to
   runs/sofa/bridge_server.log, and wait until /health answers;
2. no tab polling (never, or the last poll older than STALE_POLL_S):
   - Chrome not running -> launch_bridge_browser.py --windows N (the
     anti-throttling flags only apply to a Chrome started cold);
   - Chrome running WITH those flags -> the bridge windows exist; wait up to
     WAIT_FOR_POLL_S for a tab to poll;
   - Chrome running WITHOUT them -> STOP. A second launch would only message
     the running Chrome and drop every flag, so the tabs would run clamped
     at ~1 req/s and nothing would say so. Quitting the operator's browser
     is the operator's decision, never this script's;
3. check_bridge.py, whose verdict is the step's verdict.

It does not change MIN_INTERVAL_MS, SOFA_TARGET_RPS or SOFA_MAX_CONCURRENCY,
and --windows should equal SOFA_MAX_CONCURRENCY (CLAUDE.md).

Exit: 0 bridge OK, 1 up but degraded (check_bridge's WARN/FAIL), 2 could not
bring it up (the message says what the operator must do).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
HEALTH_URL = "http://127.0.0.1:8787/health"
STALE_POLL_S = 30.0  # check_bridge's own WARN threshold
WAIT_FOR_SERVER_S = 15.0
WAIT_FOR_POLL_S = 90.0
FLAG = "--disable-background-timer-throttling"

Action = Literal[
    "START_SERVER", "LAUNCH_BROWSER", "WAIT_FOR_POLL", "STOP_FOREIGN_CHROME", "OK"
]


@dataclass(frozen=True)
class State:
    server_up: bool
    pull_age_s: float | None
    chrome_running: bool
    chrome_has_flags: bool


def decide(state: State) -> list[Action]:
    """What to do, in order, for this state. Pure - the tests hold it."""
    actions: list[Action] = []
    if not state.server_up:
        actions.append("START_SERVER")
    polling = state.pull_age_s is not None and state.pull_age_s <= STALE_POLL_S
    if state.server_up and polling:
        return ["OK"]
    if not state.chrome_running:
        actions.append("LAUNCH_BROWSER")
    elif state.chrome_has_flags:
        actions.append("WAIT_FOR_POLL")
    else:
        actions.append("STOP_FOREIGN_CHROME")
    return actions


def health() -> dict[str, object] | None:
    try:
        with urlopen(HEALTH_URL, timeout=3) as r:
            data: dict[str, object] = json.loads(r.read().decode("utf-8"))
            return data
    except (URLError, OSError, ValueError):
        return None


def pull_age(h: dict[str, object] | None) -> float | None:
    if h is None:
        return None
    age = h.get("last_pull_age_s")
    return float(age) if isinstance(age, (int, float)) else None


def chrome_processes() -> list[str]:
    out = subprocess.run(
        ["ps", "-axo", "command="], capture_output=True, text=True, timeout=10
    ).stdout
    return [
        line
        for line in out.splitlines()
        if "Google Chrome.app/Contents/MacOS/Google Chrome" in line
    ]


def observe() -> State:
    h = health()
    procs = chrome_processes()
    return State(
        server_up=h is not None,
        pull_age_s=pull_age(h),
        chrome_running=bool(procs),
        chrome_has_flags=any(FLAG in p for p in procs),
    )


def start_server() -> bool:
    log = REPO / os.environ.get("SOFA_RUNS_DIR", "runs/sofa") / "bridge_server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as fh:
        subprocess.Popen(
            [PYTHON, str(REPO / "scripts/sofa/bridge_server.py")],
            cwd=REPO,
            stdout=fh,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.monotonic() + WAIT_FOR_SERVER_S
    while time.monotonic() < deadline:
        if health() is not None:
            print(f"OK    bridge server started (log {log})")
            return True
        time.sleep(0.5)
    print(
        f"FAIL  bridge server did not answer within {WAIT_FOR_SERVER_S:.0f} s "
        f"- see {log}"
    )
    return False


def wait_for_poll() -> bool:
    deadline = time.monotonic() + WAIT_FOR_POLL_S
    while time.monotonic() < deadline:
        age = pull_age(health())
        if age is not None and age <= STALE_POLL_S:
            print(f"OK    a tab is polling (last poll {age:.0f} s ago)")
            return True
        time.sleep(2)
    print(
        f"FAIL  no tab polled within {WAIT_FOR_POLL_S:.0f} s. Reload https://www.sofascore.com/"
        " in the bridge windows (a 403 there means the tab's x-captcha expired)."
    )
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--windows", type=int, default=int(os.environ.get("SOFA_MAX_CONCURRENCY", "5"))
    )
    args = parser.parse_args()
    # Our lines and check_bridge's must come out in the order they happen.
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    for action in decide(observe()):
        if action == "OK":
            print("OK    bridge already up and polling - nothing started")
        elif action == "START_SERVER":
            if not start_server():
                return 2
        elif action == "LAUNCH_BROWSER":
            rc = subprocess.call(
                [
                    PYTHON,
                    str(REPO / "scripts/sofa/launch_bridge_browser.py"),
                    "--windows",
                    str(args.windows),
                ],
                cwd=REPO,
            )
            if rc != 0 or not wait_for_poll():
                return 2
        elif action == "WAIT_FOR_POLL":
            if not wait_for_poll():
                return 2
        elif action == "STOP_FOREIGN_CHROME":
            print("STOP  Chrome is running without the bridge's anti-throttling flags.")
            print(
                "      Launching now would drop them silently "
                "(tabs clamped to ~1 req/s)."
            )
            print("      Quit Chrome completely (Cmd+Q), then re-run this step.")
            return 2
    rc = subprocess.call([PYTHON, str(REPO / "scripts/sofa/check_bridge.py")], cwd=REPO)
    return 0 if rc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
