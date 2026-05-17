"""Tests for src/bet/db/connection.py retry_on_lock utility."""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from bet.db.connection import retry_on_lock


class TestRetryOnLock:
    def test_succeeds_first_try(self):
        """No retry needed when function succeeds."""
        fn = MagicMock(return_value="ok")
        result = retry_on_lock(fn, "arg1", key="val")
        assert result == "ok"
        fn.assert_called_once_with("arg1", key="val")

    def test_retries_on_locked_error(self):
        """Retries on sqlite3.OperationalError with 'database is locked'."""
        fn = MagicMock(
            side_effect=[
                sqlite3.OperationalError("database is locked"),
                "success",
            ]
        )
        with patch("time.sleep"):
            result = retry_on_lock(fn, max_retries=3, base_delay=0.01)
        assert result == "success"
        assert fn.call_count == 2

    def test_raises_after_max_retries(self):
        """Re-raises after exhausting max_retries."""
        fn = MagicMock(
            side_effect=sqlite3.OperationalError("database is locked")
        )
        with patch("time.sleep"):
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                retry_on_lock(fn, max_retries=2, base_delay=0.01)
        assert fn.call_count == 3  # initial + 2 retries

    def test_no_retry_on_other_operational_error(self):
        """Non-lock OperationalErrors are raised immediately."""
        fn = MagicMock(
            side_effect=sqlite3.OperationalError("no such table: foo")
        )
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            retry_on_lock(fn, max_retries=3)
        fn.assert_called_once()

    def test_exponential_backoff_delays(self):
        """Verifies exponential backoff timing."""
        fn = MagicMock(
            side_effect=[
                sqlite3.OperationalError("database is locked"),
                sqlite3.OperationalError("database is locked"),
                "ok",
            ]
        )
        with patch("time.sleep") as mock_sleep:
            retry_on_lock(fn, max_retries=3, base_delay=0.5)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.5)   # 0.5 * 2^0
        mock_sleep.assert_any_call(1.0)   # 0.5 * 2^1


class TestBusyTimeout:
    def test_busy_timeout_is_30s(self):
        """Verify busy_timeout is set to 30000ms (30 seconds)."""
        source = (Path(__file__).parent.parent / "src" / "bet" / "db" / "connection.py").read_text()
        assert "busy_timeout = 30000" in source