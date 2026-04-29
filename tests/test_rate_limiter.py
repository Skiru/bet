"""Unit tests for RateLimiter."""

import json
import tempfile
import unittest
from pathlib import Path

from scripts.api_clients.rate_limiter import RateLimiter, _validate_api_name


class TestRateLimiterValidation(unittest.TestCase):
    """Test API name validation."""

    def test_valid_names(self):
        for name in ["api-football", "odds-api", "thesportsdb", "balldontlie"]:
            _validate_api_name(name)  # should not raise

    def test_invalid_empty(self):
        with self.assertRaises(ValueError):
            _validate_api_name("")

    def test_invalid_path_traversal(self):
        with self.assertRaises(ValueError):
            _validate_api_name("../etc/passwd")

    def test_invalid_slashes(self):
        with self.assertRaises(ValueError):
            _validate_api_name("api/football")

    def test_invalid_spaces(self):
        with self.assertRaises(ValueError):
            _validate_api_name("api football")

    def test_invalid_special_chars(self):
        with self.assertRaises(ValueError):
            _validate_api_name("api_football")


class TestRateLimiterCounter(unittest.TestCase):
    """Test counter increment, quota, and reset."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.usage_dir = Path(self.tmp_dir)
        self.limiter = RateLimiter(
            usage_dir=self.usage_dir,
            limits={"test-api": 5, "big-api": 1000},
        )

    def test_initial_state(self):
        """New API should have full quota."""
        self.assertTrue(self.limiter.can_request("test-api"))
        self.assertEqual(self.limiter.get_remaining("test-api"), 5)

    def test_increment(self):
        """Recording requests should decrement remaining."""
        self.limiter.record_request("test-api", "/endpoint1")
        self.assertEqual(self.limiter.get_remaining("test-api"), 4)

        self.limiter.record_request("test-api", "/endpoint2")
        self.assertEqual(self.limiter.get_remaining("test-api"), 3)

    def test_quota_exhaustion(self):
        """Should block requests when quota is exhausted."""
        for i in range(5):
            self.assertTrue(self.limiter.can_request("test-api"))
            self.limiter.record_request("test-api", f"/endpoint{i}")

        self.assertFalse(self.limiter.can_request("test-api"))
        self.assertEqual(self.limiter.get_remaining("test-api"), 0)

    def test_cost_parameter(self):
        """Requests with cost > 1 should consume multiple credits."""
        self.limiter.record_request("test-api", "/expensive", cost=3)
        self.assertEqual(self.limiter.get_remaining("test-api"), 2)

    def test_can_request_cost_check(self):
        """can_request should check if cost fits in remaining quota."""
        self.limiter.record_request("test-api", "/endpoint", cost=4)
        self.assertTrue(self.limiter.can_request("test-api", cost=1))
        self.assertFalse(self.limiter.can_request("test-api", cost=2))

    def test_daily_reset_different_dates(self):
        """Different dates should have independent counters."""
        # Record requests for a specific date
        usage_data = {
            "api_name": "test-api",
            "date": "2026-04-27",
            "count": 5,
            "requests": [],
        }
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        usage_file = self.usage_dir / "test-api_2026-04-27.json"
        usage_file.write_text(json.dumps(usage_data), encoding="utf-8")

        # Today's counter should be independent
        self.assertTrue(self.limiter.can_request("test-api"))
        self.assertEqual(self.limiter.get_remaining("test-api"), 5)

    def test_usage_summary(self):
        """get_usage_summary should report all configured APIs."""
        self.limiter.record_request("test-api", "/ep1")
        summary = self.limiter.get_usage_summary()

        self.assertIn("test-api", summary)
        self.assertIn("big-api", summary)
        self.assertEqual(summary["test-api"]["used"], 1)
        self.assertEqual(summary["test-api"]["limit"], 5)
        self.assertEqual(summary["test-api"]["remaining"], 4)
        self.assertEqual(summary["big-api"]["used"], 0)
        self.assertEqual(summary["big-api"]["remaining"], 1000)

    def test_usage_file_written(self):
        """Usage data should be persisted to disk."""
        self.limiter.record_request("test-api", "/ep1")

        # Find the usage file
        files = list(self.usage_dir.glob("test-api_*.json"))
        self.assertEqual(len(files), 1)

        data = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(data["count"], 1)
        self.assertEqual(len(data["requests"]), 1)
        self.assertEqual(data["requests"][0]["endpoint"], "/ep1")

    def test_unknown_api_allowed(self):
        """Unknown APIs should be allowed (with warning)."""
        self.assertTrue(self.limiter.can_request("unknown-api"))


if __name__ == "__main__":
    unittest.main()
