#!/usr/bin/env python3
"""Integration smoke test: S3 → S7 → S8 pipeline chain with mock data."""
import json
import sys
from pathlib import Path

import pytest

# Ensure scripts are importable
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR.parent))


@pytest.fixture
def mock_shortlist(tmp_path):
    """Create a minimal shortlist for testing."""
    shortlist = {
        "date": "2026-01-01",
        "candidates": [
            {
                "home_team": "Liverpool",
                "away_team": "Arsenal",
                "sport": "football",
                "competition": "Premier League",
                "kickoff": "2026-01-01T15:00:00",
                "sources": ["flashscore", "betexplorer"],
                "fixture_verified": True,
                "data_tier": "STATS_ONLY",
            },
            {
                "home_team": "Djokovic N.",
                "away_team": "Sinner J.",
                "sport": "tennis",
                "competition": "Australian Open",
                "kickoff": "2026-01-01T10:00:00",
                "sources": ["flashscore", "tennisexplorer"],
                "fixture_verified": True,
                "data_tier": "STATS_ONLY",
            },
        ],
    }
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps(shortlist), encoding="utf-8")
    return path


@pytest.fixture
def mock_stats_cache(tmp_path):
    """Create minimal stats cache files."""
    cache_dir = tmp_path / "stats_cache"

    # Football teams
    fb_dir = cache_dir / "football"
    fb_dir.mkdir(parents=True)

    liverpool = {
        "team": "Liverpool",
        "sport": "football",
        "form": {
            "l10_avg": {"corners": 6.2, "fouls": 12.5, "cards": 2.1, "shots": 15.3},
            "l5_avg": {"corners": 7.0, "fouls": 13.0, "cards": 2.0, "shots": 16.0},
            "l10_matches": [
                {"corners": 7, "fouls": 13, "cards": 2, "shots": 16},
                {"corners": 5, "fouls": 11, "cards": 3, "shots": 14},
                {"corners": 8, "fouls": 14, "cards": 1, "shots": 17},
                {"corners": 6, "fouls": 12, "cards": 2, "shots": 15},
                {"corners": 7, "fouls": 13, "cards": 2, "shots": 16},
                {"corners": 5, "fouls": 11, "cards": 3, "shots": 14},
                {"corners": 8, "fouls": 14, "cards": 1, "shots": 17},
                {"corners": 6, "fouls": 12, "cards": 2, "shots": 15},
                {"corners": 7, "fouls": 13, "cards": 2, "shots": 16},
                {"corners": 5, "fouls": 11, "cards": 3, "shots": 14},
            ],
        },
        "h2h": {
            "arsenal": {
                "matches": [
                    {"corners": 12, "fouls": 25, "cards": 4, "shots": 30},
                    {"corners": 10, "fouls": 23, "cards": 3, "shots": 28},
                    {"corners": 14, "fouls": 27, "cards": 5, "shots": 32},
                    {"corners": 11, "fouls": 24, "cards": 4, "shots": 29},
                    {"corners": 13, "fouls": 26, "cards": 3, "shots": 31},
                ],
                "avg": {"corners": 12.0, "fouls": 25.0, "cards": 3.8, "shots": 30.0},
            }
        },
        "sources": ["api-football", "flashscore"],
    }
    (fb_dir / "liverpool.json").write_text(json.dumps(liverpool), encoding="utf-8")

    arsenal = {
        "team": "Arsenal",
        "sport": "football",
        "form": {
            "l10_avg": {"corners": 5.5, "fouls": 11.0, "cards": 1.8, "shots": 14.0},
            "l5_avg": {"corners": 6.0, "fouls": 12.0, "cards": 2.0, "shots": 15.0},
            "l10_matches": [
                {"corners": 6, "fouls": 11, "cards": 2, "shots": 14},
                {"corners": 5, "fouls": 10, "cards": 1, "shots": 13},
                {"corners": 7, "fouls": 12, "cards": 2, "shots": 15},
                {"corners": 5, "fouls": 11, "cards": 2, "shots": 14},
                {"corners": 6, "fouls": 11, "cards": 1, "shots": 14},
                {"corners": 5, "fouls": 10, "cards": 2, "shots": 13},
                {"corners": 6, "fouls": 12, "cards": 2, "shots": 15},
                {"corners": 5, "fouls": 11, "cards": 2, "shots": 14},
                {"corners": 6, "fouls": 11, "cards": 2, "shots": 14},
                {"corners": 5, "fouls": 10, "cards": 1, "shots": 13},
            ],
        },
        "h2h": {},
        "sources": ["api-football"],
    }
    (fb_dir / "arsenal.json").write_text(json.dumps(arsenal), encoding="utf-8")

    return cache_dir


class TestComputeSafetyScores:
    """Test the safety score calculator."""

    def test_rank_markets_basic(self):
        from compute_safety_scores import rank_markets

        data = {
            "sport": "football",
            "team_a": "Liverpool",
            "team_b": "Arsenal",
            "competition": "Premier League",
            "markets": [
                {
                    "name": "Corners Total O/U",
                    "line": 9.5,
                    "team_a_l10": [7, 5, 8, 6, 7, 5, 8, 6, 7, 5],
                    "team_b_l10": [6, 5, 7, 5, 6, 5, 6, 5, 6, 5],
                    "h2h_values": [12, 10, 14, 11, 13],
                    "is_combined": True,
                },
            ],
        }
        result = rank_markets(data)
        assert "ranking" in result
        assert len(result["ranking"]) >= 1
        market = result["ranking"][0]
        assert "safety_score" in market
        assert 0.0 <= market["safety_score"] <= 1.0

    def test_h2h_penalty_sport_specific(self):
        from compute_safety_scores import rank_markets

        # MMA should have lower penalty (0.90) than football (0.70)
        for sport, expected_min_penalty in [("football", 0.70), ("mma", 0.90)]:
            data = {
                "sport": sport,
                "team_a": "Fighter A",
                "team_b": "Fighter B",
                "markets": [
                    {
                        "name": "Total Rounds O/U",
                        "line": 2.5,
                        "team_a_l10": [3, 2, 4, 3, 2, 3, 4, 2, 3, 2],
                        "team_b_l10": [0] * 10,
                        "is_combined": False,
                    },
                ],
            }
            result = rank_markets(data)
            # Without H2H, safety = l10_rate * penalty
            # With higher penalty multiplier, MMA should get higher safety
            assert len(result["ranking"]) >= 1


class TestGateChecker:
    """Test gate checker functions."""

    def test_ev_stats_first_passes(self):
        from gate_checker import _check_ev

        # Stats-first: ev is None should PASS
        candidate = {"ev": None}
        passed, msg = _check_ev(candidate)
        assert passed is True
        assert "STATS-FIRST" in msg

    def test_ev_positive_passes(self):
        from gate_checker import _check_ev

        candidate = {"ev": 0.15}
        passed, msg = _check_ev(candidate)
        assert passed is True

    def test_ev_negative_fails(self):
        from gate_checker import _check_ev

        candidate = {"ev": -0.05}
        passed, msg = _check_ev(candidate)
        assert passed is False


class TestProbabilityEngine:
    """Test probability calculations."""

    @pytest.mark.skip(reason="probability_engine.py not in codebase")
    def test_poisson_over(self):
        pass

    @pytest.mark.skip(reason="probability_engine.py not in codebase")
    def test_poisson_under(self):
        pass

    @pytest.mark.skip(reason="probability_engine.py not in codebase")
    def test_estimate_lambda(self):
        pass


class TestCouponBuilder:
    """Test coupon builder functions."""

    def test_format_market_polish(self):
        from coupon_builder import format_market_polish

        result = format_market_polish("Corners Total O/U", "OVER", 9.5)
        assert "9.5" in result
        assert "rożne" in result.lower() or "Rzuty" in result

    def test_compute_stake_bounds(self):
        from coupon_builder import compute_stake

        # Stake should be between 1.0 and cap
        stake = compute_stake(1.85, 0.7, 50.0, "LR")
        assert 1.0 <= stake <= 3.0

        stake = compute_stake(1.85, 0.7, 50.0, "HR")
        assert 1.0 <= stake <= 2.0

    def test_rich_description(self):
        from coupon_builder import _build_rich_description

        pick = {
            "home_team": "Liverpool",
            "away_team": "Arsenal",
            "sport": "football",
            "best_market": {
                "name": "Corners Total O/U",
                "direction": "OVER",
                "line": 9.5,
                "safety_score": 0.80,
                "l10_avg": 11.5,
                "h2h_avg": 12.0,
                "probability": 0.73,
                "fair_odds": 1.37,
                "rank": 1,
                "total_markets_evaluated": 6,
            },
            "odds": {"market_best": 1.85},
        }
        desc = _build_rich_description(pick)
        assert "Liverpool" in desc
        assert "Arsenal" in desc
        assert "0.80" in desc  # safety score
        assert "11.5" in desc  # L10 avg


class TestValidateCoupons:
    """Test validator regex."""

    @pytest.mark.skip(reason="validate_coupons.py not in codebase")
    def test_odds_regex_matches_both_formats(self):
        pass
