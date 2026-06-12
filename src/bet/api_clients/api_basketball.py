"""API-Basketball v1 client — adapted for bet.db.models.

Returns APIFixture and APIMatchStats objects.
"""

import logging
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

logger = logging.getLogger(__name__)
FIXTURES_PARSER_VERSION = "api-basketball-fixtures-v2"


class APIBasketballClient(APISportsClient):
    """API-Basketball v1 — per-game stats for NBA, Euroleague, and 50+ leagues."""

    _SHARES_FOOTBALL_KEY = True

    @staticmethod
    def _season_string(now: datetime | None = None) -> str:
        now = now or datetime.now()
        season_start = now.year if now.month >= 10 else now.year - 1
        return f"{season_start}-{season_start + 1}"

    def _get_game_side_map(self, game_id: str) -> dict[str, str]:
        try:
            data = self._request("/games", params={"id": game_id})
        except Exception:
            return {}

        response = data.get("response", [])
        if not response:
            return {}

        teams = response[0].get("teams", {})
        side_map: dict[str, str] = {}
        for side in ("home", "away"):
            team = teams.get(side, {})
            team_id = team.get("id")
            if team_id is not None:
                side_map[str(team_id)] = side
        return side_map

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="api-basketball",
            base_url="https://v1.basketball.api-sports.io",
            rate_limiter=rate_limiter,
        )

    def get_fixtures(self, date: str) -> list[APIFixture]:
        """GET /games?date=YYYY-MM-DD → list of APIFixture."""
        if not self._check_api_key():
            return []

        cache_key = f"basketball/fixtures/{date}"
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
        for item in data.get("response", []):
            teams = item.get("teams", {})
            league = item.get("league", {})
            status_raw = item.get("status")
            if isinstance(status_raw, dict):
                status = status_raw.get("short", "NS")
            else:
                status = str(status_raw or "NS")

            fixture = APIFixture(
                external_id=str(item.get("id", "")),
                source=self.api_name,
                sport="basketball",
                competition_name=league.get("name", ""),
                home_team_name=teams.get("home", {}).get("name", ""),
                away_team_name=teams.get("away", {}).get("name", ""),
                kickoff=item.get("date", ""),
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

    def get_fixture_stats(self, game_id: str) -> list[APIMatchStats]:
        """GET /statistics?id={game_id} → list of APIMatchStats."""
        if not self._check_api_key():
            return []

        cache_key = f"basketball/fixture_stats/{game_id}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return [APIMatchStats(**ms) for ms in cached.get("stats", [])]

        try:
            data = self._request("/statistics", params={"id": game_id})
        except Exception as e:
            print(f"[{self.api_name}] Error fetching stats for game {game_id}: {e}")
            return []

        response = data.get("response", [])
        if len(response) < 2:
            return []

        side_map = self._get_game_side_map(game_id)

        stats: dict[str, dict[str, float]] = {}
        teams: dict[str, str] = {}
        used_order_fallback = False
        for team_data in response:
            team_info = team_data.get("team", {})
            team_name = team_info.get("name", "")
            team_id = team_info.get("id")
            side = side_map.get(str(team_id))
            if side is None:
                side = "home" if not teams else "away"
                used_order_fallback = True
            teams[side] = team_name

            raw_stats = team_data.get("statistics", [])
            stat_dict: dict = {}
            if isinstance(raw_stats, list):
                for entry in raw_stats:
                    if isinstance(entry, dict):
                        stat_dict.update(entry)
            elif isinstance(raw_stats, dict):
                stat_dict = raw_stats

            stat_mapping = {
                "points": ["points", "totalPoints"],
                "rebounds": ["totalRebounds", "rebounds"],
                "assists": ["assists"],
                "steals": ["steals"],
                "blocks": ["blocks"],
                "turnovers": ["turnovers"],
                "fg_pct": ["fieldGoalsPercentage", "fgPct"],
                "three_pct": ["threePointsPercentage", "threePct"],
                "ft_pct": ["freeThrowsPercentage", "ftPct"],
                "offensive_rebounds": ["offRebounds", "offensiveRebounds"],
                "defensive_rebounds": ["defRebounds", "defensiveRebounds"],
                "fast_break_points": ["fastBreakPoints"],
                "points_in_paint": ["pointsInPaint"],
                "fouls": ["personalFouls", "fouls"],
            }

            for norm_key, api_keys in stat_mapping.items():
                value = None
                for api_key in api_keys:
                    if api_key in stat_dict and stat_dict[api_key] is not None:
                        value = stat_dict[api_key]
                        break
                if value is not None:
                    if isinstance(value, str):
                        try:
                            value = float(value.replace("%", "").strip())
                        except (ValueError, AttributeError):
                            value = 0
                    if norm_key not in stats:
                        stats[norm_key] = {}
                    stats[norm_key][side] = float(value)

        if not teams.get("home") or not teams.get("away"):
            return []

        if used_order_fallback:
            logger.warning(
                (
                    "[api-basketball] side map unavailable for game %s — "
                    "assigned home/away by response order"
                ),
                game_id,
            )

        result = [
            APIMatchStats(
                external_id=game_id,
                source=self.api_name,
                sport="basketball",
                home_team_name=teams["home"],
                away_team_name=teams["away"],
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
        """Search for a team by name → return API team ID."""
        if not self._check_api_key():
            return None
        safe_name = re.sub(r"[^a-z0-9_]", "_", team_name.lower())
        cache_key = f"basketball/team_search/{safe_name}"
        cached = self._check_cache(cache_key, ttl_hours=168)
        if cached:
            return cached.get("team_id")
        try:
            data = self._request("/teams", params={"search": team_name})
            results = data.get("response", [])
            if results:
                tid = str(results[0].get("id", ""))
                self._save_cache(cache_key, {"team_id": tid})
                return tid
        except Exception:
            pass
        return None

    def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
        """Fetch the last N finished games for a team using the current season."""
        if not self._check_api_key():
            return []
        cache_key = f"basketball/team_fixtures/{team_id}"
        cached = self._check_cache(cache_key, ttl_hours=12)
        if cached:
            return cached.get("fixtures", [])
        try:
            season_str = self._season_string()

            data = self._request(
                "/games",
                params={"team": team_id, "season": season_str},
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
                if short in ("FT", "AOT") or long_val == "Game Finished":
                    finished.append(g)
            finished.sort(
                key=lambda g: g.get("date", ""),
                reverse=True,
            )
            result = [{"id": g.get("id")} for g in finished[:last_n]]
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
        params = {"team": team_id, "season": season_id or self._season_string()}
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
            if parsed.status not in {"FT", "AOT"}:
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
                    parser_version="api-basketball-team-fixtures-v1",
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
            parser_diagnostics={
                "raw_count": len(raw_items),
                "accepted_count": len(filtered),
                "rejected_count": max(len(raw_items) - len(finished), 0),
            },
        )

    def get_fixture_stats_result(
        self,
        game_id: str,
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
            endpoint="/statistics",
            params={"id": game_id},
            operation="get_fixture_stats",
            source_event_id=game_id,
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
        stat_mapping = {
            "points": ["points", "totalPoints"],
            "rebounds": ["totalRebounds", "rebounds"],
            "assists": ["assists"],
            "steals": ["steals"],
            "blocks": ["blocks"],
            "turnovers": ["turnovers"],
            "fg_pct": ["fieldGoalsPercentage", "fgPct"],
            "three_pct": ["threePointsPercentage", "threePct"],
            "ft_pct": ["freeThrowsPercentage", "ftPct"],
            "offensive_rebounds": ["offRebounds", "offensiveRebounds"],
            "defensive_rebounds": ["defRebounds", "defensiveRebounds"],
            "fast_break_points": ["fastBreakPoints"],
            "points_in_paint": ["pointsInPaint"],
            "fouls": ["personalFouls", "fouls"],
        }
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
            if side in teams or not team_name:
                return SourceOperationResult(
                    status=SourceResultStatus.SCHEMA_ERROR,
                    http_status=result.http_status,
                    error_code="duplicate_or_blank_participant",
                    evidence_refs=result.evidence_refs,
                    retry_count=result.retry_count,
                    quota_metadata=result.quota_metadata,
                )
            teams[side] = team_name
            raw_stats = team_data.get("statistics", [])
            stat_dict: dict = {}
            if isinstance(raw_stats, list):
                for entry in raw_stats:
                    if isinstance(entry, dict):
                        stat_dict.update(entry)
            elif isinstance(raw_stats, dict):
                stat_dict = raw_stats
            for norm_key, api_keys in stat_mapping.items():
                value = None
                for api_key in api_keys:
                    if api_key in stat_dict and stat_dict[api_key] is not None:
                        value = stat_dict[api_key]
                        break
                if value is None:
                    continue
                if isinstance(value, str):
                    cleaned = value.replace("%", "").strip()
                    if not cleaned:
                        continue
                    try:
                        value = float(cleaned)
                    except ValueError:
                        continue
                elif isinstance(value, (int, float)):
                    value = float(value)
                else:
                    continue
                if side in stats.setdefault(norm_key, {}):
                    return SourceOperationResult(
                        status=SourceResultStatus.SCHEMA_ERROR,
                        http_status=result.http_status,
                        error_code="duplicate_metric_for_side",
                        evidence_refs=result.evidence_refs,
                        retry_count=result.retry_count,
                        quota_metadata=result.quota_metadata,
                    )
                stats[norm_key][side] = float(value)
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
                    parser_version="api-basketball-fixture-stats-v1",
                    source_event_refs=namespaced_source_refs(self.api_name, [game_id]),
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
                    external_id=game_id,
                    source=self.api_name,
                    sport="basketball",
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
            parser_diagnostics={"raw_count": len(raw_items), "accepted_count": 1, "rejected_count": 0},
        )

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

    def _parse_fixture_item(self, item: dict) -> APIFixture | None:
        teams = item.get("teams", {})
        league = item.get("league", {})
        home = teams.get("home", {})
        away = teams.get("away", {})
        status_raw = item.get("status")
        if isinstance(status_raw, dict):
            status = status_raw.get("short", "NS")
        else:
            status = str(status_raw or "NS")

        external_id = str(item.get("id", "")).strip()
        home_id = str(home.get("id", "")).strip()
        away_id = str(away.get("id", "")).strip()
        home_name = str(home.get("name", "")).strip()
        away_name = str(away.get("name", "")).strip()
        kickoff = str(item.get("date", "")).strip()
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
            sport="basketball",
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
