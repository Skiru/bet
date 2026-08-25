"""Test suite for Europe/Warsaw betting day semantics and time bounds (B06, C2 tests 12-18)."""

from datetime import date, datetime, UTC
import pytest

from bet.pipeline.event_runtime_contract import (
    betting_day_utc_bounds,
    parse_utc_timestamp,
    NaiveDatetimeError,
    ProviderEventRevalidationRegistry,
)


def test_b06_warsaw_betting_day_utc_bounds():
    """B06 / C2 tests 12, 13, 14, 15, 16: Warsaw betting day UTC bounds, summer, winter, DST transitions, half-open interval."""
    # 12. Summer boundary (CEST = UTC+2)
    start_utc_summer, end_utc_summer = betting_day_utc_bounds(date(2026, 7, 30), timezone_name="Europe/Warsaw")
    assert start_utc_summer.isoformat() == "2026-07-29T22:00:00+00:00", f"Summer start wrong: {start_utc_summer.isoformat()}"
    assert end_utc_summer.isoformat() == "2026-07-30T22:00:00+00:00", f"Summer end wrong: {end_utc_summer.isoformat()}"

    # 14. Half-open interval [start, end)
    evt_inside = datetime(2026, 7, 29, 23, 0, 0, tzinfo=UTC)
    evt_at_end = datetime(2026, 7, 30, 22, 0, 0, tzinfo=UTC)
    assert start_utc_summer <= evt_inside < end_utc_summer, "Event inside interval failed"
    assert not (start_utc_summer <= evt_at_end < end_utc_summer), "Half-open end boundary failed"

    # 13. Winter boundary (CET = UTC+1)
    start_utc_winter, end_utc_winter = betting_day_utc_bounds(date(2026, 1, 15), timezone_name="Europe/Warsaw")
    assert start_utc_winter.isoformat() == "2026-01-14T23:00:00+00:00", f"Winter start wrong: {start_utc_winter.isoformat()}"
    assert end_utc_winter.isoformat() == "2026-01-15T23:00:00+00:00", f"Winter end wrong: {end_utc_winter.isoformat()}"

    # 15. Spring DST transition (2026-03-29, 23-hour day local)
    start_dst_spring, end_dst_spring = betting_day_utc_bounds(date(2026, 3, 29), timezone_name="Europe/Warsaw")
    assert start_dst_spring.isoformat() == "2026-03-28T23:00:00+00:00"
    assert end_dst_spring.isoformat() == "2026-03-29T22:00:00+00:00"

    # 16. Fall DST transition (2026-10-25, 25-hour day local)
    start_dst_fall, end_dst_fall = betting_day_utc_bounds(date(2026, 10, 25), timezone_name="Europe/Warsaw")
    assert start_dst_fall.isoformat() == "2026-10-24T22:00:00+00:00"
    assert end_dst_fall.isoformat() == "2026-10-25T23:00:00+00:00"


def test_b06_naive_timestamp_rejection():
    """B06 / C2 test 17: naive datetime is rejected."""
    naive_dt = datetime(2026, 7, 30, 15, 0, 0)
    with pytest.raises(NaiveDatetimeError, match="NAIVE_DATETIME_REJECTED"):
        parse_utc_timestamp(naive_dt)

    naive_str = "2026-07-30T15:00:00"
    with pytest.raises(NaiveDatetimeError, match="NAIVE_DATETIME_REJECTED"):
        parse_utc_timestamp(naive_str)


def test_c2_equivalent_iso_instants():
    """C2 test 18: equivalent ISO instants."""
    ts1 = "2026-07-30T15:00:00Z"
    ts2 = "2026-07-30T15:00:00+00:00"
    ts3 = "2026-07-30T17:00:00+02:00"  # Same instant in UTC+2

    dt1 = parse_utc_timestamp(ts1)
    dt2 = parse_utc_timestamp(ts2)
    dt3 = parse_utc_timestamp(ts3)

    assert dt1 == dt2 == dt3
    assert ProviderEventRevalidationRegistry.timestamps_equal(ts1, ts3)
