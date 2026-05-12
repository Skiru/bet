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
import datetime
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "betting" / "data" / "html_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {"source": "betclic", "sport": "football", "url": "https://www.betclic.pl/pilka-nozna-s1"},
    {"source": "betclic", "sport": "tennis", "url": "https://www.betclic.pl/tenis-s2"},
    {"source": "betclic", "sport": "basketball", "url": "https://www.betclic.pl/koszykowka-s4"},
    {"source": "betclic", "sport": "volleyball", "url": "https://www.betclic.pl/siatkowka-s18"},
]

async def stealth_fetch_and_dump():
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"Starting Stealth HTML Dump for {today}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        # Inject stealth to bypass Datadome/Cloudflare easily on fast dumps
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        page = await context.new_page()
        
        for target in TARGETS:
            print(f"Fetching {target['source']} - {target['sport']} ({target['url']})...")
            try:
                response = await page.goto(target['url'], wait_until="domcontentloaded", timeout=45000)
                
                # Human-like wait to allow heavy JS objects/tables to render into DOM
                await page.wait_for_timeout(3500)
                
                # Auto-scroll slowly to trigger lazy-loaded odds tables (Betclic often uses this)
                for _ in range(3):
                    await page.mouse.wheel(0, 1000)
                    await page.wait_for_timeout(800)
                
                content = await page.content()
                
                # Check for Datadome/Cloudflare or blocks
                if "datadome" in content.lower() or "cloudflare" in content.lower() or "zablokowany" in content.lower():
                    print(f"  [X] BLOCKED: CAPTCHA or Datadome detected for {target['sport']}")
                    continue
                    
                out_file = CACHE_DIR / f"{today}_{target['source']}_{target['sport']}.html"
                with open(out_file, "w") as f:
                    f.write(content)
                    
                print(f"  [V] SUCCESS: Saved {len(content)} bytes to {out_file.name}")
                
            except Exception as e:
                print(f"  [!] ERROR: Failed to fetch {target['sport']} -> {e}")
                
        await browser.close()
        print("Warmup complete. HTML dumps ready for local parsing.")

if __name__ == "__main__":
    asyncio.run(stealth_fetch_and_dump())