"""Test Sofascore with new headless mode + wait for actual event elements.

New headless mode (--headless=new) uses the same engine as headed browser,
making it much harder to detect as headless.
"""
import sys, time, json
sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

with sync_playwright() as p:
    # Try "new headless" mode via channel=chrome
    browser = p.chromium.launch(
        headless=True,
        args=[
            '--headless=new',
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
            '--disable-dev-shm-usage',
        ],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="Europe/Warsaw",
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    
    # Intercept API responses
    api_responses = []
    def handle_response(response):
        url = response.url
        if "sofascore.com/api" in url and response.status == 200:
            api_responses.append({
                "url": url,
                "status": response.status,
            })
    
    page.on("response", handle_response)
    
    print("Navigating to Sofascore football page (new headless)...")
    page.goto("https://www.sofascore.com/football/2026-05-13", wait_until="networkidle", timeout=30000)
    
    print(f"API responses captured during load: {len(api_responses)}")
    for r in api_responses:
        if "/image" not in r["url"]:
            print(f"  {r['url'][:100]}")
    
    # Check if the challenge page is shown
    title = page.title()
    print(f"Page title: {title}")
    
    # Wait a bit for lazy-loaded content
    time.sleep(5)
    
    # Scroll down
    for _ in range(5):
        page.evaluate("window.scrollBy(0, 1000)")
        time.sleep(1)
    
    print(f"\nTotal API responses after scrolling: {len(api_responses)}")
    non_image = [r for r in api_responses if "/image" not in r["url"]]
    print(f"Non-image API responses: {len(non_image)}")
    for r in non_image:
        print(f"  [{r['status']}] {r['url'][:120]}")
    
    # Count actual match/event elements in the DOM
    event_count = page.evaluate("""
        () => {
            // Look for match links specifically for today's events
            const links = document.querySelectorAll('a[href*="/match/"]');
            const unique = new Set();
            const events = [];
            for (const l of links) {
                const href = l.getAttribute('href');
                const m = href?.match(/#id:(\\d+)/);
                if (m && !unique.has(m[1])) {
                    unique.add(m[1]);
                    events.push({
                        id: m[1],
                        text: l.textContent?.trim().substring(0, 100),
                        sport: href.split('/')[1],
                    });
                }
            }
            return events;
        }
    """)
    
    print(f"\nUnique events in DOM: {len(event_count)}")
    
    # Group by sport
    sports = {}
    for ev in event_count:
        s = ev.get("sport", "unknown")
        if s not in sports:
            sports[s] = []
        sports[s].append(ev)
    
    for sport, evts in sports.items():
        print(f"\n  {sport}: {len(evts)} events")
        for e in evts[:5]:
            print(f"    ID={e['id']} {e['text'][:60]}")
    
    # Check what's actually visible on the page
    print("\n\nPage content check:")
    visible_text = page.evaluate("""
        () => {
            // Get the main content area text
            const main = document.querySelector('main') || document.body;
            return main.innerText.substring(0, 2000);
        }
    """)
    print(visible_text[:1000])
    
    context.close()
    browser.close()
