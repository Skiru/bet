"""Unit tests for API-Basketball client fixes."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from bet.api_clients.api_basketball import APIBasketballClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.stats.fallback_chains import FALLBACK_CHAINS

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestSeasonComputation:
    """Test dynamic season string computation in get_team_last_fixtures."""

    def test_may_2026(self):
        assert APIBasketballClient._season_string(datetime(2026, 5, 1)) == "2025-2026"

    def test_october_2026(self):
        assert APIBasketballClient._season_string(datetime(2026, 10, 1)) == "2026-2027"

    def test_september_2025(self):
        assert APIBasketballClient._season_string(datetime(2025, 9, 1)) == "2024-2025"

    def test_january_2027(self):
        assert APIBasketballClient._season_string(datetime(2027, 1, 1)) == "2026-2027"

    def test_december_2025(self):
        assert APIBasketballClient._season_string(datetime(2025, 12, 1)) == "2025-2026"

    def test_source_has_no_hardcoded_season(self):
        src = (PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()
        # Ensure no hardcoded season string
        assert "2024-2025" not in src
        assert "2023-2024" not in src
        # Ensure dynamic computation exists
        assert "now.month >= 10" in src or "now.month>=10" in src


class TestStatMapping:
    """Test that all required stat keys exist in the stat_mapping dict."""

    def test_all_required_keys_present(self):
        src = (PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()
        required = [
            "points", "rebounds", "assists", "steals", "blocks",
            "turnovers", "fg_pct", "three_pct", "ft_pct",
            "offensive_rebounds", "defensive_rebounds",
            "fast_break_points", "points_in_paint", "fouls",
        ]
        for key in required:
            assert f'"{key}"' in src, f"Missing stat key: {key}"

    def test_api_key_mappings_exist(self):
        src = (PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()
        api_keys = [
            "offRebounds", "defRebounds", "fastBreakPoints",
            "pointsInPaint", "personalFouls",
        ]
        for key in api_keys:
            assert f'"{key}"' in src, f"Missing API key mapping: {key}"


class TestFallbackChain:
    """Test basketball fallback chain configuration."""

    def test_nba_api_in_chain(self):
        assert "nba-api" in FALLBACK_CHAINS["basketball"]

    def test_chain_ordering(self):
        chain = FALLBACK_CHAINS["basketball"]
        for name in ("espn-basketball", "nba-api", "api-basketball"):
            assert name in chain, f"'{name}' missing from basketball fallback chain"
        espn_pos = chain.index("espn-basketball")
        nba_pos = chain.index("nba-api")
        api_pos = chain.index("api-basketball")
        assert espn_pos < nba_pos < api_pos, "Chain should be: espn → nba-api → api-basketball"

    def test_balldontlie_not_in_registry(self):
        src = (PROJECT_ROOT / "src/bet/api_clients/__init__.py").read_text()
        assert 'CLIENT_REGISTRY["balldontlie"]' not in src


class TestFixtureStatsSideAssignment:
    def test_uses_fixture_side_mapping_not_response_order(self, tmp_path, monkeypatch):
        client = APIBasketballClient(RateLimiter(usage_dir=tmp_path))
        client.api_key = "test"

        monkeypatch.setattr(client, "_check_cache", lambda *args, **kwargs: None)
        monkeypatch.setattr(client, "_save_cache", lambda *args, **kwargs: None)

        def fake_request(endpoint, params=None, cost=1):
            if endpoint == "/games":
                return {
                    "response": [
                        {
                            "teams": {
                                "home": {"id": 10, "name": "Home Team"},
                                "away": {"id": 20, "name": "Away Team"},
                            }
                        }
                    ]
                }

            if endpoint == "/statistics":
                return {
                    "response": [
                        {
                            "team": {"id": 20, "name": "Away Team"},
                            "statistics": {"points": 90},
                        },
                        {
                            "team": {"id": 10, "name": "Home Team"},
                            "statistics": {"points": 101},
                        },
                    ]
                }

            raise AssertionError(f"Unexpected endpoint: {endpoint}")

        monkeypatch.setattr(client, "_request", fake_request)

        result = client.get_fixture_stats("game-1")

        assert len(result) == 1
        assert result[0].home_team_name == "Home Team"
        assert result[0].away_team_name == "Away Team"
        assert result[0].stats["points"]["home"] == 101.0
        assert result[0].stats["points"]["away"] == 90.0

    def test_logs_when_side_map_unavailable(self, tmp_path, monkeypatch, caplog):
        client = APIBasketballClient(RateLimiter(usage_dir=tmp_path))
        client.api_key = "test"

        monkeypatch.setattr(client, "_check_cache", lambda *args, **kwargs: None)
        monkeypatch.setattr(client, "_save_cache", lambda *args, **kwargs: None)

        def fake_request(endpoint, params=None, cost=1):
            if endpoint == "/games":
                raise RuntimeError("fixture lookup unavailable")

            if endpoint == "/statistics":
                return {
                    "response": [
                        {
                            "team": {"id": 20, "name": "Away Team"},
                            "statistics": {"points": 90},
                        },
                        {
                            "team": {"id": 10, "name": "Home Team"},
                            "statistics": {"points": 101},
                        },
                    ]
                }

            raise AssertionError(f"Unexpected endpoint: {endpoint}")

        monkeypatch.setattr(client, "_request", fake_request)

        with caplog.at_level("WARNING"):
            result = client.get_fixture_stats("game-1")

        assert len(result) == 1
        assert "assigned home/away by response order" in caplog.text
