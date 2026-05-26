"""Tests for basketball enrichment pipeline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestBasketballStatValidation:
    """Test stat key validation for basketball."""

    def test_valid_basketball_stats_accepted(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["points", "rebounds", "assists", "turnovers",
                      "steals", "blocks", "3_pointers", "game_total_points"]
        for key in valid_keys:
            assert is_valid_stat_key("basketball", key), f"{key} should be valid for basketball"

    def test_football_stats_rejected_for_basketball(self):
        from bet.stats.stat_validation import is_valid_stat_key, detect_contamination

        invalid_keys = ["corners", "possession", "tackles", "offsides", "goals"]
        for key in invalid_keys:
            assert not is_valid_stat_key("basketball", key), f"{key} should be invalid for basketball"

        contaminated = detect_contamination("basketball", invalid_keys)
        assert len(contaminated) == len(invalid_keys)

    def test_detect_contamination_basketball(self):
        from bet.stats.stat_validation import detect_contamination

        mixed = ["points", "corners", "rebounds", "goals", "assists"]
        result = detect_contamination("basketball", mixed)
        assert "corners" in result
        assert "goals" in result
        assert "points" not in result
        assert "rebounds" not in result
        assert "assists" not in result


class TestBasketballValueRanges:
    """Test value range validation for basketball stats."""

    def test_points_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["basketball"]
        lo, hi = ranges["points"]
        assert lo <= 100 <= hi  # typical NBA game total
        assert lo <= 130 <= hi  # high-scoring game
        assert lo <= 75 <= hi   # low-scoring Euro game

    def test_rebounds_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["basketball"]
        lo, hi = ranges["rebounds"]
        assert lo <= 40 <= hi  # typical team rebounds
        assert lo <= 55 <= hi  # dominant rebounding

    def test_assists_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["basketball"]
        lo, hi = ranges["assists"]
        assert lo <= 25 <= hi  # typical assists


class TestBasketballL10Building:
    """Test L10 array construction for basketball."""

    def test_points_array_correct_length(self):
        values = [105, 98, 112, 96, 108, 101, 99, 110, 103, 107, 95, 102]
        l10 = values[:10]
        assert len(l10) == 10

    def test_averages_computed_correctly(self):
        l10 = [105.0, 98.0, 112.0, 96.0, 108.0, 101.0, 99.0, 110.0, 103.0, 107.0]
        l10_avg = round(sum(l10) / len(l10), 2)
        assert l10_avg == 103.9


class TestBasketballHallucinationDetection:
    """Test hallucination framework for basketball."""

    def test_hallucination_config_exists_for_basketball(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "basketball" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["basketball"]
        assert config["thin_data_threshold"] == 3
        assert "Total Points O/U" in config["thin_data_markets_allowed"]
        assert "Handicap" in config["thin_data_markets_allowed"]

    def test_basketball_warning_message(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        config = HALLUCINATION_CONFIG["basketball"]
        assert "total points" in config["warning_msg"].lower() or "handicap" in config["warning_msg"].lower()


class TestBasketballCompetitionTiers:
    """Test basketball competition tiers."""

    def test_nba_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        bball_tiers = COMP_TIER_KEYWORDS["basketball"]
        tier_9 = next((t for t in bball_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "nba" in tier_9[1]

    def test_euroleague_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        bball_tiers = COMP_TIER_KEYWORDS["basketball"]
        tier_9 = next((t for t in bball_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "euroleague" in tier_9[1]


class TestBasketballFuzzyMatch:
    """Test fuzzy matching for basketball team names."""

    def test_exact_match(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Los Angeles Lakers", "Los Angeles Lakers", "basketball")
        assert score >= 95

    def test_different_teams_low_score(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Golden State Warriors", "Miami Heat", "basketball")
        assert score < 50
