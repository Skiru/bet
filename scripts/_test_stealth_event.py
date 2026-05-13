"""Test Sofascore stealth on individual EVENT pages.
Schedule pages don't embed events, but event pages might embed stats/form/H2H.
"""
import logging
import json
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
sys.path.insert(0, "src")

from bet.api_clients.sofascore import SofascoreClient

client = SofascoreClient()

# First get a Sofascore event ID via ESPN → we need to search sofascore for a known match
# Use a direct Sofascore event page test

# Test 1: Try to get form data for a known event via the API (will fallback to stealth)
print("=" * 60)
print("TEST 1: get_pregame_form for football event")
print("=" * 60)

# We need a real event ID — let's find one from sofascore.com
# Try a Champions League match or something popular
# For now, test with event ID 13000000 (may not exist)
# Actually let's search sofascore for today's events by navigating to the page
# and extracting event links from the DOM

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

print("\nSearching for event IDs on sofascore.com/football/2026-05-13...")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
    )
    page = context.new_page()
    Stealth().apply_stealth_sync(page)
    
    page.goto("https://www.sofascore.com/football/2026-05-13", wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(6000)
    
    # Extract all event links from the page
    links = page.evaluate("""() => {
        const anchors = document.querySelectorAll('a[href*="/football/"]');
        const eventLinks = [];
        for (const a of anchors) {
            const href = a.getAttribute('href');
            // Event URLs look like: /{team1}-{team2}/{event-slug}/XYZ
            // or /match/{id}
            if (href && /\\/[a-z-]+-[a-z-]+\\/[a-z]+\\/\\d+$/.test(href)) {
                eventLinks.push(href);
            }
        }
        return [...new Set(eventLinks)].slice(0, 10);
    }""")
    
    print(f"Found {len(links)} event links:")
    for link in links:
        print(f"  {link}")
    
    # Also try extracting from __NEXT_DATA__
    next_data = page.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        return el ? JSON.parse(el.textContent) : null;
    }""")
    
    if next_data:
        # Look for event IDs in the data
        data_str = json.dumps(next_data)
        print(f"\n__NEXT_DATA__ size: {len(data_str)} bytes")
        
        # Check initialProps
        initial_props = next_data.get("props", {}).get("pageProps", {}).get("initialProps", {})
        if initial_props:
            print(f"initialProps keys: {list(initial_props.keys())[:10]}")
            # Check for events in initialProps
            for key, val in initial_props.items():
                if isinstance(val, list) and len(val) > 0:
                    print(f"  {key}: list of {len(val)}, first type: {type(val[0]).__name__}")
                    if isinstance(val[0], dict):
                        print(f"    keys: {list(val[0].keys())[:8]}")
                elif isinstance(val, dict):
                    print(f"  {key}: dict keys: {list(val.keys())[:8]}")
    
    context.close()
    browser.close()

# If we found event links, test one
if links:
    # Extract event ID from link
    event_id = links[0].rstrip("/").split("/")[-1]
    print(f"\n{'=' * 60}")
    print(f"TEST 2: Fetching event page for ID {event_id}")
    print(f"{'=' * 60}")
    
    # Navigate to event page and check __NEXT_DATA__
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        
        url = f"https://www.sofascore.com{links[0]}"
        print(f"Navigating to {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(4000)
        
        next_data = page.evaluate("""() => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? JSON.parse(el.textContent) : null;
        }""")
        
        if next_data:
            page_props = next_data.get("props", {}).get("pageProps", {})
            print(f"pageProps keys: {list(page_props.keys())[:10]}")
            
            initial_props = page_props.get("initialProps", {})
            print(f"initialProps keys: {list(initial_props.keys())[:15]}")
            
            # Check for event data
            event_data = initial_props.get("event", initial_props.get("match", {}))
            if event_data:
                print(f"\nEvent data found! Keys: {list(event_data.keys())[:15]}")
                home = event_data.get("homeTeam", {}).get("name", "?")
                away = event_data.get("awayTeam", {}).get("name", "?")
                print(f"Match: {home} vs {away}")
            
            # Check for form data
            form = initial_props.get("form", initial_props.get("pregameForm", {}))
            if form:
                print(f"\nForm data found! Keys: {list(form.keys())[:10]}")
            
            # Check for H2H
            h2h = initial_props.get("h2h", initial_props.get("headToHead", {}))
            if h2h:
                print(f"\nH2H data found! Keys: {list(h2h.keys())[:10]}")
            
            # Check for odds
            odds = initial_props.get("odds", initial_props.get("markets", {}))
            if odds:
                print(f"\nOdds data found! Keys: {list(odds.keys()) if isinstance(odds, dict) else 'list'}")
            
            # Dump all top-level initialProps keys with types
            print(f"\n--- All initialProps ---")
            for k, v in initial_props.items():
                if isinstance(v, dict):
                    print(f"  {k}: dict({len(v)} keys)")
                elif isinstance(v, list):
                    print(f"  {k}: list({len(v)} items)")
                else:
                    print(f"  {k}: {type(v).__name__} = {str(v)[:80]}")
        else:
            print("No __NEXT_DATA__ found on event page")
        
        context.close()
        browser.close()
else:
    print("\nNo event links found — cannot test event page")
