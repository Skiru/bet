"""Football-Data.org client — EU football fixtures, results, standings.

Docs: https://docs.football-data.org/general/v4/index.html
Host: api.football-data.org/v4
Auth: X-Auth-Token header
Rate limit: 10 requests/minute (free tier)
"""

import json

import requests

from bet.integration.evidence import (
    namespaced_source_refs,
    write_source_operation_bundle,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.models.normalized import NormalizedFixture

from .base_client import BaseAPIClient
from .rate_limiter import RateLimiter

FIXTURES_PARSER_VERSION = "football-data-org-fixtures-v1"
STANDINGS_PARSER_VERSION = "football-data-org-standings-v1"


class FootballDataOrgClient(BaseAPIClient):
    """Football-Data.org client for football fixtures and standings."""

    COMPETITION_CODES = {
        "PL": "Premier League",
        "BL1": "Bundesliga",
        "SA": "Serie A",
        "PD": "La Liga",
        "FL1": "Ligue 1",
        "DED": "Eredivisie",
        "PPL": "Primeira Liga",
        "ELC": "Championship",
        "BSA": "Brasileirão",
        "CLI": "Copa Libertadores",
    }

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="football-data-org",
            base_url="https://api.football-data.org/v4",
            rate_limiter=rate_limiter,
        )

    def _build_headers(self) -> dict:
        """Override to use X-Auth-Token header."""
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-Auth-Token"] = self.api_key
        return headers

    def _check_api_key(self) -> bool:
        """Return True if API key is available."""
        if not self.api_key:
            print(f"[{self.api_name}] Skipping — no API key configured")
            return False
        return True

    def _request_with_evidence(
        self,
        endpoint: str,
        params: dict | None = None,
        operation: str = "",
        source_event_id: str | None = None,
        cost: int = 1,
        expects_response_list: bool = False,
    ) -> SourceOperationResult[dict]:
        from bet.integration.evidence import persist_response_evidence
        from bet.integration.telemetry_wrapper import wrap_request

        if not self.rate_limiter.can_request(self.api_name, cost):
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                retryable=True,
                error_code="quota_exhausted",
            )

        url = f"{self.base_url}{endpoint}"
        result = wrap_request(
            provider=self.api_name,
            request_fn=requests.get,
            url=url,
            params=params,
            headers=self._build_headers(),
            timeout=self.TIMEOUT,
            scope_id=endpoint,
        )
        self.rate_limiter.record_request(self.api_name, endpoint, cost)

        evidence_refs = []
        if result.status_code is not None:
            try:
                evidence_ref = persist_response_evidence(
                    operation=operation,
                    url=url,
                    params=params,
                    response=result,
                    source_event_id=source_event_id,
                )
                evidence_refs.append(evidence_ref)
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=result.status_code,
                    error_code="evidence_persist_failed",
                    retry_count=result.retry_count,
                )

        if result.error and result.status_code is None:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                retryable=bool(result.error.retryable),
                error_code=result.error.type or "transport_error",
                evidence_refs=evidence_refs,
                retry_count=result.retry_count,
            )

        status_code = result.status_code or 0
        if status_code == 401:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                http_status=401,
                error_code="http_401",
                evidence_refs=evidence_refs,
            )
        if status_code == 403:
            return SourceOperationResult(
                status=SourceResultStatus.BLOCKED,
                http_status=403,
                error_code="http_403",
                evidence_refs=evidence_refs,
            )
        if status_code == 404:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND,
                http_status=404,
                error_code="http_404",
                evidence_refs=evidence_refs,
            )
        if status_code == 429:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                http_status=429,
                retryable=True,
                error_code="http_429",
                evidence_refs=evidence_refs,
            )
        if status_code >= 400:
            return SourceOperationResult(
                status=SourceResultStatus.UPSTREAM_ERROR,
                http_status=status_code,
                error_code=f"http_{status_code}",
                evidence_refs=evidence_refs,
            )

        try:
            payload = json.loads(result.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                http_status=status_code,
                error_code="json_decode_error",
                evidence_refs=evidence_refs,
            )

        if not isinstance(payload, dict):
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=status_code,
                error_code="payload_not_object",
                evidence_refs=evidence_refs,
            )

        if expects_response_list and not isinstance(payload.get("response"), list):
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=status_code,
                error_code="response_not_list",
                evidence_refs=evidence_refs,
            )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=payload,
            http_status=status_code,
            evidence_refs=evidence_refs,
            retry_count=result.retry_count,
            quota_metadata={},
        )

    def get_fixtures_result(
        self, date: str, competition: str | None = None
    ) -> SourceOperationResult[list[NormalizedFixture]]:
        """GET /matches?dateFrom={date}&dateTo={date} with evidence capture."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        if competition:
            endpoint = f"/competitions/{competition}/matches"
            params = {"dateFrom": date, "dateTo": date}
        else:
            endpoint = "/matches"
            params = {"dateFrom": date, "dateTo": date}

        result = self._request_with_evidence(
            endpoint=endpoint,
            params=params,
            operation="get_fixtures",
            expects_response_list=False,
        )
        if (
            result.status is not SourceResultStatus.SUCCESS
            or not isinstance(result.value, dict)
        ):
            return result

        raw_matches = result.value.get("matches", [])
        if not isinstance(raw_matches, list):
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                error_code="matches_not_list",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        fixtures: list[NormalizedFixture] = []
        rejected_count = 0
        for match in raw_matches:
            try:
                home = match.get("homeTeam", {})
                away = match.get("awayTeam", {})
                competition = match.get("competition", {})
                fixtures.append(
                    NormalizedFixture(
                        fixture_id=str(match.get("id", "")),
                        source=self.api_name,
                        sport="football",
                        competition=(
                            competition.get("code")
                            or competition.get("name", "")
                        ),
                        home_team=home.get("name", ""),
                        away_team=away.get("name", ""),
                        home_team_id=str(home.get("id", "")),
                        away_team_id=str(away.get("id", "")),
                        kickoff=match.get("utcDate", ""),
                        status=match.get("status", "SCHEDULED"),
                    )
                )
            except Exception:
                rejected_count += 1

        diagnostics = {
            "raw_count": len(raw_matches),
            "accepted_count": len(fixtures),
            "rejected_count": rejected_count,
        }
        if raw_matches and not fixtures:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                error_code="no_valid_fixture_rows",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
                parser_diagnostics=diagnostics,
            )

        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_fixtures",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version=FIXTURES_PARSER_VERSION,
                    source_event_refs=namespaced_source_refs(
                        self.api_name,
                        [fixture.fixture_id for fixture in fixtures],
                    ),
                    evidence_refs=result.evidence_refs,
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=result.http_status,
                    error_code="bundle_manifest_failed",
                    evidence_refs=result.evidence_refs,
                    retry_count=result.retry_count,
                    quota_metadata=result.quota_metadata,
                    parser_diagnostics=diagnostics,
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=fixtures,
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            retry_count=result.retry_count,
            quota_metadata=result.quota_metadata,
            parser_diagnostics=diagnostics,
        )

    def get_fixtures(self, date: str) -> list:
        """GET /matches?dateFrom={date}&dateTo={date}

        Returns list of NormalizedFixture.
        Note: Does NOT provide per-match corner/foul stats — only scores.
        """
        result = self.get_fixtures_result(date)
        if result.status is not SourceResultStatus.SUCCESS:
            return []
        return list(result.value or [])

    def get_standings_result(
        self, competition: str
    ) -> SourceOperationResult[list[dict]]:
        """GET /competitions/{code}/standings with evidence capture."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        result = self._request_with_evidence(
            endpoint=f"/competitions/{competition}/standings",
            params=None,
            operation="get_standings",
            expects_response_list=False,
        )
        if (
            result.status is not SourceResultStatus.SUCCESS
            or not isinstance(result.value, dict)
        ):
            return result

        standings = result.value.get("standings", [])
        if not isinstance(standings, list):
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                error_code="standings_not_list",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        diagnostics = {
            "raw_count": len(standings),
            "accepted_count": len(standings),
            "rejected_count": 0,
        }

        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_standings",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version=STANDINGS_PARSER_VERSION,
                    source_event_refs=[],
                    evidence_refs=result.evidence_refs,
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=result.http_status,
                    error_code="bundle_manifest_failed",
                    evidence_refs=result.evidence_refs,
                    retry_count=result.retry_count,
                    quota_metadata=result.quota_metadata,
                    parser_diagnostics=diagnostics,
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=standings,
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            retry_count=result.retry_count,
            quota_metadata=result.quota_metadata,
            parser_diagnostics=diagnostics,
        )

    def get_fixture_stats(self, fixture_id: str) -> dict:
        """Not supported — Football-Data.org does not provide per-match detailed stats.

        Returns empty dict.
        """
        return {}

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list:
        """Not directly supported. Returns empty list."""
        return []

    def get_team_matches(self, team_id: str, last_n: int = 10) -> list:
        """GET /teams/{id}/matches?status=FINISHED&limit={n}

        Returns list of NormalizedFixture for recent finished matches.
        """
        if not self._check_api_key():
            return []

        cache_key = f"football-data-org/team_matches/{team_id}_last{last_n}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return [NormalizedFixture(**f) for f in cached.get("fixtures", [])]

        try:
            data = self._request(
                f"/teams/{team_id}/matches",
                params={"status": "FINISHED", "limit": str(last_n)},
            )
        except Exception as e:
            print(f"[{self.api_name}] Error fetching matches for team {team_id}: {e}")
            return []

        fixtures = []
        for match in data.get("matches", []):
            home = match.get("homeTeam", {})
            away = match.get("awayTeam", {})
            competition = match.get("competition", {})

            fixture = NormalizedFixture(
                fixture_id=str(match.get("id", "")),
                source=self.api_name,
                sport="football",
                competition=competition.get("name", ""),
                home_team=home.get("name", ""),
                away_team=away.get("name", ""),
                home_team_id=str(home.get("id", "")),
                away_team_id=str(away.get("id", "")),
                kickoff=match.get("utcDate", ""),
                status="FT",
            )
            fixtures.append(fixture)

        from dataclasses import asdict
        self._save_cache(cache_key, {
            "fixtures": [asdict(f) for f in fixtures],
            "count": len(fixtures),
        })

        return fixtures

    def get_standings(self, competition: str) -> list:
        """GET /competitions/{code}/standings

        Returns standings data for a competition code (e.g. 'PL', 'BL1').
        """
        result = self.get_standings_result(competition)
        if result.status is not SourceResultStatus.SUCCESS:
            return []
        return list(result.value or [])
