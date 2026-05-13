"""Quick test of Sofascore API connectivity for all sports."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import json
import logging
from bet.api_clients.sofascore import SofascoreClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SPORT_MAP = {
    "football": "football",
    "tennis": "tennis",
    "basketball": "basketball",
    "hockey": "ice-hockey",
}

def main():
    date = "2026-05-13"
    client = SofascoreClient()
    
    for sport_label, sofascore_sport in SPORT_MAP.items():
        try:
            fixtures = client.get_fixtures(date, sport=sofascore_sport)
            logger.info(f"[{sport_label}] Found {len(fixtures)} events via Sofascore API")
            
            if fixtures:
                ev = fixtures[0]
                eid = ev.get("id")
                home = ev.get("homeTeam", {}).get("name", "?")
                away = ev.get("awayTeam", {}).get("name", "?")
                logger.info(f"  Sample: {home} vs {away} (id={eid})")
                
                # Test stats endpoint
                stats = client.get_fixture_stats(str(eid))
                logger.info(f"  Stats groups: {len(stats)}")
                
                # Test H2H endpoint
                h2h = client.get_event_h2h(str(eid))
                h2h_keys = list(h2h.keys()) if h2h else []
                logger.info(f"  H2H keys: {h2h_keys}")
                
                # Test form endpoint
                form = client.get_team_last_fixtures(
                    str(ev.get("homeTeam", {}).get("id", "")), last_n=5
                )
                logger.info(f"  Home form matches: {len(form)}")
        except Exception as e:
            logger.error(f"[{sport_label}] FAILED: {e}")

    logger.info("=== Sofascore API test complete ===")

if __name__ == "__main__":
    main()
