"""File-based daily request counter for API rate limiting.

Usage files stored at: betting/data/.api_usage/{api_name}_{YYYY-MM-DD}.json
Auto-resets daily (new file per day). Atomic writes via temp file + rename.
"""

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

# Daily request limits per API
API_DAILY_LIMITS = {
    "api-football": 100,
    "api-basketball": 100,
    "api-hockey": 100,
    "api-tennis": 100,       # shares api-sports.io quota with api-football
    "api-volleyball": 100,   # shares api-sports.io quota with api-football
    "football-data-org": 1000,
    "balldontlie": 1000,
    "thesportsdb": 100,
    "odds-api": 16,
    "oddsportal-scraper": 50,
    "betexplorer-scraper": 50,
    "betclic-scraper": 50,
    "serpapi": 8,  # ~250/month ≈ 8/day
    "odds-api-io": 200,  # 5000/hour, cap at 200/day to be safe
    "nba-api": 1800,  # ~30 req/min, cap at 1800/day
    "understat": 10000,  # unlimited, nominal cap
    # ESPN clients — free, unlimited, no cap needed but tracked
    "espn-football": 10000,
    "espn-basketball": 10000,
    "espn-hockey": 10000,
    "espn-tennis": 10000,
    "espn-volleyball": 10000,
}

USAGE_DIR = Path(__file__).parent.parent.parent / "betting" / "data" / ".api_usage"

# Validation pattern: alphanumeric + hyphens only
_VALID_API_NAME = re.compile(r"^[a-zA-Z0-9-]+$")


def _validate_api_name(api_name: str) -> None:
    """Validate api_name to prevent path traversal."""
    if not api_name or not _VALID_API_NAME.match(api_name):
        raise ValueError(
            f"Invalid api_name '{api_name}': must be alphanumeric with hyphens only"
        )


def _today_str() -> str:
    """Current date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class RateLimiter:
    """File-based daily API request counter.

    Thread-safe: uses per-API locks to prevent TOCTOU races on
    read-increment-write cycles in can_request() and record_request().
    """

    def __init__(self, usage_dir: Path | None = None, limits: dict | None = None):
        self.usage_dir = usage_dir or USAGE_DIR
        self.limits = limits or API_DAILY_LIMITS
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, api_name: str) -> threading.Lock:
        """Get or create a per-API lock."""
        with self._global_lock:
            if api_name not in self._locks:
                self._locks[api_name] = threading.Lock()
            return self._locks[api_name]

    def _usage_file(self, api_name: str, date: str | None = None) -> Path:
        """Get path to usage file for an API on a given date."""
        _validate_api_name(api_name)
        date = date or _today_str()
        return self.usage_dir / f"{api_name}_{date}.json"

    def _read_usage(self, api_name: str, date: str | None = None) -> dict:
        """Read current usage data for an API."""
        path = self._usage_file(api_name, date)
        if not path.exists():
            return {"api_name": api_name, "date": date or _today_str(), "count": 0, "requests": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"api_name": api_name, "date": date or _today_str(), "count": 0, "requests": []}

    def _write_usage(self, api_name: str, data: dict) -> None:
        """Atomically write usage data."""
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        path = self._usage_file(api_name, data.get("date"))

        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.usage_dir), suffix=".tmp", prefix=f"{api_name}_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(path))
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def can_request(self, api_name: str, cost: int = 1) -> bool:
        """Check if we have remaining quota for this API today."""
        _validate_api_name(api_name)
        limit = self.limits.get(api_name)
        if limit is None:
            # Unknown API — allow but warn
            print(f"[rate_limiter] WARNING: No limit configured for '{api_name}', allowing request")
            return True
        with self._get_lock(api_name):
            usage = self._read_usage(api_name)
            return usage["count"] + cost <= limit

    def record_request(self, api_name: str, endpoint: str, cost: int = 1) -> None:
        """Record a completed API request."""
        _validate_api_name(api_name)
        today = _today_str()
        with self._get_lock(api_name):
            usage = self._read_usage(api_name, today)
            usage["count"] = usage.get("count", 0) + cost
            usage["date"] = today
            usage["api_name"] = api_name
            usage.setdefault("requests", []).append({
                "endpoint": endpoint,
                "cost": cost,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._write_usage(api_name, usage)

    def get_remaining(self, api_name: str) -> int:
        """Get remaining requests for this API today."""
        _validate_api_name(api_name)
        limit = self.limits.get(api_name, 0)
        usage = self._read_usage(api_name)
        return max(0, limit - usage["count"])

    def get_usage_summary(self) -> dict:
        """Get summary of today's usage across all configured APIs."""
        today = _today_str()
        summary = {}
        for api_name, limit in self.limits.items():
            usage = self._read_usage(api_name, today)
            summary[api_name] = {
                "used": usage["count"],
                "limit": limit,
                "remaining": max(0, limit - usage["count"]),
            }
        return summary
