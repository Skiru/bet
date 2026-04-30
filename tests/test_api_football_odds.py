"""Unit tests for APIFootballOddsClient with mocked API responses."""

from unittest.mock import MagicMock, patch

import pytest

from scripts.api_clients.rate_limiter import RateLimiter
from scripts.api_clients.api_football_odds import APIFootballOddsClient, BET_TYPE_MAP


# ---------------------------------------------------------------------------
# Fixtures (pytest)
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_usage_dir(tmp_path):
    return tmp_path / "usage"


@pytest.fixture
def rate_limiter(tmp_usage_dir):
    return RateLimiter(usage_dir=tmp_usage_dir)


@pytest.fixture
def cache_dir(tmp_path):
    return tmp_path / "cache"


@pytest.fixture
def client(rate_limiter, cache_dir):
    with patch.object(APIFootballOddsClient, "_load_api_key", return_value="test-key-123"):
        c = APIFootballOddsClient(rate_limiter=rate_limiter)
    c._test_cache_dir = cache_dir
    return c


@pytest.fixture
def client_no_key(rate_limiter, cache_dir):
    with patch.object(APIFootballOddsClient, "_load_api_key", return_value=None):
        c = APIFootballOddsClient(rate_limiter=rate_limiter)
    c._test_cache_dir = cache_dir
    return c


@pytest.fixture(autouse=True)
def _isolate_cache(cache_dir):
    """Patch CACHE_DIR for test isolation."""
    with patch("scripts.api_clients.base_client.CACHE_DIR", cache_dir), \
         patch("scripts.api_clients.api_football_odds.CACHE_DIR", cache_dir):
        yield


# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

def _make_odds_response(items, page=1, total_pages=1):
    """Build a paginated /odds response."""
    return {
        "response": items,
        "paging": {"current": page, "total": total_pages},
    }


FIXTURE_ODDS_ITEM = {
    "fixture": {
        "id": 99001,
        "date": "2026-04-29T18:00:00+00:00",
        "home": "Liverpool",
        "away": "Arsenal",
    },
    "league": {"id": 39, "name": "Premier League"},
    "bookmakers": [
        {
            "id": 1,
            "name": "Bet365",
            "bets": [
                {
                    "id": 1,
                    "name": "Match Winner",
                    "values": [
                        {"value": "Home", "odd": "1.50"},
                        {"value": "Draw", "odd": "3.40"},
                        {"value": "Away", "odd": "5.00"},
                    ],
                },
                {
                    "id": 5,
                    "name": "Goals Over/Under",
                    "values": [
                        {"value": "Over 2.5", "odd": "1.80"},
                        {"value": "Under 2.5", "odd": "2.00"},
                    ],
                },
                {
                    "id": 99,
                    "name": "Some Other Market",
                    "values": [
                        {"value": "Yes", "odd": "1.90"},
                    ],
                },
            ],
        },
    ],
}

FIXTURE_ODDS_ITEM_2 = {
    "fixture": {
        "id": 99002,
        "date": "2026-04-29T20:00:00+00:00",
        "home": "Barcelona",
        "away": "Real Madrid",
    },
    "league": {"id": 140, "name": "La Liga"},
    "bookmakers": [
        {
            "id": 2,
            "name": "William Hill",
            "bets": [
                {
                    "id": 1,
                    "name": "Match Winner",
                    "values": [
                        {"value": "Home", "odd": "2.10"},
                        {"value": "Draw", "odd": "3.20"},
                        {"value": "Away", "odd": "3.00"},
                    ],
                },
            ],
        },
    ],
}


# ---------------------------------------------------------------------------
# Tests: single-page response
# ---------------------------------------------------------------------------

class TestSinglePage:
    def test_converts_to_snapshot_format(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_odds_response([FIXTURE_ODDS_ITEM])

        with patch("requests.get", return_value=mock_resp):
            events = client.fetch_odds_for_date("2026-04-29")

        assert len(events) == 1
        ev = events[0]
        assert ev["id"] == "99001"
        assert ev["sport_key"] == "soccer_api_football"
        assert ev["sport_title"] == "Premier League"
        assert ev["commence_time"] == "2026-04-29T18:00:00+00:00"
        assert ev["home_team"] == "Liverpool"
        assert ev["away_team"] == "Arsenal"
        assert ev["_our_sport"] == "football"
        assert ev["_odds_source"] == "api-football"
        assert ev["_sport_key"] == "soccer_api_football"

        # Bookmaker structure
        assert len(ev["bookmakers"]) == 1
        bm = ev["bookmakers"][0]
        assert bm["key"] == "bet365"
        assert bm["title"] == "Bet365"

        # Markets — only h2h and totals (bet IDs 1 and 5), not 99
        market_keys = [m["key"] for m in bm["markets"]]
        assert "h2h" in market_keys
        assert "totals" in market_keys
        assert len(bm["markets"]) == 2

    def test_h2h_outcomes(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_odds_response([FIXTURE_ODDS_ITEM])

        with patch("requests.get", return_value=mock_resp):
            events = client.fetch_odds_for_date("2026-04-29")

        bm = events[0]["bookmakers"][0]
        h2h = next(m for m in bm["markets"] if m["key"] == "h2h")
        assert len(h2h["outcomes"]) == 3
        assert h2h["outcomes"][0] == {"name": "Home", "price": 1.50}
        assert h2h["outcomes"][1] == {"name": "Draw", "price": 3.40}
        assert h2h["outcomes"][2] == {"name": "Away", "price": 5.00}

    def test_totals_outcomes(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_odds_response([FIXTURE_ODDS_ITEM])

        with patch("requests.get", return_value=mock_resp):
            events = client.fetch_odds_for_date("2026-04-29")

        bm = events[0]["bookmakers"][0]
        totals = next(m for m in bm["markets"] if m["key"] == "totals")
        assert len(totals["outcomes"]) == 2
        assert totals["outcomes"][0] == {"name": "Over 2.5", "price": 1.80}
        assert totals["outcomes"][1] == {"name": "Under 2.5", "price": 2.00}


# ---------------------------------------------------------------------------
# Tests: multi-page pagination
# ---------------------------------------------------------------------------

class TestPagination:
    def test_two_pages(self, client):
        page1_resp = MagicMock()
        page1_resp.status_code = 200
        page1_resp.json.return_value = _make_odds_response(
            [FIXTURE_ODDS_ITEM], page=1, total_pages=2
        )

        page2_resp = MagicMock()
        page2_resp.status_code = 200
        page2_resp.json.return_value = _make_odds_response(
            [FIXTURE_ODDS_ITEM_2], page=2, total_pages=2
        )

        with patch("requests.get", side_effect=[page1_resp, page2_resp]):
            events = client.fetch_odds_for_date("2026-04-29")

        assert len(events) == 2
        assert events[0]["id"] == "99001"
        assert events[1]["id"] == "99002"
        assert events[1]["sport_title"] == "La Liga"


# ---------------------------------------------------------------------------
# Tests: empty response
# ---------------------------------------------------------------------------

class TestEmptyResponse:
    def test_empty_returns_empty_list(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_odds_response([])

        with patch("requests.get", return_value=mock_resp):
            events = client.fetch_odds_for_date("2026-04-29")

        assert events == []


# ---------------------------------------------------------------------------
# Tests: no API key
# ---------------------------------------------------------------------------

class TestNoApiKey:
    def test_no_key_returns_empty(self, client_no_key):
        events = client_no_key.fetch_odds_for_date("2026-04-29")
        assert events == []


# ---------------------------------------------------------------------------
# Tests: bet type mapping
# ---------------------------------------------------------------------------

class TestBetTypeMapping:
    def test_known_mappings(self):
        assert BET_TYPE_MAP[1] == "h2h"
        assert BET_TYPE_MAP[5] == "totals"
        assert BET_TYPE_MAP[6] == "totals_corners"

    def test_unknown_bet_id_ignored(self, client):
        """Fixture with only an unknown bet type produces no bookmakers → filtered out."""
        item = {
            "fixture": {"id": 88888, "date": "2026-04-29T12:00:00+00:00", "home": "A", "away": "B"},
            "league": {"id": 1, "name": "Test League"},
            "bookmakers": [
                {
                    "id": 10,
                    "name": "NoMarkets Bookie",
                    "bets": [
                        {
                            "id": 999,
                            "name": "Unknown Market",
                            "values": [{"value": "X", "odd": "2.00"}],
                        }
                    ],
                }
            ],
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _make_odds_response([item])

        with patch("requests.get", return_value=mock_resp):
            events = client.fetch_odds_for_date("2026-04-29")

        # Item is filtered out because no supported markets → no bookmakers
        assert events == []
