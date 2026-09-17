import math

import pytest

from bet.sofa.contracts import SheetRow
from bet.sofa.engine import (
    bar_probability,
    calc_p_central,
    calculate_p_low,
    devig,
    get_required_odds,
    ladder_centre,
    normal_cdf,
    predictive_sd,
    winning_boundary,
)


def test_t17_p_central_sum_to_one():
    # p_central(OVER) + p_central(UNDER) == 1 before clamp.
    # A half line has no push, so both directions read the same boundary,
    # and therefore their z-scores are symmetric.
    # Let's test on a half line first to avoid push mass.
    line = 2.5
    centre = 2.2
    sd = 1.3

    bound_over = winning_boundary(line, "OVER")
    bound_under = winning_boundary(line, "UNDER")

    assert bound_over == 2.5
    assert bound_under == 2.5

    # Calculate directly without clamp
    z_under = (bound_under - centre) / sd
    p_under_raw = normal_cdf(z_under)

    z_over = -(bound_over - centre) / sd
    p_over_raw = normal_cdf(z_over)

    assert math.isclose(p_under_raw + p_over_raw, 1.0, rel_tol=1e-9)

    # With clamp
    p_over = calc_p_central(centre, sd, bound_over, "OVER")
    p_under = calc_p_central(centre, sd, bound_under, "UNDER")

    # If clamped to 0.95 and 0.05, sum is 1.0
    # Difference from 1.0 is bounded by 2 * (1 - 0.95) = 0.1
    diff = abs(1.0 - (p_over + p_under))
    assert diff <= 0.10001


def test_t18_monotonicity_with_line():
    centre = 2.0
    sd = 1.0

    lines = [0.5, 1.5, 2.5, 3.5, 4.5]
    p_overs = []
    p_unders = []

    for line in lines:
        bound_over = winning_boundary(line, "OVER")
        bound_under = winning_boundary(line, "UNDER")
        p_overs.append(calc_p_central(centre, sd, bound_over, "OVER"))
        p_unders.append(calc_p_central(centre, sd, bound_under, "UNDER"))

    for i in range(1, len(lines)):
        assert p_overs[i] <= p_overs[i - 1]  # OVER should decrease
        assert p_unders[i] >= p_unders[i - 1]  # UNDER should increase


def test_t19_required_odds_monotonicity_and_floor():
    p_bars = [0.9, 0.5, 0.1, 0.05, 0.01, 0.0001]

    # If bar_probability returns 0.01 because of floor
    p_bar_clamped, _ = bar_probability(
        p_central=0.001, hits=0, n=10, p_low_val=0.001, market_p=None
    )
    assert p_bar_clamped == 0.01

    odds = [get_required_odds(p) for p in p_bars]
    for i in range(1, len(odds)):
        # Odds should increase as p decreases
        assert odds[i] >= odds[i - 1]


def test_t20_predictive_sd():
    variance = 2.0
    mean = 2.0
    sample_sd = math.sqrt(variance)

    for n in range(2, 20):
        pred_sd = predictive_sd(variance, mean, n)
        assert pred_sd > sample_sd

    # Specifically for n=5
    pred_sd_5 = predictive_sd(variance, mean, 5)
    ratio = pred_sd_5 / sample_sd
    assert math.isclose(ratio, math.sqrt(1 + 1 / 5), rel_tol=1e-5)


def test_t21_winning_boundary_whole_line():
    assert winning_boundary(2.0, "OVER") == 2.5
    assert winning_boundary(2.0, "UNDER") == 1.5

    # Ensure push mass is not included in either direction
    centre = 2.0
    sd = 1.0
    p_over = calc_p_central(centre, sd, 2.5, "OVER")
    p_under = calc_p_central(centre, sd, 1.5, "UNDER")

    # For a perfect standard normal around 2.0, mass between 1.5 and 2.5 is push
    # So P(OVER) + P(UNDER) < 1.0
    assert p_over + p_under < 1.0


def test_t22_devig_single_sided():
    assert devig(1.9, None) is None
    assert devig(None, 1.9) is None


def test_t23_ladder_centre():
    # Only one rung
    assert ladder_centre([(2.5, 0.6)]) is None

    # Both above 0.5
    assert ladder_centre([(1.5, 0.8), (2.5, 0.6)]) is None

    # Both below 0.5
    assert ladder_centre([(4.5, 0.4), (5.5, 0.2)]) is None

    # Crossing 0.5
    res = ladder_centre([(2.5, 0.6), (3.5, 0.4)])
    assert res is not None
    assert math.isclose(res, 3.0, rel_tol=1e-5)


def test_t24_calibration_correction_cannot_raise_p():
    p_central = 0.5
    market_p = None

    p_bar_zero, _ = bar_probability(
        p_central, hits=5, n=10, p_low_val=0.5, market_p=market_p, correction=0.0
    )
    p_bar_corr, _ = bar_probability(
        p_central, hits=5, n=10, p_low_val=0.5, market_p=market_p, correction=0.05
    )

    assert p_bar_corr < p_bar_zero


def test_t25_edge_uses_p_central_not_p_bar():
    # edge = p_central - market_p
    # Create a dummy row to test field calculations
    row = SheetRow(
        sofascore_event_id=1,
        sport="football",
        market="goals_total",
        subject="",
        line=2.5,
        direction="OVER",
        sample_size=10,
        sample_mean=2.5,
        sample_sd=1.0,
        centre=2.5,
        p_central=0.6,
        market_p=0.5,
        ladder_centre=None,
        ladder_sigma=None,
        p_bar=0.55,  # explicitly different from p_central
        bar_reason="none",
        required_odds=2.0,
        offered_odds=2.1,
        edge=0.6 - 0.5,  # p_central - market_p
        surplus=0.1,
        verdict="VALUE",
        notes=[],
    )

    assert math.isclose(row.edge, 0.1, rel_tol=1e-5)
    # If edge was using p_bar, it would be 0.55 - 0.5 = 0.05
    assert not math.isclose(row.edge, 0.05, rel_tol=1e-5)


# --------------------------------------------------------------------------
# Edges of the engine: the branches where a wrong answer is silent.
# --------------------------------------------------------------------------

def test_predictive_sd_refuses_an_empty_sample():
    """n=0 has no predictive spread; returning something would invent one."""
    with pytest.raises(ValueError, match="n must be greater than 0"):
        predictive_sd(1.0, 1.0, 0)


def test_p_low_refuses_an_empty_sample():
    with pytest.raises(ValueError, match="n must be greater than 0"):
        calculate_p_low(2.0, 1.0, 0, 2.5, "OVER")


@pytest.mark.parametrize(
    ("centre", "boundary", "direction", "expected"),
    [
        (0.0, 0.5, "UNDER", 0.95),  # clamped from 1.0
        (0.0, 0.5, "OVER", 0.05),   # clamped from 0.0
        (3.0, 2.5, "OVER", 0.95),
        (3.0, 2.5, "UNDER", 0.05),
    ],
)
def test_zero_spread_still_respects_the_clamp(centre, boundary, direction, expected):
    """A sample with no spread is certain; the clamp says we are not.

    sd == 0 happens on a real sample where every match had the same value.
    Reporting p = 1.0 would make required_odds 1.10 and the row unbeatable on
    paper — the clamp is what stops that becoming a bet.
    """
    assert calc_p_central(centre, 0.0, boundary, direction) == expected


@pytest.mark.parametrize(
    ("over", "under"),
    [(1.0, 2.0), (2.0, 1.0), (0.5, 2.0), (1.0, 1.0)],
)
def test_devig_refuses_impossible_prices(over, under):
    """An odds of 1.0 or below implies p >= 1; devigging it invents a market."""
    assert devig(over, under) is None


def test_ladder_centre_of_a_flat_pair_is_the_midpoint():
    """Two rungs quoted at the same probability locate the centre between them."""
    assert ladder_centre([(2.5, 0.5), (3.5, 0.5)]) == 3.0


def test_veto_sets_the_sample_weight_to_zero_against_a_price():
    """SAMPLE_UNINFORMATIVE means the sample is worth zero observations.

    No value of n expresses that, so it is a separate switch — and when a
    market price exists, p_bar must collapse onto it entirely.
    """
    p_bar, reason = bar_probability(
        p_central=0.80,
        hits=5,
        n=10,
        p_low_val=0.70,
        market_p=0.40,
        force_weight_0=True,
    )
    assert p_bar == pytest.approx(0.40)
    assert reason == "veto_uninformative"


def test_veto_without_a_price_is_named_differently():
    """There is nothing to shrink toward, and the report must not pretend there was."""
    p_bar, reason = bar_probability(
        p_central=0.80,
        hits=5,
        n=10,
        p_low_val=0.70,
        market_p=None,
        force_weight_0=True,
    )
    assert p_bar == pytest.approx(0.80)
    assert reason == "veto_uninformative_no_price"


def test_a_negative_correction_cannot_lower_the_bar():
    """T24 as a property: §6.5 step 2 may only raise the required price.

    A hand-edited config with a negative correction would otherwise turn a
    measured overconfidence into a discount.
    """
    base, _ = bar_probability(0.60, 3, 10, 0.50, None, correction=0.0)
    lifted, _ = bar_probability(0.60, 3, 10, 0.50, None, correction=-0.20)
    assert lifted == pytest.approx(base)
    lowered, _ = bar_probability(0.60, 3, 10, 0.50, None, correction=0.20)
    assert lowered < base


def test_the_probability_floor_keeps_required_odds_finite():
    """T19: p_bar -> 0 must not make the required price infinite."""
    p_bar, _ = bar_probability(0.05, 0, 10, 0.05, None, correction=0.99)
    assert p_bar == pytest.approx(0.01)
    assert get_required_odds(p_bar) == pytest.approx(110.0)


def test_zero_misses_takes_the_laplace_cap():
    """A sample that hit every time does not mean the next one will.

    (hits+1)/(n+2) is the cap; without it a 10-for-10 sample declares ~0.95 and
    the bar it implies is a price the market will happily take the other side of.
    """
    p_bar, reason = bar_probability(
        p_central=0.95,
        hits=10,
        n=10,
        p_low_val=0.99,   # deliberately not the binding cap
        market_p=None,
    )
    assert reason == "laplace_cap"
    assert p_bar == pytest.approx(11 / 12)


def test_the_laplace_cap_never_raises_p():
    """It is a ceiling, not a replacement: a modest p is left alone."""
    p_bar, reason = bar_probability(
        p_central=0.40, hits=10, n=10, p_low_val=0.99, market_p=None
    )
    assert reason == "none"
    assert p_bar == pytest.approx(0.40)
