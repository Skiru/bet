"""Fixes from the 2026-09-26 settlement review (2026-09-27).

1. One physical match listed twice by Sofascore entered a sample twice
   (16 of 1,280 sample sides on 09-26, 12 of 970 on 09-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa.samples import get_historical_events, one_listing_per_match


def _event(
    event_id: int,
    day: int,
    opponent: int = 99,
    score: tuple[int, int] = (1, 0),
    hour: int = 12,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "startTimestamp": int(
            datetime(2026, 9, day, hour, 0, tzinfo=UTC).timestamp()
        ),
        "status": {"type": "finished", "code": 100},
        "homeTeam": {"id": 1},
        "awayTeam": {"id": opponent},
        "homeScore": {"current": score[0]},
        "awayScore": {"current": score[1]},
        "tournament": {"uniqueTournament": {"id": 186}},
    }


def test_two_listings_of_one_match_count_once() -> None:
    # APS Zakynthos - APO Ellas Syrou: 17056234 and 17079707, one match.
    events = [_event(17079707, 19), _event(17056234, 19), _event(500, 12)]
    kept = one_listing_per_match(events)
    assert sorted(e["id"] for e in kept) == [500, 17056234]


def test_same_opponent_on_another_day_is_another_match() -> None:
    kept = one_listing_per_match([_event(1, 12), _event(2, 19)])
    assert len(kept) == 2


def test_copies_that_disagree_on_the_score_are_both_dropped() -> None:
    # FK Zlatibor: 3-0 in the cup listing, 1-1 in the "friendly" one.
    events = [_event(16721756, 1, score=(3, 0)), _event(16695008, 1, score=(1, 1))]
    assert one_listing_per_match(events) == []


def test_side_order_does_not_hide_a_copy() -> None:
    a = _event(10, 5)
    b = _event(11, 5)
    b["homeTeam"], b["awayTeam"] = b["awayTeam"], b["homeTeam"]
    b["homeScore"], b["awayScore"] = a["homeScore"], a["awayScore"]
    assert len(one_listing_per_match([a, b])) == 1


def test_a_mirror_under_other_entity_ids_is_caught_by_the_names() -> None:
    # Japan Regional League: one match in two tournaments, the opponent under
    # two entity ids, two hours apart on the same day.
    a = _event(16365146, 17, opponent=501, score=(0, 2), hour=8)
    b = _event(16189754, 17, opponent=502, score=(0, 2), hour=6)
    for e in (a, b):
        e["homeTeam"]["name"] = "Fujieda City Hall SC"
        e["awayTeam"]["name"] = "Gakunan F Mosuperio"
    kept = one_listing_per_match([a, b])
    assert [e["id"] for e in kept] == [16189754]


def test_the_sample_is_filled_after_the_duplicate_is_removed() -> None:
    # Eleven listings, one of them a copy: sample_n=10 must still be ten
    # distinct matches, not nine plus a double.
    page = [_event(1000 + d, d) for d in range(1, 11)]
    page.append(_event(2010, 10))

    class _Cache:
        def get_entity_events(self, *a: object) -> dict[str, Any] | None:
            return {"events": page}

        def save_entity_events(self, *a: object) -> None:
            return None

        def get_listed_events(self, *a: object) -> list[dict]:
            return []  # empty listed-event index

    class _Fixture:
        kickoff_utc = datetime(2026, 9, 25, tzinfo=UTC)
        ground_type = None
        default_period_count = None

    class _Config:
        sample_n = 10

    events = get_historical_events(
        client=None,  # type: ignore[arg-type]
        cache=_Cache(),  # type: ignore[arg-type]
        entity_id=1,
        sport="football",
        fixture=_Fixture(),  # type: ignore[arg-type]
        config=_Config(),  # type: ignore[arg-type]
    )
    ids = [e["id"] for e in events]
    assert len(ids) == 10
    assert 2010 not in ids
    days = {datetime.fromtimestamp(e["startTimestamp"], UTC).day for e in events}
    assert len(days) == 10
