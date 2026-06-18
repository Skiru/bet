"""Football-Data.org discovery adapter for football fixture discovery."""

from datetime import UTC, datetime

from bet.api_clients.base_client import SourceResultStatus
from bet.api_clients.football_data_org import FootballDataOrgClient
from bet.api_clients.rate_limiter import RateLimiter

from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class FootballDataOrgDiscoveryAdapter(AbstractSourceAdapter):
    """Football-Data.org discovery source for football."""

    name = "football-data"
    priority = 2
    supported_sports = ["football"]

    def __init__(self, competition: str | None = "PL", rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = FootballDataOrgClient(rate_limiter=self._limiter)
        self.competition = competition
        super().__init__()

    def is_available(self) -> bool:
        return self._client.is_available()

    def _fetch_events_impl(self, date: str, sport: str) -> list[DiscoveredEvent]:
        result = self._client.get_fixtures_result(date, competition=self.competition)
        if result.status is not SourceResultStatus.SUCCESS:
            self._record_error(
                f"status={result.status.value} code={result.error_code} "
                f"http={result.http_status} bundle={result.bundle_id or '-'}"
            )
            return []

        events: list[DiscoveredEvent] = []
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
                        external_id=fixture.fixture_id,
                        sport="football",
                        competition=fixture.competition,
                        home_team=fixture.home_team,
                        away_team=fixture.away_team,
                        kickoff=kickoff,
                        status=fixture.status,
                        raw_data={
                            "provider_participant_ids": {
                                "home": fixture.home_team_id,
                                "away": fixture.away_team_id,
                            },
                            "competition_code": fixture.competition,
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
                self.logger.debug("Skipping Football-Data.org event: %s", exc)
                continue

        return events
