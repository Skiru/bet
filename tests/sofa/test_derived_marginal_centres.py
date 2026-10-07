"""Football goals joints built from the marginal rows' centres (2026-10-07).

Walk-forward 2025-08..2026-09 (375,714 matches, bootstrap by match): BTTS Brier
against the competition's base rate +0.0172 with the raw sample mean / variance
the joint used, +0.0051 with the marginal rows' centre and variance; the
printable region (p >= 0.70) of "both >= 2" had realised 0.31 at +0.457 below p.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from bet.sofa import epochs
from bet.sofa.contracts import FixtureOffer, PricedRung
from bet.sofa.derived import SideStats, marginal_centred_stats, price_derived_rungs
from bet.sofa.engine import sheet_count_p_raw, sheet_predictive_sd
from bet.sofa.timeutil import now
from tests.sofa.test_derived_markets import make_fixture, make_samples

A = [2, 0, 1, 3, 1, 0, 2, 1, 1, 2]
B = [0, 1, 1, 0, 2, 1, 0, 0, 1, 1]


def _offer() -> FixtureOffer:
    rungs = [PricedRung(market="both_over_goals", subject="", line=0.5,
                        over_odds=1.80, under_odds=1.95, fetched_at_utc=now())]
    return FixtureOffer(sofascore_event_id=1, status="PRICED", rungs=rungs,
                        unmapped_markets=[])


def _price(centres):  # type: ignore[no-untyped-def]
    rows, _ = price_derived_rungs(
        fixture=make_fixture(), samples=make_samples("goals_for", A, B),
        offer=_offer(), correlations={"goals": 0.0}, vetoes=[], min_sample=5,
        max_ladder_sigma=9.0, k_price=10.0, unfitted=[], stats_only=True,
        marginal_centres=centres)
    return {r.direction: r for r in rows if r.line == 0.5}


def _marginal_p(centre: float, vals: list[int]) -> float:
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
    sd = sheet_predictive_sd("goals_for", "football", mean, var, len(vals), centre)
    return sheet_count_p_raw("goals_for", centre, sd, 0.5, "OVER")


def test_centred_stats_are_the_marginal_rows_estimator() -> None:
    raw = SideStats(n=10, mean=1.5, variance=1.2, sd=math.sqrt(1.2))
    got = marginal_centred_stats(raw, "goals_for", 1.3)
    sd = sheet_predictive_sd("goals_for", "football", 1.5, 1.2, 10, 1.3)
    assert got.mean == 1.3 and math.isclose(got.variance, sd * sd)
    assert got.n == 10


def test_btts_with_no_correlation_is_the_product_of_the_marginal_rows() -> None:
    centres = {("goals_for", "side_a"): 1.45, ("goals_for", "side_b"): 0.80}
    got = _price(centres)["OVER"].p_central
    assert got == pytest.approx(_marginal_p(1.45, A) * _marginal_p(0.80, B),
                                abs=3e-3)


def test_the_centres_move_the_joint_off_the_raw_sample() -> None:
    raw = _price(None)["OVER"].p_central
    centred = _price({("goals_for", "side_a"): 1.2,
                      ("goals_for", "side_b"): 1.1})["OVER"].p_central
    assert centred != raw


def test_without_both_centres_the_raw_joint_is_kept() -> None:
    raw = _price(None)
    one = _price({("goals_for", "side_a"): 1.4})
    for direction in raw:
        assert one[direction].p_central == raw[direction].p_central


def test_the_switch_opens_at_its_moment_for_the_day_being_built() -> None:
    at = epochs.DERIVED_MARGINAL_CENTRES_FROM_UTC
    assert at is not None
    day = epochs.DERIVED_MARGINAL_CENTRES_DATE
    assert not epochs.derived_marginal_centres_enabled(
        day, at.replace(minute=at.minute - 1))
    assert epochs.derived_marginal_centres_enabled(day, at)
    # a rebuild of an earlier day keeps the rule it printed under
    assert not epochs.derived_marginal_centres_enabled(
        "2026-10-06", datetime(2026, 10, 9, tzinfo=UTC))


def test_only_the_measured_metrics_are_recentred() -> None:
    measured = epochs.DERIVED_MARGINAL_CENTRES_METRICS
    assert {"goals_for", "corners_for", "shots_on_target_for",
            "cards_points_for"} == measured
    assert "fouls_for" not in measured and "shots_for" not in measured
