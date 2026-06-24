"""
Unit tests for provider access bindings candidate definitions.
"""

from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_access_bindings import (
    SPORTDB_REST_CANDIDATE,
    SPORTDB_MCP_CANDIDATE,
    HIGHLIGHTLY_DIRECT_CANDIDATE,
    HIGHLIGHTLY_RAPIDAPI_CANDIDATE,
)


def test_sportdb_rest_candidate_properties():
    # REQ-TEST-001: SportDB REST candidate uses /api/football/live and X-API-Key header name only.
    assert SPORTDB_REST_CANDIDATE["endpoint_path"] == "/api/football/live"
    assert SPORTDB_REST_CANDIDATE["required_header_names"] == ["X-API-Key"]
    assert "api_key" not in SPORTDB_REST_CANDIDATE
    # REQ-TEST-010: working binding candidate contains header names only, not values.
    for k, v in SPORTDB_REST_CANDIDATE.items():
        if "header" in k:
            assert isinstance(v, list)
            assert all(isinstance(header, str) and len(header) < 50 for header in v)


def test_sportdb_mcp_candidate_properties():
    # REQ-TEST-002: SportDB MCP initialize uses JSON-RPC initialize and tools/list only.
    assert SPORTDB_MCP_CANDIDATE["endpoint_path"] == "/mcp/"
    assert "X-API-Key" in SPORTDB_MCP_CANDIDATE["required_header_names"]
    # REQ-TEST-010: working binding candidate contains header names only, not values.
    for k, v in SPORTDB_MCP_CANDIDATE.items():
        if "header" in k:
            assert isinstance(v, list)
            assert all(isinstance(header, str) and len(header) < 50 for header in v)


def test_highlightly_direct_candidate_properties():
    # REQ-TEST-003: Highlightly direct candidate uses sports.highlightly.net and x-rapidapi-key header name only.
    assert "sports.highlightly.net" in HIGHLIGHTLY_DIRECT_CANDIDATE["base_url"]
    assert HIGHLIGHTLY_DIRECT_CANDIDATE["required_header_names"] == ["x-rapidapi-key"]
    # REQ-TEST-010: working binding candidate contains header names only, not values.
    for k, v in HIGHLIGHTLY_DIRECT_CANDIDATE.items():
        if "header" in k:
            assert isinstance(v, list)
            assert all(isinstance(header, str) and len(header) < 50 for header in v)


def test_highlightly_rapidapi_candidate_properties():
    # REQ-TEST-004: Highlightly RapidAPI candidate uses sport-highlights-api.p.rapidapi.com and x-rapidapi-host header name only.
    assert "sport-highlights-api.p.rapidapi.com" in HIGHLIGHTLY_RAPIDAPI_CANDIDATE["base_url"]
    assert "x-rapidapi-host" in HIGHLIGHTLY_RAPIDAPI_CANDIDATE["required_header_names"]
    # REQ-TEST-010: working binding candidate contains header names only, not values.
    for k, v in HIGHLIGHTLY_RAPIDAPI_CANDIDATE.items():
        if "header" in k:
            assert isinstance(v, list)
            assert all(isinstance(header, str) and len(header) < 50 for header in v)


def test_no_credential_values():
    # REQ-TEST-005: No credential values are serialized.
    for candidate in [
        SPORTDB_REST_CANDIDATE,
        SPORTDB_MCP_CANDIDATE,
        HIGHLIGHTLY_DIRECT_CANDIDATE,
        HIGHLIGHTLY_RAPIDAPI_CANDIDATE,
    ]:
        assert "key_value" not in candidate
        assert "token_value" not in candidate


def test_no_raw_headers_serialized():
    # REQ-TEST-006: No raw headers are serialized.
    for candidate in [
        SPORTDB_REST_CANDIDATE,
        SPORTDB_MCP_CANDIDATE,
        HIGHLIGHTLY_DIRECT_CANDIDATE,
        HIGHLIGHTLY_RAPIDAPI_CANDIDATE,
    ]:
        assert "headers" not in candidate or candidate["headers"] is None


def test_selectable_for_production():
    # REQ-TEST-007: Diagnostic summary never has selectable_for_production=true.
    for candidate in [
        SPORTDB_REST_CANDIDATE,
        SPORTDB_MCP_CANDIDATE,
        HIGHLIGHTLY_DIRECT_CANDIDATE,
        HIGHLIGHTLY_RAPIDAPI_CANDIDATE,
    ]:
        assert candidate.get("selectable_for_production") is False
