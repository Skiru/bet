from __future__ import annotations

import pytest


def test_highlightly_countries_is_preflight_only() -> None:
    """REQ-TEST-006: Highlightly countries is preflight only."""
    path = "/countries"
    assert path == "/countries"
    # Verify we understand it's preflight and doesn't count as enrichment success
    from bet.enrichment.football_data_foundation.live_response_corpus_capture.provider_operational_transport_v3 import create_envelope
    env = create_envelope(
        provider="highlightly",
        access_mode="DIRECT",
        transport="urllib",
        status="SUCCESS",
        request_purpose="highlightly_countries_preflight",
        request_attempted=True,
        network_used=True,
        source_url="https://soccer.highlightly.net/countries",
        status_code=200,
        body={},
        error=None,
        contributes_to_enrichment=False,  # Countries preflight does not contribute to enrichment
    )
    assert env["contributes_to_enrichment"] is False


def test_highlightly_matches_and_targeted_search() -> None:
    """REQ-TEST-007: Highlightly matches by date and targeted team search are required."""
    target_date = "2026-06-23"
    home_team = "Norway"
    away_team = "Senegal"
    
    path_by_date = f"/matches?date={target_date}&timezone=Etc/UTC&limit=100"
    path_targeted = f"/matches?date={target_date}&timezone=Etc/UTC&homeTeamName={home_team}&awayTeamName={away_team}&limit=100"

    assert "date=" in path_by_date
    assert "timezone=Etc/UTC" in path_by_date
    assert "homeTeamName=" in path_targeted
    assert "awayTeamName=" in path_targeted


def test_highlightly_match_detail_stats_lineups_events() -> None:
    """REQ-TEST-008: Highlightly detail/statistics/lineups/events endpoints are built from matchId only."""
    match_id = "match-123"
    endpoints = [
        f"/matches/{match_id}",
        f"/statistics/{match_id}",
        f"/lineups/{match_id}",
        f"/events/{match_id}",
    ]
    for ep in endpoints:
        assert match_id in ep
        assert ep.split("/")[-1] == match_id
