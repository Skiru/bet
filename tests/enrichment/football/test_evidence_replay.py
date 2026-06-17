# ruff: noqa: E501
import pytest
import tempfile
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from bet.enrichment.football.contracts import (
    BatchIdsCapability,
    AcquisitionMode,
)
from bet.enrichment.football.replay import EvidenceReplayAcquirer
from bet.integration.evidence import (
    EvidenceRef,
    write_bundle_manifest,
    persist_response_evidence,
    get_evidence_root,
)
from bet.integration.telemetry_wrapper import TransportResult

@pytest.fixture
def temp_evidence_root():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

def test_replay_preserves_observed_at_and_zero_http(temp_evidence_root):
    # Set evidence root
    import os
    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(temp_evidence_root)
    
    try:
        # Create some fake response evidence
        response_disc = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"response": [
                {
                    "fixture": {
                        "id": 123,
                        "status": {"short": "FT"},
                        "date": "2023-01-01T12:00:00+00:00"
                    },
                    "league": {"id": 39, "name": "Premier League", "season": 2023},
                    "teams": {
                        "home": {"id": 10, "name": "Home Team"},
                        "away": {"id": 20, "name": "Away Team"}
                    },
                    "goals": {"home": 2, "away": 1},
                    "score": {"penalty": {"home": None, "away": None}}
                }
            ]}).encode("utf-8")
        )
        
        ref_disc = persist_response_evidence(
            operation="history_discovery",
            url="https://v3.football.api-sports.io/fixtures",
            params={"league": "39", "season": "2023"},
            response=response_disc,
            source_event_id="123",
        )
        
        # Manifest with captured_at
        # Force captured_at to a specific fixed time
        from dataclasses import replace
        ref_disc = replace(ref_disc, captured_at="2023-01-01T15:30:00.000000Z")
        
        bundle_id, manifest_path = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="TEAM_MATCH_FACTS",
            canonical_fixture_id=100,
            parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:123"],
            evidence_refs=[ref_disc],
        )
        
        # Replay should parse it without any HTTP client
        acquirer = EvidenceReplayAcquirer(bundle_ids=(bundle_id,))
        res = acquirer.acquire(
            competition_provider_id="39",
            season=2023,
            from_date=None,
            to_date=None,
            max_fixtures=10,
            max_fallback_stats_calls=5,
            attempt_budget=None,
            ids_capability=BatchIdsCapability.UNKNOWN,
        )
        
        assert len(res.fixtures) == 1
        fix = res.fixtures[0]
        assert fix.fixture.provider_fixture_id == "123"
        assert fix.fixture.home_score == 2
        assert fix.fixture.away_score == 1
        
        # Replay preserves the maximum captured_at of evidence as observed_at
        assert fix.observed_at == datetime(2023, 1, 1, 15, 30, tzinfo=timezone.utc)
        assert fix.acquisition_mode == AcquisitionMode.REPLAY
        
        # Zero physical HTTP attempts during replay
        assert res.physical_attempts == 0
        assert res.discovery_calls == 0
        
    finally:
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)

def test_tampered_manifest_or_object_rejected(temp_evidence_root):
    import os
    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(temp_evidence_root)
    
    try:
        response_disc = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"response": []}).encode("utf-8")
        )
        ref_disc = persist_response_evidence(
            operation="history_discovery",
            url="https://v3.football.api-sports.io/fixtures",
            params={"league": "39", "season": "2023"},
            response=response_disc,
            source_event_id="123",
        )
        
        bundle_id, manifest_path = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="TEAM_MATCH_FACTS",
            canonical_fixture_id=100,
            parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:123"],
            evidence_refs=[ref_disc],
        )
        
        # 1. Tamper manifest by changing some fields inside json directly
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["identity"]["parser_version"] = "tampered_version"
        manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")
        
        # Loading it should raise ValueError due to bundle ID mismatch
        from bet.integration.evidence import load_bundle_manifest
        with pytest.raises(ValueError, match="Evidence bundle hash mismatch"):
            load_bundle_manifest(bundle_id)
            
        # 2. Tamper evidence object file itself
        # Re-create correct manifest first
        bundle_id2, manifest_path2 = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="TEAM_MATCH_FACTS",
            canonical_fixture_id=100,
            parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:123"],
            evidence_refs=[ref_disc],
        )
        
        obj_path = temp_evidence_root / "objects" / ref_disc.object_sha256[:2] / ref_disc.object_sha256
        obj_path.write_bytes(b"tampered raw body bytes")
        
        # Loading manifest with tampered object should raise ValueError due to object hash mismatch
        with pytest.raises(ValueError, match="Evidence object hash mismatch"):
            load_bundle_manifest(bundle_id2)
            
    finally:
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)
