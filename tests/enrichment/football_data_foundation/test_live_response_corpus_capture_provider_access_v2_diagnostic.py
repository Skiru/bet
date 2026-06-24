"""
Unit tests for provider access V2 rescue diagnostic execution.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2 import (
    run_provider_access_rescue_diagnostic_v2,
    find_norway_senegal_match_id,
)


def test_find_norway_senegal_match_id():
    # Test typical structure of SportDB or Highlightly response body
    data = {
        "matches": [
            {
                "id": "match_12345",
                "home": {"name": "Norway"},
                "away": {"name": "Senegal"},
            }
        ]
    }
    match_id = find_norway_senegal_match_id(data)
    assert match_id == "match_12345"


def test_find_norway_senegal_match_id_nested():
    data = {
        "status": "success",
        "data": {
            "fixtures": [
                {
                    "fixture_id": 998877,
                    "homeTeam": "Norway",
                    "awayTeam": "Senegal",
                }
            ]
        }
    }
    match_id = find_norway_senegal_match_id(data)
    assert match_id == "998877"


@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.safe_http_get")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.safe_http_post")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.get_credential")
def test_diagnostic_v2_run_all_working(mock_get_credential, mock_safe_http_post, mock_safe_http_get, tmp_path):
    # Mock credentials present
    mock_get_credential.side_effect = lambda name: "mock-secret-key" if name in ("SPORTDB_API_KEY", "HIGHLIGHTLY_API_KEY") else None

    # Mock safe_http_get to succeed
    def fake_get(url, headers=None, params=None, timeout=10.0):
        if "sportdb" in url:
            return 200, {"status": "ok", "events": [{"idLive": "sdb_match_1", "home": "Norway", "away": "Senegal"}]}, None
        elif "soccer.highlightly.net" in url:
            return 200, {
                "matches": [
                    {
                        "id": "hl_match_1",
                        "home": "Norway",
                        "away": "Senegal"
                    }
                ]
            }, None
        return 404, None, "Not found"

    mock_safe_http_get.side_effect = fake_get

    # Run diagnostic
    result = run_provider_access_rescue_diagnostic_v2(tmp_path)

    assert result["verdict"] == "PASS"
    assert result["sportdb_verdict"] == "SPORTDB_WORKING_REST"
    assert result["highlightly_verdict"] == "HIGHLIGHTLY_WORKING_DIRECT"
    assert result["mapping_candidates_found"] == 2
    assert result["secret_leak_check"] == "PASS"

    # Verify output files written
    run_dir = Path(result["run_dir"])
    assert (run_dir / "diagnostic_summary.json").exists()
    assert (run_dir / "sportdb_access_probe_v2.json").exists()
    assert (run_dir / "highlightly_access_probe_v2.json").exists()
    assert (run_dir / "provider_access_bindings_candidate_v2.json").exists()

    summary = json.loads((run_dir / "diagnostic_summary.json").read_text(encoding="utf-8"))
    assert summary["selectable_for_production"] is False
    assert summary["headers_stored"] is False


@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.safe_http_post")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.safe_http_get")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic_v2.get_credential")
def test_diagnostic_v2_sportdb_rest_fails_mcp_works(mock_get_credential, mock_safe_http_get, mock_safe_http_post, tmp_path):
    # Mock credentials present
    mock_get_credential.side_effect = lambda name: "mock-secret-key" if name in ("SPORTDB_API_KEY", "HIGHLIGHTLY_API_KEY") else None

    # SportDB REST fails with 401
    # Highlightly direct succeeds
    def fake_get(url, headers=None, params=None, timeout=10.0):
        if "sportdb" in url:
            return 401, {"error": "Unauthorized"}, "HTTPError 401"
        elif "soccer.highlightly.net" in url:
            return 200, {"matches": [{"id": "hl_match_2", "home": "Norway", "away": "Senegal"}]}, None
        return 404, None, "Not found"

    mock_safe_http_get.side_effect = fake_get

    # MCP POST requests: initialize (returns 200), tools/list (returns 200)
    # REQ-TEST-007: SportDB MCP initialize uses initialize only before tools/list.
    call_order = []
    def fake_post(url, headers=None, json_data=None, timeout=10.0):
        if "mcp" in url:
            method = json_data.get("method") if json_data else None
            call_order.append(method)
            if method == "initialize":
                return 200, {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}}, None
            elif method == "tools/list":
                return 200, {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {
                        "tools": [
                            {"name": "get_match"},
                            {"name": "list_events"}
                        ]
                    }
                }, None
        return 404, None, "Not found"

    mock_safe_http_post.side_effect = fake_post

    # Run diagnostic
    result = run_provider_access_rescue_diagnostic_v2(tmp_path)

    assert result["verdict"] == "PASS"
    assert result["sportdb_verdict"] == "SPORTDB_WORKING_MCP"
    assert result["highlightly_verdict"] == "HIGHLIGHTLY_WORKING_DIRECT"
    assert call_order == ["initialize", "tools/list"]
