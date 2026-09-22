"""The launcher must remove the timer clamp, and must open real windows.

The bridge's slow mode was never Sofascore. `pace()` waits on setTimeout to
hold MIN_INTERVAL_MS = 350, and Chrome clamps setTimeout in a hidden page to
>=1000 ms, so a background tab ran at ~1 req/s instead of 2.86. Measured over
80,964 live requests: fast p50 175 ms, slow p50 1,997 ms (p10 1,889 / p90
2,097) - a 200 ms-wide band around a round number is a clamped timer, not a
network.

These tests pin the two things that make the fix real: the flags that turn the
clamp off, and separate windows rather than tabs.
"""

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent.parent / "scripts" / "sofa"
SCRIPT = SCRIPTS / "launch_bridge_browser.py"


@pytest.fixture(scope="module")
def launcher():
    spec = importlib.util.spec_from_file_location("launch_bridge_browser", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_window_carries_all_three_anti_throttle_flags(launcher):
    """Chrome backgrounds a window for three different reasons - unfocused,
    occluded, and whole-renderer deprioritisation - and each one reaches the
    same timer clamp. Two of the three flags is still a throttled tab."""
    commands = launcher.build_command("/chrome", Path("/tmp/profile"), 5)
    assert len(commands) == 5
    for command in commands:
        for flag in (
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ):
            assert flag in command, f"{flag} missing from {command}"


def test_extra_windows_are_windows_and_not_tabs(launcher):
    """N tabs in one window is ONE working tab, because only the active tab of
    a window is visible. The capacity claim of 2.86 req/s per window is only
    true if these are separate windows."""
    commands = launcher.build_command("/chrome", Path("/tmp/profile"), 3)
    assert "--new-window" not in commands[0]
    assert all("--new-window" in command for command in commands[1:])


def test_a_single_window_asks_for_no_new_window(launcher):
    commands = launcher.build_command("/chrome", Path("/tmp/profile"), 1)
    assert len(commands) == 1
    assert "--new-window" not in commands[0]


def test_the_launched_profile_is_the_one_holding_tampermonkey(launcher, tmp_path):
    """The bridge is the userscript. Launching a profile without Tampermonkey
    gives a window that looks right and serves nothing, which reads exactly
    like an idle bridge."""
    (tmp_path / "Default").mkdir()
    wanted = tmp_path / "Profile 1" / "Extensions" / launcher.TAMPERMONKEY_ID
    wanted.mkdir(parents=True)
    assert launcher.find_tampermonkey_profile(tmp_path) == "Profile 1"

    commands = launcher.build_command("/chrome", tmp_path, 2, "Profile 1")
    for command in commands:
        assert "--profile-directory=Profile 1" in command
        assert any(arg.startswith("--user-data-dir=") for arg in command)


def test_a_profile_without_tampermonkey_is_not_selected(launcher, tmp_path):
    (tmp_path / "Default").mkdir()
    assert launcher.find_tampermonkey_profile(tmp_path) is None


def test_a_running_chrome_is_refused_not_silently_unflagged(
    launcher, monkeypatch, capsys
):
    """The flags are process-creation flags. Launching while Chrome runs only
    messages the existing process: the window opens, every flag is dropped,
    and the tab stays clamped with nothing saying so.

    That is the failure mode that cost 2026-09-22 - a check that reported
    healthy while the tabs ran at a fifth of their speed - so this must be a
    hard refusal and never a warning.
    """
    monkeypatch.setattr(launcher, "find_chrome", lambda: "/chrome")
    monkeypatch.setattr(launcher, "chrome_is_running", lambda: True)
    monkeypatch.setattr(launcher, "find_tampermonkey_profile", lambda _p: "Profile 1")
    monkeypatch.setattr(launcher.sys, "argv", ["launch_bridge_browser.py"])
    launched = []
    monkeypatch.setattr(
        launcher.subprocess, "Popen", lambda *a, **k: launched.append(a)
    )

    rc = launcher.main()

    assert rc == 1
    assert launched == [], "nothing launches when the flags would be dropped"
    assert "already running" in capsys.readouterr().err


def test_the_default_window_count_stays_above_one(launcher):
    """Capacity comes from opening more windows, never from making one window
    faster - MIN_INTERVAL_MS is the floor and is never lowered."""
    assert launcher.DEFAULT_WINDOWS >= 3


def test_min_interval_ms_is_not_something_this_script_touches(launcher):
    """The fix is that a background tab becomes as fast as a visible one
    already was. It must never become a way to outpace the 350 ms floor."""
    import inspect

    source = inspect.getsource(launcher)
    assert "MIN_INTERVAL_MS" not in launcher.ANTI_THROTTLE_FLAGS
    assert "--disable-features" not in source, (
        "no blanket feature disabling - the three named flags are the contract"
    )
