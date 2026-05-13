"""Quick test: volleyball fixtures."""
import sys, logging
sys.stdout.reconfigure(line_buffering=True)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from bet.api_clients.flashscore import FlashscoreClient

client = FlashscoreClient()
try:
    fixtures = client.get_fixtures("2026-05-13", sport="volleyball")
    print(f"Volleyball fixtures: {len(fixtures)}", flush=True)
    for f in fixtures[:5]:
        print(f"  {f.competition_name}: {f.home_team_name} vs {f.away_team_name}", flush=True)
finally:
    client.close()
print("DONE", flush=True)
