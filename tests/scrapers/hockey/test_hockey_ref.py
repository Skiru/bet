"""Tests for HockeyRefScraper — mocked HTML responses."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock

from bet.scrapers.hockey.hockey_ref import HockeyRefScraper
from bet.scrapers.models import PlayerSeasonStat


TEAM_HTML = """
<html><body>
<table id="stats">
<thead><tr><th>Rk</th><th>Team</th><th>GP</th><th>W</th><th>L</th><th>PTS</th><th>GF</th><th>GA</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href="/teams/EDM/">Edmonton Oilers*</a></td><td>82</td><td>52</td><td>20</td><td>114</td><td>300</td><td>220</td></tr>
<tr><td>2</td><td><a href="/teams/TOR/">Toronto Maple Leafs</a></td><td>82</td><td>48</td><td>24</td><td>106</td><td>280</td><td>240</td></tr>
</tbody>
</table>
</body></html>
"""

PLAYER_HTML = """
<html><body>
<table id="stats">
<thead><tr><th>Rk</th><th>Player</th><th>Pos</th><th>Tm</th><th>GP</th><th>G</th><th>A</th><th>PTS</th><th>+/-</th><th>PIM</th><th>S</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href="/players/m/mcdavco01.html">Connor McDavid</a></td><td>C</td><td>EDM</td><td>82</td><td>64</td><td>89</td><td>153</td><td>32</td><td>36</td><td>350</td></tr>
<tr><td>2</td><td><a href="/players/d/draisle01.html">Leon Draisaitl</a></td><td>C</td><td>EDM</td><td>80</td><td>55</td><td>70</td><td>125</td><td>24</td><td>40</td><td>290</td></tr>
</tbody>
</table>
</body></html>
"""


def _mock_get(url, **kwargs):
    mock = MagicMock()
    mock.status_code = 200
    if "skaters" in url:
        mock.text = PLAYER_HTML
    else:
        mock.text = TEAM_HTML
    return mock


class TestHockeyRefTeamStats:
    @patch("bet.scrapers.hockey.hockey_ref.requests.get", side_effect=_mock_get)
    def test_scrape_team_season_stats(self, mock_req, session_factory):
        scraper = HockeyRefScraper(session_factory)
        count = scraper.scrape_team_season_stats("NHL", "2025")
        assert count > 0

    @patch("bet.scrapers.hockey.hockey_ref.requests.get", side_effect=_mock_get)
    def test_scrape_player_season_stats(self, mock_req, session_factory):
        scraper = HockeyRefScraper(session_factory)
        count = scraper.scrape_player_season_stats("NHL", "2025")
        assert count >= 2
        with session_factory() as session:
            rows = session.query(PlayerSeasonStat).all()
            assert len(rows) >= 2
            stats = json.loads(rows[0].stats_json)
            assert "goals" in stats
            assert stats["goals"] == 64.0
