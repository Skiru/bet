import asyncio
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

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
            ]
        )
        # Use a realistic user agent
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
        )
        
        page = await context.new_page()
        
        try:
            await Stealth().apply_stealth_async(page)
            print(f"[stealth_fetch] Navigating to {url}...")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            if response and response.status in (403, 429):
                print(f"[stealth_fetch] WARNING: HTTP {response.status} returned. Blocked?")
                
            # Wait for dynamic content to load (like odds tables)
            await page.wait_for_timeout(wait_time)
            
            content = await page.content()
            
            # Wait for Cloudflare JS challenge to resolve
            if "Just a moment" in content or "cf-browser-verification" in content:
                print(f"[stealth_fetch] Cloudflare challenge detected, waiting 5s...")
                await page.wait_for_timeout(5000)
                content = await page.content()
            
            # Check for generic Datadome/Cloudflare blocks
            lower_content = content.lower()
            if "datadome" in lower_content or "cloudflare" in lower_content or "zablokowany" in lower_content:
                print(f"[stealth_fetch] ERROR: Encountered bot protection on {url}.")
                return None
                
            return content
            
        except Exception as e:
            print(f"[stealth_fetch] Exception fetching {url}: {e}")
            return None
        finally:
            await browser.close()
