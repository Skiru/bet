"""Targeted tests for the Sofascore client behavior used by football completion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.base_client import APIError, APINotFoundError
from bet.api_clients.rate_limiter import RateLimiter
from bet.api_clients.sofascore import SofascoreClient


def _make_client(tmp_path):
    return SofascoreClient(rate_limiter=RateLimiter(usage_dir=tmp_path / "usage"))


def _make_response(payload: dict, status_code: int = 200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _patch_session_get(client, mock_get):
    return patch.object(client.session, "get", side_effect=mock_get)


class TestSofascoreFixtureStats:
    def test_parses_all_period_and_aliases(self, tmp_path):
        client = _make_client(tmp_path)

        stats_payload = {
            "statistics": [
                {
                    "period": "1H",
                    "groups": [
                        {
                            "statisticsItems": [
                                {"name": "Corner Kicks", "home": 1, "away": 0},
                                {"name": "Shots on Goal", "home": 2, "away": 1},
                            ]
                        }
                    ],
                },
                {
                    "period": "ALL",
                    "groups": [
                        {
                            "statisticsItems": [
                                {"name": "Corner Kicks", "home": 7, "away": 3},
                                {"name": "Fouls", "home": 11, "away": 9},
                                {"name": "Yellow Cards", "home": 2, "away": 4},
                                {"name": "Red Cards", "home": 1, "away": 0},
                                {"name": "Total Shots", "home": 14, "away": 8},
                                {"name": "Shots on Goal", "home": 6, "away": 2},
                                {"name": "Ball Possession", "home": "64%", "away": "36%"},
                            ]
                        }
                    ],
                },
            ]
        }
        event_payload = {
            "event": {
                "homeTeam": {"name": "Arsenal"},
                "awayTeam": {"name": "Chelsea"},
                "startTimestamp": 1747766400,
            }
        }

        def mock_get(url, params=None, timeout=None):
            if url.endswith("/statistics"):
                return _make_response(stats_payload)
            if url.endswith("/12345"):
                return _make_response(event_payload)
            raise AssertionError(f"Unexpected URL: {url}")

        with _patch_session_get(client, mock_get):
            stats = client.get_fixture_stats("12345")

        assert stats is not None
        assert stats.stats["corners"]["home"] == 7
        assert stats.stats["fouls"]["away"] == 9
        assert stats.stats["yellow_cards"]["home"] == 2
        assert stats.stats["red_cards"]["home"] == 1
        assert stats.stats["shots"]["home"] == 14
        assert stats.stats["shots_on_target"]["home"] == 6
        assert stats.stats["possession"]["home"] == 64.0

    def test_falls_back_when_all_period_missing(self, tmp_path):
        client = _make_client(tmp_path)

        stats_payload = {
            "statistics": [
                {
                    "period": "1H",
                    "groups": [
                        {"statisticsItems": [{"name": "Corner Kicks", "home": 2, "away": 1}]}
                    ],
                },
                {
                    "period": "2H",
                    "groups": [
                        {"statisticsItems": [{"name": "Corner Kicks", "home": 5, "away": 2}]}
                    ],
                },
            ]
        }
        event_payload = {
            "event": {
                "homeTeam": {"name": "Arsenal"},
                "awayTeam": {"name": "Chelsea"},
                "startTimestamp": 1747766400,
            }
        }

        def mock_get(url, params=None, timeout=None):
            if url.endswith("/statistics"):
                return _make_response(stats_payload)
            if url.endswith("/12346"):
                return _make_response(event_payload)
            raise AssertionError(f"Unexpected URL: {url}")

        with _patch_session_get(client, mock_get):
            stats = client.get_fixture_stats("12346")

        assert stats is not None
        assert stats.stats["corners"]["home"] == 2

    def test_non_numeric_event_id_returns_none_without_request(self, tmp_path):
        client = _make_client(tmp_path)

        with patch.object(client.session, "get") as mock_get:
            assert client.get_fixture_stats("abc") is None

        mock_get.assert_not_called()

    def test_non_numeric_team_id_returns_empty_fixture_list(self, tmp_path):
        client = _make_client(tmp_path)

        with patch.object(client.session, "get") as mock_get:
            assert client.get_team_last_fixtures("abc") == []

        mock_get.assert_not_called()


class TestSofascoreBlockedRequests:
    def test_blocked_request_raises_deterministic_error_when_circuit_open(self, tmp_path):
        client = _make_client(tmp_path)
        original_state = (SofascoreClient._stealth_failures, SofascoreClient._stealth_circuit_open)
        SofascoreClient._stealth_failures = 2
        SofascoreClient._stealth_circuit_open = True

        mock_response = _make_response({}, status_code=403)
        mock_response.raise_for_status.side_effect = APIError("should not be reached")

        try:
            with patch.object(client.session, "get", return_value=mock_response):
                with pytest.raises(APIError, match="stealth circuit is OPEN"):
                    client.get_fixture_stats("12345")
        finally:
            SofascoreClient._stealth_failures, SofascoreClient._stealth_circuit_open = original_state

    def test_playwright_worker_thread_error_is_classifiable(self, tmp_path):
        client = _make_client(tmp_path)
        mock_response = _make_response({}, status_code=403)
        mock_response.raise_for_status.side_effect = APIError("should not be reached")

        with patch.object(client.session, "get", return_value=mock_response), \
             patch.object(client, "_request_playwright", side_effect=APIError("Sofascore Playwright fallback disabled in worker thread (would crash greenlet)")):
            with pytest.raises(APIError, match="worker thread"):
                client.get_fixture_stats("12345")