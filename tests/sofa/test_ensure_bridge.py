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


def test_fresh_windows_are_graded_again_until_the_token_is_minted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """2026-10-01: 403 'challenge' right after the launch, 200 a minute later."""
    import scripts.sofa.ensure_bridge as eb

    answers = iter([1, 1, 0])
    calls: list[int] = []
    monkeypatch.setattr(eb, "run_check_bridge", lambda: calls.append(1) or next(answers))
    monkeypatch.setattr(eb.time, "sleep", lambda s: None)
    assert eb.graded_check(eb.FRESH_LAUNCH_CHECKS) == 0
    assert len(calls) == 3


def test_a_bridge_that_was_already_up_is_graded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.sofa.ensure_bridge as eb

    calls: list[int] = []
    monkeypatch.setattr(eb, "run_check_bridge", lambda: calls.append(1) or 1)
    monkeypatch.setattr(eb.time, "sleep", lambda s: None)
    assert eb.graded_check(1) == 1
    assert len(calls) == 1


def test_a_failure_that_outlasts_the_retries_is_still_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.sofa.ensure_bridge as eb

    calls: list[int] = []
    monkeypatch.setattr(eb, "run_check_bridge", lambda: calls.append(1) or 1)
    monkeypatch.setattr(eb.time, "sleep", lambda s: None)
    assert eb.graded_check(eb.FRESH_LAUNCH_CHECKS) == 1
    assert len(calls) == eb.FRESH_LAUNCH_CHECKS
