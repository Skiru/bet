"""Abstract base class for all API clients.

Provides rate limiting, retry with exponential backoff, API key loading,
and stats cache integration.

Adapted from scripts/api_clients/base_client.py for src/bet/ package layout.
"""

import json
import os
import sys
import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests

from .rate_limiter import RateLimiter

# Resolve project root: src/bet/api_clients/base_client.py → project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"
CACHE_DIR = PROJECT_ROOT / "betting" / "data" / "stats_cache"


def _record_source_health(source_name: str, success: bool) -> None:
    """Record API source health to DB (best-effort, non-blocking)."""
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import SourceHealthRepo
        with get_db() as conn:
            repo = SourceHealthRepo(conn)
            if success:
                repo.record_success(source_name, response_ms=0.0)
            else:
                repo.record_failure(source_name)
            conn.commit()
    except Exception:
        pass  # Non-critical — don't break API calls


class APIError(Exception):
    """General API error."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class APIRateLimitError(APIError):
    """API rate limit exceeded (HTTP 429 or quota exhausted)."""
    pass


class APINotFoundError(APIError):
    """Resource not found (HTTP 404)."""
    pass


class BaseAPIClient(ABC):
    """Abstract base class for sports data API clients."""

    MAX_RETRIES = 3
    TIMEOUT = 15  # seconds
    BACKOFF_BASE = 1  # seconds — retry delays: 1s, 2s, 4s

    def __init__(self, api_name: str, base_url: str, rate_limiter: RateLimiter):
        self.api_name = api_name
        self.base_url = base_url.rstrip("/")
        self.rate_limiter = rate_limiter
        self.api_key = self._load_api_key()

    @abstractmethod
    def get_fixtures(self, date: str) -> list:
        """Get all fixtures/games for a given date (YYYY-MM-DD)."""
        ...

    @abstractmethod
    def get_fixture_stats(self, fixture_id: str) -> list:
        """Get match statistics for a specific fixture."""
        ...

    @abstractmethod
    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get head-to-head history between two teams."""
        ...

    def resolve_team_id(self, team_name: str) -> str | None:
        """Resolve a team name to an API-specific team ID. Override in subclasses."""
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get last N finished fixtures for a team. Override in subclasses."""
        return []

    def is_available(self) -> bool:
        """Return True if the client can make requests (has key or doesn't need one)."""
        return bool(self.api_key)

    def _load_api_key(self) -> str | None:
        """Load API key from env var → config/api_keys.json → None."""
        env_var = self.api_name.upper().replace("-", "_") + "_KEY"
        key = os.environ.get(env_var)
        if key and key.strip():
            return key.strip()

        keys_file = CONFIG_DIR / "api_keys.json"
        if keys_file.exists():
            try:
                keys = json.loads(keys_file.read_text(encoding="utf-8"))
                key = keys.get(self.api_name, "")
                if key and key.strip():
                    return key.strip()
            except (json.JSONDecodeError, OSError):
                pass

        return None

    def _check_api_key(self) -> bool:
        """Check if API key is available. Prints warning if not."""
        if not self.api_key:
            print(f"[{self.api_name}] WARNING: No API key — skipping request")
            return False
        return True

    def _request(self, endpoint: str, params: dict | None = None, cost: int = 1) -> dict:
        """Make API request with rate limiting, retry, and error handling."""
        if not self.rate_limiter.can_request(self.api_name, cost):
            remaining = self.rate_limiter.get_remaining(self.api_name)
            raise APIRateLimitError(
                f"[{self.api_name}] Daily quota exhausted. Remaining: {remaining}"
            )

        url = f"{self.base_url}{endpoint}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    params=params,
                    headers=self._build_headers(),
                    timeout=self.TIMEOUT,
                )

                if response.status_code == 429:
                    raise APIRateLimitError(
                        f"[{self.api_name}] HTTP 429 Too Many Requests",
                        status_code=429,
                    )
                if response.status_code == 404:
                    raise APINotFoundError(
                        f"[{self.api_name}] Not found: {endpoint}",
                        status_code=404,
                    )
                if response.status_code >= 400:
                    raise APIError(
                        f"[{self.api_name}] HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                    )

                self.rate_limiter.record_request(self.api_name, endpoint, cost)
                return response.json()

            except APIRateLimitError:
                raise
            except APINotFoundError:
                raise
            except APIError:
                raise
            except requests.exceptions.RequestException as e:
                last_error = e
                if attempt < self.MAX_RETRIES:
                    backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        raise APIError(f"[{self.api_name}] Failed after {self.MAX_RETRIES} attempts: {last_error}")

    def _build_headers(self) -> dict:
        """Build request headers. Override in subclasses for custom auth."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-apisports-key"] = self.api_key
        return headers

    @staticmethod
    def _validate_cache_key(cache_key: str) -> None:
        """Validate cache_key to prevent path traversal."""
        if not cache_key:
            raise ValueError("cache_key must not be empty")
        if ".." in cache_key or cache_key.startswith("/") or cache_key.startswith("\\"):
            raise ValueError(
                f"Invalid cache_key '{cache_key}': must not contain '..' or start with '/'"
            )

    def _check_cache(self, cache_key: str, ttl_hours: int = 24) -> dict | None:
        """Check stats_cache for a cached response."""
        from datetime import datetime, timezone

        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return None  # Legacy cache format (raw list) — treat as expired
            last_updated = data.get("last_updated", "")
            if not last_updated:
                return None
            updated_dt = datetime.fromisoformat(last_updated)
            age_hours = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600
            if age_hours < ttl_hours:
                return data
        except (json.JSONDecodeError, ValueError, OSError):
            pass

        return None

    def _save_cache(self, cache_key: str, data: dict) -> None:
        """Save response data to stats_cache."""
        from datetime import datetime, timezone

        self._validate_cache_key(cache_key)
        cache_file = CACHE_DIR / f"{cache_key}.json"
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        cache_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )


class APISportsClient(BaseAPIClient):
    """Shared base for API-Sports family clients.

    Provides common x-apisports-key auth and shared-key fallback loading.
    """

    _SHARES_FOOTBALL_KEY = False

    def _load_api_key(self) -> str | None:
        """Load API key — optionally falls back to the shared api-football key."""
        key = super()._load_api_key()
        if key:
            return key

        if not self._SHARES_FOOTBALL_KEY:
            return None

        env_key = os.environ.get("API_FOOTBALL_KEY")
        if env_key and env_key.strip():
            return env_key.strip()

        keys_file = CONFIG_DIR / "api_keys.json"
        if keys_file.exists():
            try:
                keys = json.loads(keys_file.read_text(encoding="utf-8"))
                key = keys.get("api-football", "")
                if key and key.strip():
                    return key.strip()
            except (json.JSONDecodeError, OSError):
                pass

        return None

    def _build_headers(self) -> dict:
        """Use x-apisports-key header for authentication."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-apisports-key"] = self.api_key
        return headers
