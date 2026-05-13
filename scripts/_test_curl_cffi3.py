"""Test curl_cffi with session cookie warming.

Strategy: visit sofascore.com first to get Cloudflare/DataDome cookies,
then use the same session for API calls.
"""
from curl_cffi import requests as r
import time

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}
BASE = "https://www.sofascore.com/api/v1"

# Use a persistent session (keeps cookies across requests)
session = r.Session(impersonate="chrome120")

# Step 1: Visit the main page to get cookies
print("Step 1: Warming cookies via sofascore.com...")
resp_warm = session.get("https://www.sofascore.com", headers=HEADERS, timeout=30)
print(f"  Status: {resp_warm.status_code}, Size: {len(resp_warm.text)} bytes")
print(f"  Cookies: {dict(session.cookies)}")
time.sleep(1)

# Step 2: Visit a sport page to get more cookies
print("\nStep 2: Visit football page...")
resp_sport = session.get("https://www.sofascore.com/football/2026-05-13", headers=HEADERS, timeout=30)
print(f"  Status: {resp_sport.status_code}, Size: {len(resp_sport.text)} bytes")
print(f"  Cookies: {list(session.cookies.keys())}")
time.sleep(1)

# Step 3: Try the API with session cookies
print("\nStep 3: API call with cookies...")
url = f"{BASE}/sport/football/scheduled-events/2026-05-13"
resp_api = session.get(url, headers=HEADERS, timeout=30)
print(f"  Status: {resp_api.status_code}")

if resp_api.status_code == 200:
    data = resp_api.json()
    events = data.get("events", [])
    print(f"  SUCCESS! Football events: {len(events)}")
    if events:
        ev = events[0]
        print(f"  First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}")
        
    # Test event-specific endpoints
    if events:
        eid = events[0]["id"]
        print(f"\nStep 4: Event {eid} endpoints...")
        for ep in ["pregame-form", "h2h", "odds/1/all"]:
            resp_ev = session.get(f"{BASE}/event/{eid}/{ep}", headers=HEADERS, timeout=30)
            if resp_ev.status_code == 200:
                keys = list(resp_ev.json().keys())[:6]
                print(f"  {ep}: 200 OK — {keys}")
            else:
                print(f"  {ep}: HTTP {resp_ev.status_code}")
            time.sleep(0.5)
        
    # Test other sports
    print("\nStep 5: Other sports...")
    for sport in ["basketball", "tennis", "ice-hockey", "volleyball"]:
        resp_s = session.get(f"{BASE}/sport/{sport}/scheduled-events/2026-05-13", headers=HEADERS, timeout=30)
        if resp_s.status_code == 200:
            count = len(resp_s.json().get("events", []))
            print(f"  {sport}: {count} events")
        else:
            print(f"  {sport}: HTTP {resp_s.status_code}")
        time.sleep(0.5)
else:
    print(f"  FAILED: {resp_api.text[:300]}")
    
    # Try with extra headers mimicking the browser's XHR
    print("\nStep 3b: Retry with XHR headers...")
    xhr_headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.sofascore.com/football/2026-05-13",
        "Origin": "https://www.sofascore.com",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    resp_api2 = session.get(url, headers=xhr_headers, timeout=30)
    print(f"  Status: {resp_api2.status_code}")
    if resp_api2.status_code == 200:
        events2 = resp_api2.json().get("events", [])
        print(f"  SUCCESS! Events: {len(events2)}")
    else:
        print(f"  Body: {resp_api2.text[:300]}")

session.close()
