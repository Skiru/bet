"""
Unit tests for provider access rescue diagnostic execution.
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic import (
    run_provider_access_rescue_diagnostic,
    find_highlightly_match_id,
)


def test_find_highlightly_match_id():
    # Test typical structure of Highlightly response body
    data = {
        "matches": [
            {
                "id": "match_999888",
                "home": {"name": "Norway National Team"},
                "away": {"name": "Senegal"},
            }
        ]
    }
    match_id = find_highlightly_match_id(data)
    assert match_id == "match_999888"


def test_find_highlightly_match_id_nested():
    data = {
        "status": "success",
        "data": {
            "fixtures": [
                {
                    "fixture_id": 12345,
                    "homeTeam": "Norway",
                    "awayTeam": "Senegal",
                }
            ]
        }
    }
    match_id = find_highlightly_match_id(data)
    assert match_id == "12345"


@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.safe_http_get")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.get_credential")
def test_diagnostic_run_all_working(mock_get_credential, mock_safe_http_get, tmp_path):
    # Mock credentials present
    mock_get_credential.side_effect = lambda name: "mock-secret-key" if name in ("SPORTDB_API_KEY", "HIGHLIGHTLY_API_KEY") else None

    # Mock safe_http_get to succeed for both REST endpoints
    def fake_get(url, headers=None, params=None, timeout=10.0):
        if "sportdb" in url:
            return 200, {"status": "ok", "events": []}, None
        elif "highlightly" in url:
            return 200, {
                "matches": [
                    {
                        "id": "match-987",
                        "home": "Norway",
                        "away": "Senegal"
                    }
                ]
            }, None
        return 404, None, "Not found"

    mock_safe_http_get.side_effect = fake_get

    # Run diagnostic
    result = run_provider_access_rescue_diagnostic(tmp_path)

    assert result["verdict"] == "PASS"
    assert result["sportdb_verdict"] == "SPORTDB_WORKING_REST"
    assert result["highlightly_verdict"] == "HIGHLIGHTLY_WORKING_DIRECT"
    assert result["mapping_candidates_found"] == 1
    assert result["secret_leak_check"] == "PASS"

    # Verify output files written
    run_dir = Path(result["run_dir"])
    assert (run_dir / "diagnostic_summary.json").exists()
    assert (run_dir / "sportdb_access_probe.json").exists()
    assert (run_dir / "highlightly_access_probe.json").exists()
    assert (run_dir / "provider_access_bindings_candidate.json").exists()

    summary = json.loads((run_dir / "diagnostic_summary.json").read_text(encoding="utf-8"))
    assert summary["selectable_for_production"] is False
    assert summary["headers_stored"] is False


@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.safe_http_post")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.safe_http_get")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.get_credential")
def test_diagnostic_sportdb_rest_fails_mcp_works(mock_get_credential, mock_safe_http_get, mock_safe_http_post, tmp_path):
    # Mock credentials present
    mock_get_credential.side_effect = lambda name: "mock-secret-key" if name in ("SPORTDB_API_KEY", "HIGHLIGHTLY_API_KEY") else None

    # SportDB REST fails with 401
    # Highlightly direct succeeds
    def fake_get(url, headers=None, params=None, timeout=10.0):
        if "sportdb" in url:
            return 401, {"error": "Unauthorized"}, "HTTPError 401"
        elif "highlightly" in url:
            return 200, {"matches": [{"id": "99", "home": "Norway", "away": "Senegal"}]}, None
        return 404, None, "Not found"

    mock_safe_http_get.side_effect = fake_get

    # MCP POST requests: initialize (returns 200), tools/list (returns 200)
    def fake_post(url, headers=None, json_data=None, timeout=10.0):
        if "mcp" in url:
            method = json_data.get("method") if json_data else None
            if method == "initialize":
                return 200, {"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}}, None
            elif method == "tools/list":
                return 200, {
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {
                        "tools": [
                            {"name": "get_match_by_id"},
                            {"name": "list_live_events"}
                        ]
                    }
                }, None
        return 404, None, "Not found"

    mock_safe_http_post.side_effect = fake_post

    # Run diagnostic
    result = run_provider_access_rescue_diagnostic(tmp_path)

    assert result["verdict"] == "PASS"
    assert result["sportdb_verdict"] == "SPORTDB_WORKING_MCP"
    assert result["highlightly_verdict"] == "HIGHLIGHTLY_WORKING_DIRECT"
    assert result["mapping_candidates_found"] == 1


@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.safe_http_get")
@patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.get_credential")
def test_diagnostic_highlightly_direct_fails_rapidapi_works(mock_get_credential, mock_safe_http_get, tmp_path):
    mock_get_credential.side_effect = lambda name: "mock-secret-key" if name in ("SPORTDB_API_KEY", "HIGHLIGHTLY_API_KEY") else None

    # SportDB REST fails, but don't care here
    # Highlightly direct fails with 403, RapidAPI succeeds
    def fake_get(url, headers=None, params=None, timeout=10.0):
        if "sportdb" in url:
            return 404, None, "Not found"
        elif "sports.highlightly.net" in url:
            return 403, {"error": "Invalid API Key"}, "HTTPError 403"
        elif "sport-highlights-api.p.rapidapi.com" in url:
            return 200, {"matches": [{"id": "100", "home": "Norway", "away": "Senegal"}]}, None
        return 404, None, "Not found"

    mock_safe_http_get.side_effect = fake_get

    # Run diagnostic with MCP mock failing to isolate to REST/RapidAPI checks
    with patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_diagnostic.safe_http_post") as mock_post:
        mock_post.return_value = (404, None, "Failed")
        result = run_provider_access_rescue_diagnostic(tmp_path)

    assert result["highlightly_verdict"] == "HIGHLIGHTLY_WORKING_RAPIDAPI"
    assert result["mapping_candidates_found"] == 1


def test_guardrails_requests_and_canary():
    # REQ-TEST-009 requests dependency is absent.
    # REQ-TEST-008 canary-fixture-one is absent.
    src_file = Path(__file__).parent.parent.parent / "src/bet/enrichment/football_data_foundation/live_response_corpus_capture/provider_access_diagnostic.py"
    if src_file.exists():
        content = src_file.read_text(encoding="utf-8")
        assert "requests" not in content
        assert "canary" not in content
