#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.sportdb.dev"
REST_CALL_BUDGET = 6
MCP_CALL_BUDGET = 1
SLEEP_SECONDS = 10
KEY_ALIASES = ("SPORTDB_API_KEY", "SPORTDB_KEY")
SUMMARY_PATH = Path("certification/football/p2e_sportdb_mapping_summary.json")


def parse_dot_env(file_path: Path) -> dict[str, str]:
    env_dict: dict[str, str] = {}
    if not file_path.exists():
        return env_dict
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and (
            (val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")
        ):
            val = val[1:-1]
        env_dict[key] = val
    return env_dict


def resolve_api_key() -> tuple[str | None, str]:
    for alias in KEY_ALIASES:
        value = os.environ.get(alias, "").strip()
        if value:
            return value, alias
    dot_env = parse_dot_env(Path(".env"))
    for alias in KEY_ALIASES:
        value = dot_env.get(alias, "").strip()
        if value:
            return value, alias
    return None, "SPORTDB_API_KEY"


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


def top_level_keys(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        return sorted(str(key) for key in payload.keys())
    if isinstance(payload, list):
        return ["<list>"]
    return [f"<{type(payload).__name__}>"]


def to_jsonable(payload: Any) -> Any:
    if isinstance(payload, (dict, list, str, int, float, bool)) or payload is None:
        return payload
    return str(payload)


def extract_country_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("countries", "data", "rows", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def country_label(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("name") or "").strip(),
        str(row.get("slug") or "").strip(),
        str(row.get("country") or "").strip(),
    ]
    return " ".join(part for part in parts if part).lower()


def extract_slug(row: dict[str, Any]) -> str | None:
    for key in ("slug", "country_slug", "competition_slug", "id"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def select_country_slug(
    rows: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    selected: str | None = None
    for row in rows:
        label = country_label(row)
        slug = extract_slug(row)
        if any(
            token in label
            for token in ("england", "united kingdom", "great britain", "uk")
        ):
            candidates.append(
                {
                    "name": row.get("name") or row.get("country"),
                    "slug": slug,
                }
            )
            if selected is None and slug:
                if "england" in label:
                    selected = slug
    if selected is None:
        for candidate in candidates:
            if candidate.get("slug"):
                selected = str(candidate["slug"])
                break
    return selected, candidates


def extract_competition_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("competitions", "leagues", "data", "rows", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return []


def select_competition_slug(
    rows: list[dict[str, Any]],
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    summary: list[dict[str, Any]] = []
    matches: list[dict[str, Any]] = []
    selected: str | None = None
    for row in rows:
        name = str(
            row.get("name") or row.get("competition") or row.get("title") or ""
        ).strip()
        slug = extract_slug(row)
        item = {"name": name, "slug": slug}
        summary.append(item)
        haystack = f"{name} {slug or ''}".lower()
        if any(
            token in haystack
            for token in ("premier league", "epl", "english premier", "england")
        ):
            matches.append(item)
            if selected is None and slug:
                selected = slug
    return selected, summary, matches


def extract_season_strings(payload: Any) -> list[str]:
    values: list[str] = []
    if isinstance(payload, dict):
        seasons = payload.get("seasons")
        if isinstance(seasons, list):
            for row in seasons:
                if isinstance(row, str) and row.strip():
                    values.append(row.strip())
                elif isinstance(row, dict):
                    for key in ("season", "name", "slug"):
                        value = row.get(key)
                        if value is not None and str(value).strip():
                            values.append(str(value).strip())
                            break
    elif isinstance(payload, list):
        for row in payload:
            if isinstance(row, str) and row.strip():
                values.append(row.strip())
    return values


def select_season(seasons: list[str]) -> str | None:
    if not seasons:
        return None
    preferred = [season for season in seasons if "2025" in season or "2026" in season]
    return preferred[0] if preferred else seasons[0]


def extract_fixture_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("fixtures", "matches", "data", "rows", "results"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def extract_match_ids(rows: list[dict[str, Any]]) -> list[str]:
    match_ids: list[str] = []
    for row in rows:
        for key in ("match_id", "matchId", "id", "fixture_id", "fixtureId"):
            value = row.get(key)
            if value is not None and str(value).strip():
                match_ids.append(str(value).strip())
                break
    deduped: list[str] = []
    seen: set[str] = set()
    for match_id in match_ids:
        if match_id in seen:
            continue
        seen.add(match_id)
        deduped.append(match_id)
    return deduped


def derive_match_teams(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {
        "home": payload.get("homeTeam")
        or payload.get("home")
        or payload.get("home_name"),
        "away": payload.get("awayTeam")
        or payload.get("away")
        or payload.get("away_name"),
    }


def derive_match_score(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    score = payload.get("score")
    if isinstance(score, dict):
        return score
    return {
        "home": payload.get("homeScore") or payload.get("home_score"),
        "away": payload.get("awayScore") or payload.get("away_score"),
    }


def extract_stat_field_names(payload: Any) -> list[str]:
    rows = payload if isinstance(payload, list) else []
    fields: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("name", "stat", "label", "type", "metric"):
            value = row.get(key)
            if value is not None and str(value).strip():
                fields.append(str(value).strip())
                break
    deduped: list[str] = []
    seen: set[str] = set()
    for field in fields:
        if field in seen:
            continue
        seen.add(field)
        deduped.append(field)
    return deduped


def derive_team_split(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else []
    keys: set[str] = set()
    sample: dict[str, Any] = {}
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        keys.update(str(key) for key in row.keys())
        if not sample:
            sample = row
    return {
        "observed_keys": sorted(keys),
        "sample": to_jsonable(sample),
        "home_away_fields_present": any(
            key.lower() in {"home", "away", "homevalue", "awayvalue", "team", "side"}
            for key in keys
        ),
    }


def note_status_blockers(
    summary: dict[str, Any], call_name: str, result: dict[str, Any]
) -> None:
    status = result["status"]
    payload = result["payload"]
    if status in {401, 403}:
        summary["blockers"].append(f"auth_http_status_{status}_{call_name}")
    elif status >= 400 and status != 429:
        summary["blockers"].append(f"contradictory_http_status_{status}_{call_name}")
    if isinstance(payload, dict) and payload.get("_non_json"):
        summary["blockers"].append(f"schema_unreadable_{call_name}")


class ProbeRunner:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rest_calls_made = 0
        self.mcp_calls_made = 0
        self.stopped_on_429 = False
        self.retry_after: str | None = None
        self.aggregate_rate_headers: dict[str, dict[str, str]] = {}

    def sleep_if_needed(self) -> None:
        if self.rest_calls_made > 0 or self.mcp_calls_made > 0:
            time.sleep(SLEEP_SECONDS)

    def rest_get(self, path: str) -> dict[str, Any]:
        if self.stopped_on_429:
            raise RuntimeError("SportDB probe already stopped on 429")
        if self.rest_calls_made >= REST_CALL_BUDGET:
            raise RuntimeError("SportDB REST call budget exceeded")
        self.sleep_if_needed()
        url = f"{BASE_URL}{path}"
        response = requests.get(
            url,
            headers={"X-API-Key": self.api_key},
            timeout=30,
        )
        self.rest_calls_made += 1
        raw_sha256 = hashlib.sha256(response.content).hexdigest()
        headers = dict(response.headers)
        kept_rate_headers = rate_headers(headers)
        self.aggregate_rate_headers[f"rest_call_{self.rest_calls_made}"] = (
            kept_rate_headers
        )
        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = {"_non_json": True, "text_preview": response.text[:500]}
        if response.status_code == 429:
            self.stopped_on_429 = True
            self.retry_after = headers.get("Retry-After") or headers.get("retry-after")
        if self.retry_after:
            self.stopped_on_429 = True
        return {
            "path": path,
            "status": response.status_code,
            "headers": headers,
            "rate_limit_headers": kept_rate_headers,
            "payload": payload,
            "raw_response_sha256": raw_sha256,
        }

    def mcp_tools_list(self) -> dict[str, Any]:
        if self.stopped_on_429:
            raise RuntimeError("SportDB probe already stopped on 429")
        if self.mcp_calls_made >= MCP_CALL_BUDGET:
            raise RuntimeError("SportDB MCP call budget exceeded")
        self.sleep_if_needed()
        response = requests.post(
            f"{BASE_URL}/mcp/",
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            timeout=30,
        )
        self.mcp_calls_made += 1
        headers = dict(response.headers)
        kept_rate_headers = rate_headers(headers)
        self.aggregate_rate_headers[f"mcp_call_{self.mcp_calls_made}"] = (
            kept_rate_headers
        )
        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"_non_json": True, "text_preview": response.text[:500]}
        if response.status_code == 429:
            self.stopped_on_429 = True
            self.retry_after = headers.get("Retry-After") or headers.get("retry-after")
        return {
            "status": response.status_code,
            "headers": headers,
            "rate_limit_headers": kept_rate_headers,
            "payload": payload,
            "raw_response_sha256": hashlib.sha256(response.content).hexdigest(),
        }


def extract_mcp_tool_names(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    tools = result.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            names.append(str(tool["name"]))
    return names


def build_empty_summary(key_name_used: str) -> dict[str, Any]:
    return {
        "phase_id": "P2E_SPORTDB_STRATEGIC_MULTISPORT_MAPPING_WITH_RATE_LIMIT_GUARD",
        "previous_accepted_sha": "b51885d86042084aec81c92560b1c51e18519dd0",
        "evidence_level": "TRACKED_MAPPING_SUMMARY",
        "provider": "sportdb",
        "auth": {
            "key_name_used": key_name_used,
            "secret_safe": True,
        },
        "football_mapping": {
            "country_discovery": {},
            "competition_discovery": {},
            "season_discovery": {},
            "fixtures_probe": {},
            "match_details": {},
            "match_stats": {},
            "mcp_metadata": {},
        },
        "classification": "",
        "call_budget": {
            "rest_calls_made": 0,
            "mcp_calls_made": 0,
            "stopped_on_429": False,
        },
        "rate_limit_headers": {},
        "provider_native_ids": {},
        "raw_stat_field_names": [],
        "blockers": [],
        "next_step": "",
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "secret_safe": True,
        "final_review": "",
    }


def classify(summary: dict[str, Any]) -> tuple[str, str]:
    if summary["call_budget"]["stopped_on_429"]:
        return "SPORTDB_RATE_LIMITED_RETRY_LATER", "sportdb_rate_limit_retry"

    blockers = summary["blockers"]
    country_slug = summary["provider_native_ids"].get("country_slug")
    competition_slug = summary["provider_native_ids"].get("competition_slug")
    season = summary["provider_native_ids"].get("season")
    match_id = summary["provider_native_ids"].get("match_id")
    stats_count = summary["football_mapping"]["match_stats"].get("result_count")
    fixtures_status = summary["football_mapping"]["fixtures_probe"].get("status")
    fixtures_count = summary["football_mapping"]["fixtures_probe"].get("result_count")

    if any(
        blocker.startswith("auth_")
        or blocker.startswith("schema_")
        or blocker.startswith("contradictory_")
        for blocker in blockers
    ):
        return "SPORTDB_BLOCKED", "defer"
    if competition_slug is None:
        return "SPORTDB_NOT_MAPPED_FOR_ENG1", "defer"
    if fixtures_status == 200 and fixtures_count == 0:
        return "SPORTDB_ENG1_FIXTURES_EMPTY_FOR_PROVIDER_SEASON", "defer"
    if (
        all(
            value is not None
            for value in (country_slug, competition_slug, season, match_id)
        )
        and isinstance(stats_count, int)
        and stats_count > 0
    ):
        return "SPORTDB_REOPEN_AS_COMPETITOR", "sportdb_certification"
    if (
        all(value is not None for value in (country_slug, competition_slug, season))
        and fixtures_status == 200
        and isinstance(fixtures_count, int)
        and fixtures_count > 0
    ):
        return "SPORTDB_PARTIAL_BUT_PROMISING", "defer"
    return "SPORTDB_BLOCKED", "defer"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded SportDB mapping probe.")
    parser.add_argument("--out", default=str(SUMMARY_PATH), help="Output summary path")
    args = parser.parse_args()

    api_key, key_name_used = resolve_api_key()
    summary = build_empty_summary(key_name_used)
    output_path = Path(args.out)

    if not api_key:
        summary["classification"] = "SPORTDB_BLOCKED"
        summary["blockers"] = ["auth_key_missing"]
        summary["next_step"] = "defer"
        output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "classification": summary["classification"],
                    "rest_calls_made": 0,
                    "mcp_calls_made": 0,
                }
            )
        )
        return 1

    runner = ProbeRunner(api_key)

    try:
        call_1 = runner.rest_get("/api/football/countries")
        note_status_blockers(summary, "country_discovery", call_1)
        country_rows = extract_country_rows(call_1["payload"])
        country_slug, country_candidates = select_country_slug(country_rows)
        summary["football_mapping"]["country_discovery"] = {
            "status": call_1["status"],
            "raw_response_sha256": call_1["raw_response_sha256"],
            "response_top_level_keys": top_level_keys(call_1["payload"]),
            "england_candidates": country_candidates,
            "selected_country_slug": country_slug,
            "rate_limit_headers": call_1["rate_limit_headers"],
        }
        if country_slug:
            summary["provider_native_ids"]["country_slug"] = country_slug

        if runner.stopped_on_429:
            raise StopIteration

        if not country_slug:
            summary["blockers"].append("country_slug_not_found")
        else:
            call_2 = runner.rest_get(f"/api/football/{country_slug}")
            note_status_blockers(summary, "competition_discovery", call_2)
            competition_rows = extract_competition_rows(call_2["payload"])
            competition_slug, competition_summary, competition_matches = (
                select_competition_slug(competition_rows)
            )
            summary["football_mapping"]["competition_discovery"] = {
                "status": call_2["status"],
                "raw_response_sha256": call_2["raw_response_sha256"],
                "competitions_list_summary": competition_summary,
                "pl_like_matches": competition_matches,
                "selected_competition_slug": competition_slug,
            }
            if competition_slug:
                summary["provider_native_ids"]["competition_slug"] = competition_slug

            if runner.stopped_on_429:
                raise StopIteration

            if competition_slug is None:
                summary["blockers"].append("pl_like_competition_not_found")
            else:
                call_3 = runner.rest_get(
                    f"/api/football/{country_slug}/{competition_slug}"
                )
                note_status_blockers(summary, "season_discovery", call_3)
                season_strings = extract_season_strings(call_3["payload"])
                selected_season = select_season(season_strings)
                summary["football_mapping"]["season_discovery"] = {
                    "status": call_3["status"],
                    "raw_response_sha256": call_3["raw_response_sha256"],
                    "season_strings": season_strings,
                    "selected_season": selected_season,
                }
                if selected_season:
                    summary["provider_native_ids"]["season"] = selected_season

                if runner.stopped_on_429:
                    raise StopIteration

                if selected_season is None:
                    summary["blockers"].append("season_not_found")
                else:
                    encoded_season = requests.utils.quote(selected_season, safe="")
                    call_4 = runner.rest_get(
                        f"/api/football/{country_slug}/{competition_slug}/{encoded_season}/fixtures"
                    )
                    note_status_blockers(summary, "fixtures_probe", call_4)
                    fixture_rows = extract_fixture_rows(call_4["payload"])
                    match_ids = extract_match_ids(fixture_rows)
                    summary["football_mapping"]["fixtures_probe"] = {
                        "status": call_4["status"],
                        "result_count": len(fixture_rows),
                        "provider_native_match_ids": match_ids,
                        "raw_response_sha256": call_4["raw_response_sha256"],
                        "rate_limit_headers": call_4["rate_limit_headers"],
                    }
                    if match_ids:
                        summary["provider_native_ids"]["match_id"] = match_ids[0]

                    if runner.stopped_on_429:
                        raise StopIteration

                    if match_ids:
                        match_id = match_ids[0]
                        call_5 = runner.rest_get(f"/api/match/{match_id}")
                        note_status_blockers(summary, "match_details", call_5)
                        summary["football_mapping"]["match_details"] = {
                            "status": call_5["status"],
                            "teams": derive_match_teams(call_5["payload"]),
                            "match_status": call_5["payload"].get("status")
                            if isinstance(call_5["payload"], dict)
                            else None,
                            "score": derive_match_score(call_5["payload"]),
                            "response_top_level_keys": top_level_keys(
                                call_5["payload"]
                            ),
                            "raw_response_sha256": call_5["raw_response_sha256"],
                        }

                        if runner.stopped_on_429:
                            raise StopIteration

                        if call_5["status"] == 200:
                            call_6 = runner.rest_get(f"/api/match/{match_id}/stats")
                            note_status_blockers(summary, "match_stats", call_6)
                            stat_fields = extract_stat_field_names(call_6["payload"])
                            summary["raw_stat_field_names"] = stat_fields
                            summary["football_mapping"]["match_stats"] = {
                                "status": call_6["status"],
                                "raw_stat_field_names": stat_fields,
                                "team_split": derive_team_split(call_6["payload"]),
                                "result_count": len(call_6["payload"])
                                if isinstance(call_6["payload"], list)
                                else 0,
                                "raw_response_sha256": call_6["raw_response_sha256"],
                            }
    except StopIteration:
        pass
    except requests.RequestException as exc:
        summary["blockers"].append(f"transport_error:{exc.__class__.__name__}")

    summary["call_budget"] = {
        "rest_calls_made": runner.rest_calls_made,
        "mcp_calls_made": runner.mcp_calls_made,
        "stopped_on_429": runner.stopped_on_429,
    }
    summary["rate_limit_headers"] = runner.aggregate_rate_headers
    if runner.retry_after:
        summary["rate_limit_headers"]["retry_after"] = {
            "Retry-After": runner.retry_after
        }

    classification, next_step = classify(summary)
    summary["classification"] = classification
    summary["next_step"] = next_step

    mcp_metadata = {
        "performed": False,
        "reason": "not_needed_without_rest_ambiguity",
        "endpoint": "https://api.sportdb.dev/mcp/",
        "documented_capabilities": [
            "competitions",
            "fixtures",
            "stats",
            "lineups",
        ],
    }
    if (
        not runner.stopped_on_429
        and runner.mcp_calls_made == 0
        and any(blocker.startswith("contradictory_") for blocker in summary["blockers"])
    ):
        try:
            mcp_result = runner.mcp_tools_list()
            mcp_metadata = {
                "performed": True,
                "status": mcp_result["status"],
                "raw_response_sha256": mcp_result["raw_response_sha256"],
                "rate_limit_headers": mcp_result["rate_limit_headers"],
                "tool_names": extract_mcp_tool_names(mcp_result["payload"]),
                "response_top_level_keys": top_level_keys(mcp_result["payload"]),
                "endpoint": "https://api.sportdb.dev/mcp/",
                "documented_capabilities": [
                    "competitions",
                    "fixtures",
                    "stats",
                    "lineups",
                ],
            }
            if isinstance(mcp_result["payload"], dict) and mcp_result["payload"].get(
                "error"
            ):
                mcp_metadata["error"] = to_jsonable(mcp_result["payload"].get("error"))
        except requests.RequestException as exc:
            mcp_metadata = {
                "performed": True,
                "status": None,
                "endpoint": "https://api.sportdb.dev/mcp/",
                "error": f"transport_error:{exc.__class__.__name__}",
                "documented_capabilities": [
                    "competitions",
                    "fixtures",
                    "stats",
                    "lineups",
                ],
            }
    summary["football_mapping"]["mcp_metadata"] = mcp_metadata

    summary["call_budget"] = {
        "rest_calls_made": runner.rest_calls_made,
        "mcp_calls_made": runner.mcp_calls_made,
        "stopped_on_429": runner.stopped_on_429,
    }
    summary["rate_limit_headers"] = runner.aggregate_rate_headers
    if runner.retry_after:
        summary["rate_limit_headers"]["retry_after"] = {
            "Retry-After": runner.retry_after
        }

    classification, next_step = classify(summary)
    summary["classification"] = classification
    summary["next_step"] = next_step

    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "classification": summary["classification"],
                "rest_calls_made": summary["call_budget"]["rest_calls_made"],
                "mcp_calls_made": summary["call_budget"]["mcp_calls_made"],
                "stopped_on_429": summary["call_budget"]["stopped_on_429"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
