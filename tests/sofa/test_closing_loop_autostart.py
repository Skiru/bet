"""The day's closing-price loop starts by itself (2026-10-15: started by hand
85 min after the first print, so the legs that kicked off in between closed
with no price).

cs2_daily.py (chained at 23:30Z the day before) and shadow_daily.py (04:30Z)
start capture_closing.py --loop for their date as they start
(cs2_daily.ensure_closing -> capture_closing.ensure_loop); a live loop for the
date is left alone; the loop waits for the coupon until the day is over;
day_status WARNs on a missing loop already before the build.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from scripts.sofa import capture_closing as cc
from scripts.sofa import cs2_daily, day_status, shadow_daily
from scripts.sofa.capture_closing import spawn_loop as real_spawn_loop

D = "2026-10-16"
KO = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def now(self) -> datetime:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += timedelta(seconds=s)


def _runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    runs = tmp_path / "runs"
    monkeypatch.setenv("SOFA_RUNS_DIR", str(runs))
    return runs


def _coupon(day: Path, n: int = 1) -> None:
    day.mkdir(parents=True, exist_ok=True)
    legs = [{"sofascore_event_id": 7000 + i, "kickoff_utc": KO.isoformat(),
             "market": "goals_total", "subject": "", "line": 2.5,
             "direction": "OVER", "offered_odds": 1.9, "sport": "football"}
            for i in range(n)]
    (day / "02_fixtures.json").write_text("[]")
    (day / "11_coupon.json").write_text(
        json.dumps({"singles": legs, "pdf_max_singles": None}))


# --- ensure_loop: the spawn decision and the guard -----------------------------------


def test_ensure_loop_starts_one_when_none_runs(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = _runs(tmp_path, monkeypatch)
    spawned: list[str] = []
    seen: list[Path] = []

    def holder(day_dir: Path) -> int | None:
        seen.append(day_dir)
        return None

    line = cc.ensure_loop(D, spawn=lambda d: spawned.append(d) or 4242,
                          holder=holder,
                          clock=lambda: datetime(2026, 10, 15, 23, 30, tzinfo=UTC))
    assert spawned == [D] and "started pid 4242" in line
    assert seen == [runs / D]


def test_ensure_loop_leaves_a_live_loop_alone(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _runs(tmp_path, monkeypatch)
    spawned: list[str] = []
    line = cc.ensure_loop(D, spawn=lambda d: spawned.append(d) or 1,
                          holder=lambda day_dir: 999,
                          clock=lambda: datetime(2026, 10, 16, 4, 30, tzinfo=UTC))
    assert spawned == [] and "already running (pid 999)" in line


def test_ensure_loop_uses_the_pid_file_guard(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default holder is loop_holder: a pid file whose live process is a
    capture_closing loop for the date blocks; a foreign process does not."""
    runs = _runs(tmp_path, monkeypatch)
    (runs / D).mkdir(parents=True)
    (runs / D / cc.PID_FILE).write_text(str(os.getppid()))
    spawned: list[str] = []
    clock = lambda: datetime(2026, 10, 16, 4, 30, tzinfo=UTC)  # noqa: E731
    monkeypatch.setattr(cc, "spawn_loop", lambda d: spawned.append(d) or 5)
    real_holder = cc.loop_holder
    command = {"line": "/usr/sbin/someone_else"}
    monkeypatch.setattr(
        cc, "loop_holder",
        lambda day_dir: real_holder(day_dir, lambda pid: command["line"]))
    assert "started" in cc.ensure_loop(D, clock=clock) and spawned == [D]
    command["line"] = f"python scripts/sofa/capture_closing.py --date {D} --loop"
    assert "already running" in cc.ensure_loop(D, clock=clock) and spawned == [D]


def test_ensure_loop_skips_a_finished_day_and_never_raises(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _runs(tmp_path, monkeypatch)
    spawned: list[str] = []
    after = lambda: datetime(2026, 10, 17, 0, 0, tzinfo=UTC)  # noqa: E731
    assert "day over" in cc.ensure_loop(
        D, spawn=lambda d: spawned.append(d) or 1, holder=lambda p: None, clock=after)
    assert spawned == []

    def broken(date: str) -> int:
        raise OSError("no fork")

    line = cc.ensure_loop(D, spawn=broken, holder=lambda p: None,
                          clock=lambda: datetime(2026, 10, 16, tzinfo=UTC))
    assert "NOT started" in line and "no fork" in line


def test_spawn_loop_is_detached_into_the_days_log(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runs = _runs(tmp_path, monkeypatch)
    calls: list[tuple[list[str], dict[str, Any]]] = []

    class FakeProc:
        pid = 31337

    def popen(cmd: list[str], **kw: Any) -> FakeProc:
        calls.append((cmd, kw))
        return FakeProc()

    monkeypatch.setattr(cc.subprocess, "Popen", popen)
    assert real_spawn_loop(D) == 31337
    (cmd, kw), = calls
    assert cmd[1:] == ["scripts/sofa/capture_closing.py", "--date", D, "--loop"]
    assert kw["start_new_session"] is True and kw["cwd"] == cc.REPO
    assert kw["stdout"].name == str(runs / D / "capture_closing.log")
    assert kw["env"]["PYTHONPATH"].split(os.pathsep)[:2] == [
        str(cc.REPO / "src"), str(cc.REPO)]


# --- the daily loops call it as they start ---------------------------------


def test_cs2_daily_starts_the_days_closing_loop_at_its_start(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs2_daily, "REPO", tmp_path)
    monkeypatch.setenv("SOFA_RUNS_DIR", "runs")
    events: list[str] = []
    monkeypatch.setattr(cs2_daily, "run",
                        lambda *a, **k: events.append("run") or 0)
    monkeypatch.setattr("sys.argv", ["cs2_daily", "--date", D, "--chain"])
    assert cs2_daily.main(spawn=lambda d: 1,
                          closing=lambda d: events.append(f"closing:{d}") or "x") == 0
    assert events == [f"closing:{D}", "run"]


def test_shadow_daily_starts_the_days_closing_loop_at_its_start(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(shadow_daily, "REPO", Path("/"))
    events: list[str] = []
    monkeypatch.setattr(shadow_daily, "loop",
                        lambda *a, **k: events.append("loop") or 0)
    monkeypatch.setattr("sys.argv", ["shadow_daily", "--date", D])
    assert shadow_daily.main(
        spawn=lambda d: 1,
        closing=lambda d: events.append(f"closing:{d}") or "x") == 0
    assert events == [f"closing:{D}", "loop"]


def test_a_second_daily_loop_does_not_start_the_closing_loop(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused (duplicate) daily loop exits before touching anything."""
    monkeypatch.setattr(cs2_daily, "REPO", tmp_path)
    monkeypatch.setenv("SOFA_RUNS_DIR", "runs")
    monkeypatch.setattr(cs2_daily, "already_running", lambda *a, **k: 123)
    called: list[str] = []
    monkeypatch.setattr("sys.argv", ["cs2_daily", "--date", D])
    assert cs2_daily.main(closing=lambda d: called.append(d) or "x") == 2
    assert called == []


def test_ensure_closing_goes_through_capture_closing(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _runs(tmp_path, monkeypatch)
    line = cs2_daily.ensure_closing("2020-01-01")  # long over: nothing spawned
    assert line == "capture_closing 2020-01-01: day over, not started"


# --- the loop waits for the coupon ---------------------------------------------------


def test_a_loop_started_before_the_build_waits_for_the_coupon(
        tmp_path: Path) -> None:
    day = tmp_path / D
    day.mkdir()
    clock = Clock(datetime(2026, 10, 15, 23, 30, tzinfo=UTC))
    passes: list[datetime] = []

    def once(day_dir: Path, fetcher: Any) -> int:
        passes.append(clock.t)
        if clock.t >= datetime(2026, 10, 16, 6, 0, tzinfo=UTC) and not (
                day_dir / "11_coupon.json").exists():
            _coupon(day_dir)  # the build prints at 06:00Z
        return 0

    assert cc.loop(day, None, clock=clock.now, sleep=clock.sleep, once=once) == 0
    # waited from 23:30Z, then closed until the 09:00Z leg was inside its window
    assert passes[0] == datetime(2026, 10, 15, 23, 30, tzinfo=UTC)
    assert passes[-1] >= KO - timedelta(minutes=cc.CLOSE_MAX_MINUTES)
    assert clock.t <= KO  # it ends with the last leg, not with the night


def test_a_loop_whose_coupon_never_comes_ends_with_the_day(tmp_path: Path) -> None:
    day = tmp_path / D
    day.mkdir()
    clock = Clock(datetime(2026, 10, 16, 20, 0, tzinfo=UTC))
    assert cc.loop(day, None, clock=clock.now, sleep=clock.sleep,
                   once=lambda d, f: 0) == 0
    assert clock.t >= datetime(2026, 10, 17, tzinfo=UTC)
    assert clock.t < datetime(2026, 10, 17, 0, 10, tzinfo=UTC)


def test_08_confidence_alone_is_not_a_built_stats_only_day(tmp_path: Path) -> None:
    day = tmp_path / D
    day.mkdir()
    (day / "08_confidence.json").write_text("{}")
    assert not cc.coupon_built(day)
    (day / "11_coupon.json").write_text("{}")
    assert cc.coupon_built(day)
    old = tmp_path / "2026-10-01"
    old.mkdir()
    (old / "08_confidence.json").write_text("{}")
    assert cc.coupon_built(old)


# --- day_status: a missing loop is a WARN before the build -----------------


def _closing_check(runs: Path, now: datetime, pid_cmd: str = "") -> day_status.Check:
    got = {c.name: c for c in day_status.loop_checks(
        runs, D, now, command_of=lambda pid: pid_cmd)}
    return got["loop:capture_closing"]


def test_day_status_warns_on_a_missing_closing_loop_before_the_build(
        tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    (runs / D).mkdir(parents=True)
    early = datetime(2026, 10, 16, 1, 0, tzinfo=UTC)
    c = _closing_check(runs, early)
    assert c.status == day_status.WARN and "not built yet" in c.detail
    # before D has even begun (the loop is due at 23:30Z D-1)
    assert _closing_check(runs, datetime(2026, 10, 15, 23, 45, tzinfo=UTC)
                          ).status == day_status.WARN
    # a waiting loop is OK
    (runs / D / cc.PID_FILE).write_text(str(os.getppid()))
    ok = _closing_check(
        runs, early, f"python scripts/sofa/capture_closing.py --date {D} --loop")
    assert ok.status == day_status.OK and f"pid {os.getppid()}" in ok.detail


def test_day_status_closing_after_the_build_and_after_the_day(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _coupon(runs / D)
    # built, a leg ahead, no loop: the existing WARN
    c = _closing_check(runs, datetime(2026, 10, 16, 6, 0, tzinfo=UTC))
    assert c.status == day_status.WARN and "still to close" in c.detail
    # built, every leg past its window: OK
    assert _closing_check(runs, datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
                          ).status == day_status.OK
    # never built and the day is over: nothing left to close
    (runs / D / "11_coupon.json").unlink()
    assert _closing_check(runs, datetime(2026, 10, 17, 1, 0, tzinfo=UTC)
                          ).status == day_status.OK
