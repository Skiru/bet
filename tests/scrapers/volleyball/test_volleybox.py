"""Tests for VolleyboxScraper — mocked HTML responses."""
from __future__ import annotations

import json

import pytest
from unittest.mock import patch, MagicMock

from bet.scrapers.volleyball.volleybox import VolleyboxScraper
from bet.scrapers.models import PlayerSeasonStat


STANDINGS_HTML = """
<html><body>
<table class="standing-table">
<thead><tr><th>#</th><th>Team</th><th>GP</th><th>W</th><th>L</th><th>Pts</th></tr></thead>
<tbody>
<tr><td>1</td><td>Jastrzębski Węgiel</td><td>30</td><td>25</td><td>5</td><td>72</td></tr>
<tr><td>2</td><td>ZAKSA Kędzierzyn-Koźle</td><td>30</td><td>23</td><td>7</td><td>66</td></tr>
</tbody>
</table>
</body></html>
"""

PLAYERS_HTML = """
<html><body>
<table class="player-stats">
<thead><tr><th>#</th><th>Player</th><th>Pos</th><th>Team</th><th>GP</th><th>Pts</th><th>Aces</th><th>Blk</th><th>Att%</th></tr></thead>
<tbody>
<tr><td>1</td><td><a href="/player/wilfredo-leon">Wilfredo León</a></td><td>OH</td><td>Jastrzębski Węgiel</td><td>28</td><td>512</td><td>45</td><td>38</td><td>56,2</td></tr>
<tr><td>2</td><td><a href="/player/bartosz-kurek">Bartosz Kurek</a></td><td>OP</td><td>ZAKSA Kędzierzyn-Koźle</td><td>30</td><td>480</td><td>32</td><td>42</td><td>53,8</td></tr>
</tbody>
</table>
</body></html>
"""


def _mock_get(url, **kwargs):
    mock = MagicMock()
    mock.status_code = 200
    if "/players" in url:
        mock.text = PLAYERS_HTML
    else:
        mock.text = STANDINGS_HTML
    return mock


class TestVolleyboxTeamStats:
    @patch("bet.scrapers.volleyball.volleybox.requests.get", side_effect=_mock_get)
    def test_scrape_team_season_stats(self, mock_req, session_factory):
        scraper = VolleyboxScraper(session_factory)
        count = scraper.scrape_team_season_stats("plusliga", "2024-2025")
        assert count > 0

    @patch("bet.scrapers.volleyball.volleybox.requests.get", side_effect=_mock_get)
    def test_scrape_player_season_stats(self, mock_req, session_factory):
        scraper = VolleyboxScraper(session_factory)
        count = scraper.scrape_player_season_stats("plusliga", "2024-2025")
        assert count >= 2
        with session_factory() as session:
            rows = session.query(PlayerSeasonStat).all()
            assert len(rows) >= 2
            stats = json.loads(rows[0].stats_json)
            assert "points" in stats
            assert stats["aces"] == 45.0
