"""F42 — K_CENTRE must not be published as measured when it is not.

`_pick_plateau_k` accepted every K within PLATEAU_TOLERANCE of the best and
returned the *smallest*, which is the most sample-trusting value on the grid
and the opposite of what its own docstring argued for. Once the F41 support
floor flattened the error curve, the tolerance band covered the entire grid —
K=0 ("ignore the prior") and K=1000 ("ignore the sample") were both inside it
— and the script published K_CENTRE = 0.0 as FITTED, on a curve whose minimum
sat at 5.0.
"""

from __future__ import annotations

import importlib

import pytest

fit_constants = importlib.import_module("scripts.sofa.fit_constants")
_pick_plateau_k = fit_constants._pick_plateau_k
PLATEAU_TOLERANCE = fit_constants.PLATEAU_TOLERANCE


def test_an_empty_curve_is_not_a_fit() -> None:
    assert _pick_plateau_k({}) is None


def test_a_curve_flat_across_the_whole_grid_is_not_a_fit() -> None:
    """The live failure: the band swallows the grid, so nothing is measured."""
    curve = {
        0.0: 0.252810,
        2.0: 0.252394,
        5.0: 0.251653,
        8.0: 0.251673,
        10.0: 0.251868,
        15.0: 0.252635,
        25.0: 0.253234,
        1000.0: 0.253636,
    }
    assert max(curve.values()) - min(curve.values()) < PLATEAU_TOLERANCE
    assert _pick_plateau_k(curve) is None


def test_the_conservative_end_of_a_real_plateau_wins() -> None:
    """Among values the data cannot tell apart, shrink more, not less."""
    curve = {0.0: 0.30, 2.0: 0.2605, 5.0: 0.2600, 8.0: 0.2610, 25.0: 0.40}
    # 2.0, 5.0 and 8.0 are within tolerance of the best; 8.0 trusts the
    # sample least of the three.
    assert _pick_plateau_k(curve) == 8.0


def test_a_lone_minimum_is_returned_unchanged() -> None:
    curve = {0.0: 0.40, 5.0: 0.20, 10.0: 0.40}
    assert _pick_plateau_k(curve) == 5.0


def test_the_rule_never_returns_a_k_outside_the_curve() -> None:
    curve = {0.0: 0.31, 5.0: 0.30, 8.0: 0.3005, 1000.0: 0.45}
    picked = _pick_plateau_k(curve)
    assert picked in curve


@pytest.mark.parametrize("k_worst", [0.0, 1000.0])
def test_an_extreme_grid_end_is_never_picked_when_it_is_measurably_worse(
    k_worst: float,
) -> None:
    curve = {0.0: 0.30, 5.0: 0.30, 1000.0: 0.30}
    curve[k_worst] = 0.50
    assert _pick_plateau_k(curve) != k_worst


# --------------------------------------------------------------------------
# F44 — the criterion must be a proper scoring rule, and the sentinel must
# never be the answer.
# --------------------------------------------------------------------------

IGNORE_SAMPLE_K = fit_constants.IGNORE_SAMPLE_K
BRIER_PLATEAU_TOLERANCE = fit_constants.BRIER_PLATEAU_TOLERANCE


def test_the_ignore_the_sample_sentinel_is_never_selected() -> None:
    """K=1000 means "the sample is worthless". Shipping it switches off
    every stage that produces a sample."""
    curve = {0.0: 0.30, 8.0: 0.19030, 25.0: 0.19020, IGNORE_SAMPLE_K: 0.19000}
    picked = _pick_plateau_k(curve, BRIER_PLATEAU_TOLERANCE)
    assert picked != IGNORE_SAMPLE_K
    assert picked == 25.0


def test_a_curve_only_the_sentinel_can_win_is_not_a_fit() -> None:
    curve = {0.0: 0.50, 8.0: 0.50, IGNORE_SAMPLE_K: 0.20}
    assert _pick_plateau_k(curve, BRIER_PLATEAU_TOLERANCE) is None


def test_the_measured_brier_curve_picks_its_interior_optimum() -> None:
    """The real 2026-09-18 curve, 516,900 settled rows."""
    curve = {
        0.0: 0.169679,
        2.0: 0.167159,
        5.0: 0.165352,
        8.0: 0.164559,
        10.0: 0.164286,
        15.0: 0.163994,
        25.0: 0.163936,
        IGNORE_SAMPLE_K: 0.164953,
    }
    assert min(curve, key=lambda k: curve[k]) == 25.0
    assert _pick_plateau_k(curve, BRIER_PLATEAU_TOLERANCE) == 25.0


def test_the_brier_tolerance_is_tighter_than_the_absolute_error_one() -> None:
    """Brier differences are an order of magnitude smaller; one band for both
    scales is how the sentinel got onto the plateau."""
    assert BRIER_PLATEAU_TOLERANCE < PLATEAU_TOLERANCE


def test_fit_k_centre_scores_with_a_proper_rule_not_a_median() -> None:
    """Median |p - outcome| is minimised by throwing the sample away.

    Pinned at the source level because the failure is invisible in the output:
    the fit reported FITTED with a number, and the number was "ignore the
    sample".
    """
    import inspect

    # The scoring lives in _k_centre_curve, which both the pooled fit and the
    # per-sport fit call (F46). Checking fit_k_centre alone would pass while
    # the curve it delegates to went back to a median.
    source = inspect.getsource(fit_constants._k_centre_curve)
    assert "statistics.mean(errors)" in source
    assert "statistics.median(errors)" not in source
    assert "** 2" in source

    for fn in (fit_constants.fit_k_centre, fit_constants.fit_k_centre_by_sport):
        assert "_k_centre_curve" in inspect.getsource(fn), fn.__name__
