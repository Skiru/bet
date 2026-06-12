"""API-Volleyball v1 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats objects.
"""

import re
from dataclasses import asdict
from datetime import datetime

from bet.integration.evidence import (
    namespaced_source_refs,
    write_source_operation_bundle,
)

from .api_football import APIFixture, APIMatchStats
from .base_client import APISportsClient, SourceOperationResult, SourceResultStatus
from .rate_limiter import RateLimiter

STAT_TYPE_MAP = {
    "points": "points",
    "total_points": "total_points",
    "aces": "aces",
    "blocks": "blocks",
    "attack_pct": "hitting_pct",
    "hitting_pct": "hitting_pct",
    "sets_won": "sets_won",
    "errors": "errors",
    "service_errors": "errors",
}

FIXTURES_PARSER_VERSION = "api-volleyball-fixtures-v2"


def _normalize_stat_type(raw_stat_type: str) -> str:
    normalized = str(raw_stat_type or "").lower().replace("%", " pct ")
    normalized = normalized.replace("percentage", "pct")
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


class APIVolleyballClient(APISportsClient):
    """Volleyball API client using api-sports.io unified platform."""

    _SHARES_FOOTBALL_KEY = True

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-volleyball",
            base_url="https://v1.volleyball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """GET /games?date=YYYY-MM-DD → list of APIFixture."""
        if not self._check_api_key():
            return []

        cache_key = f"volleyball/fixtures/{date}"
        cached = self._check_cache(cache_key, ttl_hours=6)
        if cached:
            return [
                APIFixture(**f)
                for f in cached.get("fixtures", [])
                if isinstance(f, dict) and "external_id" in f
            ]

        try:
            data = self._request("/games", params={"date": date})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching fixtures for {date}: {e}")
            return []

        fixtures = []
        for game in data.get("response", []):
            teams = game.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})
            league = game.get("league", {})

            status_raw = game.get("status")
            if isinstance(status_raw, dict):
                status = status_raw.get("long", "scheduled")
            else:
                status = str(status_raw or "NS")

            fixture = APIFixture(
                external_id=str(game.get("id", "")),
                source=self.api_name,
                sport="volleyball",
                competition_name=league.get("name", "Unknown"),
                home_team_name=home.get("name", "Unknown"),
                away_team_name=away.get("name", "Unknown"),
                kickoff=game.get("date", ""),
                status=status,
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
        """GET /games/statistics?id={fixture_id} → list of APIMatchStats."""
        if not self._check_api_key():
            return []

        cache_key = f"volleyball/fixture_stats/{fixture_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/games/statistics", params={"id": fixture_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for {fixture_id}: {e}")
            return []

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        for entry in data.get("response", []):
            team_info = entry.get("team", {})
            if team_info:
                side = "home" if not teams else "away"
                teams[side] = team_info.get("name", "")

            for stat in entry.get("statistics", []):
                stat_type = _normalize_stat_type(stat.get("type", ""))
                mapped = STAT_TYPE_MAP.get(stat_type)
                if mapped:
                    home_val = stat.get("home", 0)
                    away_val = stat.get("away", 0)
                    if home_val is not None and away_val is not None:
                        stats[mapped] = {
                            "home": float(home_val),
                            "away": float(away_val),
                        }

        if not stats or not teams.get("home"):
            return []

        result = [
            APIMatchStats(
                external_id=fixture_id,
                source=self.api_name,
                sport="volleyball",
                home_team_name=teams.get("home", ""),
                away_team_name=teams.get("away", ""),
                stats=stats,
            )
        ]

        self._save_cache(cache_key, {"stats": [asdict(ms) for ms in result]})

        return result

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        """Get head-to-head history."""
        if not self._check_api_key():
            return []
        try:
            data = self._request(
                "/games",
                params={"h2h": f"{team1_id}-{team2_id}", "last": str(last_n)},
            )
            return data.get("response", [])
        except Exception:
            return []

    def get_event_fixture_result(
        self, date: str, event_id: str
    ) -> SourceOperationResult[APIFixture]:
        del date
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )
        result = self._request_with_evidence(
            endpoint="/games",
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
        exact = [fixture for fixture in fixtures if fixture.external_id == str(event_id).strip()]
        if len(exact) != 1:
            return SourceOperationResult(
                status=SourceResultStatus.NOT_FOUND if not exact else SourceResultStatus.AMBIGUOUS,
                http_status=result.http_status,
                error_code="event_fixture_missing",
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
        """Search for a team by name → return API team ID.

        Prefers men's teams (excludes names ending in ' W') for ambiguous searches.
        """
        if not self._check_api_key():
            return None
        cache_key = f"volleyball/team_search/{team_name.lower().replace(' ', '_')}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")
        try:
            data = self._request("/teams", params={"search": team_name})
            results = data.get("response", [])
            if results:
                best = None
                for r in results:
                    name = r.get("name", "")
                    if name.lower() == team_name.lower():
                        best = r
                        break
                    if not name.endswith(" W") and best is None:
                        best = r
                if best is None:
                    best = results[0]
                tid = str(best.get("id", ""))
                self._save_cache(cache_key, {"team_id": tid})
                return tid
        except Exception:
            pass
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """GET /games?team={id}&season=2024 → filter to last N finished."""
        if not self._check_api_key():
            return []
        cache_key = f"volleyball/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])
        try:
            data = self._request(
                "/games",
                params={"team": team_id, "season": "2024"},
            )
            games = data.get("response", [])
            finished = []
            for g in games:
                status = g.get("status")
                if isinstance(status, dict):
                    short = status.get("short", "")
                    long_val = status.get("long", "")
                else:
                    short = str(status or "")
                    long_val = ""
                if short == "FT" or "finished" in long_val.lower():
                    finished.append(g)
            finished.sort(
                key=lambda g: g.get("date", ""),
                reverse=True,
            )
            result = []
            for g in finished[:last_n]:
                teams = g.get("teams", {})
                result.append(
                    {
                        "id": str(g.get("id", "")),
                        "date": g.get("date", ""),
                        "home_team": teams.get("home", {}).get("name", ""),
                        "away_team": teams.get("away", {}).get("name", ""),
                    }
                )
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
        cutoff_dt = datetime.fromisoformat(analysis_cutoff_at.replace("Z", "+00:00")) if analysis_cutoff_at else None
        params = {"team": team_id, "season": season_id or "2024"}
        if competition_id:
            params["league"] = competition_id
        result = self._request_with_evidence(
            endpoint="/games",
            params=params,
            operation="get_team_last_fixtures",
            source_event_id=None,
            expects_response_list=True,
        )
        if result.status is not SourceResultStatus.SUCCESS or result.value is None:
            return result
        raw_items = result.value.get("response", [])
        finished: list[dict] = []
        for item in raw_items:
            parsed = self._parse_fixture_item(item)
            if parsed is None or parsed.external_id in excluded_ids:
                continue
            kickoff_dt = datetime.fromisoformat(parsed.kickoff.replace("Z", "+00:00"))
            if cutoff_dt is not None and not kickoff_dt < cutoff_dt:
                continue
            status_lower = parsed.status.lower()
            if parsed.status != "FT" and "finished" not in status_lower:
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
                    parser_version="api-volleyball-team-fixtures-v1",
                    source_event_refs=namespaced_source_refs(self.api_name, [item["id"] for item in filtered]),
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
            parser_diagnostics={"raw_count": len(raw_items), "accepted_count": len(filtered), "rejected_count": max(len(raw_items) - len(finished), 0)},
        )

    def get_fixture_stats_result(
        self,
        fixture_id: str,
        home_participant_id: str = "",
        away_participant_id: str = "",
    ) -> SourceOperationResult[list[APIMatchStats]]:
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
            endpoint="/games/statistics",
            params={"id": fixture_id},
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
        participant_ids: set[str] = set()
        for entry in raw_items:
            team_info = entry.get("team", {})
            team_id = str(team_info.get("id", "")).strip()
            if team_id:
                participant_ids.add(team_id)
            for stat in entry.get("statistics", []):
                stat_type = _normalize_stat_type(stat.get("type", ""))
                mapped = STAT_TYPE_MAP.get(stat_type)
                if not mapped:
                    continue
                home_val = stat.get("home")
                away_val = stat.get("away")
                side_values: dict[str, float] = {}
                for side, raw_value in (("home", home_val), ("away", away_val)):
                    if raw_value is None:
                        continue
                    if isinstance(raw_value, str):
                        cleaned = raw_value.replace("%", "").strip()
                        if not cleaned:
                            continue
                        try:
                            side_values[side] = float(cleaned)
                        except ValueError:
                            continue
                    elif isinstance(raw_value, (int, float)):
                        side_values[side] = float(raw_value)
                if not side_values:
                    continue
                if mapped in stats:
                    return SourceOperationResult(
                        status=SourceResultStatus.SCHEMA_ERROR,
                        http_status=result.http_status,
                        error_code="duplicate_metric_for_side",
                        evidence_refs=result.evidence_refs,
                        retry_count=result.retry_count,
                        quota_metadata=result.quota_metadata,
                    )
                stats[mapped] = side_values
        if participant_ids and participant_ids != {requested_home, requested_away}:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                http_status=result.http_status,
                error_code="unexpected_participant_id",
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
                    parser_version="api-volleyball-fixture-stats-v1",
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
                    sport="volleyball",
                    home_team_name="",
                    away_team_name="",
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
            parser_diagnostics={"raw_count": len(raw_items), "accepted_count": 1, "rejected_count": 0},
        )

    def get_match_stats(self, game_id: str) -> dict[str, float] | None:
        """GET /games?id={game_id} → per-match stat dict from scores/periods."""
        if not self._check_api_key():
            return None

        cache_key = f"volleyball/match_stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("stats")

        try:
            data = self._request("/games", params={"id": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching match {game_id}: {e}")
            return None

        games = data.get("response", [])
        if not games:
            return None

        game = games[0]
        status = game.get("status", {})
        if isinstance(status, dict) and status.get("short") != "FT":
            return None

        scores = game.get("scores", {})
        periods = game.get("periods", {})

        if not scores or not periods:
            return None

        home_points = 0
        away_points = 0
        sets_played = 0
        for period_name in ("first", "second", "third", "fourth", "fifth"):
            period = periods.get(period_name, {})
            if period and period.get("home") is not None:
                home_points += int(period["home"])
                away_points += int(period["away"])
                sets_played += 1

        match_stats: dict[str, float] = {
            "total_points": float(home_points + away_points),
            "sets_won": float(max(scores.get("home", 0), scores.get("away", 0))),
            "sets_played": float(sets_played),
            "points_home": float(home_points),
            "points_away": float(away_points),
        }

        self._save_cache(cache_key, {"stats": match_stats})
        return match_stats

    def get_team_l10_stats(self, team_name: str) -> dict[str, list[float]] | None:
        """Build L10 per-match stat arrays for a team."""
        team_id = self.resolve_team_id(team_name)
        if not team_id:
            return None

        fixtures = self.get_team_last_fixtures(team_id, last_n=10)
        if not fixtures:
            return None

        l10: dict[str, list[float]] = {}
        for fix in fixtures:
            game_id = str(fix.get("id", ""))
            if not game_id:
                continue
            stats = self.get_match_stats(game_id)
            if not stats:
                continue
            for key, val in stats.items():
                l10.setdefault(key, []).append(val)

        return l10 if l10 else None

    def get_fixtures_result(self, date: str) -> SourceOperationResult:
        """GET /games?date=YYYY-MM-DD with evidence capture."""
        if not self._check_api_key():
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                error_code="missing_api_key",
            )

        result = self._request_with_evidence(
            endpoint="/games",
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

    def _parse_fixture_item(self, game: dict) -> APIFixture | None:
        teams = game.get("teams", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        league = game.get("league", {})
        status_raw = game.get("status")
        if isinstance(status_raw, dict):
            status = status_raw.get("long", "scheduled")
        else:
            status = str(status_raw or "NS")

        external_id = str(game.get("id", "")).strip()
        home_id = str(home.get("id", "")).strip()
        away_id = str(away.get("id", "")).strip()
        home_name = str(home.get("name", "")).strip()
        away_name = str(away.get("name", "")).strip()
        kickoff = str(game.get("date", "")).strip()
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
            sport="volleyball",
            competition_name=competition_name,
            home_team_name=home_name,
            away_team_name=away_name,
            kickoff=kickoff,
            status=status,
            home_participant_id=home_id,
            away_participant_id=away_id,
            competition_id=competition_id,
            season_id=season_id,
        )
