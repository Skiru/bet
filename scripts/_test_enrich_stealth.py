#!/usr/bin/env python3
"""Test enrichment with stealth — try a few specific teams."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from data_enrichment_agent import enrich_team

# Test 1: Football team
print("=== Test 1: Manchester City (football) ===")
result = enrich_team("Manchester City", "football")
print(f"  Status: {result['status']}, Source: {result['source']}")
print(f"  Stats: {result['stats_found']}")
print(f"  Error: {result['error']}")

# Test 2: Tennis player
print("\n=== Test 2: Elena Rybakina (tennis) ===")
result2 = enrich_team("Elena Rybakina", "tennis")
print(f"  Status: {result2['status']}, Source: {result2['source']}")
print(f"  Stats: {result2['stats_found']}")
print(f"  Error: {result2['error']}")

# Test 3: Basketball
print("\n=== Test 3: Dallas Wings (basketball) ===")
result3 = enrich_team("Dallas Wings", "basketball")
print(f"  Status: {result3['status']}, Source: {result3['source']}")
print(f"  Stats: {result3['stats_found']}")
print(f"  Error: {result3['error']}")

print("\n=== DONE ===")
