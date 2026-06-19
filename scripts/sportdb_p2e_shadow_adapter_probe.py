#!/usr/bin/env python3
"""SportDB P2E Shadow Adapter Probe Script.

Executes shadow adapter calls and writes the tracked summary file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

# Add src to python path to import SportDBMCPShadowAdapter
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.api_clients.sportdb_mcp import (
    SportDBMCPShadowAdapter,
    SportDBMCPAuthError,
    SportDBMCPRateLimitError,
    SportDBMCPNotAcceptableError,
    SportDBMCPServerError,
    SportDBMCPParserError,
    RequiredPayloadFieldUnknownError,
    SportDBMCPError,
)


def parse_dot_env(file_path: Path) -> dict[str, str]:
    env_dict: dict[str, str] = {}
    if not file_path.exists():
        return env_dict
    try:
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
    except Exception:
        pass
    return env_dict


def normalize_jsonable(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    return str(value)


def redact_text(value: str) -> str:
    redacted = value.replace("SPORTDB_API_KEY", "REDACTED_KEY_NAME")
    for alias in ("SPORTDB_API_KEY", "SPORTDB_KEY"):
        secret = os.environ.get(alias, "")
        if secret:
            redacted = redacted.replace(secret, "REDACTED")
    
    # Also redact from dot_env
    dot_env = parse_dot_env(Path(".env"))
    for alias in ("SPORTDB_API_KEY", "SPORTDB_KEY"):
        secret = dot_env.get(alias, "")
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        default="certification/football/p2e_sportdb_shadow_adapter_summary.json",
        help="Output summary file path",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Initialize summary keys
    summary: dict[str, Any] = {
        "phase_id": "P2E_A4_SPORTDB_SHADOW_ADAPTER_MINIMAL",
        "prompt_version": "v3_scope_locked_corrective_with_kilo_archive_delete",
        "previous_accepted_sha": "25db7518569384858969b545d82b46e10eb87206",
        "evidence_level": "TRACKED_MCP_SHADOW_ADAPTER_SUMMARY",
        "provider": "sportdb",
        "adapter": {
            "module": "src/bet/api_clients/sportdb_mcp.py",
            "class": "SportDBMCPShadowAdapter",
            "parser_version": "sportdb-mcp-shadow-adapter-v1",
            "production_registered": False,
            "routing_registered": False,
        },
        "mapping_source": {
            "path": "certification/football/p2e_sportdb_mcp_football_mapping_summary.json",
            "loaded": False,
            "selected_sport_key": None,
            "selected_country_slug": None,
            "selected_country_id": None,
            "selected_competition_slug": None,
            "selected_competition_id": None,
            "selected_season": None,
            "selected_match_id": None,
        },
        "schema_source": {
            "path": "certification/football/p2e_sportdb_mcp_schema_summary.json",
            "loaded": False,
            "used_for_payload_construction": True,
        },
        "results_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "accepted_count": 0,
            "rejected_count": 0,
            "safe_preview": {},
        },
        "stats_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "provider_match_id": None,
            "top_level_keys": [],
            "raw_stat_field_names": [],
            "normalized_metric_names": [],
            "unknown_metrics": [],
            "team_side_detection": "UNKNOWN",
            "safe_preview": {},
        },
        "events_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "event_count": 0,
            "event_type_names": [],
            "goal_count": None,
            "card_count": None,
            "safe_preview": {},
        },
        "lineups_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "formation_values": [],
            "player_count": None,
            "safe_preview": {},
        },
        "standings_probe": {
            "performed": False,
            "available": False,
            "raw_response_sha256": None,
            "row_count": 0,
            "team_names": [],
            "safe_preview": {},
        },
        "call_budget": {
            "max_mcp_tool_calls": 5,
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
            "verdict": "NOT_CERTIFIED_SHADOW_ADAPTER_ONLY",
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": [],
        "secret_safe": True,
        "final_review": "PASS",
    }

    # Step 1: Initialize Shadow Adapter
    adapter = None
    try:
        adapter = SportDBMCPShadowAdapter()
        summary["schema_source"]["loaded"] = True
        summary["mapping_source"]["loaded"] = True
        
        # Populate mapping source fields
        map_src = adapter.mapping_summary
        summary["mapping_source"].update({
            "selected_sport_key": map_src.get("sport", {}).get("selected_sport_key"),
            "selected_country_slug": map_src.get("country", {}).get("selected_country_slug"),
            "selected_country_id": map_src.get("country", {}).get("selected_country_id"),
            "selected_competition_slug": map_src.get("competition", {}).get("selected_competition_slug"),
            "selected_competition_id": map_src.get("competition", {}).get("selected_competition_id"),
            "selected_season": map_src.get("season", {}).get("selected_season"),
            "selected_match_id": map_src.get("finished_match_probe", {}).get("selected_match_id"),
        })
    except FileNotFoundError as exc:
        summary["final_review"] = "FAIL"
        if "schema" in str(exc):
            summary["classification"] = "SPORTDB_SHADOW_ADAPTER_BLOCKED_SCHEMA_SUMMARY_INVALID"
            summary["next_step"] = "blocked_or_retry_after_review"
            summary["blockers"].append("schema_summary_file_missing")
        else:
            summary["classification"] = "SPORTDB_SHADOW_ADAPTER_BLOCKED_MAPPING_SUMMARY_INVALID"
            summary["next_step"] = "blocked_or_retry_after_review"
            summary["blockers"].append("mapping_summary_file_missing")
        
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        summary["final_review"] = "FAIL"
        summary["classification"] = "SPORTDB_SHADOW_ADAPTER_BLOCKED_MAPPING_SUMMARY_INVALID"
        summary["next_step"] = "blocked_or_retry_after_review"
        summary["blockers"].append(f"adapter_init_failure: {exc}")
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0

    # Step 2: Execute Probes Sequentially
    classification = "UNKNOWN"
    blocker_found = None

    # Probe A: Competition Results
    summary["results_probe"]["performed"] = True
    try:
        res = adapter.get_competition_results_shadow()
        summary["results_probe"]["available"] = True
        summary["results_probe"]["accepted_count"] = len(res)
        summary["results_probe"]["safe_preview"] = safe_preview(res)
        if getattr(adapter, "last_results_raw", None) is not None:
            summary["results_probe"]["raw_response_sha256"] = sha256_jsonable(adapter.last_results_raw)
    except SportDBMCPAuthError as exc:
        classification = "SPORTDB_AUTH_BLOCKED"
        blocker_found = f"auth_blocked: {exc}"
    except SportDBMCPRateLimitError as exc:
        classification = "SPORTDB_RATE_LIMITED_RETRY_LATER"
        blocker_found = f"rate_limited: {exc}"
        summary["call_budget"]["stopped_on_429"] = True
    except SportDBMCPNotAcceptableError as exc:
        classification = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
        blocker_found = f"not_acceptable_406: {exc}"
    except SportDBMCPParserError as exc:
        classification = "PLAN_DEFECT_SSE_OR_JSON_PARSER"
        blocker_found = f"parser_defect: {exc}"
    except RequiredPayloadFieldUnknownError as exc:
        classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
        blocker_found = f"required_field_unknown: {exc}"
    except Exception as exc:
        classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_TRANSPORT_OR_SERVER"
        blocker_found = f"results_failed: {exc}"

    # Probe B: Match Stats
    if not blocker_found:
        summary["stats_probe"]["performed"] = True
        try:
            stat_res = adapter.get_match_stats_shadow()
            summary["stats_probe"]["available"] = True
            summary["stats_probe"]["provider_match_id"] = stat_res["provider_match_id"]
            summary["stats_probe"]["top_level_keys"] = stat_res["top_level_keys"]
            summary["stats_probe"]["raw_stat_field_names"] = stat_res["raw_stat_field_names"]
            summary["stats_probe"]["normalized_metric_names"] = stat_res["normalized_metric_names"]
            summary["stats_probe"]["unknown_metrics"] = stat_res["unknown_metrics"]
            summary["stats_probe"]["team_side_detection"] = stat_res["team_side_detection"]
            summary["stats_probe"]["safe_preview"] = safe_preview(stat_res["raw_result"])
            summary["stats_probe"]["raw_response_sha256"] = sha256_jsonable(stat_res["raw_result"])
        except SportDBMCPAuthError as exc:
            classification = "SPORTDB_AUTH_BLOCKED"
            blocker_found = f"auth_blocked: {exc}"
        except SportDBMCPRateLimitError as exc:
            classification = "SPORTDB_RATE_LIMITED_RETRY_LATER"
            blocker_found = f"rate_limited: {exc}"
            summary["call_budget"]["stopped_on_429"] = True
        except SportDBMCPNotAcceptableError as exc:
            classification = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
            blocker_found = f"not_acceptable_406: {exc}"
        except SportDBMCPParserError as exc:
            classification = "PLAN_DEFECT_SSE_OR_JSON_PARSER"
            blocker_found = f"parser_defect: {exc}"
        except RequiredPayloadFieldUnknownError as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
            blocker_found = f"required_field_unknown: {exc}"
        except Exception as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_TRANSPORT_OR_SERVER"
            blocker_found = f"stats_failed: {exc}"

    # Probe C: Match Events
    if not blocker_found:
        summary["events_probe"]["performed"] = True
        try:
            evt_res = adapter.get_match_events_shadow()
            summary["events_probe"]["available"] = True
            summary["events_probe"]["event_count"] = evt_res["event_count"]
            summary["events_probe"]["event_type_names"] = evt_res["event_type_names"]
            summary["events_probe"]["goal_count"] = evt_res["goal_count"]
            summary["events_probe"]["card_count"] = evt_res["card_count"]
            summary["events_probe"]["safe_preview"] = safe_preview(evt_res["raw_result"])
            summary["events_probe"]["raw_response_sha256"] = sha256_jsonable(evt_res["raw_result"])
        except SportDBMCPAuthError as exc:
            classification = "SPORTDB_AUTH_BLOCKED"
            blocker_found = f"auth_blocked: {exc}"
        except SportDBMCPRateLimitError as exc:
            classification = "SPORTDB_RATE_LIMITED_RETRY_LATER"
            blocker_found = f"rate_limited: {exc}"
            summary["call_budget"]["stopped_on_429"] = True
        except SportDBMCPNotAcceptableError as exc:
            classification = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
            blocker_found = f"not_acceptable_406: {exc}"
        except SportDBMCPParserError as exc:
            classification = "PLAN_DEFECT_SSE_OR_JSON_PARSER"
            blocker_found = f"parser_defect: {exc}"
        except RequiredPayloadFieldUnknownError as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
            blocker_found = f"required_field_unknown: {exc}"
        except Exception as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_TRANSPORT_OR_SERVER"
            blocker_found = f"events_failed: {exc}"

    # Probe D: Match Lineups
    if not blocker_found:
        summary["lineups_probe"]["performed"] = True
        try:
            lin_res = adapter.get_match_lineups_shadow()
            summary["lineups_probe"]["available"] = True
            summary["lineups_probe"]["formation_values"] = lin_res["formation_values"]
            summary["lineups_probe"]["player_count"] = lin_res["player_count"]
            summary["lineups_probe"]["safe_preview"] = safe_preview(lin_res["raw_result"])
            summary["lineups_probe"]["raw_response_sha256"] = sha256_jsonable(lin_res["raw_result"])
        except SportDBMCPAuthError as exc:
            classification = "SPORTDB_AUTH_BLOCKED"
            blocker_found = f"auth_blocked: {exc}"
        except SportDBMCPRateLimitError as exc:
            classification = "SPORTDB_RATE_LIMITED_RETRY_LATER"
            blocker_found = f"rate_limited: {exc}"
            summary["call_budget"]["stopped_on_429"] = True
        except SportDBMCPNotAcceptableError as exc:
            classification = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
            blocker_found = f"not_acceptable_406: {exc}"
        except SportDBMCPParserError as exc:
            classification = "PLAN_DEFECT_SSE_OR_JSON_PARSER"
            blocker_found = f"parser_defect: {exc}"
        except RequiredPayloadFieldUnknownError as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
            blocker_found = f"required_field_unknown: {exc}"
        except Exception as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_TRANSPORT_OR_SERVER"
            blocker_found = f"lineups_failed: {exc}"

    # Probe E: Competition Standings
    if not blocker_found:
        summary["standings_probe"]["performed"] = True
        try:
            std_res = adapter.get_competition_standings_shadow()
            summary["standings_probe"]["available"] = True
            summary["standings_probe"]["row_count"] = std_res["row_count"]
            summary["standings_probe"]["team_names"] = std_res["team_names"]
            summary["standings_probe"]["safe_preview"] = safe_preview(std_res["raw_result"])
            summary["standings_probe"]["raw_response_sha256"] = sha256_jsonable(std_res["raw_result"])
        except SportDBMCPAuthError as exc:
            classification = "SPORTDB_AUTH_BLOCKED"
            blocker_found = f"auth_blocked: {exc}"
        except SportDBMCPRateLimitError as exc:
            classification = "SPORTDB_RATE_LIMITED_RETRY_LATER"
            blocker_found = f"rate_limited: {exc}"
            summary["call_budget"]["stopped_on_429"] = True
        except SportDBMCPNotAcceptableError as exc:
            classification = "PLAN_DEFECT_MCP_ACCEPT_OR_TRANSPORT"
            blocker_found = f"not_acceptable_406: {exc}"
        except SportDBMCPParserError as exc:
            classification = "PLAN_DEFECT_SSE_OR_JSON_PARSER"
            blocker_found = f"parser_defect: {exc}"
        except RequiredPayloadFieldUnknownError as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_REQUIRED_PAYLOAD_FIELD_UNKNOWN"
            blocker_found = f"required_field_unknown: {exc}"
        except Exception as exc:
            classification = "SPORTDB_SHADOW_ADAPTER_BLOCKED_TRANSPORT_OR_SERVER"
            blocker_found = f"standings_failed: {exc}"

    # Update call budgets
    summary["call_budget"]["mcp_tool_calls_made"] = adapter.client.mcp_tool_calls_made
    summary["call_budget"]["mcp_session_calls_made"] = adapter.client.mcp_session_calls_made

    # Step 3: Determine Classification & Verdict & Next Step
    if blocker_found:
        summary["final_review"] = "FAIL"
        summary["classification"] = classification
        summary["blockers"].append(blocker_found)
        summary["next_step"] = "blocked_or_retry_after_review"
    else:
        # Check if we are ready for replay or stats-only
        results_ok = summary["results_probe"]["available"]
        stats_ok = summary["stats_probe"]["available"]
        events_ok = summary["events_probe"]["available"]
        lineups_ok = summary["lineups_probe"]["available"]
        standings_ok = summary["standings_probe"]["available"]

        if stats_ok and results_ok and events_ok and lineups_ok and standings_ok:
            summary["classification"] = "SPORTDB_SHADOW_ADAPTER_READY_FOR_REPLAY_COMPARISON"
            summary["next_step"] = "P2E_A5_SPORTDB_REPLAY_COMPARISON_AGAINST_ACCEPTED_PROVIDERS"
            summary["final_review"] = "PASS"
        elif stats_ok:
            summary["classification"] = "SPORTDB_SHADOW_ADAPTER_READY_STATS_ONLY"
            summary["next_step"] = "P2E_A5_SPORTDB_STATS_ONLY_REPLAY_COMPARISON"
            summary["final_review"] = "PASS"
        else:
            summary["classification"] = "SPORTDB_SHADOW_ADAPTER_BLOCKED_STATS_UNAVAILABLE"
            summary["next_step"] = "blocked_or_retry_after_review"
            summary["blockers"].append("stats_probe_failed_or_unavailable")
            summary["final_review"] = "FAIL"

    # Save summary file
    out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    
    # Print summary as compact JSON as required
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
