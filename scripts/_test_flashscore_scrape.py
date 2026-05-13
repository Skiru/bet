"""Test Flashscore scraping approaches.

Tests:
1. curl_cffi → flashscore.ninja internal API feeds
2. Playwright stealth → flashscore.com DOM scraping
3. Playwright stealth → intercept flashscore.ninja XHR from rendered page
"""
import sys
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TARGET_DATE = "2026-05-13"
SPORT = "football"

# Flashscore sport codes for internal API
SPORT_CODES = {
    "football": 1,
    "tennis": 2,
    "basketball": 3,
    "hockey": 4,
    "volleyball": 12,
}

# ── Approach 1: curl_cffi to flashscore.ninja ──────────────────────────────

def test_curl_cffi():
    """Try curl_cffi with TLS impersonation to hit flashscore.ninja."""
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        logger.error("curl_cffi not installed — skip")
        return None

    logger.info("=== APPROACH 1: curl_cffi → flashscore.ninja ===")

    # Multiple endpoints to try
    endpoints = [
        # Sport fixtures feed
        f"https://local-global.flashscore.ninja/2/x/feed/f_1_0_{TARGET_DATE.replace('-', '')}_0_2_en-gb_1",
        # Alternative feed format
        f"https://d.flashscore.com/x/feed/f_1_0_{TARGET_DATE.replace('-', '')}_0_2_en-gb_1",
        # Today's summary feed  
        f"https://local-global.flashscore.ninja/2/x/feed/tr_1_0_en-gb_1",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.flashscore.com/",
        "x-fsign": "SW9D1eZo",
    }

    for url in endpoints:
        try:
            logger.info(f"  Trying: {url[:80]}...")
            resp = curl_requests.get(
                url,
                headers=headers,
                impersonate="chrome",
                timeout=15,
            )
            logger.info(f"  Status: {resp.status_code}, Length: {len(resp.text)}")
            if resp.status_code == 200 and len(resp.text) > 100:
                # Show first 500 chars
                preview = resp.text[:500]
                logger.info(f"  Preview: {preview}")
                return resp.text
            else:
                logger.warning(f"  Got {resp.status_code} or short response")
        except Exception as e:
            logger.error(f"  Error: {e}")
    
    return None


# ── Approach 2: Playwright DOM scraping ────────────────────────────────────

def test_playwright_dom():
    """Use Playwright stealth to load flashscore.com and scrape DOM."""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        logger.error("playwright/playwright_stealth not installed — skip")
        return None

    logger.info("=== APPROACH 2: Playwright DOM scraping ===")

    url = f"https://www.flashscore.com/{SPORT}/"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        logger.info(f"  Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        # Handle cookie consent
        try:
            consent_btn = page.locator("#onetrust-accept-btn-handler")
            if consent_btn.is_visible(timeout=3000):
                consent_btn.click()
                logger.info("  Clicked cookie consent")
                page.wait_for_timeout(1000)
        except Exception:
            pass

        # Check if blocked
        content = page.content()
        if "Just a moment" in content:
            logger.info("  Cloudflare challenge detected, waiting 8s...")
            page.wait_for_timeout(8000)
            content = page.content()
        
        if len(content) < 5000:
            logger.error(f"  Likely blocked — content only {len(content)} bytes")
            browser.close()
            return None

        logger.info(f"  Page loaded: {len(content)} bytes")

        # Try multiple selector strategies to find events
        selectors_to_try = [
            # Modern Flashscore selectors  
            ".event__match",
            ".sportName.soccer .event__match",
            "[class*='event__match']",
            # League headers
            ".event__title",
            # Participant names
            ".event__participant",
            # Generic containers
            ".leagues--live",
            ".event",
            # Newer structure
            "[class*='EventRow']",
            "[class*='event_']",
            "div[id^='g_1_']",
        ]

        found_any = False
        for sel in selectors_to_try:
            try:
                count = page.locator(sel).count()
                if count > 0:
                    logger.info(f"  ✓ Selector '{sel}': {count} elements")
                    found_any = True
                    # Get first few elements' text
                    if count > 0 and count <= 5:
                        for i in range(min(count, 3)):
                            text = page.locator(sel).nth(i).inner_text()
                            logger.info(f"    [{i}]: {text[:120]}")
                    elif count > 5:
                        text = page.locator(sel).first.inner_text()
                        logger.info(f"    [0]: {text[:120]}")
            except Exception as e:
                pass

        if not found_any:
            logger.warning("  No known selectors matched. Dumping page structure...")
            # Get all divs with class containing 'event'
            try:
                event_divs = page.evaluate("""() => {
                    const els = document.querySelectorAll('[class*="event"]');
                    return Array.from(els).slice(0, 20).map(el => ({
                        tag: el.tagName,
                        class: el.className,
                        id: el.id,
                        text: el.textContent?.substring(0, 80)
                    }));
                }""")
                for div in event_divs:
                    logger.info(f"    {div}")
            except Exception as e:
                logger.error(f"  Could not dump structure: {e}")

        # Also look at all class names containing interesting patterns
        try:
            classes = page.evaluate("""() => {
                const allClasses = new Set();
                document.querySelectorAll('*').forEach(el => {
                    el.classList.forEach(c => {
                        if (c.includes('event') || c.includes('match') || c.includes('team') || c.includes('sport') || c.includes('league') || c.includes('participant'))
                            allClasses.add(c);
                    });
                });
                return Array.from(allClasses).sort().slice(0, 50);
            }""")
            logger.info(f"  Relevant CSS classes found ({len(classes)}):")
            for c in classes:
                logger.info(f"    .{c}")
        except Exception as e:
            logger.error(f"  CSS class scan error: {e}")

        browser.close()
    
    return found_any


# ── Approach 3: Playwright XHR intercept ───────────────────────────────────

def test_playwright_xhr():
    """Use Playwright to intercept flashscore.ninja XHR calls from the real site."""
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        logger.error("playwright/playwright_stealth not installed — skip")
        return None

    logger.info("=== APPROACH 3: Playwright XHR intercept ===")
    
    url = f"https://www.flashscore.com/{SPORT}/"
    captured_responses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-GB",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)

        def handle_response(response):
            resp_url = response.url
            if ("flashscore" in resp_url or "fls" in resp_url) and response.status == 200:
                try:
                    body = response.text()
                    if len(body) > 100:
                        captured_responses.append({
                            "url": resp_url,
                            "length": len(body),
                            "preview": body[:300],
                        })
                except Exception:
                    pass

        page.on("response", handle_response)

        logger.info(f"  Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        
        # Handle cookie consent  
        try:
            consent_btn = page.locator("#onetrust-accept-btn-handler")
            if consent_btn.is_visible(timeout=3000):
                consent_btn.click()
                page.wait_for_timeout(1000)
        except Exception:
            pass

        page.wait_for_timeout(8000)  # Wait for all XHR calls

        logger.info(f"  Captured {len(captured_responses)} responses:")
        for resp in captured_responses:
            logger.info(f"    URL: {resp['url'][:120]}")
            logger.info(f"    Length: {resp['length']}")
            if "¬" in resp["preview"]:
                logger.info(f"    Format: Flashscore delimited (¬)")
                logger.info(f"    Preview: {resp['preview'][:200]}")
            elif resp["preview"].startswith("{"):
                logger.info(f"    Format: JSON")
                logger.info(f"    Preview: {resp['preview'][:200]}")
            else:
                logger.info(f"    Preview: {resp['preview'][:100]}")

        browser.close()
    
    return captured_responses


if __name__ == "__main__":
    results = {}
    
    # Test 1: curl_cffi
    r1 = test_curl_cffi()
    results["curl_cffi"] = "OK" if r1 else "FAILED"
    
    print("\n" + "="*60)
    
    # Test 2: Playwright DOM
    r2 = test_playwright_dom()
    results["playwright_dom"] = "OK" if r2 else "FAILED"
    
    print("\n" + "="*60)

    # Test 3: Playwright XHR
    r3 = test_playwright_xhr()
    results["playwright_xhr"] = "OK" if r3 else "FAILED"
    
    print("\n" + "="*60)
    print("RESULTS:")
    for approach, status in results.items():
        print(f"  {approach}: {status}")
