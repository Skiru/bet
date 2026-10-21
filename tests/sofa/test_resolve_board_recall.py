"""RESOLVE's recall counts board entries bridged, not fixtures over entries.

2026-10-21: 718 board entries, 104 of them second listings of a match already
resolved (tennis, shifted clock), 33 real gaps. Fixtures over entries gave
0.809 and read every merge as a miss; entries bridged give 685 / 718.
"""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa.contracts import BoardFixture, Fixture
from scripts.sofa.run_resolve import board_recall


def _board(sid: str) -> BoardFixture:
    return BoardFixture(
        superbet_event_id=sid, sport="tennis", match_name="A·B",
        side_a="A", side_b="B",
        kickoff_utc=datetime(2026, 10, 21, 1, 30, tzinfo=UTC),
        tournament_id=None, category_id=None,
    )


def _fixture(event_id: int, sids: list[str]) -> Fixture:
    return Fixture(
        sofascore_event_id=event_id, superbet_event_ids=sids, sport="tennis",
        kickoff_utc=datetime(2026, 10, 21, 1, 30, tzinfo=UTC),
        home_name="A", away_name="B", home_entity_id=1, away_entity_id=2,
        competition_name="C", competition_id=1, season_id=1,
        category_name="X", identity="CONFIRMED", round_number=None,
        round_name=None, cup_round_type=None, previous_leg_event_id=None,
        venue_name=None, referee=None, ground_type=None,
        default_period_count=None,
    )


def test_merged_second_listing_is_not_a_miss() -> None:
    board = [_board("1"), _board("2"), _board("3"), _board("4")]
    resolved = [_fixture(10, ["1", "2"]), _fixture(11, ["3"])]
    # two fixtures from four entries, but only entry 4 is a gap
    assert board_recall(board, resolved) == 0.75


def test_empty_board() -> None:
    assert board_recall([], []) == 0.0
