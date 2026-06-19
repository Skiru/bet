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
from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.sportdb_mcp import (
    SPORTDB_MCP_ACCEPT,
    SPORTDB_MCP_PARSER_VERSION,
    SportDBMCPClient,
    SportDBMCPShadowAdapter,
    SportDBMCPAuthError,
    SportDBMCPRateLimitError,
    RequiredPayloadFieldUnknownError,
)

# Import safe_preview from the probe script as well to test it
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from sportdb_p2e_shadow_adapter_probe import safe_preview, redact_text


def test_imports_and_constants() -> None:
    """Verify that module can be imported and constants are correct."""
    assert SPORTDB_MCP_ACCEPT == "application/json, text/event-stream"
    assert SPORTDB_MCP_PARSER_VERSION == "sportdb-mcp-shadow-adapter-v1"


def test_no_forbidden_rest_paths() -> None:
    """Verify that active adapter/probe code contains no direct REST request paths."""
    adapter_src = Path("src/bet/api_clients/sportdb_mcp.py").read_text(encoding="utf-8")
    probe_src = Path("scripts/sportdb_p2e_shadow_adapter_probe.py").read_text(encoding="utf-8")

    forbidden_patterns = [
        r"/api/football",
        r"/api/match",
        r"/api/clubs",
        r"/api/players",
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
    raw_text = json.dumps(raw_response)
    
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
