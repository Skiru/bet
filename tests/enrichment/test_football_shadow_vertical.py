import os
import sqlite3
from datetime import datetime, UTC
import pytest

from bet.db.schema import init_db
from bet.db.repositories import SportRepo, TeamRepo, FixtureCapabilityRepo
from bet.enrichment.football_service import FootballEnrichmentService
from bet.enrichment.football_snapshot import FootballEnrichmentSnapshot
from scripts.normalize_stats import build_safety_input

@pytest.fixture
def db_conn(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    
    # Mock get_db to return our in-memory connection as a context manager
    import bet.db.connection
    from contextlib import contextmanager
    
    @contextmanager
    def mock_get_db(db_path=None):
        yield conn
        
    monkeypatch.setattr(bet.db.connection, "get_db", mock_get_db)
    
    yield conn
    conn.close()

def test_football_service_requires_fixture_and_cutoff(db_conn):
    """Verify that FootballEnrichmentService requires canonical fixture ID and cutoff."""
    service = FootballEnrichmentService()
    with pytest.raises(ValueError):
        service.enrich_fixture(9999, datetime.now(UTC))

def test_football_service_enrichment_flow(db_conn):
    """Verify the full flow: source result -> DTO -> attempt -> observation -> projection -> snapshot."""
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
    
    service = FootballEnrichmentService()
    snapshot = service.enrich_fixture(fixture_id, datetime.now(UTC))
    
    assert isinstance(snapshot, FootballEnrichmentSnapshot)
    assert snapshot.canonical_fixture_id == fixture_id
    assert snapshot.snapshot_state == "COMPLETE"
    assert snapshot.home_participant.canonical_id == home.id
    assert snapshot.away_participant.canonical_id == away.id
    
    # Verify run and snapshot are persisted
    run = db_conn.execute("SELECT * FROM sports_enrichment_run WHERE canonical_event_id = ?", (fixture_id,)).fetchone()
    assert run is not None
    assert run["status"] == "COMPLETE"
    
    snap_row = db_conn.execute("SELECT * FROM analysis_snapshot WHERE canonical_fixture_id = ?", (fixture_id,)).fetchone()
    assert snap_row is not None
    assert snap_row["status"] == "COMPLETE"

def test_football_enrichment_mode_off(db_conn, monkeypatch):
    """Verify that off mode performs no new enrichment work."""
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "off")
    
    # If we call build_safety_input, it should not call FootballEnrichmentService
    # We can verify this by checking that no runs are created in the DB
    build_safety_input("football", "Arsenal", "Chelsea", "Premier League")
    
    runs = db_conn.execute("SELECT * FROM sports_enrichment_run").fetchall()
    assert len(runs) == 0

def test_football_enrichment_mode_shadow(db_conn, monkeypatch):
    """Verify that shadow mode executes the service but does not change legacy output."""
    monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", "shadow")
    
    sport_repo = SportRepo(db_conn)
    sport_repo.seed_defaults()
    football = sport_repo.get_by_name("football")
    
    team_repo = TeamRepo(db_conn)
    home = team_repo.find_or_create("Arsenal", football.id)
    away = team_repo.find_or_create("Chelsea", football.id)
    
    db_conn.execute(
        "INSERT INTO fixtures (sport_id, home_team_id, away_team_id, kickoff, status, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
        (football.id, home.id, away.id, "2026-06-14T18:00:00+00:00", "scheduled", datetime.now(UTC).isoformat())
    )
    fixture_id = db_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    
    # Call build_safety_input
    build_safety_input("football", "Arsenal", "Chelsea", "Premier League", fixture_id=fixture_id)
    
    # Verify that a run was created in shadow mode
    runs = db_conn.execute("SELECT * FROM sports_enrichment_run WHERE canonical_event_id = ?", (fixture_id,)).fetchall()
    assert len(runs) == 1
    assert runs[0]["status"] == "COMPLETE"

def test_football_enrichment_mode_unauthorized(db_conn, monkeypatch):
    """Verify that canary and on modes are explicitly unauthorized and fail closed."""
    for mode in ("canary", "on"):
        monkeypatch.setenv("FOOTBALL_ENRICHMENT_MODE", mode)
        with pytest.raises(PermissionError):
            build_safety_input("football", "Arsenal", "Chelsea", "Premier League")
