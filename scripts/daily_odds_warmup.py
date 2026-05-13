#!/usr/bin/env python3
"""S0.1 — Daily Odds Warm-Up (Stealth Dump)

This script runs at the very beginning of the pipeline (or orchestrated daily)
to safely fetch the HTML from Betclic/OddsPortal using Playwright with stealth 
injections. It dumps the CSS/HTML to a local cache to prevent getting 403s on 
frequent programmatic accesses.

Downstream scripts and DB loaders can then parse these HTML files using local Regex
or BeautifulSoup instantly.
"""

import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "betting" / "data" / "html_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"source": "betclic", "sport": "football", "url": "https://www.betclic.pl/pilka-nozna-s1"},
    {"source": "betclic", "sport": "tennis", "url": "https://www.betclic.pl/tenis-s2"},
    {"source": "betclic", "sport": "basketball", "url": "https://www.betclic.pl/koszykowka-s4"},
    {"source": "betclic", "sport": "volleyball", "url": "https://www.betclic.pl/siatkowka-s18"},
    {"source": "betclic", "sport": "hockey", "url": "https://www.betclic.pl/hokej-na-lodzie-s13"},
]

async def stealth_fetch_and_dump():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"Starting Stealth HTML Dump for {today}")
    
    try:
        from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_async
        import random
    except ImportError:
        try:
            from stealth_utils import USER_AGENTS, BROWSER_ARGS, is_actually_blocked, random_delay_async
            import random
        except ImportError:
            USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
            BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']
            def is_actually_blocked(content, status_code):
                return "datadome" in content.lower() or "cloudflare" in content.lower() or "zablokowany" in content.lower()
            async def random_delay_async(min_s, max_s):
                await asyncio.sleep(min_s)
            import random
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=BROWSER_ARGS
        )
        
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL",
        )
        
        # Inject stealth to bypass Datadome/Cloudflare easily on fast dumps
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)
        
        for idx, target in enumerate(TARGETS):
            if idx > 0 and idx % 2 == 0:
                print("Rotating browser context...")
                await context.close()
                await random_delay_async(5, 10)
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="pl-PL",
                )
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
            elif idx > 0:
                await random_delay_async(5, 10)

            print(f"Fetching {target['source']} - {target['sport']} ({target['url']})...")
            
            for backoff in [8, 20]:
                try:
                    response = await page.goto(target['url'], wait_until="domcontentloaded", timeout=45000)
                    
                    # Human-like wait to allow heavy JS objects/tables to render into DOM
                    await page.wait_for_timeout(3500)
                    
                    # Auto-scroll slowly to trigger lazy-loaded odds tables (Betclic often uses this)
                    for _ in range(3):
                        await page.mouse.wheel(0, 1000)
                        await page.wait_for_timeout(800)
                    
                    content = await page.content()
                    status_code = response.status if response else 0
                    
                    if is_actually_blocked(content, status_code):
                        print(f"  [X] BLOCKED: Datadome detected for {target['sport']}")
                        print(f"  Waiting {backoff}s before retry...")
                        await asyncio.sleep(backoff)
                        continue
                        
                    out_file = CACHE_DIR / f"{today}_{target['source']}_{target['sport']}.html"
                    with open(out_file, "w") as f:
                        f.write(content)
                        
                    print(f"  [V] SUCCESS: Saved {len(content)} bytes to {out_file.name}")
                    break
                    
                except Exception as e:
                    print(f"  [!] ERROR: Failed to fetch {target['sport']} -> {e}")
                    if backoff == 8:
                        await asyncio.sleep(8)
                    elif backoff == 20:
                        await asyncio.sleep(20)
                
        await context.close()
        await browser.close()
        print("Warmup complete. HTML dumps ready for local parsing.")

if __name__ == "__main__":
    asyncio.run(stealth_fetch_and_dump())