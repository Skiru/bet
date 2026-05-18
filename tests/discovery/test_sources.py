"""Tests for source adapters with mocked HTTP clients."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.api_football import APIFixture
from bet.discovery.sources.sofascore import SofaScoreAdapter
from bet.discovery.sources.odds_api import OddsAPIAdapter
from bet.discovery.sources.api_football import APIFootballAdapter


class TestSofaScoreAdapter:
    def test_supported_sports(self):
        adapter = SofaScoreAdapter.__new__(SofaScoreAdapter)
        assert "football" in adapter.supported_sports
        assert "volleyball" in adapter.supported_sports
        assert "hockey" in adapter.supported_sports

    def test_is_available(self):
        adapter = SofaScoreAdapter.__new__(SofaScoreAdapter)
        assert adapter.is_available() is True

    def test_fetch_events_converts_api_fixtures(self):
        mock_client = MagicMock()
        mock_client.get_fixtures.return_value = [
            APIFixture(
                external_id="12345",
                source="sofascore",
                sport="football",
                competition_name="Premier League",
                home_team_name="Arsenal",
                away_team_name="Chelsea",
                kickoff="2026-05-14T15:00:00Z",
                status="Not started",
            ),
        ]

        adapter = SofaScoreAdapter.__new__(SofaScoreAdapter)
        adapter.name = "sofascore"
        adapter.supported_sports = ["football", "volleyball", "basketball", "tennis", "hockey"]
        adapter._client = mock_client
        adapter.logger = MagicMock()

        events = adapter._fetch_events_impl("2026-05-14", "football")
        assert len(events) == 1
        assert events[0].source == "sofascore"
        assert events[0].home_team == "Arsenal"
        assert events[0].external_id == "12345"

    def test_unsupported_sport_returns_empty(self):
        adapter = SofaScoreAdapter.__new__(SofaScoreAdapter)
        adapter.name = "sofascore"
        adapter.supported_sports = ["football"]
        adapter.logger = MagicMock()
        # fetch_events checks supported_sports before calling impl
        result = adapter.fetch_events("2026-05-14", "cricket")
        assert result == []


class TestOddsAPIAdapter:
    def test_is_available_without_key(self):
        adapter = OddsAPIAdapter.__new__(OddsAPIAdapter)
        adapter._api_key = None
        assert adapter.is_available() is False

    def test_is_available_with_key(self):
        adapter = OddsAPIAdapter.__new__(OddsAPIAdapter)
        adapter._api_key = "test-key"
        assert adapter.is_available() is True

    def test_no_volleyball_support(self):
        adapter = OddsAPIAdapter.__new__(OddsAPIAdapter)
        assert "volleyball" not in adapter.supported_sports

    @patch("bet.discovery.sources.odds_api.requests.get")
    def test_fetch_events_parses_response(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"x-requests-remaining": "450"}
        mock_resp.json.return_value = [
            {
                "id": "abc123",
                "sport_key": "soccer_epl",
                "sport_title": "EPL",
                "commence_time": "2026-05-14T15:00:00Z",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "bookmakers": [
                    {
                        "key": "betfair",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 2.1},
                                    {"name": "Chelsea", "price": 3.5},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        adapter = OddsAPIAdapter.__new__(OddsAPIAdapter)
        adapter.name = "odds-api"
        adapter.priority = 2
        adapter.supported_sports = ["football", "basketball", "hockey", "tennis"]
        adapter._api_key = "test-key"
        adapter._active_keys = {"football": ["soccer_epl"]}
        adapter._auth_failed = False
        adapter.logger = MagicMock()

        events = adapter._fetch_events_impl("2026-05-14", "football")
        assert len(events) == 1
        assert events[0].source == "odds-api"
        assert events[0].home_team == "Arsenal"
        assert events[0].odds is not None


class TestAPIFootballAdapter:
    def test_football_only(self):
        adapter = APIFootballAdapter.__new__(APIFootballAdapter)
        assert adapter.supported_sports == ["football"]

    def test_fetch_events_converts_fixtures(self):
        mock_client = MagicMock()
        mock_client.get_fixtures.return_value = [
            APIFixture(
                external_id="999",
                source="api-football",
                sport="football",
                competition_name="Bundesliga",
                home_team_name="Bayern Munich",
                away_team_name="Dortmund",
                kickoff="2026-05-14T18:30:00Z",
                status="NS",
            ),
        ]
        mock_client.is_available.return_value = True

        adapter = APIFootballAdapter.__new__(APIFootballAdapter)
        adapter.name = "api-football"
        adapter.priority = 3
        adapter.supported_sports = ["football"]
        adapter._client = mock_client
        adapter._limiter = MagicMock()
        adapter.logger = MagicMock()

        events = adapter._fetch_events_impl("2026-05-14", "football")
        assert len(events) == 1
        assert events[0].source == "api-football"
        assert events[0].competition == "Bundesliga"
