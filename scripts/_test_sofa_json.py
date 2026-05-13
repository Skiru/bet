#!/usr/bin/env python3
"""Test Sofascore JSON API with stealth."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.api_clients.sofascore import SofascoreClient

client = SofascoreClient()

# Test 1: Football fixtures
print("=== Football fixtures 2026-05-13 ===")
fixtures = client.get_fixtures("2026-05-13", sport="football")
print(f"Found {len(fixtures)} football events")
if fixtures:
    ev = fixtures[0]
    home = ev.get("homeTeam", {}).get("name", "?")
    away = ev.get("awayTeam", {}).get("name", "?")
    eid = ev.get("id")
    print(f"  Sample: {home} vs {away} (id={eid})")

# Test 2: Tennis fixtures  
print("\n=== Tennis fixtures 2026-05-13 ===")
fixtures_t = client.get_fixtures("2026-05-13", sport="tennis")
print(f"Found {len(fixtures_t)} tennis events")
if fixtures_t:
    ev = fixtures_t[0]
    home = ev.get("homeTeam", {}).get("name", "?")
    away = ev.get("awayTeam", {}).get("name", "?")
    eid = ev.get("id")
    print(f"  Sample: {home} vs {away} (id={eid})")

# Test 3: Basketball
print("\n=== Basketball fixtures 2026-05-13 ===")
fixtures_b = client.get_fixtures("2026-05-13", sport="basketball")
print(f"Found {len(fixtures_b)} basketball events")

# Test 4: Hockey
print("\n=== Hockey fixtures 2026-05-13 ===")
fixtures_h = client.get_fixtures("2026-05-13", sport="ice-hockey")
print(f"Found {len(fixtures_h)} hockey events")

print("\n=== DONE ===")
