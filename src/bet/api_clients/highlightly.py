from __future__ import annotations

import json
import os
from typing import Any

import requests

from bet.integration.evidence import namespaced_source_refs
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

from .base_client import BaseAPIClient
from .evidence_request import EvidenceRequestMixin
from .env import get_env
from .rate_limiter import RateLimiter

LEAGUE_DISCOVERY_PARSER_VERSION = "highlightly-league-discovery-v1"
MATCH_DISCOVERY_PARSER_VERSION = "highlightly-match-discovery-v1"
CURRENT_FORM_PARSER_VERSION = "highlightly-current-form-v1"
H2H_PARSER_VERSION = "highlightly-h2h-v1"
STATISTICS_PARSER_VERSION = "highlightly-statistics-v1"

STAT_NAME_MAP = {
    "Expected Goals": ("expected_goals", "xg"),
    "Big Chances Created": ("big_chances_created", "count"),
    "Free Kicks": ("free_kicks", "count"),
    "Throw-Ins": ("throw_ins", "count"),
    "Goal Kicks": ("goal_kicks", "count"),
    "Shots accuracy": ("shots_accuracy", "ratio"),
    "Shots on target": ("shots_on_goal", "count"),
    "Shots off target": ("shots_off_target", "count"),
    "Blocked shots": ("blocked_shots", "count"),
    "Shots within penalty area": ("shots_within_penalty_area", "count"),
    "Shots outside penalty area": ("shots_outside_penalty_area", "count"),
    "Fouls": ("fouls", "count"),
    "Corners": ("corners", "count"),
    "Offsides": ("offsides", "count"),
    "Possession": ("possession", "ratio"),
    "Yellow cards": ("yellow_cards", "count"),
    # "Red cards" is present in live /statistics payloads (verified 2026-08-25
    # against soccer.highlightly.net) but was previously unmapped, so it fell
    # through to unknown_metrics. Red cards are a real market and correlate
    # with total cards, so they are mapped rather than discarded.
    "Red cards": ("red_cards", "count"),
    "Attacks": ("attacks", "count"),
    "Goalkeeper saves": ("goalkeeper_saves", "count"),
    "Total passes": ("total_passes", "count"),
    "Successful passes": ("successful_passes", "count"),
    "Failed passes": ("failed_passes", "count"),
}

# Formerly ["Red cards"]; that metric is now mapped in STAT_NAME_MAP above,
# so no target metric is knowingly dropped by this parser.
MISSING_TARGET_METRICS: list[str] = []


class HighlightlyClient(EvidenceRequestMixin, BaseAPIClient):
    """Highlightly client limited to the proven eng.1 completed-season scope."""

    def __init__(self, rate_limiter: RateLimiter):
        super().__init__(
            api_name="highlightly",
            base_url="https://soccer.highlightly.net",
            rate_limiter=rate_limiter,
        )

    def _load_api_key(self) -> str | None:
        for alias in ("HIGHLIGHTLY_API_KEY", "RAPIDAPI_KEY"):
            value = get_env(alias)
            if value:
                return value
        return super()._load_api_key()

    def _build_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-rapidapi-key"] = self.api_key
        return headers

    @staticmethod
    def _extract_quota_metadata(
        headers: dict[str, Any] | None,
    ) -> dict[str, int | str | None]:
        if not headers:
            return {}
        normalized = {str(key).lower(): value for key, value in headers.items()}
        header_map = {
            "x-ratelimit-limit": "minute_limit",
            "x-ratelimit-remaining": "minute_remaining",
            "x-ratelimit-requests-limit": "minute_limit",
            "x-ratelimit-requests-remaining": "minute_remaining",
            "x-ratelimit-day-limit": "daily_limit",
            "x-ratelimit-day-remaining": "daily_remaining",
        }
        metadata: dict[str, int | str | None] = {}
        for header_name, field_name in header_map.items():
            if header_name not in normalized:
                continue
            raw_value = normalized[header_name]
            try:
                metadata[field_name] = int(str(raw_value))
            except (TypeError, ValueError):
                metadata[field_name] = str(raw_value)
        return metadata

    @staticmethod
    def _classify_provider_payload_error(
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        errors = payload.get("errors")
        if errors in (None, {}, [], ""):
            return None

        if isinstance(errors, dict):
            flattened = " | ".join(
                f"{key}:{value}" for key, value in sorted(errors.items())
            )
        elif isinstance(errors, list):
            flattened = " | ".join(str(item) for item in errors)
        else:
            flattened = str(errors)

        lowered = flattened.lower()
        if "rate limit" in lowered or "too many" in lowered:
            return {
                "status": SourceResultStatus.RATE_LIMITED,
                "error_code": "provider_rate_limited",
            }
        if any(
            token in lowered
            for token in ("free plans", "subscription", "access denied", "plan")
        ):
            return {
                "status": SourceResultStatus.PLAN_RESTRICTED,
                "error_code": "provider_plan_restricted",
            }
        if any(
            token in lowered
            for token in ("invalid key", "unauthorized", "forbidden", "authentication")
        ):
            return {
                "status": SourceResultStatus.AUTHENTICATION_ERROR,
                "error_code": "provider_authentication_error",
            }
        return {
            "status": SourceResultStatus.UPSTREAM_ERROR,
            "error_code": "provider_error_payload",
        }

    def get_fixtures(self, date: str) -> list:
        return []

    def get_fixture_stats(self, fixture_id: str) -> list:
        return []

    def get_h2h(self, team1_id: str, team2_id: str, last_n: int = 10) -> list[dict]:
        result = self.get_head_to_head_result(team1_id, team2_id)
        if result.status is not SourceResultStatus.SUCCESS:
            return []
        payload = result.value or {}
        return list(payload.get("matches") or [])[:last_n]

    def discover_league_result(
        self,
        league_name: str,
        country_name: str,
        season: int,
    ) -> SourceOperationResult[dict[str, Any]]:
        result = self._request_with_evidence(
            endpoint="/leagues",
            params={
                "leagueName": league_name,
                "countryName": country_name,
                "season": season,
            },
            operation="league_discovery",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")

        rows = payload.get("data")
        if not isinstance(rows, list):
            return self._schema_error(result, "data_not_list")

        normalized = []
        rejected_count = 0
        for row in rows:
            if not isinstance(row, dict):
                rejected_count += 1
                continue
            league_id = row.get("id")
            country = row.get("country") if isinstance(row.get("country"), dict) else {}
            normalized.append(
                {
                    "provider_league_id": str(league_id),
                    "league_name": row.get("name"),
                    "country_name": country.get("name"),
                    "country_code": country.get("code"),
                    "season_values": [
                        item.get("season")
                        for item in row.get("seasons", [])
                        if isinstance(item, dict) and item.get("season") is not None
                    ],
                }
            )

        return self._bundle_result(
            result=result,
            parser_version=LEAGUE_DISCOVERY_PARSER_VERSION,
            operation_name="league_discovery",
            source_event_refs=namespaced_source_refs(self.api_name, []),
            value={
                "rows": normalized,
                "accepted_count": len(normalized),
                "rejected_count": rejected_count,
                "plan": payload.get("plan"),
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(normalized),
                "rejected_count": rejected_count,
            },
        )

    def discover_matches_result(
        self,
        league_id: str | int,
        season: int,
        limit: int = 20,
    ) -> SourceOperationResult[dict[str, Any]]:
        result = self._request_with_evidence(
            endpoint="/matches",
            params={"leagueId": str(league_id), "season": season, "limit": limit},
            operation="match_discovery",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, dict):
            return self._schema_error(result, "payload_not_object")

        rows = payload.get("data")
        if not isinstance(rows, list):
            return self._schema_error(result, "data_not_list")

        normalized = []
        rejected_count = 0
        for row in rows:
            match_row = self._normalize_match_row(
                row,
                requested_team_id=None,
                source_order=len(normalized) + 1,
            )
            if match_row is None:
                rejected_count += 1
                continue
            normalized.append(match_row)

        return self._bundle_result(
            result=result,
            parser_version=MATCH_DISCOVERY_PARSER_VERSION,
            operation_name="match_discovery",
            source_event_refs=namespaced_source_refs(
                self.api_name,
                [item["provider_match_id"] for item in normalized],
            ),
            value={
                "rows": normalized,
                "accepted_count": len(normalized),
                "rejected_count": rejected_count,
                "plan": payload.get("plan"),
            },
            parser_diagnostics={
                "raw_count": len(rows),
                "accepted_count": len(normalized),
                "rejected_count": rejected_count,
            },
        )

    def get_last_five_games_result(
        self,
        team_id: str | int,
        requested_sample_size: int = 5,
    ) -> SourceOperationResult[dict[str, Any]]:
        result = self._request_with_evidence(
            endpoint="/last-five-games",
            params={"teamId": str(team_id)},
            operation="current_form",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, list):
            return self._schema_error(result, "payload_not_list")

        matches = []
        rejected_count = 0
        for index, row in enumerate(payload, start=1):
            match_row = self._normalize_match_row(
                row,
                requested_team_id=str(team_id),
                source_order=index,
            )
            if match_row is None:
                rejected_count += 1
                continue
            matches.append(match_row)

        coverage_status = "COMPLETE"
        if not matches:
            coverage_status = "EMPTY"
        elif len(matches) < requested_sample_size:
            coverage_status = "PARTIAL"

        return self._bundle_result(
            result=result,
            parser_version=CURRENT_FORM_PARSER_VERSION,
            operation_name="current_form",
            source_event_refs=namespaced_source_refs(
                self.api_name,
                [item["provider_match_id"] for item in matches],
            ),
            value={
                "provider_team_id": str(team_id),
                "requested_sample_size": requested_sample_size,
                "accepted_sample_size": len(matches),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
                "coverage_status": coverage_status,
                "matches": matches,
            },
            parser_diagnostics={
                "raw_count": len(payload),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
                "coverage_status": coverage_status,
            },
        )

    def get_head_to_head_result(
        self,
        team_id_one: str | int,
        team_id_two: str | int,
    ) -> SourceOperationResult[dict[str, Any]]:
        result = self._request_with_evidence(
            endpoint="/head-2-head",
            params={"teamIdOne": str(team_id_one), "teamIdTwo": str(team_id_two)},
            operation="historical_form_h2h",
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, list):
            return self._schema_error(result, "payload_not_list")

        matches = []
        rejected_count = 0
        for index, row in enumerate(payload, start=1):
            match_row = self._normalize_h2h_row(row, source_order=index)
            if match_row is None:
                rejected_count += 1
                continue
            matches.append(match_row)

        status = (
            SourceResultStatus.SUCCESS if matches else SourceResultStatus.VALID_EMPTY
        )
        return self._bundle_result(
            result=result,
            parser_version=H2H_PARSER_VERSION,
            operation_name="historical_form_h2h",
            source_event_refs=namespaced_source_refs(
                self.api_name,
                [item["provider_match_id"] for item in matches],
            ),
            value={
                "provider_team_id_one": str(team_id_one),
                "provider_team_id_two": str(team_id_two),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
                "matches": matches,
            },
            parser_diagnostics={
                "raw_count": len(payload),
                "accepted_count": len(matches),
                "rejected_count": rejected_count,
            },
            forced_status=status,
        )

    def get_statistics_result(
        self,
        match_id: str | int,
        *,
        home_team_id: str | int,
        away_team_id: str | int,
    ) -> SourceOperationResult[dict[str, Any]]:
        home_id = str(home_team_id).strip()
        away_id = str(away_team_id).strip()
        if not home_id or not away_id or home_id == away_id:
            return SourceOperationResult(
                status=SourceResultStatus.AMBIGUOUS,
                provider=self.api_name,
                operation="detailed_metrics",
                error_code="provider_native_team_ids_required",
            )

        result = self._request_with_evidence(
            endpoint=f"/statistics/{match_id}",
            params={},
            operation="detailed_metrics",
            source_event_id=str(match_id),
        )
        if result.status is not SourceResultStatus.SUCCESS:
            return result
        payload = result.value
        if not isinstance(payload, list):
            return self._schema_error(result, "payload_not_list")

        if payload and not all(
            isinstance(row, dict) and isinstance(row.get("statistics"), list)
            for row in payload
        ):
            return self._schema_error(result, "statistics_list_missing")

        stats_rows = []
        raw_stat_field_names: list[str] = []
        raw_stat_name_set: set[str] = set()
        unknown_metrics: list[str] = []
        rejected_count = 0
        team_rows = []
        for row in payload:
            if not isinstance(row, dict):
                rejected_count += 1
                continue
            team = row.get("team") if isinstance(row.get("team"), dict) else {}
            provider_team_id = str(team.get("id") or "").strip()
            if provider_team_id == home_id:
                side = "home"
            elif provider_team_id == away_id:
                side = "away"
            else:
                return self._schema_error(result, "unexpected_team_id")
            team_rows.append(
                {
                    "provider_team_id": provider_team_id,
                    "team_name": team.get("name"),
                    "side": side,
                }
            )
            for stat in row.get("statistics", []):
                if not isinstance(stat, dict):
                    rejected_count += 1
                    continue
                raw_name = str(stat.get("displayName") or "").strip()
                if not raw_name:
                    rejected_count += 1
                    continue
                if raw_name not in raw_stat_name_set:
                    raw_stat_name_set.add(raw_name)
                    raw_stat_field_names.append(raw_name)
                mapping = STAT_NAME_MAP.get(raw_name)
                normalized_name = mapping[0] if mapping else None
                unit = mapping[1] if mapping else None
                if mapping is None and raw_name not in unknown_metrics:
                    unknown_metrics.append(raw_name)
                stats_rows.append(
                    {
                        "provider_match_id": str(match_id),
                        "provider_team_id": provider_team_id,
                        "team_name": team.get("name"),
                        "side": side,
                        "raw_stat_name": raw_name,
                        "normalized_metric_name": normalized_name,
                        "value": stat.get("value"),
                        "unit": unit,
                        "parser_version": STATISTICS_PARSER_VERSION,
                    }
                )

        if not stats_rows:
            return self._schema_error(result, "statistics_empty")

        normalized_metric_names = [
            row["normalized_metric_name"]
            for row in stats_rows
            if row["normalized_metric_name"]
        ]
        return self._bundle_result(
            result=result,
            parser_version=STATISTICS_PARSER_VERSION,
            operation_name="detailed_metrics",
            source_event_refs=namespaced_source_refs(self.api_name, [str(match_id)]),
            value={
                "provider_match_id": str(match_id),
                "team_rows": team_rows,
                "statistics": stats_rows,
                "raw_stat_field_names": raw_stat_field_names,
                "normalized_metric_names": normalized_metric_names,
                "accepted_count": len(stats_rows),
                "rejected_count": rejected_count,
                "missing_target_metrics": list(MISSING_TARGET_METRICS),
                "unknown_metrics": unknown_metrics,
            },
            parser_diagnostics={
                "raw_count": len(payload),
                "accepted_count": len(stats_rows),
                "rejected_count": rejected_count,
                "raw_stat_fields_count": len(raw_stat_field_names),
                "missing_target_metrics": list(MISSING_TARGET_METRICS),
                "unknown_metrics": unknown_metrics,
            },
        )

    def _normalize_match_row(
        self,
        row: Any,
        *,
        requested_team_id: str | None,
        source_order: int,
    ) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        home_team = row.get("homeTeam") if isinstance(row.get("homeTeam"), dict) else {}
        away_team = row.get("awayTeam") if isinstance(row.get("awayTeam"), dict) else {}
        league = row.get("league") if isinstance(row.get("league"), dict) else {}
        state = row.get("state") if isinstance(row.get("state"), dict) else {}
        score = state.get("score") if isinstance(state.get("score"), dict) else {}

        home_id = str(home_team.get("id") or "").strip()
        away_id = str(away_team.get("id") or "").strip()
        if not str(row.get("id") or "").strip() or not home_id or not away_id:
            return None

        home_goals, away_goals = self._parse_score(score.get("current"))
        team_side = None
        opponent = {"provider_team_id": None, "team_name": None}
        result_code = None
        if requested_team_id == home_id:
            team_side = "home"
            opponent = {
                "provider_team_id": away_id,
                "team_name": away_team.get("name"),
            }
            result_code = self._infer_result(home_goals, away_goals)
        elif requested_team_id == away_id:
            team_side = "away"
            opponent = {
                "provider_team_id": home_id,
                "team_name": home_team.get("name"),
            }
            result_code = self._infer_result(away_goals, home_goals)

        normalized = {
            "provider_match_id": str(row.get("id")),
            "kickoff": row.get("date"),
            "date": row.get("date"),
            "home_team": {
                "provider_team_id": home_id,
                "team_name": home_team.get("name"),
            },
            "away_team": {
                "provider_team_id": away_id,
                "team_name": away_team.get("name"),
            },
            "opponent": opponent,
            "home_away": team_side,
            "score": {
                "display": score.get("current"),
                "home": home_goals,
                "away": away_goals,
            }
            if score.get("current") is not None
            else None,
            "result": result_code,
            "match_status": state.get("description"),
            "competition": league.get("name"),
            "competition_provider_id": str(league.get("id"))
            if league.get("id") is not None
            else None,
            "season": league.get("season"),
            "source_order": source_order,
        }
        return normalized

    def _normalize_h2h_row(
        self,
        row: Any,
        *,
        source_order: int,
    ) -> dict[str, Any] | None:
        match_row = self._normalize_match_row(
            row,
            requested_team_id=None,
            source_order=source_order,
        )
        if match_row is None:
            return None
        score = match_row.get("score") or {}
        home_goals = score.get("home")
        away_goals = score.get("away")
        winner = None
        is_draw = None
        if home_goals is not None and away_goals is not None:
            if home_goals > away_goals:
                winner = "home"
                is_draw = False
            elif away_goals > home_goals:
                winner = "away"
                is_draw = False
            else:
                winner = None
                is_draw = True
        return {
            "provider_match_id": match_row["provider_match_id"],
            "date": match_row["date"],
            "home_team_id": match_row["home_team"]["provider_team_id"],
            "home_team_name": match_row["home_team"]["team_name"],
            "away_team_id": match_row["away_team"]["provider_team_id"],
            "away_team_name": match_row["away_team"]["team_name"],
            "score": match_row["score"],
            "status": match_row["match_status"],
            "winner": winner,
            "draw": is_draw,
            "competition": match_row["competition"],
            "competition_provider_id": match_row["competition_provider_id"],
            "season": match_row["season"],
            "source_order": source_order,
        }

    @staticmethod
    def _parse_score(raw_score: Any) -> tuple[int | None, int | None]:
        if not isinstance(raw_score, str) or "-" not in raw_score:
            return None, None
        left, right = raw_score.split("-", 1)
        try:
            return int(left.strip()), int(right.strip())
        except ValueError:
            return None, None

    @staticmethod
    def _infer_result(goals_for: int | None, goals_against: int | None) -> str | None:
        if goals_for is None or goals_against is None:
            return None
        if goals_for > goals_against:
            return "W"
        if goals_for < goals_against:
            return "L"
        return "D"
