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
        ground_type=None,
        default_period_count=None,
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


# --------------------------------------------------------------------------
# F35: a rung past the model's resolution is refused, not floored.
#
# On the production path, because the defect was invisible to every unit test
# of the estimator — calc_p_central returned 0.05 exactly as documented. What
# it could not see is that 0.05 then travelled on as a *claim* and, ranked by
# surplus, took 33 of the coupon's 40 slots.
# --------------------------------------------------------------------------


def test_f35_a_tail_rung_produces_no_priced_row() -> None:
    """A team averaging ~1.3 goals, asked for 6.5+, at odds of 150."""
    samples = make_samples(
        "goals_total", [1, 2, 1, 0, 2, 1, 1, 2, 1, 1], [1, 1, 2, 1, 0, 1, 2, 1, 1, 1]
    )
    rows, skipped = run(samples, make_offer([rung(6.5, 150.0, 1.01)]))

    over_rows = [r for r in rows if r.direction == "OVER" and r.line == 6.5]
    assert over_rows == [], (
        "the tail rung must not be priced at all; before F35 it produced a row "
        f"with p_central=0.05 and a surplus of +128: {over_rows}"
    )

    reasons = {str(reason) for _rung, reason, _detail in skipped}
    assert "OUTSIDE_MODEL_RESOLUTION" in reasons, (
        f"the refusal must be recorded with a reason, got {reasons}"
    )


def test_f35_the_central_rung_of_the_same_ladder_survives() -> None:
    """The refusal is a tail rule; it must not empty the ladder it sits on."""
    samples = make_samples(
        "goals_total", [1, 2, 1, 0, 2, 1, 1, 2, 1, 1], [1, 1, 2, 1, 0, 1, 2, 1, 1, 1]
    )
    rows, _ = run(samples, make_offer([rung(2.5, 2.10, 1.75), rung(6.5, 150.0, 1.01)]))

    assert [r for r in rows if r.line == 2.5], (
        "a rung the model can resolve must still be priced"
    )


# --------------------------------------------------------------------------
# Tennis shrinks its centre onto the ladder. See K_TENNIS_LADDER_CENTRE.
#
# `config/sofa_league_baselines.json` holds 451 per-competition entries for
# `goals_for` and exactly one for `games_won_for`, so the tennis shrink target
# was a single global mean spanning ATP to ITF and the shrunk centre came out
# indistinguishable from the raw sample (corr +0.198 against +0.199 over 327
# settled player-fixtures). Superbet's ladder is twice as correlated (+0.388).
# --------------------------------------------------------------------------


def _tennis_fixture() -> Fixture:
    return make_fixture(
        sport="tennis",
        home_name="Timo Legout",
        away_name="Daniil Ostapenkov",
        competition_name="ITF M25",
    )


def _games_ladder(market: str = "games_total") -> list[PricedRung]:
    """A two-sided ladder whose even-money crossing sits near 21.5 games."""
    return [
        rung(line, over, under, market=market)
        for line, over, under in (
            (19.5, 1.36, 3.10),
            (20.5, 1.57, 2.38),
            (21.5, 1.95, 1.89),
            (22.5, 2.50, 1.53),
            (23.5, 3.30, 1.33),
        )
    ]


def test_tennis_centre_is_pulled_onto_the_ladder() -> None:
    # A sample that says 17 games against a ladder that says about 21.5.
    samples = make_samples(
        "games_total", [17, 16, 18, 17, 17, 16, 18, 17, 17, 17], []
    )
    rows, _ = run(samples, make_offer(_games_ladder()), _tennis_fixture())
    assert rows
    row = rows[0]
    assert row.sample_mean == pytest.approx(17.0, abs=1e-6)
    assert row.ladder_centre is not None
    # n = 10, so the sample keeps 10 / (10 + 30) = 0.25 of the weight.
    expected = 0.25 * 17.0 + 0.75 * row.ladder_centre
    assert row.centre == pytest.approx(expected, abs=1e-3)
    assert 17.0 < row.centre < row.ladder_centre
    assert any("CENTRE_SHRUNK_TO_LADDER" in n for n in row.notes)


def test_football_is_not_in_scope() -> None:
    """Football is already calibrated to within 0.027 and has real baselines.

    With no baseline supplied the football path must fall through to the raw
    mean, exactly as before — never to the ladder.
    """
    samples = make_samples(
        "goals_total", [1, 2, 1, 2, 1, 2, 1, 2, 1, 2], []
    )
    rungs = [
        rung(line, over, under)
        for line, over, under in (
            (2.5, 1.36, 3.10), (3.5, 1.95, 1.89), (4.5, 3.30, 1.33),
        )
    ]
    rows, _ = run(samples, make_offer(rungs), make_fixture())
    assert rows
    for row in rows:
        assert row.centre == pytest.approx(row.sample_mean)
        assert not any("CENTRE_SHRUNK_TO_LADDER" in n for n in row.notes)


def test_tennis_without_a_ladder_keeps_the_old_path() -> None:
    """A one-sided ladder fits no centre, so there is nothing to shrink to."""
    samples = make_samples(
        "games_total", [17, 16, 18, 17, 17, 16, 18, 17, 17, 17], []
    )
    rungs = [rung(21.5, 1.95, None), rung(22.5, 2.50, None)]
    rows, _ = run(samples, make_offer(rungs), _tennis_fixture())
    for row in rows:
        assert row.centre == pytest.approx(row.sample_mean)
        assert not any("CENTRE_SHRUNK_TO_LADDER" in n for n in row.notes)
