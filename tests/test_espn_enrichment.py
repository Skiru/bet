"""Tests for ESPN enrichment integration.

Verifies that the enrichment pipeline:
1. Tries ESPN before API-Sports
2. Falls back to API-Sports when ESPN fails
3. Volleyball still uses API-Sports (no ESPN coverage)
"""

from unittest.mock import patch, MagicMock

import pytest

from bet.stats.enrichment import _try_api_fetch, _try_espn_fetch, _try_api_sports_fetch


class MockTeam:
    """Mock team object."""
    def __init__(self, name="Arsenal", team_id=1):
        self.id = team_id
        self.name = name


class MockDBConn:
    """Mock database connection."""
    def __init__(self, competition_name="Premier League"):
        self._competition_name = competition_name

    def execute(self, query, params=None):
        """Mock execute that returns competition info or empty match_stats."""
        if "competitions" in query:
            return MockCursor(self._competition_name)
        return MockCursor(None)

    def commit(self):
        pass


class MockCursor:
    """Mock cursor."""
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        if self._value:
            return {"name": self._value}
        return None

    def fetchall(self):
        return []


@patch("bet.stats.enrichment._try_espn_fetch")
@patch("bet.stats.enrichment._try_api_sports_fetch")
class TestTryApiFetchOrder:
    """Test that _try_api_fetch tries ESPN before API-Sports."""

    def test_espn_success_skips_api_sports(self, mock_api_sports, mock_espn):
        """When ESPN succeeds, API-Sports is NOT called."""
        mock_espn.return_value = True
        mock_api_sports.return_value = False

        team = MockTeam()
        result = _try_api_fetch(team, "football", ["corners", "fouls"], MagicMock())

        assert result is True
        mock_espn.assert_called_once()
        mock_api_sports.assert_not_called()

    def test_espn_failure_falls_back_to_api_sports(self, mock_api_sports, mock_espn):
        """When ESPN fails, API-Sports is tried as fallback."""
        mock_espn.return_value = False
        mock_api_sports.return_value = True

        team = MockTeam()
        result = _try_api_fetch(team, "football", ["corners", "fouls"], MagicMock())

        assert result is True
        mock_espn.assert_called_once()
        mock_api_sports.assert_called_once()

    def test_both_fail(self, mock_api_sports, mock_espn):
        """When both ESPN and API-Sports fail, returns False."""
        mock_espn.return_value = False
        mock_api_sports.return_value = False

        team = MockTeam()
        result = _try_api_fetch(team, "football", ["corners", "fouls"], MagicMock())

        assert result is False


class TestESPNFetchVolleyball:
    """Test that volleyball doesn't use ESPN (no coverage)."""

    def test_volleyball_not_in_espn(self):
        """Volleyball returns False from ESPN fetch (not in API_ESPN)."""
        team = MockTeam(name="Some Volleyball Team")
        db_conn = MockDBConn()

        result = _try_espn_fetch(team, "volleyball", ["sets", "points"], db_conn)
        assert result is False


class TestESPNFetchFootball:
    """Test ESPN football fetch with league detection."""

    @patch("bet.api_clients.espn.ESPNClient.get_fixture_stats")
    @patch("bet.api_clients.espn.ESPNClient.get_team_last_fixtures")
    @patch("bet.api_clients.espn.ESPNClient.resolve_team_id")
    def test_football_with_known_league(self, mock_resolve, mock_fixtures, mock_stats):
        """Football with a known league (Premier League) uses ESPN."""
        mock_resolve.return_value = "359"
        mock_fixtures.return_value = [
            {"id": "100", "date": "2025-04-01", "home_team": "Arsenal", "away_team": "Chelsea", "score": "2-1"},
        ]
        from bet.api_clients.api_football import APIMatchStats
        mock_stats.return_value = [
            APIMatchStats(
                external_id="100",
                source="espn-football",
                sport="football",
                home_team_name="Arsenal",
                away_team_name="Chelsea",
                stats={"corners": {"home": 7.0, "away": 4.0}},
            )
        ]

        team = MockTeam(name="Arsenal")
        db_conn = MockDBConn(competition_name="Premier League")

        # Mock the StatsRepo and SportRepo
        with patch("bet.stats.enrichment.StatsRepo") as mock_stats_repo, \
             patch("bet.stats.enrichment.SportRepo") as mock_sport_repo, \
             patch("bet.stats.enrichment._record_source_success"):

            mock_sport_obj = MagicMock()
            mock_sport_obj.id = 1
            mock_sport_repo.return_value.get_by_name.return_value = mock_sport_obj

            result = _try_espn_fetch(team, "football", ["corners"], db_conn)
            assert result is True

    def test_football_unknown_league_returns_false(self):
        """Football with unknown league falls back (returns False)."""
        team = MockTeam(name="Some Team")
        db_conn = MockDBConn(competition_name="Unknown Regional League")

        result = _try_espn_fetch(team, "football", ["corners"], db_conn)
        assert result is False


class TestAPIStortsFetch:
    """Test API-Sports fallback."""

    @patch("bet.api_clients.get_client")
    def test_volleyball_uses_api_sports(self, mock_get_client):
        """Volleyball goes through API-Sports path."""
        mock_client = MagicMock()
        mock_client.is_available.return_value = True
        mock_client.resolve_team_id.return_value = "123"
        mock_client.get_team_last_fixtures.return_value = [{"id": "500"}]
        from bet.api_clients.api_football import APIMatchStats
        mock_client.get_fixture_stats.return_value = [
            APIMatchStats(
                external_id="500",
                source="api-volleyball",
                sport="volleyball",
                home_team_name="Team A",
                away_team_name="Team B",
                stats={"sets": {"home": 3.0, "away": 1.0}},
            )
        ]
        mock_client.rate_limiter = MagicMock()
        mock_client.rate_limiter.can_request.return_value = True
        mock_client.api_name = "api-volleyball"
        mock_get_client.return_value = mock_client

        team = MockTeam(name="Team A")
        db_conn = MockDBConn()

        with patch("bet.stats.enrichment.StatsRepo") as mock_stats_repo, \
             patch("bet.stats.enrichment.SportRepo") as mock_sport_repo, \
             patch("bet.stats.enrichment._record_source_success"):
            mock_sport_obj = MagicMock()
            mock_sport_obj.id = 5
            mock_sport_repo.return_value.get_by_name.return_value = mock_sport_obj

            result = _try_api_sports_fetch(team, "volleyball", ["sets"], db_conn)
            assert result is True
            mock_get_client.assert_called_with("api-volleyball")
