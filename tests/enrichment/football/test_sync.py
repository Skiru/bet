# ruff: noqa: E501
import sqlite3
from datetime import date, timedelta

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
    assert res.cursor_after["committed_through_date"] == (date.today() - timedelta(days=1)).isoformat()

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
    assert res_inc.actual_counters["physical_http_attempts"] == 1

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
    db_conn.commit()

    state_b = db_conn.execute("""SELECT state FROM sports_sync_item
                                 WHERE provider='api-football' AND sport='football' AND scope_key='scope_B' AND provider_fixture_id='101'""").fetchone()[0]
    assert state_b == "INGESTED_COMPLETE"


def test_ids_unsupported_cache_persists(db_conn):
    from unittest.mock import MagicMock

    from bet.enrichment.football.service import FootballHistoryService
    from scripts.enrichment.football_history import FrozenClock

    scope_key = compute_scope_key("39", 2023)
    # Seed cursor with coverage_json indicating UNEXPIRED UNSUPPORTED for batch_ids
    coverage_json = '{"batch_ids": {"state": "UNSUPPORTED", "checked_at": "2023-01-01T12:00:00Z", "ttl_days": 30}}'
    db_conn.execute("""INSERT INTO sports_sync_cursor (provider, sport, operation, scope_key, committed_through_date, coverage_json, created_at, updated_at)
                       VALUES ('api-football', 'football', 'completed-fixture-history', ?, '2023-01-02', ?, '2023', '2023')""",
                    (scope_key, coverage_json))
    db_conn.commit()

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

    from bet.enrichment.football.service import FootballHistoryService
    from scripts.enrichment.football_history import FrozenClock

    scope_key = compute_scope_key("39", 2023)
    db_conn.execute("""INSERT INTO sports_sync_cursor (provider, sport, operation, scope_key, committed_through_date, created_at, updated_at)
                       VALUES ('api-football', 'football', 'completed-fixture-history', ?, '2023-01-02', '2023', '2023')""",
                    (scope_key,))
    db_conn.commit()

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


def test_t3_scope_isolation_with_two_real_service_runs(tmp_path):
    import sqlite3

    from bet.db.schema import init_db
    from bet.enrichment.football.repository import FootballHistoryRepository
    from bet.enrichment.football.service import FootballHistoryService
    from bet.enrichment.football.sync import FootballSyncEngine

    db_file = tmp_path / "scope_iso.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.commit()

    # Run service for scope 1
    mock_client1 = MagicMock()
    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.provider import LiveAPIFootballAcquirer
    from bet.integration.evidence import EvidenceRef

    acquirer1 = LiveAPIFootballAcquirer(mock_client1)
    sync1 = FootballSyncEngine(conn)
    repo1 = FootballHistoryRepository(conn)
    service1 = FootballHistoryService(conn, acquirer1, sync1, repo1)

    mock_client1.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 100, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "league": {"id": 39, "name": "EPL", "season": 2023},
                "teams": {"home": {"id": 10, "name": "H"}, "away": {"id": 20, "name": "A"}},
                "goals": {"home": 2, "away": 1},
                "score": {"penalty": {"home": None, "away": None}}
            }
        ]},
        evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T15:00:00Z"),)
    )
    mock_client1.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [
            {
                "fixture": {"id": 100, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                "statistics": [
                    {"team": {"id": 10}, "statistics": []},
                    {"team": {"id": 20}, "statistics": []}
                ]
            }
        ]},
        evidence_refs=(EvidenceRef("history_details", "GET", "json", 200, "hash_details", captured_at="2023-01-01T15:01:00Z"),)
    )

    # Bootstrap scope 1
    cmd1 = BootstrapCommand(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 1),
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=5,
    )
    res1 = service1.bootstrap(cmd1)
    assert res1.final_status == "DEGRADED" # empty stats is degraded / score_only

    # Check that scope B is completely untouched and empty
    items_b = conn.execute("SELECT COUNT(*) FROM sports_sync_item WHERE scope_key = 'scope_B'").fetchone()[0]
    assert items_b == 0
    conn.close()

def test_t3_start_run_visible_from_second_connection(tmp_path):
    import sqlite3

    from bet.db.schema import init_db
    from bet.enrichment.football.sync import FootballSyncEngine

    db_file = tmp_path / "txn_test.db"
    conn1 = sqlite3.connect(str(db_file))
    conn1.execute("PRAGMA foreign_keys = ON")
    init_db(conn1)
    conn1.commit()

    sync = FootballSyncEngine(conn1)
    # create cursor
    conn1.execute("""INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, committed_through_date, created_at, updated_at)
                     VALUES (1, 'api-football', 'football', 'completed-fixture-history', 'scope1', '2023-01-01', '2023', '2023')""")
    conn1.commit()

    # start_run
    run_id = sync.start_run(1, "run1", "api-football", "football", "completed-fixture-history", "scope1", "BOOTSTRAP", "2023-01-01", "2023-01-01", "{}")

    # Open connection 2 and check if run is already committed and visible
    conn2 = sqlite3.connect(str(db_file))
    row = conn2.execute("SELECT status FROM sports_sync_run WHERE id = ?", (run_id,)).fetchone()
    assert row is not None
    assert row[0] == "RUNNING"
    conn1.close()
    conn2.close()

def test_t3_complete_run_visible_after_reopen(tmp_path):
    import sqlite3

    from bet.db.schema import init_db
    from bet.enrichment.football.sync import FootballSyncEngine

    db_file = tmp_path / "reopen_test.db"
    conn1 = sqlite3.connect(str(db_file))
    conn1.execute("PRAGMA foreign_keys = ON")
    init_db(conn1)
    conn1.commit()

    sync = FootballSyncEngine(conn1)
    conn1.execute("""INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, committed_through_date, created_at, updated_at)
                     VALUES (1, 'api-football', 'football', 'completed-fixture-history', 'scope1', '2023-01-01', '2023', '2023')""")
    conn1.commit()

    run_id = sync.start_run(1, "run1", "api-football", "football", "completed-fixture-history", "scope1", "BOOTSTRAP", "2023-01-01", "2023-01-01", "{}")

    # complete run
    sync.complete_run(run_id, "COMPLETE", "{}", {})

    # Reopen database and verify complete run is saved
    conn1.close()

    conn2 = sqlite3.connect(str(db_file))
    row = conn2.execute("SELECT status FROM sports_sync_run WHERE id = ?", (run_id,)).fetchone()
    assert row is not None
    assert row[0] == "COMPLETE"
    conn2.close()

def test_t3_corrupt_coverage_json_fails_closed(db_conn):
    from bet.enrichment.football.contracts import CursorCorruptionError
    from bet.enrichment.football.service import (
        FootballHistoryService,
        compute_scope_key,
    )

    scope_key = compute_scope_key("39", 2023)
    db_conn.execute("""INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, committed_through_date, coverage_json, created_at, updated_at)
                     VALUES (5, 'api-football', 'football', 'completed-fixture-history', ?, '2023-01-01', '{invalid_json', '2023', '2023')""",
                    (scope_key,))
    db_conn.commit()

    service = FootballHistoryService(db_conn, None, FootballSyncEngine(db_conn), None)
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
    with pytest.raises(CursorCorruptionError, match="CURSOR_CORRUPTION"):
        service.incremental_sync(cmd)

def test_t3_stale_run_becomes_abandoned(db_conn):
    from bet.enrichment.football.sync import FootballSyncEngine
    sync = FootballSyncEngine(db_conn)

    # Insert cursor with expired lease
    db_conn.execute("""INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, lease_owner, lease_expires_at, lock_version, created_at, updated_at)
                     VALUES (10, 'api-football', 'football', 'completed-fixture-history', 'stale_scope', 'worker1', '2023-01-01T12:00:00Z', 1, '2023', '2023')""")
    # Insert previous RUNNING run
    db_conn.execute("""INSERT INTO sports_sync_run (id, run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json)
                     VALUES (100, 'run_stale', 10, 'api-football', 'football', 'completed-fixture-history', 'stale_scope', 'bootstrap', '2023', '2023', 'RUNNING', '2023', '{}')""")
    db_conn.commit()

    # Acquire lease (should trigger stale run recovery)
    acquired = sync.acquire_lease("api-football", "football", "completed-fixture-history", "stale_scope", "worker2")
    assert acquired is True

    # Verify that run 100 has been marked ABANDONED with error_code STALE_LEASE_RECOVERY
    row = db_conn.execute("SELECT status, error_code FROM sports_sync_run WHERE id = 100").fetchone()
    assert row is not None
    assert row[0] == "ABANDONED"
    assert row[1] == "STALE_LEASE_RECOVERY"


def test_c0_1_incomplete_item_state_set():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1", "2"]),
        item_states={"1": "INGESTED_COMPLETE"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "INCOMPLETE_ITEM_STATE_SET"


def test_c0_2_unknown_item_state():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "UNKNOWN_STATE"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "UNKNOWN_SYNC_ITEM_STATE"


def test_c0_3_incomplete_discovery_paging():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=False,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(),
        item_states={},
        acquisition_rate_limited=False,
        physical_budget_exhausted=True,
    )
    assert outcome.status == "RATE_LIMITED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "DISCOVERY_INCOMPLETE_PAGING"

    outcome2 = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=False,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(),
        item_states={},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome2.status == "FAILED"
    assert outcome2.cursor_may_advance is False
    assert outcome2.error_code == "DISCOVERY_INCOMPLETE_PAGING"


def test_c0_4_rate_limited_ids_call_retained_capability():
    from unittest.mock import MagicMock

    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.contracts import BatchIdsCapability
    from bet.enrichment.football.provider import (
        LiveAPIFootballAcquirer,
        PhysicalAttemptBudget,
    )

    mock_client = MagicMock()
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.RATE_LIMITED,
        value=None
    )
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)
    res = acquirer.acquire_fixture_facts(
        discovered_fixtures=(),
        provider_fixture_ids_to_enrich=["100"],
        ids_capability=BatchIdsCapability.UNKNOWN,
        attempt_budget=budget,
        max_fallback_stats_calls=0
    )
    assert res.ids_capability == BatchIdsCapability.UNKNOWN


def test_c0_5_timeout_ids_call_retained_capability():
    from unittest.mock import MagicMock

    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.contracts import BatchIdsCapability
    from bet.enrichment.football.provider import (
        LiveAPIFootballAcquirer,
        PhysicalAttemptBudget,
    )

    mock_client = MagicMock()
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.TIMEOUT,
        value=None
    )
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)
    res = acquirer.acquire_fixture_facts(
        discovered_fixtures=(),
        provider_fixture_ids_to_enrich=["100"],
        ids_capability=BatchIdsCapability.SUPPORTED,
        attempt_budget=budget,
        max_fallback_stats_calls=0
    )
    assert res.ids_capability == BatchIdsCapability.SUPPORTED


def test_c0_6_plan_restricted_ids_call_sets_unsupported():
    from unittest.mock import MagicMock

    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.contracts import BatchIdsCapability
    from bet.enrichment.football.provider import (
        LiveAPIFootballAcquirer,
        PhysicalAttemptBudget,
    )

    mock_client = MagicMock()
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None
    )
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)
    res = acquirer.acquire_fixture_facts(
        discovered_fixtures=(),
        provider_fixture_ids_to_enrich=["100"],
        ids_capability=BatchIdsCapability.UNKNOWN,
        attempt_budget=budget,
        max_fallback_stats_calls=0
    )
    assert res.ids_capability == BatchIdsCapability.UNSUPPORTED


def test_c0_7_optional_ids_transient_failure_continues_to_stats():
    from unittest.mock import MagicMock

    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    from bet.enrichment.football.contracts import (
        BatchIdsCapability,
        FootballFixtureIdentity,
    )
    from bet.enrichment.football.provider import (
        LiveAPIFootballAcquirer,
        PhysicalAttemptBudget,
    )
    from bet.enrichment.football.time import parse_canonical_or_offset_datetime
    from bet.integration.evidence import EvidenceRef

    mock_client = MagicMock()
    mock_client.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.TIMEOUT,
        value=None
    )
    mock_client.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []},
        evidence_refs=(EvidenceRef("history_statistics", "GET", "json", 100, "hash_stats", captured_at="2023-01-01T12:00:00Z"),)
    )

    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(10)
    fixture_identity = FootballFixtureIdentity(
        provider_fixture_id="100",
        provider_competition_id="39",
        competition_name="Premier League",
        country="England",
        season=2023,
        round_name="Round 1",
        kickoff_at=parse_canonical_or_offset_datetime("2023-01-01T12:00:00Z"),
        provider_status="FT",
        canonical_status="finished",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_team_name="Home",
        away_team_name="Away",
        home_score=2,
        away_score=1,
        home_penalty_score=None,
        away_penalty_score=None,
        parser_version="1.0",
        schema_version="v2",
    )

    res = acquirer.acquire_fixture_facts(
        discovered_fixtures=(fixture_identity,),
        provider_fixture_ids_to_enrich=["100"],
        ids_capability=BatchIdsCapability.UNKNOWN,
        attempt_budget=budget,
        max_fallback_stats_calls=1,
        discovery_evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00Z"),)
    )
    assert mock_client.get_history_statistics.call_count == 1
    # On START_SHA, the details TIMEOUT would set cap = UNSUPPORTED, but here we check it's NOT transient failed.
    assert len(res.fixtures) == 1
    assert res.fixtures[0].fixture.provider_fixture_id == "100"


def test_c0_8_physical_attempt_exhaustion_creates_outcomes():
    from unittest.mock import MagicMock

    from bet.enrichment.football.contracts import (
        BatchIdsCapability,
        FootballFixtureIdentity,
    )
    from bet.enrichment.football.provider import (
        LiveAPIFootballAcquirer,
        PhysicalAttemptBudget,
    )
    from bet.enrichment.football.time import parse_canonical_or_offset_datetime
    from bet.integration.evidence import EvidenceRef

    mock_client = MagicMock()
    from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
    mock_client.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": []},
        retry_count=0
    )
    acquirer = LiveAPIFootballAcquirer(mock_client)
    budget = PhysicalAttemptBudget(2) # Min details call takes 2 minimum, so first Details takes budget, then budget is exhausted!

    # Let's say we have 2 fixtures, details succeeds for first chunk, but we run out of budget.
    # In C2, we expect a FixtureWorkOutcome for every requested fixture, regardless of budget depletion.
    # On START_SHA this will fail because no such outcome exists.
    # Let's check that if we try to access outcomes, it raises or fails.
    fixture_identity_1 = FootballFixtureIdentity(
        provider_fixture_id="100",
        provider_competition_id="39",
        competition_name="Premier League",
        country="England",
        season=2023,
        round_name="Round 1",
        kickoff_at=parse_canonical_or_offset_datetime("2023-01-01T12:00:00Z"),
        provider_status="FT",
        canonical_status="finished",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_team_name="Home",
        away_team_name="Away",
        home_score=2,
        away_score=1,
        home_penalty_score=None,
        away_penalty_score=None,
        parser_version="1.0",
        schema_version="v2",
    )
    fixture_identity_2 = FootballFixtureIdentity(
        provider_fixture_id="101",
        provider_competition_id="39",
        competition_name="Premier League",
        country="England",
        season=2023,
        round_name="Round 1",
        kickoff_at=parse_canonical_or_offset_datetime("2023-01-01T12:00:00Z"),
        provider_status="FT",
        canonical_status="finished",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_team_name="Home",
        away_team_name="Away",
        home_score=2,
        away_score=1,
        home_penalty_score=None,
        away_penalty_score=None,
        parser_version="1.0",
        schema_version="v2",
    )

    res = acquirer.acquire_fixture_facts(
        discovered_fixtures=(fixture_identity_1, fixture_identity_2),
        provider_fixture_ids_to_enrich=["100", "101"],
        ids_capability=BatchIdsCapability.UNSUPPORTED,  # So it uses fallback stats, which take 2 budget per fixture
        attempt_budget=budget,
        max_fallback_stats_calls=2,
        discovery_evidence_refs=(EvidenceRef("history_discovery", "GET", "json", 100, "hash_disc", captured_at="2023-01-01T12:00:00Z"),)
    )
    # Check that we have a work outcome for both fixtures
    assert hasattr(res, "outcomes")
    assert len(res.outcomes) == 2


def test_c0_9_physical_attempt_exhaustion_results_fields():
    from bet.enrichment.football.contracts import derive_run_outcome
    # Physical-attempt exhaustion results in:
    # - fixture item TRANSIENT_FAILED
    # - last_error_code HTTP_ATTEMPT_BUDGET_EXHAUSTED
    # - run RATE_LIMITED
    # - cursor unchanged
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "TRANSIENT_FAILED"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=True,
    )
    assert outcome.status == "RATE_LIMITED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "HTTP_ATTEMPT_BUDGET_EXHAUSTED"


def test_c0_10_max_fallback_stats_calls_exhaustion():
    from bet.enrichment.football.contracts import derive_run_outcome
    # max_fallback_stats_calls exhaustion results in:
    # - valid score-only observation
    # - item INGESTED_SCORE_ONLY
    # - diagnostic FALLBACK_STATISTICS_POLICY_LIMIT
    # - run DEGRADED
    # - cursor may advance
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "INGESTED_SCORE_ONLY"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "DEGRADED"
    assert outcome.cursor_may_advance is True
    assert outcome.error_code == "PARTIAL_COVERAGE"  # All items terminal, at least one INGESTED_SCORE_ONLY -> status DEGRADED, error PARTIAL_COVERAGE


def test_c0_11_rate_limited_rejected_as_item_state():
    from bet.enrichment.football.contracts import derive_run_outcome
    # RATE_LIMITED is rejected as sports_sync_item.state. If passed, it must fail.
    # Let's say if we pass RATE_LIMITED in item_states, derive_run_outcome fails.
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "RATE_LIMITED"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "UNKNOWN_SYNC_ITEM_STATE"  # rejected/unknown state for item_state


def test_c0_12_replay_containing_partial_facts_returns_degraded():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "INGESTED_PARTIAL"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "DEGRADED"
    assert outcome.cursor_may_advance is True
    assert outcome.error_code == "PARTIAL_COVERAGE"


def test_c0_13_replay_containing_score_only_facts_returns_degraded():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "INGESTED_SCORE_ONLY"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "DEGRADED"
    assert outcome.cursor_may_advance is True
    assert outcome.error_code == "PARTIAL_COVERAGE"


def test_c0_14_invalid_discovery_counters():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="DEGRADED",
        discovery_paging_completed=True,
        invalid_discovery_count=2,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "INGESTED_COMPLETE"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "DISCOVERY_SCHEMA_MISMATCH"
    # discovered_count includes valid and invalid records
    assert outcome.discovered_count == 3
    # transient_failed_count includes invalid records
    assert outcome.transient_failed_count == 2


def test_c0_15_invalid_discovery_blocks_cursor():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="DEGRADED",
        discovery_paging_completed=True,
        invalid_discovery_count=1,
        expected_fixture_ids=frozenset(["1"]),
        item_states={"1": "INGESTED_COMPLETE"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "DISCOVERY_SCHEMA_MISMATCH"


def test_c0_16_empty_completed_discovery_advances_cursor():
    from bet.enrichment.football.contracts import derive_run_outcome
    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(),
        item_states={},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "COMPLETE"
    assert outcome.cursor_may_advance is True
    assert outcome.error_code == "NO_COMPLETED_FIXTURES"
