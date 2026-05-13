"""Extract __NEXT_DATA__ from Sofascore page — this is where SSR data lives."""
import sys, time, json
sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

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
    
    print("Navigating to football page...")
    page.goto("https://www.sofascore.com/football/2026-05-13", wait_until="domcontentloaded", timeout=25000)
    time.sleep(5)  # Wait for full render
    
    # Extract __NEXT_DATA__
    print("\nExtracting __NEXT_DATA__...")
    next_data = page.evaluate("""
        () => {
            const el = document.getElementById('__NEXT_DATA__');
            return el ? el.textContent : null;
        }
    """)
    
    if next_data:
        data = json.loads(next_data)
        print(f"__NEXT_DATA__ keys: {list(data.keys())}")
        
        # Explore the structure
        if "props" in data:
            props = data["props"]
            print(f"  props keys: {list(props.keys())}")
            if "pageProps" in props:
                pp = props["pageProps"]
                print(f"  pageProps keys: {list(pp.keys())}")
                
                # Look for events data
                for key in pp:
                    val = pp[key]
                    if isinstance(val, dict):
                        print(f"    {key}: dict with keys {list(val.keys())[:10]}")
                        if "events" in val:
                            events = val["events"]
                            print(f"      FOUND EVENTS! Count: {len(events)}")
                            if events:
                                ev = events[0]
                                print(f"      First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}")
                                print(f"      Event keys: {list(ev.keys())}")
                    elif isinstance(val, list):
                        print(f"    {key}: list with {len(val)} items")
                        if len(val) > 0 and isinstance(val[0], dict):
                            print(f"      First item keys: {list(val[0].keys())[:10]}")
                    elif isinstance(val, str) and len(val) > 100:
                        print(f"    {key}: string ({len(val)} chars)")
                    else:
                        print(f"    {key}: {type(val).__name__} = {str(val)[:80]}")
        
        # Save full structure for analysis
        with open("betting/data/_next_data_dump.json", "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to betting/data/_next_data_dump.json ({len(next_data)} bytes)")
    else:
        print("No __NEXT_DATA__ found!")
        
        # Try alternative: React state or window variables
        print("\nTrying window.__NEXT_DATA__...")
        win_data = page.evaluate("() => window.__NEXT_DATA__ ? JSON.stringify(Object.keys(window.__NEXT_DATA__)) : 'none'")
        print(f"  Result: {win_data}")
        
        # Check if there's event data in other global vars
        print("\nChecking window.__next_f...")
        has_next_f = page.evaluate("() => typeof window.__next_f !== 'undefined'")
        print(f"  window.__next_f exists: {has_next_f}")
        
        if has_next_f:
            next_f_data = page.evaluate("""
                () => {
                    try {
                        return window.__next_f.map(item => {
                            if (Array.isArray(item)) return item.map(x => typeof x === 'string' ? x.substring(0, 200) : typeof x);
                            return typeof item;
                        });
                    } catch(e) { return e.message; }
                }
            """)
            print(f"  __next_f content sample: {json.dumps(next_f_data, indent=2)[:2000]}")
    
    context.close()
    browser.close()
