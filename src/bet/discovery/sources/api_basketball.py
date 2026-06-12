"""API-Basketball source adapter — basketball fixture discovery."""

from datetime import UTC, datetime

from bet.api_clients.api_basketball import APIBasketballClient
from bet.api_clients.base_client import SourceResultStatus
from bet.api_clients.rate_limiter import RateLimiter

from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class APIBasketballAdapter(AbstractSourceAdapter):
    """Supplementary source — basketball fixtures beyond bookmaker feeds."""

    name = "api-basketball"
    priority = 3
    supported_sports = ["basketball"]

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = APIBasketballClient(rate_limiter=self._limiter)
        super().__init__()

    def is_available(self) -> bool:
        return self._client.is_available()

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        result = self._client.get_fixtures_result(date)
        if result.status is not SourceResultStatus.SUCCESS:
            self._record_error(

                    f"status={result.status.value} code={result.error_code} "
                    f"http={result.http_status} bundle={result.bundle_id or '-'}"

            )
            return []

        events = []
        for fixture in result.value or []:
            try:
                kickoff = (
                    datetime.fromisoformat(fixture.kickoff.replace("Z", "+00:00"))
                    if isinstance(fixture.kickoff, str)
                    else fixture.kickoff
                )
                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=UTC)
                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=fixture.external_id,
                        sport="basketball",
                        competition=fixture.competition_name,
                        home_team=fixture.home_team_name,
                        away_team=fixture.away_team_name,
                        kickoff=kickoff,
                        status=fixture.status,
                        raw_data={
                            "provider_participant_ids": {
                                "home": fixture.home_participant_id,
                                "away": fixture.away_participant_id,
                            },
                            "competition_id": fixture.competition_id,
                            "season_id": fixture.season_id,
                            "source_operation_status": result.status.value,
                            "evidence_bundle_id": result.bundle_id,
                            "evidence_object_ids": [
                                ref.object_sha256 for ref in result.evidence_refs
                            ],
                            "parser_diagnostics": result.parser_diagnostics,
                            "quota_metadata": result.quota_metadata,
                        },
                    )
                )
            except Exception as exc:
                self.logger.debug("Skipping API-Basketball event: %s", exc)
        return events
