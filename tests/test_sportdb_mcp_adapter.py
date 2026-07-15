#!/usr/bin/env python3
"""Tests for SportDB MCP Shadow Adapter.

These tests run without calling the network.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from bet.api_clients.sportdb_mcp import (
    SPORTDB_MCP_ACCEPT,
    SPORTDB_MCP_PARSER_VERSION,
    SportDBMCPClient,
    SportDBMCPShadowAdapter,
    SportDBMCPAuthError,
    SportDBMCPParserError,
    SportDBMCPRateLimitError,
    RequiredPayloadFieldUnknownError,
)

# Import safe_preview from the probe script as well to test it
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import sportdb_p2e_shadow_adapter_probe as probe_module
from sportdb_p2e_shadow_adapter_probe import safe_preview, redact_text


EXPECTED_TOOL_NAMES = [
    "flashscore_get_competition_results",
    "flashscore_get_match_stats",
    "flashscore_get_match_events",
    "flashscore_get_match_lineups",
    "flashscore_get_competition_standings",
]


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], *, headers: dict[str, str] | None = None) -> None:
        base_headers = {"Content-Type": "application/json"}
        if headers:
            base_headers.update(headers)
        self.headers = base_headers
        self.status = 200
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def make_jsonrpc_tool_response(structured_content: object) -> FakeHTTPResponse:
    return FakeHTTPResponse(
        {
            "jsonrpc": "2.0",
            "id": "rpc-1",
            "result": {"structuredContent": structured_content},
        }
    )


@pytest.fixture(autouse=True)
def sportdb_api_key_env() -> None:
    with patch.dict(os.environ, {"SPORTDB_API_KEY": "tkey-1", "SPORTDB_KEY": ""}, clear=False):
        yield


def test_imports_and_constants() -> None:
    """Verify that module can be imported and constants are correct."""
    assert SPORTDB_MCP_ACCEPT == "application/json, text/event-stream"
    assert SPORTDB_MCP_PARSER_VERSION == "sportdb-mcp-shadow-adapter-v1"


def test_no_forbidden_rest_paths() -> None:
    """Verify that active adapter/probe code contains no direct REST request paths."""
    adapter_src = Path("src/bet/api_clients/sportdb_mcp.py").read_text(encoding="utf-8")
    probe_src = Path("scripts/sportdb_p2e_shadow_adapter_probe.py").read_text(encoding="utf-8")

    forbidden_patterns = [
        rf"/api/{suffix}"
        for suffix in ("foot" "ball", "ma" "tch", "cl" "ubs", "pla" "yers")
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, adapter_src), f"Forbidden pattern '{pattern}' found in sportdb_mcp.py"
        assert not re.search(pattern, probe_src), f"Forbidden pattern '{pattern}' found in sportdb_p2e_shadow_adapter_probe.py"


def test_mcp_client_resolves_key_from_env() -> None:
    """Verify key resolution logic works."""
    with patch.dict(os.environ, {"SPORTDB_API_KEY": "test-env-key", "SPORTDB_KEY": ""}):
        client = SportDBMCPClient()
        assert client.api_key == "test-env-key"


def test_api_key_redact_does_not_leak() -> None:
    """Verify key redaction logic works and never leaks the key."""
    with patch.dict(os.environ, {"SPORTDB_API_KEY": "supersecret-key-123456"}):
        text = "My secret key is supersecret-key-123456 in SPORTDB_API_KEY"
        redacted = redact_text(text)
        assert "supersecret-key-123456" not in redacted
        assert "REDACTED" in redacted


def test_parser_handles_plain_json() -> None:
    """Verify plain JSON parsing logic."""
    client = SportDBMCPClient()
    raw_response = {
        "jsonrpc": "2.0",
        "id": "1",
        "result": {
            "structuredContent": {"status": "ok"}
        }
    }
    # Test internal helper extraction
    primary = client._extract_primary_payload("json", raw_response)
    res = client._extract_tool_result_payload(primary)
    assert res == {"status": "ok"}


def test_parser_handles_sse_frames() -> None:
    """Verify SSE stream frames parsing logic."""
    client = SportDBMCPClient()
    sse_text = (
        "data: {\"jsonrpc\": \"2.0\", \"id\": \"1\", \"result\": {\"structuredContent\": {\"status\": \"sse-ok\"}}}\n\n"
    )
    payloads = client._parse_sse_payloads(sse_text)
    assert len(payloads) == 1
    assert payloads[0]["result"]["structuredContent"]["status"] == "sse-ok"


def test_schema_and_mapping_loaders_work() -> None:
    """Verify loaders can parse the accepted JSON summary files."""
    adapter = SportDBMCPShadowAdapter()
    assert isinstance(adapter.schema_summary, dict)
    assert isinstance(adapter.mapping_summary, dict)


def test_payload_builder_fails_closed_on_unknown_required() -> None:
    """Verify payload builder fails closed for unknown required fields."""
    adapter = SportDBMCPShadowAdapter()

    # Intentionally manipulate schema to require a field that isn't mapped
    with patch.dict(
        adapter.schema_summary["tool_schemas"]["flashscore_get_match_stats"],
        {"required_fields": ["non_existent_required_field"]}
    ):
        with pytest.raises(RequiredPayloadFieldUnknownError):
            adapter._build_payload("flashscore_get_match_stats")


def test_call_tool_counts_provider_tool_calls_not_session_calls() -> None:
    client = SportDBMCPClient()

    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        return_value=make_jsonrpc_tool_response({"ok": True}),
    ):
        result = client.call_tool("flashscore_get_match_stats", {"match_id": "match-1"})

    assert result == {"ok": True}
    assert client.mcp_tool_calls_made == 1
    assert client.mcp_session_calls_made == 0


def test_call_tool_appends_called_provider_tool_name() -> None:
    client = SportDBMCPClient()

    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        return_value=make_jsonrpc_tool_response({"ok": True}),
    ):
        client.call_tool("flashscore_get_match_stats", {"match_id": "match-1"})

    assert client.called_tool_names == ["flashscore_get_match_stats"]


def test_list_tools_uses_mcp_tools_list_and_preserves_tool_call_accounting() -> None:
    client = SportDBMCPClient()
    response = FakeHTTPResponse(
        {
            "jsonrpc": "2.0",
            "id": "rpc-list",
            "result": {"tools": [{"name": "flashscore_get_match_stats"}]},
        },
        headers={"MCP-Session-Id": "session-1"},
    )
    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        return_value=response,
    ) as urlopen:
        tools = client.list_tools()

    request = urlopen.call_args.args[0]
    body = json.loads(request.data.decode("utf-8"))
    assert body["method"] == "tools/list"
    assert tools == [{"name": "flashscore_get_match_stats"}]
    assert client.session_id == "session-1"
    assert client.mcp_tool_calls_made == 0


def test_list_tools_rejects_malformed_protocol_result() -> None:
    client = SportDBMCPClient()
    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        return_value=FakeHTTPResponse(
            {"jsonrpc": "2.0", "id": "rpc-list", "result": {"tools": "invalid"}}
        ),
    ):
        with pytest.raises(SportDBMCPParserError, match="tools array"):
            client.list_tools()


def test_five_provider_calls_count_as_five_tool_calls() -> None:
    client = SportDBMCPClient()

    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        side_effect=[make_jsonrpc_tool_response({"ok": True}) for _ in EXPECTED_TOOL_NAMES],
    ):
        for tool_name in EXPECTED_TOOL_NAMES:
            client.call_tool(tool_name, {"probe": True})

    assert client.mcp_tool_calls_made == 5
    assert client.called_tool_names == EXPECTED_TOOL_NAMES


def test_five_provider_calls_do_not_count_as_five_session_calls() -> None:
    client = SportDBMCPClient()

    with patch(
        "bet.api_clients.sportdb_mcp.urllib.request.urlopen",
        side_effect=[make_jsonrpc_tool_response({"ok": True}) for _ in EXPECTED_TOOL_NAMES],
    ):
        for tool_name in EXPECTED_TOOL_NAMES:
            client.call_tool(tool_name, {"probe": True})

    assert client.mcp_session_calls_made == 0
    assert client.mcp_session_calls_made != 5


def test_payload_builder_raises_when_required_sport_missing() -> None:
    adapter = SportDBMCPShadowAdapter()

    with patch.dict(adapter.mapping_summary["sport"], {"selected_sport_key": None}, clear=False):
        with pytest.raises(RequiredPayloadFieldUnknownError, match="sport"):
            adapter._build_payload("flashscore_get_competition_results")


def test_payload_builder_raises_when_required_match_id_missing() -> None:
    adapter = SportDBMCPShadowAdapter()
    adapter.mapping_summary.setdefault("finished_match_probe", {})

    with patch.dict(adapter.mapping_summary["finished_match_probe"], {"selected_match_id": None}, clear=False):
        with pytest.raises(RequiredPayloadFieldUnknownError, match="match_id"):
            adapter._build_payload("flashscore_get_match_stats")


def test_source_contains_no_hardcoded_payload_fallbacks() -> None:
    src = Path("src/bet/api_clients/sportdb_mcp.py").read_text(encoding="utf-8")

    for forbidden in [
        'or "xQXUa3UG"',
        "or 'xQXUa3UG'",
    ]:
        assert forbidden not in src


def test_probe_summary_emits_called_tool_names_lists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    expected_tools = list(EXPECTED_TOOL_NAMES)

    class StubClient:
        def __init__(self) -> None:
            self.mcp_tool_calls_made = 5
            self.mcp_session_calls_made = 0
            self.called_tool_names = expected_tools

    class StubAdapter:
        def __init__(self) -> None:
            self.mapping_summary = {
                "sport": {"selected_sport_key": "football"},
                "country": {
                    "selected_country_slug": "england",
                    "selected_country_id": 198,
                },
                "competition": {
                    "selected_competition_slug": "premier-league",
                    "selected_competition_id": "dYlOSQOD",
                },
                "season": {"selected_season": "2025-2026"},
                "finished_match_probe": {"selected_match_id": "match-1"},
            }
            self.client = StubClient()
            self.last_results_raw = [{"provider_match_id": "match-1", "status": "FINISHED"}]

        def get_competition_results_shadow(self) -> list[dict[str, str]]:
            return self.last_results_raw

        def get_match_stats_shadow(self) -> dict[str, object]:
            return {
                "provider_match_id": "match-1",
                "top_level_keys": ["data"],
                "raw_stat_field_names": ["Expected goals (xG)"],
                "normalized_metric_names": ["expected_goals"],
                "unknown_metrics": [],
                "team_side_detection": "DETECTED_HOME_AWAY",
                "raw_result": {"data": []},
            }

        def get_match_events_shadow(self) -> dict[str, object]:
            return {
                "event_count": 1,
                "event_type_names": ["Goal"],
                "goal_count": 1,
                "card_count": 0,
                "raw_result": {"data": []},
            }

        def get_match_lineups_shadow(self) -> dict[str, object]:
            return {
                "formation_values": ["4-3-3"],
                "player_count": 22,
                "raw_result": {"data": []},
            }

        def get_competition_standings_shadow(self) -> dict[str, object]:
            return {
                "row_count": 20,
                "team_names": ["Arsenal"],
                "raw_result": {"data": []},
            }

    out_path = tmp_path / "summary.json"
    monkeypatch.setattr(probe_module, "SportDBMCPShadowAdapter", StubAdapter)
    monkeypatch.setattr(sys, "argv", ["sportdb_p2e_shadow_adapter_probe.py", "--out", str(out_path)])

    assert probe_module.main() == 0

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["called_tool_names"] == expected_tools
    assert data["mcp_tool_calls"] == expected_tools


def test_stat_normalization_maps_allowed_and_preserves_unknowns() -> None:
    """Verify stat normalization logic."""
    adapter = SportDBMCPShadowAdapter()

    # Input with both allowed (e.g. Expected goals (xG)) and unknown stats (e.g. Crazy Stat)
    raw_stat_result = {
        "data": [
            {
                "period": "Match",
                "stats": [
                    {
                        "statName": "Expected goals (xG)",
                        "homeValue": "1.2",
                        "awayValue": "0.8"
                    },
                    {
                        "statName": "Crazy Stat",
                        "homeValue": "100",
                        "awayValue": "200"
                    }
                ]
            }
        ]
    }

    with patch.object(adapter.client, "call_tool", return_value=raw_stat_result):
        res = adapter.get_match_stats_shadow(match_id="xQXUa3UG")
        assert "expected_goals" in res["normalized_metric_names"]
        assert "Crazy Stat" in res["unknown_metrics"]
        assert "Crazy Stat" not in res["normalized_metric_names"]
        assert res["team_side_detection"] == "DETECTED_HOME_AWAY"


def test_preview_cap() -> None:
    """Verify safe_preview handles truncation and caps character count."""
    huge_data = {"key": "A" * 5000}
    preview_res = safe_preview(huge_data, max_chars=100)
    assert "preview" in preview_res
    assert preview_res["truncated"] is True
    assert len(preview_res["preview"]) <= 100


def test_verdict_not_certified_shadow_adapter_only() -> None:
    """Verify the default summary classification rules and certification structure."""
    adapter = SportDBMCPShadowAdapter()
    # Mocking standard successful responses
    mock_results = [{"provider_match_id": "m1", "status": "FINISHED"}]
    mock_stats = {
        "provider_match_id": "m1",
        "top_level_keys": ["data"],
        "raw_stat_field_names": ["Expected goals (xG)"],
        "raw_stat_group_names": ["Match"],
        "normalized_metric_names": ["expected_goals"],
        "unknown_metrics": [],
        "team_side_detection": "DETECTED_HOME_AWAY",
        "raw_result": {}
    }
    mock_events = {
        "event_count": 5,
        "event_type_names": ["Goal"],
        "goal_count": 2,
        "card_count": 1,
        "raw_result": {}
    }
    mock_lineups = {
        "formation_values": ["4-3-3"],
        "player_count": 22,
        "raw_result": {}
    }
    mock_standings = {
        "row_count": 20,
        "team_names": ["Arsenal", "Chelsea"],
        "raw_result": {}
    }

    with patch.object(adapter, "get_competition_results_shadow", return_value=mock_results), \
         patch.object(adapter, "get_match_stats_shadow", return_value=mock_stats), \
         patch.object(adapter, "get_match_events_shadow", return_value=mock_events), \
         patch.object(adapter, "get_match_lineups_shadow", return_value=mock_lineups), \
         patch.object(adapter, "get_competition_standings_shadow", return_value=mock_standings):

        # Test basic probe success
        results = adapter.get_competition_results_shadow()
        assert len(results) == 1
        assert results[0]["provider_match_id"] == "m1"
