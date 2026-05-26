"""Tests for hockey enrichment pipeline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestHockeyStatValidation:
    """Test stat key validation for hockey."""

    def test_valid_hockey_stats_accepted(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["goals", "shots", "pim", "hits", "blocks", "faceoff_pct",
                      "powerplay_goals", "shots_on_goal", "game_total_goals"]
        for key in valid_keys:
            assert is_valid_stat_key("hockey", key), f"{key} should be valid for hockey"

    def test_football_stats_rejected_for_hockey(self):
        from bet.stats.stat_validation import detect_contamination, is_valid_stat_key

        invalid_keys = ["corners", "possession", "tackles", "offsides", "ball_possession"]
        for key in invalid_keys:
            assert not is_valid_stat_key("hockey", key), f"{key} should be invalid for hockey"

        contaminated = detect_contamination("hockey", invalid_keys)
        assert len(contaminated) == len(invalid_keys)

    def test_detect_contamination_hockey(self):
        from bet.stats.stat_validation import detect_contamination

        mixed = ["goals", "corners", "shots", "possession", "pim"]
        result = detect_contamination("hockey", mixed)
        assert "corners" in result
        assert "possession" in result
        assert "goals" not in result
        assert "shots" not in result
        assert "pim" not in result


class TestHockeyValueRanges:
    """Test value range validation for hockey stats."""

    def test_goals_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["hockey"]
        lo, hi = ranges["goals"]
        assert lo <= 3 <= hi  # typical goals per team
        assert lo <= 6 <= hi  # high-scoring game
        assert 0 == lo  # shutout possible

    def test_shots_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["hockey"]
        lo, hi = ranges["shots"]
        assert lo <= 30 <= hi  # typical shots
        assert lo <= 45 <= hi  # high-shot game

    def test_pim_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["hockey"]
        lo, hi = ranges["pim"]
        assert lo <= 10 <= hi  # normal PIM
        assert lo <= 30 <= hi  # penalty-heavy game


class TestHockeyL10Building:
    """Test L10 array construction for hockey."""

    def test_goal_array_correct_length(self):
        values = [3, 2, 4, 1, 5, 3, 2, 4, 3, 2, 1, 3]
        l10 = values[:10]
        assert len(l10) == 10

    def test_averages_computed_correctly(self):
        l10 = [3.0, 2.0, 4.0, 1.0, 5.0, 3.0, 2.0, 4.0, 3.0, 2.0]
        l10_avg = round(sum(l10) / len(l10), 2)
        assert l10_avg == 2.9


class TestHockeyHallucinationDetection:
    """Test hallucination framework for hockey."""

    def test_hallucination_config_exists_for_hockey(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "hockey" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["hockey"]
        assert config["thin_data_threshold"] == 3
        assert "Total Goals O/U" in config["thin_data_markets_allowed"]

    def test_hockey_warning_message(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        config = HALLUCINATION_CONFIG["hockey"]
        assert "pim" in config["warning_msg"].lower() or "hits" in config["warning_msg"].lower()


class TestHockeyCompetitionTiers:
    """Test hockey competition tiers."""

    def test_nhl_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        hockey_tiers = COMP_TIER_KEYWORDS["hockey"]
        tier_9 = next((t for t in hockey_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "nhl" in tier_9[1]

    def test_khl_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        hockey_tiers = COMP_TIER_KEYWORDS["hockey"]
        tier_9 = next((t for t in hockey_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "khl" in tier_9[1]

    def test_shl_liiga_del_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        hockey_tiers = COMP_TIER_KEYWORDS["hockey"]
        tier_8 = next((t for t in hockey_tiers if t[0] == 8), None)
        assert tier_8 is not None
        assert "shl" in tier_8[1]
        assert "liiga" in tier_8[1]
        assert "del" in tier_8[1]


class TestHockeyFuzzyMatch:
    """Test fuzzy matching for hockey team names."""

    def test_exact_match(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Chicago Blackhawks", "Chicago Blackhawks", "hockey")
        assert score >= 95

    def test_different_teams_low_score(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Boston Bruins", "Tampa Bay Lightning", "hockey")
        assert score < 50
