#!/usr/bin/env python3
"""Quick test of VLR and bo3.gg scrapers for esports enrichment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.scrapers.vlr import VLRScraper

vlr = VLRScraper()

# Test Valorant teams from today's fixtures
test_teams = ["FunPlus Phoenix", "Joblife", "FENNEL", "Leviatan", "BESTIA", "KRU"]

for team in test_teams:
    print(f"\n=== Testing: {team} ===")
    url = vlr.search_team(team)
    print(f"  URL found: {url}")
    if url:
        stats = vlr.get_team_stats(team)
        print(f"  Stats: {stats}")
    else:
        print("  NOT FOUND")
