"""Tests for the mandatory data gate in build_coupons().

Verifies:
- Candidates with safety_score=0.0 → build_coupons() returns []
- Candidates with real data (safety_score>0, hit_rate_l10>0) → returns coupons
- Mixed candidates: only real-data ones are used
"""

import pytest

from bet.config import BettingConfig
from bet.coupon.builder import build_coupons
from bet.db.models import Fixture, MarketCandidate, Team


@pytest.fixture
def config():
    """Minimal BettingConfig for testing."""
    return BettingConfig(
        bankroll_pln=50.0,
        daily_exposure_range=(5.0, 15.0),
        max_stake_pln=2.0,
        max_legs_per_coupon=3,
        min_coupons_per_day=3,
        preferred_odds_range=(1.30, 3.50),
        min_safety_score=0.60,
        timezone="Europe/Warsaw",
        sports=["football", "volleyball", "basketball", "hockey", "tennis", "snooker", "speedway"],
        db_path=":memory:",
    )


def _make_candidate(
    fixture_id: int,
    safety_score: float,
    hit_rate_l10: float,
    sport: str = "football",
    market: str = "Corners Total O/U",
    ev: float = 0.10,
) -> MarketCandidate:
    """Create a minimal MarketCandidate for testing."""
    fixture = Fixture(
        id=fixture_id,
        sport_id=1,
        competition_id=None,
        home_team_id=fixture_id * 2 - 1,
        away_team_id=fixture_id * 2,
        kickoff=f"2026-05-03T{14 + fixture_id}:00:00",
    )
    home = Team(id=fixture_id * 2 - 1, sport_id=1, name=f"Home Team {fixture_id}")
    away = Team(id=fixture_id * 2, sport_id=1, name=f"Away Team {fixture_id}")

    return MarketCandidate(
        fixture=fixture,
        home_team=home,
        away_team=away,
        sport_name=sport,
        competition_name="Test League",
        market_name=market,
        direction="OVER",
        line=9.5,
        safety_score=safety_score,
        hit_rate_l10=hit_rate_l10,
        hit_rate_h2h=0.7 if hit_rate_l10 > 0 else None,
        hit_rate_l5=hit_rate_l10,
        three_way_aligned=True,
        min_odds=1.25 if hit_rate_l10 > 0 else 0.0,
        best_odds=1.72 if hit_rate_l10 > 0 else None,
        ev=ev if safety_score > 0 else None,
        betclic_hit_rate=None,
    )


class TestDataGate:
    def test_all_zero_safety_returns_empty(self, config):
        """All candidates with safety_score=0.0 → build_coupons returns []."""
        candidates = [
            _make_candidate(i, safety_score=0.0, hit_rate_l10=0.0)
            for i in range(1, 6)
        ]
        result = build_coupons(candidates, config)
        assert result == []

    def test_all_zero_hit_rate_returns_empty(self, config):
        """All candidates with hit_rate_l10=0.0 → build_coupons returns []."""
        candidates = [
            _make_candidate(i, safety_score=0.65, hit_rate_l10=0.0)
            for i in range(1, 6)
        ]
        result = build_coupons(candidates, config)
        assert result == []

    def test_valid_candidates_produce_coupons(self, config):
        """Candidates with safety_score>0 and hit_rate>0 → returns coupons."""
        candidates = [
            _make_candidate(i, safety_score=0.65, hit_rate_l10=0.7, ev=0.10)
            for i in range(1, 6)
        ]
        result = build_coupons(candidates, config)
        assert len(result) > 0
        # Each coupon is a (Coupon, [Bet, ...]) tuple
        for coupon, bets in result:
            assert len(bets) >= 1
            assert len(bets) <= 3

    def test_mixed_candidates_only_real_data_used(self, config):
        """Mix of zero and real candidates — only real ones end up in coupons."""
        zero_candidates = [
            _make_candidate(i, safety_score=0.0, hit_rate_l10=0.0)
            for i in range(1, 4)
        ]
        real_candidates = [
            _make_candidate(i, safety_score=0.75, hit_rate_l10=0.8, ev=0.12)
            for i in range(4, 7)
        ]
        all_candidates = zero_candidates + real_candidates

        result = build_coupons(all_candidates, config)
        assert len(result) > 0

        # Verify no bet references a fixture from zero-data candidates (IDs 1-3)
        zero_fixture_ids = {1, 2, 3}
        for coupon, bets in result:
            for bet in bets:
                assert bet.fixture_id not in zero_fixture_ids

    def test_empty_candidates_returns_empty(self, config):
        """No candidates → returns []."""
        result = build_coupons([], config)
        assert result == []
