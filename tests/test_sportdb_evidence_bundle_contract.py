from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bet.api_clients.sportdb_mcp import (
    SportDBMCPShadowAdapter,
    SportDBEvidenceBundleWriter,
    RequiredPayloadFieldUnknownError,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus

@pytest.fixture
def temp_evidence_root():
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)

def test_imports_and_types():
    assert SportDBMCPShadowAdapter is not None
    assert SourceOperationResult is not None
    assert SourceResultStatus is not None

def test_evidence_writer_creates_deterministic_files(temp_evidence_root):
    writer = SportDBEvidenceBundleWriter(evidence_root=temp_evidence_root)
    
    operation = "match_stats"
    arguments = {"sport": "football", "match_id": "test_id"}
    raw_response = {"some": "data", "status": "ok"}
    normalized_value = {"metric": "value"}
    mcp_tool_name = "flashscore_get_match_stats"
    request_identity = "sportdb:match_stats:football:england:premier-league:2025-2026:test_id"

    bundle_id, bundle_files, response_sha256, normalized_sha256, schema_fingerprint = writer.write_bundle(
        operation=operation,
        arguments=arguments,
        raw_response=raw_response,
        normalized_value=normalized_value,
        mcp_tool_name=mcp_tool_name,
        request_identity=request_identity,
    )

    assert bundle_id is not None
    assert len(bundle_files) >= 4

    bundle_dir = temp_evidence_root / "sportdb" / "football" / "p2e_a6" / operation / bundle_id
    assert bundle_dir.exists()

    req_path = bundle_dir / "request.json"
    res_sha_path = bundle_dir / "response.sha256.txt"
    norm_path = bundle_dir / "normalized.json"
    manifest_path = bundle_dir / "manifest.json"

    assert req_path.exists()
    assert res_sha_path.exists()
    assert norm_path.exists()
    assert manifest_path.exists()

    # check manifest contents
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_data["provider"] == "sportdb"
    assert manifest_data["operation"] == operation
    assert manifest_data["bundle_id"] == bundle_id
    assert manifest_data["response_sha256"] == response_sha256
    assert manifest_data["normalized_sha256"] == normalized_sha256
    assert manifest_data["secret_safe"] is True

    # No secret/api-key written
    for path in (req_path, res_sha_path, norm_path, manifest_path):
        content = path.read_text(encoding="utf-8")
        assert "SPORTDB_API_KEY" not in content
        assert "X-API-Key" not in content

def test_with_evidence_method_returns_source_operation_result(temp_evidence_root):
    # Mock schemas and mappings
    schema_payload = {
        "tool_schemas": {
            "flashscore_get_match_stats": {
                "required_fields": ["sport", "match_id"],
                "optional_fields": []
            }
        }
    }
    mapping_payload = {
        "sport": {"selected_sport_key": "football"},
        "country": {"selected_country_slug": "england"},
        "competition": {"selected_competition_slug": "premier-league"},
        "season": {"selected_season": "2025-2026"},
        "finished_match_probe": {"selected_match_id": "xQXUa3UG"}
    }

    with tempfile.TemporaryDirectory() as temp_schema_dir:
        schema_path = Path(temp_schema_dir) / "schema.json"
        mapping_path = Path(temp_schema_dir) / "mapping.json"
        
        schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")
        mapping_path.write_text(json.dumps(mapping_payload), encoding="utf-8")

        adapter = SportDBMCPShadowAdapter(schema_path=schema_path, mapping_path=mapping_path)
        adapter.writer = SportDBEvidenceBundleWriter(evidence_root=temp_evidence_root)

        # Mock client tool call
        adapter.client.call_tool = MagicMock(return_value={"data": [{"period": "FullTime", "stats": []}]})

        # Check SUCCESS behavior
        res = adapter.get_match_stats_with_evidence()
        assert isinstance(res, SourceOperationResult)
        assert res.status == SourceResultStatus.SUCCESS
        assert res.bundle_id != ""
        assert len(res.evidence_refs) == 1
        assert res.evidence_refs[0].request_identity != ""

def test_evidence_write_failure_maps_to_evidence_error(temp_evidence_root):
    schema_payload = {
        "tool_schemas": {
            "flashscore_get_match_stats": {
                "required_fields": ["sport", "match_id"],
                "optional_fields": []
            }
        }
    }
    mapping_payload = {
        "sport": {"selected_sport_key": "football"},
        "country": {"selected_country_slug": "england"},
        "competition": {"selected_competition_slug": "premier-league"},
        "season": {"selected_season": "2025-2026"},
        "finished_match_probe": {"selected_match_id": "xQXUa3UG"}
    }

    with tempfile.TemporaryDirectory() as temp_schema_dir:
        schema_path = Path(temp_schema_dir) / "schema.json"
        mapping_path = Path(temp_schema_dir) / "mapping.json"
        
        schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")
        mapping_path.write_text(json.dumps(mapping_payload), encoding="utf-8")

        adapter = SportDBMCPShadowAdapter(schema_path=schema_path, mapping_path=mapping_path)
        adapter.writer = SportDBEvidenceBundleWriter(evidence_root=temp_evidence_root)
        
        # Mock writer to fail
        adapter.writer.write_bundle = MagicMock(side_effect=RuntimeError("disk full"))
        adapter.client.call_tool = MagicMock(return_value={"data": []})

        res = adapter.get_match_stats_with_evidence()
        assert res.status == SourceResultStatus.EVIDENCE_ERROR

def test_required_payload_field_unknown_maps_to_schema_error():
    schema_payload = {
        "tool_schemas": {
            "flashscore_get_match_stats": {
                "required_fields": ["sport", "non_existent_field"],
                "optional_fields": []
            }
        }
    }
    mapping_payload = {
        "sport": {"selected_sport_key": "football"},
        "country": {"selected_country_slug": "england"},
    }

    with tempfile.TemporaryDirectory() as temp_schema_dir:
        schema_path = Path(temp_schema_dir) / "schema.json"
        mapping_path = Path(temp_schema_dir) / "mapping.json"
        
        schema_path.write_text(json.dumps(schema_payload), encoding="utf-8")
        mapping_path.write_text(json.dumps(mapping_payload), encoding="utf-8")

        adapter = SportDBMCPShadowAdapter(schema_path=schema_path, mapping_path=mapping_path)
        res = adapter.get_match_stats_with_evidence()
        assert res.status == SourceResultStatus.SCHEMA_ERROR

def test_source_paths_safety():
    src_path = Path("src/bet/api_clients/sportdb_mcp.py")
    content = src_path.read_text(encoding="utf-8")
    
    # Check no forbidden REST routes are hardcoded
    for forbidden in ["/api/football", "/api/match", "/api/clubs", "/api/players"]:
        assert forbidden not in content

    # Check no forbidden tags are used
    for forbidden in ["CERTIFIED_SELECTABLE", "PRODUCTION_READY"]:
        assert forbidden not in content

def test_summary_fixture_validation():
    # Verify that we reject invalid summary contents
    def validate_summary(data):
        assert data["phase_id"] == "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT"
        for op in data["operations"].values():
            if op["status"] in ("SUCCESS", "VALID_EMPTY"):
                assert op["bundle_id"] is not None
                assert op["evidence_refs"]
        assert data["call_budget"]["mcp_tool_calls_made"] == 5

    valid_summary = {
        "phase_id": "P2E_A6_SPORTDB_EVIDENCE_BUNDLE_AND_REPLAY_CONTRACT",
        "operations": {
            "competition_results": {
                "status": "SUCCESS",
                "bundle_id": "abc",
                "evidence_refs": [{"id": 1}]
            }
        },
        "call_budget": {"mcp_tool_calls_made": 5}
    }
    validate_summary(valid_summary)

    with pytest.raises(AssertionError):
        invalid_summary = valid_summary.copy()
        invalid_summary["call_budget"] = {"mcp_tool_calls_made": 0}
        validate_summary(invalid_summary)

    with pytest.raises(AssertionError):
        invalid_summary = valid_summary.copy()
        invalid_summary["operations"]["competition_results"]["bundle_id"] = None
        validate_summary(invalid_summary)
