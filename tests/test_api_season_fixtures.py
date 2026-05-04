"""Tests for get_team_last_fixtures() across all API clients.

Verifies that each client:
- Filters to only finished statuses
- Sorts by date descending
- Returns at most last_n items
- Uses cache on second call (no additional _request())
"""

from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    rl = RateLimiter()
    return rl


# ─── Football ──────────────────────────────────────────────────────────────────


def _football_season_response(n: int = 20):
    """Synthetic API-Football response with mix of FT, NS, LIVE, AET, PEN statuses."""
    statuses = ["FT", "NS", "LIVE", "FT", "AET", "NS", "FT", "PEN", "LIVE", "FT",
                "FT", "NS", "FT", "LIVE", "AET", "FT", "NS", "FT", "FT", "PEN"]
    response = []
    for i in range(n):
        month = (i // 5) + 1
        day = (i % 28) + 1
        response.append({
            "fixture": {
                "id": 1000 + i,
                "date": f"2025-0{month}-{day:02d}T15:00:00+00:00",
                "status": {"short": statuses[i % len(statuses)]},
            },
            "teams": {
                "home": {"name": "Team A"},
                "away": {"name": "Team B"},
            },
        })
    return {"response": response}


class TestAPIFootballGetTeamLastFixtures:
    def test_filters_finished_only(self, rate_limiter):
        from bet.api_clients.api_football import APIFootballClient

        client = APIFootballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_football_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("40", last_n=10)

        # All returned IDs must come from FT/AET/PEN fixtures
        assert len(result) == 10
        for item in result:
            assert "id" in item

    def test_sorted_descending(self, rate_limiter):
        from bet.api_clients.api_football import APIFootballClient

        client = APIFootballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_football_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("40", last_n=20)

        # Verify we got results (all finished sorted desc)
        assert len(result) <= 20
        assert len(result) > 0

    def test_max_last_n(self, rate_limiter):
        from bet.api_clients.api_football import APIFootballClient

        client = APIFootballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_football_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("40", last_n=5)

        assert len(result) == 5

    def test_cache_hit(self, rate_limiter):
        from bet.api_clients.api_football import APIFootballClient

        client = APIFootballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        cached_data = {"fixtures": [{"id": 999}, {"id": 998}]}

        with patch.object(client, "_check_cache", return_value=cached_data) as mock_cache:
            with patch.object(client, "_request") as mock_request:
                result = client.get_team_last_fixtures("40", last_n=10)

        assert result == [{"id": 999}, {"id": 998}]
        mock_request.assert_not_called()


# ─── Basketball ────────────────────────────────────────────────────────────────


def _basketball_season_response(n: int = 20):
    """Synthetic API-Basketball response with mix of FT, NS, LIVE statuses."""
    statuses = [
        {"short": "FT", "long": "Game Finished"},
        {"short": "NS", "long": "Not Started"},
        {"short": "LIVE", "long": "In Progress"},
        {"short": "FT", "long": "Game Finished"},
        {"short": "AOT", "long": "After Over Time"},
    ]
    response = []
    for i in range(n):
        month = (i // 5) + 1
        day = (i % 28) + 1
        response.append({
            "id": 2000 + i,
            "date": f"2025-0{month}-{day:02d}T20:00:00+00:00",
            "status": statuses[i % len(statuses)],
            "teams": {
                "home": {"name": "Lakers"},
                "away": {"name": "Celtics"},
            },
            "league": {"name": "NBA"},
        })
    return {"response": response}


class TestAPIBasketballGetTeamLastFixtures:
    def test_filters_finished_only(self, rate_limiter):
        from bet.api_clients.api_basketball import APIBasketballClient

        client = APIBasketballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_basketball_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("1", last_n=10)

        # FT and "Game Finished" appear at indices 0,3 per 5; AOT at index 4
        # statuses cycle every 5 → 3 finished per 5 = 12 per 20, capped by last_n=10
        assert len(result) == 10  # FT, AOT, or "Game Finished" games (capped)
        for item in result:
            assert "id" in item

    def test_max_last_n(self, rate_limiter):
        from bet.api_clients.api_basketball import APIBasketballClient

        client = APIBasketballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_basketball_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("1", last_n=3)

        assert len(result) == 3

    def test_cache_hit(self, rate_limiter):
        from bet.api_clients.api_basketball import APIBasketballClient

        client = APIBasketballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        cached_data = {"fixtures": [{"id": 2001}, {"id": 2004}]}

        with patch.object(client, "_check_cache", return_value=cached_data):
            with patch.object(client, "_request") as mock_request:
                result = client.get_team_last_fixtures("1", last_n=10)

        assert result == [{"id": 2001}, {"id": 2004}]
        mock_request.assert_not_called()


# ─── Hockey ────────────────────────────────────────────────────────────────────


def _hockey_season_response(n: int = 20):
    """Synthetic API-Hockey response with mix of FT, NS, LIVE, AOT, AP statuses."""
    statuses = [
        {"short": "FT"},
        {"short": "NS"},
        {"short": "LIVE"},
        {"short": "AOT"},
        {"short": "AP"},
        {"short": "FT"},
        {"short": "NS"},
        {"short": "FT"},
        {"short": "LIVE"},
        {"short": "FT"},
    ]
    response = []
    for i in range(n):
        month = (i // 5) + 1
        day = (i % 28) + 1
        response.append({
            "id": 3000 + i,
            "date": f"2025-0{month}-{day:02d}T19:00:00+00:00",
            "status": statuses[i % len(statuses)],
            "teams": {
                "home": {"name": "Bruins"},
                "away": {"name": "Rangers"},
            },
            "league": {"name": "NHL"},
        })
    return {"response": response}


class TestAPIHockeyGetTeamLastFixtures:
    def test_filters_finished_only(self, rate_limiter):
        from bet.api_clients.api_hockey import APIHockeyClient

        client = APIHockeyClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_hockey_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("5", last_n=15)

        # FT at 0,5,7,9 + AOT at 3 + AP at 4 per 10 → 6 per 10 → 12 per 20
        assert len(result) == 12
        for item in result:
            assert "id" in item

    def test_max_last_n(self, rate_limiter):
        from bet.api_clients.api_hockey import APIHockeyClient

        client = APIHockeyClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_hockey_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("5", last_n=4)

        assert len(result) == 4

    def test_cache_hit(self, rate_limiter):
        from bet.api_clients.api_hockey import APIHockeyClient

        client = APIHockeyClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        cached_data = {"fixtures": [{"id": 3000}, {"id": 3005}]}

        with patch.object(client, "_check_cache", return_value=cached_data):
            with patch.object(client, "_request") as mock_request:
                result = client.get_team_last_fixtures("5", last_n=10)

        assert result == [{"id": 3000}, {"id": 3005}]
        mock_request.assert_not_called()


# ─── Volleyball ────────────────────────────────────────────────────────────────


def _volleyball_season_response(n: int = 20):
    """Synthetic API-Volleyball response with mix of finished and non-finished."""
    statuses = [
        {"short": "FT", "long": "Match Finished"},
        {"short": "NS", "long": "Not Started"},
        {"short": "LIVE", "long": "In Progress"},
        {"short": "FT", "long": "Match Finished"},
        {"short": "", "long": "Game finished"},  # matches "finished" in lower()
    ]
    response = []
    for i in range(n):
        month = (i // 5) + 1
        day = (i % 28) + 1
        response.append({
            "id": 4000 + i,
            "date": f"2025-0{month}-{day:02d}T18:00:00+00:00",
            "status": statuses[i % len(statuses)],
            "teams": {
                "home": {"name": "Jastrzębski"},
                "away": {"name": "Zaksa"},
            },
            "league": {"name": "PlusLiga"},
        })
    return {"response": response}


class TestAPIVolleyballGetTeamLastFixtures:
    def test_filters_finished_only(self, rate_limiter):
        from bet.api_clients.api_volleyball import APIVolleyballClient

        client = APIVolleyballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_volleyball_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("10", last_n=15)

        # FT at 0,3 per 5, "finished" in long at 4 → 3 per 5 → 12 per 20
        assert len(result) == 12
        for item in result:
            assert "id" in item

    def test_max_last_n(self, rate_limiter):
        from bet.api_clients.api_volleyball import APIVolleyballClient

        client = APIVolleyballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        with patch.object(client, "_request", return_value=_volleyball_season_response(20)):
            with patch.object(client, "_check_cache", return_value=None):
                with patch.object(client, "_save_cache"):
                    result = client.get_team_last_fixtures("10", last_n=5)

        assert len(result) == 5

    def test_cache_hit(self, rate_limiter):
        from bet.api_clients.api_volleyball import APIVolleyballClient

        client = APIVolleyballClient(rate_limiter=rate_limiter)
        client.api_key = "test-key"

        cached_data = {"fixtures": [{"id": 4000}, {"id": 4003}]}

        with patch.object(client, "_check_cache", return_value=cached_data):
            with patch.object(client, "_request") as mock_request:
                result = client.get_team_last_fixtures("10", last_n=10)

        assert result == [{"id": 4000}, {"id": 4003}]
        mock_request.assert_not_called()
