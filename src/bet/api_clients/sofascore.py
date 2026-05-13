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
import re
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

    # Circuit breaker: after N consecutive stealth failures, skip Playwright
    _stealth_failures = 0
    _stealth_circuit_open = False
    _STEALTH_FAILURE_THRESHOLD = 2  # After 2 failures, stop trying stealth

    @staticmethod
    def _is_sofascore_id(event_id: str) -> bool:
        """Return True only for numeric-only strings (valid Sofascore event IDs)."""
        return bool(event_id and re.fullmatch(r"\d+", str(event_id)))

    def __init__(self, rate_limiter: RateLimiter | None = None):
        if rate_limiter is None:
            rate_limiter = RateLimiter()
        super().__init__("sofascore", "https://api.sofascore.com/api/v1", rate_limiter)
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
                if SofascoreClient._stealth_circuit_open:
                    raise APIError(f"Sofascore blocked ({resp.status_code}) and stealth circuit is OPEN — skipping Playwright")
                logger.warning(f"Sofascore blocked HTTP request ({resp.status_code}) for {url}. Falling back to Playwright...")
                return self._request_playwright(url, params)
                
            resp.raise_for_status()
            # Reset circuit on HTTP success
            SofascoreClient._stealth_failures = 0
            SofascoreClient._stealth_circuit_open = False
            return resp.json()
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (403, 429):
                if SofascoreClient._stealth_circuit_open:
                    raise APIError(f"Sofascore blocked and stealth circuit is OPEN")
                return self._request_playwright(url, params)
            raise APIError(f"Sofascore Network error: {e}")

    def _request_playwright(self, url: str, params: dict | None = None) -> dict:
        """Stealth Playwright — intercept Sofascore's own API calls from schedule page."""
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        import urllib.parse
        import time
        import random
        import json as _json
        
        try:
            from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
        except ImportError:
            try:
                from stealth_utils import USER_AGENTS, BROWSER_ARGS
            except ImportError:
                USER_AGENTS = [
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
                ]
                BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
        
        if params:
            query = urllib.parse.urlencode(params)
            full_url = f"{url}?{query}"
        else:
            full_url = url
        
        # Extract the API path to know what response to intercept
        # e.g. /sport/football/scheduled-events/2026-05-13
        api_path = full_url.replace(self.base_url, "").lstrip("/")
        
        def _safe_close(ctx):
            try:
                ctx.close()
            except Exception:
                pass
        
        # Build the schedule page URL from the API endpoint
        # /sport/{sport}/scheduled-events/{date} → sofascore.com/{sport}/{date}
        schedule_url = None
        m = re.match(r"sport/([^/]+)/scheduled-events/(\d{4}-\d{2}-\d{2})", api_path)
        if m:
            sport_slug = m.group(1)
            date_str = m.group(2)
            schedule_url = f"https://www.sofascore.com/{sport_slug}/{date_str}"
        
        # For event-specific endpoints, extract event ID
        event_match = re.match(r"event/(\d+)/", api_path)
        event_id = event_match.group(1) if event_match else None
            
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
            
            for attempt, backoff in enumerate([5, 12], 1):
                captured_data = {}
                ua = random.choice(USER_AGENTS)
                context = browser.new_context(
                    user_agent=ua,
                    viewport={"width": 1440, "height": 900},
                    locale="en-US",
                )
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
                
                # Set up response interceptor for API calls
                all_api_responses = []
                
                def handle_response(response):
                    resp_url = response.url
                    # Capture ALL Sofascore API responses
                    if "api.sofascore.com" in resp_url and response.status == 200:
                        try:
                            json_data = response.json()
                            all_api_responses.append({"url": resp_url, "json": json_data})
                            # Check if this is the one we want
                            if api_path in resp_url:
                                captured_data["json"] = json_data
                                captured_data["url"] = resp_url
                                logger.info(f"[Sofascore stealth] Captured target: {resp_url[:100]}")
                            else:
                                logger.debug(f"[Sofascore stealth] Captured other: {resp_url[:100]}")
                        except Exception:
                            pass
                
                page.on("response", handle_response)
                
                try:
                    # Navigate to the appropriate Sofascore page
                    if schedule_url:
                        nav_url = schedule_url
                    elif event_id:
                        nav_url = f"https://www.sofascore.com/event/{event_id}"
                    else:
                        raise APIError(f"Sofascore stealth: no valid navigation target for path '{api_path}'")
                    
                    logger.info(f"[Sofascore stealth] Attempt {attempt}: navigating to {nav_url}")
                    page.goto(nav_url, wait_until="domcontentloaded", timeout=25000)
                    
                    # Wait for JS hydration + API calls
                    page.wait_for_timeout(6000)
                    
                    # Handle Cloudflare challenge
                    content = page.content()
                    if "Just a moment" in content:
                        logger.info("[Sofascore stealth] Cloudflare challenge, waiting 8s...")
                        page.wait_for_timeout(8000)
                    
                    # Check if we already captured API data during page load
                    if captured_data.get("json"):
                        logger.info(f"[Sofascore stealth] Intercepted during load: {captured_data.get('url', '?')[:80]}")
                        result = captured_data["json"]
                        _safe_close(context)
                        browser.close()
                        return result
                    
                    # Wait more — Sofascore may lazy-load after hydration
                    page.wait_for_timeout(5000)
                    
                    if captured_data.get("json"):
                        logger.info(f"[Sofascore stealth] Intercepted after wait")
                        result = captured_data["json"]
                        _safe_close(context)
                        browser.close()
                        return result
                    
                    # Try scrolling to trigger lazy loading
                    page.evaluate("window.scrollBy(0, 500)")
                    page.wait_for_timeout(3000)
                    
                    if captured_data.get("json"):
                        logger.info(f"[Sofascore stealth] Intercepted after scroll")
                        result = captured_data["json"]
                        _safe_close(context)
                        browser.close()
                        return result
                    
                    # Last resort: check all captured API responses
                    logger.info(f"[Sofascore stealth] No exact match for {api_path}. Captured {len(all_api_responses)} API responses.")
                    for resp in all_api_responses:
                        logger.info(f"  - {resp['url'][:120]}")
                    
                    # Try to find events in any captured response
                    for resp in all_api_responses:
                        if "events" in resp.get("json", {}):
                            logger.info(f"[Sofascore stealth] Found events in: {resp['url'][:100]}")
                            result = resp["json"]
                            _safe_close(context)
                            browser.close()
                            return result
                    
                    # Fallback: try __NEXT_DATA__ from SSR (has event data on event pages)
                    try:
                        next_data = page.evaluate("""() => {
                            const el = document.getElementById('__NEXT_DATA__');
                            return el ? JSON.parse(el.textContent) : null;
                        }""")
                        if next_data:
                            logger.info(f"[Sofascore stealth] Extracted __NEXT_DATA__ (keys: {list(next_data.get('props',{}).get('pageProps',{}).keys())[:5]})")
                            _safe_close(context)
                            browser.close()
                            return next_data
                    except Exception:
                        pass
                    
                    logger.warning(f"[Sofascore stealth] No API response captured on attempt {attempt}")
                    SofascoreClient._stealth_failures += 1
                    if SofascoreClient._stealth_failures >= SofascoreClient._STEALTH_FAILURE_THRESHOLD:
                        SofascoreClient._stealth_circuit_open = True
                        logger.warning(f"[Sofascore stealth] Circuit breaker OPEN after {SofascoreClient._stealth_failures} failures")
                    _safe_close(context)
                    if attempt < 2:
                        time.sleep(backoff)
                        continue
                    browser.close()
                    raise APIError(f"Sofascore stealth: no data intercepted for {api_path}")
                    
                except (APIError, APINotFoundError):
                    raise
                except Exception as e:
                    logger.warning(f"[Sofascore stealth] Attempt {attempt} error: {e}")
                    _safe_close(context)
                    if attempt < 2:
                        time.sleep(backoff)
                        continue
                    browser.close()
                    raise APIError(f"Sofascore stealth failed: {e}")
                finally:
                    _safe_close(context)
            
            browser.close()
            raise APIError(f"Sofascore stealth exhausted retries for {full_url}")

    # -------- REQUIRED INTERFACE IMPLEMENTATIONS --------

    def get_fixtures(self, date: str, sport: str = "football") -> list:
        """Get all scheduled events for a sport on a specific date (YYYY-MM-DD).
        
        Returns list of APIFixture objects (matching the common contract).
        """
        from .api_football import APIFixture
        from datetime import datetime, timezone
        
        try:
            data = self._request(f"/sport/{sport}/scheduled-events/{date}")
        except (APINotFoundError, APIError):
            return []
        
        raw_events = data.get("events", [])
        fixtures = []
        for ev in raw_events:
            try:
                event_id = str(ev.get("id", ""))
                tournament = ev.get("tournament", {})
                comp_name = tournament.get("name", "Unknown")
                home = ev.get("homeTeam", {}).get("name", "Unknown")
                away = ev.get("awayTeam", {}).get("name", "Unknown")
                
                # Convert Unix timestamp to ISO format
                ts = ev.get("startTimestamp")
                if ts:
                    kickoff = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    kickoff = date + "T00:00:00Z"
                
                status_desc = ev.get("status", {}).get("description", "Not started")
                
                fixtures.append(APIFixture(
                    external_id=event_id,
                    source="sofascore",
                    sport=sport if sport != "ice-hockey" else "hockey",
                    competition_name=comp_name,
                    home_team_name=home,
                    away_team_name=away,
                    kickoff=kickoff,
                    status=status_desc,
                ))
            except Exception as e:
                logger.debug(f"Skipping Sofascore event: {e}")
                continue
        
        return fixtures

    def get_fixture_stats(self, event_id: str) -> list:
        """Get match statistics for a specific fixture."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_fixture_stats — non-Sofascore ID: {event_id}")
            return []
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
        if not self._is_sofascore_id(team_id):
            logger.debug(f"Skipping get_team_last_fixtures — non-Sofascore ID: {team_id}")
            return []
        try:
            # endpoint: /team/{id}/events/last/0 
            data = self._request(f"/team/{team_id}/events/last/0")
            events = data.get("events", [])
            return events[:last_n]
        except APINotFoundError:
            return []

    # -------- ADVANCED SOFASCORE SPECIFIC ENDPOINTS --------

    def get_pregame_form(self, event_id: str) -> dict:
        """Get pregame form data (W/L/D sequences, standings position, points)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_pregame_form — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/pregame-form")
        except (APINotFoundError, APIError):
            return {}

    def get_event_h2h(self, event_id: str) -> dict:
        """Get rich H2H stats for a specific event."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_h2h — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/h2h")
        except (APINotFoundError, APIError):
            return {}
            
    def get_event_odds(self, event_id: str) -> dict:
        """Get pre-match odds for an event (usually 1x2 and O/U)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_odds — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/odds/1/all")
        except (APINotFoundError, APIError):
            return {}

    def get_event_incidents(self, event_id: str) -> list:
        """Get match incidents (goals, cards, substitutions)."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_event_incidents — non-Sofascore ID: {event_id}")
            return []
        try:
            data = self._request(f"/event/{event_id}/incidents")
            return data.get("incidents", [])
        except APINotFoundError:
            return []

    def get_lineups(self, event_id: str) -> dict:
        """Get starting lineups, benches, and formations."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_lineups — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/lineups")
        except APINotFoundError:
            return {}
            
    def get_player_stats(self, event_id: str) -> dict:
        """Get individual player summary statistics for a match."""
        if not self._is_sofascore_id(event_id):
            logger.debug(f"Skipping get_player_stats — non-Sofascore ID: {event_id}")
            return {}
        try:
            return self._request(f"/event/{event_id}/lineups/statistics")
        except APINotFoundError:
            return {}
