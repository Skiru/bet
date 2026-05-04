"""Tests for safety score computation and odds utilities."""

import pytest

from bet.stats.safety_scores import (
    compute_hit_rate,
    compute_safety_score,
    infer_direction,
)
from bet.utils.odds import (
    american_to_decimal,
    expected_value,
    kelly_fraction,
    min_acceptable_odds,
)


# ---------------------------------------------------------------------------
# Safety score computation
# ---------------------------------------------------------------------------


def test_safety_score_corners_example():
    """Known input → known output for corners safety score.

    L10 corners: [6, 7, 8, 9, 6, 7, 8, 9, 6, 7] → avg 7.3
    H2H corners: [7, 8, 9, 6, 7] → avg 7.4
    L5  corners: [6, 7, 8, 9, 6] → avg 7.2
    Line: 5.5, Direction: OVER

    L10 hits: 10/10 = 1.0 (all > 5.5)
    H2H hits: 5/5 = 1.0
    L5  hits: 5/5 = 1.0
    Safety = min(1.0, 1.0) = 1.0
    """
    l10 = [6.0, 7.0, 8.0, 9.0, 6.0, 7.0, 8.0, 9.0, 6.0, 7.0]
    h2h = [7.0, 8.0, 9.0, 6.0, 7.0]
    l5 = [6.0, 7.0, 8.0, 9.0, 6.0]

    result = compute_safety_score(l10, h2h, l5, line=5.5, direction="OVER")
    assert result["hit_rate_l10"] == 1.0
    assert result["hit_rate_h2h"] == 1.0
    assert result["hit_rate_l5"] == 1.0
    assert result["safety_score"] == 1.0
    assert result["direction"] == "OVER"


def test_three_way_alignment():
    """Three-way alignment: all aligned → True, mismatch → False."""
    # All support OVER (averages above line)
    l10 = [10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0]
    h2h = [10.0, 11.0, 12.0]
    l5 = [10.0, 11.0, 12.0, 10.0, 11.0]
    result = compute_safety_score(l10, h2h, l5, line=9.5)
    assert result["three_way_aligned"] is True

    # L5 trend drops below line → not aligned
    l5_low = [8.0, 7.0, 8.0, 7.0, 8.0]  # avg 7.6 < 9.5
    result2 = compute_safety_score(l10, h2h, l5_low, line=9.5)
    assert result2["three_way_aligned"] is False


def test_safety_score_no_h2h():
    """Without H2H data, safety = L10 * 0.7."""
    l10 = [10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0]
    l5 = [10.0, 11.0, 12.0, 10.0, 11.0]

    result = compute_safety_score(l10, None, l5, line=9.5, direction="OVER")
    # All 10 values > 9.5 → hit_rate_l10 = 1.0
    # safety = 1.0 * 0.7 = 0.70
    assert result["hit_rate_l10"] == 1.0
    assert result["hit_rate_h2h"] is None
    assert result["safety_score"] == 0.70


# ---------------------------------------------------------------------------
# Odds utilities
# ---------------------------------------------------------------------------


def test_ev_calculation():
    """EV = (probability * odds) - 1."""
    # 80% chance at 1.35 odds → EV = 0.80 * 1.35 - 1 = 0.08
    ev = expected_value(0.80, 1.35)
    assert round(ev, 2) == 0.08

    # 50% chance at 1.80 → EV = 0.50 * 1.80 - 1 = -0.10
    ev_neg = expected_value(0.50, 1.80)
    assert round(ev_neg, 2) == -0.10


def test_kelly_negative_ev_returns_zero():
    """Kelly fraction must be 0 when EV is non-positive."""
    # 40% chance at 2.0 → edge = 0.4*1.0 - 0.6 = -0.20 → 0
    k = kelly_fraction(0.40, 2.0)
    assert k == 0.0

    # Edge case: probability=0
    k2 = kelly_fraction(0.0, 2.0)
    assert k2 == 0.0


def test_american_conversion():
    """American ↔ decimal conversion: +150→2.50, -200→1.50."""
    assert american_to_decimal("+150") == 2.5
    assert american_to_decimal("-200") == 1.5
    assert american_to_decimal("+100") == 2.0
    assert american_to_decimal("-100") == 2.0


def test_min_acceptable_odds():
    """Minimum odds for positive EV = 1 / hit_rate."""
    assert min_acceptable_odds(0.80) == 1.25
    assert min_acceptable_odds(0.50) == 2.0
    # Edge: zero hit rate → infinity
    assert min_acceptable_odds(0.0) == float("inf")
