import pytest
import json
from pathlib import Path
from bet.enrichment.football_data_foundation.live_response_corpus_capture.verifier import verify_run_directory

def write_mock_corpus(dir_path: Path, manifest_data: dict, envelopes: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    for relative_path, env_data in envelopes.items():
        p = dir_path / relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(env_data, indent=2), encoding="utf-8")


def test_rescue_verifier_fails_if_sportdb_credential_present_and_no_sportdb_attempt(tmp_path):
    """
    REQ-TEST-004 / REQ-VERIFIER-002: Rescue verifier fails if SportDB credential present and no SportDB request attempted.
    """
    manifest = {
        "run_id": "run-rescue-1",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 3,
        "fetched_count": 1,
        "skipped_count": 2,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": [
            "sportdb/worldcup2026-norway-senegal_rescue_live.json",
            "highlightly/worldcup2026-norway-senegal_rescue.json",
            "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json",
            "manifest.json"
        ]
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal_rescue_live.json": {
            "provider": "sportdb",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "sportdb_rest_football_live_probe",
            "request_attempted": False,  # Missing attempt even though manifest says sportdb is True!
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "sportdb",
            "selectable_for_production": False,
        },
        "highlightly/worldcup2026-norway-senegal_rescue.json": {
            "provider": "highlightly",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "highlightly_rescue_probe",
            "request_attempted": False,
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "highlightly",
            "selectable_for_production": False,
        },
        "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json": {
            "provider": "espn-baseline",
            "status": "RESCUE_FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "espn_fifa_world_scoreboard_rescue",
            "request_attempted": True,
            "network_used": True,
            "body_sha256": "fake_sha",
            "rescue_attempt": True,
            "rescue_provider": "espn-baseline",
            "selectable_for_production": False,
            "unofficial_shadow_baseline": True,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("SportDB credential is present but no SportDB request was attempted" in err for err in res["failed_requirements"])


def test_rescue_verifier_fails_if_espn_not_attempted(tmp_path):
    """
    REQ-TEST-005 / REQ-VERIFIER-003: Rescue verifier fails if ESPN request not attempted.
    """
    manifest = {
        "run_id": "run-rescue-2",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 3,
        "fetched_count": 0,
        "skipped_count": 3,
        "failed_count": 0,
        "credentials_present": {"sportdb": False},
        "files_written": [
            "sportdb/worldcup2026-norway-senegal_rescue_live.json",
            "highlightly/worldcup2026-norway-senegal_rescue.json",
            "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json",
            "manifest.json"
        ]
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal_rescue_live.json": {
            "provider": "sportdb",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "sportdb_rest_football_live_probe",
            "request_attempted": False,
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "sportdb",
            "selectable_for_production": False,
        },
        "highlightly/worldcup2026-norway-senegal_rescue.json": {
            "provider": "highlightly",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "highlightly_rescue_probe",
            "request_attempted": False,
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "highlightly",
            "selectable_for_production": False,
        },
        "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json": {
            "provider": "espn-baseline",
            "status": "RESCUE_FAILED_HTTP",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "espn_fifa_world_scoreboard_rescue",
            "request_attempted": False,  # Missing attempt!
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "espn-baseline",
            "selectable_for_production": False,
            "unofficial_shadow_baseline": True,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("ESPN request was not attempted" in err for err in res["failed_requirements"])


def test_rescue_fetched_requires_source_url_and_body_sha256(tmp_path):
    """
    REQ-TEST-006 / REQ-VERIFIER-005: RESCUE_FETCHED and RESCUE_NO_MATCH_FOUND require source_url and body_sha256.
    """
    manifest = {
        "run_id": "run-rescue-3",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 3,
        "fetched_count": 1,
        "skipped_count": 2,
        "failed_count": 0,
        "credentials_present": {"sportdb": False},
        "files_written": [
            "sportdb/worldcup2026-norway-senegal_rescue_live.json",
            "highlightly/worldcup2026-norway-senegal_rescue.json",
            "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json",
            "manifest.json"
        ]
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal_rescue_live.json": {
            "provider": "sportdb",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "sportdb_rest_football_live_probe",
            "request_attempted": False,
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "sportdb",
            "selectable_for_production": False,
        },
        "highlightly/worldcup2026-norway-senegal_rescue.json": {
            "provider": "highlightly",
            "status": "SKIPPED_CREDENTIALS_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "highlightly_rescue_probe",
            "request_attempted": False,
            "network_used": False,
            "rescue_attempt": True,
            "rescue_provider": "highlightly",
            "selectable_for_production": False,
        },
        "espn-baseline/worldcup2026-norway-senegal_rescue_scoreboard.json": {
            "provider": "espn-baseline",
            "status": "RESCUE_FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,  # Missing!
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "espn_fifa_world_scoreboard_rescue",
            "request_attempted": True,
            "network_used": True,
            "body_sha256": "fake_sha",
            "rescue_attempt": True,
            "rescue_provider": "espn-baseline",
            "selectable_for_production": False,
            "unofficial_shadow_baseline": True,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("lacks source_url" in err for err in res["failed_requirements"])
