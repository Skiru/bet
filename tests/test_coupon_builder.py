"""Tests for the coupon builder module."""

import pytest

from bet.coupon.builder import MAX_LEGS, build_coupons


# ---------------------------------------------------------------------------
# Coupon constraint tests
# ---------------------------------------------------------------------------


def test_max_3_legs_enforced(sample_candidates, config):
    """No coupon exceeds 3 legs."""
    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    for coupon, bets in coupons:
        assert len(bets) <= MAX_LEGS, (
            f"Coupon {coupon.coupon_id} has {len(bets)} legs (max {MAX_LEGS})"
        )


def test_no_same_fixture_in_coupon(sample_candidates, config):
    """Each coupon has legs from different events (fixture IDs)."""
    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    for coupon, bets in coupons:
        fixture_ids = [b.fixture_id for b in bets]
        assert len(fixture_ids) == len(set(fixture_ids)), (
            f"Coupon {coupon.coupon_id} has duplicate fixture IDs: {fixture_ids}"
        )


def test_sport_diversity(sample_candidates, config):
    """Max 2 legs from the same sport in a single coupon."""
    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    for coupon, bets in coupons:
        sport_counts: dict[str, int] = {}
        for bet in bets:
            sport_counts[bet.sport] = sport_counts.get(bet.sport, 0) + 1
        for sport, count in sport_counts.items():
            assert count <= 2, (
                f"Coupon {coupon.coupon_id} has {count} legs for {sport} (max 2)"
            )


def test_flat_staking(sample_candidates, config):
    """Each coupon's stake equals config.max_stake_pln."""
    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    for coupon, _ in coupons:
        assert coupon.stake_pln == config.max_stake_pln


def test_coupon_id_format(sample_candidates, config):
    """Coupon IDs match AKO-YYYY-MM-DD-NNN."""
    import re

    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    pattern = re.compile(r"^AKO-\d{4}-\d{2}-\d{2}-\d{3}$")
    for coupon, _ in coupons:
        assert pattern.match(coupon.coupon_id), (
            f"Coupon ID '{coupon.coupon_id}' does not match AKO-YYYY-MM-DD-NNN"
        )


def test_daily_exposure_limit(sample_candidates, config):
    """Total stake across all coupons ≤ exposure cap."""
    coupons = build_coupons(sample_candidates, config, max_coupons=10)
    total_stake = sum(c.stake_pln or 0 for c, _ in coupons)
    assert total_stake <= config.daily_exposure_range[1], (
        f"Total stake {total_stake} exceeds cap {config.daily_exposure_range[1]}"
    )


def test_empty_candidates_returns_no_coupons(config):
    """No candidates → no coupons."""
    coupons = build_coupons([], config)
    assert coupons == []
