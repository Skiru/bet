"""The SHEET stage on its production path.

These drive ``process_fixture`` itself rather than hand-constructing a SheetRow.
A test that builds the row it then asserts on cannot fail when the production
code computes the field differently — which is exactly how `edge` stayed
untested while being the number the operator reads.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.contracts import (
    Fixture,
    FixtureOffer,
    FixtureSamples,
    MetricSample,
    Observation,
    PricedRung,
)
from scripts.sofa.run_sheet import determine_side, process_fixture

FETCHED = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)


def make_fixture(**overrides: object) -> Fixture:
    base = dict(
        sofascore_event_id=1,
        superbet_event_ids=["sb1"],
        sport="football",
        kickoff_utc=datetime(2026, 9, 17, 18, 0, tzinfo=UTC),
        home_name="Arsenal",
        away_name="Chelsea",
        home_entity_id=42,
        away_entity_id=38,
        competition_name="Premier League",
        competition_id=17,
        season_id=1,
        category_name="England",
        identity="CONFIRMED",
        round_number=5,
        round_name=None,
        cup_round_type=None,
        previous_leg_event_id=None,
        venue_name=None,
        referee=None,
        has_xg=True,
        ground_type=None,
        best_of=None,
    )
    base.update(overrides)
    return Fixture(**base)  # type: ignore[arg-type]


def observations(values: list[float], start_id: int = 1000) -> list[Observation]:
    return [
        Observation(
            sofascore_event_id=start_id + i,
            match_date_utc=datetime(2026, 9, 1 + i, tzinfo=UTC),
            opponent=f"Opp{i}",
            value=v,
            competition_id=17,
            season_id=1,
            venue="home",
        )
        for i, v in enumerate(values)
    ]


def make_samples(
    metric: str, side_a: list[float], side_b: list[float]
) -> FixtureSamples:
    return FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            metric: MetricSample(
                metric=metric,
                side_a=observations(side_a, 1000),
                side_b=observations(side_b, 2000),
                h2h=[],
            )
        },
        gaps=[],
    )


def make_offer(rungs: list[PricedRung]) -> FixtureOffer:
    return FixtureOffer(
        sofascore_event_id=1, status="PRICED", rungs=rungs, unmapped_markets=[]
    )


def rung(
    line: float, over: float | None, under: float | None, market: str = "goals_total"
) -> PricedRung:
    return PricedRung(
        market=market,
        subject="",
        line=line,
        over_odds=over,
        under_odds=under,
        fetched_at_utc=FETCHED,
    )


def run(samples: FixtureSamples, offer: FixtureOffer, fixture: Fixture | None = None):
    return process_fixture(
        fixture or make_fixture(),
        samples,
        offer,
        baselines={},
        reliability={},
        engine_constants={},
        vetoes=[],
        config=SofaConfig(),
    )


# --------------------------------------------------------------------------
# The ladder gate is the only external check a live row gets (§3.2, §6.6).
# --------------------------------------------------------------------------


def test_single_rung_cannot_be_value() -> None:
    """One rung gives a probability, not a position — so no ladder check exists."""
    samples = make_samples("goals_total", [3, 2, 4, 3, 2, 5], [2, 3, 3, 4, 2, 3])
    # A single rung priced generously enough that surplus is comfortably > 0.
    rows, _ = run(samples, make_offer([rung(2.5, 5.00, 1.10)]))

    value_rows = [r for r in rows if r.verdict == "VALUE"]
    assert value_rows == []

    leaned = [r for r in rows if r.verdict == "LEAN"]
    assert leaned, "a priced rung with surplus must still produce a row"
    assert any("NO_LADDER_CHECK" in note for r in leaned for note in r.notes)
    assert all(r.ladder_sigma is None for r in leaned)


def test_one_sided_ladder_cannot_be_value() -> None:
    """A ladder entirely on one side of 0.5 never locates a centre."""
    samples = make_samples("goals_total", [3, 2, 4, 3, 2, 5], [2, 3, 3, 4, 2, 3])
    # Both rungs sit far above 0.5 for OVER, so no 0.5 crossing exists.
    offer = make_offer([rung(0.5, 1.02, 15.0), rung(1.5, 1.05, 10.0)])
    rows, _ = run(samples, offer)
    assert all(r.ladder_sigma is None for r in rows)
    assert all(r.verdict != "VALUE" for r in rows)


def test_crossing_ladder_can_be_value() -> None:
    """A ladder that does straddle 0.5 measures sigma and can promote."""
    samples = make_samples("goals_total", [3, 3, 3, 3, 3, 3, 4], [3, 3, 3, 3, 3, 2, 3])
    offer = make_offer(
        [
            rung(2.5, 1.60, 2.30),  # OVER favoured
            rung(3.5, 2.60, 1.48),  # UNDER favoured -> crossing between them
        ]
    )
    rows, _ = run(samples, offer)
    measured = [r for r in rows if r.ladder_sigma is not None]
    assert measured, "a crossing ladder must produce a measured sigma"
    assert all(r.ladder_centre is not None for r in measured)


# --------------------------------------------------------------------------
# edge is computed on the production path, from p_central (L17, T25).
# --------------------------------------------------------------------------


def test_edge_is_p_central_minus_market_p_on_the_real_path() -> None:
    samples = make_samples("goals_total", [3, 2, 4, 3, 2, 5], [2, 3, 3, 4, 2, 3])
    rows, _ = run(samples, make_offer([rung(2.5, 1.90, 1.90), rung(3.5, 2.90, 1.40)]))
    priced = [r for r in rows if r.market_p is not None]
    assert priced
    for r in priced:
        assert r.edge == pytest.approx(round(r.p_central - r.market_p, 4), abs=1e-9)


def test_edge_differs_from_the_p_bar_version() -> None:
    """Construct a case where p_bar != p_central, then prove edge uses p_central."""
    samples = make_samples("goals_total", [5, 5, 5, 5, 5, 5], [5, 5, 5, 5, 5, 5])
    rows, _ = run(samples, make_offer([rung(2.5, 1.10, 8.0), rung(3.5, 1.30, 4.0)]))
    differing = [
        r for r in rows if r.market_p is not None and abs(r.p_bar - r.p_central) > 1e-6
    ]
    assert differing, "need a row where the two differ for this test to mean anything"
    for r in differing:
        assert r.edge == pytest.approx(round(r.p_central - r.market_p, 4), abs=1e-9)
        assert r.edge != pytest.approx(round(r.p_bar - r.market_p, 4), abs=1e-9)


# --------------------------------------------------------------------------
# Rungs that produce no row must say why (C8).
# --------------------------------------------------------------------------


def test_thin_sample_is_reported_not_silent() -> None:
    samples = make_samples("goals_total", [1, 2], [2, 3])
    rows, skipped = run(samples, make_offer([rung(2.5, 1.9, 1.9)]))
    assert rows == []
    assert [reason.value for _, reason, _ in skipped] == ["THIN_SAMPLE"]


def test_all_zero_sample_is_refused() -> None:
    """L1: a median of zero is a signal about the provider, not about football."""
    samples = make_samples("corners_total", [0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0])
    rows, skipped = run(samples, make_offer([rung(9.5, 1.9, 1.9, "corners_total")]))
    assert rows == []
    assert [reason.value for _, reason, _ in skipped] == ["ALL_ZERO_SAMPLE"]


def test_unmatched_subject_does_not_land_on_the_home_side() -> None:
    fixture = make_fixture()
    samples = FixtureSamples(
        sofascore_event_id=1,
        readiness="READY",
        metrics={
            "corners_for": MetricSample(
                metric="corners_for",
                side_a=observations([5, 6, 4, 7, 5, 6], 1000),
                side_b=observations([3, 2, 4, 3, 2, 3], 2000),
                h2h=[],
            )
        },
        gaps=[],
    )
    offer = make_offer(
        [
            PricedRung(
                market="corners_for",
                subject="Tottenham Hotspur",  # neither side
                line=4.5,
                over_odds=1.9,
                under_odds=1.9,
                fetched_at_utc=FETCHED,
            )
        ]
    )
    rows, skipped = run(samples, offer, fixture)
    assert rows == []
    assert skipped and "matches neither side" in skipped[0][2]


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Arsenal", "side_a"),
        ("Arsenal FC", "side_a"),
        ("Chelsea", "side_b"),
        ("Tottenham Hotspur", None),
        ("", None),
    ],
)
def test_determine_side(subject: str, expected: str | None) -> None:
    assert determine_side(subject, make_fixture()) == expected


# --------------------------------------------------------------------------
# A push is neither a hit nor a miss when counting for the Laplace cap.
# --------------------------------------------------------------------------


def test_push_is_not_counted_as_a_hit_for_the_laplace_cap() -> None:
    """Every observation lands exactly on an integer line: all pushes.

    If pushes counted as hits, hits == n would trigger the Laplace cap and the
    bar would be built from a sample that never actually won.
    """
    samples = make_samples("goals_total", [3, 3, 3, 3, 3, 3], [3, 3, 3, 3, 3, 3])
    rows, _ = run(samples, make_offer([rung(3.0, 1.9, 1.9)]))
    assert rows
    assert all(r.bar_reason != "laplace_cap" for r in rows)
