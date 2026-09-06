"""The two count-model defects found by settling 283,147 sheet rows on 2026-09-06.

Both were invisible to every existing invariant test, and for the same reason:
they moved the OVER and the UNDER at a rung by equal and opposite amounts, so
the pair still summed to 1, the ladder stayed monotone, and ``bound <=
central`` still held. Only settling the rows against what happened could see
them.

The measurements quoted here come from replaying the eight slates in ``runs/``
through ``backtest_slate.rebuild`` and settling every row that had actuals.
"""
from __future__ import annotations

import statistics

import pytest

from bet.simple_stats.analyze import (
    MAX_COUNT_MODEL_PROBABILITY,
    _predictive_dispersion,
    _sample_dispersion,
    count_model_bound,
    count_model_central,
)


def test_the_next_observation_is_more_uncertain_than_the_sample_was():
    """``Var(X_new - mean_hat) = sigma^2 (1 + 1/n)``, not ``sigma^2``.

    ``count_model_central`` used the sample's own variance as the predictive
    variance for its whole existence, which treats an estimated mean as if it
    were the true one. The correction is largest exactly where the samples are
    smallest -- the per-team and per-player rows, median n=5, where realised
    spread ran 12-18% above what the sheet claimed.
    """
    values = [2.0, 4.0, 3.0, 2.0, 3.0]
    assert _predictive_dispersion(values) == pytest.approx(
        _sample_dispersion(values) * 1.2
    )
    # sqrt(1 + 1/5) = 1.0954, which is most of the measured 1.17x at n=5.
    ratio = (_predictive_dispersion(values) / _sample_dispersion(values)) ** 0.5
    assert ratio == pytest.approx(1.0954, abs=1e-4)


def test_the_correction_shrinks_as_the_sample_grows():
    """It must vanish for a large sample, or it is a fudge factor.

    The 12-observation football match totals measured a realised/claimed spread
    ratio of 0.98-1.01 and must barely move; the 5-observation per-team rows
    measured 1.12-1.18 and must.
    """
    small = [3.0] * 4 + [7.0]            # n=5,  sqrt(1 + 1/5)  = 1.0954
    large = [3.0] * 24 + [7.0]           # n=25, sqrt(1 + 1/25) = 1.0198
    small_ratio = (_predictive_dispersion(small) / _sample_dispersion(small)) ** 0.5
    large_ratio = (_predictive_dispersion(large) / _sample_dispersion(large)) ** 0.5
    assert small_ratio == pytest.approx(1.0954, abs=1e-4)
    assert large_ratio == pytest.approx(1.0198, abs=1e-4)
    assert small_ratio > large_ratio > 1.0
    # A 2% inflation at n=25 against a measured 0.98-1.01 at n=12 is inside the
    # noise of the measurement; a 10% one at n=5 against a measured 1.12-1.18
    # is not, which is the asymmetry the correction exists to produce.
    assert (small_ratio - 1.0) > 4 * (large_ratio - 1.0)


def test_a_single_observation_is_not_given_an_infinite_correction():
    """n=1 has no sample variance to inflate; the Poisson floor is all there is."""
    assert _predictive_dispersion([4.0]) == _sample_dispersion([4.0])


def test_predictive_spread_pushes_both_sides_of_a_rung_toward_a_coin_flip():
    """The tell that hid this bug: the correction is symmetric.

    Both sides move *toward* 0.5 and still sum to 1, which is why no invariant
    test could see the error and why the calibration curve had to.
    """
    values = [2.0, 4.0, 3.0, 2.0, 3.0]
    over = count_model_central(values, 4.5, "OVER")
    under = count_model_central(values, 4.5, "UNDER")
    assert over + under == pytest.approx(1.0)
    assert 0.5 < under < 1.0
    # Recomputed without the correction, the UNDER would be more confident.
    naive_spread = _sample_dispersion(values) ** 0.5
    corrected_spread = _predictive_dispersion(values) ** 0.5
    assert corrected_spread > naive_spread


def test_an_all_zero_sample_no_longer_claims_certainty():
    """A player with no recorded tackle in five matches is not a sure thing.

    ``spread <= 0`` returned a literal ``1.0``. 19,770 settled rows took that
    branch -- a footballer with no offside, assist or tackle in n matches -- and
    they realised **0.941**, flatly: 0.903 at n=1, 0.967 at n=10. The sample
    says the event is rare, which was known before we looked; it does not say
    it cannot happen.
    """
    zeros = [0.0] * 5
    assert _sample_dispersion(zeros) == 0.0
    assert count_model_central(zeros, 0.5, "UNDER") == MAX_COUNT_MODEL_PROBABILITY
    assert count_model_central(zeros, 0.5, "OVER") == pytest.approx(
        1.0 - MAX_COUNT_MODEL_PROBABILITY
    )


def test_the_ceiling_is_symmetric_so_a_rung_still_sums_to_one():
    """Floor and ceiling are mirrors, or the two sides of a rung stop summing to 1."""
    for values in ([0.0] * 5, [1.0] * 8, [20.0] * 6 + [21.0]):
        for line in (0.5, 5.5, 25.5):
            total = sum(count_model_central(values, line, d) for d in ("OVER", "UNDER"))
            assert total == pytest.approx(1.0)


def test_the_ceiling_binds_the_bound_too_so_it_never_exceeds_the_centre():
    """``count_model_bound <= count_model_central`` must hold by construction.

    Capping only the centre would break it on any row whose bound crossed the
    ceiling -- 15 rows of the frozen 2026-08-31 fixture do.
    """
    for values in ([0.0] * 6, [1.0] * 10, [8.0, 9.0, 8.0, 9.0, 8.0]):
        for line in (0.5, 4.5, 12.5):
            for direction in ("OVER", "UNDER"):
                assert (
                    count_model_bound(values, line, direction)
                    <= count_model_central(values, line, direction) + 1e-12
                )
                assert (
                    count_model_bound(values, line, direction)
                    <= MAX_COUNT_MODEL_PROBABILITY
                )


def test_the_ceiling_is_where_the_rows_past_it_actually_landed():
    """0.95 is not a round number picked for tidiness.

    Of the 42,857 settled rows claiming 0.95 or better, the realised rate was
    0.9500. If someone raises this constant, that measurement has to be redone
    -- it is the only thing holding it up.
    """
    assert MAX_COUNT_MODEL_PROBABILITY == 0.95
