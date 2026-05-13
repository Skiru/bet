"""Quick smoke test: verify ESPN + UnifiedAPIClient work for scanning."""
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
sys.path.insert(0, "src")

from bet.api_clients.unified import UnifiedAPIClient
from bet.api_clients.api_football import APIFixture

client = UnifiedAPIClient()
date = "2026-05-13"

SPORTS = ["football", "basketball", "tennis", "hockey", "volleyball"]

total = 0
for sport in SPORTS:
    fixtures = client.get_fixtures(date, sport)
    count = len(fixtures)
    total += count
    
    # Check types
    if fixtures:
        assert isinstance(fixtures[0], APIFixture), f"Expected APIFixture, got {type(fixtures[0])}"
        # Show sample
        f = fixtures[0]
        print(f"  {sport}: {count} fixtures | Sample: {f.home_team_name} vs {f.away_team_name} ({f.competition_name}) [src={f.source}]")
    else:
        print(f"  {sport}: 0 fixtures")

print(f"\nTOTAL: {total} fixtures across {len(SPORTS)} sports")
print("All fixtures are APIFixture objects: OK" if total > 0 else "WARNING: 0 total fixtures")
