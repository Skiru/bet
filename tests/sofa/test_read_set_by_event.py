"""The analysts' read set counts events, not positions (operator, 2026-10-08:
"30 wydarzeń a nie 30 rynków - 30 wydarzeń może mieć 150 rynków")."""

from __future__ import annotations

import datetime
from typing import Any

from bet.sofa import epochs
from bet.sofa.confidence import (
    READ_REQUIRED_EVENTS,
    READ_REQUIRED_SINGLES,
    legs_requiring_read,
)
from scripts.sofa.build_coupon import assemble

UTC = datetime.UTC


def leg(eid: int, conf: float, line: float) -> dict[str, Any]:
    return {"sofascore_event_id": eid, "confidence": conf,
            "kickoff_utc": "2026-10-09T20:00:00Z", "market": "corners_total",
            "subject": "", "line": line, "direction": "OVER",
            "offered_odds": 1.3, "match": f"M{eid}", "display_market": "c"}


def day(events: int, legs_each: int) -> list[dict[str, Any]]:
    # match i's best leg is a bit weaker than match i-1's, legs within a match
    # fall by 0.001: one block per match in order
    return [leg(e, 0.95 - e * 0.005 - k * 0.0005, 5.5 + k)
            for e in range(1, events + 1) for k in range(legs_each)]


def build(singles: list[dict[str, Any]], by_event: bool) -> dict[str, Any]:
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}
    return assemble(conf, None, [], {}, "now", "2026-10-09", read_events=by_event)


def test_the_epoch_switch_is_the_next_days_midnight() -> None:
    at = epochs.READ_EVENTS_FROM_UTC
    assert at == datetime.datetime(2026, 10, 9, 0, 0, tzinfo=UTC)
    assert not epochs.read_by_event("2026-10-08", at)
    assert not epochs.read_by_event("2026-10-09", at - datetime.timedelta(seconds=1))
    assert epochs.read_by_event("2026-10-09", at)


def test_thirty_events_with_every_market_are_read_not_thirty_positions() -> None:
    singles = day(events=40, legs_each=5)                 # 200 legs, 40 matches
    old = build(singles, by_event=False)
    new = build(singles, by_event=True)
    assert old["read_unit"] == "position" and new["read_unit"] == "event"
    assert len(legs_requiring_read(old)) == READ_REQUIRED_SINGLES      # 30 legs, 6 matches
    got = legs_requiring_read(new)
    assert len(got) == READ_REQUIRED_EVENTS * 5                         # 150 legs
    assert {s["sofascore_event_id"] for s in got} == set(range(1, 31))
    # every leg still prints either way
    assert len(old["singles"]) == len(new["singles"]) == 200


def test_the_first_matches_are_those_of_the_coupons_own_order() -> None:
    singles = day(events=35, legs_each=2)
    singles.append(leg(99, 0.999, 4.5))                   # the best leg: its match first
    new = build(singles, by_event=True)
    ids = {s["sofascore_event_id"] for s in legs_requiring_read(new)}
    assert 99 in ids and len(ids) == READ_REQUIRED_EVENTS
    assert 30 not in ids        # pushed out by the best-leg match


def test_locked_legs_builders_and_requests_still_join_the_set() -> None:
    singles = day(events=33, legs_each=1)
    singles.append({**leg(500, 0.99, 3.5), "locked": True,
                    "printed_at_utc": "2026-10-09T05:00:00Z"})
    doc = build(singles, by_event=True)
    got = legs_requiring_read(doc)
    assert all(not s.get("locked") for s in got)          # a locked leg is no read
    asked = [{"group_key": "sofa:33"}]
    more = legs_requiring_read(doc, asked)
    assert {s["sofascore_event_id"] for s in more} - {s["sofascore_event_id"] for s in got} == {33}


def test_an_old_artifact_keeps_the_position_rule() -> None:
    doc = build(day(events=40, legs_each=5), by_event=False)
    doc.pop("read_unit")
    assert len(legs_requiring_read(doc)) == READ_REQUIRED_SINGLES
