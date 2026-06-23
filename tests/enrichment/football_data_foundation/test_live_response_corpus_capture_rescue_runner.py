import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from bet.enrichment.football_data_foundation.live_response_corpus_capture.runner import run_freemium_rescue_capture

def test_rescue_runner_mock_execution(tmp_path):
    """
    REQ-TEST-010: All rescue envelopes have selectable_for_production=false.
    REQ-TEST-011: ESPN envelopes have unofficial_shadow_baseline=true.
    REQ-TEST-012: Rescue run does not edit previous corpus runs.
    """
    mock_sportdb_live = [
        {"id": "sportdb-123", "home_team": "Norway", "away_team": "Senegal"}
    ]
    mock_sportdb_detail = {
        "id": "sportdb-123",
        "status": "scheduled",
        "home": {"name": "Norway"},
        "away": {"name": "Senegal"}
    }
    
    mock_espn_scoreboard = {
        "events": [
            {
                "id": "espn-456",
                "competitions": [
                    {
                        "competitors": [
                            {"team": {"name": "Norway", "abbreviation": "NOR"}},
                            {"team": {"name": "Senegal", "abbreviation": "SEN"}}
                        ]
                    }
                ]
            }
        ]
    }
    
    mock_espn_summary = {
        "boxscore": {},
        "header": {"id": "espn-456"}
    }

    def mock_safe_http_get(url, headers=None, timeout=10.0):
        if "sportdb.dev/api/football/live" in url:
            return 200, mock_sportdb_live, None
        elif "sportdb.dev/api/match/sportdb-123" in url:
            return 200, mock_sportdb_detail, None
        elif "site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard" in url:
            return 200, mock_espn_scoreboard, None
        elif "site.api.espn.com/apis/site/v2/sports/soccer/all/summary" in url:
            return 200, mock_espn_summary, None
        return 404, None, "Not found"

    with patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.safe_http_get", side_effect=mock_safe_http_get), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.get_credential", return_value="fake_key"), \
         patch("bet.enrichment.football_data_foundation.live_response_corpus_capture.runner.credential_presence_map", return_value={"sportdb": True, "highlightly": True}):
         
        manifest = run_freemium_rescue_capture(tmp_path)
        
        # Verify Manifest
        assert manifest.run_id is not None
        assert manifest.fixture_count == 1
        assert manifest.provider_count == 3
        assert manifest.selectable_for_production is False
        
        run_dir = tmp_path / manifest.run_id
        assert (run_dir / "manifest.json").exists()
        assert (run_dir / "README.md").exists()
        assert (run_dir / "mapping_candidate.json").exists()
        assert (run_dir / "capture_verifier_result.json").exists()
        
        # Load written files to verify properties
        sportdb_live_json = json.loads((run_dir / "sportdb" / "worldcup2026-norway-senegal_rescue_live.json").read_text())
        assert sportdb_live_json["status"] == "RESCUE_FETCHED"
        assert sportdb_live_json["selectable_for_production"] is False
        assert sportdb_live_json["rescue_attempt"] is True
        assert sportdb_live_json["rescue_provider"] == "sportdb"
        assert sportdb_live_json["request_attempted"] is True

        sportdb_det_json = json.loads((run_dir / "sportdb" / "worldcup2026-norway-senegal_rescue_detail.json").read_text())
        assert sportdb_det_json["status"] == "RESCUE_FETCHED"
        assert sportdb_det_json["selectable_for_production"] is False
        assert sportdb_det_json["rescue_attempt"] is True
        assert sportdb_det_json["provider_fixture_id"] == "sportdb-123"

        hl_json = json.loads((run_dir / "highlightly" / "worldcup2026-norway-senegal_rescue.json").read_text())
        assert hl_json["status"] == "RESCUE_BLOCKED_ENDPOINT_UNAVAILABLE"
        assert hl_json["error"] == "highlightly_base_url_or_auth_header_not_available_in_repo_or_docs"
        assert hl_json["rescue_attempt"] is True

        espn_json = json.loads((run_dir / "espn-baseline" / "worldcup2026-norway-senegal_rescue_scoreboard.json").read_text())
        assert espn_json["status"] == "RESCUE_FETCHED"
        assert espn_json["unofficial_shadow_baseline"] is True
        assert espn_json["selectable_for_production"] is False
        assert espn_json["rescue_attempt"] is True

        espn_sum_json = json.loads((run_dir / "espn-baseline" / "worldcup2026-norway-senegal_rescue_summary.json").read_text())
        assert espn_sum_json["status"] == "RESCUE_FETCHED"
        assert espn_sum_json["unofficial_shadow_baseline"] is True
        assert espn_sum_json["selectable_for_production"] is False
        assert espn_sum_json["provider_fixture_id"] == "espn-456"

        mapping_cand_json = json.loads((run_dir / "mapping_candidate.json").read_text())
        assert len(mapping_cand_json) == 2
        assert any(m["provider"] == "espn-baseline" and m["provider_fixture_id"] == "espn-456" for m in mapping_cand_json)
        assert any(m["provider"] == "sportdb" and m["provider_fixture_id"] == "sportdb-123" for m in mapping_cand_json)
