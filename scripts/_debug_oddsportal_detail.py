#!/usr/bin/env python3
"""Quick debug: OddsPortal match detail page structure."""
import json
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

try:
    from stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    USER_AGENTS = ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox']

# A real match URL from the listing output
URL = "https://www.oddsportal.com/pl/football/h2h/crystal-palace-AovF1Mia/manchester-city-Wtn9Stg0/#xfi4Ju8N"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
    ctx = browser.new_context(user_agent=random.choice(USER_AGENTS), viewport={"width": 1920, "height": 1080}, locale="en-GB")
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

    print(f"Current URL: {page.url}")
    body = page.inner_text("body")
    print(f"Body length: {len(body)}")

    # Extract detail page structure
    result = page.evaluate("""() => {
        const info = {};
        
        // Match header / participants
        const participants = document.querySelectorAll('[data-testid="event-participants"] a, [class*="participant"] a');
        info.participants = Array.from(participants).slice(0, 10).map(p => ({
            text: p.textContent.trim(),
            href: p.href || '',
        }));
        
        // Odds sections
        const oddsDivs = document.querySelectorAll('[class*="odds"], [data-testid*="odds"]');
        info.oddsDivCount = oddsDivs.length;
        info.oddsSamples = Array.from(oddsDivs).slice(0, 5).map(d => ({
            classes: d.className.substring(0, 200),
            testId: d.getAttribute('data-testid') || '',
            text: d.textContent.trim().substring(0, 300),
        }));
        
        // All data-testid elements on detail page
        const testIds = new Set();
        document.querySelectorAll('[data-testid]').forEach(el => {
            testIds.add(el.getAttribute('data-testid'));
        });
        info.allTestIds = Array.from(testIds).sort();
        
        // Market tabs
        const tabs = document.querySelectorAll('ul[class*="tab"] li, div[class*="tab"] a, [role="tab"], [class*="Tab"] button, button[class*="tab"]');
        info.tabCount = tabs.length;
        info.tabs = Array.from(tabs).slice(0, 20).map(t => ({
            text: t.textContent.trim().substring(0, 50),
            classes: t.className.substring(0, 100),
        }));
        
        // Bookmaker rows
        const bookmakerImgs = document.querySelectorAll('img[alt], a[title]');
        const bkNames = [];
        bookmakerImgs.forEach(img => {
            const alt = img.alt || img.title || '';
            if (alt && !bkNames.includes(alt) && alt.length < 50) {
                bkNames.push(alt);
            }
        });
        info.bookmakerNames = bkNames.slice(0, 20);
        
        // Odds values
        const oddsCells = document.querySelectorAll('[class*="odds"] span, [class*="odds"] p, [class*="odds"] div');
        const oddsValues = [];
        oddsCells.forEach(cell => {
            const text = cell.textContent.trim();
            if (/^\d+\.\d{2}$/.test(text)) {
                oddsValues.push(text);
            }
        });
        info.oddsValues = oddsValues.slice(0, 30);
        
        // Broader odds scan - any element with odds-like content
        const allSpans = document.querySelectorAll('p, span');
        const broaderOdds = [];
        allSpans.forEach(el => {
            const t = el.textContent.trim();
            if (/^\d+\.\d{2}$/.test(t) && parseFloat(t) >= 1.01 && parseFloat(t) <= 100) {
                const parent = el.parentElement;
                broaderOdds.push({
                    value: t,
                    parentClass: parent ? parent.className.substring(0, 100) : '',
                    grandparentClass: parent && parent.parentElement ? parent.parentElement.className.substring(0, 100) : '',
                });
            }
        });
        info.broaderOdds = broaderOdds.slice(0, 20);
        
        return info;
    }""")

    print(json.dumps(result, indent=2, ensure_ascii=False))

    ctx.close()
    browser.close()
