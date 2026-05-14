"""Tests for HockeyNHLScraper — mocked NHL API responses."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock

from bet.scrapers.hockey.nhl_api import HockeyNHLScraper
from bet.scrapers.models import PlayerSeasonStat


# ---- fixtures ----

STANDINGS_RESPONSE = {
    "standings": [
        {
            "teamName": {"default": "Edmonton Oilers"},
            "teamAbbrev": {"default": "EDM"},
            "gamesPlayed": 82,
            "wins": 52,
            "losses": 20,
            "otLosses": 10,
            "points": 114,
            "goalFor": 300,
            "goalAgainst": 220,
            "goalDifferential": 80,
            "regulationWins": 40,
            "homeWins": 28,
            "homeLosses": 10,
            "roadWins": 24,
            "roadLosses": 10,
            "shootoutWins": 3,
            "shootoutLosses": 2,
        },
    ],
}

SKATER_LEADERS_RESPONSE = {
    "goals": [
        {
            "id": 8478402,
            "firstName": {"default": "Connor"},
            "lastName": {"default": "McDavid"},
            "position": "C",
            "teamAbbrev": "EDM",
            "value": 64,
        },
    ],
    "assists": [
        {
            "id": 8478402,
            "firstName": {"default": "Connor"},
            "lastName": {"default": "McDavid"},
            "position": "C",
            "teamAbbrev": "EDM",
            "value": 89,
        },
    ],
    "points": [
        {
            "id": 8478402,
            "firstName": {"default": "Connor"},
            "lastName": {"default": "McDavid"},
            "position": "C",
            "teamAbbrev": "EDM",
            "value": 153,
        },
    ],
}

SCHEDULE_RESPONSE = {
    "gameWeek": [
        {
            "date": "2025-01-15",
            "games": [
                {
                    "id": 2024020001,
                    "homeTeam": {"abbrev": "EDM"},
                    "awayTeam": {"abbrev": "TOR"},
                    "startTimeUTC": "2025-01-16T01:00:00Z",
                },
            ],
        },
    ],
}


def _mock_api_get(self, endpoint):
    if "standings" in endpoint:
        return STANDINGS_RESPONSE
    if "skater-stats-leaders" in endpoint:
        return SKATER_LEADERS_RESPONSE
    if "schedule" in endpoint:
        return SCHEDULE_RESPONSE
    return {}


class TestNHLTeamStats:
    @patch.object(HockeyNHLScraper, "_api_get", _mock_api_get)
    def test_scrape_team_season_stats(self, session_factory):
        scraper = HockeyNHLScraper(session_factory)
        count = scraper.scrape_team_season_stats("NHL", "2425")
        assert count > 0

    @patch.object(HockeyNHLScraper, "_api_get", _mock_api_get)
    def test_scrape_player_season_stats(self, session_factory):
        scraper = HockeyNHLScraper(session_factory)
        count = scraper.scrape_player_season_stats("NHL", "2425")
        assert count >= 1
        with session_factory() as session:
            rows = session.query(PlayerSeasonStat).all()
            assert len(rows) >= 1
            stats = json.loads(rows[0].stats_json)
            assert "goals" in stats

    @patch.object(HockeyNHLScraper, "_api_get", _mock_api_get)
    def test_scrape_fixtures(self, session_factory):
        scraper = HockeyNHLScraper(session_factory)
        count = scraper.scrape_fixtures("2025-01-15")
        assert count >= 1
