"""Test curl_cffi impersonation against Sofascore API.

Two key findings from tunjayoff/sofascore_scraper:
1. Use curl_cffi with impersonate="chrome" (TLS fingerprint)
2. Use https://www.sofascore.com/api/v1 (NOT api.sofascore.com)
"""
import sys
sys.path.insert(0, "src")

from curl_cffi import requests as cffi_requests
import random
import json

PROFILES = ["chrome", "chrome110", "chrome120", "chrome124"]
HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.sofascore.com/",
}

# TEST 1: scheduled-events (our main scan endpoint)
print("=" * 60)
print("TEST 1: Scheduled events via www.sofascore.com/api/v1")
print("=" * 60)

profile = random.choice(PROFILES)
url = "https://www.sofascore.com/api/v1/sport/football/scheduled-events/2026-05-13"
print(f"URL: {url}")
print(f"Profile: {profile}")

resp = cffi_requests.get(url, headers=HEADERS, impersonate=profile, timeout=15)
print(f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    events = data.get("events", [])
    print(f"Events: {len(events)}")
    if events:
        ev = events[0]
        home = ev.get("homeTeam", {}).get("name", "?")
        away = ev.get("awayTeam", {}).get("name", "?")
        comp = ev.get("tournament", {}).get("name", "?")
        print(f"First: {home} vs {away} ({comp})")
else:
    print(f"Body: {resp.text[:200]}")

# TEST 2: Also test api.sofascore.com for comparison
print(f"\n{'=' * 60}")
print("TEST 2: Same endpoint via api.sofascore.com (old URL)")
print("=" * 60)

url2 = "https://api.sofascore.com/api/v1/sport/football/scheduled-events/2026-05-13"
resp2 = cffi_requests.get(url2, headers=HEADERS, impersonate=profile, timeout=15)
print(f"Status: {resp2.status_code}")
if resp2.status_code == 200:
    data2 = resp2.json()
    print(f"Events: {len(data2.get('events', []))}")
else:
    print(f"Body: {resp2.text[:200]}")

# TEST 3: Event-specific endpoint (pregame form)
if resp.status_code == 200 and events:
    event_id = events[0].get("id")
    print(f"\n{'=' * 60}")
    print(f"TEST 3: Pregame form for event {event_id}")
    print("=" * 60)
    
    url3 = f"https://www.sofascore.com/api/v1/event/{event_id}/pregame-form"
    resp3 = cffi_requests.get(url3, headers=HEADERS, impersonate=profile, timeout=15)
    print(f"Status: {resp3.status_code}")
    if resp3.status_code == 200:
        form = resp3.json()
        print(f"Keys: {list(form.keys())[:10]}")
    else:
        print(f"Body: {resp3.text[:200]}")

    # TEST 4: H2H
    print(f"\n{'=' * 60}")
    print(f"TEST 4: H2H for event {event_id}")
    print("=" * 60)
    
    url4 = f"https://www.sofascore.com/api/v1/event/{event_id}/h2h"
    resp4 = cffi_requests.get(url4, headers=HEADERS, impersonate=profile, timeout=15)
    print(f"Status: {resp4.status_code}")
    if resp4.status_code == 200:
        h2h = resp4.json()
        print(f"Keys: {list(h2h.keys())[:10]}")

    # TEST 5: Event statistics
    print(f"\n{'=' * 60}")
    print(f"TEST 5: Statistics for event {event_id}")
    print("=" * 60)
    
    url5 = f"https://www.sofascore.com/api/v1/event/{event_id}/statistics"
    resp5 = cffi_requests.get(url5, headers=HEADERS, impersonate=profile, timeout=15)
    print(f"Status: {resp5.status_code}")

    # TEST 6: Event odds
    print(f"\n{'=' * 60}")
    print(f"TEST 6: Odds for event {event_id}")
    print("=" * 60)
    
    url6 = f"https://www.sofascore.com/api/v1/event/{event_id}/odds/1/all"
    resp6 = cffi_requests.get(url6, headers=HEADERS, impersonate=profile, timeout=15)
    print(f"Status: {resp6.status_code}")
    if resp6.status_code == 200:
        odds = resp6.json()
        markets = odds.get("markets", [])
        print(f"Markets: {len(markets)}")

# TEST 7: Other sports
print(f"\n{'=' * 60}")
print("TEST 7: Multiple sports scan")
print("=" * 60)

for sport in ["basketball", "tennis", "ice-hockey", "volleyball"]:
    url7 = f"https://www.sofascore.com/api/v1/sport/{sport}/scheduled-events/2026-05-13"
    resp7 = cffi_requests.get(url7, headers=HEADERS, impersonate=random.choice(PROFILES), timeout=15)
    count = len(resp7.json().get("events", [])) if resp7.status_code == 200 else f"ERR {resp7.status_code}"
    print(f"  {sport}: {count}")
