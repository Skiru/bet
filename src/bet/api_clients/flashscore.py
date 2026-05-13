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

    def _request_playwright(self, url: str, params: dict | None = None) -> str:
        """Fallback method using Playwright stealth to bypass Cloudflare/DataDome."""
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
        import time
        import random

        logger.info(f"[Flashscore] Using Playwright stealth fallback for: {url}")
        
        try:
            from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked
        except ImportError:
            try:
                from stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked
            except ImportError:
                USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
                BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
                def is_actually_blocked(content, status_code):
                    if status_code in (403, 429) and len(content) < 15_000:
                        return True
                    if len(content) < 10_000:
                        lower = content.lower()
                        if any(kw in lower for kw in ("zablokowany", "access denied", "you have been blocked")):
                            return True
                    return False

        # Build URL with params if any
        if params:
            import urllib.parse
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=BROWSER_ARGS
            )
            
            for attempt, backoff in enumerate([3, 10], 1):
                context = browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080}
                )
                page = context.new_page()
                Stealth().apply_stealth_sync(page)
                
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                    status_code = response.status if response else 0
                    page.wait_for_timeout(2000)  # Let dynamic protections resolve
                    
                    content = page.content()
                    
                    # Cloudflare JS challenge wait
                    if "Just a moment" in content or "cf-browser-verification" in content:
                        logger.warning("[Flashscore] Cloudflare challenge detected, waiting...")
                        page.wait_for_timeout(5000)
                        content = page.content()
                    
                    if is_actually_blocked(content, status_code):
                        logger.warning(f"[Flashscore] Playwright blocked by Cloudflare/DataDome on attempt {attempt}.")
                        context.close()
                        if attempt < 2:
                            time.sleep(backoff)
                            continue
                        browser.close()
                        raise APIError(f"Blocked by Cloudflare/DataDome: {url}", status_code=403)
                    
                    text = page.inner_text("body")
                    context.close()
                    browser.close()
                    return text
                except APIError:
                    raise
                except Exception as e:
                    logger.error(f"[Flashscore] Playwright fetch failed on attempt {attempt}: {e}")
                    context.close()
                    if attempt < 2:
                        time.sleep(backoff)
                        continue
                    raise APIError(f"Flashscore Playwright error: {e}")
                finally:
                    if not context.is_closed():
                        context.close()
                        
            browser.close()

    def _request(self, endpoint: str, params: dict | None = None) -> str:
        """Flashscore usually returns a custom delimited format or JSON depending on the endpoint."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=self.TIMEOUT)
            if resp.status_code == 404:
                raise APINotFoundError(f"Resource not found: {url}")
            if resp.status_code in (403, 429):
                logger.warning(f"Flashscore Access denied/Rate limit ({resp.status_code}): {url}. Retrying with Playwright...")
                return self._request_playwright(url, params)
                
            resp.raise_for_status()
            # Flashscore feeds are often returning custom text separated by ¬ or ÷
            return resp.text
        except requests.exceptions.RequestException as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (403, 429):
                logger.warning(f"Flashscore blocked ({e.response.status_code}): {e}. Retrying with Playwright...")
                return self._request_playwright(url, params)
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
