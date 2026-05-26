"""Tests for fuzzy_match module."""
import pytest
from unittest.mock import patch, MagicMock
from bet.fuzzy_match import match_team, SPORT_THRESHOLDS


class TestMatchTeam:
    def test_exact_match(self):
        score, _ = match_team("Manchester United", "Manchester United")
        assert score == 100.0

    def test_close_match(self):
        score, _ = match_team("Manchester United", "Manchester Utd")
        assert score > 70.0

    def test_no_match(self):
        score, _ = match_team("Manchester United", "Real Madrid")
        assert score < 50.0

    def test_normalized_match(self):
        # normalize_team_name should handle FC/AFC prefixes etc
        score, _ = match_team("FC Barcelona", "Barcelona")
        assert score > 75.0

    def test_sport_specific_esports(self):
        # Esports should trigger resolve_alias
        score, _ = match_team("Natus Vincere", "NAVI", sport="cs2")
        # Score depends on alias resolution — just verify no crash
        assert 0 <= score <= 100


class TestSportThresholds:
    def test_all_sports_have_thresholds(self):
        expected = {"tennis", "football", "basketball", "hockey", "volleyball", "cs2", "valorant", "dota2"}
        assert expected == set(SPORT_THRESHOLDS.keys())

    def test_thresholds_are_reasonable(self):
        for sport, threshold in SPORT_THRESHOLDS.items():
            assert 60 <= threshold <= 95, f"{sport} threshold {threshold} is unreasonable"

    def test_esports_higher_threshold(self):
        # Esports names are short and ambiguous, need higher threshold
        for sport in ("cs2", "valorant", "dota2"):
            assert SPORT_THRESHOLDS[sport] >= 85
