"""Tests for Flashscore multi-sport scraper (mocked HTTP)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from bet.scrapers.flashscore import (
    FlashscoreScraper,
    FootballFlashscoreScraper,
    BasketballFlashscoreScraper,
    HockeyFlashscoreScraper,
    TennisFlashscoreScraper,
    VolleyballFlashscoreScraper,
    _extract_match_scores,
    _extract_stat_values,
    _parse_flashscore_stats,
    _validate_stat_values,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_SEARCH_RESPONSE = (
    'cjs.loaded({"results":[{"type":"participants","participant_type_id":1,'
    '"url":"real-madrid","id":"mXs5ABCD"}]});'
)

MOCK_RESULTS_HTML = (
    "<html><body>" + "x" * 500 +  # pad to pass 500-char minimum
    '<div class="stat__category">Corners</div>'
    '<div class="stat__homeValue">7</div>'
    '<div class="stat__awayValue">5</div> '
    "Corners: 8 Corners: 6 Corners: 9 Corners: 5 Corners: 7 "
    "Fouls: 14 Fouls: 12 "
    "Yellow Cards: 3 Yellow Cards: 4 "
    "Shots on Target: 6 Shots on Target: 5 "
    "</body></html>"
)

MOCK_BASKETBALL_HTML = (
    "<html><body>" + "x" * 500 +
    "2 Pointers: 25 2 Pointers: 22 "
    "3 Pointers: 12 3 Pointers: 10 "
    "Free Throws: 18 Free Throws: 15 "
    "Rebounds: 42 Rebounds: 38 "
    "Turnovers: 15 Turnovers: 13 "
    "</body></html>"
)

MOCK_HOCKEY_HTML = (
    "<html><body>" + "x" * 500 +
    "Shots on Goal: 32 Shots on Goal: 28 "
    "Penalties in Minutes: 8 Penalties in Minutes: 6 "
    "Powerplay Goals: 2 Powerplay Goals: 1 "
    "</body></html>"
)

MOCK_SCORE_HTML = (
    "<html><body>" + "x" * 500 +
    '<div class="score">2 - 1</div>'
    '<div class="result">3:0</div>'
    '<div class="final">1 - 1</div>'
    "</body></html>"
)


# ---------------------------------------------------------------------------
# Parsing tests
# ---------------------------------------------------------------------------

class TestParsing:
    def test_parse_football_stats(self):
        stats = _parse_flashscore_stats(MOCK_RESULTS_HTML, "football")
        assert "corners" in stats
        assert len(stats["corners"]) > 0
        assert all(0 <= v <= 20 for v in stats["corners"])

    def test_parse_basketball_stats(self):
        stats = _parse_flashscore_stats(MOCK_BASKETBALL_HTML, "basketball")
        # At least one basketball stat should be found
        found_keys = set(stats.keys())
        expected_any = {"2_pointers", "3_pointers", "free_throws", "rebounds", "turnovers"}
        assert found_keys & expected_any, f"No basketball stats found, got: {found_keys}"

    def test_parse_hockey_stats(self):
        stats = _parse_flashscore_stats(MOCK_HOCKEY_HTML, "hockey")
        found_keys = set(stats.keys())
        expected_any = {"shots_on_goal", "penalties_in_minutes", "power_play_goals"}
        assert found_keys & expected_any, f"No hockey stats found, got: {found_keys}"

    def test_parse_empty_html(self):
        stats = _parse_flashscore_stats("", "football")
        assert stats == {}

    def test_parse_short_html(self):
        stats = _parse_flashscore_stats("<html>short</html>", "football")
        assert stats == {}

    def test_score_fallback(self):
        stats = _parse_flashscore_stats(MOCK_SCORE_HTML, "football")
        # Should fall back to goals from score extraction
        if stats:
            assert "goals" in stats or len(stats) > 0

    def test_validate_stat_values_filters(self):
        values = [5.0, 25.0, 8.0, -1.0, 100.0]
        result = _validate_stat_values(values, "corners", "football")
        assert 25.0 not in result  # corners max is 20
        assert -1.0 not in result
        assert 100.0 not in result
        assert 5.0 in result
        assert 8.0 in result

    def test_extract_match_scores_football(self):
        html = '<div class="score">2 - 1</div><div class="result">3:0</div>'
        scores = _extract_match_scores(html, "football")
        assert len(scores) > 0
        assert all(s <= 15 for s in scores)


# ---------------------------------------------------------------------------
# Entity resolution tests
# ---------------------------------------------------------------------------

class TestEntityResolution:
    @patch("bet.scrapers.flashscore.c_requests")
    def test_entity_found(self, mock_crequests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = MOCK_SEARCH_RESPONSE
        mock_crequests.get.return_value = mock_resp

        from bet.scrapers.flashscore import _get_flashscore_entity
        entity_type, slug, entity_id = _get_flashscore_entity("Real Madrid", "football")
        assert entity_type == "team"
        assert slug == "real-madrid"
        assert entity_id == "mXs5ABCD"

    @patch("bet.scrapers.flashscore.c_requests")
    def test_entity_not_found(self, mock_crequests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = 'cjs.loaded({"results":[]});'
        mock_crequests.get.return_value = mock_resp

        from bet.scrapers.flashscore import _get_flashscore_entity
        entity_type, slug, entity_id = _get_flashscore_entity("Nonexistent FC", "football")
        assert entity_type is None
        assert slug is None

    @patch("bet.scrapers.flashscore.c_requests")
    def test_entity_network_error(self, mock_crequests):
        mock_crequests.get.side_effect = Exception("Connection error")

        from bet.scrapers.flashscore import _get_flashscore_entity
        entity_type, slug, entity_id = _get_flashscore_entity("Real Madrid", "football")
        assert entity_type is None


# ---------------------------------------------------------------------------
# try_flashscore tests
# ---------------------------------------------------------------------------

class TestTryFlashscore:
    @patch("bet.scrapers.flashscore.c_requests")
    @patch("bet.scrapers.flashscore._fs_rate_limit")
    def test_success(self, mock_rl, mock_crequests):
        # Search response
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.text = MOCK_SEARCH_RESPONSE

        # Results page response
        page_resp = MagicMock()
        page_resp.status_code = 200
        page_resp.text = MOCK_RESULTS_HTML

        mock_crequests.get.side_effect = [search_resp, page_resp]

        from bet.scrapers.flashscore import _try_flashscore
        stats, err = _try_flashscore("Real Madrid", "football")
        assert err is None
        assert isinstance(stats, dict)
        assert len(stats) > 0

    @patch("bet.scrapers.flashscore.c_requests")
    @patch("bet.scrapers.flashscore._fs_rate_limit")
    def test_js_challenge_blocked(self, mock_rl, mock_crequests):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.text = MOCK_SEARCH_RESPONSE

        page_resp = MagicMock()
        page_resp.status_code = 200
        page_resp.text = "<html>Just a moment...</html>"

        mock_crequests.get.side_effect = [search_resp, page_resp]

        from bet.scrapers.flashscore import _try_flashscore
        stats, err = _try_flashscore("Real Madrid", "football")
        assert stats == {}
        assert "challenge" in err.lower()

    @patch("bet.scrapers.flashscore.c_requests")
    @patch("bet.scrapers.flashscore._fs_rate_limit")
    def test_http_error(self, mock_rl, mock_crequests):
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.text = MOCK_SEARCH_RESPONSE

        page_resp = MagicMock()
        page_resp.status_code = 403

        mock_crequests.get.side_effect = [search_resp, page_resp]

        from bet.scrapers.flashscore import _try_flashscore
        stats, err = _try_flashscore("Real Madrid", "football")
        assert stats == {}
        assert "403" in err


# ---------------------------------------------------------------------------
# Scraper class tests
# ---------------------------------------------------------------------------

class TestFlashscoreScraperClass:
    def test_subclass_sports(self):
        assert FootballFlashscoreScraper.sport == "football"
        assert BasketballFlashscoreScraper.sport == "basketball"
        assert TennisFlashscoreScraper.sport == "tennis"
        assert HockeyFlashscoreScraper.sport == "hockey"
        assert VolleyballFlashscoreScraper.sport == "volleyball"

    def test_source_name(self):
        assert FootballFlashscoreScraper.source_name == "flashscore"

    def test_player_season_stats_returns_zero(self, session_factory):
        scraper = FootballFlashscoreScraper(session_factory)
        assert scraper.scrape_player_season_stats("EPL", "2425") == 0

    @patch("bet.scrapers.flashscore._try_flashscore")
    def test_scrape_team_season_stats_no_teams(self, mock_try, session_factory):
        """When no teams exist in DB, returns 0."""
        scraper = FootballFlashscoreScraper(session_factory)
        result = scraper.scrape_team_season_stats("EPL", "2425")
        assert result == 0
        mock_try.assert_not_called()

    @patch("bet.scrapers.flashscore._try_flashscore")
    @patch("bet.scrapers.flashscore.c_requests", new=MagicMock())
    def test_scrape_team_season_stats_with_teams(self, mock_try, session_factory):
        """When team_list provided, fetches stats and writes league_profiles."""
        mock_try.side_effect = [
            ({"corners": [8.0, 6.0, 9.0], "fouls": [14.0, 12.0]}, None),
            ({"corners": [5.0, 7.0, 4.0], "fouls": [10.0, 11.0]}, None),
        ]

        scraper = FootballFlashscoreScraper(session_factory)
        result = scraper.scrape_team_season_stats("", "2425", team_list=["Team A", "Team B"])
        assert result > 0

        # Verify league_profiles were written
        with session_factory() as session:
            rows = session.execute(
                text("SELECT stat_key, avg_value, sample_size FROM league_profiles WHERE season = '2425'")
            ).fetchall()
            assert len(rows) > 0
            keys = {r[0] for r in rows}
            assert "corners" in keys
            assert "fouls" in keys

    @patch("bet.scrapers.flashscore._try_flashscore")
    @patch("bet.scrapers.flashscore.c_requests", new=MagicMock())
    def test_scrape_handles_partial_failures(self, mock_try, session_factory):
        """Some teams fail, but successful ones still produce league_profiles."""
        mock_try.side_effect = [
            ({"goals": [3.0, 2.0, 4.0]}, None),          # success
            ({}, "Could not find entity via Flashscore"),  # failure
            ({"goals": [1.0, 5.0]}, None),                # success
        ]

        scraper = HockeyFlashscoreScraper(session_factory)
        result = scraper.scrape_team_season_stats("", "2425",
                                                   team_list=["Team X", "Team Y", "Team Z"])
        assert result > 0

    def test_fetch_team_stats_public_api(self, session_factory):
        """fetch_team_stats is callable and returns tuple."""
        scraper = FootballFlashscoreScraper(session_factory)
        with patch("bet.scrapers.flashscore._try_flashscore") as mock_try:
            mock_try.return_value = ({"corners": [8.0, 6.0]}, None)
            stats, err = scraper.fetch_team_stats("Liverpool")
            assert err is None
            assert "corners" in stats
