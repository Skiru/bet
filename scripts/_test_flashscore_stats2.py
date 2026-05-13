"""Quick test: extract stats from Man City vs Crystal Palace finished match."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--disable-blink-features=AutomationControlled", "--no-sandbox",
    ])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1920, "height": 1080},
        locale="en-GB",
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)

    event_id = "xfi4Ju8N"  # Man City vs Crystal Palace
    stats_url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
    logger.info(f"Loading stats: {stats_url}")
    page.goto(stats_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(6000)
    
    # Cookie consent
    try:
        consent = page.locator("#onetrust-accept-btn-handler")
        if consent.is_visible(timeout=3000):
            consent.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # Get innerText from the #detail section — this will have all visible text
    detail_text = page.evaluate("""() => {
        const detail = document.querySelector('#detail');
        return detail ? detail.innerText : 'NO #detail';
    }""")
    logger.info(f"#detail innerText ({len(detail_text)} chars):")
    logger.info(detail_text[:2000])
    
    # Try to find data-testid elements with stat values
    testid_data = page.evaluate("""() => {
        const result = [];
        const els = document.querySelectorAll('[data-testid]');
        for (const el of els) {
            const testid = el.getAttribute('data-testid');
            if (testid && (testid.includes('stat') || testid.includes('wcl'))) {
                result.push({
                    testid: testid,
                    text: (el.innerText || el.textContent || '').trim().substring(0, 100),
                    tag: el.tagName,
                    children: el.children.length
                });
            }
        }
        return result;
    }""")
    
    logger.info(f"\ndata-testid elements: {len(testid_data)}")
    for item in testid_data[:25]:
        logger.info(f"  testid={item['testid']} tag={item['tag']} children={item['children']} text='{item['text'][:80]}'")

    # Try direct wcl approach
    wcl_data = page.evaluate("""() => {
        const result = [];
        // Any element with wcl- in class
        const els = document.querySelectorAll('[class*="wcl-stat"], [class*="wcl-category"]');
        for (const el of els) {
            result.push({
                cls: (el.getAttribute('class') || '').substring(0, 80),
                text: (el.innerText || '').trim().substring(0, 100),
                tag: el.tagName,
            });
        }
        return result;
    }""")
    logger.info(f"\nWCL elements: {len(wcl_data)}")
    for item in wcl_data[:20]:
        logger.info(f"  .{item['cls'][:60]} → '{item['text'][:60]}'")

    browser.close()
