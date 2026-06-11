"""API-Volleyball source adapter — broad volleyball fixture discovery."""

from datetime import datetime, timezone

from bet.api_clients.api_volleyball import APIVolleyballClient
from bet.api_clients.rate_limiter import RateLimiter

from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class APIVolleyballAdapter(AbstractSourceAdapter):
    """Supplementary source — volleyball fixtures beyond bookmaker feeds."""

    name = "api-volleyball"
    priority = 3
    supported_sports = ["volleyball"]

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = APIVolleyballClient(rate_limiter=self._limiter)
        super().__init__()

    def is_available(self) -> bool:
        return self._client.is_available()

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        fixtures = self._client.get_fixtures(date)
        events = []
        for fixture in fixtures:
            try:
                kickoff = datetime.fromisoformat(
                    fixture.kickoff.replace("Z", "+00:00")
                ) if isinstance(fixture.kickoff, str) else fixture.kickoff
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=timezone.utc)
                events.append(DiscoveredEvent(
                    source=self.name,
                    external_id=fixture.external_id,
                    sport="volleyball",
                    competition=fixture.competition_name,
                    home_team=fixture.home_team_name,
                    away_team=fixture.away_team_name,
                    kickoff=kickoff,
                    status=fixture.status,
                ))
            except Exception as exc:
                self.logger.debug("Skipping API-Volleyball event: %s", exc)
        return events
