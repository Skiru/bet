"""Tests for ESPN multi-sport scraper.

Follows the established pattern: mock ESPN API responses, verify DB writes.
"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass, field
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Mock data — mimics ESPNClient return types
# ---------------------------------------------------------------------------

@dataclass
class MockAPIFixture:
    external_id: str = ""
    source: str = "espn-football"
    sport: str = "football"
    competition_name: str = "eng.1"
    home_team_name: str = ""
    away_team_name: str = ""
    kickoff: str = ""
    status: str = "STATUS_FULL_TIME"


@dataclass
class MockAPIMatchStats:
    external_id: str = ""
    source: str = "espn-football"
    sport: str = "football"
    home_team_name: str = ""
    away_team_name: str = ""
    stats: dict = field(default_factory=dict)


MOCK_STANDINGS = [
    {"team_id": "359", "team_name": "Arsenal", "rank": "1", "wins": "25", "losses": "3"},
    {"team_id": "364", "team_name": "Liverpool", "rank": "2", "wins": "24", "losses": "5"},
]

MOCK_FIXTURES_ARSENAL = [
    {"id": "1001", "date": "2026-05-10T15:00Z", "home_team": "Arsenal", "away_team": "Chelsea", "score": "2-1"},
    {"id": "1002", "date": "2026-05-03T15:00Z", "home_team": "Arsenal", "away_team": "Everton", "score": "3-0"},
]

MOCK_FIXTURES_LIVERPOOL = [
    {"id": "2001", "date": "2026-05-10T15:00Z", "home_team": "Liverpool", "away_team": "Man City", "score": "1-1"},
    {"id": "2002", "date": "2026-05-03T15:00Z", "home_team": "Wolves", "away_team": "Liverpool", "score": "0-2"},
]

MOCK_MATCH_STATS_1001 = [MockAPIMatchStats(
    external_id="1001",
    source="espn-football",
    sport="football",
    home_team_name="Arsenal",
    away_team_name="Chelsea",
    stats={
        "corners": {"home": 8.0, "away": 3.0},
        "fouls": {"home": 10.0, "away": 14.0},
        "shots_on_target": {"home": 7.0, "away": 4.0},
        "goals": {"home": 2.0, "away": 1.0},
        "possession": {"home": 62.0, "away": 38.0},
    },
)]

MOCK_MATCH_STATS_1002 = [MockAPIMatchStats(
    external_id="1002",
    source="espn-football",
    sport="football",
    home_team_name="Arsenal",
    away_team_name="Everton",
    stats={
        "corners": {"home": 10.0, "away": 2.0},
        "fouls": {"home": 8.0, "away": 16.0},
        "shots_on_target": {"home": 9.0, "away": 1.0},
        "goals": {"home": 3.0, "away": 0.0},
        "possession": {"home": 68.0, "away": 32.0},
    },
)]

MOCK_MATCH_STATS_2001 = [MockAPIMatchStats(
    external_id="2001",
    source="espn-football",
    sport="football",
    home_team_name="Liverpool",
    away_team_name="Man City",
    stats={
        "corners": {"home": 5.0, "away": 7.0},
        "fouls": {"home": 12.0, "away": 11.0},
        "shots_on_target": {"home": 5.0, "away": 6.0},
        "goals": {"home": 1.0, "away": 1.0},
    },
)]

MOCK_MATCH_STATS_2002 = [MockAPIMatchStats(
    external_id="2002",
    source="espn-football",
    sport="football",
    home_team_name="Wolves",
    away_team_name="Liverpool",
    stats={
        "corners": {"home": 3.0, "away": 6.0},
        "fouls": {"home": 15.0, "away": 9.0},
        "shots_on_target": {"home": 2.0, "away": 8.0},
        "goals": {"home": 0.0, "away": 2.0},
    },
)]

MOCK_NBA_STANDINGS = [
    {"team_id": "2", "team_name": "Boston Celtics", "rank": "1"},
    {"team_id": "7", "team_name": "Denver Nuggets", "rank": "2"},
]

MOCK_NBA_MATCH_STATS = [MockAPIMatchStats(
    external_id="5001",
    source="espn-basketball",
    sport="basketball",
    home_team_name="Boston Celtics",
    away_team_name="New York Knicks",
    stats={
        "rebounds": {"home": 48.0, "away": 42.0},
        "assists": {"home": 28.0, "away": 22.0},
        "turnovers": {"home": 12.0, "away": 15.0},
        "points": {"home": 118.0, "away": 105.0},
    },
)]

MOCK_ROSTER = [
    {"id": "4065648", "name": "Jayson Tatum", "position": "SF", "age": 28},
    {"id": "3032976", "name": "Jaylen Brown", "position": "SG", "age": 29},
]


# ---------------------------------------------------------------------------
# Fixtures — mock ESPNClient
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_espn_client():
    """Mock ESPNClient that returns pre-built data."""
    with patch("bet.scrapers.espn.BaseESPNScraper._get_espn_client") as mock_factory:
        client = MagicMock()
        mock_factory.return_value = client
        yield client


@pytest.fixture
def mock_resolve_leagues():
    """Mock league resolution to return a single league."""
    with patch("bet.scrapers.espn.BaseESPNScraper._resolve_leagues") as mock:
        mock.return_value = ["eng.1"]
        yield mock


# ---------------------------------------------------------------------------
# Football tests
# ---------------------------------------------------------------------------

class TestFootballESPNScraper:

    def test_scrape_team_season_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import FootballESPNScraper

        # Setup mock
        mock_espn_client.get_standings.return_value = MOCK_STANDINGS

        def _get_fixtures(team_id, last_n=10):
            if team_id == "359":
                return MOCK_FIXTURES_ARSENAL
            return MOCK_FIXTURES_LIVERPOOL

        mock_espn_client.get_team_last_fixtures.side_effect = _get_fixtures

        def _get_stats(fix_id):
            mapping = {
                "1001": MOCK_MATCH_STATS_1001,
                "1002": MOCK_MATCH_STATS_1002,
                "2001": MOCK_MATCH_STATS_2001,
                "2002": MOCK_MATCH_STATS_2002,
            }
            return mapping.get(fix_id, [])

        mock_espn_client.get_fixture_stats.side_effect = _get_stats

        scraper = FootballESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("Premier League", "2526")

        assert result > 0

        # Verify teams were created
        with session_factory() as session:
            teams = session.execute(
                text("SELECT name FROM teams ORDER BY name")
            ).fetchall()
            team_names = [t[0] for t in teams]
            assert "Arsenal" in team_names
            assert "Liverpool" in team_names

        # Verify league_profiles were written
        with session_factory() as session:
            profiles = session.execute(
                text("SELECT stat_key, avg_value FROM league_profiles")
            ).fetchall()
            stat_keys = [p[0] for p in profiles]
            assert "corners" in stat_keys
            assert "fouls" in stat_keys
            assert "goals" in stat_keys

    def test_scrape_team_stats_no_standings(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        """No standings → returns 0."""
        from bet.scrapers.espn import FootballESPNScraper

        mock_espn_client.get_standings.return_value = []
        scraper = FootballESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("Premier League", "2526")
        assert result == 0

    def test_player_stats_not_available_for_football(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        """Football player stats returns 0 (ESPN has no soccer player gamelogs)."""
        from bet.scrapers.espn import FootballESPNScraper

        scraper = FootballESPNScraper(session_factory)
        result = scraper.scrape_player_season_stats("Premier League", "2526")
        assert result == 0


# ---------------------------------------------------------------------------
# Basketball tests
# ---------------------------------------------------------------------------

class TestBasketballESPNScraper:

    def test_scrape_team_season_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import BasketballESPNScraper

        mock_resolve_leagues.return_value = ["nba"]
        mock_espn_client.get_standings.return_value = MOCK_NBA_STANDINGS

        mock_espn_client.get_team_last_fixtures.return_value = [
            {"id": "5001", "date": "2026-05-10T19:00Z", "home_team": "Boston Celtics", "away_team": "New York Knicks", "score": "118-105"},
        ]
        mock_espn_client.get_fixture_stats.return_value = MOCK_NBA_MATCH_STATS

        scraper = BasketballESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("NBA", "2526")

        assert result > 0

        with session_factory() as session:
            profiles = session.execute(
                text("SELECT stat_key FROM league_profiles")
            ).fetchall()
            stat_keys = [p[0] for p in profiles]
            assert "rebounds" in stat_keys
            assert "assists" in stat_keys

    def test_player_season_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import BasketballESPNScraper

        mock_resolve_leagues.return_value = ["nba"]
        mock_espn_client.get_standings.return_value = MOCK_NBA_STANDINGS
        mock_espn_client.get_team_roster.return_value = MOCK_ROSTER

        scraper = BasketballESPNScraper(session_factory)
        result = scraper.scrape_player_season_stats("NBA", "2526")

        # 2 teams × 2 players each, but mock returns same roster → 4 total
        assert result > 0

        with session_factory() as session:
            athletes = session.execute(
                text("SELECT name FROM athletes ORDER BY name")
            ).fetchall()
            names = [a[0] for a in athletes]
            assert "Jayson Tatum" in names
            assert "Jaylen Brown" in names


# ---------------------------------------------------------------------------
# Hockey tests
# ---------------------------------------------------------------------------

class TestHockeyESPNScraper:

    def test_scrape_team_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import HockeyESPNScraper

        mock_resolve_leagues.return_value = ["nhl"]
        mock_espn_client.get_standings.return_value = [
            {"team_id": "1", "team_name": "Edmonton Oilers", "rank": "1"},
        ]
        mock_espn_client.get_team_last_fixtures.return_value = [
            {"id": "7001", "date": "2026-05-10T19:00Z", "home_team": "Edmonton Oilers", "away_team": "Dallas Stars", "score": "4-2"},
        ]
        mock_espn_client.get_fixture_stats.return_value = [MockAPIMatchStats(
            external_id="7001",
            sport="hockey",
            home_team_name="Edmonton Oilers",
            away_team_name="Dallas Stars",
            stats={
                "shots": {"home": 35.0, "away": 28.0},
                "hits": {"home": 22.0, "away": 30.0},
                "powerplay_goals": {"home": 2.0, "away": 0.0},
                "goals": {"home": 4.0, "away": 2.0},
            },
        )]

        scraper = HockeyESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("NHL", "2526")
        assert result > 0


# ---------------------------------------------------------------------------
# Tennis tests
# ---------------------------------------------------------------------------

class TestTennisESPNScraper:

    def test_scrape_tennis_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import TennisESPNScraper

        mock_resolve_leagues.return_value = ["atp"]
        mock_espn_client.get_fixtures.return_value = [
            MockAPIFixture(
                external_id="9001",
                sport="tennis",
                home_team_name="Carlos Alcaraz",
                away_team_name="Jannik Sinner",
            ),
        ]
        mock_espn_client.get_fixture_stats.return_value = [MockAPIMatchStats(
            external_id="9001",
            sport="tennis",
            home_team_name="Carlos Alcaraz",
            away_team_name="Jannik Sinner",
            stats={
                "sets_won": {"home": 2.0, "away": 1.0},
                "games_won": {"home": 19.0, "away": 15.0},
                "total_games": {"home": 19.0, "away": 15.0},
                "total_sets": {"home": 3.0, "away": 3.0},
            },
        )]

        scraper = TennisESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("ATP", "2526")
        assert result > 0

        with session_factory() as session:
            profiles = session.execute(
                text("SELECT stat_key FROM league_profiles")
            ).fetchall()
            stat_keys = [p[0] for p in profiles]
            assert "total_games" in stat_keys or "games_won" in stat_keys


# ---------------------------------------------------------------------------
# Volleyball tests
# ---------------------------------------------------------------------------

class TestVolleyballESPNScraper:

    def test_scrape_team_stats(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        from bet.scrapers.espn import VolleyballESPNScraper

        mock_resolve_leagues.return_value = ["fivb.m"]
        mock_espn_client.get_standings.return_value = [
            {"team_id": "100", "team_name": "Poland", "rank": "1"},
        ]
        mock_espn_client.get_team_last_fixtures.return_value = [
            {"id": "8001", "date": "2026-05-10T18:00Z", "home_team": "Poland", "away_team": "Brazil", "score": "3-1"},
        ]
        mock_espn_client.get_fixture_stats.return_value = [MockAPIMatchStats(
            external_id="8001",
            sport="volleyball",
            home_team_name="Poland",
            away_team_name="Brazil",
            stats={
                "kills": {"home": 55.0, "away": 48.0},
                "aces": {"home": 8.0, "away": 5.0},
                "blocks": {"home": 12.0, "away": 9.0},
                "errors": {"home": 18.0, "away": 22.0},
            },
        )]

        scraper = VolleyballESPNScraper(session_factory)
        result = scraper.scrape_team_season_stats("FIVB", "2526")
        assert result > 0


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestESPNRegistry:

    def test_all_sports_registered(self):
        from bet.scrapers import available_scrapers

        scrapers = available_scrapers()
        for sport in ("football", "basketball", "hockey", "tennis", "volleyball"):
            assert (sport, "espn") in scrapers, f"ESPN not registered for {sport}"

    def test_get_scraper_returns_correct_class(self):
        from bet.scrapers import get_scraper

        cls = get_scraper("football", "espn")
        assert cls.__name__ == "FootballESPNScraper"

        cls = get_scraper("basketball", "espn")
        assert cls.__name__ == "BasketballESPNScraper"

        cls = get_scraper("tennis", "espn")
        assert cls.__name__ == "TennisESPNScraper"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestESPNEdgeCases:

    def test_guess_side(self):
        from bet.scrapers.espn import BaseESPNScraper

        assert BaseESPNScraper._guess_side("Arsenal", "Arsenal FC", "Chelsea FC") == "home"
        assert BaseESPNScraper._guess_side("Chelsea", "Arsenal FC", "Chelsea FC") == "away"
        assert BaseESPNScraper._guess_side("Boston Celtics", "Boston Celtics", "NY Knicks") == "home"

    def test_safe_float(self):
        from bet.scrapers.espn import _safe_float

        assert _safe_float(42.0) == 42.0
        assert _safe_float("65.3%") == 65.3
        assert _safe_float(None) == 0.0
        assert _safe_float("") == 0.0
        assert _safe_float("abc") == 0.0
        assert _safe_float(float("nan")) == 0.0
        assert _safe_float(float("inf")) == 0.0

    def test_scraper_run_tracking(
        self, session_factory, mock_espn_client, mock_resolve_leagues,
    ):
        """Verify scraper_runs table is populated."""
        from bet.scrapers.espn import FootballESPNScraper

        mock_espn_client.get_standings.return_value = MOCK_STANDINGS[:1]
        mock_espn_client.get_team_last_fixtures.return_value = MOCK_FIXTURES_ARSENAL[:1]
        mock_espn_client.get_fixture_stats.return_value = MOCK_MATCH_STATS_1001

        scraper = FootballESPNScraper(session_factory)
        scraper.scrape_team_season_stats("Premier League", "2526")

        with session_factory() as session:
            runs = session.execute(
                text("SELECT scraper_name, sport, status FROM scraper_runs")
            ).fetchall()
            assert len(runs) >= 1
            assert runs[0][0] == "FootballESPNScraper"
            assert runs[0][1] == "football"
            assert runs[0][2] == "success"
