"""kickoff_disagreement_h follows the merged Superbet clock - 2026-10-03:
Humbert - Lehecka had both clocks at 08:10Z beside a gap of 8.17 h, the gap
of the first listing's 00:00Z placeholder."""

from __future__ import annotations

from datetime import UTC, datetime

from bet.sofa.contracts import BoardFixture, Fixture
from bet.sofa.resolve import kickoff_gap_h
from scripts.sofa.run_resolve import merge_duplicate_listing

SOFA = datetime(2026, 10, 3, 8, 10, tzinfo=UTC)
MIDNIGHT = datetime(2026, 10, 3, 0, 0, tzinfo=UTC)


def _fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["sb1"],
        sport="tennis",
        kickoff_utc=SOFA,
        home_name="Ugo Humbert",
        away_name="Jiri Lehecka",
        home_entity_id=10,
        away_entity_id=11,
        competition_name="ATP",
        competition_id=2,
        season_id=3,
        category_name="ATP",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type=None,
        default_period_count=3,
        superbet_kickoff_utc=MIDNIGHT,
        kickoff_disagreement_h=kickoff_gap_h(SOFA, MIDNIGHT),
    )


def _board(kickoff: datetime) -> BoardFixture:
    return BoardFixture(
        superbet_event_id="sb2",
        sport="tennis",
        match_name="Humbert U. - Lehecka J.",
        side_a="Humbert U.",
        side_b="Lehecka J.",
        kickoff_utc=kickoff,
    )


def test_gap_is_recomputed_when_the_placeholder_gives_way() -> None:
    held = _fixture()
    assert held.kickoff_disagreement_h == 8.17
    merge_duplicate_listing(held, _board(SOFA))
    assert held.superbet_kickoff_utc == SOFA
    assert held.kickoff_disagreement_h == 0.0
    assert held.superbet_event_ids == ["sb1", "sb2"]


def test_gap_follows_a_real_time_that_differs() -> None:
    held = _fixture()
    later = datetime(2026, 10, 3, 14, 40, tzinfo=UTC)
    merge_duplicate_listing(held, _board(later))
    assert held.kickoff_disagreement_h == 6.5


def test_kickoff_gap_without_superbet_clock_is_none() -> None:
    assert kickoff_gap_h(SOFA, None) is None
