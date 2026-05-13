"""Hybrid approach: Playwright solves JS challenge, curl_cffi does fast API calls.

1. Playwright navigates to sofascore.com → JS challenge sets cookies
2. Extract cookies from Playwright browser context  
3. Inject into curl_cffi session
4. curl_cffi makes fast API calls with valid cookies
"""
import sys, time, random, json
sys.path.insert(0, "src")

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from curl_cffi import requests as cffi_requests

PROFILES = ["chrome120", "chrome124"]
HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}
BASE = "https://www.sofascore.com/api/v1"

print("=" * 60)
print("PHASE 1: Playwright — solve JS challenge, extract cookies")
print("=" * 60)

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
    Stealth().apply_stealth_sync(page)
    
    # Navigate to sofascore — browser solves JS challenge
    print("Navigating to sofascore.com...")
    page.goto("https://www.sofascore.com/football/2026-05-13", wait_until="domcontentloaded", timeout=25000)
    
    # Wait for JS challenge to complete
    time.sleep(4)
    
    # Check if challenge was solved
    content = page.content()
    if "Just a moment" in content:
        print("  Cloudflare challenge detected, waiting...")
        time.sleep(8)
    
    # Extract ALL cookies from the browser
    cookies = context.cookies()
    print(f"  Extracted {len(cookies)} cookies:")
    for c in cookies:
        print(f"    {c['name']}: {c['value'][:40]}... (domain: {c['domain']})")
    
    # Also extract the user-agent the page is using
    ua = page.evaluate("navigator.userAgent")
    print(f"  User-Agent: {ua[:80]}")
    
    context.close()
    browser.close()

print(f"\n{'=' * 60}")
print("PHASE 2: curl_cffi — API calls with stolen cookies")
print("=" * 60)

# Create curl_cffi session with the same user-agent
session = cffi_requests.Session(impersonate="chrome120")

# Inject cookies
for cookie in cookies:
    session.cookies.set(
        cookie["name"],
        cookie["value"],
        domain=cookie.get("domain", ".sofascore.com"),
    )

print(f"Session cookies: {list(session.cookies.keys())}")

# Test API call
url = f"{BASE}/sport/football/scheduled-events/2026-05-13"
print(f"\nGET {url}")
resp = session.get(url, headers=HEADERS, timeout=30)
print(f"  Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    events = data.get("events", [])
    print(f"  SUCCESS! Football events: {len(events)}")
    
    if events:
        ev = events[0]
        print(f"  First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}")
        eid = ev["id"]
        
        # Test event-specific endpoints
        print(f"\n  Event {eid} endpoints:")
        for ep in ["pregame-form", "h2h", "odds/1/all"]:
            resp_ev = session.get(f"{BASE}/event/{eid}/{ep}", headers=HEADERS, timeout=30)
            status = resp_ev.status_code
            if status == 200:
                keys = list(resp_ev.json().keys())[:6]
                print(f"    {ep}: 200 — {keys}")
            else:
                print(f"    {ep}: HTTP {status}")
            time.sleep(0.3)
    
    # Test other sports
    print("\n  Other sports:")
    for sport in ["basketball", "tennis", "ice-hockey", "volleyball"]:
        resp_s = session.get(f"{BASE}/sport/{sport}/scheduled-events/2026-05-13", headers=HEADERS, timeout=30)
        if resp_s.status_code == 200:
            count = len(resp_s.json().get("events", []))
            print(f"    {sport}: {count} events")
        else:
            print(f"    {sport}: HTTP {resp_s.status_code}")
        time.sleep(0.3)
else:
    print(f"  FAILED: {resp.text[:300]}")
    # Try with the exact UA from the browser
    print(f"\n  Retrying with exact browser UA...")
    HEADERS["User-Agent"] = ua
    resp2 = session.get(url, headers=HEADERS, timeout=30)
    print(f"  Status: {resp2.status_code}")
    if resp2.status_code == 200:
        print(f"  Events: {len(resp2.json().get('events', []))}")
    else:
        print(f"  Body: {resp2.text[:300]}")

session.close()
