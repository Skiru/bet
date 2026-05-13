"""Probe Sofascore WAF bypass approaches.

Tests 4 approaches:
1. www.sofascore.com/api/v1 (same-domain API path)
2. Playwright DOM scraping (rendered events, not API interception)
3. Playwright cookie → requests session transfer
4. cloudscraper package
"""
import sys, time, json, re
sys.path.insert(0, "src")

DATE = "2026-05-13"

# ── Approach 1: Same-domain API via requests ──
print("=" * 60)
print("APPROACH 1: www.sofascore.com/api/v1/ (same-domain)")
print("=" * 60)
import requests

for base in [
    f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}",
    f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}",
]:
    try:
        r = requests.get(base, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": "https://www.sofascore.com/",
        }, timeout=15)
        print(f"  {base.split('//')[1][:50]}... → HTTP {r.status_code}")
        if r.status_code == 200:
            events = r.json().get("events", [])
            print(f"    SUCCESS! {len(events)} events")
    except Exception as e:
        print(f"  {base.split('//')[1][:50]}... → ERROR: {e}")

# ── Approach 2: Playwright DOM scraping ──
print(f"\n{'=' * 60}")
print("APPROACH 2: Playwright DOM scraping (rendered page)")
print("=" * 60)

from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--disable-blink-features=AutomationControlled',
        '--disable-infobars',
        '--no-sandbox',
    ])
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-US",
    )
    page = context.new_page()
    if Stealth:
        Stealth().apply_stealth_sync(page)
    
    # Track API responses
    api_responses = []
    def on_response(response):
        url = response.url
        if "api.sofascore.com" in url and response.status == 200:
            try:
                data = response.json()
                api_responses.append({"url": url, "data": data})
            except Exception:
                pass
    page.on("response", on_response)
    
    print(f"  Navigating to sofascore.com/football/{DATE}...")
    page.goto(f"https://www.sofascore.com/football/{DATE}", wait_until="domcontentloaded", timeout=30000)
    
    # Wait for full render
    time.sleep(8)
    
    # Check Cloudflare
    content = page.content()
    if "Just a moment" in content:
        print("  CF challenge detected, waiting 10s...")
        time.sleep(10)
        content = page.content()
    
    print(f"  Page size: {len(content)} bytes")
    print(f"  API responses intercepted: {len(api_responses)}")
    for r in api_responses[:5]:
        print(f"    {r['url'][:80]}")
    
    # ── 2a: Try scraping event elements from DOM ──
    print("\n  2a: DOM event elements...")
    events_js = page.evaluate("""() => {
        // Try various selectors that Sofascore uses
        const selectors = [
            '[class*="event"]',
            '[class*="match"]', 
            '[data-testid*="event"]',
            'a[href*="/match/"]',
            '[class*="EventCell"]',
            '[class*="eventCell"]',
        ];
        const results = {};
        for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            results[sel] = els.length;
        }
        
        // Get all links containing /match/
        const matchLinks = [];
        document.querySelectorAll('a[href*="/match/"]').forEach(a => {
            const href = a.getAttribute('href');
            const text = a.innerText.trim().substring(0, 80);
            matchLinks.push({href, text});
        });
        results._matchLinks = matchLinks;
        
        // Also get any elements with event IDs
        const idElements = [];
        document.querySelectorAll('[id*="event"], [data-id]').forEach(el => {
            idElements.push({id: el.id, dataId: el.dataset.id, tag: el.tagName});
        });
        results._idElements = idElements;
        
        return results;
    }""")
    
    for sel, count in events_js.items():
        if not sel.startswith("_") and count > 0:
            print(f"    {sel}: {count} elements")
    
    match_links = events_js.get("_matchLinks", [])
    print(f"    Match links found: {len(match_links)}")
    for link in match_links[:5]:
        print(f"      {link['href'][:60]} — {link['text'][:40]}")
    
    id_elements = events_js.get("_idElements", [])
    if id_elements:
        print(f"    Elements with event IDs: {len(id_elements)}")
        for el in id_elements[:5]:
            print(f"      {el}")
    
    # ── 2b: Extract event IDs from href patterns ──
    print("\n  2b: Extract Sofascore event IDs from match links...")
    sofa_ids = set()
    for link in match_links:
        href = link.get("href", "")
        # Pattern: /football/match/team1-team2/SLUG#id:12345
        m = re.search(r'#id:(\d+)', href)
        if m:
            sofa_ids.add(m.group(1))
        # Also try /match/slug/ID pattern
        m2 = re.search(r'/match/[^/]+/[^/]+/(\d+)', href)
        if m2:
            sofa_ids.add(m2.group(1))
    
    print(f"    Found {len(sofa_ids)} unique Sofascore event IDs")
    if sofa_ids:
        sample = list(sofa_ids)[:10]
        print(f"    Sample: {sample}")
    
    # ── 2c: Extract __NEXT_DATA__ and check initialState ──
    print("\n  2c: __NEXT_DATA__ deep probe...")
    next_data = page.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        return el ? JSON.parse(el.textContent) : null;
    }""")
    
    if next_data:
        # Check initialState for events
        initial_state = next_data.get("props", {}).get("pageProps", {}).get("initialState", {})
        print(f"    initialState keys: {list(initial_state.keys())[:10]}")
        
        # Check if there's an events store
        for key in initial_state:
            val = initial_state[key]
            if isinstance(val, dict):
                subkeys = list(val.keys())[:5]
                size = len(json.dumps(val))
                print(f"      {key}: dict ({len(val)} keys, {size} bytes) — {subkeys}")
            elif isinstance(val, list):
                print(f"      {key}: list ({len(val)} items)")
    
    # ── Approach 3: Cookie transfer ──
    print(f"\n{'=' * 60}")
    print("APPROACH 3: Cookie transfer (Playwright → requests)")
    print("=" * 60)
    
    cookies = context.cookies()
    print(f"  Extracted {len(cookies)} cookies")
    for c in cookies:
        print(f"    {c['name']}: {c['value'][:30]}... (domain: {c['domain']})")
    
    # Create requests session with cookies
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.sofascore.com/",
    })
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain", ".sofascore.com"))
    
    # Try API with cookies — both domains
    for base_url in [
        f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}",
        f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}",
    ]:
        try:
            r = s.get(base_url, timeout=15)
            domain = base_url.split("//")[1].split("/")[0]
            print(f"  {domain}: HTTP {r.status_code}")
            if r.status_code == 200:
                events = r.json().get("events", [])
                print(f"    SUCCESS! {len(events)} events")
        except Exception as e:
            print(f"  ERROR: {e}")
    
    # If we have event IDs from DOM, try fetching event details
    if sofa_ids:
        print(f"\n  Testing event endpoints with DOM-extracted IDs...")
        test_id = list(sofa_ids)[0]
        for ep in ["pregame-form", "h2h", "statistics"]:
            # Try via Playwright page navigation (new page)
            try:
                event_page = context.new_page()
                if Stealth:
                    Stealth().apply_stealth_sync(event_page)
                event_url = f"https://www.sofascore.com/api/v1/event/{test_id}/{ep}"
                event_page.goto(event_url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                body = event_page.evaluate("document.body.innerText")
                event_page.close()
                if body and len(body) > 10:
                    try:
                        data = json.loads(body)
                        print(f"    event/{test_id}/{ep}: OK — keys: {list(data.keys())[:5]}")
                    except:
                        print(f"    event/{test_id}/{ep}: non-JSON ({len(body)} bytes)")
                else:
                    print(f"    event/{test_id}/{ep}: empty/blocked")
            except Exception as e:
                print(f"    event/{test_id}/{ep}: ERROR — {e}")
    
    context.close()
    browser.close()

# ── Approach 4: cloudscraper ──
print(f"\n{'=' * 60}")
print("APPROACH 4: cloudscraper")
print("=" * 60)
try:
    import cloudscraper
    scraper = cloudscraper.create_scraper()
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}"
    r = scraper.get(url)
    print(f"  api.sofascore.com: HTTP {r.status_code}")
    if r.status_code == 200:
        events = r.json().get("events", [])
        print(f"    SUCCESS! {len(events)} events")
    
    url2 = f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{DATE}"
    r2 = scraper.get(url2)
    print(f"  www.sofascore.com: HTTP {r2.status_code}")
    if r2.status_code == 200:
        events = r2.json().get("events", [])
        print(f"    SUCCESS! {len(events)} events")
except ImportError:
    print("  cloudscraper not installed. Install with: pip install cloudscraper")
except Exception as e:
    print(f"  ERROR: {e}")

print(f"\n{'=' * 60}")
print("SUMMARY")
print("=" * 60)
