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
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Accept": "application/json",
}

class SofascoreClient(BaseAPIClient):
    """Deep data client for Sofascore."""

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("sofascore", "https://api.sofascore.com/api/v1", rate_limiter)
        # Sofascore doesn't use API keys, it relies on User-Agent + limiting
        self.api_key = "no-key-needed"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _request(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if hasattr(self.rate_limiter, 'wait'):
            self.rate_limiter.wait("sofascore")
        
        try:
            resp = self.session.get(url, params=params, timeout=self.TIMEOUT)
            
            if resp.status_code == 404:
                raise APINotFoundError(f"Resource not found: {url}")
            if resp.status_code in (403, 429):
                logger.warning(f"Sofascore blocked HTTP request ({resp.status_code}) for {url}. Falling back to Playwright...")
                return self._request_playwright(url, params)
                
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (403, 429):
                return self._request_playwright(url, params)
            raise APIError(f"Sofascore Network error: {e}")

    def _request_playwright(self, url: str, params: dict | None = None) -> dict:
        """Fallback method using Playwright for Cloudflare 403 blocks."""
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        import urllib.parse
        
        if params:
            query = urllib.parse.urlencode(params)
            full_url = f"{url}?{query}"
        else:
            full_url = url
            
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                ]
            )
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 720}
            )
            
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            
            try:
                response = page.goto(full_url, wait_until="networkidle", timeout=self.TIMEOUT * 1000)
                if not response:
                    raise APIError(f"Playwright received no response for {full_url}")
                
                # Cloudflare check
                content = page.content()
                if "Just a moment" in content or "cf-browser-verification" in content or "DataDome" in content:
                    logger.warning("Challenge page detected in Playwright, waiting...")
                    page.wait_for_timeout(5000)
                    content = page.content()
                
                if response.status == 404:
                    raise APINotFoundError(f"Resource not found via playwright: {full_url}")
                    
                import json
                try:
                    # Sofascore endpoints usually return pure JSON
                    json_str = page.evaluate("document.body.innerText")
                    logger.info(f"Playwright raw json_str: {json_str[:200]}")
                    return json.loads(json_str)
                except Exception as e:
                    logger.error(f"Failed to parse JSON from Playwright. Raw body: {page.evaluate('document.body.innerHTML')[:200]}")
                    raise APIError(f"Failed to parse JSON from Playwright response: {e}")
            finally:
                browser.close()

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
