"""Base class for Playwright-based API clients."""
import logging
import random
import time

from .base_client import BaseAPIClient, APIError

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

logger = logging.getLogger(__name__)


class PlaywrightBaseClient(BaseAPIClient):
    """Base client for Playwright DOM scraping.

    Uses stealth Playwright to render pages and extract structured data.
    Lazy-initializes browser on first use; reuses context across calls.
    """

    # Circuit breaker
    _failures = 0
    _circuit_open = False
    _circuit_opened_at = 0
    _CIRCUIT_COOLDOWN = 300
    _FAILURE_THRESHOLD = 3

    _COOKIE_SELECTOR = "#onetrust-accept-btn-handler"
    _COOKIE_TIMEOUT = 2500

    def __init__(self, api_name: str, base_url: str, rate_limiter=None):
        super().__init__(api_name, base_url, rate_limiter)
        self.api_key = "no-key"
        self._playwright = None
        self._browser = None

    def is_available(self) -> bool:
        return True

    def _ensure_browser(self):
        """Lazy-init Playwright browser."""
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=True, args=BROWSER_ARGS,
            )
        except Exception as e:
            logger.error(f"[{self.api_name.capitalize()}] Failed to launch browser: {e}")
            raise APIError(f"{self.api_name.capitalize()} browser launch failed: {e}")

    def _new_page(self):
        """Create a new stealth page with random UA."""
        try:
            from playwright_stealth import Stealth
        except ImportError:
            Stealth = None

        ctx = self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        try:
            page = ctx.new_page()
            if Stealth:
                Stealth().apply_stealth_sync(page)
            return ctx, page
        except Exception:
            ctx.close()
            raise

    def _dismiss_cookies(self, page):
        """Dismiss cookie consent banner if present."""
        if not self._COOKIE_SELECTOR:
            return
        try:
            consent = page.locator(self._COOKIE_SELECTOR)
            if consent.is_visible(timeout=self._COOKIE_TIMEOUT):
                consent.click()
                page.wait_for_timeout(800)
        except Exception:
            pass

    def _handle_cloudflare(self, page) -> bool:
        """Wait for Cloudflare challenge if detected. Returns True if blocked."""
        content = page.content()
        if "Just a moment" in content or "cf-browser-verification" in content:
            logger.info(f"[{self.api_name.capitalize()}] Cloudflare challenge detected, waiting 8s...")
            page.wait_for_timeout(8000)
            content = page.content()
            if "Just a moment" in content:
                return True
        try:
            body_text = page.inner_text('body')
            return len(body_text) < 500
        except Exception:
            return len(content) < 3000

    def _load_page(self, url: str, wait_ms: int = 5000, max_retries: int = 2) -> tuple:
        """Load a page with stealth, retrying on failure.

        Returns (context, page) on success.
        Raises APIError on persistent failure.
        """
        if type(self)._circuit_open:
            if time.time() - type(self)._circuit_opened_at > type(self)._CIRCUIT_COOLDOWN:
                type(self)._circuit_open = False
                type(self)._failures = 0
                logger.info(f"[{self.api_name.capitalize()}] Circuit breaker reset after cooldown")
            else:
                raise APIError(f"{self.api_name.capitalize()} circuit breaker is OPEN — too many failures")

        self._ensure_browser()

        for attempt in range(1, max_retries + 1):
            ctx, page = self._new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(wait_ms)
                self._dismiss_cookies(page)

                if self._handle_cloudflare(page):
                    logger.warning(f"[{self.api_name.capitalize()}] Blocked on attempt {attempt}")
                    ctx.close()
                    if attempt < max_retries:
                        time.sleep(3 * attempt)
                        continue
                    type(self)._failures += 1
                    if type(self)._failures >= type(self)._FAILURE_THRESHOLD:
                        type(self)._circuit_open = True
                        type(self)._circuit_opened_at = time.time()
                    raise APIError(f"{self.api_name.capitalize()} blocked by Cloudflare", status_code=403)

                # Success — reset failure counter
                type(self)._failures = 0
                return ctx, page

            except APIError:
                try:
                    ctx.close()
                except Exception:
                    pass
                raise
            except Exception as e:
                logger.warning(f"[{self.api_name.capitalize()}] Page load attempt {attempt} failed: {e}")
                try:
                    ctx.close()
                except Exception:
                    pass
                if attempt < max_retries:
                    time.sleep(3 * attempt)
                    continue
                type(self)._failures += 1
                raise APIError(f"{self.api_name.capitalize()} page load failed: {e}")

    def _evaluate_js(self, page, js_code: str):
        try:
            return page.evaluate(js_code)
        except Exception as e:
            logger.error(f"[{self.api_name.capitalize()}] JS evaluation failed: {e}")
            return None

    def close(self):
        """Clean up browser resources."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def get_fixtures(self, *args, **kwargs):
        raise NotImplementedError

    def get_fixture_stats(self, *args, **kwargs):
        raise NotImplementedError

    def get_h2h(self, *args, **kwargs):
        raise NotImplementedError
