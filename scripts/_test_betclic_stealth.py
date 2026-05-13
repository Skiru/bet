#!/usr/bin/env python3
"""Live test: stealth Playwright against Betclic.pl

Tests multiple Betclic endpoints to verify stealth bypasses Datadome/Cloudflare:
1. Sport listing pages (football, tennis, basketball, volleyball, hockey)
2. A specific match page (first link found)
3. Check for block indicators (datadome, captcha, zablokowany, 403)

Usage:
    python3 scripts/_test_betclic_stealth.py
    python3 scripts/_test_betclic_stealth.py --headed   # visible browser
"""
import asyncio
import argparse
import time
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

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
            lower = content.lower()
            return "datadome" in lower or "cloudflare" in lower or "zablokowany" in lower
        async def random_delay_async(min_s, max_s):
            await asyncio.sleep(min_s)
        import random


BETCLIC_URLS = [
    ("football",   "https://www.betclic.pl/pilka-nozna-s1"),
    ("tennis",     "https://www.betclic.pl/tenis-s2"),
    ("basketball", "https://www.betclic.pl/koszykowka-s4"),
    ("volleyball", "https://www.betclic.pl/siatkowka-s18"),
    ("hockey",     "https://www.betclic.pl/hokej-na-lodzie-s13"),
]

async def run_tests(headed: bool):
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            args=BROWSER_ARGS
        )
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="pl-PL",
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        match_url = None

        # Test 1: Sport listing pages
        print("=" * 70)
        print("TEST 1: Sport Listing Pages")
        print("=" * 70)
        
        for idx, (sport, url) in enumerate(BETCLIC_URLS):
            if idx > 0 and idx % 3 == 0:
                print("Rotating context...")
                await context.close()
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1920, "height": 1080},
                    locale="pl-PL",
                )
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
            elif idx > 0:
                await random_delay_async(3, 6)
                
            t0 = time.time()
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)

                # Scroll to trigger lazy loading
                for _ in range(2):
                    await page.mouse.wheel(0, 800)
                    await page.wait_for_timeout(500)

                content = await page.content()
                elapsed = time.time() - t0
                status = resp.status if resp else 0
                content_len = len(content)

                # Try to find a match link for test 2
                if match_url is None:
                    links = await page.query_selector_all("a[href*='/mecz/']")
                    if not links:
                        links = await page.query_selector_all("a[href*='/match/']")
                    if not links:
                        links = await page.query_selector_all("a[href*='/-e']")
                    if not links:
                        # Betclic uses event links like /pilka-nozna/liga/event-eXXXXX
                        all_links = await page.query_selector_all("a[href]")
                        for link in all_links[:100]:
                            href = await link.get_attribute("href")
                            if href and ("-e" in href or "/event" in href) and sport in (href or ""):
                                links = [link]
                                break
                    # Last resort: find any link with a numeric suffix (Betclic event pattern)
                    if not links:
                        all_links = await page.query_selector_all("a.cardEvent")
                        if not all_links:
                            all_links = await page.query_selector_all("[data-qa='event-card'] a")
                        if not all_links:
                            all_links = await page.query_selector_all("a.is-event, a.event-link, a.sportEvent")
                        links = all_links[:1]
                    if links:
                        href = await links[0].get_attribute("href")
                        if href:
                            match_url = f"https://www.betclic.pl{href}" if href.startswith("/") else href
                            print(f"     → found match link: {match_url}")

                # Check for actual betting content (odds, match names)
                betting_keywords = ["zakład", "kurs", "mecz", "wynik", "over", "under", "handicap", "total",
                                    "1x2", "poniżej", "powyżej", "gole", "sety", "gemy"]
                betting_hits = [kw for kw in betting_keywords if kw in content.lower()]
                has_betting_content = len(betting_hits) >= 2
                
                blocked_status = is_actually_blocked(content, status)

                if blocked_status:
                    verdict = "BLOCKED"
                elif has_betting_content:
                    verdict = "OK"
                else:
                    verdict = "UNCLEAR"

                result = {"sport": sport, "status": status, "size": content_len, "time": f"{elapsed:.1f}s", "verdict": verdict, "betting_hits": betting_hits}
                results.append(result)
                icon = "✅" if verdict == "OK" else "❌"
                print(f"  {icon} {sport:12s} | HTTP {status} | {content_len:>7,} bytes | {elapsed:.1f}s | {verdict}")
                if betting_hits:
                    print(f"     betting keywords found: {', '.join(betting_hits[:8])}")

            except Exception as e:
                elapsed = time.time() - t0
                result = {"sport": sport, "status": "ERROR", "size": 0, "time": f"{elapsed:.1f}s", "verdict": f"ERROR: {e}", "blocks": []}
                results.append(result)
                print(f"  ❌ {sport:12s} | ERROR | {elapsed:.1f}s | {e}")

        # Test 2: Specific match page
        print()
        print("=" * 70)
        print("TEST 2: Match Detail Page")
        print("=" * 70)
        # Try to find a real match/event link from the last loaded page
        import re as _re
        page_html = await page.content()
        # Betclic event URLs look like: /pilka-nozna/.../-eXXXXX or contain /wydarzenie/
        event_re = _re.compile(r'href="(/[^"]*-e\d{5,}[^"]*)"')
        event_matches = event_re.findall(page_html)
        if event_matches:
            match_url = f"https://www.betclic.pl{event_matches[0]}"
        elif match_url and "-e" not in match_url:
            match_url = None  # discard category links

        if match_url:
            t0 = time.time()
            try:
                resp = await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                content = await page.content()
                elapsed = time.time() - t0
                status = resp.status if resp else 0
                content_len = len(content)

                betting_keywords = ["zakład", "kurs", "mecz", "wynik", "over", "under", "handicap", "total",
                                    "1x2", "poniżej", "powyżej", "gole", "sety", "gemy"]
                betting_hits = [kw for kw in betting_keywords if kw in content.lower()]
                has_betting_content = len(betting_hits) >= 2

                blocked_status = is_actually_blocked(content, status)

                if blocked_status:
                    verdict = "BLOCKED"
                elif has_betting_content:
                    verdict = "OK"
                else:
                    verdict = "UNCLEAR"

                icon = "✅" if verdict.startswith("OK") else "❌"
                print(f"  {icon} {match_url}")
                print(f"     HTTP {status} | {content_len:>7,} bytes | {elapsed:.1f}s | {verdict}")
                if betting_hits:
                    print(f"     betting keywords: {', '.join(betting_hits[:8])}")
            except Exception as e:
                elapsed = time.time() - t0
                print(f"  ❌ {match_url}")
                print(f"     ERROR | {elapsed:.1f}s | {e}")
        else:
            print("  ⚠️  No match/event link found (no -eXXXXX pattern) — skipping")

        # Test 3: Navigator checks (bot detection)
        print()
        print("=" * 70)
        print("TEST 3: Bot Detection Fingerprint")
        print("=" * 70)
        webdriver = await page.evaluate("() => navigator.webdriver")
        plugins_len = await page.evaluate("() => navigator.plugins.length")
        languages = await page.evaluate("() => navigator.languages")
        print(f"  navigator.webdriver = {webdriver}  {'✅' if not webdriver else '❌ (should be false/undefined)'}")
        print(f"  navigator.plugins   = {plugins_len} plugins  {'✅' if plugins_len > 0 else '⚠️  (0 plugins looks bot-like)'}")
        print(f"  navigator.languages = {languages}")

        await browser.close()

    # Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    ok_count = sum(1 for r in results if r["verdict"].startswith("OK"))
    total = len(results)
    print(f"  {ok_count}/{total} sport pages loaded successfully")
    if ok_count == total:
        print("  ✅ STEALTH IS WORKING — Betclic is not blocking us")
    elif ok_count > 0:
        print("  ⚠️  PARTIAL — Some pages blocked, stealth may need tuning")
    else:
        print("  ❌ ALL BLOCKED — Stealth is NOT working against Betclic")

    return ok_count == total


def main():
    parser = argparse.ArgumentParser(description="Live test stealth Playwright on Betclic")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    args = parser.parse_args()

    success = asyncio.run(run_tests(headed=args.headed))
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
