import asyncio
import random
from typing import Optional

async def stealth_fetch(url: str, headless: bool = True, wait_time: int = 2000) -> Optional[str]:
    """
    Safely fetches a URL using Playwright with stealth modifications.
    Used to bypass 403 blocks from Cloudflare/Datadome on OddsPortal and Betclic.
    """
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth
    except ImportError:
        print("[stealth_fetch] ERROR: playwright or playwright-stealth not installed.")
        return None

    try:
        from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked
    except ImportError:
        try:
            from stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked
        except ImportError:
            USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
            BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
            def is_actually_blocked(content, status_code):
                return "datadome" in content.lower() or "cloudflare" in content.lower() or "zablokowany" in content.lower()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=BROWSER_ARGS
        )
        
        for attempt, backoff in enumerate([5, 15, 30], 1):
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1920, "height": 1080},
                locale="pl-PL",
            )
            
            page = await context.new_page()
            
            try:
                await Stealth().apply_stealth_async(page)
                print(f"[stealth_fetch] Navigating to {url} (Attempt {attempt})...")
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                status_code = response.status if response else 0
                
                if status_code in (403, 429):
                    print(f"[stealth_fetch] WARNING: HTTP {status_code} returned. Blocked?")
                    
                # Wait for dynamic content to load (like odds tables)
                await page.wait_for_timeout(wait_time)
                
                content = await page.content()
                
                # Wait for Cloudflare JS challenge to resolve
                if "Just a moment" in content or "cf-browser-verification" in content:
                    print(f"[stealth_fetch] Cloudflare challenge detected, waiting 5s...")
                    await page.wait_for_timeout(5000)
                    content = await page.content()
                
                if is_actually_blocked(content, status_code):
                    print(f"[stealth_fetch] ERROR: Encountered bot protection on {url}.")
                    await context.close()
                    if attempt < 3:
                        print(f"Waiting {backoff}s before retry...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        await browser.close()
                        return None
                    
                await context.close()
                await browser.close()
                return content
                
            except Exception as e:
                print(f"[stealth_fetch] Exception fetching {url}: {e}")
                await context.close()
                if attempt < 3:
                    await asyncio.sleep(backoff)
                    continue
                else:
                    await browser.close()
                    return None
