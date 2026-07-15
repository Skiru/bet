#!/usr/bin/env python3
"""SportDB MCP Shadow Adapter Implementation.

This module provides the minimal SportDB MCP client and shadow adapter
for football canonical enrichment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.integration.evidence import EvidenceRef

SPORTDB_MCP_ENDPOINT = "https://api.sportdb.dev/mcp/"
SPORTDB_MCP_ACCEPT = "application/json, text/event-stream"
SPORTDB_MCP_PARSER_VERSION = "sportdb-mcp-shadow-adapter-v1"

ALLOWED_STAT_MAP = {
    "Expected Goals": "expected_goals",
    "Expected goals (xG)": "expected_goals",
    "Shots on target": "shots_on_goal",
    "Shots off target": "shots_off_target",
    "Blocked shots": "blocked_shots",
    "Total shots": "total_shots",
    "Shots": "total_shots",
    "Corner Kicks": "corners",
    "Corners": "corners",
    "Corner kicks": "corners",
    "Yellow Cards": "yellow_cards",
    "Yellow cards": "yellow_cards",
    "Red Cards": "red_cards",
    "Red cards": "red_cards",
    "Fouls": "fouls",
    "Offsides": "offsides",
    "Ball Possession": "possession",
    "Ball possession": "possession",
    "Possession": "possession",
    "Goalkeeper Saves": "goalkeeper_saves",
    "Goalkeeper saves": "goalkeeper_saves",
    "Passes": "total_passes",
    "Successful Passes": "successful_passes",
}


class SportDBEvidenceBundleWriter:
    """Writes SportDB evidence bundle files according to the P2E_A6 contract."""

    def __init__(self, evidence_root: Path | str | None = None) -> None:
        if evidence_root is None:
            project_root = Path(__file__).resolve().parents[3]
            self.evidence_root = project_root / "betting" / "data" / "evidence"
        else:
            self.evidence_root = Path(evidence_root)

    def write_bundle(
        self,
        *,
        operation: str,
        arguments: dict[str, Any],
        raw_response: Any,
        normalized_value: Any,
        mcp_tool_name: str,
        request_identity: str,
    ) -> tuple[str, list[str], str, str, str]:
        """Writes the bundle directory and files. Returns (bundle_id, bundle_files_paths, response_sha256, normalized_sha256, schema_fingerprint)."""
        try:
            # 1. Compute response hash
            response_bytes = json.dumps(raw_response, sort_keys=True).encode("utf-8")
            response_sha256 = hashlib.sha256(response_bytes).hexdigest()

            # 2. Compute normalized hash
            normalized_bytes = json.dumps(normalized_value, sort_keys=True).encode("utf-8")
            normalized_sha256 = hashlib.sha256(normalized_bytes).hexdigest()

            # 3. Generate schema fingerprint
            if isinstance(raw_response, dict):
                fingerprint_keys = sorted(list(raw_response.keys()))
            elif isinstance(raw_response, list) and raw_response:
                if isinstance(raw_response[0], dict):
                    fingerprint_keys = sorted(list(raw_response[0].keys()))
                else:
                    fingerprint_keys = ["list_of_non_dict"]
            else:
                fingerprint_keys = ["empty_or_unknown"]
            schema_fingerprint = hashlib.sha256(json.dumps(fingerprint_keys).encode("utf-8")).hexdigest()

            # 4. Generate stable deterministic bundle_id
            bundle_input = {
                "provider": "sportdb",
                "operation": operation,
                "request_identity": request_identity,
                "mcp_tool_name": mcp_tool_name,
                "response_sha256": response_sha256,
                "normalized_sha256": normalized_sha256,
            }
            bundle_id = hashlib.sha256(json.dumps(bundle_input, sort_keys=True).encode("utf-8")).hexdigest()

            # 5. Build bundle directory path
            bundle_dir = self.evidence_root / "sportdb" / "football" / "p2e_a6" / operation / bundle_id
            bundle_dir.mkdir(parents=True, exist_ok=True)

            # 6. Prepare manifest
            created_at = datetime.now(UTC).isoformat()
            manifest = {
                "provider": "sportdb",
                "operation": operation,
                "bundle_id": bundle_id,
                "request_identity": request_identity,
                "created_at": created_at,
                "mcp_tool_name": mcp_tool_name,
                "response_sha256": response_sha256,
                "normalized_sha256": normalized_sha256,
                "parser_version": SPORTDB_MCP_PARSER_VERSION,
                "schema_fingerprint": schema_fingerprint,
                "source_summary_inputs": [
                    "certification/football/p2e_sportdb_mcp_schema_summary.json",
                    "certification/football/p2e_sportdb_mcp_football_mapping_summary.json",
                    "certification/football/p2e_sportdb_shadow_adapter_summary.json",
                    "certification/football/p2e_sportdb_replay_comparison_summary.json"
                ],
                "secret_safe": True,
            }

            # 7. Write files
            request_data = {
                "provider": "sportdb",
                "tool_name": mcp_tool_name,
                "arguments": arguments,
            }

            response_preview = {}
            if isinstance(raw_response, dict):
                preview_keys = list(raw_response.keys())[:10]
                response_preview = {k: raw_response[k] for k in preview_keys}
            elif isinstance(raw_response, list):
                response_preview = raw_response[:5]

            request_path = bundle_dir / "request.json"
            response_sha_path = bundle_dir / "response.sha256.txt"
            normalized_path = bundle_dir / "normalized.json"
            manifest_path = bundle_dir / "manifest.json"
            preview_path = bundle_dir / "response.safe_preview.json"

            try:
                from bet.resilience import atomic_write
                atomic_write(request_path, json.dumps(request_data, indent=2, sort_keys=True).encode("utf-8"))
                atomic_write(response_sha_path, (response_sha256 + "\n").encode("utf-8"))
                atomic_write(normalized_path, json.dumps(normalized_value, indent=2, sort_keys=True).encode("utf-8"))
                atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
                atomic_write(preview_path, json.dumps(response_preview, indent=2, sort_keys=True).encode("utf-8"))
            except ImportError:
                request_path.write_text(json.dumps(request_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                response_sha_path.write_text(response_sha256 + "\n", encoding="utf-8")
                normalized_path.write_text(json.dumps(normalized_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                preview_path.write_text(json.dumps(response_preview, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            project_root = Path(__file__).resolve().parents[3]
            
            def safe_rel(p: Path) -> str:
                try:
                    return str(p.relative_to(project_root))
                except ValueError:
                    return str(p.relative_to(self.evidence_root))

            written_files = [
                safe_rel(request_path),
                safe_rel(response_sha_path),
                safe_rel(normalized_path),
                safe_rel(manifest_path),
                safe_rel(preview_path),
            ]

            return bundle_id, written_files, response_sha256, normalized_sha256, schema_fingerprint
        except Exception as exc:
            raise RuntimeError(f"Failed to write evidence bundle: {exc}") from exc


class SportDBMCPError(RuntimeError):
    """Base error for SportDB MCP communication."""
    pass


class SportDBMCPAuthError(SportDBMCPError):
    """Error raised on 401 or 403 HTTP status."""
    pass


class SportDBMCPRateLimitError(SportDBMCPError):
    """Error raised on 429 HTTP status."""
    pass


class SportDBMCPNotAcceptableError(SportDBMCPError):
    """Error raised on 406 HTTP status."""
    pass


class SportDBMCPServerError(SportDBMCPError):
    """Error raised on 5xx HTTP status."""
    pass


class SportDBMCPParserError(SportDBMCPError):
    """Error raised when JSON/SSE parsing fails."""
    pass


class RequiredPayloadFieldUnknownError(RuntimeError):
    """Error raised when a required tool payload field cannot be resolved."""
    pass


class SportDBMCPClient:
    """Minimal HTTP client for SportDB MCP endpoint."""

    def __init__(self, endpoint: str = SPORTDB_MCP_ENDPOINT) -> None:
        self.endpoint = endpoint
        # Construction is offline-safe so schema validation, replay, and
        # dependency injection do not require a production secret.  The first
        # real network call resolves the credential fail-closed.
        self.api_key = self._resolve_api_key(required=False)
        self.session_id: str | None = None
        self.mcp_tool_calls_made = 0
        self.mcp_session_calls_made = 0
        self.called_tool_names: list[str] = []

    def _record_successful_rpc_call(
        self,
        rpc_method: str,
        provider_tool_name: str | None = None,
    ) -> None:
        """Record only successful JSON-RPC calls for audit accounting."""
        if rpc_method == "tools/call":
            self.mcp_tool_calls_made += 1
            if provider_tool_name:
                self.called_tool_names.append(provider_tool_name)
            return

        if rpc_method == "initialize" or rpc_method.startswith("session"):
            self.mcp_session_calls_made += 1

    def _resolve_api_key(self, *, required: bool = True) -> str:
        """Resolve API key from environment first, then .env file."""
        for alias in ("SPORTDB_API_KEY", "SPORTDB_KEY"):
            val = os.environ.get(alias, "").strip()
            if val:
                return val

        # Parse .env if present
        env_path = Path(".env")
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k in ("SPORTDB_API_KEY", "SPORTDB_KEY"):
                        if len(v) >= 2 and (
                            (v[0] == '"' and v[-1] == '"')
                            or (v[0] == "'" and v[-1] == "'")
                        ):
                            v = v[1:-1]
                        if v.strip():
                            return v.strip()
            except Exception:
                pass

        if required:
            raise SportDBMCPAuthError("SPORTDB_API_KEY not found in environment or .env file.")
        return ""

    def _parse_sse_payloads(self, raw_text: str) -> list[Any]:
        """Parse SSE payloads from raw event-stream text."""
        payloads = []
        data_lines = []

        def flush_data() -> None:
            if data_lines:
                data_text = "\n".join(data_lines).strip()
                if data_text and data_text != "[DONE]":
                    try:
                        payloads.append(json.loads(data_text))
                    except json.JSONDecodeError:
                        payloads.append({"_raw_sse_data": data_text})
                data_lines.clear()

        for raw_line in raw_text.splitlines():
            line = raw_line.rstrip("\r")
            if not line:
                flush_data()
                continue
            if line.startswith(":"):
                continue
            field, sep, value = line.partition(":")
            if not sep:
                continue
            value = value.lstrip(" ")
            if field == "data":
                data_lines.append(value)

        flush_data()
        return payloads

    def _extract_primary_payload(self, response_mode: str, parsed_payload: Any) -> Any:
        """Extract the primary JSON-RPC response dict from parsed data."""
        if response_mode == "sse":
            if isinstance(parsed_payload, list):
                for item in reversed(parsed_payload):
                    if isinstance(item, dict) and (
                        item.get("jsonrpc") == "2.0"
                        or "result" in item
                        or "error" in item
                    ):
                        return item
                if parsed_payload:
                    return parsed_payload[-1]
            return parsed_payload
        return parsed_payload

    def _extract_tool_result_payload(self, primary_payload: Any) -> Any:
        """Extract nested content from the primary JSON-RPC result payload."""
        if not isinstance(primary_payload, dict):
            return primary_payload

        # Handle top-level JSON-RPC error
        if "error" in primary_payload and primary_payload["error"] is not None:
            err = primary_payload["error"]
            err_msg = err.get("message", "Unknown error")
            err_code = err.get("code")
            raise SportDBMCPError(f"JSON-RPC error [{err_code}]: {err_msg}")

        result = primary_payload.get("result")
        if not isinstance(result, dict):
            return primary_payload

        if "structuredContent" in result:
            return result["structuredContent"]

        content = result.get("content")
        if isinstance(content, list):
            payloads = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if "json" in item and item["json"] is not None:
                    payloads.append(item["json"])
                elif "text" in item and isinstance(item["text"], str):
                    text = item["text"].strip()
                    if text.startswith("{") or text.startswith("["):
                        try:
                            payloads.append(json.loads(text))
                        except json.JSONDecodeError:
                            payloads.append(text)
                    else:
                        payloads.append(text)

            if len(payloads) == 1:
                return payloads[0]
            if payloads:
                return payloads

        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the MCP server's advertised tools using the real protocol.

        This is deliberately a ``tools/list`` JSON-RPC request, not a synthetic
        wrapper around ``tools/call``.  Authentication, response modes, session
        binding, and error mapping match :meth:`call_tool`.
        """
        if not self.api_key:
            self.api_key = self._resolve_api_key(required=True)
        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": SPORTDB_MCP_ACCEPT,
            "User-Agent": "bet-sportdb-shadow-adapter/1.0",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        body = {
            "jsonrpc": "2.0",
            "id": f"list-{int(time.time() * 1000)}",
            "method": "tools/list",
            "params": {},
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_headers = dict(response.headers.items())
                content_type = response_headers.get("Content-Type", "")
                session_id = response_headers.get("MCP-Session-Id") or response_headers.get("mcp-session-id")
                if session_id:
                    self.session_id = str(session_id).strip()
                raw_bytes = response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise SportDBMCPAuthError(f"Authentication failed with status {exc.code}") from exc
            if exc.code == 429:
                raise SportDBMCPRateLimitError("Rate limit exceeded") from exc
            if exc.code == 406:
                raise SportDBMCPNotAcceptableError("Format not acceptable") from exc
            if exc.code >= 500:
                raise SportDBMCPServerError(f"Server error with status {exc.code}") from exc
            raise SportDBMCPError(f"HTTP error with status {exc.code}") from exc
        except Exception as exc:
            raise SportDBMCPError(f"Transport/network failure: {exc}") from exc

        raw_text = raw_bytes.decode("utf-8", errors="replace")
        try:
            if "text/event-stream" in content_type.lower():
                parsed = self._parse_sse_payloads(raw_text)
                primary = self._extract_primary_payload("sse", parsed)
            else:
                primary = self._extract_primary_payload("json", json.loads(raw_text))
            result = self._extract_tool_result_payload(primary)
        except SportDBMCPError:
            raise
        except Exception as exc:
            raise SportDBMCPParserError(f"Failed to parse tools/list response: {exc}") from exc
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list) or any(not isinstance(tool, dict) for tool in tools):
            raise SportDBMCPParserError("tools/list response does not contain a tools array")
        return tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute HTTP POST to call an MCP tool."""
        if not self.api_key:
            self.api_key = self._resolve_api_key(required=True)

        headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": SPORTDB_MCP_ACCEPT,
            "User-Agent": "bet-sportdb-shadow-adapter/1.0",
        }
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id

        rpc_id = f"call-{int(time.time() * 1000)}"
        body = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_headers = dict(resp.headers.items())
                content_type = resp_headers.get("Content-Type", "")
                
                # Check for session id in response headers
                sess_id = resp_headers.get("MCP-Session-Id") or resp_headers.get("mcp-session-id")
                if sess_id:
                    self.session_id = str(sess_id).strip()

                raw_bytes = resp.read()
                status = resp.status
        except urllib.error.HTTPError as exc:
            resp_headers = dict(exc.headers.items()) if exc.headers is not None else {}
            raw_bytes = exc.read() if exc.fp is not None else b""
            status = exc.code
            
            # Map known status codes to custom exceptions
            if status in (401, 403):
                raise SportDBMCPAuthError(f"Authentication failed with status {status}")
            elif status == 429:
                raise SportDBMCPRateLimitError("Rate limit exceeded")
            elif status == 406:
                raise SportDBMCPNotAcceptableError("Format not acceptable")
            elif status >= 500:
                raise SportDBMCPServerError(f"Server error with status {status}")
            else:
                raise SportDBMCPError(f"HTTP error with status {status}")
        except Exception as exc:
            raise SportDBMCPError(f"Transport/network failure: {exc}")

        # Check response content-type
        is_sse = "text/event-stream" in content_type.lower()
        raw_text = raw_bytes.decode("utf-8", errors="replace")

        try:
            if is_sse:
                parsed_payload = self._parse_sse_payloads(raw_text)
                response_mode = "sse"
            else:
                parsed_payload = json.loads(raw_text)
                response_mode = "json"
        except Exception as exc:
            raise SportDBMCPParserError(f"Failed to parse response: {exc}")

        primary_payload = self._extract_primary_payload(response_mode, parsed_payload)
        result_payload = self._extract_tool_result_payload(primary_payload)

        # Inspect if result payload embeds upstream HTTP status errors
        if isinstance(result_payload, dict):
            src_code = result_payload.get("source_status_code")
            if src_code in (401, 403):
                raise SportDBMCPAuthError(f"Embedded authentication failure status: {src_code}")
            elif src_code == 429:
                raise SportDBMCPRateLimitError("Embedded rate limit failure")
            elif src_code == 406:
                raise SportDBMCPNotAcceptableError("Embedded format not acceptable")

        self._record_successful_rpc_call(body["method"], tool_name)
        return result_payload


class SportDBMCPShadowAdapter:
    """Adapter wrapping SportDBMCPClient to provide normalized football telemetry."""

    def __init__(
        self,
        schema_path: str | Path = "certification/football/p2e_sportdb_mcp_schema_summary.json",
        mapping_path: str | Path = "certification/football/p2e_sportdb_mcp_football_mapping_summary.json",
    ) -> None:
        self.schema_path = Path(schema_path)
        self.mapping_path = Path(mapping_path)
        
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Missing schema summary path: {self.schema_path}")
        if not self.mapping_path.exists():
            raise FileNotFoundError(f"Missing mapping summary path: {self.mapping_path}")

        self.schema_summary = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self.mapping_summary = json.loads(self.mapping_path.read_text(encoding="utf-8"))

        self.client = SportDBMCPClient()
        self.writer = SportDBEvidenceBundleWriter()

    def _build_payload(self, tool_name: str, custom_match_id: str | None = None) -> dict[str, Any]:
        """Build argument payloads using tool schemas and observed mapping values."""
        tool_schema = self.schema_summary.get("tool_schemas", {}).get(tool_name, {})
        if not tool_schema:
            raise ValueError(f"Tool schema not found for: {tool_name}")

        required_fields = tool_schema.get("required_fields", [])
        optional_fields = tool_schema.get("optional_fields", [])

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key")
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug")
        country_id_val = self.mapping_summary.get("country", {}).get("selected_country_id")
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug")
        competition_id_val = self.mapping_summary.get("competition", {}).get("selected_competition_id")
        season_val = self.mapping_summary.get("season", {}).get("selected_season")

        default_match_id = self.mapping_summary.get("finished_match_probe", {}).get("selected_match_id")
        match_id_val = custom_match_id if custom_match_id not in (None, "") else default_match_id

        known = {
            "sport": sport_val,
            "country_slug": country_slug_val,
            "country_id": country_id_val,
            "competition_slug": competition_slug_val,
            "competition_id": competition_id_val,
            "season": season_val,
            "match_id": match_id_val,
        }

        payload: dict[str, Any] = {}
        for field in required_fields:
            if field in known and known[field] not in (None, ""):
                payload[field] = known[field]
            else:
                raise RequiredPayloadFieldUnknownError(
                    f"Required payload field is unknown: {field}"
                )

        for field in optional_fields:
            if field in known and known[field] not in (None, ""):
                payload[field] = known[field]

        return payload

    def get_competition_results_shadow(self) -> Any:
        """Fetch and normalize competition results."""
        tool_name = "flashscore_get_competition_results"
        payload = self._build_payload(tool_name)
        raw_result = self.client.call_tool(tool_name, payload)
        self.last_results_raw = raw_result

        items = []
        if isinstance(raw_result, list):
            items = raw_result
        elif isinstance(raw_result, dict):
            for key in ("data", "results", "matches", "items"):
                val = raw_result.get(key)
                if isinstance(val, list):
                    items = val
                    break
            else:
                items = [raw_result]

        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            match_id = item.get("eventId") or item.get("match_id") or item.get("id") or item.get("matchId")
            home_name = item.get("homeName") or item.get("homeFirstName") or item.get("home_team", {}).get("name") if isinstance(item.get("home_team"), dict) else item.get("home_team")
            away_name = item.get("awayName") or item.get("awayFirstName") or item.get("away_team", {}).get("name") if isinstance(item.get("away_team"), dict) else item.get("away_team")
            status = item.get("eventStage") or item.get("status") or item.get("state")
            
            home_score = item.get("homeScore") or item.get("homeFullTimeScore") or item.get("home_score")
            away_score = item.get("awayScore") or item.get("awayFullTimeScore") or item.get("away_score")
            score = item.get("score")
            if not score and home_score is not None and away_score is not None:
                score = f"{home_score}-{away_score}"

            normalized.append({
                "provider_match_id": match_id,
                "home_name": home_name,
                "away_name": away_name,
                "status": status,
                "score": score,
                "parser_version": SPORTDB_MCP_PARSER_VERSION,
            })
        return normalized

    def get_match_stats_shadow(self, match_id: str | None = None) -> Any:
        """Fetch and normalize match statistics."""
        tool_name = "flashscore_get_match_stats"
        payload = self._build_payload(tool_name, custom_match_id=match_id)
        raw_result = self.client.call_tool(tool_name, payload)

        top_level_keys = sorted(list(raw_result.keys())) if isinstance(raw_result, dict) else []
        raw_stat_field_names = set()
        raw_stat_group_names = set()
        normalized_metric_names = set()
        unknown_metrics = set()
        team_side_detection = "UNKNOWN"

        periods = []
        if isinstance(raw_result, dict):
            periods = raw_result.get("data") or []
            if not isinstance(periods, list):
                periods = []
        elif isinstance(raw_result, list):
            periods = raw_result

        for p in periods:
            if not isinstance(p, dict):
                continue
            group_name = p.get("period") or p.get("group")
            if group_name:
                raw_stat_group_names.add(str(group_name))

            stats_list = p.get("stats") or p.get("items") or []
            if isinstance(stats_list, list):
                for stat in stats_list:
                    if not isinstance(stat, dict):
                        continue
                    name = stat.get("statName") or stat.get("name") or stat.get("label")
                    if name:
                        name_str = str(name).strip()
                        raw_stat_field_names.add(name_str)
                        norm = ALLOWED_STAT_MAP.get(name_str)
                        if norm:
                            normalized_metric_names.add(norm)
                        else:
                            unknown_metrics.add(name_str)

                    if "homeValue" in stat or "awayValue" in stat or "home_value" in stat or "away_value" in stat:
                        team_side_detection = "DETECTED_HOME_AWAY"

        target_match_id = payload.get("match_id")

        return {
            "provider_match_id": target_match_id,
            "top_level_keys": top_level_keys,
            "raw_stat_field_names": sorted(list(raw_stat_field_names)),
            "raw_stat_group_names": sorted(list(raw_stat_group_names)),
            "normalized_metric_names": sorted(list(normalized_metric_names)),
            "unknown_metrics": sorted(list(unknown_metrics)),
            "team_side_detection": team_side_detection,
            "raw_result": raw_result,
        }

    def get_match_events_shadow(self, match_id: str | None = None) -> Any:
        """Fetch and normalize match events."""
        tool_name = "flashscore_get_match_events"
        payload = self._build_payload(tool_name, custom_match_id=match_id)
        raw_result = self.client.call_tool(tool_name, payload)

        events_list = []
        if isinstance(raw_result, dict):
            data = raw_result.get("data")
            if isinstance(data, dict):
                events_list = data.get("events") or []
            elif isinstance(data, list):
                events_list = data
            else:
                events_list = raw_result.get("events") or []
        elif isinstance(raw_result, list):
            events_list = raw_result

        event_count = len(events_list)
        event_type_names = set()
        goal_count = 0
        card_count = 0

        for ev in events_list:
            if not isinstance(ev, dict):
                continue
            type_name = ev.get("incidentTypeName") or ev.get("incidentType") or ev.get("type")
            if type_name:
                if isinstance(type_name, list):
                    for t in type_name:
                        event_type_names.add(str(t))
                else:
                    event_type_names.add(str(type_name))

            type_str = ""
            if isinstance(type_name, list):
                type_str = " ".join([str(t).lower() for t in type_name])
            elif type_name:
                type_str = str(type_name).lower()

            if "goal" in type_str:
                goal_count += 1
            if "card" in type_str or "yellow" in type_str or "red" in type_str:
                card_count += 1

        target_match_id = payload.get("match_id")

        return {
            "provider_match_id": target_match_id,
            "event_count": event_count,
            "event_type_names": sorted(list(event_type_names)),
            "goal_count": goal_count,
            "card_count": card_count,
            "raw_result": raw_result,
        }

    def get_match_lineups_shadow(self, match_id: str | None = None) -> Any:
        """Fetch and normalize match lineups."""
        tool_name = "flashscore_get_match_lineups"
        payload = self._build_payload(tool_name, custom_match_id=match_id)
        raw_result = self.client.call_tool(tool_name, payload)

        formation_values = set()
        player_count = 0

        teams_data = []
        if isinstance(raw_result, dict):
            teams_data = raw_result.get("data") or []
            if not isinstance(teams_data, list):
                teams_data = [raw_result]
        elif isinstance(raw_result, list):
            teams_data = raw_result

        for team_item in teams_data:
            if not isinstance(team_item, dict):
                continue
            for side in ("home", "away", "players", "starters", "substitutes"):
                players_list = team_item.get(side)
                if isinstance(players_list, list):
                    player_count += len(players_list)
                    for player in players_list:
                        if isinstance(player, dict):
                            form = player.get("formation")
                            if form:
                                formation_values.add(str(form))

            team_formation = team_item.get("formation")
            if team_formation:
                formation_values.add(str(team_formation))

        target_match_id = payload.get("match_id")

        return {
            "provider_match_id": target_match_id,
            "formation_values": sorted(list(formation_values)),
            "player_count": player_count,
            "raw_result": raw_result,
        }

    def get_competition_standings_shadow(self) -> Any:
        """Fetch and normalize competition standings."""
        tool_name = "flashscore_get_competition_standings"
        payload = self._build_payload(tool_name)
        raw_result = self.client.call_tool(tool_name, payload)

        top_level_keys = sorted(list(raw_result.keys())) if isinstance(raw_result, dict) else []
        rows = []
        if isinstance(raw_result, dict):
            rows = raw_result.get("data") or []
            if not isinstance(rows, list):
                rows = []
        elif isinstance(raw_result, list):
            rows = raw_result

        row_count = len(rows)
        team_names = set()
        for r in rows:
            if not isinstance(r, dict):
                continue
            team_name = r.get("teamName") or r.get("team_name") or r.get("team", {}).get("name") if isinstance(r.get("team"), dict) else r.get("team")
            if not team_name:
                team_name = r.get("participantName") or r.get("name")
            if team_name:
                team_names.add(str(team_name))

        return {
            "row_count": row_count,
            "team_names": sorted(list(team_names)),
            "top_level_keys": top_level_keys,
            "raw_result": raw_result,
        }

    def get_competition_results_with_evidence(self) -> SourceOperationResult[Any]:
        """Fetch competition results, normalize them, and write the evidence bundle."""
        tool_name = "flashscore_get_competition_results"
        operation = "competition_results"
        retrieved_at = datetime.now(UTC)

        try:
            payload = self._build_payload(tool_name)
        except RequiredPayloadFieldUnknownError:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                provider="sportdb",
                operation=operation,
                error_code="missing_required_fields",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key") or "football"
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug") or "england"
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug") or "premier-league"
        season_val = self.mapping_summary.get("season", {}).get("selected_season") or "2025-2026"
        request_identity = f"sportdb:{operation}:{sport_val}:{country_slug_val}:{competition_slug_val}:{season_val}"

        try:
            raw_result = self.client.call_tool(tool_name, payload)
        except SportDBMCPAuthError:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="auth_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPRateLimitError:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="rate_limited",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPParserError:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="parser_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except (SportDBMCPError, Exception) as exc:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code=type(exc).__name__,
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        try:
            items = []
            if isinstance(raw_result, list):
                items = raw_result
            elif isinstance(raw_result, dict):
                for key in ("data", "results", "matches", "items"):
                    val = raw_result.get(key)
                    if isinstance(val, list):
                        items = val
                        break
                else:
                    items = [raw_result]

            normalized = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                match_id = item.get("eventId") or item.get("match_id") or item.get("id") or item.get("matchId")
                home_name = item.get("homeName") or item.get("homeFirstName") or item.get("home_team", {}).get("name") if isinstance(item.get("home_team"), dict) else item.get("home_team")
                away_name = item.get("awayName") or item.get("awayFirstName") or item.get("away_team", {}).get("name") if isinstance(item.get("away_team"), dict) else item.get("away_team")
                status = item.get("eventStage") or item.get("status") or item.get("state")
                
                home_score = item.get("homeScore") or item.get("homeFullTimeScore") or item.get("home_score")
                away_score = item.get("awayScore") or item.get("awayFullTimeScore") or item.get("away_score")
                score = item.get("score")
                if not score and home_score is not None and away_score is not None:
                    score = f"{home_score}-{away_score}"

                normalized.append({
                    "provider_match_id": match_id,
                    "home_name": home_name,
                    "away_name": away_name,
                    "status": status,
                    "score": score,
                    "parser_version": SPORTDB_MCP_PARSER_VERSION,
                })
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="normalization_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        status_code = SourceResultStatus.SUCCESS
        if not normalized:
            status_code = SourceResultStatus.VALID_EMPTY

        try:
            bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = self.writer.write_bundle(
                operation=operation,
                arguments=payload,
                raw_response=raw_result,
                normalized_value=normalized,
                mcp_tool_name=tool_name,
                request_identity=request_identity,
            )
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.EVIDENCE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="evidence_write_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        evidence_ref = EvidenceRef(
            operation=operation,
            request_identity=request_identity,
            media_type="application/json",
            byte_size=len(json.dumps(raw_result).encode("utf-8")),
            object_sha256=response_sha256,
            captured_at=retrieved_at.isoformat(),
        )

        return SourceOperationResult(
            status=status_code,
            value=normalized,
            provider="sportdb",
            operation=operation,
            request_identity=request_identity,
            evidence_refs=(evidence_ref,),
            bundle_id=bundle_id,
            retrieved_at=retrieved_at,
            parser_version=SPORTDB_MCP_PARSER_VERSION,
            schema_fingerprint=schema_fingerprint,
        )

    def get_match_stats_with_evidence(self, match_id: str | None = None) -> SourceOperationResult[Any]:
        """Fetch match stats, normalize them, and write the evidence bundle."""
        tool_name = "flashscore_get_match_stats"
        operation = "match_stats"
        retrieved_at = datetime.now(UTC)

        try:
            payload = self._build_payload(tool_name, custom_match_id=match_id)
        except RequiredPayloadFieldUnknownError:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                provider="sportdb",
                operation=operation,
                error_code="missing_required_fields",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key") or "football"
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug") or "england"
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug") or "premier-league"
        season_val = self.mapping_summary.get("season", {}).get("selected_season") or "2025-2026"
        target_match_id = payload.get("match_id") or ""
        request_identity = f"sportdb:{operation}:{sport_val}:{country_slug_val}:{competition_slug_val}:{season_val}:{target_match_id}"

        try:
            raw_result = self.client.call_tool(tool_name, payload)
        except SportDBMCPAuthError:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="auth_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPRateLimitError:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="rate_limited",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPParserError:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="parser_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except (SportDBMCPError, Exception) as exc:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code=type(exc).__name__,
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        try:
            top_level_keys = sorted(list(raw_result.keys())) if isinstance(raw_result, dict) else []
            raw_stat_field_names = set()
            raw_stat_group_names = set()
            normalized_metric_names = set()
            unknown_metrics = set()
            team_side_detection = "UNKNOWN"

            periods = []
            if isinstance(raw_result, dict):
                periods = raw_result.get("data") or []
                if not isinstance(periods, list):
                    periods = []
            elif isinstance(raw_result, list):
                periods = raw_result

            for p in periods:
                if not isinstance(p, dict):
                    continue
                group_name = p.get("period") or p.get("group")
                if group_name:
                    raw_stat_group_names.add(str(group_name))

                stats_list = p.get("stats") or p.get("items") or []
                if isinstance(stats_list, list):
                    for stat in stats_list:
                        if not isinstance(stat, dict):
                            continue
                        name = stat.get("statName") or stat.get("name") or stat.get("label")
                        if name:
                            name_str = str(name).strip()
                            raw_stat_field_names.add(name_str)
                            norm = ALLOWED_STAT_MAP.get(name_str)
                            if norm:
                                normalized_metric_names.add(norm)
                            else:
                                unknown_metrics.add(name_str)

                        if "homeValue" in stat or "awayValue" in stat or "home_value" in stat or "away_value" in stat:
                            team_side_detection = "DETECTED_HOME_AWAY"

            normalized = {
                "provider_match_id": target_match_id,
                "top_level_keys": top_level_keys,
                "raw_stat_field_names": sorted(list(raw_stat_field_names)),
                "raw_stat_group_names": sorted(list(raw_stat_group_names)),
                "normalized_metric_names": sorted(list(normalized_metric_names)),
                "unknown_metrics": sorted(list(unknown_metrics)),
                "team_side_detection": team_side_detection,
                "raw_result": raw_result,
            }
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="normalization_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        status_code = SourceResultStatus.SUCCESS
        if not raw_result:
            status_code = SourceResultStatus.VALID_EMPTY

        try:
            bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = self.writer.write_bundle(
                operation=operation,
                arguments=payload,
                raw_response=raw_result,
                normalized_value=normalized,
                mcp_tool_name=tool_name,
                request_identity=request_identity,
            )
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.EVIDENCE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="evidence_write_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        evidence_ref = EvidenceRef(
            operation=operation,
            request_identity=request_identity,
            media_type="application/json",
            byte_size=len(json.dumps(raw_result).encode("utf-8")),
            object_sha256=response_sha256,
            captured_at=retrieved_at.isoformat(),
        )

        return SourceOperationResult(
            status=status_code,
            value=normalized,
            provider="sportdb",
            operation=operation,
            request_identity=request_identity,
            evidence_refs=(evidence_ref,),
            bundle_id=bundle_id,
            retrieved_at=retrieved_at,
            parser_version=SPORTDB_MCP_PARSER_VERSION,
            schema_fingerprint=schema_fingerprint,
        )

    def get_match_events_with_evidence(self, match_id: str | None = None) -> SourceOperationResult[Any]:
        """Fetch match events, normalize them, and write the evidence bundle."""
        tool_name = "flashscore_get_match_events"
        operation = "match_events"
        retrieved_at = datetime.now(UTC)

        try:
            payload = self._build_payload(tool_name, custom_match_id=match_id)
        except RequiredPayloadFieldUnknownError:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                provider="sportdb",
                operation=operation,
                error_code="missing_required_fields",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key") or "football"
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug") or "england"
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug") or "premier-league"
        season_val = self.mapping_summary.get("season", {}).get("selected_season") or "2025-2026"
        target_match_id = payload.get("match_id") or ""
        request_identity = f"sportdb:{operation}:{sport_val}:{country_slug_val}:{competition_slug_val}:{season_val}:{target_match_id}"

        try:
            raw_result = self.client.call_tool(tool_name, payload)
        except SportDBMCPAuthError:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="auth_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPRateLimitError:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="rate_limited",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPParserError:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="parser_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except (SportDBMCPError, Exception) as exc:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code=type(exc).__name__,
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        try:
            events_list = []
            if isinstance(raw_result, dict):
                data = raw_result.get("data")
                if isinstance(data, dict):
                    events_list = data.get("events") or []
                elif isinstance(data, list):
                    events_list = data
                else:
                    events_list = raw_result.get("events") or []
            elif isinstance(raw_result, list):
                events_list = raw_result

            event_count = len(events_list)
            event_type_names = set()
            goal_count = 0
            card_count = 0

            for ev in events_list:
                if not isinstance(ev, dict):
                    continue
                type_name = ev.get("incidentTypeName") or ev.get("incidentType") or ev.get("type")
                if type_name:
                    if isinstance(type_name, list):
                        for t in type_name:
                            event_type_names.add(str(t))
                    else:
                        event_type_names.add(str(type_name))

                type_str = ""
                if isinstance(type_name, list):
                    type_str = " ".join([str(t).lower() for t in type_name])
                elif type_name:
                    type_str = str(type_name).lower()

                if "goal" in type_str:
                    goal_count += 1
                if "card" in type_str or "yellow" in type_str or "red" in type_str:
                    card_count += 1

            normalized = {
                "provider_match_id": target_match_id,
                "event_count": event_count,
                "event_type_names": sorted(list(event_type_names)),
                "goal_count": goal_count,
                "card_count": card_count,
                "raw_result": raw_result,
            }
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="normalization_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        status_code = SourceResultStatus.SUCCESS
        if not raw_result:
            status_code = SourceResultStatus.VALID_EMPTY

        try:
            bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = self.writer.write_bundle(
                operation=operation,
                arguments=payload,
                raw_response=raw_result,
                normalized_value=normalized,
                mcp_tool_name=tool_name,
                request_identity=request_identity,
            )
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.EVIDENCE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="evidence_write_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        evidence_ref = EvidenceRef(
            operation=operation,
            request_identity=request_identity,
            media_type="application/json",
            byte_size=len(json.dumps(raw_result).encode("utf-8")),
            object_sha256=response_sha256,
            captured_at=retrieved_at.isoformat(),
        )

        return SourceOperationResult(
            status=status_code,
            value=normalized,
            provider="sportdb",
            operation=operation,
            request_identity=request_identity,
            evidence_refs=(evidence_ref,),
            bundle_id=bundle_id,
            retrieved_at=retrieved_at,
            parser_version=SPORTDB_MCP_PARSER_VERSION,
            schema_fingerprint=schema_fingerprint,
        )

    def get_match_lineups_with_evidence(self, match_id: str | None = None) -> SourceOperationResult[Any]:
        """Fetch match lineups, normalize them, and write the evidence bundle."""
        tool_name = "flashscore_get_match_lineups"
        operation = "match_lineups"
        retrieved_at = datetime.now(UTC)

        try:
            payload = self._build_payload(tool_name, custom_match_id=match_id)
        except RequiredPayloadFieldUnknownError:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                provider="sportdb",
                operation=operation,
                error_code="missing_required_fields",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key") or "football"
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug") or "england"
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug") or "premier-league"
        season_val = self.mapping_summary.get("season", {}).get("selected_season") or "2025-2026"
        target_match_id = payload.get("match_id") or ""
        request_identity = f"sportdb:{operation}:{sport_val}:{country_slug_val}:{competition_slug_val}:{season_val}:{target_match_id}"

        try:
            raw_result = self.client.call_tool(tool_name, payload)
        except SportDBMCPAuthError:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="auth_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPRateLimitError:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="rate_limited",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPParserError:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="parser_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except (SportDBMCPError, Exception) as exc:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code=type(exc).__name__,
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        try:
            formation_values = set()
            player_count = 0

            teams_data = []
            if isinstance(raw_result, dict):
                teams_data = raw_result.get("data") or []
                if not isinstance(teams_data, list):
                    teams_data = [raw_result]
            elif isinstance(raw_result, list):
                teams_data = raw_result

            for team_item in teams_data:
                if not isinstance(team_item, dict):
                    continue
                for side in ("home", "away", "players", "starters", "substitutes"):
                    players_list = team_item.get(side)
                    if isinstance(players_list, list):
                        player_count += len(players_list)
                        for player in players_list:
                            if isinstance(player, dict):
                                form = player.get("formation")
                                if form:
                                    formation_values.add(str(form))

                team_formation = team_item.get("formation")
                if team_formation:
                    formation_values.add(str(team_formation))

            normalized = {
                "provider_match_id": target_match_id,
                "formation_values": sorted(list(formation_values)),
                "player_count": player_count,
                "raw_result": raw_result,
            }
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="normalization_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        status_code = SourceResultStatus.SUCCESS
        if not raw_result:
            status_code = SourceResultStatus.VALID_EMPTY

        try:
            bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = self.writer.write_bundle(
                operation=operation,
                arguments=payload,
                raw_response=raw_result,
                normalized_value=normalized,
                mcp_tool_name=tool_name,
                request_identity=request_identity,
            )
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.EVIDENCE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="evidence_write_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        evidence_ref = EvidenceRef(
            operation=operation,
            request_identity=request_identity,
            media_type="application/json",
            byte_size=len(json.dumps(raw_result).encode("utf-8")),
            object_sha256=response_sha256,
            captured_at=retrieved_at.isoformat(),
        )

        return SourceOperationResult(
            status=status_code,
            value=normalized,
            provider="sportdb",
            operation=operation,
            request_identity=request_identity,
            evidence_refs=(evidence_ref,),
            bundle_id=bundle_id,
            retrieved_at=retrieved_at,
            parser_version=SPORTDB_MCP_PARSER_VERSION,
            schema_fingerprint=schema_fingerprint,
        )

    def get_competition_standings_with_evidence(self) -> SourceOperationResult[Any]:
        """Fetch competition standings, normalize them, and write the evidence bundle."""
        tool_name = "flashscore_get_competition_standings"
        operation = "competition_standings"
        retrieved_at = datetime.now(UTC)

        try:
            payload = self._build_payload(tool_name)
        except RequiredPayloadFieldUnknownError:
            return SourceOperationResult(
                status=SourceResultStatus.SCHEMA_ERROR,
                provider="sportdb",
                operation=operation,
                error_code="missing_required_fields",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        sport_val = self.mapping_summary.get("sport", {}).get("selected_sport_key") or "football"
        country_slug_val = self.mapping_summary.get("country", {}).get("selected_country_slug") or "england"
        competition_slug_val = self.mapping_summary.get("competition", {}).get("selected_competition_slug") or "premier-league"
        season_val = self.mapping_summary.get("season", {}).get("selected_season") or "2025-2026"
        request_identity = f"sportdb:{operation}:{sport_val}:{country_slug_val}:{competition_slug_val}:{season_val}"

        try:
            raw_result = self.client.call_tool(tool_name, payload)
        except SportDBMCPAuthError:
            return SourceOperationResult(
                status=SourceResultStatus.AUTHENTICATION_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="auth_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPRateLimitError:
            return SourceOperationResult(
                status=SourceResultStatus.RATE_LIMITED,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="rate_limited",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except SportDBMCPParserError:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="parser_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )
        except (SportDBMCPError, Exception) as exc:
            return SourceOperationResult(
                status=SourceResultStatus.TRANSPORT_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code=type(exc).__name__,
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        try:
            top_level_keys = sorted(list(raw_result.keys())) if isinstance(raw_result, dict) else []
            rows = []
            if isinstance(raw_result, dict):
                rows = raw_result.get("data") or []
                if not isinstance(rows, list):
                    rows = []
            elif isinstance(raw_result, list):
                rows = raw_result

            row_count = len(rows)
            team_names = set()
            for r in rows:
                if not isinstance(r, dict):
                    continue
                team_name = r.get("teamName") or r.get("team_name") or r.get("team", {}).get("name") if isinstance(r.get("team"), dict) else r.get("team")
                if not team_name:
                    team_name = r.get("participantName") or r.get("name")
                if team_name:
                    team_names.add(str(team_name))

            normalized = {
                "row_count": row_count,
                "team_names": sorted(list(team_names)),
                "top_level_keys": top_level_keys,
                "raw_result": raw_result,
            }
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.PARSE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="normalization_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        status_code = SourceResultStatus.SUCCESS
        if not raw_result:
            status_code = SourceResultStatus.VALID_EMPTY

        try:
            bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = self.writer.write_bundle(
                operation=operation,
                arguments=payload,
                raw_response=raw_result,
                normalized_value=normalized,
                mcp_tool_name=tool_name,
                request_identity=request_identity,
            )
        except Exception as exc:
            return SourceOperationResult(
                status=SourceResultStatus.EVIDENCE_ERROR,
                provider="sportdb",
                operation=operation,
                request_identity=request_identity,
                error_code="evidence_write_error",
                parser_version=SPORTDB_MCP_PARSER_VERSION,
                retrieved_at=retrieved_at,
            )

        evidence_ref = EvidenceRef(
            operation=operation,
            request_identity=request_identity,
            media_type="application/json",
            byte_size=len(json.dumps(raw_result).encode("utf-8")),
            object_sha256=response_sha256,
            captured_at=retrieved_at.isoformat(),
        )

        return SourceOperationResult(
            status=status_code,
            value=normalized,
            provider="sportdb",
            operation=operation,
            request_identity=request_identity,
            evidence_refs=(evidence_ref,),
            bundle_id=bundle_id,
            retrieved_at=retrieved_at,
            parser_version=SPORTDB_MCP_PARSER_VERSION,
            schema_fingerprint=schema_fingerprint,
        )
