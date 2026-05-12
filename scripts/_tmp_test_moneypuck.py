#!/usr/bin/env python3
"""Test MoneyPuck data URLs to find working CSV/JSON endpoints."""
import requests

URLS = [
    # Known MoneyPuck data patterns
    "https://moneypuck.com/moneypuck/playerData/seasonSummary/2024/regular/teams.csv",
    "https://moneypuck.com/moneypuck/playerData/careers/gameByGame/regular/teams/all_teams.csv",
    "https://peter-tanner.com/moneypuck/downloads/shots_2024.zip",
    # Try the data API
    "https://moneypuck.com/data.htm",
]

headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

for url in URLS:
    try:
        r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        ct = r.headers.get("content-type", "")
        print(f"{r.status_code:3d} {len(r.text):>8d}B {ct[:40]:40s} {url}")
        if r.status_code == 200 and len(r.text) > 200:
            lines = r.text.strip().split("\n")
            if len(lines) > 1:
                print(f"     Headers: {lines[0][:120]}")
                print(f"     Row 1:   {lines[1][:120]}")
    except Exception as e:
        print(f"ERR {str(e)[:60]:60s} {url}")
