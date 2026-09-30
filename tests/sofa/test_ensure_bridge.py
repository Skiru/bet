"""Step 0 of /sofa-day: bring the bridge up, never touch one that works."""

from __future__ import annotations

import pytest

from scripts.sofa.ensure_bridge import STALE_POLL_S, State, decide


@pytest.mark.parametrize(
    "state, want",
    [
        (State(True, 3.0, True, True), ["OK"]),
        # a polling bridge is never touched - but a Chrome without the flags
        # is named: its tabs poll clamped
        (State(True, 3.0, True, False), ["WARN_UNFLAGGED"]),
        # the port is held by a server that does not answer: never a second one
        (State(False, None, False, False, port_busy=True), ["STOP_PORT_BUSY"]),
        (State(False, None, False, False), ["START_SERVER", "LAUNCH_BROWSER"]),
        (State(False, None, True, True), ["START_SERVER", "WAIT_FOR_POLL"]),
        (State(True, STALE_POLL_S + 1, True, True), ["WAIT_FOR_POLL"]),
        (State(True, None, False, False), ["LAUNCH_BROWSER"]),
        # a Chrome without the flags is the operator's: stop, never relaunch
        (State(True, None, True, False), ["STOP_FOREIGN_CHROME"]),
        (State(False, None, True, False), ["START_SERVER", "STOP_FOREIGN_CHROME"]),
    ],
)
def test_decide(state: State, want: list[str]) -> None:
    assert decide(state) == want
