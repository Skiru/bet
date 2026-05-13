"""Test curl_cffi with correct Sofascore API domain."""
from curl_cffi import requests as r
import random, time

PROFILES = ["chrome", "chrome110", "chrome120", "chrome124"]
HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}
BASE = "https://www.sofascore.com/api/v1"

profile = random.choice(PROFILES)
print(f"Profile: {profile}\n")

# Test 1: Football scheduled events
url = f"{BASE}/sport/football/scheduled-events/2026-05-13"
print(f"GET {url}")
resp = r.get(url, headers=HEADERS, impersonate=profile, timeout=30)
print(f"  Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    events = data.get("events", [])
    print(f"  Football events: {len(events)}")
    if events:
        ev = events[0]
        print(f"  First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')} ({ev.get('tournament',{}).get('name')})")
        event_id = ev["id"]
else:
    print(f"  Body: {resp.text[:300]}")
    event_id = None

# Test 2: Other sports
print()
for sport in ["basketball", "tennis", "ice-hockey", "volleyball"]:
    url2 = f"{BASE}/sport/{sport}/scheduled-events/2026-05-13"
    resp2 = r.get(url2, headers=HEADERS, impersonate=random.choice(PROFILES), timeout=30)
    if resp2.status_code == 200:
        count = len(resp2.json().get("events", []))
        print(f"  {sport}: {count} events")
    else:
        print(f"  {sport}: HTTP {resp2.status_code}")
    time.sleep(0.3)

# Test 3: Event-specific endpoints
if event_id:
    print(f"\nEvent {event_id} endpoints:")
    for endpoint in ["pregame-form", "h2h", "odds/1/all", "lineups"]:
        url3 = f"{BASE}/event/{event_id}/{endpoint}"
        resp3 = r.get(url3, headers=HEADERS, impersonate=random.choice(PROFILES), timeout=30)
        if resp3.status_code == 200:
            data3 = resp3.json()
            print(f"  {endpoint}: 200 OK — keys: {list(data3.keys())[:6]}")
        else:
            print(f"  {endpoint}: HTTP {resp3.status_code}")
        time.sleep(0.3)
