# ruff: noqa: E501
import sqlite3
import pytest
from datetime import date, datetime, timezone
import json

from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    BatchIdsCapability,
    BootstrapCommand,
    IncrementalCommand,
    AcquisitionResult,
)
from bet.enrichment.football.service import FootballHistoryService, compute_scope_key
from bet.enrichment.football.sync import FootballSyncEngine
from bet.enrichment.football.repository import FootballHistoryRepository

@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    yield conn
    conn.close()

def test_lease_conflict_blocks_execution(db_conn):
    sync = FootballSyncEngine(db_conn)
    scope_key = "test_scope"
    
    # Worker 1 acquires lease
    acq1 = sync.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, "worker1", ttl_minutes=15)
    assert acq1 is True
    
    # Worker 2 tries to acquire lease, should fail (returns False)
    acq2 = sync.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, "worker2", ttl_minutes=15)
    assert acq2 is False
    
    # Worker 1 can renew lease
    ren1 = sync.renew_lease("api-football", "football", "completed-fixture-history", scope_key, "worker1")
    assert ren1 is True
    
    # Worker 1 releases lease
    sync.release_lease("api-football", "football", "completed-fixture-history", scope_key, "worker1")
    
    # Now Worker 2 can acquire it!
    acq3 = sync.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, "worker2", ttl_minutes=15)
    assert acq3 is True

def test_lease_expired_recovery(db_conn):
    sync = FootballSyncEngine(db_conn)
    scope_key = "test_scope"
    
    # Worker 1 acquires lease with 0 duration (expired instantly)
    acq1 = sync.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, "worker1", ttl_minutes=-1)
    assert acq1 is True
    
    # Worker 2 tries to acquire it, should succeed due to expired-lease recovery!
    acq2 = sync.acquire_lease("api-football", "football", "completed-fixture-history", scope_key, "worker2")
    assert acq2 is True

def test_bootstrap_and_incremental_flow(db_conn):
    sync = FootballSyncEngine(db_conn)
    repo = FootballHistoryRepository(db_conn)
    
    # Mock client and acquirer
    mock_client = MagicMock()
    from bet.enrichment.football.provider import LiveAPIFootballAcquirer
    acquirer = LiveAPIFootballAcquirer(mock_client)
    
    service = FootballHistoryService(db_conn, acquirer, sync, repo)
    
    # 1. Mock bootstrap responses (discovery returned 1 fixture)
    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.contracts import FootballSide, FootballFactCompleteness
    from bet.integration.evidence import EvidenceRef
    
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 100, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "Premier League", "season": 2023},
                "teams": {
                    "home": {"id": 10, "name": "Home Team"},
                    "away": {"id": 20, "name": "Away Team"}
                },
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T15:00:00Z"),)
    )
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 100, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "statistics": [
                    {"team": {"id": 10}, "statistics": [
                        {"type": "Total Shots", "value": 10},
                        {"type": "Shots on Goal", "value": 5},
                        {"type": "Ball Possession", "value": "50%"},
                        {"type": "Fouls", "value": 12},
                        {"type": "Yellow Cards", "value": 1},
                        {"type": "Red Cards", "value": 0},
                        {"type": "Offsides", "value": 2},
                        {"type": "Corner Kicks", "value": 4},
                        {"type": "Goalkeeper Saves", "value": 3}
                    ]},
                    {"team": {"id": 20}, "statistics": [
                        {"type": "Total Shots", "value": 8},
                        {"type": "Shots on Goal", "value": 4},
                        {"type": "Ball Possession", "value": "50%"},
                        {"type": "Fouls", "value": 10},
                        {"type": "Yellow Cards", "value": 2},
                        {"type": "Red Cards", "value": 0},
                        {"type": "Offsides", "value": 1},
                        {"type": "Corner Kicks", "value": 3},
                        {"type": "Goalkeeper Saves", "value": 5}
                    ]}
                ]
            }
        ]},
        evidence_refs=(EvidenceRef("history_details", "GET", "json", 200, "hash_details", captured_at="2023-01-01T15:01:00Z"),)
    )
    
    # Run Bootstrap
    cmd = BootstrapCommand(
        competition_provider_id="39",
        season=2023,
        from_date=date.today(),
        to_date=date.today(),
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=5,
    )
    
    res = service.bootstrap(cmd)
    assert res.final_status == "COMPLETE"
    assert res.actual_counters["complete_count"] == 1
    
    # Cursor should have advanced committed_through_date to 2023-01-02
    assert res.cursor_after["committed_through_date"] == date.today().isoformat()
    
    # Incremental with 0 lookback days should execute zero physical calls and succeed immediately
    cmd_inc = IncrementalCommand(
        competition_provider_id="39",
        season=2023,
        correction_lookback_days=0,
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=5,
        daily_quota_reserve=10,
        minute_quota_reserve=2,
    )
    
    res_inc = service.incremental_sync(cmd_inc)
    assert res_inc.final_status == "COMPLETE"
    assert res_inc.actual_counters["physical_http_attempts"] == 0

from unittest.mock import MagicMock
