from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text


@pytest.fixture
def mock_nba_api():
    """Patch all three nba_api endpoints used by the scraper."""
    with (
        patch("bet.scrapers.basketball.nba_api_scraper.leaguedashteamstats") as mock_team,
        patch("bet.scrapers.basketball.nba_api_scraper.leaguedashplayerstats") as mock_player,
        patch("bet.scrapers.basketball.nba_api_scraper.playergamelog") as mock_gl,
    ):
        yield {"team": mock_team, "player": mock_player, "gamelog": mock_gl}


def test_scrape_team_season_stats(session_factory, mock_nba_api):
    from bet.scrapers.basketball.nba_api_scraper import BasketballNBAScraper

    df = pd.DataFrame({
        "TEAM_NAME": ["Los Angeles Lakers", "Boston Celtics"],
        "W": [50, 55],
        "L": [32, 27],
        "PTS": [115.2, 118.1],
        "REB": [44.3, 46.1],
        "AST": [27.5, 29.0],
    })
    mock_nba_api["team"].LeagueDashTeamStats.return_value.get_data_frames.return_value = [df]

    scraper = BasketballNBAScraper(session_factory)
    result = scraper.scrape_team_season_stats("NBA", "2425")

    assert result > 0
    with session_factory() as session:
        teams = session.execute(text("SELECT name FROM teams ORDER BY name")).fetchall()
        assert len(teams) == 2
        assert teams[0][0] == "Boston Celtics"

        profiles = session.execute(
            text("SELECT stat_key, avg_value FROM league_profiles WHERE stat_key = 'pts'")
        ).fetchall()
        assert len(profiles) >= 1


def test_scrape_player_season_stats(session_factory, mock_nba_api):
    from bet.scrapers.basketball.nba_api_scraper import BasketballNBAScraper

    df = pd.DataFrame({
        "PLAYER_ID": [201939, 203507],
        "PLAYER_NAME": ["Stephen Curry", "Giannis Antetokounmpo"],
        "TEAM_ABBREVIATION": ["GSW", "MIL"],
        "GP": [74, 73],
        "GS": [74, 73],
        "MIN": [32.7, 35.2],
        "PTS": [26.4, 30.4],
        "REB": [5.1, 11.5],
        "AST": [5.1, 6.5],
        "STL": [1.0, 1.2],
        "BLK": [0.4, 1.1],
        "TOV": [3.2, 3.4],
        "FGM": [8.8, 11.2],
        "FGA": [19.5, 20.1],
        "FG_PCT": [0.451, 0.557],
    })
    mock_nba_api["player"].LeagueDashPlayerStats.return_value.get_data_frames.return_value = [df]

    scraper = BasketballNBAScraper(session_factory)
    result = scraper.scrape_player_season_stats("NBA", "2425")

    assert result == 2
    with session_factory() as session:
        athletes = session.execute(text("SELECT name FROM athletes ORDER BY name")).fetchall()
        assert len(athletes) == 2

        from bet.scrapers.models import PlayerSeasonStat
        stats = session.query(PlayerSeasonStat).all()
        assert len(stats) == 2
        curry = session.query(PlayerSeasonStat).filter(
            PlayerSeasonStat.games_played == 74
        ).first()
        assert curry is not None
        assert "pts" in curry.stats_json
