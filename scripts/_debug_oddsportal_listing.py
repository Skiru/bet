#!/usr/bin/env python3
"""Quick debug: save OddsPortal listing page HTML and extract game structure."""
import os
import random
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

try:
    from stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

URL = "https://www.oddsportal.com/matches/football/"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
    ctx = browser.new_context(
        user_agent=random.choice(USER_AGENTS),
        viewport={"width": 1920, "height": 1080},
        locale="en-GB",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)

    print(f"Navigating to {URL}")
    try:
        page.goto(URL, wait_until="networkidle", timeout=30000)
    except Exception:
        page.wait_for_timeout(8000)
    page.wait_for_timeout(3000)

    # Dismiss cookies
    try:
        btn = page.locator("#onetrust-accept-btn-handler")
        if btn.is_visible(timeout=2000):
            btn.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # Check current URL (may have been redirected)
    print(f"Current URL: {page.url}")
    body = page.inner_text("body")
    print(f"Body length: {len(body)}")

    # Save full HTML
    os.makedirs("betting/data/debug", exist_ok=True)
    html = page.content()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"betting/data/debug/oddsportal_listing_{ts}.html"
    with open(path, "w") as f:
        f.write(html)
    print(f"Saved to {path}")

    # Extract game structure with JS
    result = page.evaluate("""() => {
        const games = [];
        // Try data-testid selectors
        const gameRows = document.querySelectorAll('[data-testid="game-row"]');
        const eventRows = document.querySelectorAll('[data-testid="event-name"]');
        const matchRows = document.querySelectorAll('[class*="eventRow"]');
        
        // Broader search: all links containing /h2h/ (match detail links)
        const h2hLinks = document.querySelectorAll('a[href*="/h2h/"], a[href*="/match/"]');
        
        return {
            gameRowCount: gameRows.length,
            eventNameCount: eventRows.length,
            matchRowCount: matchRows.length,
            h2hLinkCount: h2hLinks.length,
            h2hSamples: Array.from(h2hLinks).slice(0, 10).map(a => ({
                href: a.href,
                text: a.textContent.trim().substring(0, 200),
                parentClasses: a.parentElement ? a.parentElement.className : '',
                grandparentClasses: a.parentElement && a.parentElement.parentElement ? a.parentElement.parentElement.className : '',
                grandparentTestId: a.parentElement && a.parentElement.parentElement ? a.parentElement.parentElement.getAttribute('data-testid') : '',
            })),
            gameRowSamples: Array.from(gameRows).slice(0, 3).map(r => ({
                innerHTML: r.innerHTML.substring(0, 800),
                classes: r.className,
                testId: r.getAttribute('data-testid'),
            })),
            eventNameSamples: Array.from(eventRows).slice(0, 3).map(r => ({
                text: r.textContent.trim().substring(0, 200),
                href: r.href || r.getAttribute('href') || '',
                parentClasses: r.parentElement ? r.parentElement.className : '',
            })),
        };
    }""")

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Also try broader game extraction
    result2 = page.evaluate("""() => {
        // Find all elements that look like they contain match data
        const allDivs = document.querySelectorAll('div[class*="border"]');
        const samples = [];
        for (let i = 0; i < Math.min(allDivs.length, 200); i++) {
            const div = allDivs[i];
            const text = div.textContent.trim();
            // Match patterns: team names typically have "–" or "vs" separators
            if (text.includes('–') && text.length > 20 && text.length < 500) {
                const gameRow = div.querySelector('[data-testid="game-row"]');
                samples.push({
                    classes: div.className.substring(0, 200),
                    text: text.substring(0, 300),
                    hasGameRow: !!gameRow,
                    childCount: div.children.length,
                });
                if (samples.length >= 5) break;
            }
        }
        return samples;
    }""")

    print("\n=== MATCH-LIKE DIVS ===")
    print(json.dumps(result2, indent=2, ensure_ascii=False))

    ctx.close()
    browser.close()
