"""API-Football odds source — wrapper around api_clients/api_football_odds.py."""

import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from odds_sources import OddsSource
from api_clients.api_football_odds import APIFootballOddsClient
from api_clients.rate_limiter import RateLimiter


class APIFootballOddsSource(OddsSource):
    """Wrapper around APIFootballOddsClient."""

    name = "api-football-odds"

    def __init__(self):
        self._limiter = RateLimiter()
        self._client = APIFootballOddsClient(rate_limiter=self._limiter)

    def supported_sports(self) -> list[str]:
        return ["football"]

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        if sport != "football":
            return []

        all_events = []
        # API-Football odds endpoint works per-date; iterate date range
        from datetime import datetime, timedelta
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            end = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            return []

        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            try:
                events = self._client.fetch_odds_for_date(date_str)
            except Exception as e:
                print(f"[api-football-odds] Error fetching {date_str}: {e}")
                current += timedelta(days=1)
                continue

            for event in events:
                event["_odds_source"] = self.name
                all_events.append(event)

            current += timedelta(days=1)

        return all_events


SOURCE = APIFootballOddsSource()
