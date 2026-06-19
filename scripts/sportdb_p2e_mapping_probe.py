#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENDPOINT = "https://api.sportdb.dev/mcp/"
USER_AGENT = "bet-sportdb-probe/1.0"
MCP_PROTOCOL_VERSION = "2025-06-18"
MCP_CALL_BUDGET = 4
TIMEOUT_SECONDS = 30
KEY_ALIASES = ("SPORTDB_API_KEY", "SPORTDB_KEY")
SUMMARY_PATH = Path("certification/football/p2e_sportdb_mcp_schema_summary.json")

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
    def __init__(self, api_key: str, timeout: int, protocol_version: str):
        self.api_key = api_key
        self.timeout = timeout
        self.protocol_version = protocol_version
        self.calls_made = 0
        self.stopped_on_429 = False

    def post_jsonrpc(self, method: str, params: dict[str, Any], rpc_id: str) -> dict[str, Any]:
        if self.stopped_on_429:
            raise RuntimeError("SportDB probe already stopped on 429")
        if self.calls_made >= MCP_CALL_BUDGET:
            raise RuntimeError("SportDB MCP call budget exceeded")

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
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
        self.calls_made += 1

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
        ],
        help="Probe command to execute.",
    )
    parser.add_argument(
        "--out",
        default=str(SUMMARY_PATH),
        help="Summary output path for mcp-tool-schema-summary.",
    )
    parser.add_argument(
        "--previous-accepted-sha",
        default="5acd3bf4ce7bc0b8bc900ada0c13e70c588bdc02",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key, key_name_used, key_source = resolve_api_key()

    if not api_key:
        if args.command == "mcp-tool-schema-summary":
            summary = {
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

    probe = MCPProbe(api_key, timeout=args.timeout, protocol_version=args.protocol_version)

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
