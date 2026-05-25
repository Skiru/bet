#!/usr/bin/env python3
"""Quick test of fixed bo3.gg scraper (Playwright-based search)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.scrapers.bo3gg import Bo3GGScraper

with Bo3GGScraper() as scraper:
    # Test CS2 teams from today's fixtures
    test_teams = ["G2 Esports", "NAVI Junior", "BIG Academy"]
    
    for team in test_teams:
        print(f"\n=== Testing: {team} ===")
        url = scraper.search_team(team)
        print(f"  URL: {url}")
        if url:
            stats = scraper.get_team_stats(team)
            print(f"  Stats: {stats}")
        else:
            print("  NOT FOUND")
