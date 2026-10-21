"""cs2_daily: the unattended CS2 day, on a fake clock."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.sofa import cs2_daily


class Clock:
    def __init__(self, start: datetime) -> None:
        self.t = start
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += timedelta(seconds=seconds)


def test_a_day_runs_snapshots_then_the_morning_steps_in_order() -> None:
    start = datetime(2026, 9, 29, 21, 45, tzinfo=UTC)
    clock = Clock(start)
    calls: list[tuple[datetime, list[str]]] = []

    def runner(cmd: list[str]) -> int:
        calls.append((clock.now(), cmd))
        return 1 if "CS2_SETTLE" in cmd else 0

    until = cs2_daily._at("2026-09-29", "23:30")
    settle_at = cs2_daily._at("2026-09-29", "05:00", day_offset=1)
    code = cs2_daily.run(
        "2026-09-29",
        30,
        until,
        settle_at,
        6.0,
        clock=clock.now,
        sleep=clock.sleep,
        runner=runner,
    )
    snaps = [t for t, c in calls if "CS2" in c and "--only" in c and c[-1] == "CS2"]
    # 21:45, 22:15, 22:45, 23:15 - never at or after 23:30.
    assert [t.strftime("%H:%M") for t in snaps] == ["21:45", "22:15", "22:45", "23:15"]
    identity = [c for _, c in calls if c[0].endswith("run_sport_identity.py")]
    # SPORT_IDENTITY for D and D+1 after each of the 4 snapshots
    assert len(identity) == 8 and {c[2] for c in identity} == {
        "2026-09-29", "2026-09-30"}
    bridge = [c for _, c in calls if c[0].endswith("ensure_bridge.py")]
    assert len(bridge) == 4  # before each snapshot's identity runs
    morning = [(t, c) for t, c in calls
               if c[-1] != "CS2" and c not in identity and c not in bridge]
    assert morning[0][0] == settle_at and morning[0][1][-1] == "CS2_SETTLE"
    assert morning[0][1][2] == "2026-09-29"
    # the day before again: its STATS_PENDING series and night series
    assert morning[1][1][2] == "2026-09-28" and morning[1][1][-1] == "CS2_SETTLE"
    # D-7..D-2: settle_cs2 decides at run time which of them still wait
    assert morning[2][1] == ["scripts/sofa/settle_cs2.py", "--sweep-from",
                             "2026-09-22", "--sweep-to", "2026-09-27"]
    assert morning[3][1][0].endswith("record_results.py")
    assert morning[3][1][1:] == ["--from", "2026-09-22", "--to", "2026-09-29"]
    assert morning[4][1][0].endswith("backfill_cs2.py")
    assert morning[5][1][0].endswith("audit_cs2.py") and "--history" in morning[5][1]
    assert not any("sport_coupon" in c[0] for _, c in calls)
    assert code == 1  # the worst step, the audit not counted


def test_backfill_can_be_skipped_and_a_late_start_goes_straight_to_morning() -> None:
    clock = Clock(datetime(2026, 9, 30, 6, 0, tzinfo=UTC))  # after both times
    calls: list[list[str]] = []
    cs2_daily.run(
        "2026-09-29",
        30,
        cs2_daily._at("2026-09-29", "23:30"),
        cs2_daily._at("2026-09-29", "05:00", 1),
        0,
        clock=clock.now,
        sleep=clock.sleep,
        runner=lambda c: calls.append(c) or 0,
    )
    assert [c[-1] for c in calls][0] == "CS2_SETTLE"
    assert not any(c[0].endswith("backfill_cs2.py") for c in calls)
    assert clock.slept == []


def test_a_second_cs2_loop_for_the_same_day_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    import sys

    from scripts.sofa import cs2_daily

    loop = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            "scripts/sofa/cs2_daily.py",
            "--date",
            "2026-09-30",
        ]
    )
    other = subprocess.Popen(["sleep", "30"])
    try:
        pid_file = tmp_path / "daily.pid"
        pid_file.write_text(str(loop.pid))
        assert cs2_daily.already_running(pid_file, "2026-09-30") == loop.pid
        # A shadow loop's pid, or another date, is not this loop.
        assert cs2_daily.already_running(pid_file, "2026-10-01") is None
        assert (
            cs2_daily.already_running(pid_file, "2026-09-30", script="shadow_daily.py")
            is None
        )
        pid_file.write_text(str(other.pid))  # a recycled pid
        assert cs2_daily.already_running(pid_file, "2026-09-30") is None

        monkeypatch.setattr(cs2_daily, "REPO", tmp_path)
        monkeypatch.setenv("SOFA_RUNS_DIR", "runs")
        cs2_daily.pid_file("2026-09-30").parent.mkdir(parents=True)
        cs2_daily.pid_file("2026-09-30").write_text(str(loop.pid))
        monkeypatch.setattr("sys.argv", ["cs2_daily", "--date", "2026-09-30"])
        ran: list[object] = []
        monkeypatch.setattr(cs2_daily, "run", lambda *a, **k: ran.append(a) or 0)
        assert cs2_daily.main() == 2 and not ran
    finally:
        for p in (loop, other):
            p.kill()
            p.wait()



def test_chain_starts_the_next_day_once_when_the_snapshots_end() -> None:
    clock = Clock(datetime(2026, 9, 29, 22, 50, tzinfo=UTC))
    events: list[str] = []

    def runner(cmd: list[str]) -> int:
        events.append("settle" if "CS2_SETTLE" in cmd else cmd[0])
        return 0

    cs2_daily.run(
        "2026-09-29",
        30,
        cs2_daily._at("2026-09-29", "23:30"),
        cs2_daily._at("2026-09-29", "05:00", day_offset=1),
        0,
        clock=clock.now,
        sleep=clock.sleep,
        runner=runner,
        after_snapshots=lambda: events.append("chain"),
    )
    assert events.count("chain") == 1
    # after every snapshot, before the first settle
    assert events.index("chain") < events.index("settle")
    assert all(e != "settle" for e in events[: events.index("chain")])


# --- morning retries (2026-10-02: CS2_SETTLE 403'd at 05:00Z and FAILED) ---------


def _retry_day(fail_times: int) -> tuple[list[tuple[datetime, list[str]]], int]:
    clock = Clock(datetime(2026, 10, 2, 4, 59, tzinfo=UTC))
    calls: list[tuple[datetime, list[str]]] = []
    left = {"n": fail_times}

    def runner(cmd: list[str]) -> int:
        calls.append((clock.now(), cmd))
        if cmd[-1] == "CS2_SETTLE" and cmd[2] == "2026-10-01":
            if left["n"] > 0:
                left["n"] -= 1
                return 2
        if cmd[0].endswith("backfill_cs2.py"):
            return 2  # a failed backfill is never retried
        clock.t += timedelta(seconds=60)
        return 0

    code = cs2_daily.run(
        "2026-10-01",
        30,
        cs2_daily._at("2026-10-01", "23:30"),
        cs2_daily._at("2026-10-01", "05:00", day_offset=1),
        6.0,
        clock=clock.now,
        sleep=clock.sleep,
        runner=runner,
    )
    return calls, code


def test_a_failed_settle_is_retried_with_its_dependent_steps() -> None:
    calls, code = _retry_day(fail_times=1)
    names = [Path(c[0]).name + ("" if c[-1] != "CS2_SETTLE" else f":{c[2]}")
             for _, c in calls]
    first = [t for t, c in calls if c[-1] == "CS2_SETTLE" and c[2] == "2026-10-01"]
    assert len(first) == 2, "one retry, then it settled"
    assert timedelta(minutes=30) <= first[1] - first[0] <= timedelta(minutes=40)
    after = names[names.index("run_pipeline.py:2026-10-01", 1):]
    # the retry, then the offline steps that read what it wrote, then the audit
    assert after == ["run_pipeline.py:2026-10-01", "record_results.py", "audit_cs2.py"]
    assert names.count("backfill_cs2.py") == 1, "a backfill is never repeated"
    assert names.count("settle_cs2.py") == 1, "a step that worked is not repeated"
    assert code == 2  # the backfill's own failure still counts


def test_retries_stop_after_four_hours() -> None:
    calls, _ = _retry_day(fail_times=99)
    tries = [t for t, c in calls if c[-1] == "CS2_SETTLE" and c[2] == "2026-10-01"]
    assert len(tries) == 1 + 8
    assert tries[-1] - tries[0] <= timedelta(hours=4, minutes=30)


def test_a_clean_morning_is_not_retried() -> None:
    calls, _ = _retry_day(fail_times=0)
    assert sum(1 for _, c in calls if c[-1] == "CS2_SETTLE") == 2


def test_watchdog_relaunch_keeps_the_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.sofa import cs2_watchdog

    seen: list[list[str]] = []
    monkeypatch.setattr(cs2_watchdog, "spawn", lambda args, log: seen.append(args))
    monkeypatch.setattr(cs2_watchdog, "log", lambda msg: None)
    cs2_watchdog.act("RELAUNCH", "2026-10-01")
    assert seen == [["scripts/sofa/cs2_daily.py", "--date", "2026-10-01", "--chain"]]


def _sleeper(tmp_path: Path, seconds: float, grandchild: bool = False) -> Path:
    """A tiny step script: optionally starts a grandchild that writes its pid,
    then sleeps."""
    script = tmp_path / "slow_step.py"
    pidfile = tmp_path / "grandchild.pid"
    body = ["import subprocess, sys, time"]
    if grandchild:
        body += [
            "p = subprocess.Popen("
            "[sys.executable, '-c', 'import time; time.sleep(60)'])",
            f"open({str(pidfile)!r}, 'w').write(str(p.pid))",
        ]
    body += [f"time.sleep({seconds})"]
    script.write_text("\n".join(body) + "\n", encoding="utf-8")
    return script


def _alive(pid: int) -> bool:
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie is dead for our purpose
    import subprocess

    stat = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                          capture_output=True, text=True).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


def test_a_hung_step_is_killed_with_its_group_and_failed_as_timeout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import sys
    import time

    script = _sleeper(tmp_path, 60, grandchild=True)
    t0 = time.monotonic()
    code = cs2_daily.step([str(script)], timeout_s=1.0, kill_grace_s=0.5,
                          python=sys.executable)
    assert code == 2
    assert time.monotonic() - t0 < 10
    assert "STEP_FAILED TIMEOUT" in capsys.readouterr().out
    gpid = int((tmp_path / "grandchild.pid").read_text())
    deadline = time.monotonic() + 5
    while _alive(gpid) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not _alive(gpid), "the step's whole process group is killed"


def test_a_step_that_ignores_sigterm_is_killed(tmp_path: Path) -> None:
    import sys
    import time

    script = tmp_path / "stubborn.py"
    script.write_text(
        "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "time.sleep(60)\n", encoding="utf-8")
    t0 = time.monotonic()
    assert cs2_daily.step([str(script)], timeout_s=1.0, kill_grace_s=0.5,
                          python=sys.executable) == 2
    assert time.monotonic() - t0 < 10


def test_a_step_within_its_limit_keeps_its_own_exit(tmp_path: Path) -> None:
    import sys

    script = tmp_path / "quick.py"
    script.write_text("import sys, time\ntime.sleep(0.2)\nsys.exit(1)\n",
                      encoding="utf-8")
    assert cs2_daily.step([str(script)], timeout_s=5.0, python=sys.executable) == 1


def test_a_timed_out_snapshot_does_not_stop_the_loop(tmp_path: Path) -> None:
    """The loop treats a TIMEOUT as any FAILED step: the next steps run."""
    import sys

    slow = _sleeper(tmp_path, 60)
    quick = tmp_path / "ok.py"
    quick.write_text("pass\n", encoding="utf-8")
    start = datetime(2026, 10, 1, 23, 0, tzinfo=UTC)
    clock = Clock(start)
    ran: list[str] = []

    def runner(cmd: list[str]) -> int:
        ran.append(cmd[0])
        return cs2_daily.step(cmd, timeout_s=0.5, kill_grace_s=0.2,
                              python=sys.executable)

    code = cs2_daily.loop(
        [str(slow)], [[str(quick)]], [str(quick)], 30,
        start + timedelta(minutes=45), start + timedelta(hours=6),
        clock=clock.now, sleep=clock.sleep, runner=runner,
        each_snapshot=[[str(quick)]],
    )
    assert ran.count(str(slow)) == 2, "the next iteration still snapshots"
    assert ran[-2:] == [str(quick), str(quick)], "morning and audit still run"
    assert code == 2


def test_the_step_limit_is_three_times_the_longest_measured_step() -> None:
    # 119.7 min: the longest step in every shadow / cs2 loop log 09-28..10-12
    assert cs2_daily.STEP_TIMEOUT_S >= 3 * 119.7 * 60
