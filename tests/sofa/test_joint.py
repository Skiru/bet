"""The bivariate machinery behind both-teams, comparative and handicap markets."""

import math

import pytest

from bet.sofa.joint import (
    bivariate_normal_cdf,
    build_joint,
    count_pmf,
    normal_cdf,
    normal_ppf,
    observed_correlation,
)


class TestNormalPrimitives:
    @pytest.mark.parametrize("p", [0.001, 0.01, 0.1, 0.5, 0.9, 0.99, 0.999])
    def test_ppf_inverts_cdf(self, p: float) -> None:
        assert normal_cdf(normal_ppf(p)) == pytest.approx(p, abs=1e-10)

    def test_bivariate_reduces_to_product_at_zero_correlation(self) -> None:
        assert bivariate_normal_cdf(0.3, -0.7, 0.0) == pytest.approx(
            normal_cdf(0.3) * normal_cdf(-0.7), abs=1e-12
        )

    def test_bivariate_is_comonotone_at_rho_one(self) -> None:
        assert bivariate_normal_cdf(0.3, -0.7, 1.0) == pytest.approx(
            min(normal_cdf(0.3), normal_cdf(-0.7))
        )

    def test_bivariate_matches_known_value(self) -> None:
        # Phi2(0, 0, rho) = 1/4 + arcsin(rho) / (2*pi), exactly.
        for rho in (-0.8, -0.3, 0.25, 0.75):
            expected = 0.25 + math.asin(rho) / (2.0 * math.pi)
            assert bivariate_normal_cdf(0.0, 0.0, rho) == pytest.approx(
                expected, abs=1e-9
            )


class TestCountMarginal:
    def test_poisson_branch_when_not_overdispersed(self) -> None:
        pmf = count_pmf(2.0, 1.5, 40)
        assert sum(pmf) == pytest.approx(1.0, abs=1e-9)
        assert pmf[0] == pytest.approx(math.exp(-2.0), rel=1e-6)

    def test_negative_binomial_branch_keeps_the_extra_spread(self) -> None:
        """A sample wider than Poisson must not be flattened onto one.

        Overdispersion is the normal case for corners and cards, and a Poisson
        fitted to the mean alone puts too little mass in both tails - which is
        exactly where these markets are priced.
        """
        poisson = count_pmf(2.0, 2.0, 60)
        overdispersed = count_pmf(2.0, 6.0, 60)
        assert sum(overdispersed) == pytest.approx(1.0, abs=1e-9)
        assert overdispersed[0] > poisson[0]
        assert sum(overdispersed[6:]) > sum(poisson[6:])

    def test_variance_is_reproduced(self) -> None:
        pmf = count_pmf(3.0, 7.0, 90)
        mean = sum(k * p for k, p in enumerate(pmf))
        var = sum((k - mean) ** 2 * p for k, p in enumerate(pmf))
        assert mean == pytest.approx(3.0, rel=1e-3)
        assert var == pytest.approx(7.0, rel=2e-2)


class TestJoint:
    def test_zero_correlation_is_the_product_of_marginals(self) -> None:
        joint = build_joint(5.0, 5.0, 4.0, 4.0, 0.0)
        pmf_a = count_pmf(5.0, 5.0, joint.kmax)
        pmf_b = count_pmf(4.0, 4.0, joint.kmax)
        expected = sum(pmf_a[4:]) * sum(pmf_b[4:])
        assert joint.p_both_at_least(4, 4) == pytest.approx(expected, abs=2e-3)

    def test_target_correlation_is_reproduced(self) -> None:
        """The copula parameter is solved, not used raw.

        A Gaussian copula on discrete margins attenuates correlation. Passing
        the measured value straight through as the latent parameter prices a
        weaker dependence than the one measured, and the attenuation is worst
        where the counts are smallest - the short-priced rungs.
        """
        for target in (-0.30, -0.145, 0.15, 0.30):
            joint = build_joint(5.2, 6.0, 4.9, 5.5, target)
            assert observed_correlation(joint) == pytest.approx(target, abs=5e-3)

    def test_negative_dependence_lowers_the_both_teams_probability(self) -> None:
        dependent = build_joint(5.2, 6.0, 4.9, 5.5, -0.145)
        independent = build_joint(5.2, 6.0, 4.9, 5.5, 0.0)
        assert dependent.p_both_at_least(4, 4) < independent.p_both_at_least(4, 4)

    def test_comparative_outcomes_are_a_partition(self) -> None:
        joint = build_joint(5.2, 6.0, 4.9, 5.5, -0.145)
        total = joint.p_a_greater() + joint.p_equal() + joint.p_b_greater()
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_handicap_at_half_a_goal_is_the_comparative(self) -> None:
        """P(A - B > -0.5) is P(A >= B), which must equal P(A>B) + P(A=B)."""
        joint = build_joint(5.2, 6.0, 4.9, 5.5, -0.145)
        assert joint.p_diff_greater(-0.5) == pytest.approx(
            joint.p_a_greater() + joint.p_equal(), abs=1e-9
        )

    def test_both_teams_probability_falls_as_the_line_rises(self) -> None:
        joint = build_joint(5.2, 6.0, 4.9, 5.5, -0.145)
        values = [joint.p_both_at_least(n, n) for n in range(0, 10)]
        assert values == sorted(values, reverse=True)

    def test_min_spread_is_narrower_than_the_sum_spread(self) -> None:
        """Regression: the both-teams ladder is on min(A, B), not on A + B.

        Scaling a disagreement by the sum's spread understates it by about a
        factor of two, which on 2026-09-18 let every rung of one corners
        ladder through the gate as VALUE at once.
        """
        joint = build_joint(6.1, 6.32, 7.56, 5.78, -0.145)
        _, min_sd = joint.min_moments()
        sum_sd = math.sqrt(6.32 + 5.78)
        assert min_sd < sum_sd / 1.5

    def test_min_moments_match_a_brute_force_sum(self) -> None:
        joint = build_joint(3.0, 4.0, 4.0, 5.0, -0.2)
        mean, sd = joint.min_moments()
        brute_mean = sum(
            joint.pmf[i][j] * min(i, j)
            for i in range(joint.kmax + 1)
            for j in range(joint.kmax + 1)
        )
        assert mean == pytest.approx(brute_mean, abs=1e-9)
        assert sd > 0.0

    def test_diff_mean_is_the_difference_of_means(self) -> None:
        joint = build_joint(6.0, 6.0, 4.0, 4.0, -0.145)
        diff_mean, _ = joint.diff_moments()
        assert diff_mean == pytest.approx(2.0, abs=0.05)


class TestLadderImpliedSpread:
    """The second moment of the market's ladder — the check nothing did.

    `ladder_centre` compares where the model and the market put the middle.
    A distribution with the right middle and the wrong width is mispriced at
    every rung simultaneously, and always in the direction that makes the bar
    easiest to clear, because a wider distribution overstates both tails.
    """

    def test_a_normal_ladder_recovers_its_own_sigma(self) -> None:
        import math

        from bet.sofa.engine import ladder_implied_sd
        from bet.sofa.joint import normal_cdf

        centre, sigma = 10.0, 3.0
        rungs = [
            (line, 1.0 - normal_cdf((line - centre) / sigma))
            for line in [x + 0.5 for x in range(2, 18)]
        ]
        recovered = ladder_implied_sd(rungs)
        assert recovered is not None
        assert recovered == pytest.approx(sigma, rel=0.05)
        assert not math.isnan(recovered)

    def test_a_ladder_that_never_reaches_a_quartile_returns_none(self) -> None:
        from bet.sofa.engine import ladder_implied_sd

        # Every rung is deep in one tail: no quartile is straddled, so the
        # spread is unmeasurable and must not be reported as agreement.
        assert ladder_implied_sd([(0.5, 0.99), (1.5, 0.98), (2.5, 0.97)]) is None

    def test_two_rungs_are_not_a_spread(self) -> None:
        from bet.sofa.engine import ladder_implied_sd

        assert ladder_implied_sd([(2.5, 0.8), (3.5, 0.2)]) is None

    def test_the_band_brackets_the_measured_spread_of_real_ladders(self) -> None:
        """Guard on the constants, so a later edit cannot quietly invert them.

        Measured over 314 ladders on 2026-09-18 the ratio ran p05=0.77 to
        p95=1.83; the band has to be wider than that or it stops being an
        outlier test and becomes a fit to one day.
        """
        from bet.sofa.engine import MAX_SPREAD_RATIO, MIN_SPREAD_RATIO

        assert MIN_SPREAD_RATIO < 0.77
        assert MAX_SPREAD_RATIO > 1.83
        assert MIN_SPREAD_RATIO * MAX_SPREAD_RATIO == pytest.approx(1.0, abs=0.1)
