from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text

MOCK_TEAM_HTML = """
<html><body>
<table id="per_game-team">
  <thead><tr><th>Rk</th><th>Team</th><th>G</th><th>PTS</th><th>TRB</th><th>AST</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>Boston Celtics*</td><td>82</td><td>120.6</td><td>46.2</td><td>27.8</td></tr>
    <tr><td>2</td><td>Denver Nuggets</td><td>82</td><td>113.7</td><td>43.8</td><td>28.4</td></tr>
  </tbody>
</table>
</body></html>
"""

MOCK_PLAYER_HTML = """
<html><body>
<table id="per_game_stats">
  <thead><tr><th>Rk</th><th>Player</th><th>Pos</th><th>Age</th><th>Tm</th><th>G</th><th>GS</th><th>MP</th><th>PTS/G</th><th>TRB</th><th>AST</th></tr></thead>
  <tbody>
    <tr><td>1</td><td><a href="/players/t/tatumja01.html">Jayson Tatum</a></td><td>SF</td><td>26</td><td>BOS</td><td>74</td><td>74</td><td>35.8</td><td>26.9</td><td>8.1</td><td>4.9</td></tr>
    <tr class="thead"><td colspan="11">Header Row</td></tr>
    <tr><td>2</td><td><a href="/players/j/jokicni01.html">Nikola Jokic</a></td><td>C</td><td>29</td><td>DEN</td><td>79</td><td>79</td><td>34.6</td><td>26.4</td><td>12.4</td><td>9.0</td></tr>
  </tbody>
</table>
</body></html>
"""


@pytest.fixture
def mock_requests():
    with patch("bet.scrapers.basketball.bball_ref.requests.get") as mock_get:
        yield mock_get


def test_scrape_team_season_stats(session_factory, mock_requests):
    from bet.scrapers.basketball.bball_ref import BasketballBRefScraper

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_TEAM_HTML
    mock_requests.return_value = mock_resp

    scraper = BasketballBRefScraper(session_factory)
    result = scraper.scrape_team_season_stats("NBA", "2425")

    assert result > 0
    with session_factory() as session:
        teams = session.execute(text("SELECT name FROM teams ORDER BY name")).fetchall()
        team_names = [t[0] for t in teams]
        assert "Boston Celtics" in team_names
        assert "Denver Nuggets" in team_names


def test_scrape_player_season_stats(session_factory, mock_requests):
    from bet.scrapers.basketball.bball_ref import BasketballBRefScraper

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = MOCK_PLAYER_HTML
    mock_requests.return_value = mock_resp

    scraper = BasketballBRefScraper(session_factory)
    result = scraper.scrape_player_season_stats("NBA", "2425")

    assert result == 2
    with session_factory() as session:
        athletes = session.execute(text("SELECT name FROM athletes ORDER BY name")).fetchall()
        names = [a[0] for a in athletes]
        assert "Jayson Tatum" in names
        assert "Nikola Jokic" in names

        from bet.scrapers.models import PlayerSeasonStat
        tatum = session.query(PlayerSeasonStat).filter(
            PlayerSeasonStat.games_played == 74
        ).first()
        assert tatum is not None
        assert tatum.games_started == 74
