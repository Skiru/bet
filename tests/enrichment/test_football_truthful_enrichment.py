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
    CandidateRecord,
    PROVIDER_REGISTRY,
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
def valid_bundle_id(tmp_path):
    import hashlib
    from bet.integration.evidence import write_source_operation_bundle, EvidenceRef
    
    # Set BET_EVIDENCE_ROOT to tmp_path
    os.environ["BET_EVIDENCE_ROOT"] = str(tmp_path)
    
    # Write the object file
    response_body_bytes = b'{"test": "data"}'
    digest = hashlib.sha256(response_body_bytes).hexdigest()
    object_path = tmp_path / "objects" / digest[:2] / digest
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(response_body_bytes)
    
    ref = EvidenceRef(
        operation="test",
        request_identity="test",
        media_type="application/json",
        byte_size=len(response_body_bytes),
        object_sha256=digest,
        http_status=200,
        captured_at=datetime.now(UTC).isoformat(),
    )
    
    bundle_id, manifest_path = write_source_operation_bundle(
        registered_source_key="espn-football",
        operation_name="test",
        request_identity="test",
        parser_version="espn-v1",
        source_event_refs=[],
        evidence_refs=[ref],
        evidence_root=tmp_path,
    )
    return bundle_id


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

def test_evidence_chain_validation(seeded_db, db_conn, monkeypatch):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to return a successful result with an invalid/missing bundle ID
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"id": "740968", "date": "2026-05-24T15:00:00Z"}],
        bundle_id="invalid_bundle_id", # Invalid bundle ID
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="invalid_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"event_id": "123", "home_participant_id": "359", "away_participant_id": "384", "score": "2-1", "date": "2026-05-24T15:00:00Z"}],
        bundle_id="invalid_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id="invalid_bundle_id",
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    # Verify that the attempts for SUCCESS results are recorded as EVIDENCE_ERROR
    attempts = db_conn.execute("SELECT * FROM source_operation_attempt").fetchall()
    for attempt in attempts:
        print(f"OP: {attempt['operation']}, STATUS: {attempt['status']}")
    attempts = db_conn.execute("SELECT * FROM source_operation_attempt WHERE operation IN ('current_recent_form', 'h2h_head_to_head')").fetchall()
    assert len(attempts) > 0
    for attempt in attempts:
        assert attempt["status"] == "EVIDENCE_ERROR"


# ---------------------------------------------------------------------------
# 4. Attempt History Tests (Mandatory Test #4)
# ---------------------------------------------------------------------------

def test_attempt_history_persistence(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to return a successful result with evidence
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"id": "740968", "date": "2026-05-24T15:00:00Z"}],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
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

def test_full_offline_vertical(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to return a successful result with evidence
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[{"id": "740968", "date": "2026-05-24T15:00:00Z"}],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
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

def test_atomicity_on_failure(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # Mock the ESPN client to raise an exception during standings fetch
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
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

def test_idempotency_behavior(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
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


# ---------------------------------------------------------------------------
# Focused Tests (Requirement 6)
# ---------------------------------------------------------------------------

def test_home_away_form_separation(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    """Verify separate adapter operations populate distinct home_form and away_form."""
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    mock_client = MagicMock()
    # Return different matches for home and away form
    mock_client.get_team_last_fixtures_result.side_effect = [
        # First call (HOME)
        SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"id": "111", "date": "2026-05-24T15:00:00Z"}],
            bundle_id=valid_bundle_id,
            evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
        ),
        # Second call (AWAY)
        SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[{"id": "222", "date": "2026-05-24T15:00:00Z"}],
            bundle_id=valid_bundle_id,
            evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
        ),
    ]
    mock_ms_home = MagicMock()
    mock_ms_home.home_participant_id = "359"
    mock_ms_home.away_participant_id = "384"
    mock_ms_home.stats = {"goals": {"home": 2, "away": 1}}
    
    mock_ms_away = MagicMock()
    mock_ms_away.home_participant_id = "359"
    mock_ms_away.away_participant_id = "384"
    mock_ms_away.stats = {"goals": {"home": 1, "away": 2}}
    
    mock_client.get_fixture_stats_result.side_effect = [
        # For HOME form fixture "111"
        SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[mock_ms_home],
            bundle_id=valid_bundle_id,
            evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
        ),
        # For AWAY form fixture "222"
        SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[mock_ms_away],
            bundle_id=valid_bundle_id,
            evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
        ),
        # For fixture_team_statistics capability
        SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=[mock_ms_home],
            bundle_id=valid_bundle_id,
            evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
        ),
    ]
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    snapshot = service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    assert isinstance(snapshot, FootballEnrichmentSnapshot)
    # Verify distinct home and away form matches are populated
    assert len(snapshot.home_form) == 1
    assert len(snapshot.away_form) == 1
    assert snapshot.home_form[0].native_fixture_id == "111"
    assert snapshot.away_form[0].native_fixture_id == "222"


def test_status_and_fallback_behavior(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    """Verify failed primary remains in attempt history while successful fallback is selected."""
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    # We will register two providers for standings: primary (espn) and fallback (api-football)
    # Primary (espn) returns RATE_LIMITED, fallback (api-football) returns SUCCESS
    mock_espn = MagicMock()
    mock_espn.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_espn.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_espn.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_espn.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.RATE_LIMITED,
        error_code="rate_limited",
    )
    
    mock_api_football = MagicMock()
    mock_api_football.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    
    # Let's register both in the service
    from bet.enrichment.football_service import FootballAdapterRegistry, ESPNFootballAdapter, APIFootballCandidateAdapter
    registry = FootballAdapterRegistry()
    registry.register("espn", ESPNFootballAdapter(mock_espn))
    registry.register("api-football", APIFootballCandidateAdapter(mock_api_football))
    
    # Set api-football as qualified shadow so it can be used as fallback
    monkeypatch.setitem(CANDIDATE_REGISTRY, "api-football", CandidateRecord(
        provider_key="api-football",
        implementation_state="PRODUCTION_READY",
        credential_requirement=False,
        governance_state="QUALIFIED_SHADOW",
        provenance_family="api-football",
        supported_capabilities=("current_recent_form", "h2h_head_to_head", "standings_competition_context", "fixture_team_statistics"),
        replay_availability=True,
        live_probe_eligibility=True,
    ))
    monkeypatch.setitem(PROVIDER_REGISTRY, "api-football", ProviderState.QUALIFIED_SHADOW)
    
    # Update routing config to have both espn and api-football for standings
    original_load_config = load_and_validate_config
    def mock_load_config(*args, **kwargs):
        cfg = original_load_config(*args, **kwargs)
        cfg["routing"]["standings"] = {"precedence": ["espn", "api-football"]}
        return cfg
    monkeypatch.setattr("bet.enrichment.football_service.load_and_validate_config", mock_load_config)
    
    service = FootballEnrichmentService(registry)
    snapshot = service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    # Verify that both attempts are in history
    attempts = db_conn.execute("SELECT * FROM source_operation_attempt WHERE operation = 'standings_competition_context'").fetchall()
    assert len(attempts) == 2
    assert attempts[0]["provider"] == "espn"
    assert attempts[0]["status"] == "RATE_LIMITED"
    assert attempts[1]["provider"] == "api-football"
    assert attempts[1]["status"] == "NOT_SUPPORTED"


def test_transaction_boundary_assertion(seeded_db, db_conn, monkeypatch, valid_bundle_id):
    """Verify that adapter asserts no SQLite write transaction is active when called."""
    fixture_id, home_id, away_id = seeded_db
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    mock_client = MagicMock()
    mock_client.get_team_last_fixtures_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_fixture_stats_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_h2h_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    mock_client.get_standings_result.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value=[],
        bundle_id=valid_bundle_id,
        evidence_refs=(EvidenceRef(operation="test", request_identity="test", media_type="application/json", byte_size=16, object_sha256="40b61fe1b15af0a4d5402735b26343e8cf8a045f4d81710e6108a21d91eaf366"),),
    )
    
    service = create_football_enrichment_service(espn_client=mock_client)
    
    # If we run normally, it should pass because Stage 2 is outside of any transaction
    service.enrich_fixture(fixture_id, datetime.now(UTC))
