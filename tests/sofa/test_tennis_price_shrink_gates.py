"""The three holes the 2026-09-23 verifier found in the tennis price shrink.

N1: p_central is 75% price at n=10, so a disagreement gate reading it saw a
quarter of the sample's disagreement - all 13 printed tennis singles passed.
N2: carried-forward rungs fetched after kickoff put in-play prices into the
number itself (Taro Daniel UNDER 12.5 at 50.0, fetched 05:49Z, kickoff 04:00Z).
N4: a one-rung ladder has no centre but has a price; it skipped the shrink.
And a unanimous sample stays refused (F35) instead of being priced by the price.
"""

from datetime import UTC, datetime

from bet.sofa.confidence import disagrees_with_price
from bet.sofa.contracts import (
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from scripts.sofa.run_sheet import strip_in_play_prices
from tests.sofa.test_player_markets import _sheet, dataclasses_replace_tennis

KICKOFF = datetime(2026, 9, 23, tzinfo=UTC)  # dataclasses_replace_tennis()


def _obs(values: list[float], start: int) -> list[Observation]:
    return [
        Observation(
            sofascore_event_id=start + i,
            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
            opponent=f"O{i}",
            value=v,
            competition_id=1,
            season_id=1,
            venue=None,
        )
        for i, v in enumerate(values)
    ]


def _samples(side_a: list[float]) -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            "games_won_set1_for": MetricSample(
                metric="games_won_set1_for",
                side_a=_obs(side_a, 1000),
                side_b=_obs([3, 2, 4, 1, 3, 2, 5, 2, 3, 2], 2000),
                h2h=[],
            )
        },
        gaps=[],
    )


def _rung(line: float, over: float, under: float, fetched: datetime) -> PricedRung:
    return PricedRung(
        market="games_won_set1_for", subject="Kenta Kawada", line=line,
        over_odds=over, under_odds=under, fetched_at_utc=fetched,
    )


def test_the_gate_reads_the_sample_not_the_price_shrunk_number():
    # sample 0.9, market 0.70: p_central 0.25*0.9 + 0.75*0.70 = 0.75
    assert disagrees_with_price(0.75, 0.70, 0.74, 1.35, sample_frequency=0.9)
    assert not disagrees_with_price(0.75, 0.70, 0.74, 1.35)


def test_a_rung_fetched_after_kickoff_loses_its_odds_not_its_row():
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[
            _rung(4.5, 1.60, 2.20, datetime(2026, 9, 22, 20, tzinfo=UTC)),
            _rung(5.5, 50.0, 1.01, datetime(2026, 9, 23, 1, tzinfo=UTC)),
        ],
    )
    fixture = dataclasses_replace_tennis()
    stripped, keys = strip_in_play_prices(offer, fixture)
    assert keys == {("games_won_set1_for", "Kenta Kawada", 5.5)}
    assert stripped.rungs[0].over_odds == 1.60
    assert stripped.rungs[1].over_odds is None and stripped.rungs[1].under_odds is None

    rows = _sheet(fixture, _samples([6, 6, 6, 7, 6, 6, 4, 6, 6, 3]), offer)
    in_play = [r for r in rows if r.line == 5.5]
    assert in_play, "the row must survive for SETTLE"
    assert all(r.offered_odds is None and r.market_p is None for r in in_play)
    assert all(any("IN_PLAY_PRICE_DROPPED" in n for n in r.notes) for r in in_play)


def test_a_one_rung_ladder_is_shrunk_toward_its_price_and_says_so():
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[_rung(4.5, 1.60, 2.20, datetime(2026, 9, 22, 20, tzinfo=UTC))],
    )
    rows = _sheet(
        dataclasses_replace_tennis(), _samples([6, 6, 6, 7, 6, 6, 4, 6, 6, 3]), offer
    )
    over = next(r for r in rows if r.direction == "OVER")
    assert over.sample_frequency == 0.8
    assert over.market_p is not None
    assert abs(over.p_central - (0.25 * 0.8 + 0.75 * over.market_p)) < 2e-3
    assert any(n.startswith("P_SHRUNK_TO_PRICE") for n in over.notes)
    assert any("K_TENNIS_LADDER_CENTRE" in n for n in over.notes)


def test_a_unanimous_sample_is_refused_not_priced_by_the_price():
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED", unmapped_markets=[],
        rungs=[_rung(3.5, 1.41, 2.57, datetime(2026, 9, 22, 20, tzinfo=UTC))],
    )
    rows = _sheet(
        dataclasses_replace_tennis(), _samples([6, 6, 6, 7, 6, 6, 4, 6, 6, 6]), offer
    )
    assert not [r for r in rows if r.line == 3.5], "10/10 over 3.5 has no resolution"


def test_coupon_reads_the_sample_frequency_too():
    import inspect

    import bet.sofa.coupon as coupon

    src = inspect.getsource(coupon.build_coupon)
    assert "row.sample_frequency" in src
