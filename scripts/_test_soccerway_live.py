#!/usr/bin/env python3
"""Live test — fetch today's fixtures from Soccerway."""
import sys
sys.path.insert(0, "src")

from bet.api_clients.soccerway import SoccerwayClient

print("Fetching fixtures from Soccerway (Playwright)...")
print("This will take ~15 seconds for browser startup + rendering\n")

with SoccerwayClient() as client:
    fixtures = client.get_fixtures("2026-05-13")
    
    print(f"Total fixtures: {len(fixtures)}")
    
    if fixtures:
        # Show first 20 fixtures grouped by competition
        comps = {}
        for f in fixtures:
            comps.setdefault(f.competition_name, []).append(f)
        
        print(f"\nCompetitions: {len(comps)}")
        for comp, fxs in sorted(comps.items()):
            print(f"\n  {comp} ({len(fxs)} matches):")
            for fx in fxs[:3]:
                print(f"    {fx.home_team_name} vs {fx.away_team_name} [{fx.kickoff}] ({fx.status})")
            if len(fxs) > 3:
                print(f"    ... +{len(fxs) - 3} more")
    else:
        print("No fixtures found!")

print("\nDone.")
