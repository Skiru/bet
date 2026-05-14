"""Tests for TennisSofascoreScraper — mocked API responses."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from bet.scrapers.tennis.sofascore_tennis import TennisSofascoreScraper
from bet.scrapers.base import ScraperError


FIXTURES_RESPONSE = {
    "events": [
        {
            "id": 11223344,
            "tournament": {
                "name": "Roland Garros",
                "category": {"name": "France"},
            },
            "homeTeam": {"name": "Carlos Alcaraz"},
            "awayTeam": {"name": "Jannik Sinner"},
            "startTimestamp": 1717416000,
            "status": {"type": "notstarted"},
        },
        {
            "id": 11223345,
            "tournament": {
                "name": "Roland Garros",
                "category": {"name": "France"},
            },
            "homeTeam": {"name": ""},
            "awayTeam": {"name": "Novak Djokovic"},
            "startTimestamp": 0,
            "status": {"type": "notstarted"},
        },
    ],
}

EMPTY_RESPONSE = {"events": []}


def _mock_api_get_ok(self, endpoint):
    if "scheduled-events" in endpoint:
        return FIXTURES_RESPONSE
    return {}


def _mock_api_get_empty(self, endpoint):
    return EMPTY_RESPONSE


class TestSofascoreTennis:
    @patch.object(TennisSofascoreScraper, "_api_get", _mock_api_get_ok)
    def test_scrape_fixtures_happy(self, session_factory):
        scraper = TennisSofascoreScraper(session_factory)
        count = scraper.scrape_fixtures("2024-06-03")
        assert count >= 1  # second event skipped (empty home name)

    @patch.object(TennisSofascoreScraper, "_api_get", _mock_api_get_empty)
    def test_scrape_fixtures_empty(self, session_factory):
        scraper = TennisSofascoreScraper(session_factory)
        count = scraper.scrape_fixtures("2024-06-03")
        assert count == 0

    def test_scrape_team_returns_zero(self, session_factory):
        scraper = TennisSofascoreScraper(session_factory)
        assert scraper.scrape_team_season_stats("ATP", "2024") == 0

    def test_scrape_player_returns_zero(self, session_factory):
        scraper = TennisSofascoreScraper(session_factory)
        assert scraper.scrape_player_season_stats("ATP", "2024") == 0

    @patch.object(TennisSofascoreScraper, "_api_get",
                  side_effect=ScraperError("SofaScore 403 Forbidden"))
    def test_scrape_fixtures_403(self, mock_get, session_factory):
        scraper = TennisSofascoreScraper(session_factory)
        with pytest.raises(ScraperError, match="403"):
            scraper.scrape_fixtures("2024-06-03")
