"""Unit tests for DB-first safety input pipeline (Phase 5).

Tests for _strip_ha_suffix, _synthesize_l10, build_safety_input_from_db,
and build_safety_input wrapper in scripts/normalize_stats.py.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.normalize_stats import (
    _strip_ha_suffix,
    _synthesize_l10,
    build_safety_input,
    build_safety_input_from_db,
)


# ---------------------------------------------------------------------------
# TestStripHaSuffix
# ---------------------------------------------------------------------------


class TestStripHaSuffix:
    def test_strips_home_suffix(self):
        assert _strip_ha_suffix("corners_home") == ("corners", "home")

    def test_strips_away_suffix(self):
        assert _strip_ha_suffix("corners_away") == ("corners", "away")

    def test_bare_key_passthrough(self):
        assert _strip_ha_suffix("corners") == ("corners", None)

    def test_compound_key_home(self):
        assert _strip_ha_suffix("shots_on_target_home") == ("shots_on_target", "home")

    def test_compound_key_away(self):
        assert _strip_ha_suffix("shots_on_target_away") == ("shots_on_target", "away")

    def test_key_containing_home_not_suffix(self):
        # "home_runs" should NOT be stripped — "home" is prefix, not suffix
        bare, side = _strip_ha_suffix("home_runs")
        assert side is None
        assert bare == "home_runs"

    def test_empty_string(self):
        assert _strip_ha_suffix("") == ("", None)

    def test_just_home(self):
        # "_home" at the end of a 4-char key → bare = ""
        bare, side = _strip_ha_suffix("_home")
        assert side == "home"
        assert bare == ""

    def test_fouls_away(self):
        assert _strip_ha_suffix("fouls_away") == ("fouls", "away")

    def test_yellow_cards_home(self):
        assert _strip_ha_suffix("yellow_cards_home") == ("yellow_cards", "home")


# ---------------------------------------------------------------------------
# TestSynthesizeL10
# ---------------------------------------------------------------------------


class TestSynthesizeL10:
    def test_produces_correct_count_default(self):
        values = _synthesize_l10(5.0, 5.5)
        assert len(values) == 10

    def test_produces_custom_count(self):
        values = _synthesize_l10(5.0, 5.5, count=6)
        assert len(values) == 6

    def test_average_near_input(self):
        l10_avg = 7.3
        values = _synthesize_l10(l10_avg, l5_avg=7.5)
        actual_avg = sum(values) / len(values)
        assert abs(actual_avg - l10_avg) / l10_avg < 0.10  # within 10%

    def test_average_near_input_no_l5(self):
        l10_avg = 4.0
        values = _synthesize_l10(l10_avg, l5_avg=None)
        actual_avg = sum(values) / len(values)
        assert abs(actual_avg - l10_avg) / l10_avg < 0.10

    def test_spread_avoids_degenerate(self):
        values = _synthesize_l10(5.0, 5.5)
        # Not all values should be identical
        assert len(set(values)) > 1

    def test_handles_zero_avg(self):
        values = _synthesize_l10(0.0, None)
        assert values == [0.0] * 10

    def test_handles_zero_avg_with_l5(self):
        values = _synthesize_l10(0.0, 0.0)
        assert all(v == 0.0 for v in values)

    def test_l5_influence(self):
        # When l5_avg > l10_avg, first 5 values should skew higher
        values = _synthesize_l10(5.0, 7.0)
        l5_subset_avg = sum(values[:5]) / 5
        full_avg = sum(values) / len(values)
        assert l5_subset_avg >= full_avg - 0.5  # L5 subset is at least close to or above full avg

    def test_all_values_are_floats(self):
        values = _synthesize_l10(3.2, 3.5)
        assert all(isinstance(v, float) for v in values)

    def test_large_avg(self):
        values = _synthesize_l10(120.0, 115.0)
        assert len(values) == 10
        actual_avg = sum(values) / len(values)
        assert abs(actual_avg - 120.0) / 120.0 < 0.10

    def test_deterministic(self):
        # Same inputs always produce same outputs (no randomness)
        v1 = _synthesize_l10(5.0, 5.5)
        v2 = _synthesize_l10(5.0, 5.5)
        assert v1 == v2


# ---------------------------------------------------------------------------
# TestBuildSafetyInputFromDb
# ---------------------------------------------------------------------------


def _make_mock_team_form(stat_key, l10_avg, l5_avg=None, l10_values=None,
                         h2h_opponent_id=None):
    """Create a mock TeamForm-like object."""
    form = MagicMock()
    form.stat_key = stat_key
    form.l10_avg = l10_avg
    form.l5_avg = l5_avg
    form.l10_values = l10_values or []
    form.l5_values = []
    form.h2h_opponent_id = h2h_opponent_id
    form.trend = "STABLE"
    form.source = "test"
    return form


class TestBuildSafetyInputFromDb:
    @patch("bet.db.repositories.StatsRepo")
    @patch("bet.db.repositories.TeamRepo")
    @patch("bet.db.repositories.SportRepo")
    @patch("bet.db.connection.get_db")
    def test_returns_none_on_unknown_team(self, mock_get_db, MockSport, MockTeam, MockStats):
        """Team not in DB → None."""
        ctx = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        sport_obj = MagicMock()
        sport_obj.id = 1
        MockSport.return_value.get_by_name.return_value = sport_obj
        MockTeam.return_value.resolve.return_value = None  # team not found

        result = build_safety_input_from_db("football", "Unknown FC", "Also Unknown", "Test League")
        assert result is None

    @patch("bet.db.repositories.StatsRepo")
    @patch("bet.db.repositories.TeamRepo")
    @patch("bet.db.repositories.SportRepo")
    @patch("bet.db.connection.get_db")
    def test_returns_none_on_unknown_sport(self, mock_get_db, MockSport, MockTeam, MockStats):
        ctx = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        MockSport.return_value.get_by_name.return_value = None

        result = build_safety_input_from_db("curling", "Team A", "Team B", "League")
        assert result is None

    @patch("bet.db.connection.get_db", side_effect=Exception("DB gone"))
    def test_returns_none_on_db_error(self, mock_get_db):
        """DB connection fails → None (no exception raised)."""
        result = build_safety_input_from_db("football", "Arsenal", "Chelsea", "PL")
        assert result is None

    def test_returns_none_on_import_error(self):
        """If bet.db.connection is not importable → None."""
        with patch.dict("sys.modules", {"bet.db.connection": None}):
            # The function catches ImportError internally
            result = build_safety_input_from_db("football", "Arsenal", "Chelsea", "PL")
        # Should either return None or raise — the function is designed to return None
        assert result is None

    @patch("scripts.normalize_stats.SPORT_MARKETS", {
        "football": [
            {"name": "Corners Total O/U", "stat_a": "corners", "stat_b": "corners", "is_combined": True},
        ],
    })
    @patch("bet.db.repositories.StatsRepo")
    @patch("bet.db.repositories.TeamRepo")
    @patch("bet.db.repositories.SportRepo")
    @patch("bet.db.connection.get_db")
    def test_returns_correct_format(self, mock_get_db, MockSport, MockTeam, MockStats):
        """Output has sport, team_a, team_b, competition, markets keys."""
        ctx = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        sport_obj = MagicMock()
        sport_obj.id = 1
        MockSport.return_value.get_by_name.return_value = sport_obj

        team_a_obj = MagicMock()
        team_a_obj.id = 10
        team_b_obj = MagicMock()
        team_b_obj.id = 20
        MockTeam.return_value.resolve.side_effect = [team_a_obj, team_b_obj]

        # Team A form: corners_home with avg 5.0
        form_a = [_make_mock_team_form("corners_home", l10_avg=5.0, l5_avg=5.5)]
        # Team B form: corners_away with avg 4.0
        form_b = [_make_mock_team_form("corners_away", l10_avg=4.0, l5_avg=3.8)]
        MockStats.return_value.get_all_form_for_team.side_effect = [form_a, form_b]

        # H2H — empty
        ctx.execute.return_value.fetchall.return_value = []

        result = build_safety_input_from_db("football", "Arsenal", "Chelsea", "Premier League")

        assert result is not None
        assert result["sport"] == "football"
        assert result["team_a"] == "Arsenal"
        assert result["team_b"] == "Chelsea"
        assert result["competition"] == "Premier League"
        assert "markets" in result
        assert isinstance(result["markets"], list)
        assert len(result["markets"]) > 0

    @patch("bet.db.repositories.StatsRepo")
    @patch("bet.db.repositories.TeamRepo")
    @patch("bet.db.repositories.SportRepo")
    @patch("bet.db.connection.get_db")
    def test_returns_none_when_no_form_data(self, mock_get_db, MockSport, MockTeam, MockStats):
        """No form data for either team → None."""
        ctx = MagicMock()
        mock_get_db.return_value.__enter__ = MagicMock(return_value=ctx)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        sport_obj = MagicMock()
        sport_obj.id = 1
        MockSport.return_value.get_by_name.return_value = sport_obj

        team_a_obj = MagicMock()
        team_a_obj.id = 10
        team_b_obj = MagicMock()
        team_b_obj.id = 20
        MockTeam.return_value.resolve.side_effect = [team_a_obj, team_b_obj]

        # No form data
        MockStats.return_value.get_all_form_for_team.return_value = []

        result = build_safety_input_from_db("football", "Arsenal", "Chelsea", "Premier League")
        assert result is None


# ---------------------------------------------------------------------------
# TestBuildSafetyInputWrapper
# ---------------------------------------------------------------------------


class TestBuildSafetyInputWrapper:
    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_db_result_returned_when_available(self, mock_db, mock_cache):
        """DB returns data → DB result used, cache not called."""
        db_result = {
            "sport": "football",
            "team_a": "Arsenal",
            "team_b": "Chelsea",
            "competition": "PL",
            "markets": [{"name": "Corners Total O/U", "line": 9.5}],
        }
        mock_db.return_value = db_result

        result = build_safety_input("football", "Arsenal", "Chelsea", "PL")

        assert result is db_result
        mock_db.assert_called_once_with("football", "Arsenal", "Chelsea", "PL", fixture_id=None)
        mock_cache.assert_not_called()

    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_falls_back_to_cache_when_db_returns_none(self, mock_db, mock_cache):
        """DB returns None → cache result used."""
        mock_db.return_value = None
        cache_result = {
            "sport": "football",
            "team_a": "Arsenal",
            "team_b": "Chelsea",
            "competition": "PL",
            "markets": [{"name": "Corners Total O/U", "line": 9.5}],
        }
        mock_cache.return_value = cache_result

        result = build_safety_input("football", "Arsenal", "Chelsea", "PL")

        assert result is cache_result
        mock_cache.assert_called_once()

    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_falls_back_when_db_returns_empty_markets(self, mock_db, mock_cache):
        """DB returns dict with empty markets list → cache used."""
        mock_db.return_value = {
            "sport": "football",
            "team_a": "Arsenal",
            "team_b": "Chelsea",
            "competition": "PL",
            "markets": [],
        }
        cache_result = {"sport": "football", "team_a": "A", "team_b": "B",
                        "competition": "PL", "markets": [{"name": "X"}]}
        mock_cache.return_value = cache_result

        result = build_safety_input("football", "Arsenal", "Chelsea", "PL")

        assert result is cache_result

    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_falls_back_on_db_exception(self, mock_db, mock_cache):
        """DB raises exception → build_safety_input_from_db returns None → cache used."""
        # build_safety_input_from_db itself catches exceptions and returns None,
        # but we mock it to return None to simulate that behavior
        mock_db.return_value = None
        cache_result = {"sport": "tennis", "team_a": "A", "team_b": "B",
                        "competition": "ATP", "markets": [{"name": "Total Games O/U"}]}
        mock_cache.return_value = cache_result

        result = build_safety_input("tennis", "A", "B", "ATP")

        assert result is cache_result

    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_cache_dir_passed_to_cache_fallback(self, mock_db, mock_cache):
        """cache_dir parameter is forwarded to cache fallback."""
        mock_db.return_value = None
        mock_cache.return_value = None
        custom_dir = Path("/tmp/test_cache")

        build_safety_input("football", "A", "B", "PL", cache_dir=custom_dir)

        mock_cache.assert_called_once_with("football", "A", "B", "PL", custom_dir)

    @patch("scripts.normalize_stats.build_safety_input_from_cache")
    @patch("scripts.normalize_stats.build_safety_input_from_db")
    def test_returns_none_when_both_fail(self, mock_db, mock_cache):
        """Both DB and cache return None → None."""
        mock_db.return_value = None
        mock_cache.return_value = None

        result = build_safety_input("football", "A", "B", "PL")

        assert result is None
