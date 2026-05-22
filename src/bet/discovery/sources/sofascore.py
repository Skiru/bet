"""SofaScore source adapter — wraps existing SofascoreClient.

STATUS: DEGRADED — permanently blocked (403). Not registered in coordinator.
Keep file for potential re-enablement. SofascoreClient is still used for
enrichment (H2H, statistics) via main-thread Playwright fallback.
"""

from datetime import datetime, timezone

from bet.api_clients.sofascore import SofascoreClient
from bet.api_clients.rate_limiter import RateLimiter
from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter

# SofaScore uses different sport slugs
SPORT_SLUG_MAP = {
    "football": "football",
    "basketball": "basketball",
    "tennis": "tennis",
    "hockey": "ice-hockey",
    "volleyball": "volleyball",
}


class SofaScoreAdapter(AbstractSourceAdapter):
    """DEGRADED — 403 blocked. Cannot work in ThreadPoolExecutor (Playwright main-thread only)."""

    name = "sofascore"
    priority = 99  # degraded — not registered
    supported_sports = ["football", "volleyball", "basketball", "tennis", "hockey"]

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._client = SofascoreClient(rate_limiter=rate_limiter or RateLimiter())
        super().__init__()

    def is_available(self) -> bool:
        return True  # No API key needed

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        slug = SPORT_SLUG_MAP.get(sport, sport)
        api_fixtures = self._client.get_fixtures(date, sport=slug)

        events = []
        for f in api_fixtures:
            try:
                kickoff = datetime.fromisoformat(
                    f.kickoff.replace("Z", "+00:00")
                ) if isinstance(f.kickoff, str) else f.kickoff

                # Ensure timezone-aware
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)

                events.append(DiscoveredEvent(
                    source="sofascore",
                    external_id=f.external_id,
                    sport=f.sport,
                    competition=f.competition_name,
                    home_team=f.home_team_name,
                    away_team=f.away_team_name,
                    kickoff=kickoff,
                    status=f.status,
                ))
            except Exception as e:
                self.logger.debug("Skipping SofaScore event: %s", e)
                continue

        return events
