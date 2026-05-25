#!/usr/bin/env python3
"""Test the new get_cs2_match_detail method."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.scrapers.bo3gg import Bo3GGScraper
import json

with Bo3GGScraper() as scraper:
    # Test with the BIG Academy vs Kinoa match
    url = "https://bo3.gg/matches/big-academy-vs-kinoa-25-05-2026"
    print(f"=== Testing CS2 match detail: {url} ===\n")
    detail = scraper.get_cs2_match_detail(url)
    
    print(f"Home: {detail.get('home_team')}")
    print(f"Away: {detail.get('away_team')}")
    print(f"Format: {detail.get('format')}")
    print(f"ML Odds: {detail.get('ml_odds')}")
    print(f"H2H: {detail.get('h2h')}")
    print(f"Form home: {detail.get('form_home')}")
    print(f"Form away: {detail.get('form_away')}")
    print(f"Map WR home: {detail.get('map_winrate_home')}")
    print(f"Map WR away: {detail.get('map_winrate_away')}")
    print(f"Lineups home: {detail.get('lineups_home')}")
    print(f"Lineups away: {detail.get('lineups_away')}")
    print(f"Insights ({len(detail.get('insights', []))}):")
    for ins in detail.get('insights', [])[:4]:
        print(f"  - {ins[:80]}")
