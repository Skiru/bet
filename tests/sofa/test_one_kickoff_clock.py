"""OFFER, COUPON and CONFIDENCE read one kickoff clock and one margin.

2026-09-23: OFFER filtered on Sofascore's clock alone and re-priced 22 ITF
fixtures already in play (Sofascore runs 7-9 h late there), and CONFIDENCE had
no margin at all, so a builder was printed five minutes before its kickoff.
"""

import inspect
from datetime import UTC, datetime, timedelta

from bet.sofa.confidence import MIN_MINUTES_TO_KICKOFF, too_close_to_kickoff
from bet.sofa.contracts import Fixture
from bet.sofa.coupon import effective_kickoff

NOW = datetime(2026, 9, 23, 6, 25, tzinfo=UTC)


def _fixture(sofa: datetime, superbet: datetime | None) -> Fixture:
    return Fixture(
        sofascore_event_id=1,
        superbet_event_ids=["s"],
        sport="tennis",
        kickoff_utc=sofa,
        home_name="A",
        away_name="B",
        home_entity_id=1,
        away_entity_id=2,
        competition_name="ITF",
        competition_id=1,
        season_id=1,
        category_name="Cat",
        identity="CONFIRMED",
        round_number=None,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        ground_type="Hard",
        default_period_count=3,
        superbet_kickoff_utc=superbet,
    )


def test_the_earlier_clock_wins():
    late_sofascore = _fixture(NOW + timedelta(hours=7), NOW - timedelta(minutes=30))
    assert effective_kickoff(late_sofascore) == NOW - timedelta(minutes=30)
    only_sofascore = _fixture(NOW + timedelta(hours=1), None)
    assert effective_kickoff(only_sofascore) == NOW + timedelta(hours=1)


def test_confidence_keeps_the_coupon_margin():
    assert MIN_MINUTES_TO_KICKOFF == 15
    assert too_close_to_kickoff([NOW + timedelta(minutes=5)], NOW)
    assert too_close_to_kickoff([NOW + timedelta(minutes=15)], NOW)
    assert not too_close_to_kickoff([NOW + timedelta(minutes=16)], NOW)
    # The earlier of two clocks decides.
    assert too_close_to_kickoff(
        [NOW + timedelta(hours=7), NOW + timedelta(minutes=10)], NOW
    )
    assert too_close_to_kickoff([], NOW), "no clock at all is not 'far away'"


def test_every_gate_reads_the_shared_clock():
    import scripts.sofa.run_confidence as conf
    import scripts.sofa.run_coupon as coup
    import scripts.sofa.run_offer as offer

    assert "effective_kickoff(f) > cutoff" in inspect.getsource(offer)
    assert "f.kickoff_utc > cutoff" not in inspect.getsource(offer)
    assert "too_close_to_kickoff(clocks, now)" in inspect.getsource(conf)
    assert "minutes=MIN_MINUTES_TO_KICKOFF" in inspect.getsource(coup)
