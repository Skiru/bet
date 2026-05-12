"""Unit tests for API-Basketball client fixes."""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure imports work
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


class TestSeasonComputation:
    """Test dynamic season string computation in get_team_last_fixtures."""

    def _compute_season(self, month: int, year: int) -> str:
        """Replicate the season logic from api_basketball.py."""
        season_start = year if month >= 10 else year - 1
        return f"{season_start}-{season_start + 1}"

    def test_may_2026(self):
        assert self._compute_season(5, 2026) == "2025-2026"

    def test_october_2026(self):
        assert self._compute_season(10, 2026) == "2026-2027"

    def test_september_2025(self):
        assert self._compute_season(9, 2025) == "2024-2025"

    def test_january_2027(self):
        assert self._compute_season(1, 2027) == "2026-2027"

    def test_december_2025(self):
        assert self._compute_season(12, 2025) == "2025-2026"

    def test_source_has_no_hardcoded_season(self):
        src = (PROJECT_ROOT / "src/bet/api_clients/api_basketball.py").read_text()
        # Ensure no hardcoded season string
        assert '"2024-2025"' not in src
        assert '"2023-2024"' not in src
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
        src = (PROJECT_ROOT / "scripts/fetch_api_stats.py").read_text()
        assert '"nba-api"' in src

    def test_chain_ordering(self):
        src = (PROJECT_ROOT / "scripts/fetch_api_stats.py").read_text()
        espn_pos = src.index('"espn-basketball"')
        nba_pos = src.index('"nba-api"')
        api_pos = src.index('"api-basketball"')
        assert espn_pos < nba_pos < api_pos, "Chain should be: espn → nba-api → api-basketball"

    def test_balldontlie_not_in_registry(self):
        src = (PROJECT_ROOT / "scripts/api_clients/__init__.py").read_text()
        assert 'CLIENT_REGISTRY["balldontlie"]' not in src
