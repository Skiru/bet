"""The sticky read set (epochs.READ_SET_STICKY_FROM_UTC, confidence.
READ_SET_MEMBERS): a match once in the analysts' read set stays in until its
start, a free place is filled only from matches starting more than
READ_SET_ENTRY_CLOSE after the build, and an artifact without members keeps
the recomputed top 20. The defect of 2026-11-15: every rebuild re-ranked the
top 20, rounds of unread legs went 42 -> 91 -> 7 -> ... -> 0 and Leixões -
Chaves entered 12 min before its start and printed unread."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from bet.sofa import confidence as cf
from bet.sofa import epochs
from scripts.sofa import read_set as rs
from scripts.sofa.build_coupon import assemble, prior_read_members

UTC = datetime.UTC
AT = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


def leg(eid: int, value: float, start_min: int, market: str = "corners_total",
        ) -> dict[str, Any]:
    """A measured-sport leg (no price_gap cap): read_value = conf x odds."""
    start = AT + datetime.timedelta(minutes=start_min)
    return {"sofascore_event_id": eid, "confidence": value / 2.0, "sport": "hockey",
            "kickoff_utc": start.isoformat().replace("+00:00", "Z"),
            "market": market, "subject": "", "line": 5.5, "direction": "OVER",
            "offered_odds": 2.0, "match": f"M{eid}", "display_market": "c"}


def build(singles: list[dict[str, Any]], prior: list[dict[str, Any]] | None,
          at: datetime.datetime = AT, n: int = 3) -> dict[str, Any]:
    conf = {"profile": "standard", "epoch": "stats_only", "created_at_utc": "x",
            "singles": singles, "legs": singles, "builders": []}
    return assemble(conf, None, [], {}, at.isoformat().replace("+00:00", "Z"),
                    None, read_events=True, read_value_order=True,
                    read_events_n=n, read_members_prior=prior)


def ids(doc: dict[str, Any]) -> set[int]:
    return {int(s["sofascore_event_id"]) for s in cf.legs_requiring_read(doc)}


def test_the_switch_is_the_next_days_midnight() -> None:
    at = epochs.READ_SET_STICKY_FROM_UTC
    assert at == datetime.datetime(2026, 11, 25, 0, 0, tzinfo=UTC)
    assert not epochs.read_set_sticky("2026-11-24", at)
    assert not epochs.read_set_sticky("2026-11-25", at - datetime.timedelta(seconds=1))
    assert epochs.read_set_sticky("2026-11-25", at)


def test_entry_close_is_the_window_reads_margin() -> None:
    from bet.sofa.window_reads import START_MARGIN

    assert cf.READ_SET_ENTRY_CLOSE == START_MARGIN == datetime.timedelta(minutes=30)


def test_first_build_takes_the_best_value_open_matches() -> None:
    doc = build([leg(1, 1.0, 300), leg(2, 0.9, 300), leg(3, 0.8, 300),
                 leg(4, 0.7, 300)], prior=[])
    assert ids(doc) == {1, 2, 3}
    assert [m["group_key"] for m in doc[cf.READ_SET_MEMBERS]] == [
        cf.group_key(leg(e, 1, 0)) for e in (1, 2, 3)]


def test_a_better_priced_newcomer_does_not_displace_a_member() -> None:
    first = build([leg(1, 1.0, 300), leg(2, 0.9, 300), leg(3, 0.8, 300)], prior=[])
    # a fresh price lifts match 4 to the top: the set does not rotate
    again = build([leg(1, 1.0, 300), leg(2, 0.9, 300), leg(3, 0.8, 300),
                   leg(4, 1.5, 300)], prior=first[cf.READ_SET_MEMBERS])
    assert ids(again) == {1, 2, 3}


def test_a_member_whose_legs_left_keeps_its_place_and_its_new_legs_are_read() -> None:
    first = build([leg(1, 1.0, 300), leg(2, 0.9, 300), leg(3, 0.8, 300),
                   leg(4, 0.7, 300)], prior=[])
    # a read removed match 2's leg: no newcomer takes its place (no new round)
    second = build([leg(1, 1.0, 300), leg(3, 0.8, 300), leg(4, 0.7, 300)],
                   prior=first[cf.READ_SET_MEMBERS])
    assert ids(second) == {1, 3}
    # its new leg later is still a member's leg
    third = build([leg(1, 1.0, 300), leg(2, 0.5, 300, market="shots_total"),
                   leg(3, 0.8, 300), leg(4, 0.7, 300)],
                  prior=second[cf.READ_SET_MEMBERS])
    assert ids(third) == {1, 2, 3}


def test_a_started_member_frees_a_place_only_for_a_match_far_enough_ahead() -> None:
    first = build([leg(1, 1.0, 60), leg(2, 0.9, 300), leg(3, 0.8, 300),
                   leg(5, 0.6, 300)], prior=[])
    later = AT + datetime.timedelta(minutes=70)  # match 1 started
    # match 4 (best value) starts 20 min after the build: it never enters,
    # the place goes to match 5 (230 min ahead)
    doc = build([leg(2, 0.9, 300), leg(3, 0.8, 300), leg(4, 1.4, 90),
                 leg(5, 0.6, 300)], prior=first[cf.READ_SET_MEMBERS], at=later)
    assert ids(doc) == {2, 3, 5}
    # every member is kept, the started one too (membership only grows)
    assert len(doc[cf.READ_SET_MEMBERS]) == 4
    # and match 4 is not a read-set leg, so C3 does not count it unread
    assert 4 not in ids(doc)


def test_no_place_is_filled_inside_the_entry_close() -> None:
    doc = build([leg(1, 1.0, 29), leg(2, 0.9, 30), leg(3, 0.8, 31)], prior=[])
    assert ids(doc) == {3}


def test_without_members_the_artifact_keeps_the_recomputed_top() -> None:
    doc = build([leg(1, 1.0, 10), leg(2, 0.9, 300), leg(3, 0.8, 300),
                 leg(4, 0.7, 300)], prior=None)
    assert cf.READ_SET_MEMBERS not in doc
    assert ids(doc) == {1, 2, 3}


def test_prior_members_come_from_the_days_coupon(tmp_path: Path) -> None:
    assert prior_read_members(tmp_path) == []
    first = build([leg(1, 1.0, 300)], prior=[])
    (tmp_path / cf.COUPON_ARTIFACT).write_text(json.dumps(first), encoding="utf-8")
    assert prior_read_members(tmp_path) == first[cf.READ_SET_MEMBERS]


def test_buffer_is_the_next_non_members() -> None:
    first = build([leg(1, 1.0, 300), leg(2, 0.9, 300), leg(3, 0.8, 300)], prior=[])
    doc = build([leg(1, 0.1, 300), leg(2, 0.9, 300), leg(3, 0.8, 300),
                 leg(4, 1.2, 300), leg(5, 0.7, 300), leg(6, 0.6, 300)],
                prior=first[cf.READ_SET_MEMBERS])
    assert ids(doc) == {1, 2, 3}
    got = {int(s["sofascore_event_id"]) for s in rs.buffer_legs(doc, 2)}
    assert got == {4, 5}
