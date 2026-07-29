import json
import pytest
from pathlib import Path
from bet.enrichment.football_data_foundation.live_response_corpus_capture.verifier import (
    verify_run_directory,
)


def write_mock_corpus(dir_path: Path, manifest_data: dict, envelopes: dict) -> None:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    for relative_path, env_data in envelopes.items():
        p = dir_path / relative_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(env_data, indent=2), encoding="utf-8")


def test_verifier_fails_on_credential_present_only_blocked(tmp_path):
    """
    REQ-TEST-003 credential-present + only BLOCKED_PROVIDER_MAPPING_MISSING fails verifier.
    """
    manifest = {
        "run_id": "run-123",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 5,
        "fetched_count": 0,
        "skipped_count": 5,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": ["sportdb/worldcup2026-norway-senegal.json", "manifest.json"],
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "BLOCKED_PROVIDER_MAPPING_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "fixture_detail",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("BLOCKED_PROVIDER_MAPPING_MISSING" in req for req in res["failed_requirements"])


def test_verifier_passes_on_discovery_no_match_found(tmp_path):
    """
    REQ-TEST-004 credential-present + DISCOVERY_NO_MATCH_FOUND passes verifier.
    """
    manifest = {
        "run_id": "run-123",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 5,
        "fetched_count": 0,
        "skipped_count": 5,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": [
            "sportdb/worldcup2026-norway-senegal_discovery.json",
            "sportdb/worldcup2026-norway-senegal.json",
            "manifest.json"
        ],
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal_discovery.json": {
            "provider": "sportdb",
            "status": "DISCOVERY_NO_MATCH_FOUND",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "https://api.sportdb.dev/mcp/",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "mcp_live_or_match_search_discovery",
            "body_sha256": "0" * 64,
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        },
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "BLOCKED_PROVIDER_MAPPING_MISSING",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "fixture_detail",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "PASS"


def test_discovery_fetched_requires_source_url_and_body_sha256(tmp_path):
    """
    REQ-TEST-005 DISCOVERY_FETCHED requires source_url and body_sha256.
    """
    # Test failure when source_url is missing
    manifest = {
        "run_id": "run-123",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 5,
        "fetched_count": 1,
        "skipped_count": 4,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": ["sportdb/worldcup2026-norway-senegal_discovery.json", "manifest.json"],
    }

    envelopes = {
        "sportdb/worldcup2026-norway-senegal_discovery.json": {
            "provider": "sportdb",
            "status": "DISCOVERY_FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": None,  # Missing!
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "mcp_live_or_match_search_discovery",
            "body_sha256": "abc",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }

    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("source_url" in req for req in res["failed_requirements"])


def test_no_secrets_or_headers_in_reports(tmp_path):
    """
    REQ-TEST-008 no secrets or headers in reports.
    """
    manifest = {
        "run_id": "run-123",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 5,
        "fetched_count": 1,
        "skipped_count": 4,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": ["sportdb/worldcup2026-norway-senegal.json", "manifest.json"],
    }

    # Test failure when secrets_stored=True
    envelopes = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "http://example.com",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "fixture_detail",
            "raw_headers_stored": False,
            "secrets_stored": True,  # Blocked!
            "selectable_for_production": False,
        }
    }
    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"

    # Test failure when raw_headers_stored=True
    envelopes2 = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "http://example.com",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "fixture_detail",
            "raw_headers_stored": True,  # Blocked!
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }
    write_mock_corpus(tmp_path, manifest, envelopes2)
    res2 = verify_run_directory(tmp_path)
    assert res2["verdict"] == "FAIL"


def test_selectable_for_production_remains_false(tmp_path):
    """
    REQ-TEST-012 provider discovery output remains selectable_for_production=false.
    """
    manifest = {
        "run_id": "run-123",
        "run_started_at_utc": "2026-06-23T12:00:00Z",
        "target_date_utc": "2026-06-23",
        "fixture_count": 1,
        "provider_count": 5,
        "fetched_count": 1,
        "skipped_count": 4,
        "failed_count": 0,
        "credentials_present": {"sportdb": True},
        "files_written": ["sportdb/worldcup2026-norway-senegal.json", "manifest.json"],
    }

    # Test failure when selectable_for_production=True
    envelopes = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "http://example.com",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "request_purpose": "fixture_detail",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": True,  # Blocked!
        }
    }
    write_mock_corpus(tmp_path, manifest, envelopes)
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
