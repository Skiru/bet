"""BetExplorer odds source — uses BetExplorerClient (HTTP-first, no Playwright)."""

import logging
import sys
from pathlib import Path

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
_SRC_DIR = str(Path(__file__).resolve().parent.parent.parent / "src")
for p in (_SCRIPTS_DIR, _SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from odds_sources import OddsSource, make_event_id

logger = logging.getLogger(__name__)


class BetExplorerSource(OddsSource):
    """BetExplorer HTTP-first source — fast, no Playwright overhead."""

    name = "betexplorer"
    _client = None

    SUPPORTED = ["football", "tennis", "basketball", "hockey", "volleyball"]

    def _get_client(self):
        if self._client is None:
            try:
                from bet.api_clients.betexplorer import BetExplorerClient
                self._client = BetExplorerClient()
            except Exception as e:
                logger.warning(f"BetExplorerClient unavailable: {e}")
        return self._client

    def supported_sports(self) -> list[str]:
        return list(self.SUPPORTED)

    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        if sport not in self.SUPPORTED:
            return []

        client = self._get_client()
        if not client:
            return []

        events = []
        try:
            fixtures = client.get_fixtures(date_from, sport=sport)

            for fix in fixtures:
                event_id = make_event_id(
                    self.name, sport, fix.home_team_name, fix.away_team_name, fix.kickoff
                )

                # BetExplorerClient.get_fixtures() returns APIFixture objects
                # which do NOT contain odds. Listing odds exist in the HTML but
                # are not parsed by the current client. Events are added with
                # empty bookmakers — useful for fixture discovery but not odds.
                bookmakers = []

                events.append({
                    "id": event_id,
                    "home_team": fix.home_team_name,
                    "away_team": fix.away_team_name,
                    "commence_time": fix.kickoff,
                    "sport_key": sport,
                    "bookmakers": bookmakers,
                    "_our_sport": sport,
                    "_source": self.name,
                })

            if events:
                logger.info(f"[BetExplorer] Fetched {len(events)} events for {sport} (no odds — client stub)")
            else:
                logger.info(f"[BetExplorer] No events found for {sport}")

        except Exception as e:
            logger.error(f"[BetExplorer] fetch_odds failed for {sport}: {e}")

        return events


SOURCE = BetExplorerSource()
