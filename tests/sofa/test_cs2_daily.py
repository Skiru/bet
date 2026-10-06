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
    morning = [(t, c) for t, c in calls
               if c[-1] != "CS2" and c not in identity]
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
