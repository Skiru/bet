"""Quick: find finished match and extract stats."""
import sys
import traceback
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
sys.stdout.reconfigure(line_buffering=True)
print("START", flush=True)

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

try:
    p = sync_playwright().start()
    print("Playwright started", flush=True)
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    print("Browser launched", flush=True)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/136.0.0.0",
        viewport={"width": 1920, "height": 1080},
        locale="en-GB",
    )
    page = ctx.new_page()
    Stealth().apply_stealth_sync(page)
    print("Page created + stealth applied", flush=True)

    # Load results page (finished matches)
    page.goto("https://www.flashscore.com/football/results/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    print("Results page loaded", flush=True)
    
    try:
        c = page.locator("#onetrust-accept-btn-handler")
        if c.is_visible(timeout=2000):
            c.click()
    except Exception:
        pass
    page.wait_for_timeout(1000)

    # Get first 5 finished matches
    ids = page.evaluate("""() => {
        const ms = document.querySelectorAll(".event__match[id^='g_1_']");
        return Array.from(ms).slice(0, 5).map(m => ({
            id: m.id,
            text: m.innerText.substring(0, 120)
        }));
    }""")
    print(f"Found {len(ids)} matches", flush=True)
    for x in ids:
        print(f"  Match: {x}", flush=True)

    if ids:
        event_id = ids[0]["id"].replace("g_1_", "")
        print(f"\nTesting stats for event: {event_id}", flush=True)

        stats_url = f"https://www.flashscore.com/match/{event_id}/#/match-summary/match-statistics/0"
        page.goto(stats_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        print("Stats page loaded", flush=True)

        detail_text = page.evaluate("""() => {
            const detail = document.querySelector('#detail');
            return detail ? detail.innerText : 'NO DETAIL';
        }""")
        
        print(f"Detail text ({len(detail_text)} chars):", flush=True)
        print(detail_text[:3000], flush=True)

    browser.close()
    p.stop()
    print("DONE", flush=True)
except Exception as e:
    print(f"ERROR: {e}", flush=True)
    traceback.print_exc()
