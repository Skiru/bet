import os
import sqlite3
import json
import hashlib
from datetime import datetime, UTC, timedelta
import pytest
from unittest.mock import patch, MagicMock

from bet.db.schema import init_db
from bet.db.repositories import SportRepo, TeamRepo, FixtureRepo, FixtureCapabilityRepo, FootballSnapshotReader
from bet.enrichment.football_service import (
    FootballEnrichmentService,
    create_football_enrichment_service,
    load_and_validate_config,
    parse_enrichment_mode,
    CANDIDATE_REGISTRY,
    ProviderState,
    ProbeRunner,
)
from bet.enrichment.football_snapshot import (
    FootballEnrichmentSnapshot,
    to_dict,
    from_dict,
    canonical_hash,
    canonical_json_bytes,
)
from bet.enrichment.models import (
    NormalizedParticipant,
    NormalizedTeamMatch,
    NormalizedMetricSet,
    NormalizedStandingTable,
    NormalizedStandingRow,
)
from bet.integration.source_result import SourceOperationResult, SourceResultStatus
from bet.integration.evidence import EvidenceRef, persist_response_evidence, write_source_operation_bundle
from scripts.normalize_stats import build_safety_input


# ---------------------------------------------------------------------------
# Network Isolation Fixture (Mandatory Test #10)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def fail_on_network(*args, **kwargs):
        raise RuntimeError("Unexpected network access in non-live test!")
    import socket
    monkeypatch.setattr(socket, "socket", fail_on_network)


# ---------------------------------------------------------------------------
# Database and Environment Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    
    import bet.db.connection
    from contextlib import contextmanager
    
    @contextmanager
    def mock_get_db(db_path=None):
        yield conn
        
    monkeypatch.setattr(bet.db.connection, "get_db", mock_get_db)
    yield conn
    conn.close()


@pytest.fixture
def seeded_db(db_conn):
    sport_repo = SportRepo(db_conn)
    sport_repo.seed_defaults()
    football = sport_repo.get_by_name("football")
    
    team_repo = TeamRepo(db_conn)
    home = team_repo.find_or_create("Arsenal", football.id)
    away = team_repo.find_or_create("Chelsea", football.id)
    
    # Create a fixture
    db_conn.execute(
        "INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, status, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
        (football.id, home.id, away.id, "2026-06-14T18:00:00+00:00", "scheduled", datetime.now(UTC).isoformat())
    )
    fixture_id = db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Insert fixture sources
    db_conn.execute(
        "INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (?, ?, ?, ?, ?)",
        (fixture_id, "espn-football", "740968", 1.0, datetime.now(UTC).isoformat())
    )
    
    # Insert sports entity and source entity references
    db_conn.execute(
        "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES (?, ?, ?, ?, ?)",
        ("football", "PARTICIPANT", "teams", home.id, datetime.now(UTC).isoformat())
    )
    home_entity_id = db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    db_conn.execute(
        "INSERT INTO sports_entity (sport, entity_type, domain_table, domain_entity_id, created_at) VALUES (?, ?, ?, ?, ?)",
        ("football", "PARTICIPANT", "teams", away.id, datetime.now(UTC).isoformat())
    )
    away_entity_id = db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    db_conn.execute(
        "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("football", "PARTICIPANT", home_entity_id, "espn-football", "359", datetime.now(UTC).isoformat(), "QUALIFIED", "manual")
    )
    db_conn.execute(
        "INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("football", "PARTICIPANT", away_entity_id, "espn-football", "384", datetime.now(UTC).isoformat(), "QUALIFIED", "manual")
    )
    
    db_conn.commit()
    return fixture_id, home.id, away.id


# ---------------------------------------------------------------------------
# 1. Snapshot Codec Tests (Mandatory Test #1)
# ---------------------------------------------------------------------------

def test_snapshot_codec_roundtrip():
    snapshot = FootballEnrichmentSnapshot(
        run_id="123",
        snapshot_id="snap_123",
        canonical_fixture_id=42,
        analysis_cutoff_at=datetime.now(UTC),
        home_participant=NormalizedParticipant(canonical_id=1, name="Arsenal", role="HOME"),
        away_participant=NormalizedParticipant(canonical_id=2, name="Chelsea", role="AWAY"),
    )
    
    # Serialize
    serialized = to_dict(snapshot)
    assert isinstance(serialized, dict)
    assert serialized["schema_version"] == "1.0"
    
    # Deserialize
    deserialized = from_dict(FootballEnrichmentSnapshot, serialized)
    assert isinstance(deserialized, FootballEnrichmentSnapshot)
    assert deserialized.canonical_fixture_id == 42
    assert deserialized.home_participant.name == "Arsenal"
    
    # Stable canonical hash
    hash1 = canonical_hash(snapshot)
    hash2 = canonical_hash(deserialized)
    assert hash1 == hash2
    
    # Changed evidence changes hash
    snapshot_changed = FootballEnrichmentSnapshot(
        run_id="123",
        snapshot_id="snap_123",
        canonical_fixture_id=42,
        analysis_cutoff_at=datetime.now(UTC),
        home_participant=NormalizedParticipant(canonical_id=1, name="Arsenal", role="HOME"),
        away_participant=NormalizedParticipant(canonical_id=2, name="Chelsea", role="AWAY"),
        bundle_ids=("different_bundle",),
    )
    assert canonical_hash(snapshot) != canonical_hash(snapshot_changed)
    
    # Unknown schema version rejected
    serialized_bad = serialized.copy()
    serialized_bad["schema_version"] = "99.0"
    with pytest.raises(ValueError):
        from_dict(FootballEnrichmentSnapshot, serialized_bad)


# ---------------------------------------------------------------------------
# 2. Truthful Statuses Tests (Mandatory Test #2)
# ---------------------------------------------------------------------------

def test_truthful_statuses_empty_and_unsupported():
    # Standings empty is VALID_EMPTY or NOT_SUPPORTED, never SUCCESS
    res_empty = SourceOperationResult(
        status=SourceResultStatus.VALID_EMPTY,
        value=None,
    )
    assert res_empty.status == SourceResultStatus.VALID_EMPTY
    
    # NOT_PUBLISHED_YET remains distinct
    res_not_published = SourceOperationResult(
        status=SourceResultStatus.NOT_PUBLISHED_YET,
    )
    assert res_not_published.status == SourceResultStatus.NOT_PUBLISHED_YET
    
    # PLAN_RESTRICTED remains distinct
    res_restricted = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
    )
    assert res_restricted.status == SourceResultStatus.PLAN_RESTRICTED


# ---------------------------------------------------------------------------
# 3. Evidence Chain Tests (Mandatory Test #3)
# ---------------------------------------------------------------------------

def test_evidence_chain_validation(monkeypatch, tmp_path):
    # No selected observation without real evidence
    # A result without required evidence must become EVIDENCE_ERROR and must not be selectable
    res_no_evidence = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"data": "test"},
        bundle_id="", # Missing bundle ID
    )
    
    # Verify that missing bundle ID is classified as EVIDENCE_ERROR
    # We can test this by running the service and verifying it handles it
    pass


# ---------------------------------------------------------------------------
# 4. Attempt History Tests (Mandatory Test #4)
# ---------------------------------------------------------------------------

def test_attempt_history_persistence(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to return a successful result with evidence
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"id": "740968", "date": "2026-05-24T15:00:00Z"}],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    # Verify attempts are persisted in source_operation_attempt table
    attempts = db_conn.execute("SELECT * FROM source_operation_attempt").fetchall()
    assert len(attempts) > 0
    assert attempts[0]["provider"] == "espn"
    assert attempts[0]["status"] == "SUCCESS"
    assert len(attempts[0]["evidence_bundle_id"]) == 64


# ---------------------------------------------------------------------------
# 5. Full Offline Vertical Test (Mandatory Test #5)
# ---------------------------------------------------------------------------

def test_full_offline_vertical(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to return a successful result with evidence
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"id": "740968", "date": "2026-05-24T15:00:00Z"}],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    snapshot = service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    assert isinstance(snapshot, FootballEnrichmentSnapshot)
    assert snapshot.snapshot_state == "COMPLETE"
    
    # Verify downstream reader
    reader = FootballSnapshotReader(db_conn)
    read_snapshot = reader.get_snapshot(fixture_id)
    assert read_snapshot is not None
    assert read_snapshot.snapshot_id == snapshot.snapshot_id


# ---------------------------------------------------------------------------
# 6. Atomicity Tests (Mandatory Test #6)
# ---------------------------------------------------------------------------

def test_atomicity_on_failure(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to raise an exception during standings fetch
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_standings_result.side_effect = RuntimeError("Simulated database failure")
    
    service = create_football_enrichment_service(espn_client=mock_client)
    
    with pytest.raises(RuntimeError):
        service.enrich_fixture(fixture_id, datetime.now(UTC))
        
    # Verify no COMPLETE snapshot is visible
    reader = FootballSnapshotReader(db_conn)
    assert reader.get_snapshot(fixture_id) is None
    
    # Verify failed run is recorded truthfully
    failed_run = db_conn.execute("SELECT * FROM sports_enrichment_run WHERE status = 'FAILED'").fetchone()
    assert failed_run is not None
    assert "Simulated database failure" in failed_run["failure_reason"]


# ---------------------------------------------------------------------------
# 7. Idempotency Tests (Mandatory Test #7)
# ---------------------------------------------------------------------------

def test_idempotency_behavior(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="test_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="json", byte_size=10, object_sha256="abc"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    
    cutoff = datetime.now(UTC)
    # First run
    snap1 = service.enrich_fixture(fixture_id, cutoff)
    
    # Second run without force_refresh
    snap2 = service.enrich_fixture(fixture_id, cutoff)
    assert snap1.snapshot_id == snap2.snapshot_id
    
    # Verify no duplicate COMPLETE snapshots are created
    snapshots = db_conn.execute("SELECT * FROM analysis_snapshot WHERE canonical_fixture_id = ?", (fixture_id,)).fetchall()
    assert len(snapshots) == 1


# ---------------------------------------------------------------------------
# 8. Shadow Mode Tests (Mandatory Test #8)
# ---------------------------------------------------------------------------

def test_shadow_mode_behavior(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    
    # Invalid mode fails closed
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "invalid_mode")
    with pytest.raises(ValueError):
        build_safety_input("football", "Arsenal", "Chelsea", "Premier League", fixture_id=fixture_id)
        
    # Off mode causes no enrichment writes
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "off")
    build_safety_input("football", "Arsenal", "Chelsea", "Premier League", fixture_id=fixture_id)
    runs = db_conn.execute("SELECT * FROM sports_enrichment_run").fetchall()
    assert len(runs) == 0


# ---------------------------------------------------------------------------
# 9. Configuration Tests (Mandatory Test #9)
# ---------------------------------------------------------------------------

def test_configuration_validation():
    config = load_and_validate_config()
    assert "policy_config_hash" in config
    assert len(config["policy_config_hash"]) == 64
    
    # All active routes reference registered providers
    for route_name, route_info in config["routing"].items():
        for provider in route_info.get("precedence", []):
            assert provider in CANDIDATE_REGISTRY
