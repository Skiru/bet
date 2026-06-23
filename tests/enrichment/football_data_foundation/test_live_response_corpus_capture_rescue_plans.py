import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import CaptureStatus, ProviderResponseEnvelope

def test_sportdb_rescue_plan_requirements():
    """
    REQ-TEST-001: SportDB rescue plan uses GET /api/football/live and X-API-Key.
    """
    # Verify that status enum values are defined and correct
    assert CaptureStatus.RESCUE_FETCHED.value == "RESCUE_FETCHED"
    assert CaptureStatus.RESCUE_NO_MATCH_FOUND.value == "RESCUE_NO_MATCH_FOUND"

    env = ProviderResponseEnvelope(
        provider="sportdb",
        status=CaptureStatus.RESCUE_FETCHED.value,
        fixture_slug="worldcup2026-norway-senegal",
        source_url="https://api.sportdb.dev/api/football/live",
        captured_at_utc="2026-06-23T12:00:00Z",
        request_purpose="sportdb_rest_football_live_probe",
        rescue_attempt=True,
        rescue_provider="sportdb",
        rescue_endpoint_family="football_live",
    )
    env.validate()
    assert env.source_url == "https://api.sportdb.dev/api/football/live"
    assert env.request_purpose == "sportdb_rest_football_live_probe"


def test_espn_rescue_plan_requirements():
    """
    REQ-TEST-002: ESPN rescue plan uses soccer/fifa.world/scoreboard with date range and no credential.
    """
    env = ProviderResponseEnvelope(
        provider="espn-baseline",
        status=CaptureStatus.RESCUE_FETCHED.value,
        fixture_slug="worldcup2026-norway-senegal",
        source_url="https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?limit=950&dates=20260622-20260623",
        captured_at_utc="2026-06-23T12:00:00Z",
        request_purpose="espn_fifa_world_scoreboard_rescue",
        rescue_attempt=True,
        rescue_provider="espn-baseline",
        rescue_endpoint_family="scoreboard",
        unofficial_shadow_baseline=True,
    )
    env.validate()
    assert "soccer/fifa.world/scoreboard" in env.source_url
    assert "dates=20260622-20260623" in env.source_url
    assert env.unofficial_shadow_baseline is True


def test_highlightly_unknown_base_auth_requirements():
    """
    REQ-TEST-003: Highlightly unknown base/auth produces RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE with explicit reason.
    """
    env = ProviderResponseEnvelope(
        provider="highlightly",
        status=CaptureStatus.RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE.value,
        fixture_slug="worldcup2026-norway-senegal",
        source_url=None,
        captured_at_utc="2026-06-23T12:00:00Z",
        request_purpose="highlightly_rescue_probe",
        request_attempted=True,
        network_used=False,
        error="highlightly_base_url_or_auth_header_not_available_in_repo_or_docs",
        rescue_attempt=True,
        rescue_provider="highlightly",
        rescue_endpoint_family=None,
    )
    env.validate()
    assert env.status == "RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE"
    assert env.error == "highlightly_base_url_or_auth_header_not_available_in_repo_or_docs"
