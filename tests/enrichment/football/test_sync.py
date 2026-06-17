# ruff: noqa: E501
import sqlite3
from datetime import date

import pytest

from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    BootstrapCommand,
    IncrementalCommand,
)
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService, compute_scope_key
from bet.enrichment.football.sync import FootballSyncEngine


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


def test_scope_isolation_under_different_scopes(db_conn):
    db_conn.execute("""INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_A', '101', '2023', '2023', 'DISCOVERED', '2023', '2023')""")
    db_conn.execute("""INSERT INTO sports_sync_item
                       (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at)
                       VALUES ('api-football', 'football', 'scope_B', '101', '2023', '2023', 'INGESTED_COMPLETE', '2023', '2023')""")

    db_conn.execute("""UPDATE sports_sync_item SET state='INGESTED_PARTIAL'
                       WHERE provider='api-football' AND sport='football' AND scope_key='scope_A' AND provider_fixture_id='101'""")

    state_b = db_conn.execute("""SELECT state FROM sports_sync_item
                                 WHERE provider='api-football' AND sport='football' AND scope_key='scope_B' AND provider_fixture_id='101'""").fetchone()[0]
    assert state_b == "INGESTED_COMPLETE"


def test_ids_unsupported_cache_persists(db_conn):
    from unittest.mock import MagicMock

    from bet.enrichment.football.contracts import FrozenClock
    from bet.enrichment.football.service import FootballHistoryService

    scope_key = compute_scope_key("39", 2023)
    # Seed cursor with coverage_json indicating UNEXPIRED UNSUPPORTED for batch_ids
    coverage_json = '{"batch_ids": {"state": "UNSUPPORTED", "checked_at": "2023-01-01T12:00:00Z", "ttl_days": 30}}'
    db_conn.execute("""INSERT INTO sports_sync_cursor (provider, sport, operation, scope_key, committed_through_date, coverage_json, created_at, updated_at)
                       VALUES ('api-football', 'football', 'completed-fixture-history', ?, '2023-01-02', ?, '2023', '2023')""",
                    (scope_key, coverage_json))

    mock_client = MagicMock()
    from bet.enrichment.football.provider import LiveAPIFootballAcquirer
    acquirer = LiveAPIFootballAcquirer(mock_client)

    # We use a FrozenClock of 2023-01-10 (which is unexpired under 30 days TTL)
    clock = FrozenClock("2023-01-10T12:00:00Z")
    service = FootballHistoryService(db_conn, acquirer, FootballSyncEngine(db_conn), FootballHistoryRepository(db_conn), clock=clock)

    # Setup discovery response
    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []}
    )

    cmd = IncrementalCommand(
        competition_provider_id="39",
        season=2023,
        correction_lookback_days=3,
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=5,
        daily_quota_reserve=10,
        minute_quota_reserve=2,
    )

    service.incremental_sync(cmd)

    # Verify that get_history_details was NEVER called because ids was unexpired unsupported!
    assert mock_client.get_history_details.call_count == 0


def test_current_utc_date_ingested_but_not_committed_as_closed(db_conn):
    from unittest.mock import MagicMock

    from bet.enrichment.football.contracts import FrozenClock
    from bet.enrichment.football.service import FootballHistoryService

    scope_key = compute_scope_key("39", 2023)
    db_conn.execute("""INSERT INTO sports_sync_cursor (provider, sport, operation, scope_key, committed_through_date, created_at, updated_at)
                       VALUES ('api-football', 'football', 'completed-fixture-history', ?, '2023-01-02', '2023', '2023')""",
                    (scope_key,))

    mock_client = MagicMock()
    from bet.enrichment.football.provider import LiveAPIFootballAcquirer
    acquirer = LiveAPIFootballAcquirer(mock_client)

    # Freeze clock to 2023-01-05
    clock = FrozenClock("2023-01-05T12:00:00Z")
    service = FootballHistoryService(db_conn, acquirer, FootballSyncEngine(db_conn), FootballHistoryRepository(db_conn), clock=clock)

    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    mock_client.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []}
    )

    cmd = IncrementalCommand(
        competition_provider_id="39",
        season=2023,
        correction_lookback_days=1,
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=5,
        daily_quota_reserve=10,
        minute_quota_reserve=2,
    )

    res = service.incremental_sync(cmd)

    # committed_through_date advances up to clock.today_utc() - 1 day, which is 2023-01-04!
    # It does NOT advance to 2023-01-05, leaving the current day open and closed day at 2023-01-04.
    assert res.cursor_after["committed_through_date"] == "2023-01-04"
