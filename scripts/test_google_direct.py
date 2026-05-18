"""Test: Direct Google Search for sports stats — NO SerpAPI needed.

Can we just hit Google directly with requests and parse the sports panel?
"""

import json
import re
import sys
from pathlib import Path

import requests

# Mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

query = "PSG vs Paris FC"
url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=en"

print(f"\n{'='*60}")
print(f"Direct Google Search: '{query}'")
print(f"URL: {url}")
print(f"{'='*60}\n")

response = requests.get(url, headers=HEADERS, timeout=15)
print(f"HTTP Status: {response.status_code}")
print(f"Response size: {len(response.text)} bytes")

if response.status_code != 200:
    print(f"BLOCKED! Status: {response.status_code}")
    print(response.text[:500])
    sys.exit(1)

html = response.text

# Save raw HTML for inspection
output_dir = Path(__file__).parent.parent / "betting" / "data" / "stats_cache"
output_dir.mkdir(parents=True, exist_ok=True)
with open(output_dir / "google_direct_test.html", "w") as f:
    f.write(html)
print(f"HTML saved to: {output_dir / 'google_direct_test.html'}")

# Check for CAPTCHA/block
if "captcha" in html.lower() or "unusual traffic" in html.lower():
    print("\n⚠️  CAPTCHA/BLOCK detected!")
    sys.exit(1)

# Look for sports data patterns in HTML
print(f"\n{'='*60}")
print("SEARCHING FOR SPORTS DATA IN HTML...")
print(f"{'='*60}")

# Pattern 1: Score data (often in data attributes or JSON-LD)
scores = re.findall(r'data-score="(\d+)"', html)
if scores:
    print(f"\n✅ Found scores via data-score: {scores}")

# Pattern 2: Team names near score indicators
team_score_pattern = re.findall(r'<div[^>]*>(\d+)</div>[^<]*<[^>]*>([^<]+)</[^>]*>', html[:50000])
if team_score_pattern:
    print(f"\n✅ Found team/score pairs: {team_score_pattern[:5]}")

# Pattern 3: Look for structured data (JSON-LD)
json_ld = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
if json_ld:
    print(f"\n✅ Found {len(json_ld)} JSON-LD blocks")
    for i, block in enumerate(json_ld[:3]):
        try:
            parsed = json.loads(block)
            print(f"  Block {i}: type={parsed.get('@type', 'unknown')}")
            if "SportsEvent" in str(parsed.get("@type", "")):
                print(f"  🎯 SPORTS EVENT FOUND!")
                print(json.dumps(parsed, indent=2)[:1000])
        except json.JSONDecodeError:
            pass

# Pattern 4: Look for match statistics keywords
stat_keywords = ["corners", "shots", "possession", "fouls", "yellow", "cards", "offsides"]
found_stats = []
for kw in stat_keywords:
    if kw.lower() in html.lower():
        found_stats.append(kw)
if found_stats:
    print(f"\n✅ Stats keywords found in HTML: {found_stats}")

# Pattern 5: Look for the sports panel div (imso-ani)
if "imso-ani" in html or "imso_" in html:
    print("\n✅ Google Sports Panel (imso) detected!")
    # Extract content around sports panel
    panel_start = html.find("imso")
    panel_section = html[max(0, panel_start-100):panel_start+2000]
    print(f"  Panel region ({len(panel_section)} chars): ...exists")

# Pattern 6: Look for liveresults/sports data in script tags
sport_scripts = re.findall(r'(var\s+\w+\s*=\s*\{[^}]*(?:score|team|match|sport)[^}]*\})', html[:100000])
if sport_scripts:
    print(f"\n✅ Found {len(sport_scripts)} sport-related JS variables")

# Pattern 7: AF_initDataCallback (Google's internal data format)
af_data = re.findall(r"AF_initDataCallback\(\{[^}]*key:\s*'([^']+)'", html)
if af_data:
    print(f"\n✅ Found AF_initDataCallback keys: {af_data[:10]}")

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"  HTTP Status: {response.status_code} (OK)")
print(f"  Blocked: No")
print(f"  Sports panel: {'Yes' if 'imso' in html else 'No'}")
print(f"  Stats in HTML: {found_stats}")
print(f"  JSON-LD blocks: {len(json_ld)}")
print(f"\n  → Check google_direct_test.html for full analysis")
