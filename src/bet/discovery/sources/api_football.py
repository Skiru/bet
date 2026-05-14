"""API-Football source adapter — wraps existing APIFootballClient."""

from datetime import datetime, timezone

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.rate_limiter import RateLimiter
from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class APIFootballAdapter(AbstractSourceAdapter):
    """Tertiary source — football only, 100 req/day."""

    name = "api-football"
    priority = 3
    supported_sports = ["football"]

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = APIFootballClient(rate_limiter=self._limiter)
        super().__init__()

    def is_available(self) -> bool:
        return self._client.is_available()

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        api_fixtures = self._client.get_fixtures(date)

        events = []
        for f in api_fixtures:
            try:
                kickoff = datetime.fromisoformat(
                    f.kickoff.replace("Z", "+00:00")
                ) if isinstance(f.kickoff, str) else f.kickoff

                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)

                events.append(DiscoveredEvent(
                    source="api-football",
                    external_id=f.external_id,
                    sport="football",
                    competition=f.competition_name,
                    home_team=f.home_team_name,
                    away_team=f.away_team_name,
                    kickoff=kickoff,
                    status=f.status,
                ))
            except Exception as e:
                self.logger.debug("Skipping API-Football event: %s", e)
                continue

        return events
