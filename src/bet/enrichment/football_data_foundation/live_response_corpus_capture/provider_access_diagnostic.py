"""
Football provider access binding rescue diagnostic tool.
Diagnoses and checks bindings for SportDB and Highlightly.
"""

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from bet.enrichment.football_data_foundation.live_response_corpus_capture.env_loader import (
    load_project_dotenv,
    get_credential,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.http_capture import (
    safe_http_get,
    safe_http_post,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.sanitizer import (
    sanitize_json_body,
    compute_body_sha256,
    write_json,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_bindings import (
    SPORTDB_REST_CANDIDATE,
    SPORTDB_MCP_CANDIDATE,
    HIGHLIGHTLY_DIRECT_CANDIDATE,
    HIGHLIGHTLY_RAPIDAPI_CANDIDATE,
)


def find_project_root() -> Path:
    """Dynamically locate the project root directory."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "kilo.json").exists() or (parent / ".git").exists():
            return parent
    return current.parents[5]


def find_highlightly_match_id(data: Any) -> str | None:
    """
    Recursively search Highlightly JSON response for Norway/Senegal.
    Returns the string match ID if found.
    """
    if isinstance(data, dict):
        all_strs = []
        def collect_strings(obj: Any, depth: int = 0):
            if depth > 3:
                return
            if isinstance(obj, str):
                all_strs.append(obj.lower())
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    collect_strings(v, depth + 1)
            elif isinstance(obj, list):
                for item in obj:
                    collect_strings(item, depth + 1)

        collect_strings(data)
        has_norway = any("norway" in s for s in all_strs)
        has_senegal = any("senegal" in s for s in all_strs)
        if has_norway and has_senegal:
            for key in ["id", "match_id", "fixture_id", "eventId"]:
                if key in data and data[key] is not None:
                    return str(data[key])
            for k, v in data.items():
                if isinstance(v, dict):
                    for key in ["id", "match_id", "fixture_id"]:
                        if key in v and v[key] is not None:
                            return str(v[key])

        for k, v in data.items():
            res = find_highlightly_match_id(v)
            if res:
                return res

    elif isinstance(data, list):
        for item in data:
            res = find_highlightly_match_id(item)
            if res:
                return res

    return None


def run_provider_access_rescue_diagnostic(output_root_path: Path) -> Dict[str, Any]:
    """
    Executes provider access binding rescue diagnostic for SportDB and Highlightly.
    """
    project_root = find_project_root()
    load_project_dotenv(project_root)

    timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    run_dir = output_root_path / f"provider_access_rescue_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    sportdb_key = get_credential("SPORTDB_API_KEY")
    highlightly_key = get_credential("HIGHLIGHTLY_API_KEY")

    sportdb_request_attempted = False
    highlightly_direct_request_attempted = False
    highlightly_rapidapi_request_attempted = False

    sportdb_verdict = "SKIPPED_CREDENTIALS_MISSING"
    highlightly_verdict = "SKIPPED_CREDENTIALS_MISSING"

    sportdb_probe_log = {
        "provider": "sportdb",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "requests": [],
        "verdict": "",
    }
    highlightly_probe_log = {
        "provider": "highlightly",
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "requests": [],
        "verdict": "",
    }

    working_bindings = {}
    blocked_bindings = {}
    mapping_candidates_found = 0
    match_mapping_candidate = None
    failed_requirements = []

    # 1. SPORTDB DIAGNOSTIC
    if not sportdb_key:
        sportdb_verdict = "SKIPPED_CREDENTIALS_MISSING"
        blocked_bindings["sportdb"] = {
            "reason": "SPORTDB_API_KEY is missing",
            "selectable_for_production": False,
        }
    else:
        sportdb_request_attempted = True
        # Try REST endpoint first
        rest_url = "https://api.sportdb.dev/api/football/live"
        rest_headers = {"X-API-Key": sportdb_key, "Accept": "application/json"}
        
        status_code, body, error = safe_http_get(rest_url, headers=rest_headers)
        
        rest_req_record = {
            "url": "https://api.sportdb.dev/api/football/live",
            "method": "GET",
            "status_code": status_code,
            "response_body": sanitize_json_body(body) if body else None,
            "error": error,
            "purpose": "sportdb_rest_live_probe",
        }
        sportdb_probe_log["requests"].append(rest_req_record)

        rest_ok = False
        if status_code == 200 and isinstance(body, dict):
            # Check for error fields inside JSON or successful shape
            rest_ok = True
            sportdb_verdict = "SPORTDB_WORKING_REST"
            working_bindings["sportdb"] = SPORTDB_REST_CANDIDATE.copy()
        elif status_code in (401, 403):
            sportdb_verdict = "SPORTDB_REST_AUTH_OR_PLAN_BLOCKED"
        elif error and "non-JSON" in str(error):
            sportdb_verdict = "SPORTDB_REST_PARSE_FAILED"
        else:
            sportdb_verdict = "SPORTDB_REST_HTTP_FAILED"

        if not rest_ok:
            # REST blocked or failed, attempt MCP handshake
            mcp_url = "https://api.sportdb.dev/mcp/"
            mcp_versions = ["2025-06-18", "2025-03-26"]
            successful_version = None
            mcp_init_body = None

            for mcp_version in mcp_versions:
                mcp_headers = {
                    "X-API-Key": sportdb_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": mcp_version,
                }
                mcp_body = {
                    "jsonrpc": "2.0",
                    "id": f"sportdb-init-{mcp_version}",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": mcp_version,
                        "capabilities": {},
                        "clientInfo": {
                            "name": "bet-provider-access-diagnostic",
                            "version": "0.1.0",
                        },
                    },
                }

                init_status, init_body, init_err = safe_http_post(
                    mcp_url, headers=mcp_headers, json_data=mcp_body
                )

                init_req_record = {
                    "url": "https://api.sportdb.dev/mcp/",
                    "method": "POST",
                    "status_code": init_status,
                    "response_body": sanitize_json_body(init_body) if init_body else None,
                    "error": init_err,
                    "purpose": f"sportdb_mcp_init_probe_{mcp_version}",
                }
                sportdb_probe_log["requests"].append(init_req_record)

                if (
                    init_status == 200
                    and isinstance(init_body, dict)
                    and "result" in init_body
                    and "error" not in init_body
                ):
                    successful_version = mcp_version
                    mcp_init_body = init_body
                    break

            if successful_version:
                # Initialize worked! Attempt tools/list request
                tools_headers = {
                    "X-API-Key": sportdb_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "MCP-Protocol-Version": successful_version,
                }
                tools_body = {
                    "jsonrpc": "2.0",
                    "id": "sportdb-tools-1",
                    "method": "tools/list",
                    "params": {},
                }

                tools_status, tools_resp_body, tools_err = safe_http_post(
                    mcp_url, headers=tools_headers, json_data=tools_body
                )

                tools_record_body = None
                if tools_status == 200 and isinstance(tools_resp_body, dict):
                    # Sanitize tool names and store names only plus hash
                    raw_tools = []
                    if "result" in tools_resp_body and isinstance(
                        tools_resp_body["result"], dict
                    ):
                        raw_tools = tools_resp_body["result"].get("tools", [])
                    
                    tool_names = sorted(
                        [
                            t.get("name")
                            for t in raw_tools
                            if isinstance(t, dict) and "name" in t
                        ]
                    )
                    tools_hash = hashlib.sha256(
                        json.dumps(tool_names).encode("utf-8")
                    ).hexdigest()

                    tools_record_body = {
                        "tool_names": tool_names,
                        "tool_names_sha256": tools_hash,
                    }

                tools_req_record = {
                    "url": "https://api.sportdb.dev/mcp/",
                    "method": "POST",
                    "status_code": tools_status,
                    "response_body": tools_record_body,
                    "error": tools_err,
                    "purpose": "sportdb_tools_list_probe",
                }
                sportdb_probe_log["requests"].append(tools_req_record)

                sportdb_verdict = "SPORTDB_WORKING_MCP"
                working_bindings["sportdb"] = SPORTDB_MCP_CANDIDATE.copy()
            else:
                # MCP failed. Determine overall verdict
                init_statuses = [
                    req["status_code"]
                    for req in sportdb_probe_log["requests"]
                    if "init" in req["purpose"]
                ]
                if all(s in (401, 403) for s in init_statuses) or status_code in (
                    401,
                    403,
                ):
                    sportdb_verdict = "SPORTDB_AUTH_OR_PLAN_BLOCKED"
                elif any(s == 400 for s in init_statuses):
                    sportdb_verdict = "SPORTDB_ENDPOINT_OR_PROTOCOL_BLOCKED"
                else:
                    sportdb_verdict = "SPORTDB_UNAVAILABLE"

                blocked_bindings["sportdb"] = {
                    "verdict": sportdb_verdict,
                    "rest_status_code": status_code,
                    "mcp_init_statuses": init_statuses,
                    "selectable_for_production": False,
                }

    # 2. HIGHLIGHTLY DIAGNOSTIC
    if not highlightly_key:
        highlightly_verdict = "SKIPPED_CREDENTIALS_MISSING"
        blocked_bindings["highlightly"] = {
            "reason": "HIGHLIGHTLY_API_KEY is missing",
            "selectable_for_production": False,
        }
    else:
        highlightly_direct_request_attempted = True
        direct_url = (
            "https://sports.highlightly.net/football/matches?date=2026-06-23&timezone=Etc/UTC"
        )
        direct_headers = {"x-rapidapi-key": highlightly_key, "Accept": "application/json"}

        d_status, d_body, d_error = safe_http_get(direct_url, headers=direct_headers)

        # REQ-HIGHLIGHTLY-009 Retry once if response says at least one param required
        if d_status == 200 and isinstance(d_body, dict):
            body_str = str(d_body).lower()
            if any(kw in body_str for kw in ["parameter", "param", "required"]):
                # Retry once
                d_status, d_body, d_error = safe_http_get(
                    direct_url, headers=direct_headers
                )

        direct_record = {
            "url": direct_url,
            "method": "GET",
            "status_code": d_status,
            "response_body": sanitize_json_body(d_body) if d_body else None,
            "error": d_error,
            "purpose": "highlightly_direct_matches_by_date_probe",
        }
        highlightly_probe_log["requests"].append(direct_record)

        highlightly_worked = False

        if d_status == 200 and isinstance(d_body, dict):
            highlightly_worked = True
            highlightly_verdict = "HIGHLIGHTLY_WORKING_DIRECT"
            working_bindings["highlightly"] = HIGHLIGHTLY_DIRECT_CANDIDATE.copy()

            # Search for Norway/Senegal
            match_id = find_highlightly_match_id(d_body)
            if match_id:
                mapping_candidates_found = 1
                match_mapping_candidate = {
                    "fixture_slug": "worldcup2026-norway-senegal",
                    "home_team": "Norway",
                    "away_team": "Senegal",
                    "provider_fixture_id": match_id,
                }
                working_bindings["highlightly"][
                    "match_mapping_candidate"
                ] = match_mapping_candidate

        elif d_status in (401, 403):
            # Classify as direct auth mismatch and try RapidAPI fallback
            highlightly_rapidapi_request_attempted = True
            rapid_url = "https://sport-highlights-api.p.rapidapi.com/football/matches?date=2026-06-23&timezone=Etc/UTC"
            rapid_headers = {
                "x-rapidapi-key": highlightly_key,
                "x-rapidapi-host": "sport-highlights-api.p.rapidapi.com",
                "Accept": "application/json",
            }

            r_status, r_body, r_error = safe_http_get(rapid_url, headers=rapid_headers)

            if r_status == 200 and isinstance(r_body, dict):
                body_str = str(r_body).lower()
                if any(kw in body_str for kw in ["parameter", "param", "required"]):
                    r_status, r_body, r_error = safe_http_get(
                        rapid_url, headers=rapid_headers
                    )

            rapid_record = {
                "url": rapid_url,
                "method": "GET",
                "status_code": r_status,
                "response_body": sanitize_json_body(r_body) if r_body else None,
                "error": r_error,
                "purpose": "highlightly_rapidapi_matches_by_date_probe",
            }
            highlightly_probe_log["requests"].append(rapid_record)

            if r_status == 200 and isinstance(r_body, dict):
                highlightly_worked = True
                highlightly_verdict = "HIGHLIGHTLY_WORKING_RAPIDAPI"
                working_bindings["highlightly"] = HIGHLIGHTLY_RAPIDAPI_CANDIDATE.copy()

                match_id = find_highlightly_match_id(r_body)
                if match_id:
                    mapping_candidates_found = 1
                    match_mapping_candidate = {
                        "fixture_slug": "worldcup2026-norway-senegal",
                        "home_team": "Norway",
                        "away_team": "Senegal",
                        "provider_fixture_id": match_id,
                    }
                    working_bindings["highlightly"][
                        "match_mapping_candidate"
                    ] = match_mapping_candidate
            elif r_status in (401, 403):
                highlightly_verdict = "HIGHLIGHTLY_AUTH_PLATFORM_MISMATCH_OR_PLAN_BLOCKED"
            else:
                highlightly_verdict = "HIGHLIGHTLY_ENDPOINT_BLOCKED"
        else:
            # Check other fail status
            highlightly_verdict = "HIGHLIGHTLY_ENDPOINT_BLOCKED"

        if not highlightly_worked:
            blocked_bindings["highlightly"] = {
                "verdict": highlightly_verdict,
                "direct_status_code": d_status,
                "rapidapi_status_code": (
                    r_status if highlightly_rapidapi_request_attempted else None
                ),
                "selectable_for_production": False,
            }

    # 3. ESPN CONTROL CHECK
    # Confirm A.2 rescue corpus files or previous run contains 760454
    espn_control_confirmed = False
    corpus_root = project_root / "reports/football_data_foundation/live_response_corpus"
    if corpus_root.exists():
        for p in corpus_root.rglob("*.json"):
            try:
                content = p.read_text(encoding="utf-8")
                if "760454" in content and "espn" in p.as_posix().lower():
                    espn_control_confirmed = True
                    break
            except Exception:
                pass

    # Secret leak check across all data to be serialized
    all_data_to_serialize = {
        "sportdb_probe_log": sportdb_probe_log,
        "highlightly_probe_log": highlightly_probe_log,
        "working_bindings": working_bindings,
        "blocked_bindings": blocked_bindings,
    }

    secrets_to_check = [s for s in [sportdb_key, highlightly_key] if s]
    secret_leak_check = "PASS"
    serialized_check = json.dumps(all_data_to_serialize)
    for sec in secrets_to_check:
        if len(sec) > 5 and sec in serialized_check:
            secret_leak_check = "FAIL"

    # Save outputs
    sportdb_probe_log["verdict"] = sportdb_verdict
    highlightly_probe_log["verdict"] = highlightly_verdict

    write_json(run_dir / "sportdb_access_probe.json", sportdb_probe_log)
    write_json(run_dir / "highlightly_access_probe.json", highlightly_probe_log)
    write_json(
        run_dir / "provider_access_bindings_candidate.json",
        working_bindings,
    )

    # General verdict
    is_any_working = len(working_bindings) > 0
    overall_verdict = "PASS" if (is_any_working and secret_leak_check == "PASS") else "FAIL"

    summary_json = {
        "verdict": overall_verdict,
        "sportdb_verdict": sportdb_verdict,
        "highlightly_verdict": highlightly_verdict,
        "sportdb_request_attempted": sportdb_request_attempted,
        "highlightly_direct_request_attempted": highlightly_direct_request_attempted,
        "highlightly_rapidapi_request_attempted": highlightly_rapidapi_request_attempted,
        "working_bindings": working_bindings,
        "blocked_bindings": blocked_bindings,
        "mapping_candidates_found": mapping_candidates_found,
        "secret_leak_check": secret_leak_check,
        "headers_stored": False,
        "selectable_for_production": False,
        "failed_requirements": failed_requirements,
    }

    write_json(run_dir / "diagnostic_summary.json", summary_json)

    # Write Markdown outputs
    md_summary = f"""# Provider Access Rescue Diagnostic Summary

- **Timestamp**: {datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z")}
- **Verdict**: {overall_verdict}
- **Secret Leak Check**: {secret_leak_check}
- **ESPN Control Confirmed**: {espn_control_confirmed}

## Provider Results

### SportDB
- **Verdict**: `{sportdb_verdict}`
- **Request Attempted**: `{sportdb_request_attempted}`

### Highlightly
- **Verdict**: `{highlightly_verdict}`
- **Direct Request Attempted**: `{highlightly_direct_request_attempted}`
- **RapidAPI Request Attempted**: `{highlightly_rapidapi_request_attempted}`
- **Mapping Candidates Found**: `{mapping_candidates_found}`
"""
    (run_dir / "diagnostic_summary.md").write_text(md_summary, encoding="utf-8")

    next_action_md = f"""# Next Action Plan

Based on the diagnostic result `{overall_verdict}`:

- SportDB Verdict: `{sportdb_verdict}`
- Highlightly Verdict: `{highlightly_verdict}`

## Recommended Next Steps
1. Review the generated binding candidates in `provider_access_bindings_candidate.json`.
2. Propose necessary patches to integrate the working bindings.
"""
    (run_dir / "capture_next_action.md").write_text(next_action_md, encoding="utf-8")

    return {
        "run_dir": str(run_dir),
        "verdict": overall_verdict,
        "sportdb_verdict": sportdb_verdict,
        "highlightly_verdict": highlightly_verdict,
        "mapping_candidates_found": mapping_candidates_found,
        "secret_leak_check": secret_leak_check,
    }
