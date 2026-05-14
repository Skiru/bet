"""Tests for VolleySofascoreScraper — mocked API responses."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock

from bet.scrapers.volleyball.sofascore_volley import VolleySofascoreScraper


SCHEDULE_RESPONSE = {
    "events": [
        {
            "id": 12345678,
            "tournament": {
                "name": "PlusLiga",
                "category": {"name": "Poland"},
            },
            "homeTeam": {"name": "Jastrzębski Węgiel"},
            "awayTeam": {"name": "ZAKSA Kędzierzyn-Koźle"},
            "startTimestamp": 1705363200,
        },
    ],
}

STANDINGS_RESPONSE = {
    "standings": [
        {
            "rows": [
                {
                    "team": {"name": "Jastrzębski Węgiel"},
                    "matches": 30,
                    "wins": 25,
                    "losses": 5,
                    "points": 72,
                    "setsWon": 78,
                    "setsLost": 22,
                },
            ],
        },
    ],
}


def _mock_api_get(self, endpoint):
    if "scheduled-events" in endpoint:
        return SCHEDULE_RESPONSE
    if "standings" in endpoint:
        return STANDINGS_RESPONSE
    return {}


class TestVolleySofascore:
    @patch.object(VolleySofascoreScraper, "_api_get", _mock_api_get)
    def test_scrape_fixtures(self, session_factory):
        scraper = VolleySofascoreScraper(session_factory)
        count = scraper.scrape_fixtures("2025-01-15")
        assert count >= 1

    @patch.object(VolleySofascoreScraper, "_api_get", _mock_api_get)
    def test_scrape_team_season_stats(self, session_factory):
        scraper = VolleySofascoreScraper(session_factory)
        count = scraper.scrape_team_season_stats("plusliga", "2024")
        assert count > 0

    def test_scrape_player_returns_zero(self, session_factory):
        scraper = VolleySofascoreScraper(session_factory)
        assert scraper.scrape_player_season_stats("plusliga", "2024") == 0
