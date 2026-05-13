"""OddsPortal odds source — uses OddsPortalClient via API client layer."""

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


class OddsPortalSource(OddsSource):
    """OddsPortal source using Playwright-based OddsPortalClient."""

    name = "oddsportal"
    _client = None

    SUPPORTED = ["football", "tennis", "basketball", "hockey", "volleyball"]

    def _get_client(self):
        if self._client is None:
            try:
                from bet.api_clients.oddsportal import OddsPortalClient
                self._client = OddsPortalClient()
            except Exception as e:
                logger.warning(f"OddsPortalClient unavailable: {e}")
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
            # Use date_from as the scan date
            fixtures = client.get_fixtures(date_from, sport=sport)
            listing_odds = client.get_listing_odds()

            for fix in fixtures:
                event_id = make_event_id(
                    self.name, sport, fix.home_team_name, fix.away_team_name, fix.kickoff
                )

                bookmakers = []

                # Check if we have inline listing odds for this fixture
                match_key = f"{fix.home_team_name} vs {fix.away_team_name}"
                inline = listing_odds.get(fix.external_id) or listing_odds.get(match_key, {})

                if inline:
                    outcomes = []
                    if inline.get("odds_1"):
                        outcomes.append({"name": fix.home_team_name, "price": float(inline["odds_1"])})
                    if inline.get("odds_x"):
                        outcomes.append({"name": "Draw", "price": float(inline["odds_x"])})
                    if inline.get("odds_2"):
                        outcomes.append({"name": fix.away_team_name, "price": float(inline["odds_2"])})

                    if outcomes:
                        bookmakers.append({
                            "key": "oddsportal_average",
                            "title": "OddsPortal Average",
                            "markets": [{"key": "h2h", "outcomes": outcomes}],
                        })

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

            logger.info(f"[OddsPortal] Fetched {len(events)} events for {sport}")

        except Exception as e:
            logger.error(f"[OddsPortal] fetch_odds failed for {sport}: {e}")

        return events

    def close(self):
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


SOURCE = OddsPortalSource()
