"""Superbet voids a match not played by the end of the day after the start it
was offered at, 23:59 local time at the venue (Regulamin Zakładów Online
5.E.1.a, approved 2026-02-10; read on support.superbet.pl 2026-10-13). Until
2026-10-13 the code read the 2022 rules' 48 h (settle.VOID_AFTER), which
graded a match replayed 30 h later on the next-but-one day and refunded none
of them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bet.sofa import cs2, shadow
from bet.sofa.settle import (
    moved_beyond_void,
    not_played_beyond_void,
    venue_timezone,
    void_deadline,
)

# 20:00 in Warsaw (CEST, UTC+2)
OFFERED = datetime(2026, 10, 8, 18, 0, tzinfo=UTC)


def _event(start: datetime, *, kind: str = "finished", venue: str | None = None,
           category: str | None = None, home: str | None = None,
           sport: str = "football") -> dict[str, Any]:
    return {
        "startTimestamp": int(start.timestamp()),
        "status": {"type": kind},
        "venue": {"country": {"alpha2": venue}} if venue else None,
        "tournament": {"category": {"alpha2": category, "sport": {"slug": sport}}},
        "homeTeam": {"country": {"alpha2": home}} if home else {},
    }


def test_deadline_is_the_end_of_the_next_local_day() -> None:
    warsaw = ZoneInfo("Europe/Warsaw")
    assert void_deadline(OFFERED, warsaw) == datetime(2026, 10, 9, 21, 59, tzinfo=UTC)
    assert void_deadline(OFFERED) == datetime(2026, 10, 9, 23, 59, tzinfo=UTC)
    # a 23:30 local start keeps the whole next day, not 24 h
    late = datetime(2026, 10, 8, 21, 30, tzinfo=UTC)
    assert void_deadline(late, warsaw) == datetime(2026, 10, 9, 21, 59, tzinfo=UTC)


def test_venue_zone_venue_then_competition_then_home_side() -> None:
    assert venue_timezone(_event(OFFERED, venue="PL", category="EN")).key == "Europe/Warsaw"  # type: ignore[attr-defined]
    assert venue_timezone(_event(OFFERED, category="PL")).key == "Europe/Warsaw"  # type: ignore[attr-defined]
    assert venue_timezone(_event(OFFERED, home="JP")).key == "Asia/Tokyo"  # type: ignore[attr-defined]
    # a tennis player's nationality is not where he plays
    assert venue_timezone(_event(OFFERED, home="JP", sport="tennis")) is UTC
    assert venue_timezone(_event(OFFERED)) is UTC
    assert venue_timezone(None) is UTC


def test_moved_past_the_deadline_is_void_inside_48_h() -> None:
    clocks = [OFFERED]
    # replayed next day 23:00 local: valid
    assert not moved_beyond_void(_event(datetime(2026, 10, 9, 21, 0, tzinfo=UTC),
                                        category="PL"), clocks)
    # two days on at 19:00 local (47 h): void now, graded under the 48 h rule
    two_days = OFFERED + timedelta(hours=47)
    assert moved_beyond_void(_event(two_days, category="PL"), clocks)
    # brought forward: the 48 h rule as before
    assert not moved_beyond_void(_event(OFFERED - timedelta(hours=47), category="PL"), clocks)
    assert moved_beyond_void(_event(OFFERED - timedelta(hours=49), category="PL"), clocks)


def test_still_postponed_reads_the_venue_deadline() -> None:
    ev = _event(OFFERED, kind="postponed", category="PL")
    assert not not_played_beyond_void(ev, [OFFERED], datetime(2026, 10, 9, 21, 58, tzinfo=UTC))
    assert not_played_beyond_void(ev, [OFFERED], datetime(2026, 10, 9, 22, 0, tzinfo=UTC))


def test_measured_sports_and_cs2_read_the_same_deadline() -> None:
    detail = _event(OFFERED, kind="postponed", category="PL", sport="ice-hockey")
    before = datetime(2026, 10, 9, 21, 58, tzinfo=UTC)
    after = datetime(2026, 10, 9, 22, 0, tzinfo=UTC)
    sport = shadow.SPORTS["hockey"]
    assert shadow.event_state(detail, sport, OFFERED, before) == "PENDING"
    assert shadow.event_state(detail, sport, OFFERED, after) == "VOID"
    series = {"status": {"type": "notstarted"}}  # no country: UTC
    assert cs2.event_state(series, OFFERED, datetime(2026, 10, 9, 23, 58, tzinfo=UTC)) == "PENDING"
    assert cs2.event_state(series, OFFERED, datetime(2026, 10, 10, 0, 0, tzinfo=UTC)) == "VOID"
