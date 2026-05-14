import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

from bet.scrapers.football.fbref import FootballFBrefScraper
from sqlalchemy import text

@pytest.fixture
def mock_soccerdata():
    with patch("bet.scrapers.football.fbref.sd.FBref") as mock:
        yield mock

def test_scrape_team_season_stats(session_factory, mock_soccerdata):
    # Mock data structure matching soccerdata output
    df = pd.DataFrame(
        {
            ("Standard", "MP"): [38, 38],
            ("Standard", "Poss"): [55.5, 45.0],
        },
        index=pd.MultiIndex.from_tuples([
            ("ENG-Premier League", "2425", "Arsenal"),
            ("ENG-Premier League", "2425", "Aston Villa")
        ])
    )
    
    instance = mock_soccerdata.return_value
    instance.read_team_season_stats.return_value = df
    
    scraper = FootballFBrefScraper(session_factory)
    inserted = scraper.scrape_team_season_stats("ENG-Premier League", "2425")
    
    assert inserted == 2  # 2 unique stat keys (averaged across 2 teams)

    with session_factory() as session:
        # Check teams
        teams = session.execute(text("SELECT name FROM teams order by name")).fetchall()
        assert len(teams) == 2
        assert teams[0][0] == "Arsenal"
        assert teams[1][0] == "Aston Villa"
        
        # Check league_profiles (team season aggregates stored here)
        stats = session.execute(text("SELECT stat_key, avg_value FROM league_profiles WHERE stat_key = 'standard_poss'")).fetchall()
        # Two teams' Poss values are upserted for the same competition+stat_key, so last write wins
        assert len(stats) >= 1

def test_scrape_player_season_stats(session_factory, mock_soccerdata):
    df = pd.DataFrame(
        {
            ("Standard", "Pos"): ["FW", "MF"],
            ("Playing Time", "MP"): [38, 36],
            ("Playing Time", "Starts"): [38, 35],
            ("Playing Time", "Min"): [3400.0, 3100.0],
            ("Performance", "Gls"): [20, 5],
        },
        index=pd.MultiIndex.from_tuples([
            ("ENG-Premier League", "2425", "Arsenal", "Bukayo Saka"),
            ("ENG-Premier League", "2425", "Arsenal", "Martin Odegaard")
        ])
    )
    
    instance = mock_soccerdata.return_value
    instance.read_player_season_stats.return_value = df
    
    scraper = FootballFBrefScraper(session_factory)
    inserted = scraper.scrape_player_season_stats("ENG-Premier League", "2425")
    
    assert inserted == 2

    with session_factory() as session:
        athletes = session.execute(text("SELECT name, position FROM athletes order by name")).fetchall()
        assert len(athletes) == 2
        
        # Check stats using ORM
        from bet.scrapers.models import PlayerSeasonStat
        stat_records = session.query(PlayerSeasonStat).all()
        assert len(stat_records) == 2
        
        # Ensure playing time parsed correctly
        saka_stat = session.query(PlayerSeasonStat).filter(PlayerSeasonStat.games_played == 38).first()
        assert saka_stat.games_started == 38
        assert saka_stat.minutes_played == 3400.0
        assert "performance_gls" in saka_stat.stats_json
