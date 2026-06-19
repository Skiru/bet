#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENDPOINT = "https://api.sportdb.dev/mcp/"
USER_AGENT = "bet-sportdb-probe/1.0"
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_SCHEMA_CALL_BUDGET = 4
MCP_MAPPING_CALL_BUDGET = 11
TIMEOUT_SECONDS = 30
KEY_ALIASES = ("SPORTDB_API_KEY", "SPORTDB_KEY")
SUMMARY_PATH = Path("certification/football/p2e_sportdb_mcp_schema_summary.json")
FOOTBALL_MAPPING_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_mcp_football_mapping_summary.json"
)
FOOTBALL_MAPPING_SCHEMA_SOURCE = Path(
    "certification/football/p2e_sportdb_mcp_schema_summary.json"
)
PHASE_ID_A2 = "P2E_A2_SPORTDB_MCP_TOOL_SCHEMA_MAPPING"
PHASE_ID_A3 = "P2E_A3_SPORTDB_MCP_FOOTBALL_PROVIDER_NATIVE_MAPPING"
PROMPT_VERSION_A3 = "v2_hardened_schema_driven"
ACCEPT_HEADER = "application/json, text/event-stream"
CORE_MAPPING_TOOLS = (
    "flashscore_list_sports",
    "flashscore_list_countries",
    "flashscore_list_competitions",
    "flashscore_list_competition_seasons",
    "flashscore_get_competition_results",
    "flashscore_get_match_stats",
)
CLASSIFICATION_READY = "SPORTDB_MCP_FOOTBALL_MAPPING_READY_FOR_SHADOW_ADAPTER"
CLASSIFICATION_PARTIAL = "SPORTDB_FOOTBALL_MAPPING_PARTIAL_EVENTS_OR_LINEUPS_MISSING"
CLASSIFICATION_SCHEMA_INCOMPLETE = (
    "SPORTDB_FOOTBALL_MAPPING_BLOCKED_SCHEMA_SUMMARY_INCOMPLETE"
)
CLASSIFICATION_REQUIRED_UNKNOWN = (
    "SPORTDB_FOOTBALL_MAPPING_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
)
CLASSIFICATION_NO_SPORT = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_NO_FOOTBALL_SPORT_KEY"
CLASSIFICATION_NO_COUNTRY = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_NO_ENGLAND_COUNTRY"
CLASSIFICATION_NO_COMPETITION = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_NO_PREMIER_LEAGUE"
CLASSIFICATION_NO_SEASONS = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_NO_SEASONS"
CLASSIFICATION_NO_MATCH = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_NO_FINISHED_MATCH_ID"
CLASSIFICATION_NO_STATS = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_STATS_UNAVAILABLE"
CLASSIFICATION_RATE_LIMIT = "SPORTDB_RATE_LIMITED_RETRY_LATER"
CLASSIFICATION_AUTH = "SPORTDB_AUTH_BLOCKED"
CLASSIFICATION_ACCEPT_DEFECT = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
CLASSIFICATION_SSE_DEFECT = "PLAN_DEFECT_MCP_FOOTBALL_MAPPING_PARSER"
CLASSIFICATION_TRANSPORT = "SPORTDB_FOOTBALL_MAPPING_BLOCKED_TRANSPORT_OR_SERVER"
ALL_A3_CLASSIFICATIONS = {
    CLASSIFICATION_READY,
    CLASSIFICATION_PARTIAL,
    CLASSIFICATION_SCHEMA_INCOMPLETE,
    CLASSIFICATION_REQUIRED_UNKNOWN,
    CLASSIFICATION_NO_SPORT,
    CLASSIFICATION_NO_COUNTRY,
    CLASSIFICATION_NO_COMPETITION,
    CLASSIFICATION_NO_SEASONS,
    CLASSIFICATION_NO_MATCH,
    CLASSIFICATION_NO_STATS,
    CLASSIFICATION_RATE_LIMIT,
    CLASSIFICATION_AUTH,
    CLASSIFICATION_ACCEPT_DEFECT,
    CLASSIFICATION_SSE_DEFECT,
    CLASSIFICATION_TRANSPORT,
}

KNOWN_TOOL_ORDER = [
    "flashscore_list_sports",
    "flashscore_get_live",
    "flashscore_get_live_odds",
    "flashscore_list_countries",
    "flashscore_list_competitions",
    "flashscore_list_competition_seasons",
    "flashscore_get_competition_fixtures",
    "flashscore_get_competition_results",
    "flashscore_get_competition_standings",
    "flashscore_get_match_stats",
    "flashscore_get_match_events",
    "flashscore_get_match_lineups",
    "flashscore_get_team_details",
    "flashscore_get_player_details",
    "flashscore_search",
]

FOOTBALL_TOOL_BUCKETS = {
    "sports discovery": ["flashscore_list_sports"],
    "country discovery": ["flashscore_list_countries"],
    "competition discovery": ["flashscore_list_competitions"],
    "season discovery": ["flashscore_list_competition_seasons"],
    "fixtures": ["flashscore_get_competition_fixtures"],
    "results": ["flashscore_get_competition_results"],
    "standings": ["flashscore_get_competition_standings"],
    "match stats": ["flashscore_get_match_stats"],
    "match events": ["flashscore_get_match_events"],
    "match lineups": ["flashscore_get_match_lineups"],
    "search": ["flashscore_search"],
    "team details": ["flashscore_get_team_details"],
    "player details": ["flashscore_get_player_details"],
}


def parse_dot_env(file_path: Path) -> dict[str, str]:
    env_dict: dict[str, str] = {}
    if not file_path.exists():
        return env_dict
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and (
            (value[0] == '"' and value[-1] == '"')
            or (value[0] == "'" and value[-1] == "'")
        ):
            value = value[1:-1]
        env_dict[key] = value
    return env_dict


def resolve_api_key() -> tuple[str | None, str, str]:
    for alias in KEY_ALIASES:
        value = os.environ.get(alias, "")
        if value.strip():
            return value.strip(), alias, "environment"

    dot_env = parse_dot_env(Path(".env"))
    for alias in KEY_ALIASES:
        value = dot_env.get(alias, "")
        if value.strip():
            return value.strip(), alias, "dot_env"

    return None, "SPORTDB_API_KEY", "missing"


def rate_headers(headers: dict[str, str]) -> dict[str, str]:
    keep: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if "ratelimit" in lowered or lowered in {
            "retry-after",
            "x-api-key-limit",
            "x-api-key-remaining",
        }:
            keep[key] = value
    return keep


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


def parse_sse_payloads(raw_text: str) -> tuple[list[dict[str, Any]], list[Any]]:
    events: list[dict[str, Any]] = []
    payloads: list[Any] = []
    current: dict[str, Any] = {}
    data_lines: list[str] = []

    def flush_event() -> None:
        if not current and not data_lines:
            return

        event = dict(current)
        data_text = "\n".join(data_lines).strip()
        if data_text:
            event["data"] = data_text
            if data_text != "[DONE]":
                try:
                    payloads.append(json.loads(data_text))
                except json.JSONDecodeError:
                    payloads.append({"_raw_sse_data": data_text})
        events.append(event)
        current.clear()
        data_lines.clear()

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            flush_event()
            continue
        if line.startswith(":"):
            continue
        field, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.lstrip(" ")
        if field == "data":
            data_lines.append(value)
        else:
            current[field] = value

    flush_event()
    return events, payloads


def extract_primary_payload(response_mode: str, payload: Any) -> Any:
    if response_mode == "sse":
        if not isinstance(payload, dict):
            return payload
        payloads = payload.get("payloads")
        if not isinstance(payloads, list):
            return payload
        for item in reversed(payloads):
            if isinstance(item, dict) and (
                item.get("jsonrpc") == "2.0"
                or "result" in item
                or "error" in item
            ):
                return item
        for item in reversed(payloads):
            if isinstance(item, dict):
                return item
        return payloads[-1] if payloads else payload
    return payload


def detect_response_mode(content_type: str) -> str:
    lowered = content_type.lower()
    if "text/event-stream" in lowered:
        return "sse"
    if "application/json" in lowered or lowered.endswith("+json"):
        return "json"
    return "unknown"


def normalize_token(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def slugify_token(value: Any) -> str:
    text = normalize_token(value)
    return text.replace(" ", "-")


def extract_link_segments(value: Any) -> list[str]:
    text = str(value or "").strip().strip("/")
    if not text:
        return []
    return [segment for segment in text.split("/") if segment]


def load_json_text_if_possible(value: str) -> Any:
    text = value.strip()
    if not text or text[:1] not in "[{":
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_p2e_a2_schema_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def get_tool_schema(summary: dict[str, Any], tool_name: str) -> dict[str, Any]:
    tool_schemas = summary.get("tool_schemas")
    if not isinstance(tool_schemas, dict):
        return {}
    tool_schema = tool_schemas.get(tool_name)
    return tool_schema if isinstance(tool_schema, dict) else {}


class RequiredPayloadFieldUnknownError(RuntimeError):
    def __init__(self, field_name: str):
        self.field_name = field_name
        super().__init__(field_name)


def build_tool_payload(tool_schema: dict[str, Any], known_values: dict[str, Any]) -> dict[str, Any]:
    required = tool_schema.get("required_fields")
    optional = tool_schema.get("optional_fields")
    if not isinstance(required, list):
        required = []
    if not isinstance(optional, list):
        optional = []

    alias_map = {
        "sport": ["sport_key", "sport_slug", "sport_name"],
        "sport_key": ["sport_key", "sport_slug", "sport_name"],
        "sport_slug": ["sport_slug", "sport_key", "sport_name"],
        "sport_name": ["sport_name", "sport_key", "sport_slug"],
        "country_slug": ["country_slug"],
        "country_id": ["country_id"],
        "country_name": ["country_name"],
        "competition_slug": ["competition_slug"],
        "competition_id": ["competition_id"],
        "competition_name": ["competition_name"],
        "season": ["season", "season_name", "season_value"],
        "season_id": ["season_id"],
        "season_name": ["season_name", "season", "season_value"],
        "match_id": ["match_id"],
        "page": ["page"],
    }

    payload: dict[str, Any] = {}
    for field_name in required:
        candidate_names = [field_name] + alias_map.get(field_name, [])
        value = None
        found = False
        for candidate_name in candidate_names:
            if candidate_name in known_values:
                candidate_value = known_values[candidate_name]
                if candidate_value not in (None, ""):
                    value = candidate_value
                    found = True
                    break
        if not found:
            raise RequiredPayloadFieldUnknownError(field_name)
        payload[field_name] = value

    for field_name in optional:
        if field_name in known_values and known_values[field_name] not in (None, ""):
            payload[field_name] = known_values[field_name]
    return payload


def nested_get(item: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = item
        ok = True
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                ok = False
                break
            current = current[part]
        if ok and current not in (None, ""):
            return current
    return None


def extract_candidate_strings(item: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "name",
        "slug",
        "key",
        "sport",
        "country",
        "competition",
        "season",
        "value",
        "label",
        "title",
        "short_name",
    ):
        value = nested_get(item, key)
        if value not in (None, ""):
            values.append(str(value))
    for key in ("link", "live", "url", "href"):
        value = nested_get(item, key)
        if value in (None, ""):
            continue
        values.extend(extract_link_segments(value))
    return values


def walk_dicts(payload: Any) -> list[dict[str, Any]]:
    seen: set[int] = set()
    collected: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            marker = id(value)
            if marker in seen:
                return
            seen.add(marker)
            collected.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return collected


def extract_content_payloads(result: dict[str, Any]) -> list[Any]:
    payloads: list[Any] = []
    content = result.get("content")
    if not isinstance(content, list):
        return payloads
    for item in content:
        if not isinstance(item, dict):
            continue
        if "json" in item and item["json"] is not None:
            payloads.append(item["json"])
        text = item.get("text")
        if isinstance(text, str):
            loaded = load_json_text_if_possible(text)
            if loaded is not None:
                payloads.append(loaded)
            else:
                payloads.append(text)
    return payloads


def extract_tool_result_payload(primary_payload: Any) -> Any:
    if not isinstance(primary_payload, dict):
        return primary_payload
    result = primary_payload.get("result")
    if not isinstance(result, dict):
        return primary_payload
    if "structuredContent" in result:
        return result["structuredContent"]
    content_payloads = extract_content_payloads(result)
    if len(content_payloads) == 1:
        return content_payloads[0]
    if content_payloads:
        return content_payloads
    return result


def top_level_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "data", "results", "sports", "countries", "competitions", "seasons", "matches", "events", "lineups", "standings"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def select_football_sport(items: Any) -> dict[str, Any] | None:
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = {normalize_token(value) for value in extract_candidate_strings(item)}
        if normalized & {"football", "soccer"}:
            return item
    return None


def select_england_country(items: Any) -> dict[str, Any] | None:
    blocked = {
        "united kingdom",
        "great britain",
        "scotland",
        "wales",
        "northern ireland",
    }
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = {normalize_token(value) for value in extract_candidate_strings(item)}
        if "england" in normalized and not normalized & blocked:
            return item
    return None


def select_premier_league_competition(items: Any) -> dict[str, Any] | None:
    blocked = {
        "championship",
        "women super league",
        "premier league cup",
        "u21 premier league",
        "premier league 2",
    }
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        normalized = {normalize_token(value) for value in extract_candidate_strings(item)}
        if normalized & {"premier league", "premier-league"} and not normalized & blocked:
            return item
    return None


def select_completed_or_result_season(items: Any) -> dict[str, Any] | None:
    preferred = [
        "2025 2026",
        "2025 26",
        "2024 2025",
        "2024 25",
    ]
    observed = [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    for target in preferred:
        for item in observed:
            values = {normalize_token(value) for value in extract_candidate_strings(item)}
            if target in values:
                return item
    return observed[0] if observed else None


def select_finished_match(items: Any) -> dict[str, Any] | None:
    finished_tokens = {
        "finished",
        "full time",
        "after penalties",
        "after extra time",
        "aet",
        "pen",
        "ft",
    }
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        match_id = nested_get(item, "match_id", "eventId", "id", "match.id")
        if match_id in (None, ""):
            continue
        status_values = {
            normalize_token(value)
            for value in (
                nested_get(item, "status"),
                nested_get(item, "status_type"),
                nested_get(item, "state"),
                nested_get(item, "result"),
            )
            if value not in (None, "")
        }
        home = nested_get(item, "home_team", "home.name", "homeTeam", "participantHome", "homeName", "homeFirstName")
        away = nested_get(item, "away_team", "away.name", "awayTeam", "participantAway", "awayName", "awayFirstName")
        has_teams = home not in (None, "") and away not in (None, "")
        has_score = any(
            nested_get(item, key) not in (None, "")
            for key in ("score", "home_score", "away_score", "result.score", "homeScore", "awayScore", "homeFullTimeScore", "awayFullTimeScore")
        )
        if status_values & finished_tokens or (has_score and (has_teams or not status_values)):
            return item
    return None


def extract_top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        keys: set[str] = set()
        for item in payload:
            if isinstance(item, dict):
                keys.update(str(key) for key in item.keys())
        return sorted(keys)
    return []


def extract_stat_field_names(payload: Any) -> list[str]:
    names: set[str] = set()
    for item in walk_dicts(payload):
        for key in ("name", "label", "stat", "type", "field", "statName"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                names.add(value.strip())
    return sorted(names)


def redact_text(value: str) -> str:
    redacted = value.replace("SPORTDB_API_KEY", "REDACTED_KEY_NAME")
    for alias in KEY_ALIASES:
        secret = os.environ.get(alias, "")
        if secret:
            redacted = redacted.replace(secret, "REDACTED")
    return redacted


def safe_preview(payload: Any, max_chars: int = 2000) -> Any:
    normalized = normalize_jsonable(payload)
    text = json.dumps(normalized, ensure_ascii=True, sort_keys=True)
    text = redact_text(text)
    if len(text) <= max_chars:
        return json.loads(text)
    trimmed = text[: max_chars - 3] + "..."
    return {"preview": trimmed, "truncated": True}


def sha256_jsonable(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(normalize_jsonable(payload), ensure_ascii=True, sort_keys=True).encode(
            "utf-8"
        )
    ).hexdigest()


def extract_entity_fields(item: dict[str, Any], entity_type: str) -> dict[str, Any]:
    link_segments = extract_link_segments(nested_get(item, "link", "url", "href"))
    last_segment = link_segments[-1] if link_segments else None
    if entity_type == "sport":
        return {
            "key": nested_get(item, "key", "slug", "sport", "name") or last_segment,
            "slug": nested_get(item, "slug", "key") or last_segment,
            "name": nested_get(item, "name", "title", "sport", "slug") or last_segment,
        }
    if entity_type == "country":
        return {
            "slug": nested_get(item, "slug", "country_slug", "key") or last_segment,
            "id": nested_get(item, "id", "country_id"),
            "name": nested_get(item, "name", "country", "title", "slug") or last_segment,
        }
    if entity_type == "competition":
        return {
            "slug": nested_get(item, "slug", "competition_slug", "key") or last_segment,
            "id": nested_get(item, "id", "competition_id"),
            "name": nested_get(item, "name", "competition", "title", "slug") or last_segment,
        }
    if entity_type == "season":
        return {
            "season": nested_get(item, "season", "name", "value", "label", "id"),
            "id": nested_get(item, "id", "season_id"),
            "name": nested_get(item, "name", "label", "season", "value"),
            "value": nested_get(item, "value", "season", "name", "label"),
        }
    return {}


def extract_match_fields(item: dict[str, Any]) -> dict[str, Any]:
    home = nested_get(item, "home_team", "home.name", "homeTeam", "participantHome", "homeName", "homeFirstName")
    away = nested_get(item, "away_team", "away.name", "awayTeam", "participantAway", "awayName", "awayFirstName")
    home_score = nested_get(item, "home_score", "home.score", "homeScore", "homeFullTimeScore")
    away_score = nested_get(item, "away_score", "away.score", "awayScore", "awayFullTimeScore")
    score = nested_get(item, "score", "result.score")
    if score in (None, "") and home_score not in (None, "") and away_score not in (None, ""):
        score = f"{home_score}-{away_score}"
    match_name = nested_get(item, "name", "match_name")
    if match_name in (None, "") and home not in (None, "") and away not in (None, ""):
        match_name = f"{home} vs {away}"
    return {
        "id": nested_get(item, "match_id", "eventId", "id", "match.id"),
        "name": match_name,
        "status": nested_get(item, "status", "status_type", "state", "result", "eventStage"),
        "score": score,
    }


def select_candidate_matches(items: Any, selector: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and selector([item]) is not None:
            candidates.append(item)
    return candidates


def extract_result_list(payload: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    values = result.get(key)
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def extract_names_for_method(method: str, payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []

    if method == "tools/list":
        return [
            str(tool.get("name"))
            for tool in extract_result_list(payload, "tools")
            if tool.get("name")
        ]

    if method == "resources/list":
        names: list[str] = []
        for item in extract_result_list(payload, "resources"):
            for key in ("name", "uri", "title"):
                value = item.get(key)
                if value is not None and str(value).strip():
                    names.append(str(value).strip())
                    break
        return names

    if method == "prompts/list":
        return [
            str(item.get("name"))
            for item in extract_result_list(payload, "prompts")
            if item.get("name")
        ]

    return []


def extract_tools(payload: Any) -> list[dict[str, Any]]:
    return extract_result_list(payload, "tools")


def extract_schema(tool: dict[str, Any]) -> dict[str, Any]:
    for key in ("inputSchema", "input_schema", "parameters"):
        schema = tool.get(key)
        if isinstance(schema, dict):
            return schema
    return {}


def extract_properties(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if isinstance(properties, dict):
        return properties
    return {}


def required_fields(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required")
    if isinstance(required, list):
        return [str(item) for item in required if str(item).strip()]
    return []


def optional_fields(schema: dict[str, Any]) -> list[str]:
    required = set(required_fields(schema))
    return sorted(name for name in extract_properties(schema) if name not in required)


def enum_fields(schema: dict[str, Any]) -> dict[str, list[Any]]:
    enums: dict[str, list[Any]] = {}
    for name, spec in extract_properties(schema).items():
        if not isinstance(spec, dict):
            continue
        if isinstance(spec.get("enum"), list):
            enums[name] = [normalize_jsonable(item) for item in spec["enum"]]
            continue
        any_of = spec.get("anyOf")
        if isinstance(any_of, list):
            collected: list[Any] = []
            for item in any_of:
                if isinstance(item, dict) and isinstance(item.get("enum"), list):
                    collected.extend(normalize_jsonable(value) for value in item["enum"])
            if collected:
                enums[name] = collected
    return enums


def find_parameter_names(schema: dict[str, Any], needles: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for name in extract_properties(schema):
        lowered = name.lower()
        if any(needle in lowered for needle in needles):
            matches.append(name)
    return matches


def output_hints(tool: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("description", "title"):
        value = tool.get(key)
        if value is not None and str(value).strip():
            hints.append(str(value).strip())
    return hints


def capability_from_name(name: str) -> str:
    lookup = {
        "flashscore_list_sports": "sports discovery",
        "flashscore_list_countries": "country discovery",
        "flashscore_list_competitions": "competition discovery",
        "flashscore_list_competition_seasons": "season discovery",
        "flashscore_get_competition_fixtures": "fixtures",
        "flashscore_get_competition_results": "results",
        "flashscore_get_competition_standings": "standings",
        "flashscore_get_match_stats": "match stats",
        "flashscore_get_match_events": "match events",
        "flashscore_get_match_lineups": "match lineups",
        "flashscore_search": "search",
        "flashscore_get_team_details": "team details",
        "flashscore_get_player_details": "player details",
        "flashscore_get_live": "live scoreboard",
        "flashscore_get_live_odds": "live odds",
    }
    return lookup.get(name, "unknown")


def build_tool_schema_summary(tool: dict[str, Any]) -> dict[str, Any]:
    name = str(tool.get("name") or "")
    schema = extract_schema(tool)
    return {
        "tool_name": name,
        "description": str(tool.get("description") or "").strip(),
        "input_schema": normalize_jsonable(schema),
        "required_fields": required_fields(schema),
        "optional_fields": optional_fields(schema),
        "enum_fields": enum_fields(schema),
        "sport_parameter_support": find_parameter_names(
            schema, ("sport", "discipline")
        ),
        "country_parameters": find_parameter_names(
            schema, ("country", "nation", "region")
        ),
        "competition_parameters": find_parameter_names(
            schema, ("competition", "league", "tournament")
        ),
        "season_parameters": find_parameter_names(schema, ("season",)),
        "match_id_parameters": find_parameter_names(
            schema, ("match", "fixture", "game")
        ),
        "pagination_or_limit_parameters": find_parameter_names(
            schema, ("limit", "page", "offset", "cursor")
        ),
        "date_time_parameters": find_parameter_names(
            schema, ("date", "time", "from", "to")
        ),
        "output_hints": output_hints(tool),
        "likely_capability_mapping": capability_from_name(name),
    }


def football_mapping_tools(tool_summaries: dict[str, dict[str, Any]]) -> list[str]:
    ordered: list[str] = []
    for tools in FOOTBALL_TOOL_BUCKETS.values():
        for tool_name in tools:
            if tool_name in tool_summaries and tool_name not in ordered:
                ordered.append(tool_name)
    return ordered


def future_multisport_tools(tool_summaries: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for tool_name in KNOWN_TOOL_ORDER:
        summary = tool_summaries.get(tool_name)
        if summary is None:
            continue
        sport_params = summary.get("sport_parameter_support") or []
        if tool_name == "flashscore_list_sports" or sport_params:
            items.append(
                {
                    "tool_name": tool_name,
                    "sport_parameter_support": sport_params,
                    "basketball_potential": bool(sport_params or tool_name == "flashscore_list_sports"),
                    "hockey_potential": bool(sport_params or tool_name == "flashscore_list_sports"),
                    "tennis_potential": bool(sport_params or tool_name == "flashscore_list_sports"),
                }
            )
    return items


def not_for_canonical_enrichment_now(tool_summaries: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for tool_name, reason in (
        ("flashscore_get_live", "live_feed_not_needed_for_provider_native_eng1_mapping"),
        ("flashscore_get_live_odds", "odds_not_for_canonical_enrichment_now"),
    ):
        if tool_name in tool_summaries:
            items.append({"tool_name": tool_name, "reason": reason})
    return items


def utility_tools(tool_summaries: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    if "flashscore_search" in tool_summaries:
        items.append(
            {
                "tool_name": "flashscore_search",
                "reason": "provider_native_disambiguation_support",
            }
        )
    return items


def capability_mapping(tool_summaries: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    mapping = {
        "current_discovery": [],
        "standings": [],
        "current_form": [],
        "historical_form_h2h": [],
        "detailed_metrics": [],
        "auxiliary_lineups_events": [],
    }

    if "flashscore_list_sports" in tool_summaries:
        mapping["current_discovery"].append("flashscore_list_sports")
    for tool_name in (
        "flashscore_list_countries",
        "flashscore_list_competitions",
        "flashscore_list_competition_seasons",
        "flashscore_get_competition_fixtures",
        "flashscore_get_competition_results",
    ):
        if tool_name in tool_summaries:
            mapping["current_discovery"].append(tool_name)

    if "flashscore_get_competition_standings" in tool_summaries:
        mapping["standings"].append("flashscore_get_competition_standings")

    for tool_name in ("flashscore_get_competition_results", "flashscore_search"):
        if tool_name in tool_summaries:
            mapping["current_form"].append(tool_name)
            mapping["historical_form_h2h"].append(tool_name)

    if "flashscore_get_match_stats" in tool_summaries:
        mapping["detailed_metrics"].append("flashscore_get_match_stats")

    for tool_name in ("flashscore_get_match_events", "flashscore_get_match_lineups"):
        if tool_name in tool_summaries:
            mapping["auxiliary_lineups_events"].append(tool_name)

    return mapping


def build_tool_sequence(tool_summaries: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    sequence_order = [
        "flashscore_list_sports",
        "flashscore_list_countries",
        "flashscore_list_competitions",
        "flashscore_list_competition_seasons",
        "flashscore_get_competition_results",
        "flashscore_get_competition_fixtures",
        "flashscore_get_match_stats",
        "flashscore_get_match_events",
        "flashscore_get_match_lineups",
        "flashscore_get_competition_standings",
    ]
    goals = {
        "flashscore_list_sports": "confirm provider-native football sport key",
        "flashscore_list_countries": "discover provider-native England country id_or_slug",
        "flashscore_list_competitions": "discover provider-native Premier League competition id_or_slug",
        "flashscore_list_competition_seasons": "discover exact provider-native season id_or_string",
        "flashscore_get_competition_results": "discover provider-native finished match ids for the selected season",
        "flashscore_get_competition_fixtures": "fallback to discover provider-native match ids if results are empty",
        "flashscore_get_match_stats": "inspect raw stat field names for one provider-native match id",
        "flashscore_get_match_events": "optional later auxiliary context for event structure",
        "flashscore_get_match_lineups": "optional later auxiliary context for lineup structure",
        "flashscore_get_competition_standings": "optional later standings structure after core mapping succeeds",
    }
    sequence: list[dict[str, Any]] = []
    required_params: dict[str, list[str]] = {}

    for tool_name in sequence_order:
        summary = tool_summaries.get(tool_name)
        if summary is None:
            continue
        sequence.append(
            {
                "tool_name": tool_name,
                "goal": goals[tool_name],
                "required_fields": summary["required_fields"],
                "optional_fields": summary["optional_fields"],
            }
        )
        required_params[tool_name] = summary["required_fields"]

    return sequence, required_params


def build_tool_call_templates() -> list[dict[str, Any]]:
    return [
        {
            "step": 1,
            "tool_name": "flashscore_list_sports",
            "params": {},
        },
        {
            "step": 2,
            "tool_name": "flashscore_list_countries",
            "params": {"sport": "<sport_from_step_1>"},
        },
        {
            "step": 3,
            "tool_name": "flashscore_list_competitions",
            "params": {
                "sport": "<sport_from_step_1>",
                "country_slug": "<england_country_slug_from_step_2>",
                "country_id": "<england_country_id_from_step_2>",
            },
        },
        {
            "step": 4,
            "tool_name": "flashscore_list_competition_seasons",
            "params": {
                "sport": "<sport_from_step_1>",
                "country_slug": "<england_country_slug_from_step_2>",
                "country_id": "<england_country_id_from_step_2>",
                "competition_slug": "<premier_league_competition_slug_from_step_3>",
                "competition_id": "<premier_league_competition_id_from_step_3>",
            },
        },
        {
            "step": 5,
            "tool_name": "flashscore_get_competition_results",
            "params": {
                "sport": "<sport_from_step_1>",
                "country_slug": "<england_country_slug_from_step_2>",
                "country_id": "<england_country_id_from_step_2>",
                "competition_slug": "<premier_league_competition_slug_from_step_3>",
                "competition_id": "<premier_league_competition_id_from_step_3>",
                "season": "<season_from_step_4>",
            },
            "fallback_if_empty": "flashscore_get_competition_fixtures",
        },
        {
            "step": 6,
            "tool_name": "flashscore_get_match_stats",
            "params": {"match_id": "<match_id_from_step_5>"},
        },
        {
            "step": 7,
            "tool_name": "flashscore_get_match_events",
            "params": {"match_id": "<match_id_from_step_5>"},
            "optional": True,
        },
        {
            "step": 8,
            "tool_name": "flashscore_get_match_lineups",
            "params": {"match_id": "<match_id_from_step_5>"},
            "optional": True,
        },
        {
            "step": 9,
            "tool_name": "flashscore_get_competition_standings",
            "params": {
                "sport": "<sport_from_step_1>",
                "country_slug": "<england_country_slug_from_step_2>",
                "country_id": "<england_country_id_from_step_2>",
                "competition_slug": "<premier_league_competition_slug_from_step_3>",
                "competition_id": "<premier_league_competition_id_from_step_3>",
                "season": "<season_from_step_4>",
            },
            "optional": True,
        },
    ]


def build_final_classification(
    tool_summaries: dict[str, dict[str, Any]], calls: list[dict[str, Any]]
) -> tuple[str, str, str | None]:
    if any(call.get("status") == 429 for call in calls):
        return (
            "SPORTDB_RATE_LIMITED_RETRY_LATER",
            "sportdb_rate_limit_retry",
            "rate_limited_on_discovery",
        )

    for call in calls:
        if call.get("status") in {401, 403}:
            return (
                "SPORTDB_AUTH_BLOCKED",
                "blocked",
                f"auth_http_status_{call['status']}_{call['method'].replace('/', '_')}",
            )

    tools_present = set(tool_summaries)
    required = {
        "flashscore_list_sports",
        "flashscore_list_countries",
        "flashscore_list_competitions",
        "flashscore_list_competition_seasons",
        "flashscore_get_competition_results",
        "flashscore_get_competition_fixtures",
        "flashscore_get_competition_standings",
        "flashscore_get_match_stats",
        "flashscore_get_match_events",
        "flashscore_get_match_lineups",
    }
    missing = sorted(required - tools_present)
    if not tool_summaries:
        return (
            "SPORTDB_MCP_SCHEMA_BLOCKED",
            "blocked",
            "no_tool_schemas_extracted",
        )
    if missing:
        return (
            "SPORTDB_MCP_SCHEMA_PARTIAL",
            "sportdb_multisport_mapping",
            f"missing_required_tools:{','.join(missing)}",
        )

    multisport_ready = any(
        summary.get("sport_parameter_support")
        for summary in tool_summaries.values()
    )
    if multisport_ready:
        return (
            "SPORTDB_MCP_SCHEMA_READY_FOR_FOOTBALL_MAPPING",
            "sportdb_mcp_football_mapping",
            None,
        )
    return (
        "SPORTDB_MCP_SCHEMA_READY_FOR_MULTISPORT_MAPPING",
        "sportdb_multisport_mapping",
        None,
    )


@dataclass
class HTTPResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


def build_call_record(method: str, response: HTTPResponse, parsed_payload: Any) -> dict[str, Any]:
    content_type = response.headers.get("Content-Type", "")
    response_mode = detect_response_mode(content_type)
    primary_payload = extract_primary_payload(response_mode, parsed_payload)
    error = None
    jsonrpc_id = None

    if isinstance(primary_payload, dict):
        if primary_payload.get("id") is not None:
            jsonrpc_id = normalize_jsonable(primary_payload.get("id"))
        if isinstance(primary_payload.get("error"), dict):
            error = {
                "code": primary_payload["error"].get("code"),
                "message": primary_payload["error"].get("message"),
            }

    names = extract_names_for_method(method, primary_payload)
    schemas_returned: list[str] = []
    if method == "tools/list":
        for tool in extract_tools(primary_payload):
            if extract_schema(tool):
                schemas_returned.append(str(tool.get("name") or ""))

    return {
        "method": method,
        "status": response.status_code,
        "content_type": content_type,
        "response_mode": response_mode,
        "raw_response_sha256": hashlib.sha256(response.content).hexdigest(),
        "jsonrpc_id": jsonrpc_id,
        "error": error,
        "names": names,
        "schemas_returned": [name for name in schemas_returned if name],
        "rate_limit_headers": rate_headers(dict(response.headers)),
        "payload": normalize_jsonable(parsed_payload),
        "primary_payload": normalize_jsonable(primary_payload),
    }


class MCPProbe:
    def __init__(
        self,
        api_key: str,
        timeout: int,
        protocol_version: str,
        max_tool_calls: int,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.protocol_version = protocol_version
        self.max_tool_calls = max_tool_calls
        self.calls_made = 0
        self.tool_calls_made = 0
        self.session_calls_made = 0
        self.stopped_on_429 = False
        self.last_post_at = 0.0

    def post_jsonrpc(self, method: str, params: dict[str, Any], rpc_id: str) -> dict[str, Any]:
        if self.stopped_on_429:
            raise RuntimeError("SportDB probe already stopped on 429")
        if method == "tools/call" and self.tool_calls_made >= self.max_tool_calls:
            raise RuntimeError("SportDB MCP call budget exceeded")
        if method == "tools/call":
            elapsed = time.monotonic() - self.last_post_at
            if elapsed < 0.4:
                time.sleep(0.4 - elapsed)

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": ACCEPT_HEADER,
            "MCP-Protocol-Version": self.protocol_version,
            "User-Agent": USER_AGENT,
        }
        body = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": method,
            "params": params,
        }

        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as raw_response:
                response = HTTPResponse(
                    status_code=raw_response.status,
                    headers=dict(raw_response.headers.items()),
                    content=raw_response.read(),
                )
        except urllib.error.HTTPError as exc:
            response = HTTPResponse(
                status_code=exc.code,
                headers=dict(exc.headers.items()) if exc.headers is not None else {},
                content=exc.read() if exc.fp is not None else b"",
            )
        self.last_post_at = time.monotonic()
        self.calls_made += 1
        if method == "tools/call":
            self.tool_calls_made += 1
        else:
            self.session_calls_made += 1

        if response.status_code == 429:
            self.stopped_on_429 = True

        response_mode = detect_response_mode(response.headers.get("Content-Type", ""))
        if response_mode == "json":
            try:
                parsed_payload: Any = response.json()
            except ValueError:
                parsed_payload = {"_non_json": True, "text_preview": response.text[:1000]}
        elif response_mode == "sse":
            events, payloads = parse_sse_payloads(response.text)
            parsed_payload = {"events": events, "payloads": payloads}
        else:
            parsed_payload = {"_raw_text": response.text[:1000]}

        return build_call_record(method, response, parsed_payload)


def initialize_params(protocol_version: str) -> dict[str, Any]:
    return {
        "protocolVersion": protocol_version,
        "capabilities": {},
        "clientInfo": {"name": "bet-sportdb-probe", "version": "1.0"},
    }


def build_summary(
    previous_accepted_sha: str,
    key_name_used: str,
    key_source: str,
    calls: list[dict[str, Any]],
) -> dict[str, Any]:
    tools_call = next((call for call in calls if call["method"] == "tools/list"), None)
    resources_call = next(
        (call for call in calls if call["method"] == "resources/list"), None
    )
    prompts_call = next((call for call in calls if call["method"] == "prompts/list"), None)

    primary_payload = tools_call.get("primary_payload") if tools_call else {}
    tools = extract_tools(primary_payload)
    tool_summaries = {
        str(tool.get("name")): build_tool_schema_summary(tool)
        for tool in tools
        if tool.get("name")
    }

    tool_sequence, required_parameters = build_tool_sequence(tool_summaries)
    classification, next_step, primary_blocker = build_final_classification(
        tool_summaries, calls
    )

    response_modes = sorted(
        {
            call["response_mode"]
            for call in calls
            if call.get("response_mode") not in {None, "unknown"}
        }
    )

    return {
        "phase_id": "P2E_A2_SPORTDB_MCP_TOOL_SCHEMA_MAPPING",
        "previous_accepted_sha": previous_accepted_sha,
        "evidence_level": "TRACKED_MCP_SCHEMA_SUMMARY",
        "provider": "sportdb",
        "mcp": {
            "endpoint": ENDPOINT,
            "auth_header": "X-API-Key",
            "response_modes_observed": response_modes,
            "calls": [
                {
                    key: value
                    for key, value in call.items()
                    if key not in {"payload", "primary_payload"}
                }
                for call in calls
            ],
            "tools_count": len(tools_call["names"]) if tools_call else 0,
            "resources_count": len(resources_call["names"]) if resources_call else 0,
            "prompts_count": len(prompts_call["names"]) if prompts_call else 0,
        },
        "env_preflight": {
            "required_aliases": list(KEY_ALIASES),
            "found_key": key_name_used,
            "source": key_source,
            "secret_safe": True,
        },
        "tool_schemas": tool_summaries,
        "tool_buckets": {
            "football_mapping": football_mapping_tools(tool_summaries),
            "future_multisport": future_multisport_tools(tool_summaries),
            "not_for_canonical_enrichment_now": not_for_canonical_enrichment_now(tool_summaries),
            "utility": utility_tools(tool_summaries),
        },
        "capability_mapping": capability_mapping(tool_summaries),
        "football_mapping_plan": {
            "recommended_next_phase": "P2E_A3_SPORTDB_MCP_FOOTBALL_PROVIDER_NATIVE_MAPPING",
            "tool_sequence": tool_sequence,
            "tool_call_templates": build_tool_call_templates(),
            "required_parameters": required_parameters,
            "call_budget": {
                "max_mcp_tool_calls": 7,
                "stop_on_first_429": True,
            },
            "stop_conditions": [
                "first_429",
                "auth_failure",
                "schema_mismatch",
                "no_football_sport_key",
                "no_england_country",
                "no_premier_league_competition",
                "no_seasons",
                "empty_results_for_provider_native_selected_season",
                "no_match_id",
                "stats_unavailable",
            ],
        },
        "classification": classification,
        "next_step": next_step,
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "secret_safe": True,
        "primary_blocker": primary_blocker,
        "final_review": "NOT_RUN",
    }


def compact_result(call: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in call.items()
        if key not in {"payload", "primary_payload"}
    }


def base_mapping_summary(previous_accepted_sha: str) -> dict[str, Any]:
    return {
        "phase_id": PHASE_ID_A3,
        "prompt_version": PROMPT_VERSION_A3,
        "previous_accepted_sha": previous_accepted_sha,
        "evidence_level": "TRACKED_MCP_FOOTBALL_MAPPING_SUMMARY",
        "provider": "sportdb",
        "schema_source": {
            "path": str(FOOTBALL_MAPPING_SCHEMA_SOURCE),
            "used_for_payload_construction": True,
            "core_tools_present": [],
            "missing_core_tools": [],
        },
        "transport_contract": {
            "endpoint": ENDPOINT,
            "transport": "streamable_http_mcp",
            "auth_header": "X-API-Key",
            "required_accept": ACCEPT_HEADER,
            "content_type": "application/json",
        },
        "sport": {
            "selected_sport_key": None,
            "selected_sport_name": None,
            "selected_sport_raw": {},
            "candidates": [],
        },
        "country": {
            "target": "England",
            "selected_country_slug": None,
            "selected_country_id": None,
            "selected_country_name": None,
            "selected_country_raw": {},
            "candidates": [],
        },
        "competition": {
            "target": "Premier League",
            "selected_competition_slug": None,
            "selected_competition_id": None,
            "selected_competition_name": None,
            "selected_competition_raw": {},
            "candidates": [],
        },
        "season": {
            "selected_season": None,
            "selected_season_raw": {},
            "observed_seasons": [],
        },
        "finished_match_probe": {
            "selected_match_id": None,
            "selected_match_name": None,
            "selected_match_status": None,
            "selected_match_score": None,
            "selected_match_raw": {},
            "results_pages_checked": [],
            "fixtures_fallback_used": False,
        },
        "stats_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "top_level_keys": [],
            "stat_group_names": [],
            "stat_field_names": [],
            "team_side_detection": "UNKNOWN",
            "safe_preview": {},
        },
        "events_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "top_level_keys": [],
            "safe_preview": {},
        },
        "lineups_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "top_level_keys": [],
            "safe_preview": {},
        },
        "standings_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "top_level_keys": [],
            "safe_preview": {},
        },
        "mcp_calls": [],
        "call_budget": {
            "max_mcp_tool_calls": MCP_MAPPING_CALL_BUDGET,
            "mcp_tool_calls_made": 0,
            "mcp_session_calls_made": 0,
            "rest_calls_made": 0,
            "stopped_on_429": False,
        },
        "classification": "UNKNOWN",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": "NOT_CERTIFIED_FOOTBALL_MAPPING_ONLY",
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": [],
        "secret_safe": True,
        "final_review": "PASS",
    }


def set_mapping_classification(
    summary: dict[str, Any], classification: str, blocker: str | None = None
) -> None:
    summary["classification"] = classification
    if classification == CLASSIFICATION_READY:
        summary["next_step"] = "P2E_A4_SPORTDB_SHADOW_ADAPTER_MINIMAL"
    elif classification == CLASSIFICATION_PARTIAL:
        summary["next_step"] = "P2E_A4_SPORTDB_SHADOW_ADAPTER_MINIMAL_STATS_ONLY"
    else:
        summary["next_step"] = "blocked_or_retry_after_review"
    if blocker:
        summary["blockers"].append(blocker)


def update_call_budget(summary: dict[str, Any], probe: MCPProbe) -> None:
    summary["call_budget"]["mcp_tool_calls_made"] = probe.tool_calls_made
    summary["call_budget"]["mcp_session_calls_made"] = probe.session_calls_made
    summary["call_budget"]["stopped_on_429"] = probe.stopped_on_429


def build_mcp_call_entry(
    call: dict[str, Any], tool_name: str, payload: dict[str, Any], result_payload: Any
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "status": call.get("status"),
        "response_mode": call.get("response_mode"),
        "raw_response_sha256": call.get("raw_response_sha256"),
        "request_payload": normalize_jsonable(payload),
        "top_level_keys": extract_top_level_keys(result_payload),
        "safe_preview": safe_preview(result_payload, max_chars=1000),
        "error": call.get("error"),
    }


def embedded_upstream_status(result_payload: Any) -> int | None:
    if isinstance(result_payload, dict):
        source_status = result_payload.get("source_status_code")
        if isinstance(source_status, int):
            return source_status
    text = ""
    if isinstance(result_payload, str):
        text = result_payload
    elif isinstance(result_payload, dict):
        text = json.dumps(normalize_jsonable(result_payload), ensure_ascii=True)
    match = re.search(r"\((401|403|406|429)\)", text)
    if match:
        return int(match.group(1))
    match = re.search(r'"source_status_code"\s*:\s*(401|403|406|429)', text)
    if match:
        return int(match.group(1))
    return None


def invoke_tool(
    probe: MCPProbe,
    summary: dict[str, Any],
    tool_name: str,
    payload: dict[str, Any],
    rpc_suffix: str,
) -> tuple[dict[str, Any], Any]:
    call = probe.post_jsonrpc(
        "tools/call",
        {"name": tool_name, "arguments": payload},
        f"tools-call-{rpc_suffix}",
    )
    primary_payload = call.get("primary_payload")
    if call.get("response_mode") == "sse":
        payloads = call.get("payload", {}).get("payloads")
        if not isinstance(payloads, list) or not payloads:
            raise RuntimeError(CLASSIFICATION_SSE_DEFECT)
    result_payload = extract_tool_result_payload(primary_payload)
    summary["mcp_calls"].append(
        build_mcp_call_entry(call, tool_name=tool_name, payload=payload, result_payload=result_payload)
    )
    update_call_budget(summary, probe)
    return call, result_payload


def evaluate_hard_failure(
    summary: dict[str, Any], call: dict[str, Any], result_payload: Any | None = None
) -> str | None:
    status = call.get("status")
    embedded_status = embedded_upstream_status(result_payload) if result_payload is not None else None
    if embedded_status in {401, 403}:
        set_mapping_classification(summary, CLASSIFICATION_AUTH, f"upstream_status_{embedded_status}")
        return CLASSIFICATION_AUTH
    if embedded_status == 429:
        set_mapping_classification(summary, CLASSIFICATION_RATE_LIMIT, "upstream_status_429")
        return CLASSIFICATION_RATE_LIMIT
    if embedded_status == 406:
        set_mapping_classification(summary, CLASSIFICATION_ACCEPT_DEFECT, "upstream_status_406")
        return CLASSIFICATION_ACCEPT_DEFECT
    if status in {401, 403}:
        set_mapping_classification(summary, CLASSIFICATION_AUTH, f"http_status_{status}")
        return CLASSIFICATION_AUTH
    if status == 429:
        set_mapping_classification(summary, CLASSIFICATION_RATE_LIMIT, "http_status_429")
        return CLASSIFICATION_RATE_LIMIT
    if status == 406:
        set_mapping_classification(summary, CLASSIFICATION_ACCEPT_DEFECT, "http_status_406")
        return CLASSIFICATION_ACCEPT_DEFECT
    if isinstance(status, int) and status >= 500:
        set_mapping_classification(summary, CLASSIFICATION_TRANSPORT, f"http_status_{status}")
        return CLASSIFICATION_TRANSPORT
    if call.get("response_mode") == "unknown":
        set_mapping_classification(summary, CLASSIFICATION_TRANSPORT, "unknown_response_mode")
        return CLASSIFICATION_TRANSPORT
    return None


def collect_selector_candidates(items: Any, allowed: set[str], blocked: set[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        values = {normalize_token(value) for value in extract_candidate_strings(item)}
        if values & allowed and not values & blocked:
            candidates.append(normalize_jsonable(item))
    return candidates


def stat_group_names(payload: Any) -> list[str]:
    groups: set[str] = set()
    for item in walk_dicts(payload):
        for key in ("group", "group_name", "category", "section", "period"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                groups.add(value.strip())
    return sorted(groups)


def detect_team_sides(payload: Any) -> str:
    names = {normalize_token(name) for name in extract_stat_field_names(payload)}
    blob = normalize_token(json.dumps(normalize_jsonable(payload), ensure_ascii=True))
    if "home" in names or "away" in names or "home" in blob or "away" in blob:
        return "DETECTED_HOME_AWAY"
    if "team 1" in blob or "team 2" in blob:
        return "DETECTED_GENERIC_TEAMS"
    return "UNKNOWN"


def ensure_core_tools(summary: dict[str, Any], schema_summary: dict[str, Any]) -> bool:
    present = [tool_name for tool_name in CORE_MAPPING_TOOLS if get_tool_schema(schema_summary, tool_name)]
    missing = [tool_name for tool_name in CORE_MAPPING_TOOLS if tool_name not in present]
    summary["schema_source"]["core_tools_present"] = present
    summary["schema_source"]["missing_core_tools"] = missing
    if missing:
        set_mapping_classification(summary, CLASSIFICATION_SCHEMA_INCOMPLETE, "missing_core_tools")
        return False
    return True


def build_known_values_from_entities(
    sport: dict[str, Any] | None,
    country: dict[str, Any] | None,
    competition: dict[str, Any] | None,
    season: dict[str, Any] | None,
    match: dict[str, Any] | None,
    page: int | None = None,
) -> dict[str, Any]:
    known_values: dict[str, Any] = {}
    if sport:
        fields = extract_entity_fields(sport, "sport")
        known_values.update(
            {
                "sport_key": fields.get("key"),
                "sport_slug": fields.get("slug"),
                "sport_name": fields.get("name"),
            }
        )
    if country:
        fields = extract_entity_fields(country, "country")
        known_values.update(
            {
                "country_slug": fields.get("slug"),
                "country_id": fields.get("id"),
                "country_name": fields.get("name"),
            }
        )
    if competition:
        fields = extract_entity_fields(competition, "competition")
        known_values.update(
            {
                "competition_slug": fields.get("slug"),
                "competition_id": fields.get("id"),
                "competition_name": fields.get("name"),
            }
        )
    if season:
        fields = extract_entity_fields(season, "season")
        known_values.update(
            {
                "season": fields.get("season"),
                "season_id": fields.get("id"),
                "season_name": fields.get("name"),
                "season_value": fields.get("value"),
            }
        )
    if match:
        fields = extract_match_fields(match)
        known_values["match_id"] = fields.get("id")
    if page is not None:
        known_values["page"] = page
    return {key: value for key, value in known_values.items() if value not in (None, "")}


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def run_mcp_football_mapping(args: argparse.Namespace, probe: MCPProbe) -> int:
    summary = base_mapping_summary(args.previous_accepted_sha)
    try:
        schema_summary = load_p2e_a2_schema_summary(FOOTBALL_MAPPING_SCHEMA_SOURCE)
    except FileNotFoundError:
        set_mapping_classification(summary, CLASSIFICATION_SCHEMA_INCOMPLETE, "missing_schema_summary")
        write_summary(Path(args.out), summary)
        print(json.dumps({"classification": summary["classification"], "mcp_tool_calls_made": 0, "rest_calls_made": 0}))
        return 1

    if not ensure_core_tools(summary, schema_summary):
        write_summary(Path(args.out), summary)
        print(json.dumps({"classification": summary["classification"], "mcp_tool_calls_made": 0, "rest_calls_made": 0}))
        return 1

    try:
        probe.post_jsonrpc("initialize", initialize_params(args.protocol_version), "initialize-1")
        update_call_budget(summary, probe)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        set_mapping_classification(summary, CLASSIFICATION_TRANSPORT, "initialize_failed")
        write_summary(Path(args.out), summary)
        print(json.dumps({"classification": summary["classification"], "mcp_tool_calls_made": probe.tool_calls_made, "rest_calls_made": 0}))
        return 1

    sport = None
    country = None
    competition = None
    season = None
    match = None

    try:
        tool_schema = get_tool_schema(schema_summary, "flashscore_list_sports")
        payload = build_tool_payload(tool_schema, {})
        call, result_payload = invoke_tool(probe, summary, "flashscore_list_sports", payload, "sport-1")
        failure = evaluate_hard_failure(summary, call, result_payload)
        if failure:
            raise RuntimeError(failure)
        items = top_level_items(result_payload)
        summary["sport"]["candidates"] = collect_selector_candidates(items, {"football", "soccer"}, set())
        sport = select_football_sport(items)
        if sport is None:
            set_mapping_classification(summary, CLASSIFICATION_NO_SPORT, "no_football_sport_key")
            raise RuntimeError(CLASSIFICATION_NO_SPORT)
        sport_fields = extract_entity_fields(sport, "sport")
        summary["sport"]["selected_sport_key"] = sport_fields.get("key")
        summary["sport"]["selected_sport_name"] = sport_fields.get("name")
        summary["sport"]["selected_sport_raw"] = normalize_jsonable(sport)

        tool_schema = get_tool_schema(schema_summary, "flashscore_list_countries")
        payload = build_tool_payload(tool_schema, build_known_values_from_entities(sport, None, None, None, None))
        call, result_payload = invoke_tool(probe, summary, "flashscore_list_countries", payload, "country-2")
        failure = evaluate_hard_failure(summary, call, result_payload)
        if failure:
            raise RuntimeError(failure)
        items = top_level_items(result_payload)
        summary["country"]["candidates"] = collect_selector_candidates(
            items,
            {"england"},
            {"united kingdom", "great britain", "scotland", "wales", "northern ireland"},
        )
        country = select_england_country(items)
        if country is None:
            set_mapping_classification(summary, CLASSIFICATION_NO_COUNTRY, "no_england_country")
            raise RuntimeError(CLASSIFICATION_NO_COUNTRY)
        country_fields = extract_entity_fields(country, "country")
        summary["country"]["selected_country_slug"] = country_fields.get("slug")
        summary["country"]["selected_country_id"] = country_fields.get("id")
        summary["country"]["selected_country_name"] = country_fields.get("name")
        summary["country"]["selected_country_raw"] = normalize_jsonable(country)

        tool_schema = get_tool_schema(schema_summary, "flashscore_list_competitions")
        payload = build_tool_payload(tool_schema, build_known_values_from_entities(sport, country, None, None, None))
        call, result_payload = invoke_tool(probe, summary, "flashscore_list_competitions", payload, "competition-3")
        failure = evaluate_hard_failure(summary, call, result_payload)
        if failure:
            raise RuntimeError(failure)
        items = top_level_items(result_payload)
        summary["competition"]["candidates"] = collect_selector_candidates(
            items,
            {"premier league", "premier-league"},
            {"championship", "women super league", "premier league cup", "u21 premier league", "premier league 2"},
        )
        competition = select_premier_league_competition(items)
        if competition is None:
            set_mapping_classification(summary, CLASSIFICATION_NO_COMPETITION, "no_premier_league")
            raise RuntimeError(CLASSIFICATION_NO_COMPETITION)
        competition_fields = extract_entity_fields(competition, "competition")
        summary["competition"]["selected_competition_slug"] = competition_fields.get("slug")
        summary["competition"]["selected_competition_id"] = competition_fields.get("id")
        summary["competition"]["selected_competition_name"] = competition_fields.get("name")
        summary["competition"]["selected_competition_raw"] = normalize_jsonable(competition)

        tool_schema = get_tool_schema(schema_summary, "flashscore_list_competition_seasons")
        payload = build_tool_payload(
            tool_schema,
            build_known_values_from_entities(sport, country, competition, None, None),
        )
        call, result_payload = invoke_tool(probe, summary, "flashscore_list_competition_seasons", payload, "season-4")
        failure = evaluate_hard_failure(summary, call, result_payload)
        if failure:
            raise RuntimeError(failure)
        items = top_level_items(result_payload)
        summary["season"]["observed_seasons"] = [normalize_jsonable(item) for item in items if isinstance(item, dict)]
        season = select_completed_or_result_season(items)
        if season is None:
            set_mapping_classification(summary, CLASSIFICATION_NO_SEASONS, "no_seasons")
            raise RuntimeError(CLASSIFICATION_NO_SEASONS)
        season_fields = extract_entity_fields(season, "season")
        summary["season"]["selected_season"] = season_fields.get("season")
        summary["season"]["selected_season_raw"] = normalize_jsonable(season)

        tool_schema = get_tool_schema(schema_summary, "flashscore_get_competition_results")
        results_supports_page = "page" in (tool_schema.get("optional_fields") or [])
        result_pages = [1, 2, 3] if results_supports_page else [None]
        for page in result_pages:
            payload = build_tool_payload(
                tool_schema,
                build_known_values_from_entities(sport, country, competition, season, None, page=page),
            )
            suffix = f"results-5-{page or 1}"
            call, result_payload = invoke_tool(probe, summary, "flashscore_get_competition_results", payload, suffix)
            failure = evaluate_hard_failure(summary, call, result_payload)
            if failure:
                raise RuntimeError(failure)
            items = top_level_items(result_payload)
            summary["finished_match_probe"]["results_pages_checked"].append(page or 1)
            match = select_finished_match(items)
            if match is not None:
                break

        if match is None and get_tool_schema(schema_summary, "flashscore_get_competition_fixtures"):
            summary["finished_match_probe"]["fixtures_fallback_used"] = True
            tool_schema = get_tool_schema(schema_summary, "flashscore_get_competition_fixtures")
            payload = build_tool_payload(
                tool_schema,
                build_known_values_from_entities(sport, country, competition, season, None, page=1),
            )
            call, result_payload = invoke_tool(probe, summary, "flashscore_get_competition_fixtures", payload, "fixtures-fallback-5")
            failure = evaluate_hard_failure(summary, call, result_payload)
            if failure:
                raise RuntimeError(failure)

        if match is None:
            set_mapping_classification(summary, CLASSIFICATION_NO_MATCH, "no_finished_match_id")
            raise RuntimeError(CLASSIFICATION_NO_MATCH)

        match_fields = extract_match_fields(match)
        summary["finished_match_probe"]["selected_match_id"] = match_fields.get("id")
        summary["finished_match_probe"]["selected_match_name"] = match_fields.get("name")
        summary["finished_match_probe"]["selected_match_status"] = match_fields.get("status")
        summary["finished_match_probe"]["selected_match_score"] = match_fields.get("score")
        summary["finished_match_probe"]["selected_match_raw"] = normalize_jsonable(match)

        tool_schema = get_tool_schema(schema_summary, "flashscore_get_match_stats")
        payload = build_tool_payload(tool_schema, build_known_values_from_entities(sport, country, competition, season, match))
        summary["stats_probe"]["performed"] = True
        call, result_payload = invoke_tool(probe, summary, "flashscore_get_match_stats", payload, "stats-6")
        failure = evaluate_hard_failure(summary, call, result_payload)
        if failure:
            raise RuntimeError(failure)
        summary["stats_probe"]["available"] = True
        summary["stats_probe"]["raw_response_sha256"] = call.get("raw_response_sha256") or sha256_jsonable(result_payload)
        summary["stats_probe"]["top_level_keys"] = extract_top_level_keys(result_payload)
        summary["stats_probe"]["stat_group_names"] = stat_group_names(result_payload)
        summary["stats_probe"]["stat_field_names"] = extract_stat_field_names(result_payload)
        summary["stats_probe"]["team_side_detection"] = detect_team_sides(result_payload)
        summary["stats_probe"]["safe_preview"] = safe_preview(result_payload)
        if not summary["stats_probe"]["top_level_keys"] and not summary["stats_probe"]["stat_field_names"]:
            summary["stats_probe"]["available"] = False
            set_mapping_classification(summary, CLASSIFICATION_NO_STATS, "stats_unavailable")
            raise RuntimeError(CLASSIFICATION_NO_STATS)

        optional_statuses: list[bool] = []
        for tool_name, key_name, rpc_suffix in (
            ("flashscore_get_match_events", "events_probe", "events-7"),
            ("flashscore_get_match_lineups", "lineups_probe", "lineups-8"),
            ("flashscore_get_competition_standings", "standings_probe", "standings-9"),
        ):
            tool_schema = get_tool_schema(schema_summary, tool_name)
            if not tool_schema or probe.tool_calls_made >= MCP_MAPPING_CALL_BUDGET:
                continue
            summary[key_name]["performed"] = True
            known_values = build_known_values_from_entities(sport, country, competition, season, match)
            payload = build_tool_payload(tool_schema, known_values)
            call, result_payload = invoke_tool(probe, summary, tool_name, payload, rpc_suffix)
            failure = evaluate_hard_failure(summary, call, result_payload)
            if failure:
                raise RuntimeError(failure)
            available = bool(extract_top_level_keys(result_payload) or top_level_items(result_payload))
            summary[key_name]["available"] = available
            summary[key_name]["raw_response_sha256"] = call.get("raw_response_sha256") or sha256_jsonable(result_payload)
            summary[key_name]["top_level_keys"] = extract_top_level_keys(result_payload)
            summary[key_name]["safe_preview"] = safe_preview(result_payload)
            optional_statuses.append(available)

        if optional_statuses and all(optional_statuses):
            set_mapping_classification(summary, CLASSIFICATION_READY)
        else:
            set_mapping_classification(summary, CLASSIFICATION_PARTIAL)
    except RequiredPayloadFieldUnknownError as exc:
        set_mapping_classification(summary, CLASSIFICATION_REQUIRED_UNKNOWN, exc.field_name)
    except RuntimeError as exc:
        if str(exc) not in ALL_A3_CLASSIFICATIONS and summary["classification"] == "UNKNOWN":
            set_mapping_classification(summary, CLASSIFICATION_TRANSPORT, str(exc))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        set_mapping_classification(summary, CLASSIFICATION_TRANSPORT, exc.__class__.__name__)

    update_call_budget(summary, probe)
    write_summary(Path(args.out), summary)
    print(
        json.dumps(
            {
                "classification": summary["classification"],
                "mcp_tool_calls_made": summary["call_budget"]["mcp_tool_calls_made"],
                "rest_calls_made": 0,
                "selected_sport_key": summary["sport"]["selected_sport_key"] or "UNKNOWN",
                "selected_country_id": summary["country"]["selected_country_id"] or "UNKNOWN",
                "selected_competition_id": summary["competition"]["selected_competition_id"] or "UNKNOWN",
                "selected_season": summary["season"]["selected_season"] or "UNKNOWN",
                "selected_match_id": summary["finished_match_probe"]["selected_match_id"] or "UNKNOWN",
            }
        )
    )
    return 0 if summary["classification"] in {CLASSIFICATION_READY, CLASSIFICATION_PARTIAL} else 1


def run_single_command(command: str, probe: MCPProbe, protocol_version: str) -> dict[str, Any]:
    if command == "mcp-tools-list":
        return probe.post_jsonrpc("tools/list", {}, "tools-list-1")
    if command == "mcp-resources-list":
        return probe.post_jsonrpc("resources/list", {}, "resources-list-1")
    if command == "mcp-prompts-list":
        return probe.post_jsonrpc("prompts/list", {}, "prompts-list-1")
    if command == "mcp-initialize":
        return probe.post_jsonrpc(
            "initialize",
            initialize_params(protocol_version),
            "initialize-1",
        )
    raise ValueError(f"Unsupported command: {command}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a bounded SportDB MCP schema probe."
    )
    parser.add_argument(
        "command",
        choices=[
            "mcp-initialize",
            "mcp-tools-list",
            "mcp-resources-list",
            "mcp-prompts-list",
            "mcp-tool-schema-summary",
            "mcp-football-mapping",
        ],
        help="Probe command to execute.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Summary output path for tracked summary commands.",
    )
    parser.add_argument(
        "--previous-accepted-sha",
        default="4fa7dec9ae4dff5ca1aff8e3d7b850df10a22eef",
        help="Accepted SHA to record in the tracked summary.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT_SECONDS,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--protocol-version",
        default=MCP_PROTOCOL_VERSION,
        help="MCP-Protocol-Version header value.",
    )
    parser.add_argument(
        "--skip-initialize",
        action="store_true",
        help="Skip initialize before bounded summary collection.",
    )
    args = parser.parse_args()
    if args.out is None:
        if args.command == "mcp-football-mapping":
            args.out = str(FOOTBALL_MAPPING_SUMMARY_PATH)
        else:
            args.out = str(SUMMARY_PATH)
    return args


def main() -> int:
    args = parse_args()
    api_key, key_name_used, key_source = resolve_api_key()

    if not api_key:
        if args.command in {"mcp-tool-schema-summary", "mcp-football-mapping"}:
            if args.command == "mcp-football-mapping":
                summary = base_mapping_summary(args.previous_accepted_sha)
                set_mapping_classification(summary, CLASSIFICATION_AUTH, "missing_api_key")
                write_summary(Path(args.out), summary)
                print(
                    json.dumps(
                        {
                            "classification": CLASSIFICATION_AUTH,
                            "mcp_tool_calls_made": 0,
                            "rest_calls_made": 0,
                            "selected_sport_key": "UNKNOWN",
                            "selected_country_id": "UNKNOWN",
                            "selected_competition_id": "UNKNOWN",
                            "selected_season": "UNKNOWN",
                            "selected_match_id": "UNKNOWN",
                        }
                    )
                )
                return 1
            summary = {
                "phase_id": PHASE_ID_A2,
                "previous_accepted_sha": args.previous_accepted_sha,
                "evidence_level": "TRACKED_MCP_SCHEMA_SUMMARY",
                "provider": "sportdb",
                "mcp": {
                    "endpoint": ENDPOINT,
                    "auth_header": "X-API-Key",
                    "response_modes_observed": [],
                    "calls": [],
                    "tools_count": 0,
                    "resources_count": 0,
                    "prompts_count": 0,
                },
                "tool_schemas": {},
                "tool_buckets": {
                    "football_mapping": [],
                    "future_multisport": [],
                    "not_for_canonical_enrichment_now": [],
                    "utility": [],
                },
                "capability_mapping": {
                    "current_discovery": [],
                    "standings": [],
                    "current_form": [],
                    "historical_form_h2h": [],
                    "detailed_metrics": [],
                    "auxiliary_lineups_events": [],
                },
                "football_mapping_plan": {
                    "recommended_next_phase": "P2E_A3_SPORTDB_MCP_FOOTBALL_PROVIDER_NATIVE_MAPPING",
                    "tool_sequence": [],
                    "required_parameters": {},
                    "call_budget": {
                        "max_mcp_tool_calls": 7,
                        "stop_on_first_429": True,
                    },
                    "stop_conditions": ["auth_failure"],
                },
                "classification": "SPORTDB_AUTH_BLOCKED",
                "next_step": "blocked",
                "impact_on_p2d": "none_highlightly_remains_accepted",
                "secret_safe": True,
                "final_review": "NOT_RUN",
            }
            Path(args.out).write_text(
                json.dumps(summary, indent=2) + "\n", encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "classification": "SPORTDB_AUTH_BLOCKED",
                        "tools_count": 0,
                        "resources_count": 0,
                        "prompts_count": 0,
                    }
                )
            )
            return 1

        print(json.dumps({"error": "SPORTDB_KEY_MISSING"}))
        return 1

    max_tool_calls = (
        MCP_MAPPING_CALL_BUDGET if args.command == "mcp-football-mapping" else MCP_SCHEMA_CALL_BUDGET
    )
    probe = MCPProbe(
        api_key,
        timeout=args.timeout,
        protocol_version=args.protocol_version,
        max_tool_calls=max_tool_calls,
    )

    if args.command == "mcp-football-mapping":
        return run_mcp_football_mapping(args, probe)

    if args.command != "mcp-tool-schema-summary":
        try:
            call = run_single_command(args.command, probe, args.protocol_version)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            print(
                json.dumps(
                    {"command": args.command, "transport_error": exc.__class__.__name__}
                )
            )
            return 1
        print(json.dumps(compact_result(call), indent=2))
        return 0 if call["status"] < 400 else 1

    calls: list[dict[str, Any]] = []
    try:
        if not args.skip_initialize:
            calls.append(
                probe.post_jsonrpc(
                    "initialize",
                    initialize_params(args.protocol_version),
                    "initialize-1",
                )
            )

        if not probe.stopped_on_429:
            calls.append(probe.post_jsonrpc("tools/list", {}, "tools-list-2"))

        tools_call = next(
            (call for call in calls if call["method"] == "tools/list"), None
        )
        tools_ok = bool(tools_call and tools_call["status"] < 400)

        if not probe.stopped_on_429 and tools_ok:
            calls.append(probe.post_jsonrpc("resources/list", {}, "resources-list-3"))

        if not probe.stopped_on_429 and tools_ok:
            calls.append(probe.post_jsonrpc("prompts/list", {}, "prompts-list-4"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        output = {
            "phase_id": "P2E_A2_SPORTDB_MCP_TOOL_SCHEMA_MAPPING",
            "previous_accepted_sha": args.previous_accepted_sha,
            "evidence_level": "TRACKED_MCP_SCHEMA_SUMMARY",
            "provider": "sportdb",
            "mcp": {
                "endpoint": ENDPOINT,
                "auth_header": "X-API-Key",
                "response_modes_observed": [],
                "calls": [],
                "tools_count": 0,
                "resources_count": 0,
                "prompts_count": 0,
            },
            "tool_schemas": {},
            "tool_buckets": {
                "football_mapping": [],
                "future_multisport": [],
                "not_for_canonical_enrichment_now": [],
                "utility": [],
            },
            "capability_mapping": {
                "current_discovery": [],
                "standings": [],
                "current_form": [],
                "historical_form_h2h": [],
                "detailed_metrics": [],
                "auxiliary_lineups_events": [],
            },
            "football_mapping_plan": {
                "recommended_next_phase": "P2E_A3_SPORTDB_MCP_FOOTBALL_PROVIDER_NATIVE_MAPPING",
                "tool_sequence": [],
                "required_parameters": {},
                "call_budget": {
                    "max_mcp_tool_calls": 7,
                    "stop_on_first_429": True,
                },
                "stop_conditions": ["transport_error"],
            },
            "classification": "SPORTDB_MCP_SCHEMA_BLOCKED",
            "next_step": "blocked",
            "impact_on_p2d": "none_highlightly_remains_accepted",
            "secret_safe": True,
            "final_review": "NOT_RUN",
            "primary_blocker": f"transport_error:{exc.__class__.__name__}",
        }
        Path(args.out).write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "classification": output["classification"],
                    "tools_count": 0,
                    "resources_count": 0,
                    "prompts_count": 0,
                }
            )
        )
        return 1

    summary = build_summary(
        previous_accepted_sha=args.previous_accepted_sha,
        key_name_used=key_name_used,
        key_source=key_source,
        calls=calls,
    )
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "classification": summary["classification"],
                "tools_count": summary["mcp"]["tools_count"],
                "resources_count": summary["mcp"]["resources_count"],
                "prompts_count": summary["mcp"]["prompts_count"],
                "response_modes_observed": summary["mcp"]["response_modes_observed"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
