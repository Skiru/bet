"""A daily loop that is stopped says so in its own log.

2026-11-24: shadow_daily, cs2_daily, capture_closing and the paper capture
were ended with SIGTERM at 12:27Z (the operator asked a session to stop every
`bet` process) and their logs simply stopped - the next session read it as a
silent death. A loop now writes one stamped line when SIGTERM / SIGINT ends
it, then exits 128 + the signal as before. SIGHUP is left as it is: `nohup`
ignores it and the loops run in their own session (start_new_session), so a
closed terminal never reaches them. SIGKILL cannot be caught - a log that
stops with no STOPPED line was killed that way (or the machine went down).
"""

from __future__ import annotations

import os
import signal
import sys
from datetime import UTC, datetime
from types import FrameType

HANDLED = (signal.SIGTERM, signal.SIGINT)


def stopped_line(name: str, signum: int, at: datetime | None = None) -> str:
    when = (at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return (
        f"[{when}] STOPPED {name}: {signal.Signals(signum).name} "
        f"(pid {os.getpid()}) - ended from outside, not a crash"
    )


def log_stop_signals(name: str) -> None:
    """Install the handlers in a loop's main process (never in a step)."""

    def handler(signum: int, frame: FrameType | None) -> None:
        print(stopped_line(name, signum), flush=True)
        sys.stdout.flush()
        raise SystemExit(128 + signum)

    for sig in HANDLED:
        signal.signal(sig, handler)
