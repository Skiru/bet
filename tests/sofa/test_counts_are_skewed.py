"""The normal CDF is symmetric and a count is not.

Integrating a bell curve over a right-skewed count overstates the upper tail
near the centre, where the posted lines sit, and it does so in one direction:
every OVER rung inflated, every UNDER rung deflated by the same amount. Over
1,868,474 settled rows the shipping estimator ran +0.0469 on OVER; on the
2026-09-19 coupon that produced 462 OVER rows out of 520, claiming 0.4371
where the positions' own samples said 0.3465.

See NEGATIVE_BINOMIAL_METRICS for the per-metric measurement and the event-id
split half that chose the list.
"""

from __future__ import annotations

import math

import pytest

from bet.sofa.engine import (
    NEGATIVE_BINOMIAL_METRICS,
    calc_p_central_nb_raw,
    calc_p_central_raw,
    nb_survival,
    predictive_sd,
    support_floor_for,
    uses_negative_binomial,
    winning_boundary,
)


def test_the_measured_metrics_take_the_negative_binomial() -> None:
    for market in ("goals_for", "goals_total", "corners_for", "goals_1h_total"):
        assert uses_negative_binomial(market)
        assert market in NEGATIVE_BINOMIAL_METRICS


def test_the_metrics_it_lost_on_keep_the_normal() -> None:
    """High-mean shot and foul families are near symmetric; skew costs there."""
    for market in (
        "shots_total",
        "shots_for",
        "shots_on_target_total",
        "shots_on_target_for",
        "fouls_for",
    ):
        assert not uses_negative_binomial(market)


def test_an_unmeasured_metric_does_not_silently_change_behaviour() -> None:
    assert not uses_negative_binomial("xg_total")
    assert not uses_negative_binomial("some_metric_nobody_has_measured")


def test_survival_is_a_probability_and_decreases_in_k() -> None:
    prev = 1.0
    for k in range(0, 12):
        p = nb_survival(2.4, 3.6, k)
        assert 0.0 <= p <= 1.0
        assert p <= prev
        prev = p


def test_survival_falls_back_to_poisson_when_not_overdispersed() -> None:
    """variance <= mean has no negative binomial; it is Poisson."""
    mean = 2.0
    got = nb_survival(mean, mean, 2)
    # P(X > 2) = 1 - e^-2 (1 + 2 + 2)
    want = 1.0 - math.exp(-mean) * (1 + mean + mean * mean / 2)
    assert got == pytest.approx(want, abs=1e-12)


def test_over_and_under_are_complements() -> None:
    over = calc_p_central_nb_raw(1.4, 1.3, 1.5, "OVER")
    under = calc_p_central_nb_raw(1.4, 1.3, 1.5, "UNDER")
    assert over + under == pytest.approx(1.0, abs=1e-12)


def test_it_puts_no_mass_below_zero() -> None:
    """The defect the -0.5 support floor exists to patch cannot arise here.

    A discrete distribution on 0,1,2,... has an atom at zero, not a sliver of
    a bell curve reaching into negative counts. Ruch Chorzow's 2026-09-18 row
    claimed P(zero corners) = 0.1294 of which 82% was mass below zero.
    """
    centre, sd = 5.30, 4.25
    boundary = winning_boundary(0.5, "UNDER")
    nb = calc_p_central_nb_raw(centre, sd, boundary, "UNDER")
    unfloored = calc_p_central_raw(centre, sd, boundary, "UNDER", None)
    assert nb < unfloored
    assert nb == pytest.approx(nb_survival(centre, sd * sd, -1) - nb_survival(centre, sd * sd, 0), abs=1e-12)


def test_it_lowers_the_over_tail_where_the_lines_sit() -> None:
    """Less mass just above the centre, which is where posted lines sit.

    A low-mean count is the case that matters — goals in a half, a team's
    goals — and it is where the shipping model was most overstated
    (goals_1h_for +19.2 pp against its own sample on 2026-09-19).
    """
    mean, variance, n = 1.30, 1.90, 10
    sd = predictive_sd(variance, mean, n)
    for line in (1.5, 2.5):
        boundary = winning_boundary(line, "OVER")
        nb = calc_p_central_nb_raw(mean, sd, boundary, "OVER")
        normal = calc_p_central_raw(
            mean, sd, boundary, "OVER", support_floor_for("goals_1h_for")
        )
        assert nb < normal, f"line {line}: nb {nb:.4f} not below normal {normal:.4f}"


def test_it_keeps_a_fatter_far_tail_than_the_normal() -> None:
    """Skew is not a uniform discount, and must not be implemented as one.

    A right-skewed count has LESS mass just above the centre and MORE far out
    than a bell curve of the same width. Asserting "every OVER rung comes
    down" would pass for a model that simply shaded every OVER, which is a
    different and wrong thing.
    """
    mean, n = 0.70, 10
    sd = predictive_sd(mean * 1.45, mean, n)
    boundary = winning_boundary(4.5, "OVER")
    nb = calc_p_central_nb_raw(mean, sd, boundary, "OVER")
    normal = calc_p_central_raw(mean, sd, boundary, "OVER", support_floor_for("goals_for"))
    assert nb > normal


def test_the_bias_has_the_sign_the_replay_measured() -> None:
    """Near the centre, across a grid of low-mean counts, OVER comes down."""
    diffs = []
    for mean in (0.7, 1.1, 1.4, 2.2, 3.1):
        sd = predictive_sd(mean * 1.45, mean, 10)
        for line in (0.5, 1.5, 2.5):
            b = winning_boundary(line, "OVER")
            if abs((b - mean) / sd) > 1.5:
                continue  # far tail: tested above, and it goes the other way
            diffs.append(
                calc_p_central_nb_raw(mean, sd, b, "OVER")
                - calc_p_central_raw(mean, sd, b, "OVER", support_floor_for("goals_for"))
            )
    assert len(diffs) >= 10
    assert max(diffs) < 0.0, "every OVER rung near the centre should come down"
