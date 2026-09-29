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
    morning = [(t, c) for t, c in calls if c[-1] != "CS2"]
    assert morning[0][0] == settle_at and morning[0][1][-1] == "CS2_SETTLE"
    assert morning[1][1][0].endswith("backfill_cs2.py")
    assert morning[2][1][0].endswith("audit_cs2.py") and "--history" in morning[2][1]
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
