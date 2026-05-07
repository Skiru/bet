"""Tests for BaseSportScanner lifecycle, validation, and health recording."""
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(BASE / "src"))

from scripts.scanners.base_scanner import BaseSportScanner
from scripts.scanners.domain_semaphore import DomainSemaphoreMap
from bet.db.models import ScanRunStats


# ---------------------------------------------------------------------------
# Stub scanner for testing
# ---------------------------------------------------------------------------

class StubScanner(BaseSportScanner):
    """Concrete stub for testing BaseSportScanner logic."""

    @property
    def sport_name(self) -> str:
        return "test_sport"

    @property
    def scanner_group(self) -> str:
        return "test_group"

    @property
    def urls(self) -> list[str]:
        return ["https://www.example.com/sport/today"]

    @property
    def timeout_per_page(self) -> int:
        return 10

    @property
    def max_deep_links(self) -> int:
        return 5

    @property
    def required_stat_keys(self) -> list[str]:
        return ["goals", "assists"]

    @property
    def min_expected_events(self) -> int:
        return 3


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scanner():
    return StubScanner()


@pytest.fixture
def semaphore_map():
    return DomainSemaphoreMap()


@pytest.fixture
def in_memory_db():
    """Create in-memory DB with schema for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema_path = BASE / "src" / "bet" / "db" / "schema.sql"
    conn.executescript(schema_path.read_text())
    return conn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidation:
    def test_validate_passes_when_enough_events(self, scanner):
        passed, gaps = scanner.validate(10)
        assert passed is True
        assert gaps == []

    def test_validate_fails_when_too_few_events(self, scanner):
        passed, gaps = scanner.validate(2)
        assert passed is False
        assert len(gaps) == 1
        assert "test_group" in gaps[0]
        assert "2" in gaps[0]

    def test_validate_at_exact_minimum(self, scanner):
        passed, gaps = scanner.validate(3)
        assert passed is True
        assert gaps == []


class TestFetchUrl:
    @patch("scripts.scanners.base_scanner.fetch")
    def test_fetch_url_uses_semaphore_and_timeout(self, mock_fetch, scanner, semaphore_map):
        mock_fetch.return_value = "<html>test</html>"
        result = scanner._fetch_url("https://www.example.com/page", semaphore_map)
        assert result == "<html>test</html>"
        mock_fetch.assert_called_once_with("https://www.example.com/page")

    @patch("scripts.scanners.base_scanner.fetch")
    def test_fetch_url_raises_on_timeout(self, mock_fetch, scanner, semaphore_map):
        import time
        mock_fetch.side_effect = lambda url: time.sleep(20)
        # Use a scanner with very short timeout
        scanner._timeout_override = 1

        class QuickScanner(StubScanner):
            @property
            def timeout_per_page(self):
                return 1

        qs = QuickScanner()
        with pytest.raises(TimeoutError):
            qs._fetch_url("https://www.example.com/slow", semaphore_map)


class TestParseUrl:
    @patch("scripts.scanners.base_scanner.get_adapter")
    def test_parse_url_calls_adapter(self, mock_get_adapter, scanner):
        mock_adapter = MagicMock(return_value=[{"home": "A", "away": "B"}])
        mock_get_adapter.return_value = mock_adapter

        result = scanner._parse_url("https://www.example.com/page", "<html></html>")
        assert result == [{"home": "A", "away": "B"}]
        mock_get_adapter.assert_called_once_with("example.com")

    @patch("scripts.scanners.base_scanner.get_adapter")
    def test_parse_url_handles_adapter_error(self, mock_get_adapter, scanner):
        mock_adapter = MagicMock(side_effect=ValueError("parse error"))
        mock_get_adapter.return_value = mock_adapter

        result = scanner._parse_url("https://www.example.com/page", "<html></html>")
        assert result == []


class TestWriteResults:
    @patch("scripts.scanners.base_scanner.get_db")
    def test_write_results_returns_event_count(self, mock_get_db, scanner, in_memory_db, tmp_path):
        mock_get_db.return_value.__enter__ = MagicMock(return_value=in_memory_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        results = {
            "https://example.com/sport": [
                {"home": "Team A", "away": "Team B", "time": "18:00", "league": "Test League"},
                {"home": "Team C", "away": "Team D", "time": "20:00", "league": "Test League"},
            ]
        }

        # Patch DATA_DIR to use tmp
        with patch("scripts.scanners.base_scanner.DATA_DIR", tmp_path):
            count = scanner._write_results("2026-05-07", results)

        assert count == 2


class TestRecordHealth:
    @patch("scripts.scanners.base_scanner.get_db")
    def test_record_health_success(self, mock_get_db, scanner, in_memory_db):
        mock_get_db.return_value.__enter__ = MagicMock(return_value=in_memory_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        scanner._record_health("example.com", success=True, response_ms=150.0)

    @patch("scripts.scanners.base_scanner.get_db")
    def test_record_health_failure(self, mock_get_db, scanner, in_memory_db):
        mock_get_db.return_value.__enter__ = MagicMock(return_value=in_memory_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        # Should not raise
        scanner._record_health("example.com", success=False)


class TestScanLifecycle:
    @patch("scripts.scanners.base_scanner.get_db")
    @patch("scripts.scanners.base_scanner.fetch")
    @patch("scripts.scanners.base_scanner.get_adapter")
    def test_scan_returns_stats(self, mock_get_adapter, mock_fetch, mock_get_db, scanner, semaphore_map, in_memory_db, tmp_path):
        # Setup mocks
        mock_fetch.return_value = "<html>events</html>"
        mock_adapter = MagicMock(return_value=[
            {"home": "A", "away": "B", "time": "18:00", "league": "L1"},
            {"home": "C", "away": "D", "time": "19:00", "league": "L1"},
            {"home": "E", "away": "F", "time": "20:00", "league": "L2"},
        ])
        mock_get_adapter.return_value = mock_adapter
        mock_get_db.return_value.__enter__ = MagicMock(return_value=in_memory_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        with patch("scripts.scanners.base_scanner.DATA_DIR", tmp_path):
            stats = scanner.scan("2026-05-07", semaphore_map)

        assert isinstance(stats, ScanRunStats)
        assert stats.sport == "test_sport"
        assert stats.scanner_group == "test_group"
        assert stats.betting_date == "2026-05-07"
        assert stats.events_found == 3
        assert stats.sources_ok == 1
        assert stats.sources_failed == 0
        assert stats.validation_passed is True

    @patch("scripts.scanners.base_scanner.get_db")
    @patch("scripts.scanners.base_scanner.fetch")
    @patch("scripts.scanners.base_scanner.get_adapter")
    def test_scan_records_failure(self, mock_get_adapter, mock_fetch, mock_get_db, scanner, semaphore_map, in_memory_db, tmp_path):
        mock_fetch.side_effect = ConnectionError("Network error")
        mock_get_db.return_value.__enter__ = MagicMock(return_value=in_memory_db)
        mock_get_db.return_value.__exit__ = MagicMock(return_value=False)

        with patch("scripts.scanners.base_scanner.DATA_DIR", tmp_path):
            stats = scanner.scan("2026-05-07", semaphore_map)

        assert stats.sources_failed == 1
        assert stats.sources_ok == 0
        assert stats.events_found == 0
        assert stats.validation_passed is False


class TestGetFallbackUrls:
    def test_default_returns_empty(self, scanner):
        assert scanner.get_fallback_urls() == []
