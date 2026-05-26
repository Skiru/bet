"""Tests for esports enrichment pipeline (CS2, Valorant, Dota2)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestEsportsStatValidation:
    """Test stat key validation for esports."""

    def test_valid_cs2_stats(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["kills", "deaths", "kd_ratio", "rating_2_0",
                      "maps_played", "maps_won", "map_win_rate", "rounds_won_avg"]
        for key in valid_keys:
            assert is_valid_stat_key("cs2", key), f"{key} should be valid for cs2"

    def test_valid_valorant_stats(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["maps_played", "maps_won", "map_win_rate",
                      "win_rate_l10", "rounds_won_avg", "acs_avg", "kd_ratio"]
        for key in valid_keys:
            assert is_valid_stat_key("valorant", key), f"{key} should be valid for valorant"

    def test_valid_dota2_stats(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["kills_avg", "deaths_avg", "win_rate_l10",
                      "duration_avg_min", "hero_pool_size", "first_blood_rate"]
        for key in valid_keys:
            assert is_valid_stat_key("dota2", key), f"{key} should be valid for dota2"

    def test_football_stats_rejected_for_cs2(self):
        from bet.stats.stat_validation import detect_contamination

        invalid = ["corners", "possession", "tackles", "offsides", "goals"]
        result = detect_contamination("cs2", invalid)
        assert len(result) == len(invalid)

    def test_football_stats_rejected_for_valorant(self):
        from bet.stats.stat_validation import detect_contamination

        invalid = ["corners", "possession", "shots_on_target"]
        result = detect_contamination("valorant", invalid)
        assert len(result) == len(invalid)


class TestEsportsValueRanges:
    """Test value range validation for esports stats."""

    def test_cs2_rounds_avg_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["cs2"]
        lo, hi = ranges["rounds_won_avg"]
        assert lo <= 13 <= hi  # standard avg

    def test_valorant_rounds_avg_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["valorant"]
        lo, hi = ranges["rounds_won_avg"]
        assert lo <= 13 <= hi

    def test_dota2_duration_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["dota2"]
        lo, hi = ranges["duration_avg_min"]
        assert lo <= 35 <= hi  # typical Dota game ~35 min
        assert lo <= 60 <= hi  # long game


class TestEsportsHallucinationDetection:
    """Test hallucination framework for esports."""

    def test_cs2_config(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "cs2" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["cs2"]
        assert config["thin_data_threshold"] == 3
        assert "Match Winner" in config["thin_data_markets_allowed"]

    def test_valorant_config(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "valorant" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["valorant"]
        assert "Match Winner" in config["thin_data_markets_allowed"]

    def test_dota2_config(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "dota2" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["dota2"]
        assert "Match Winner" in config["thin_data_markets_allowed"]


class TestEsportsCompetitionTiers:
    """Test esports competition tiers in build_shortlist."""

    def test_cs2_blast_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        cs2_tiers = COMP_TIER_KEYWORDS["cs2"]
        tier_9 = next((t for t in cs2_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "blast" in tier_9[1]

    def test_cs2_major_in_top_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        cs2_tiers = COMP_TIER_KEYWORDS["cs2"]
        tier_10 = next((t for t in cs2_tiers if t[0] == 10), None)
        assert tier_10 is not None
        assert "major" in tier_10[1]

    def test_dota2_tier_exists(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        assert "dota2" in COMP_TIER_KEYWORDS
        dota_tiers = COMP_TIER_KEYWORDS["dota2"]
        assert len(dota_tiers) > 0


class TestEsportsFuzzyMatch:
    """Test fuzzy matching thresholds for esports."""

    def test_cs2_threshold_strict(self):
        from bet.fuzzy_match import SPORT_THRESHOLDS

        assert SPORT_THRESHOLDS["cs2"] == 85

    def test_valorant_threshold_strict(self):
        from bet.fuzzy_match import SPORT_THRESHOLDS

        assert SPORT_THRESHOLDS["valorant"] == 85

    def test_dota2_threshold_strict(self):
        from bet.fuzzy_match import SPORT_THRESHOLDS

        assert SPORT_THRESHOLDS["dota2"] == 85

    def test_exact_team_match(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Team Vitality", "Team Vitality", "cs2")
        assert score >= 95
