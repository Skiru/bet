"""Flashscore deep client.

Abstracts Flashscore data fetching behind a solid API client structure.
"""
import logging
import requests
from typing import Dict, List, Optional

from .base_client import BaseAPIClient, APIError, APINotFoundError
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "x-fsign": "SW9D1eZo", # Flashscore often requires a specific sign header for its feeds, or we can use mobile endpoints
}

class FlashscoreClient(BaseAPIClient):
    """Client for Flashscore."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("flashscore", "https://local-global.flashscore.ninja/2/x/feed", rate_limiter)
        self.api_key = "no-key"

    def _request(self, endpoint: str, params: dict | None = None) -> str:
        """Flashscore usually returns a custom delimited format or JSON depending on the endpoint."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                raise APINotFoundError(f"Resource not found: {url}")
            if resp.status_code == 429:
                logger.warning(f"Flashscore Rate limit hit: {url}")
                raise APIError(f"Rate limited: {url}", status_code=429)
                
            resp.raise_for_status()
            # Flashscore feeds are often returning custom text separated by ¬ or ÷
            return resp.text
        except requests.exceptions.RequestException as e:
            raise APIError(f"Flashscore Network error: {e}")

    def get_fixtures(self, date: str) -> list:
        logger.warning("FlashscoreClient is a stub. Returning empty list for fixtures.")
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        logger.warning("FlashscoreClient is a stub. Returning empty list for fixture stats.")
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        logger.warning("FlashscoreClient is a stub. Returning empty list for h2h.")
        return []
