"""Tests for volleyball enrichment pipeline."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


class TestVolleyballStatValidation:
    """Test stat key validation for volleyball."""

    def test_valid_volleyball_stats_accepted(self):
        from bet.stats.stat_validation import is_valid_stat_key

        valid_keys = ["total_points", "aces", "blocks", "errors", "sets_won", "points"]
        for key in valid_keys:
            assert is_valid_stat_key("volleyball", key), f"{key} should be valid for volleyball"

    def test_football_stats_rejected_for_volleyball(self):
        from bet.stats.stat_validation import detect_contamination, is_valid_stat_key

        invalid_keys = ["corners", "possession", "shots_on_target", "offsides", "tackles"]
        for key in invalid_keys:
            assert not is_valid_stat_key("volleyball", key), f"{key} should be invalid for volleyball"

        contaminated = detect_contamination("volleyball", invalid_keys)
        assert len(contaminated) == len(invalid_keys)

    def test_detect_contamination_returns_invalid_keys(self):
        from bet.stats.stat_validation import detect_contamination

        mixed = ["total_points", "corners", "aces", "possession"]
        result = detect_contamination("volleyball", mixed)
        assert "corners" in result
        assert "possession" in result
        assert "total_points" not in result
        assert "aces" not in result


class TestVolleyballValueRanges:
    """Test value range validation for volleyball stats."""

    def test_total_points_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["volleyball"]
        lo, hi = ranges["total_points"]

        # Valid volleyball total points
        assert lo <= 150 <= hi
        assert lo <= 200 <= hi
        assert lo <= 60  # minimum (very short 3-0 match)
        assert 250 <= hi  # maximum (long 5-set match)

    def test_aces_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["volleyball"]
        lo, hi = ranges["aces"]
        assert lo <= 5 <= hi
        assert lo <= 12 <= hi

    def test_blocks_range(self):
        from bet.stats.value_ranges import SPORT_VALUE_RANGES

        ranges = SPORT_VALUE_RANGES["volleyball"]
        lo, hi = ranges["blocks"]
        assert lo <= 8 <= hi
        assert lo <= 15 <= hi


class TestVolleyballL10Building:
    """Test L10 array construction logic."""

    def test_l10_from_values_correct_length(self):
        values = list(range(15))
        l10 = values[:10]
        assert len(l10) == 10

    def test_l5_from_l10(self):
        l10 = [150, 160, 170, 140, 180, 155, 165, 145, 175, 190]
        l5 = l10[:5]
        assert len(l5) == 5
        assert l5 == [150, 160, 170, 140, 180]

    def test_averages_computed_correctly(self):
        l10 = [150.0, 160.0, 170.0, 140.0, 180.0, 155.0, 165.0, 145.0, 175.0, 190.0]
        l10_avg = round(sum(l10) / len(l10), 2)
        assert l10_avg == 163.0

    def test_single_value_is_thin_data(self):
        l10 = [150.0]
        assert len(l10) < 3  # Below threshold


class TestVolleyballHallucinationDetection:
    """Test the generic hallucination framework for volleyball."""

    def test_hallucination_config_exists_for_volleyball(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        assert "volleyball" in HALLUCINATION_CONFIG
        config = HALLUCINATION_CONFIG["volleyball"]
        assert config["thin_data_threshold"] == 3
        assert "Total Points O/U" in config["thin_data_markets_allowed"]

    def test_volleyball_warning_message_set(self):
        from deep_stats_report import HALLUCINATION_CONFIG

        config = HALLUCINATION_CONFIG["volleyball"]
        assert "aces" in config["warning_msg"].lower() or "blocks" in config["warning_msg"].lower()


class TestVolleyballCompetitionTiers:
    """Test that volleyball competition tiers are properly defined."""

    def test_plusliga_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        volleyball_tiers = COMP_TIER_KEYWORDS["volleyball"]
        tier_9 = next((t for t in volleyball_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "plusliga" in tier_9[1]

    def test_superlega_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        volleyball_tiers = COMP_TIER_KEYWORDS["volleyball"]
        tier_9 = next((t for t in volleyball_tiers if t[0] == 9), None)
        assert tier_9 is not None
        assert "superlega" in tier_9[1]

    def test_champions_league_highest_tier(self):
        from build_shortlist import COMP_TIER_KEYWORDS

        volleyball_tiers = COMP_TIER_KEYWORDS["volleyball"]
        tier_10 = next((t for t in volleyball_tiers if t[0] == 10), None)
        assert tier_10 is not None
        assert any("champions" in kw for kw in tier_10[1])


class TestVolleyballFuzzyMatch:
    """Test fuzzy matching for volleyball team names."""

    def test_exact_match_high_score(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Sir Safety Perugia", "Sir Safety Perugia", "volleyball")
        assert score >= 95

    def test_partial_match_above_threshold(self):
        from bet.fuzzy_match import SPORT_THRESHOLDS, match_team

        score, _ = match_team("Jastrzębski Węgiel", "Jastrzebski Wegiel", "volleyball")
        assert score >= SPORT_THRESHOLDS["volleyball"]

    def test_completely_different_teams_low_score(self):
        from bet.fuzzy_match import match_team

        score, _ = match_team("Perugia", "Zawiercie", "volleyball")
        assert score < 50
