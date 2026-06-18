# ruff: noqa: E501, I001, W291, W293
"""ESPN discovery adapter — wraps ESPNClient scoreboard."""

from datetime import UTC, datetime

from bet.api_clients.espn import ESPNClient
from bet.api_clients.base_client import SourceResultStatus
from bet.api_clients.rate_limiter import RateLimiter

from ..models import DiscoveredEvent
from .base import AbstractSourceAdapter


class ESPNDiscoveryAdapter(AbstractSourceAdapter):
    """Primary/Fallback discovery source for football."""

    name = "espn"
    priority = 1
    supported_sports = ["football"]

    def __init__(self, rate_limiter: RateLimiter | None = None):
        self._limiter = rate_limiter or RateLimiter()
        self._client = ESPNClient(sport="football", league="eng.1", rate_limiter=self._limiter)
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
        for f in result.value or []:
            try:
                kickoff = (
                    datetime.fromisoformat(f.kickoff.replace("Z", "+00:00"))
                    if isinstance(f.kickoff, str)
                    else f.kickoff
                )

                if kickoff.tzinfo is None:
                    kickoff = kickoff.replace(tzinfo=UTC)

                events.append(
                    DiscoveredEvent(
                        source=self.name,
                        external_id=f.external_id,
                        sport="football",
                        competition=f.competition_name,
                        home_team=f.home_team_name,
                        away_team=f.away_team_name,
                        kickoff=kickoff,
                        status=f.status,
                        raw_data={
                            "provider_participant_ids": {
                                "home": f.home_participant_id,
                                "away": f.away_participant_id,
                            },
                            "competition_id": f.competition_id,
                            "season_id": f.season_id,
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
            except Exception as e:
                self.logger.debug("Skipping ESPN event: %s", e)
                continue

        return events
