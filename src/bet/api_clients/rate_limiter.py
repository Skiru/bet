"""File-based daily request counter for API rate limiting.

Usage files stored at: betting/data/.api_usage/{api_name}_{YYYY-MM-DD}.json
Auto-resets daily (new file per day). Atomic writes via temp file + rename.

Copied from scripts/api_clients/rate_limiter.py — paths adapted for src/bet/ layout.
"""

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

# Daily request limits per API (legacy — kept for backward compatibility)
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
    "flashscore-scraper": 200,
    "soccerway-scraper": 100,
    "serpapi": 8,  # ~250/month ≈ 8/day
    # "odds-api-io" and "nba-api" are window-capped (hourly/minute) via API_RATE_LIMITS
    # and no longer need a conservative daily backstop.  Removing them prevents
    # premature throttling while the window-aware limiter is in transition.
    "understat": 10000,  # unlimited, nominal cap
    "totalcorner-scraper": 50,
    "scores24-scraper": 100,
    # ESPN clients — free, unlimited, no cap needed but tracked
    "espn-football": 10000,
    "espn-basketball": 10000,
    "espn-hockey": 10000,
    "espn-tennis": 10000,
    "espn-volleyball": 10000,
}

# Window-aware rate limits: {api_name: {type: "hourly"|"daily"|"minute", limit: int, burst: int}}
# Prefer these when available. The RateLimiter consults this first and falls
# back to API_DAILY_LIMITS for APIs without an entry here.
API_RATE_LIMITS = {
    "odds-api-io": {"type": "hourly", "limit": 5000, "burst": 100},
    "nba-api": {"type": "minute", "limit": 30, "burst": 10},
    "odds-api": {"type": "daily", "limit": 16, "burst": 4},
}

# APIs on the api-sports.io platform — each has its OWN 100/day limit per sport endpoint.
# No shared quota: football=100, basketball=100, hockey=100, tennis=100, volleyball=100 independently.
SHARED_QUOTA_GROUPS: dict[str, list[str]] = {}
SHARED_QUOTA_LIMITS: dict[str, int] = {}
# Reverse lookup: api_name → group_name
_API_TO_GROUP: dict[str, str] = {}
for _group, _apis in SHARED_QUOTA_GROUPS.items():
    for _api in _apis:
        _API_TO_GROUP[_api] = _group

# Resolve project root: src/bet/api_clients/rate_limiter.py → project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
USAGE_DIR = PROJECT_ROOT / "betting" / "data" / ".api_usage"

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


def _window_str(window_type: str) -> str:
    """Return the current time bucket string for a rate-limit window.

    hourly → "YYYY-MM-DD_HH"
    minute → "YYYY-MM-DD_HH_MM"
    daily  → "YYYY-MM-DD"
    """
    now = datetime.now(timezone.utc)
    if window_type == "hourly":
        return now.strftime("%Y-%m-%d_%H")
    if window_type == "minute":
        return now.strftime("%Y-%m-%d_%H_%M")
    return now.strftime("%Y-%m-%d")


class RateLimiter:
    """File-based window-aware API request counter.

    Thread-safe: uses per-API locks to prevent TOCTOU races on
    read-increment-write cycles in can_request() and record_request().
    Supports daily, hourly, and minute-level windows via API_RATE_LIMITS.
    """

    def __init__(self, usage_dir: Path | None = None, limits: dict | None = None,
                 rate_limits: dict | None = None):
        self.usage_dir = usage_dir or USAGE_DIR
        self.limits = limits or API_DAILY_LIMITS
        self.rate_limits = rate_limits or API_RATE_LIMITS
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, api_name: str) -> threading.Lock:
        """Get or create a per-API lock."""
        with self._global_lock:
            if api_name not in self._locks:
                self._locks[api_name] = threading.Lock()
            return self._locks[api_name]

    def _usage_file(self, api_name: str, date: str | None = None,
                    window_type: str = "daily") -> Path:
        """Get path to usage file for an API on a given window."""
        _validate_api_name(api_name)
        bucket = date or _window_str(window_type)
        return self.usage_dir / f"{api_name}_{bucket}.json"

    def _read_usage(self, api_name: str, date: str | None = None,
                    window_type: str = "daily") -> dict:
        """Read current usage data for an API."""
        path = self._usage_file(api_name, date, window_type)
        if not path.exists():
            return {"api_name": api_name, "date": date or _window_str(window_type), "count": 0, "requests": []}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"api_name": api_name, "date": date or _window_str(window_type), "count": 0, "requests": []}

    def _write_usage(self, api_name: str, data: dict, window_type: str = "daily") -> None:
        """Atomically write usage data."""
        self.usage_dir.mkdir(parents=True, exist_ok=True)
        path = self._usage_file(api_name, data.get("date"), window_type)

        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.usage_dir), suffix=".tmp", prefix=f"{api_name}_"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _effective_limit(self, api_name: str) -> tuple[int | None, str]:
        """Return (limit, window_type) for an API.

        Prefers API_RATE_LIMITS (window-aware) over API_DAILY_LIMITS.
        """
        if api_name in self.rate_limits:
            cfg = self.rate_limits[api_name]
            return cfg.get("limit"), cfg.get("type", "daily")
        return self.limits.get(api_name), "daily"

    def can_request(self, api_name: str, cost: int = 1) -> bool:
        """Check if we have remaining quota for this API.

        Checks both window-aware limit (if defined) AND legacy daily limit.
        """
        _validate_api_name(api_name)
        limit, window_type = self._effective_limit(api_name)
        if limit is None:
            return True

        with self._get_lock(api_name):
            usage = self._read_usage(api_name, window_type=window_type)
            if usage["count"] + cost > limit:
                return False

            # Also enforce legacy daily cap as a backstop
            daily_limit = self.limits.get(api_name)
            if daily_limit is not None:
                daily_usage = self._read_usage(api_name, window_type="daily")
                if daily_usage["count"] + cost > daily_limit:
                    return False

        # Also check shared group quota
        group = _API_TO_GROUP.get(api_name)
        if group:
            group_limit = SHARED_QUOTA_LIMITS.get(group, 0)
            group_total = self._get_group_total(group)
            if group_total + cost > group_limit:
                return False

        return True

    def record_request(self, api_name: str, endpoint: str, cost: int = 1) -> None:
        """Record a completed API request."""
        _validate_api_name(api_name)
        limit, window_type = self._effective_limit(api_name)

        with self._get_lock(api_name):
            # Write to window-specific file
            bucket = _window_str(window_type)
            usage = self._read_usage(api_name, bucket, window_type)
            usage["count"] = usage.get("count", 0) + cost
            usage["date"] = bucket
            usage["api_name"] = api_name
            usage.setdefault("requests", []).append({
                "endpoint": endpoint,
                "cost": cost,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._write_usage(api_name, usage, window_type)

            # Also record to legacy daily file for backward compatibility
            if window_type != "daily":
                today = _today_str()
                daily_usage = self._read_usage(api_name, today, "daily")
                daily_usage["count"] = daily_usage.get("count", 0) + cost
                daily_usage["date"] = today
                daily_usage["api_name"] = api_name
                daily_usage.setdefault("requests", []).append({
                    "endpoint": endpoint,
                    "cost": cost,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                self._write_usage(api_name, daily_usage, "daily")

    def get_remaining(self, api_name: str) -> int:
        """Get remaining requests for this API in the current window.

        Returns the minimum of per-API remaining and shared group remaining.
        """
        _validate_api_name(api_name)
        limit, window_type = self._effective_limit(api_name)
        if limit is None:
            limit = 0
        usage = self._read_usage(api_name, window_type=window_type)
        per_api_remaining = max(0, limit - usage["count"])

        group = _API_TO_GROUP.get(api_name)
        if group:
            group_limit = SHARED_QUOTA_LIMITS.get(group, 0)
            group_total = self._get_group_total(group)
            group_remaining = max(0, group_limit - group_total)
            return min(per_api_remaining, group_remaining)

        return per_api_remaining

    def _get_group_total(self, group: str) -> int:
        """Sum usage counts across all APIs in a shared quota group."""
        total = 0
        for api_name in SHARED_QUOTA_GROUPS.get(group, []):
            usage = self._read_usage(api_name, window_type="daily")
            total += usage.get("count", 0)
        return total

    def get_usage_summary(self) -> dict:
        """Get summary of today's usage across all configured APIs.

        Includes both legacy daily-limited APIs and window-aware APIs.
        """
        today = _today_str()
        summary = {}
        # Collect all known API names from both limit registries
        all_apis = set(self.limits.keys()) | set(self.rate_limits.keys())
        for api_name in sorted(all_apis):
            limit, window_type = self._effective_limit(api_name)
            if limit is None:
                limit = 0
            usage = self._read_usage(api_name, today, window_type)
            remaining = max(0, limit - usage["count"])
            summary[api_name] = {
                "used": usage["count"],
                "limit": limit,
                "remaining": remaining,
                "window_type": window_type,
            }
        return summary
