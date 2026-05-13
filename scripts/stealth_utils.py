"""Shared stealth Playwright utilities — UA rotation, block detection, retry logic."""
import asyncio
import random
import time
import logging

logger = logging.getLogger(__name__)

# Modern Chrome UAs (Chrome 134-136, macOS + Windows)
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
]

BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--disable-infobars',
    '--no-sandbox',
]

def is_actually_blocked(content: str, status_code: int) -> bool:
    """Detect real blocks vs false positives (large JS bundles contain 'datadome'/'captcha' keywords).
    
    Real blocks: HTTP 403/429 + tiny page (3-5KB).
    False positives: HTTP 200 + 400-600KB page with 'datadome' in JS bundles.
    """
    if status_code in (403, 429) and len(content) < 15_000:
        return True
    if len(content) < 10_000:
        lower = content.lower()
        if any(kw in lower for kw in ("zablokowany", "access denied", "you have been blocked")):
            return True
    return False

def random_delay_sync(min_s: float = 3.0, max_s: float = 6.0):
    """Synchronous random delay with uniform jitter."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"[stealth] Waiting {delay:.1f}s...")
    time.sleep(delay)

async def random_delay_async(min_s: float = 3.0, max_s: float = 6.0):
    """Async random delay with uniform jitter."""
    delay = random.uniform(min_s, max_s)
    logger.debug(f"[stealth] Waiting {delay:.1f}s...")
    await asyncio.sleep(delay)

def create_context_sync(browser, *, ua=None, locale="pl-PL"):
    """Create a new browser context with random UA."""
    return browser.new_context(
        user_agent=ua or random.choice(USER_AGENTS),
        viewport={"width": 1920, "height": 1080},
        locale=locale,
    )

async def create_context_async(browser, *, ua=None, locale="pl-PL"):
    """Create a new async browser context with random UA."""
    return await browser.new_context(
        user_agent=ua or random.choice(USER_AGENTS),
        viewport={"width": 1920, "height": 1080},
        locale=locale,
    )
