"""Tests for stat_validation module."""
import pytest
from bet.stats.stat_validation import (
    is_valid_stat_key,
    get_valid_stats,
    filter_valid_stats,
    detect_contamination,
)


class TestIsValidStatKey:
    def test_valid_football_key(self):
        assert is_valid_stat_key("football", "corners") is True
        assert is_valid_stat_key("football", "fouls") is True

    def test_invalid_football_key(self):
        assert is_valid_stat_key("football", "aces") is False
        assert is_valid_stat_key("football", "kills") is False

    def test_valid_tennis_key(self):
        assert is_valid_stat_key("tennis", "aces") is True
        assert is_valid_stat_key("tennis", "double_faults") is True

    def test_invalid_tennis_key(self):
        assert is_valid_stat_key("tennis", "corners") is False
        assert is_valid_stat_key("tennis", "goals") is False

    def test_case_insensitive_sport(self):
        assert is_valid_stat_key("Football", "corners") is True
        assert is_valid_stat_key("HOCKEY", "goals") is True

    def test_unknown_sport_allows_everything(self):
        assert is_valid_stat_key("curling", "whatever") is True

    def test_esports_keys(self):
        assert is_valid_stat_key("cs2", "kills") is True
        assert is_valid_stat_key("cs2", "corners") is False
        assert is_valid_stat_key("valorant", "map_win_rate") is True
        assert is_valid_stat_key("dota2", "kills_avg") is True


class TestGetValidStats:
    def test_returns_set_for_known_sport(self):
        result = get_valid_stats("football")
        assert isinstance(result, set)
        assert "corners" in result

    def test_returns_empty_for_unknown_sport(self):
        assert get_valid_stats("curling") == set()


class TestFilterValidStats:
    def test_filters_correctly(self):
        keys = ["corners", "fouls", "aces", "kills"]
        result = filter_valid_stats("football", keys)
        assert "corners" in result
        assert "fouls" in result
        assert "aces" not in result
        assert "kills" not in result

    def test_unknown_sport_keeps_all(self):
        keys = ["anything", "goes"]
        result = filter_valid_stats("curling", keys)
        assert result == ["anything", "goes"]


class TestDetectContamination:
    def test_finds_contaminated_keys(self):
        result = detect_contamination("football", ["corners", "aces", "kills"])
        assert "aces" in result
        assert "kills" in result
        assert "corners" not in result

    def test_no_contamination(self):
        result = detect_contamination("hockey", ["goals", "shots", "hits"])
        assert result == []

    def test_unknown_sport_returns_empty(self):
        result = detect_contamination("curling", ["anything"])
        assert result == []

    def test_cross_sport_contamination(self):
        # Tennis keys appearing in hockey data
        result = detect_contamination("hockey", ["goals", "aces", "double_faults"])
        assert "aces" in result
        assert "double_faults" in result
        assert "goals" not in result
