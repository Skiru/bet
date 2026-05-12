"""Sofascore API client — advanced stats, form, H2H, and odds.

Provides deep statistics and event discovery for:
- Football (soccer)
- Basketball
- Tennis
- Hockey
- Volleyball
and more.

Base URL: https://api.sofascore.com/api/v1/
"""

import logging
from typing import Dict, List, Optional, Any
import requests

from .base_client import BaseAPIClient, APIError, APINotFoundError
from .rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

class SofascoreClient(BaseAPIClient):
    """Deep data client for Sofascore."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("sofascore", "https://api.sofascore.com/api/v1", rate_limiter)
        # Sofascore doesn't use API keys, it relies on User-Agent + limiting
        self.api_key = "no-key-needed"

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=self.TIMEOUT)
            
            if resp.status_code == 404:
                # Silently catch 404s for stats/H2H (common for lower leagues)
                raise APINotFoundError(f"Resource not found: {url}")
            if resp.status_code == 429:
                logger.warning(f"Sofascore Rate limit hit for {url}")
                raise APIError(f"Rate limited: {url}", status_code=429)
                
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None:
                raise APIError(f"Sofascore API error: {e}", status_code=e.response.status_code)
            raise APIError(f"Sofascore Network error: {e}")

    # -------- REQUIRED INTERFACE IMPLEMENTATIONS --------

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get all scheduled events for a sport on a specific date (YYYY-MM-DD)."""
        try:
            data = self._request(f"/sport/{sport}/scheduled-events/{date}")
            return data.get("events", [])
        except APINotFoundError:
            return []

    def get_fixture_stats(self, event_id: str) -> list:
        """Get match statistics for a specific fixture."""
        try:
            data = self._request(f"/event/{event_id}/statistics")
            return data.get("statistics", [])
        except APINotFoundError:
            return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Sofascore usually provides H2H via the event endpoint.
        If we want direct team-to-team H2H, we could query historical data or 
        fetch from known event's h2h endpoint.
        """
        logger.warning("get_h2h directly via team ids is not supported in Sofascore without event_id. Use get_event_h2h instead.")
        return []
        
    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list:
        """Get the latest form/results for a team."""
        try:
            # endpoint: /team/{id}/events/last/0 
            data = self._request(f"/team/{team_id}/events/last/0")
            events = data.get("events", [])
            return events[:last_n]
        except APINotFoundError:
            return []

    # -------- ADVANCED SOFASCORE SPECIFIC ENDPOINTS --------

    def get_event_h2h(self, event_id: str) -> dict:
        """Get rich H2H stats for a specific event."""
        try:
            return self._request(f"/event/{event_id}/h2h")
        except APINotFoundError:
            return {}
            
    def get_event_odds(self, event_id: str) -> dict:
        """Get pre-match odds for an event (usually 1x2 and O/U)."""
        try:
            return self._request(f"/event/{event_id}/odds/1/all")
        except APINotFoundError:
            return {}

    def get_event_incidents(self, event_id: str) -> list:
        """Get match incidents (goals, cards, substitutions)."""
        try:
            data = self._request(f"/event/{event_id}/incidents")
            return data.get("incidents", [])
        except APINotFoundError:
            return []

    def get_lineups(self, event_id: str) -> dict:
        """Get starting lineups, benches, and formations."""
        try:
            return self._request(f"/event/{event_id}/lineups")
        except APINotFoundError:
            return {}
            
    def get_player_stats(self, event_id: str) -> dict:
        """Get individual player summary statistics for a match."""
        try:
            return self._request(f"/event/{event_id}/lineups/statistics")
        except APINotFoundError:
            return {}
