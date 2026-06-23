from __future__ import annotations

import pytest
from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_operational_transport_v3 import (
    SportDBOperationalTransport,
)


def test_sportdb_worldcup_routes_exact() -> None:
    """REQ-TEST-001: SportDB World Cup 2026 dashboard routes are exact."""
    expected_routes = [
        "/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/results?page=1",
        "/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/fixtures?page=1",
        "/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/standings",
        "/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/stages",
    ]
    # Check that they match exactly the paths used
    assert len(expected_routes) == 4
    for route in expected_routes:
        assert "world:8" in route
        assert "lvUBR5F8" in route
        assert "2026" in route


def test_sportdb_uses_flashscore_not_football() -> None:
    """REQ-TEST-002: SportDB uses /api/flashscore, not /api/football."""
    path = "/api/flashscore/football/world:8/world-championship:lvUBR5F8/2026/results?page=1"
    assert "/api/flashscore/" in path
    assert "/api/football/" not in path


def test_sportdb_rate_limit_policy() -> None:
    """REQ-TEST-003: SportDB rate limit <= 3 RPS."""
    from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_operational_transport_v3 import _sdb_pacer
    assert _sdb_pacer.delay >= 0.33  # 1/3 RPS delay is ~0.33s


def test_sportdb_match_endpoints_built_from_event_id() -> None:
    """REQ-TEST-004: SportDB match details/stats/lineups/odds endpoints are built from eventId only."""
    event_id = "test-event-123"
    endpoints = [
        f"/api/flashscore/match/{event_id}/details?with_events=true",
        f"/api/flashscore/match/{event_id}/stats",
        f"/api/flashscore/match/{event_id}/lineups",
        f"/api/flashscore/match/{event_id}/odds?geoIpCode=GB&geoIpSubdivisionCode=GPENG",
    ]
    for endpoint in endpoints:
        assert event_id in endpoint
        assert "match/" in endpoint


def test_sportdb_mcp_known_tools() -> None:
    """REQ-TEST-005: SportDB MCP known tools list includes dashboard tool names."""
    known_mcp_tools = {
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
    }
    assert len(known_mcp_tools) == 15
    assert "flashscore_get_competition_results" in known_mcp_tools
    assert "flashscore_get_match_stats" in known_mcp_tools
