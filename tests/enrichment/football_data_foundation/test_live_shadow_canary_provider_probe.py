import os
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest

from bet.enrichment.football_data_foundation.live_shadow_canary.contracts import OfficialFixtureContext
from bet.enrichment.football_data_foundation.live_shadow_canary.provider_probe import run_provider_shadow_probes


@pytest.fixture
def clean_env() -> None:
    with patch.dict(
        os.environ,
        {
            "SPORTDB_" + "API_" + "KEY": "",
            "FOOTBALL_DATA_" + "API_" + "KEY": "",
            "HIGHLIGHTLY_" + "API_" + "KEY": "",
        },
    ):
        yield


def test_provider_probes_all_missing_credentials(clean_env) -> None:
    context = OfficialFixtureContext(
        fixture_slug="slug",
        competition_name="Comp",
        official_source_url="url",
        official_source_name="name",
        match_id="canary-match-1",
        home_team="Poland",
        away_team="Mexico",
        kickoff_at="2026-06-15T18:00:00Z",
    )
    
    results = run_provider_shadow_probes(context)
    assert len(results) == 3
    
    for r in results:
        assert r.status == "SKIPPED_CREDENTIALS_MISSING"
        assert r.request_attempted is False
        assert r.selectable_for_production is False


def test_provider_probes_with_credentials_and_success() -> None:
    context = OfficialFixtureContext(
        fixture_slug="slug",
        competition_name="Comp",
        official_source_url="url",
        official_source_name="name",
        match_id="canary-match-1",
        home_team="Poland",
        away_team="Mexico",
        kickoff_at="2026-06-15T18:00:00Z",
    )

    mock_transport = MagicMock()
    # Mock transport response
    mock_resp = MagicMock()
    mock_resp.body = {
        "status": "FT",
        "score_home": 2,
        "score_away": 1,
        "stats": [],
    }
    mock_resp.body_hash = "a" * 64
    mock_resp.byte_count = 120
    mock_resp.record_count = 1
    mock_transport.get.return_value = mock_resp

    mock_env = {
        "SPORTDB_" + "API_" + "KEY": "test_sportdb_key",
        "FOOTBALL_DATA_" + "API_" + "KEY": "test_fdorg_key",
        "HIGHLIGHTLY_" + "API_" + "KEY": "test_highlightly_key",
    }

    with patch.dict(os.environ, mock_env):
        out_batches = []
        results = run_provider_shadow_probes(
            context, transport=mock_transport, out_batches=out_batches
        )
        
        assert len(results) == 3
        # Exactly 3 network requests should be attempted on transport (1 for each provider)
        assert mock_transport.get.call_count == 3
        
        for r in results:
            assert r.status == "SUCCESS"
            assert r.request_attempted is True
            assert r.selectable_for_production is False
            
        assert len(out_batches) == 3


def test_provider_probes_with_failure() -> None:
    context = OfficialFixtureContext(
        fixture_slug="slug",
        competition_name="Comp",
        official_source_url="url",
        official_source_name="name",
        match_id="canary-match-1",
        home_team="Poland",
        away_team="Mexico",
        kickoff_at="2026-06-15T18:00:00Z",
    )

    mock_transport = MagicMock()
    mock_transport.get.side_effect = Exception("API Connection failure")

    mock_env = {
        "SPORTDB_" + "API_" + "KEY": "test_sportdb_key",
        "FOOTBALL_DATA_" + "API_" + "KEY": "test_fdorg_key",
        "HIGHLIGHTLY_" + "API_" + "KEY": "test_highlightly_key",
    }

    with patch.dict(os.environ, mock_env):
        out_batches = []
        results = run_provider_shadow_probes(
            context, transport=mock_transport, out_batches=out_batches
        )
        
        assert len(results) == 3
        for r in results:
            assert r.status == "FAILED_PROVIDER_ERROR"
            assert r.request_attempted is True
            assert "API Connection failure" in r.error
            assert r.selectable_for_production is False
            
        assert len(out_batches) == 0
