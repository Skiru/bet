#!/usr/bin/env python3
"""Probe Flashscore to discover working scraping approach.

Tests:
1. Playwright DOM scraping (listing page)
2. Playwright API interception (capture XHR/fetch calls)
3. curl_cffi with browser impersonation
4. Match detail page structure

Logs everything to stdout for analysis.
"""

import json
import sys
import time
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── Test URLs ──
LISTING_URL = "https://www.flashscore.com/football/"
MATCH_DETAIL_URL = None  # Will be discovered from listing
TEAM_URL = "https://www.flashscore.com/team/barcelona/xVflBRMl/"
H2H_URL = None  # Will be built from team URLs


def probe_playwright_dom():
    """Test 1: Scrape listing page DOM with Playwright stealth."""
    log.info("\n" + "=" * 70)
    log.info("TEST 1: Playwright DOM Scraping (listing page)")
    log.info("=" * 70)
    
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    try:
        from stealth_utils import USER_AGENTS, BROWSER_ARGS
    except ImportError:
        USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
        BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

    import random

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        log.info(f"Navigating to {LISTING_URL}...")
        response = page.goto(LISTING_URL, wait_until="networkidle", timeout=30_000)
        status = response.status if response else 0
        log.info(f"HTTP status: {status}")
        
        # Wait for dynamic content
        page.wait_for_timeout(3000)
        
        content = page.content()
        log.info(f"Page size: {len(content)} bytes")
        
        # Check for blocks
        if status in (403, 429) and len(content) < 15_000:
            log.info("BLOCKED by anti-bot!")
            context.close()
            browser.close()
            return None
        
        # Probe selectors from test files
        selectors_to_test = [
            ".event__match",
            ".event__homeParticipant", 
            ".event__awayParticipant",
            ".event__participant--home",
            ".event__participant--away",
            ".event__time",
            ".event__score--home",
            ".event__score--away",
            ".event__stage--block",
            ".eventRowLink",
            ".headerLeague__category-text",
            ".headerLeague__title-text",
            # New selectors to try
            "[class*='event']",
            "[class*='match']",
            "[class*='participant']",
            "[class*='score']",
            "[class*='league']",
            "[class*='fixture']",
            "[class*='game']",
            # Flashscore v4/v5 possible selectors
            ".sportName",
            ".leagues--static",
            ".event__header",
            ".event__title",
            "a[href*='/match/']",
        ]
        
        log.info("\n--- Selector probe ---")
        for sel in selectors_to_test:
            try:
                count = page.locator(sel).count()
                if count > 0:
                    log.info(f"  ✅ {sel}: {count} elements")
                    # Get sample text from first few
                    for i in range(min(3, count)):
                        text = page.locator(sel).nth(i).inner_text()
                        log.info(f"      [{i}] = {text[:100]}")
            except Exception as e:
                pass
        
        # Try to find match IDs
        log.info("\n--- Match ID probe ---")
        match_els = page.locator("[id^='g_']")
        id_count = match_els.count()
        log.info(f"Elements with id='g_*': {id_count}")
        for i in range(min(5, id_count)):
            el_id = match_els.nth(i).get_attribute("id")
            log.info(f"  {el_id}")
        
        # Try to find match links
        log.info("\n--- Match link probe ---")
        links = page.locator("a[href*='/match/']")
        link_count = links.count()
        log.info(f"Links with '/match/' in href: {link_count}")
        
        match_urls = []
        for i in range(min(5, link_count)):
            href = links.nth(i).get_attribute("href")
            log.info(f"  {href}")
            match_urls.append(href)
        
        # Dump a snippet of the page HTML around match elements
        log.info("\n--- Raw HTML snippet (first match area) ---")
        try:
            # Find first event-like container and get its outer HTML
            for sel in [".event__match", "[class*='event']", "[class*='match']"]:
                el = page.locator(sel).first
                if el.count() > 0:
                    html_snippet = el.evaluate("el => el.outerHTML")
                    log.info(f"Selector: {sel}")
                    log.info(html_snippet[:2000])
                    break
        except Exception as e:
            log.info(f"Could not extract snippet: {e}")
        
        # Try generic approach: get all text content and look for score patterns
        log.info("\n--- Text content analysis ---")
        body_text = page.inner_text("body")
        lines = body_text.split("\n")
        log.info(f"Total text lines: {len(lines)}")
        
        # Look for score-like patterns
        import re
        score_pattern = re.compile(r'\d+\s*[-:]\s*\d+')
        score_lines = [l.strip() for l in lines if score_pattern.search(l) and len(l.strip()) < 200]
        log.info(f"Lines with score patterns: {len(score_lines)}")
        for line in score_lines[:10]:
            log.info(f"  {line}")
        
        global MATCH_DETAIL_URL
        if match_urls:
            url = match_urls[0]
            if url.startswith("/"):
                url = "https://www.flashscore.com" + url
            MATCH_DETAIL_URL = url
        
        context.close()
        browser.close()
        return {"status": status, "page_size": len(content), "match_urls": match_urls}


def probe_playwright_intercept():
    """Test 2: Intercept XHR/fetch API calls that Flashscore makes."""
    log.info("\n" + "=" * 70)
    log.info("TEST 2: Playwright API Interception")
    log.info("=" * 70)
    
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    try:
        from stealth_utils import USER_AGENTS, BROWSER_ARGS
    except ImportError:
        USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
        BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

    import random
    
    captured_apis = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        def on_response(response):
            url = response.url
            status = response.status
            content_type = response.headers.get("content-type", "")
            
            # Capture API-like responses (JSON, text feeds)
            if any(kw in url for kw in ["flashscore", "fscdn", "feed", "api", "data", "ninja"]):
                entry = {
                    "url": url[:200],
                    "status": status,
                    "content_type": content_type,
                    "size": 0,
                }
                try:
                    body = response.body()
                    entry["size"] = len(body)
                    # Try to parse as JSON
                    if "json" in content_type or body[:1] in (b'{', b'['):
                        try:
                            data = json.loads(body)
                            entry["json_keys"] = list(data.keys()) if isinstance(data, dict) else f"array[{len(data)}]"
                            entry["sample"] = str(data)[:500]
                        except Exception:
                            pass
                    # If it's a text feed (¬ separated)
                    elif b'\xc2\xac' in body or b'\xc3\xb7' in body:
                        text = body.decode("utf-8", errors="replace")
                        entry["feed_format"] = "delimited"
                        entry["sample"] = text[:500]
                except Exception:
                    pass
                
                captured_apis.append(entry)
        
        page.on("response", on_response)
        
        log.info(f"Navigating to {LISTING_URL} with response interceptor...")
        page.goto(LISTING_URL, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(5000)
        
        log.info(f"\nCaptured {len(captured_apis)} API responses:")
        for i, api in enumerate(captured_apis):
            log.info(f"\n  [{i}] {api['url']}")
            log.info(f"      status={api['status']}, type={api['content_type']}, size={api['size']}")
            if "json_keys" in api:
                log.info(f"      JSON keys: {api['json_keys']}")
            if "feed_format" in api:
                log.info(f"      Feed format: {api['feed_format']}")
            if "sample" in api:
                log.info(f"      Sample: {api['sample'][:300]}")
        
        context.close()
        browser.close()
    
    return captured_apis


def probe_curl_cffi():
    """Test 3: Try curl_cffi with browser impersonation."""
    log.info("\n" + "=" * 70)
    log.info("TEST 3: curl_cffi Browser Impersonation")
    log.info("=" * 70)
    
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        log.info("curl_cffi not installed, skipping")
        return None
    
    # Try different endpoints
    urls_to_try = [
        ("Listing page", LISTING_URL),
        ("Feed endpoint", "https://local-global.flashscore.ninja/2/x/feed/f_1_0_3_en-gb_1"),
        ("D.flashscore feed", "https://d.flashscore.com/x/feed/f_1_0_3_en-gb_1"),
    ]
    
    for label, url in urls_to_try:
        log.info(f"\n  Trying {label}: {url}")
        try:
            resp = curl_requests.get(
                url,
                impersonate="chrome136",
                timeout=15,
                headers={
                    "Accept": "*/*",
                    "x-fsign": "SW9D1eZo",
                }
            )
            log.info(f"  Status: {resp.status_code}")
            log.info(f"  Size: {len(resp.content)} bytes")
            log.info(f"  Content-Type: {resp.headers.get('content-type', 'N/A')}")
            text = resp.text[:500]
            log.info(f"  Sample: {text}")
            
            # Check for feed format
            if '¬' in resp.text or '÷' in resp.text:
                log.info("  ✅ Feed format detected (¬/÷ delimiters)")
                # Parse feed
                parts = resp.text.split('¬')
                log.info(f"  Feed parts: {len(parts)}")
                for part in parts[:20]:
                    log.info(f"    {part}")
        except Exception as e:
            log.info(f"  Error: {e}")
    
    return True


def probe_match_detail():
    """Test 4: Probe match detail page for stats structure."""
    global MATCH_DETAIL_URL
    if not MATCH_DETAIL_URL:
        log.info("\n[SKIP] No match detail URL discovered")
        return None
    
    log.info("\n" + "=" * 70)
    log.info("TEST 4: Match Detail Page Structure")
    log.info("=" * 70)
    
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    try:
        from stealth_utils import USER_AGENTS, BROWSER_ARGS
    except ImportError:
        USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
        BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

    import random
    
    captured_apis = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        def on_response(response):
            url = response.url
            if any(kw in url for kw in ["flashscore", "fscdn", "feed", "api", "ninja"]):
                entry = {"url": url[:200], "status": response.status, "size": 0}
                try:
                    body = response.body()
                    entry["size"] = len(body)
                    text = body.decode("utf-8", errors="replace")
                    if '¬' in text:
                        entry["feed"] = True
                        entry["sample"] = text[:500]
                    elif body[:1] in (b'{', b'['):
                        try:
                            entry["json"] = json.loads(body)
                        except Exception:
                            pass
                except Exception:
                    pass
                captured_apis.append(entry)
        
        page.on("response", on_response)
        
        # Navigate to match detail
        stats_url = MATCH_DETAIL_URL
        if "#" not in stats_url:
            stats_url += "#/match-summary/match-statistics"
        
        log.info(f"Navigating to: {stats_url}")
        page.goto(stats_url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(5000)
        
        # Probe stat selectors
        stat_selectors = [
            ".stat__category",
            ".stat__homeValue",
            ".stat__awayValue",
            ".stat__categoryName",
            "[class*='stat']",
            "[class*='statistics']",
            "[class*='StatRow']",
            "[class*='statistic']",
            ".section",
            ".rows",
        ]
        
        log.info("\n--- Stat selector probe ---")
        for sel in stat_selectors:
            try:
                count = page.locator(sel).count()
                if count > 0:
                    log.info(f"  ✅ {sel}: {count} elements")
                    for i in range(min(5, count)):
                        text = page.locator(sel).nth(i).inner_text()
                        log.info(f"      [{i}] = {text[:150]}")
            except Exception:
                pass
        
        # Try H2H tab
        log.info("\n--- Navigating to H2H tab ---")
        h2h_url = MATCH_DETAIL_URL
        if "#" in h2h_url:
            h2h_url = h2h_url.split("#")[0]
        h2h_url += "#/h2h/overall"
        
        page.goto(h2h_url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(3000)
        
        h2h_selectors = [
            "[class*='h2h']",
            "[class*='head']",
            "[class*='rows']",
            "[class*='event']",
            ".h2h__section",
            ".h2h__row",
        ]
        
        log.info("\n--- H2H selector probe ---")
        for sel in h2h_selectors:
            try:
                count = page.locator(sel).count()
                if count > 0:
                    log.info(f"  ✅ {sel}: {count} elements")
                    for i in range(min(5, count)):
                        text = page.locator(sel).nth(i).inner_text()
                        log.info(f"      [{i}] = {text[:150]}")
            except Exception:
                pass
        
        # Show captured API calls
        log.info(f"\n--- Captured {len(captured_apis)} API calls from detail page ---")
        for api in captured_apis:
            log.info(f"  {api['url']} (status={api['status']}, size={api['size']})")
            if "sample" in api:
                log.info(f"    Feed sample: {api['sample'][:200]}")
        
        context.close()
        browser.close()
    
    return captured_apis


def main():
    log.info("Flashscore Scraping Probe")
    log.info(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Test 1: DOM scraping
    try:
        result = probe_playwright_dom()
        log.info(f"\n>>> Test 1 result: {result}")
    except Exception as e:
        log.info(f"\n>>> Test 1 FAILED: {e}")
    
    # Test 2: API interception  
    try:
        result = probe_playwright_intercept()
    except Exception as e:
        log.info(f"\n>>> Test 2 FAILED: {e}")
    
    # Test 3: curl_cffi
    try:
        result = probe_curl_cffi()
    except Exception as e:
        log.info(f"\n>>> Test 3 FAILED: {e}")
    
    # Test 4: Match detail
    try:
        result = probe_match_detail()
    except Exception as e:
        log.info(f"\n>>> Test 4 FAILED: {e}")
    
    log.info("\n" + "=" * 70)
    log.info("PROBE COMPLETE")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
