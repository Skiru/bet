"""cs2_daily: the unattended CS2 day, on a fake clock."""

from datetime import UTC, datetime, timedelta

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
