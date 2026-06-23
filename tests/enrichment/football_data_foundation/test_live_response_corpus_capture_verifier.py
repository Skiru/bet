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


def test_verifier_passes_valid_corpus(tmp_path):
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
    
    envelopes = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "http://example.com",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "status_code": 200,
            "body": {"foo": "bar", "api_key": "[REDACTED_SECRET]"},
            "body_sha256": "abc",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }
    
    write_mock_corpus(tmp_path, manifest, envelopes)
    
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "PASS"
    assert not res["failed_requirements"]
    assert res["secret_leak_check"] == "pass"


def test_verifier_fails_on_secret_leak(tmp_path):
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
    
    envelopes = {
        "sportdb/worldcup2026-norway-senegal.json": {
            "provider": "sportdb",
            "status": "FETCHED",
            "fixture_slug": "worldcup2026-norway-senegal",
            "source_url": "http://example.com",
            "captured_at_utc": "2026-06-23T12:00:00Z",
            "status_code": 200,
            "body": {"foo": "bar", "api_key": "raw_sensitive_key_123"},
            "body_sha256": "abc",
            "raw_headers_stored": False,
            "secrets_stored": False,
            "selectable_for_production": False,
        }
    }
    
    write_mock_corpus(tmp_path, manifest, envelopes)
    
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("api_key" in req for req in res["failed_requirements"])
    assert res["secret_leak_check"] == "fail"


def test_verifier_fails_on_missing_manifest(tmp_path):
    res = verify_run_directory(tmp_path)
    assert res["verdict"] == "FAIL"
    assert any("manifest.json is missing" in req for req in res["failed_requirements"])
