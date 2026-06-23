import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from bet.enrichment.football_data_foundation.live_response_corpus_capture.runner import (
    run_live_response_corpus_capture,
)
from bet.enrichment.football_data_foundation.live_response_corpus_capture.contracts import (
    CaptureStatus,
)


def test_runner_mock_execution(tmp_path):
    # Mocking provider responses
    mock_sportdb_envelope = MagicMock()
    mock_sportdb_envelope.status = "FETCHED"
    mock_sportdb_envelope.provider = "sportdb"
    mock_sportdb_envelope.to_dict = lambda: {"status": "FETCHED", "provider": "sportdb", "raw_headers_stored": False, "secrets_stored": False, "selectable_for_production": False}
    mock_sportdb_envelope.validate = lambda: None

    mock_fdo_envelope = MagicMock()
    mock_fdo_envelope.status = "SKIPPED_CREDENTIALS_MISSING"
    mock_fdo_envelope.provider = "football-data-org"
    mock_fdo_envelope.to_dict = lambda: {"status": "SKIPPED_CREDENTIALS_MISSING", "provider": "football-data-org", "raw_headers_stored": False, "secrets_stored": False, "selectable_for_production": False}
    mock_fdo_envelope.validate = lambda: None

    mock_hl_envelope = MagicMock()
    mock_hl_envelope.status = "BLOCKED_PROVIDER_MAPPING_MISSING"
    mock_hl_envelope.provider = "highlightly"
    mock_hl_envelope.to_dict = lambda: {"status": "BLOCKED_PROVIDER_MAPPING_MISSING", "provider": "highlightly", "raw_headers_stored": False, "secrets_stored": False, "selectable_for_production": False}
    mock_hl_envelope.validate = lambda: None

    mock_af_envelope = MagicMock()
    mock_af_envelope.status = "SKIPPED_CREDENTIALS_MISSING"
    mock_af_envelope.provider = "api-football"
    mock_af_envelope.to_dict = lambda: {"status": "SKIPPED_CREDENTIALS_MISSING", "provider": "api-football", "raw_headers_stored": False, "secrets_stored": False, "selectable_for_production": False}
    mock_af_envelope.validate = lambda: None

    mock_espn_envelope = MagicMock()
    mock_espn_envelope.status = "BLOCKED_PROVIDER_MAPPING_MISSING"
    mock_espn_envelope.provider = "espn-baseline"
    mock_espn_envelope.to_dict = lambda: {"status": "BLOCKED_PROVIDER_MAPPING_MISSING", "provider": "espn-baseline", "raw_headers_stored": False, "secrets_stored": False, "selectable_for_production": False}
    mock_espn_envelope.validate = lambda: None

    mock_sportdb = MagicMock(return_value=mock_sportdb_envelope)
    mock_fdo = MagicMock(return_value=mock_fdo_envelope)
    mock_hl = MagicMock(return_value=mock_hl_envelope)
    mock_af = MagicMock(return_value=mock_af_envelope)
    mock_espn = MagicMock(return_value=mock_espn_envelope)

    with patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.discover_canary_fixtures") as mock_disc, \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.capture_sportdb", mock_sportdb), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.capture_football_data_org", mock_fdo), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.capture_highlightly", mock_hl), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.capture_api_football", mock_af), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.capture_espn_baseline", mock_espn):
        
        mock_disc.return_value = [{
            "fixture_slug": "worldcup2026-norway-senegal",
            "home_team": "Norway",
            "away_team": "Senegal",
            "competition": "FIFA World Cup 2026",
            "kickoff_at": "2026-06-23T18:00:00Z",
            "source_url": "https://www.fifa.com/en/match-centre/match/17/285023/289273/400021491",
            "match_id": "400021491",
            "is_seed": True,
        }]
        
        manifest = run_live_response_corpus_capture(tmp_path, max_fixtures=1)
        
        assert manifest.run_id is not None
        assert manifest.fixture_count == 1
        assert manifest.provider_count == 5
        assert manifest.fetched_count == 1
        assert manifest.skipped_count == 4
        assert manifest.failed_count == 0
        assert "manifest.json" in manifest.files_written
        assert "fixtures_discovered.json" in manifest.files_written
        assert "README.md" in manifest.files_written
        assert "sportdb/worldcup2026-norway-senegal.json" in manifest.files_written
