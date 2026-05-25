#!/usr/bin/env python3
"""Test bo3.gg match detail approach for CS2 enrichment.

Uses the existing get_cs2_matches_with_odds() (Playwright, working)
to get today's CS2 matches, then get_valorant_match_detail() for form/H2H.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.scrapers.bo3gg import Bo3GGScraper

with Bo3GGScraper() as scraper:
    print("=== Getting CS2 matches from bo3.gg ===")
    matches = scraper.get_cs2_matches_with_odds()
    print(f"Found {len(matches)} CS2 matches on bo3.gg")
    for m in matches[:10]:
        print(f"  {m['home_team']} vs {m['away_team']} | {m['format']} | odds={m.get('odds_home')}/{m.get('odds_away')} | {m['match_url'][:60]}")

    # Get detail for first match with a URL
    if matches:
        test_match = matches[0]
        print(f"\n=== Detail for: {test_match['home_team']} vs {test_match['away_team']} ===")
        detail = scraper.get_valorant_match_detail(test_match['match_url'])
        print(f"  ML odds: {detail.get('ml_odds')}")
        print(f"  Format: {detail.get('format')}")
        print(f"  H2H: {detail.get('h2h')}")
        print(f"  Form home: {detail.get('form_home')}")
        print(f"  Form away: {detail.get('form_away')}")
        print(f"  Lineups: {len(detail.get('lineups_home', []))} + {len(detail.get('lineups_away', []))}")
