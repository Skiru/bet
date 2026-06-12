"""API-Football v3 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats (lightweight containers for scanner/discovery
to convert into DB model objects).
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime

from bet.integration.evidence import (
    namespaced_source_refs,
    write_source_operation_bundle,
)

from .base_client import APISportsClient, SourceOperationResult, SourceResultStatus
from .rate_limiter import RateLimiter

# Map API-Football stat type names → normalized stat keys
STAT_TYPE_MAP = {
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Yellow Cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Total Shots": "shots",
    "Shots on Goal": "shots_on_target",
    "Ball Possession": "possession",
    "Offsides": "offsides",
    "Goalkeeper Saves": "saves",
}

FIXTURES_PARSER_VERSION = "api-football-fixtures-v2"


@dataclass
class APIFixture:
    """Lightweight fixture as returned by API clients."""

    external_id: str
    source: str
    sport: str
    competition_name: str
    home_team_name: str
    away_team_name: str
    kickoff: str
    status: str = "scheduled"
    home_participant_id: str = ""
    away_participant_id: str = ""
    competition_id: str = ""
    season_id: str = ""


@dataclass
class APIMatchStats:
    """Match statistics as returned by API clients."""

    external_id: str
    source: str
    sport: str
    home_team_name: str
    away_team_name: str
    stats: dict[str, dict[str, float]] = field(default_factory=dict)
    home_participant_id: str = ""
    away_participant_id: str = ""


class APIFootballClient(APISportsClient):
    """API-Football v3 — returns APIFixture and APIMatchStats objects."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-football",
            base_url="https://v3.football.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """GET /fixtures?date=YYYY-MM-DD → list of APIFixture."""
        if not self._check_api_key():
            return []

        cache_key = f"football/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [
                APIFixture(**f)
                for f in cached.get("fixtures", [])
                if isinstance(f, dict) and "external_id" in f
            ]

        try:
            data = self._request("/fixtures", params={"date": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for item in data.get("response", []):
            fix = item.get("fixture", {})
            league = item.get("league", {})
            teams = item.get("teams", {})

            fixture = APIFixture(
                external_id=str(fix.get("id", "")),
                source=self.api_name,
                sport="football",
                competition_name=league.get("name", ""),
                home_team_name=teams.get("home", {}).get("name", ""),
                away_team_name=teams.get("away", {}).get("name", ""),
                kickoff=fix.get("date", ""),
                status=fix.get("status", {}).get("short", "NS"),
            )
            fixtures.append(fixture)

        self._save_cache(
            cache_key,
            {
                "fixtures": [asdict(f) for f in fixtures],
                "count": len(fixtures),
            },
        )

        return fixtures

    def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
        """GET /fixtures/statistics?fixture={id} → list of APIMatchStats."""
        if not self._check_api_key():
            return []

        cache_key = f"football/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/fixtures/statistics", params={"fixture": fixture_id})
        except Exception as e:
            print(
                f"[{self.api_name}] Error fetching stats for fixture {fixture_id}: {e}"
            )
            return []

        response = data.get("response", [])
        if len(response) < 2:
            return []

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        for team_data in response:
            team_info = team_data.get("team", {})
            team_name = team_info.get("name", "")
            side = "home" if not teams else "away"
            teams[side] = team_name

            for stat_entry in team_data.get("statistics", []):
                stat_type = stat_entry.get("type", "")
                value = stat_entry.get("value")

                normalized_key = STAT_TYPE_MAP.get(stat_type)
                if not normalized_key:
                    continue

                if normalized_key == "possession" and isinstance(value, str):
                    value = float(value.replace("%", "").strip() or 0)
                elif value is None:
                    value = 0

                if normalized_key not in stats:
                    stats[normalized_key] = {}
                stats[normalized_key][side] = float(value)

        if not teams.get("home") or not teams.get("away"):
            return []

        result = [
            APIMatchStats(
                external_id=fixture_id,
                source=self.api_name,
                sport="football",
                home_team_name=teams["home"],
                away_team_name=teams["away"],
                stats=stats,
            )
        ]

        self._save_cache(cache_key, {"stats": [asdict(ms) for ms in result]})

        return result

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """GET /fixtures/headtohead?h2h={id1}-{id2}."""
        if not self._check_api_key():
            return []

        try:
            data = self._request(
                "/fixtures/headtohead",
                params={"h2h": f"{team1_id}-{team2_id}", "last": str(last_n)},
            )
            return data.get("response", [])
        except Exception:
            return []

    def get_event_fixture_result(
        self, date: str, event_id: str
    ) -> SourceOperationResult[APIFixture]:
        """GET /fixtures?id={event_id} with typed identity validation."""
        del date
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        result = self._request_with_evidence(
            endpoint="/fixtures",
            params={"id": event_id},
            operation="get_event_fixture",
            source_event_id=event_id,
            expects_response_list=True,
        )
        if result.status is not SourceResultStatus.SUCCESS or result.value is None:
            return result

        raw_items = result.value.get("response", [])
        fixtures = [
            parsed
            for item in raw_items
            if (parsed := self._parse_fixture_item(item)) is not None
        ]
        if not fixtures:
            status = (
                SourceResultStatus.NOT_FOUND
                if not raw_items
                else SourceResultStatus.SCHEMA_ERROR
            )
            return SourceOperationResult(
                status=status,
                http_status=result.http_status,
                error_code="event_fixture_missing",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        event_id_str = str(event_id).strip()
        exact = [f for f in fixtures if f.external_id == event_id_str]
        if len(exact) != 1:
            status = (
                SourceResultStatus.AMBIGUOUS
                if len(exact) > 1
                else SourceResultStatus.SCHEMA_ERROR
            )
            return SourceOperationResult(
                status=status,
                http_status=result.http_status,
                error_code="event_fixture_id_mismatch",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_event_fixture",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version=FIXTURES_PARSER_VERSION,
                    source_event_refs=namespaced_source_refs(self.api_name, [event_id]),
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
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=exact[0],
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            retry_count=result.retry_count,
            quota_metadata=result.quota_metadata,
        )

    def resolve_team_id(self, team_name: str) -> str | None:
        """Search for a team by name → return API team ID."""
        if not self._check_api_key():
            return None
        cache_key = f"football/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)  # 7 day cache
        if cached:
            return cached.get("team_id")
        try:
            data = self._request("/teams", params={"search": team_name})
            results = data.get("response", [])
            if results:
                tid = str(results[0].get("team", {}).get("id", ""))
                self._save_cache(cache_key, {"team_id": tid})
                return tid
        except Exception:
            pass
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """GET /fixtures?team={id}&season=2024 → filter to last N finished."""
        if not self._check_api_key():
            return []
        cache_key = f"football/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])
        try:
            data = self._request(
                "/fixtures",
                params={"team": team_id, "season": "2024"},
            )
            fixtures = data.get("response", [])
            finished = [
                f
                for f in fixtures
                if f.get("fixture", {}).get("status", {}).get("short")
                in ("FT", "AET", "PEN")
            ]
            finished.sort(
                key=lambda f: f.get("fixture", {}).get("date", ""),
                reverse=True,
            )
            result = [{"id": f.get("fixture", {}).get("id")} for f in finished[:last_n]]
            self._save_cache(cache_key, {"fixtures": result})
            return result
        except Exception:
            return []

    def get_team_last_fixtures_result(
        self,
        team_id: str,
        last_n: int = 10,
        analysis_cutoff_at: str | None = None,
        exclude_event_ids: set[str] | None = None,
        season_id: str | None = None,
        competition_id: str | None = None,
    ) -> SourceOperationResult[list[dict]]:
        """GET finished team fixtures with strict temporal filtering."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        excluded_ids = {
            str(event_id).strip()
            for event_id in (exclude_event_ids or set())
            if str(event_id).strip()
        }
        params = {"team": team_id, "season": season_id or "2024"}
        if competition_id:
            params["league"] = competition_id

        result = self._request_with_evidence(
            endpoint="/fixtures",
            params=params,
            operation="get_team_last_fixtures",
            source_event_id=None,
            expects_response_list=True,
        )
        if result.status is not SourceResultStatus.SUCCESS or result.value is None:
            return result

        cutoff_dt = datetime.fromisoformat(analysis_cutoff_at.replace("Z", "+00:00")) if analysis_cutoff_at else None
        raw_items = result.value.get("response", [])
        finished: list[dict] = []

        for item in raw_items:
            parsed = self._parse_fixture_item(item)
            if parsed is None:
                continue
            if parsed.external_id in excluded_ids:
                continue
            kickoff_dt = datetime.fromisoformat(parsed.kickoff.replace("Z", "+00:00"))
            if cutoff_dt is not None and not kickoff_dt < cutoff_dt:
                continue
            if parsed.status not in {"FT", "AET", "PEN"}:
                continue
            finished.append(
                {
                    "id": parsed.external_id,
                    "date": parsed.kickoff,
                    "home_team": parsed.home_team_name,
                    "away_team": parsed.away_team_name,
                    "home_participant_id": parsed.home_participant_id,
                    "away_participant_id": parsed.away_participant_id,
                    "competition_id": parsed.competition_id,
                    "season_id": parsed.season_id,
                }
            )

        finished.sort(key=lambda item: item["date"], reverse=True)
        filtered = finished[:last_n]
        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_team_last_fixtures",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version="api-football-team-fixtures-v1",
                    source_event_refs=namespaced_source_refs(
                        self.api_name, [item["id"] for item in filtered]
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
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=filtered,
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            retry_count=result.retry_count,
            quota_metadata=result.quota_metadata,
            parser_diagnostics={
                "raw_count": len(raw_items),
                "accepted_count": len(filtered),
                "rejected_count": max(len(raw_items) - len(finished), 0),
            },
        )

    def get_fixture_stats_result(
        self,
        fixture_id: str,
        home_participant_id: str = "",
        away_participant_id: str = "",
    ) -> SourceOperationResult[list[APIMatchStats]]:
        """GET fixture stats with exact provider-side attribution."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )
        requested_home = str(home_participant_id).strip()
        requested_away = str(away_participant_id).strip()
        if not requested_home or not requested_away or requested_home == requested_away:
            return SourceOperationResult(
                status=SourceResultStatus.AMBIGUOUS,
                error_code="participant_side_map_missing",
            )

        result = self._request_with_evidence(
            endpoint="/fixtures/statistics",
            params={"fixture": fixture_id},
            operation="get_fixture_stats",
            source_event_id=fixture_id,
            expects_response_list=True,
        )
        if result.status is not SourceResultStatus.SUCCESS or result.value is None:
            return result

        raw_items = result.value.get("response", [])
        if not raw_items:
            return SourceOperationResult(
                status=SourceResultStatus.SUCCESS,
                value=[],
                http_status=result.http_status,
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        seen_ids: set[str] = set()
        for team_data in raw_items:
            team_info = team_data.get("team", {})
            team_id = str(team_info.get("id", "")).strip()
            team_name = str(team_info.get("name", "")).strip()
            if team_id == requested_home:
                side = "home"
            elif team_id == requested_away:
                side = "away"
            else:
                return SourceOperationResult(
                    status=SourceResultStatus.SCHEMA_ERROR,
                    http_status=result.http_status,
                    error_code="unexpected_participant_id",
                    evidence_refs=result.evidence_refs,
                    retry_count=result.retry_count,
                    quota_metadata=result.quota_metadata,
                )
            if side in teams or team_id in seen_ids or not team_name:
                return SourceOperationResult(
                    status=SourceResultStatus.SCHEMA_ERROR,
                    http_status=result.http_status,
                    error_code="duplicate_or_blank_participant",
                    evidence_refs=result.evidence_refs,
                    retry_count=result.retry_count,
                    quota_metadata=result.quota_metadata,
                )
            teams[side] = team_name
            seen_ids.add(team_id)

            for stat_entry in team_data.get("statistics", []):
                normalized_key = STAT_TYPE_MAP.get(stat_entry.get("type", ""))
                raw_value = stat_entry.get("value")
                if not normalized_key or raw_value is None:
                    continue
                if isinstance(raw_value, str):
                    cleaned = raw_value.replace("%", "").strip()
                    if not cleaned:
                        continue
                    try:
                        value = float(cleaned)
                    except ValueError:
                        continue
                elif isinstance(raw_value, (int, float)):
                    value = float(raw_value)
                else:
                    continue
                if side in stats.setdefault(normalized_key, {}):
                    return SourceOperationResult(
                        status=SourceResultStatus.SCHEMA_ERROR,
                        http_status=result.http_status,
                        error_code="duplicate_metric_for_side",
                        evidence_refs=result.evidence_refs,
                        retry_count=result.retry_count,
                        quota_metadata=result.quota_metadata,
                    )
                stats[normalized_key][side] = value

        if teams.get("home") is None or teams.get("away") is None:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                error_code="participants_incomplete",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
            )

        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_fixture_stats",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version="api-football-fixture-stats-v1",
                    source_event_refs=namespaced_source_refs(self.api_name, [fixture_id]),
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
                )

        return SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[
                APIMatchStats(
                    external_id=fixture_id,
                    source=self.api_name,
                    sport="football",
                    home_team_name=teams["home"],
                    away_team_name=teams["away"],
                    stats=stats,
                    home_participant_id=requested_home,
                    away_participant_id=requested_away,
                )
            ],
            http_status=result.http_status,
            evidence_refs=result.evidence_refs,
            bundle_id=bundle_id,
            retry_count=result.retry_count,
            quota_metadata=result.quota_metadata,
            parser_diagnostics={
                "raw_count": len(raw_items),
                "accepted_count": 1,
                "rejected_count": 0,
            },
        )

    def get_fixtures_result(self, date: str) -> SourceOperationResult:
        """GET /fixtures?date=YYYY-MM-DD with evidence capture."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        result = self._request_with_evidence(
            endpoint="/fixtures",
            params={"date": date},
            operation="get_fixtures",
            source_event_id=None,
            expects_response_list=True,
        )

        if result.status != SourceResultStatus.SUCCESS or result.value is None:
            return result

        raw_items = result.value.get("response", [])
        fixtures: list[APIFixture] = []
        rejected_count = 0

        for item in raw_items:
            parsed = self._parse_fixture_item(item)
            if parsed is None:
                rejected_count += 1
                continue
            fixtures.append(parsed)

        diagnostics = {
            "raw_count": len(raw_items),
            "accepted_count": len(fixtures),
            "rejected_count": rejected_count,
        }
        if raw_items and not fixtures:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                retryable=False,
                error_code="no_valid_fixture_rows",
                evidence_refs=result.evidence_refs,
                retry_count=result.retry_count,
                quota_metadata=result.quota_metadata,
                parser_diagnostics=diagnostics,
            )

        source_refs = namespaced_source_refs(
            self.api_name, [fixture.external_id for fixture in fixtures]
        )
        bundle_id = ""
        if result.evidence_refs:
            try:
                bundle_id, _ = write_source_operation_bundle(
                    registered_source_key=self.api_name,
                    operation_name="get_fixtures",
                    request_identity=result.evidence_refs[0].request_identity,
                    parser_version=FIXTURES_PARSER_VERSION,
                    source_event_refs=source_refs,
                    evidence_refs=result.evidence_refs,
                )
            except Exception:
                return SourceOperationResult(
                    status=SourceResultStatus.EVIDENCE_ERROR,
                    http_status=result.http_status,
                    retryable=False,
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

    def _parse_fixture_item(self, item: dict) -> APIFixture | None:
        fix = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})

        external_id = str(fix.get("id", "")).strip()
        home_id = str(home.get("id", "")).strip()
        away_id = str(away.get("id", "")).strip()
        home_name = str(home.get("name", "")).strip()
        away_name = str(away.get("name", "")).strip()
        kickoff = str(fix.get("date", "")).strip()
        competition_name = str(league.get("name", "")).strip()
        competition_id = str(league.get("id", "")).strip()
        season_id = str(league.get("season", "")).strip()

        if not external_id or not home_id or not away_id or home_id == away_id:
            return None
        if (
            not home_name
            or not away_name
            or home_name == "Unknown"
            or away_name == "Unknown"
        ):
            return None
        if not kickoff or not competition_name:
            return None
        try:
            parsed = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return None

        return APIFixture(
            external_id=external_id,
            source=self.api_name,
            sport="football",
            competition_name=competition_name,
            home_team_name=home_name,
            away_team_name=away_name,
            kickoff=kickoff,
            status=str(fix.get("status", {}).get("short", "NS") or "NS"),
            home_participant_id=home_id,
            away_participant_id=away_id,
            competition_id=competition_id,
            season_id=season_id,
        )
