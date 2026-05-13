"""Test ALL bypass variants discovered from GitHub repos.

Sources:
- EasySoccerData: impersonate="chrome", api.sofascore.com
- Public-Sofascore-API: impersonate="chrome110", Origin header, api.sofascore.app mirror
- Sportylytics: impersonate="chrome120", X-Requested-With: org.sofascore.results
"""
from curl_cffi import requests
import time

DATE = "2026-05-13"
ENDPOINT = f"/sport/football/scheduled-events/{DATE}"

# Test matrix: (label, base_url, impersonate, extra_headers)
VARIANTS = [
    # Different domains
    ("api.sofascore.app + chrome", "https://api.sofascore.app/api/v1", "chrome", {}),
    ("api.sofascore.app + chrome110", "https://api.sofascore.app/api/v1", "chrome110", {}),
    ("api.sofascore.app + chrome120", "https://api.sofascore.app/api/v1", "chrome120", {}),
    
    # api.sofascore.com with different profiles
    ("api.sofascore.com + chrome (ESD)", "https://api.sofascore.com/api/v1", "chrome", {}),
    ("api.sofascore.com + chrome110 (pseudo-r)", "https://api.sofascore.com/api/v1", "chrome110", {
        "Origin": "https://www.sofascore.com",
        "Referer": "https://www.sofascore.com/",
    }),
    
    # www.sofascore.com with mobile app header (Sportylytics)
    ("www + mobile app header", "https://www.sofascore.com/api/v1", "chrome120", {
        "X-Requested-With": "org.sofascore.results",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.sofascore.com",
        "Referer": "https://www.sofascore.com/",
    }),
    
    # api.sofascore.com with mobile app header
    ("api + mobile app header", "https://api.sofascore.com/api/v1", "chrome120", {
        "X-Requested-With": "org.sofascore.results",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sofascore.com/",
    }),
    
    # safari profile (different TLS fingerprint)
    ("api.sofascore.app + safari", "https://api.sofascore.app/api/v1", "safari15_5", {}),
    
    # Session-based with pre-warm (ESD style)  
    ("session + chrome + warm", "SESSION_WARM", "chrome", {}),
]

print("=" * 70)
print(f"Testing {len(VARIANTS)} bypass variants for Sofascore API")
print("=" * 70)

for label, base, profile, headers in VARIANTS:
    print(f"\n--- {label} ---")
    
    try:
        if base == "SESSION_WARM":
            # Session-based with pre-warm
            session = requests.Session(impersonate=profile)
            # Warm up
            session.get("https://www.sofascore.com/", timeout=15)
            time.sleep(0.5)
            url = f"https://api.sofascore.com/api/v1{ENDPOINT}"
            resp = session.get(url, headers=headers, timeout=15)
            session.close()
        else:
            url = f"{base}{ENDPOINT}"
            resp = requests.get(url, impersonate=profile, headers=headers, timeout=15)
        
        status = resp.status_code
        
        if status == 200:
            try:
                data = resp.json()
                if "error" in data:
                    print(f"  STATUS: {status} — ERROR: {data['error']}")
                elif "events" in data:
                    count = len(data["events"])
                    first = ""
                    if count > 0:
                        ev = data["events"][0]
                        first = f" — First: {ev.get('homeTeam',{}).get('name')} vs {ev.get('awayTeam',{}).get('name')}"
                    print(f"  STATUS: 200 — SUCCESS! {count} events{first}")
                else:
                    print(f"  STATUS: 200 — keys: {list(data.keys())[:5]}")
            except Exception as e:
                print(f"  STATUS: {status} — Not JSON: {resp.text[:100]}")
        else:
            body = resp.text[:150]
            print(f"  STATUS: {status} — {body}")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
    
    time.sleep(0.5)  # Rate limit
