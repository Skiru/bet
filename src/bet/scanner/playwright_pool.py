"""Managed pool of Playwright browser contexts for concurrent scraping.

Uses asyncio.Semaphore to cap the number of simultaneous browser contexts.
"""

import asyncio
import logging

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

logger = logging.getLogger(__name__)


class PlaywrightPool:
    """Pool of Playwright browser contexts for concurrent scraping.

    Usage::

        async with PlaywrightPool(max_contexts=4) as pool:
            html = await pool.scrape_page("https://example.com")
    """

    def __init__(self, max_contexts: int = 4, headless: bool = True):
        self._max = max_contexts
        self._headless = headless
        self._semaphore = asyncio.Semaphore(max_contexts)
        self._playwright = None
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []

    async def __aenter__(self) -> "PlaywrightPool":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Close all open contexts
        for ctx in list(self._contexts):
            try:
                await ctx.close()
            except Exception:
                pass
        self._contexts.clear()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def acquire(self) -> Page:
        """Acquire a new page from a fresh browser context.

        Blocks via semaphore when all context slots are in use.
        """
        await self._semaphore.acquire()
        ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._contexts.append(ctx)
        page = await ctx.new_page()
        return page

    async def release(self, page: Page) -> None:
        """Close the page's context and release the semaphore slot."""
        ctx = page.context
        try:
            await ctx.close()
        except Exception:
            pass
        if ctx in self._contexts:
            self._contexts.remove(ctx)
        self._semaphore.release()

    async def scrape_page(
        self,
        url: str,
        wait_selector: str | None = None,
        timeout_ms: int = 15000,
    ) -> str:
        """Convenience: acquire page, navigate, return HTML, release.

        Args:
            url: URL to navigate to.
            wait_selector: Optional CSS selector to wait for before grabbing HTML.
            timeout_ms: Navigation timeout in milliseconds (default 15s).

        Returns:
            Page HTML content.

        Raises:
            TimeoutError: If navigation or selector wait exceeds timeout.
        """
        page = await self.acquire()
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_selector:
                await page.wait_for_selector(wait_selector, timeout=timeout_ms)
            return await page.content()
        finally:
            await self.release(page)
