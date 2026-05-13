#!/usr/bin/env python3
"""Quick multi-sport test for OddsPortalClient."""
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from bet.api_clients.oddsportal import OddsPortalClient

sports = ["football", "tennis", "basketball", "hockey"]
with OddsPortalClient() as client:
    for sport in sports:
        fixtures = client.get_fixtures("2026-05-13", sport)
        leagues = set(f.competition_name for f in fixtures)
        print(f"\n{sport}: {len(fixtures)} fixtures, {len(leagues)} leagues")
        for f in fixtures[:3]:
            print(f"  {f.home_team_name} vs {f.away_team_name} ({f.competition_name})")
