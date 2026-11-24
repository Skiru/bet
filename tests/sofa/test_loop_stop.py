"""A daily loop stopped from outside says so in its log (2026-11-24).

The loops were ended with SIGTERM at 12:27Z and their logs simply stopped;
the next session read it as a silent death."""

from __future__ import annotations

import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from bet.sofa.loop_stop import stopped_line

REPO = Path(__file__).resolve().parents[2]

CHILD = """
import sys, time
sys.path.insert(0, {src!r})
from bet.sofa.loop_stop import log_stop_signals
log_stop_signals("shadow_daily 2026-11-24")
print("ready", flush=True)
try:
    time.sleep(30)
finally:
    print("cleanup ran", flush=True)
"""


def test_the_stopped_line_names_the_loop_and_the_signal() -> None:
    at = datetime(2026, 11, 24, 12, 27, 29, tzinfo=UTC)
    line = stopped_line("cs2_daily 2026-11-24", signal.SIGTERM, at)
    assert line.startswith("[2026-11-24T12:27:29+00:00] STOPPED cs2_daily 2026-11-24")
    assert "SIGTERM" in line and "not a crash" in line


def test_sigterm_writes_the_line_runs_cleanup_and_exits_143() -> None:
    proc = subprocess.Popen(
        [sys.executable, "-c", CHILD.format(src=str(REPO / "src"))],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stdout.readline().strip() == "ready"
    time.sleep(0.1)
    proc.send_signal(signal.SIGTERM)
    out, _ = proc.communicate(timeout=10)
    assert proc.returncode == 128 + signal.SIGTERM
    assert "STOPPED shadow_daily 2026-11-24: SIGTERM" in out
    # finally blocks (the loops' pid-file cleanup) still run
    assert "cleanup ran" in out


def test_sighup_is_left_to_nohup() -> None:
    import bet.sofa.loop_stop as ls

    assert signal.SIGHUP not in ls.HANDLED
