from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text

MOCK_CSV = """tourney_id,tourney_name,surface,tourney_date,winner_id,winner_name,loser_id,loser_name,score,w_ace,w_df,w_svpt,w_1stIn,w_1stWon,w_2ndWon,w_bpSaved,w_bpFaced,l_ace,l_df,l_svpt,l_1stIn,l_1stWon,l_2ndWon,l_bpSaved,l_bpFaced
2025-9900,Australian Open,Hard,20250112,104925,Jannik Sinner,104745,Alexander Zverev,6-3 7-6 6-3,12,2,80,50,42,18,4,5,8,4,75,45,35,15,3,6
2025-9900,Australian Open,Hard,20250112,104745,Alexander Zverev,106421,Tommy Paul,7-6 3-6 6-4 7-6,15,3,90,55,48,20,5,7,6,5,85,52,40,16,4,8
"""


@pytest.fixture
def mock_requests():
    with patch("bet.scrapers.tennis.sackmann.requests.get") as mock_get:
        yield mock_get


def test_scrape_player_season_stats(session_factory, mock_requests):
    from bet.scrapers.tennis.sackmann import TennisSackmannScraper

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_CSV
    mock_requests.return_value = mock_resp

    scraper = TennisSackmannScraper(session_factory)
    result = scraper.scrape_player_season_stats("ATP", "2025")

    # 3 unique players: Sinner (1W), Zverev (1W+1L=2 matches), Tommy Paul (1L)
    assert result == 3
    with session_factory() as session:
        athletes = session.execute(text("SELECT name FROM athletes ORDER BY name")).fetchall()
        names = [a[0] for a in athletes]
        assert "Jannik Sinner" in names
        assert "Alexander Zverev" in names
        assert "Tommy Paul" in names

        from bet.scrapers.models import PlayerSeasonStat
        all_stats = session.query(PlayerSeasonStat).all()
        # Sinner: 1 win, 0 losses
        # Zverev: 1 win, 1 loss
        # Tommy Paul: 0 wins, 1 loss
        assert len(all_stats) == 3  # 3 players total


def test_scrape_player_match_stats(session_factory, mock_requests):
    from bet.scrapers.tennis.sackmann import TennisSackmannScraper

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_CSV
    mock_requests.return_value = mock_resp

    scraper = TennisSackmannScraper(session_factory)
    result = scraper.scrape_player_match_stats("ATP", "2025")

    # 2 matches × 2 players per match = 4 gamelogs
    assert result == 4
    with session_factory() as session:
        gamelogs = session.execute(text("SELECT * FROM player_gamelogs")).fetchall()
        assert len(gamelogs) == 4

        wins = session.execute(
            text("SELECT COUNT(*) FROM player_gamelogs WHERE result = 'W'")
        ).fetchone()
        assert wins[0] == 2

        losses = session.execute(
            text("SELECT COUNT(*) FROM player_gamelogs WHERE result = 'L'")
        ).fetchone()
        assert losses[0] == 2


def test_scrape_team_season_stats_noop(session_factory, mock_requests):
    from bet.scrapers.tennis.sackmann import TennisSackmannScraper

    scraper = TennisSackmannScraper(session_factory)
    assert scraper.scrape_team_season_stats("ATP", "2025") == 0
