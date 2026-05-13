"""Scrape rendered DOM from Sofascore — extract events from actual page elements.

The page renders events with team names, times, leagues — all in the DOM.
Playwright executes JS → events appear → we scrape the DOM.
"""
import sys, time, json, re
sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

SPORTS = ["football", "basketball", "tennis", "ice-hockey", "volleyball"]
DATE = "2026-05-13"
ALL_EVENTS = {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--disable-blink-features=AutomationControlled',
        '--no-sandbox',
    ])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    
    for sport in SPORTS:
        url = f"https://www.sofascore.com/{sport}/{DATE}"
        print(f"\n{'='*60}")
        print(f"SPORT: {sport} — {url}")
        print(f"{'='*60}")
        
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        time.sleep(6)  # Wait for client-side render
        
        # Scroll down to load more events
        for _ in range(3):
            page.evaluate("window.scrollBy(0, 2000)")
            time.sleep(1)
        
        # Extract ALL links that point to match pages
        events = page.evaluate("""
            () => {
                const results = [];
                // Find all links to match pages
                const links = document.querySelectorAll('a[href*="/match/"]');
                const seen = new Set();
                
                for (const link of links) {
                    const href = link.getAttribute('href') || '';
                    // Extract event ID from href
                    const idMatch = href.match(/#id:(\\d+)/);
                    if (!idMatch) continue;
                    
                    const eventId = idMatch[1];
                    if (seen.has(eventId)) continue;
                    seen.add(eventId);
                    
                    // Try to extract team names from the link or parent
                    const text = link.textContent?.trim() || '';
                    const slug = href.split('/match/')[1]?.split('#')[0] || '';
                    
                    results.push({
                        eventId: eventId,
                        href: href,
                        slug: slug,
                        text: text.substring(0, 200),
                    });
                }
                return results;
            }
        """)
        
        print(f"  Found {len(events)} events via match links")
        
        if not events:
            # Try alternative: look for event containers
            print("  Trying alternative selectors...")
            events = page.evaluate("""
                () => {
                    const results = [];
                    // Look for any element with data-event-id or similar
                    const els = document.querySelectorAll('[class*="event"], [class*="match"], [data-id]');
                    for (const el of [...els].slice(0, 5)) {
                        results.push({
                            tag: el.tagName,
                            classes: el.className?.substring(0, 100),
                            text: el.textContent?.trim().substring(0, 200),
                            childCount: el.children.length,
                        });
                    }
                    return results;
                }
            """)
            print(f"  Alternative found {len(events)} elements")
            for ev in events[:3]:
                print(f"    {ev}")
        else:
            for ev in events[:10]:
                print(f"  ID={ev['eventId']} slug={ev['slug'][:60]} text={ev['text'][:60]}")
        
        ALL_EVENTS[sport] = events
        time.sleep(2)  # Rate limit between sports
    
    # Also try to find the actual event data from page state (React fiber/store)
    print(f"\n{'='*60}")
    print("Checking React state for event data...")
    react_data = page.evaluate("""
        () => {
            // Try Next.js router cache
            if (window.__NEXT_DATA__?.props?.pageProps?.initialProps) {
                return {source: '__NEXT_DATA__', data: Object.keys(window.__NEXT_DATA__.props.pageProps.initialProps)};
            }
            // Try React Query cache
            if (window.__REACT_QUERY_STATE__) {
                return {source: 'react-query', keys: Object.keys(window.__REACT_QUERY_STATE__)};
            }
            // Check for SWR or other state
            const stores = [];
            for (const key of Object.keys(window)) {
                if (key.startsWith('__') && key !== '__NEXT_DATA__') {
                    stores.push(key);
                }
            }
            return {source: 'window globals', keys: stores.slice(0, 20)};
        }
    """)
    print(f"  {react_data}")
    
    context.close()
    browser.close()

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
total = 0
for sport, events in ALL_EVENTS.items():
    count = len(events)
    total += count
    print(f"  {sport}: {count} events")
print(f"  TOTAL: {total} events with Sofascore IDs")
