"""Unit tests for APIFootballClient with mocked API responses."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.api_clients.rate_limiter import RateLimiter
from scripts.api_clients.api_football import APIFootballClient, STAT_TYPE_MAP
from scripts.normalize_stats import NormalizedFixture, NormalizedMatchStats


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
    with patch.object(APIFootballClient, "_load_api_key", return_value="test-key-123"):
        c = APIFootballClient(rate_limiter=rate_limiter)
    c._test_cache_dir = cache_dir
    return c


@pytest.fixture
def client_no_key(rate_limiter, cache_dir):
    with patch.object(APIFootballClient, "_load_api_key", return_value=None):
        c = APIFootballClient(rate_limiter=rate_limiter)
    c._test_cache_dir = cache_dir
    return c


@pytest.fixture(autouse=True)
def _isolate_cache(cache_dir):
    """Patch CACHE_DIR in both base_client and api_football modules for test isolation."""
    with patch("scripts.api_clients.base_client.CACHE_DIR", cache_dir), \
         patch("scripts.api_clients.api_football.CACHE_DIR", cache_dir):
        yield


# ---------------------------------------------------------------------------
# Sample API responses
# ---------------------------------------------------------------------------

SAMPLE_FIXTURES_RESPONSE = {
    "response": [
        {
            "fixture": {
                "id": 12345,
                "date": "2026-04-28T15:00:00+00:00",
                "status": {"short": "NS"},
            },
            "league": {"id": 39, "name": "Premier League", "country": "England"},
            "teams": {
                "home": {"id": 40, "name": "Liverpool"},
                "away": {"id": 42, "name": "Arsenal"},
            },
        },
        {
            "fixture": {
                "id": 12346,
                "date": "2026-04-28T17:30:00+00:00",
                "status": {"short": "NS"},
            },
            "league": {"id": 39, "name": "Premier League", "country": "England"},
            "teams": {
                "home": {"id": 33, "name": "Manchester United"},
                "away": {"id": 50, "name": "Manchester City"},
            },
        },
    ]
}

SAMPLE_STATS_RESPONSE = {
    "response": [
        {
            "team": {"id": 40, "name": "Liverpool"},
            "statistics": [
                {"type": "Corner Kicks", "value": 7},
                {"type": "Fouls", "value": 12},
                {"type": "Yellow Cards", "value": 2},
                {"type": "Total Shots", "value": 15},
                {"type": "Shots on Goal", "value": 6},
                {"type": "Ball Possession", "value": "58%"},
                {"type": "Offsides", "value": 3},
                {"type": "Goalkeeper Saves", "value": 4},
            ],
        },
        {
            "team": {"id": 42, "name": "Arsenal"},
            "statistics": [
                {"type": "Corner Kicks", "value": 4},
                {"type": "Fouls", "value": 10},
                {"type": "Yellow Cards", "value": 3},
                {"type": "Total Shots", "value": 12},
                {"type": "Shots on Goal", "value": 5},
                {"type": "Ball Possession", "value": "42%"},
                {"type": "Offsides", "value": 1},
                {"type": "Goalkeeper Saves", "value": 5},
            ],
        },
    ]
}

SAMPLE_H2H_RESPONSE = {
    "response": [
        {
            "fixture": {
                "id": 11111,
                "date": "2026-01-15T15:00:00+00:00",
                "status": {"short": "FT"},
            },
            "league": {"id": 39, "name": "Premier League", "country": "England"},
            "teams": {
                "home": {"id": 40, "name": "Liverpool"},
                "away": {"id": 42, "name": "Arsenal"},
            },
        }
    ]
}

SAMPLE_TEAM_SEARCH_RESPONSE = {
    "response": [
        {
            "team": {"id": 40, "name": "Liverpool", "country": "England"},
            "venue": {"name": "Anfield"},
        }
    ]
}

SAMPLE_INJURIES_RESPONSE = {
    "response": [
        {
            "player": {"name": "Mohamed Salah", "type": "Missing Fixture", "reason": "Muscle Injury"},
            "team": {"id": 40, "name": "Liverpool"},
        }
    ]
}


# ---------------------------------------------------------------------------
# Tests: fixtures
# ---------------------------------------------------------------------------

class TestGetFixtures:
    def test_parse_fixtures(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_FIXTURES_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            fixtures = client.get_fixtures("2026-04-28")

        assert len(fixtures) == 2
        assert isinstance(fixtures[0], NormalizedFixture)
        assert fixtures[0].fixture_id == "12345"
        assert fixtures[0].home_team == "Liverpool"
        assert fixtures[0].away_team == "Arsenal"
        assert fixtures[0].sport == "football"
        assert fixtures[0].competition == "Premier League"
        assert fixtures[0].source == "api-football"
        assert fixtures[0].status == "NS"

    def test_fixtures_no_api_key(self, client_no_key):
        fixtures = client_no_key.get_fixtures("2026-04-28")
        assert fixtures == []

    def test_fixtures_empty_response(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": []}

        with patch("requests.get", return_value=mock_resp):
            fixtures = client.get_fixtures("2026-04-28")

        assert fixtures == []


# ---------------------------------------------------------------------------
# Tests: stat mapping
# ---------------------------------------------------------------------------

class TestStatMapping:
    def test_all_stat_types_mapped(self):
        expected_keys = {
            "corners", "fouls", "yellow_cards", "red_cards",
            "shots", "shots_on_target", "possession", "offsides", "saves",
        }
        assert set(STAT_TYPE_MAP.values()) == expected_keys

    def test_parse_fixture_stats(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_STATS_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            stats = client.get_fixture_stats("12345")

        assert isinstance(stats, NormalizedMatchStats)
        assert stats.fixture_id == "12345"
        assert stats.sport == "football"

        # Home stats
        assert stats.stats["corners"]["home"] == 7
        assert stats.stats["fouls"]["home"] == 12
        assert stats.stats["yellow_cards"]["home"] == 2
        assert stats.stats["shots"]["home"] == 15
        assert stats.stats["shots_on_target"]["home"] == 6
        assert stats.stats["possession"]["home"] == 58.0
        assert stats.stats["offsides"]["home"] == 3
        assert stats.stats["saves"]["home"] == 4

        # Away stats
        assert stats.stats["corners"]["away"] == 4
        assert stats.stats["fouls"]["away"] == 10
        assert stats.stats["yellow_cards"]["away"] == 3
        assert stats.stats["shots"]["away"] == 12
        assert stats.stats["shots_on_target"]["away"] == 5
        assert stats.stats["possession"]["away"] == 42.0
        assert stats.stats["offsides"]["away"] == 1
        assert stats.stats["saves"]["away"] == 5

    def test_stats_no_api_key(self, client_no_key):
        result = client_no_key.get_fixture_stats("12345")
        assert result is None

    def test_stats_empty_response(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": []}

        with patch("requests.get", return_value=mock_resp):
            result = client.get_fixture_stats("12345")

        assert result is None

    def test_possession_percentage_parsing(self, client):
        """Verify that possession '58%' is parsed to float 58.0."""
        response = {
            "response": [
                {
                    "team": {"id": 1, "name": "Team A"},
                    "statistics": [{"type": "Ball Possession", "value": "75%"}],
                },
                {
                    "team": {"id": 2, "name": "Team B"},
                    "statistics": [{"type": "Ball Possession", "value": "25%"}],
                },
            ]
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = response

        with patch("requests.get", return_value=mock_resp):
            stats = client.get_fixture_stats("999")

        assert stats.stats["possession"]["home"] == 75.0
        assert stats.stats["possession"]["away"] == 25.0


# ---------------------------------------------------------------------------
# Tests: team ID resolution with cache
# ---------------------------------------------------------------------------

class TestResolveTeamId:
    def test_resolve_team_id(self, client, cache_dir):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_TEAM_SEARCH_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            team_id = client.resolve_team_id("Liverpool")

        assert team_id == "40"

        # Verify cache was written
        cache_file = cache_dir / "_team_ids" / "api-football.json"
        assert cache_file.exists()
        cached = json.loads(cache_file.read_text())
        assert cached["liverpool"] == "40"

    def test_resolve_team_id_from_cache(self, client, cache_dir):
        # Pre-populate cache
        ids_dir = cache_dir / "_team_ids"
        ids_dir.mkdir(parents=True)
        cache_file = ids_dir / "api-football.json"
        cache_file.write_text(json.dumps({"arsenal": "42"}))

        with patch("scripts.api_clients.api_football.CACHE_DIR", cache_dir):
            team_id = client.resolve_team_id("Arsenal")

        assert team_id == "42"

    def test_resolve_no_api_key(self, client_no_key):
        result = client_no_key.resolve_team_id("Liverpool")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: H2H
# ---------------------------------------------------------------------------

class TestH2H:
    def test_parse_h2h(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_H2H_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            h2h = client.get_h2h("40", "42")

        assert len(h2h) == 1
        assert isinstance(h2h[0], NormalizedFixture)
        assert h2h[0].fixture_id == "11111"
        assert h2h[0].home_team == "Liverpool"
        assert h2h[0].away_team == "Arsenal"

    def test_h2h_no_api_key(self, client_no_key):
        result = client_no_key.get_h2h("40", "42")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: injuries
# ---------------------------------------------------------------------------

class TestInjuries:
    def test_parse_injuries(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_INJURIES_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            injuries = client.get_injuries("12345")

        assert len(injuries) == 1
        assert injuries[0]["player"] == "Mohamed Salah"
        assert injuries[0]["team"] == "Liverpool"
        assert injuries[0]["reason"] == "Muscle Injury"

    def test_injuries_no_api_key(self, client_no_key):
        result = client_no_key.get_injuries("12345")
        assert result == []


# ---------------------------------------------------------------------------
# Tests: rate limiter integration
# ---------------------------------------------------------------------------

class TestRateLimitIntegration:
    def test_request_records_usage(self, client, rate_limiter):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": []}

        with patch("requests.get", return_value=mock_resp):
            client.get_fixtures("2026-04-28")

        remaining = rate_limiter.get_remaining("api-football")
        assert remaining == 99  # 100 limit - 1 used

    def test_quota_exhausted_returns_empty(self, client, rate_limiter):
        # Exhaust the quota
        for _ in range(100):
            rate_limiter.record_request("api-football", "/test")

        # Should return empty without making a request
        fixtures = client.get_fixtures("2026-04-28")
        assert fixtures == []


# ---------------------------------------------------------------------------
# Tests: last fixtures
# ---------------------------------------------------------------------------

class TestTeamLastFixtures:
    def test_get_team_last_fixtures(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_FIXTURES_RESPONSE

        with patch("requests.get", return_value=mock_resp):
            fixtures = client.get_team_last_fixtures("40", last_n=5)

        assert len(fixtures) == 2
        assert isinstance(fixtures[0], NormalizedFixture)

    def test_team_last_fixtures_no_key(self, client_no_key):
        result = client_no_key.get_team_last_fixtures("40")
        assert result == []
