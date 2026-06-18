# ruff: noqa: E501
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    BootstrapCommand,
    CursorCorruptionError,
    derive_run_outcome,
)
from bet.enrichment.football.provider import LiveAPIFootballAcquirer
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService, compute_scope_key
from bet.enrichment.football.sync import FootballSyncEngine
from bet.integration.evidence import EvidenceRef, load_bundle_manifest
from scripts.enrichment.football_history import FrozenClock


def _fixture_payload() -> dict:
    return {
        "fixture": {"id": 100, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
        "league": {"id": 39, "name": "Premier League", "season": 2023},
        "teams": {
            "home": {"id": 10, "name": "Home Team"},
            "away": {"id": 20, "name": "Away Team"},
        },
        "goals": {"home": 2, "away": 1},
        "score": {"penalty": {"home": None, "away": None}},
    }


def _statistics_payload(home_shots: int = 10, away_shots: int = 8) -> dict:
    return {
        "response": [
            {
                "team": {"id": 10},
                "statistics": [
                    {"type": "Total Shots", "value": home_shots},
                    {"type": "Shots on Goal", "value": 5},
                    {"type": "Ball Possession", "value": "50%"},
                    {"type": "Fouls", "value": 12},
                    {"type": "Yellow Cards", "value": 1},
                    {"type": "Red Cards", "value": 0},
                    {"type": "Offsides", "value": 2},
                    {"type": "Corner Kicks", "value": 4},
                    {"type": "Goalkeeper Saves", "value": 3},
                ],
            },
            {
                "team": {"id": 20},
                "statistics": [
                    {"type": "Total Shots", "value": away_shots},
                    {"type": "Shots on Goal", "value": 4},
                    {"type": "Ball Possession", "value": "50%"},
                    {"type": "Fouls", "value": 10},
                    {"type": "Yellow Cards", "value": 2},
                    {"type": "Red Cards", "value": 0},
                    {"type": "Offsides", "value": 1},
                    {"type": "Corner Kicks", "value": 3},
                    {"type": "Goalkeeper Saves", "value": 5},
                ],
            },
        ]
    }


def _seed_evidence_ref(
    evidence_root: Path,
    *,
    operation: str,
    request_identity: str,
    captured_at: str,
    payload: dict,
    source_event_id: str = "100",
    http_status: int = 200,
) -> EvidenceRef:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()
    object_path = evidence_root / "objects" / digest[:2] / digest
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_bytes(body)
    return EvidenceRef(
        operation=operation,
        request_identity=request_identity,
        media_type="application/json",
        byte_size=len(body),
        object_sha256=digest,
        source_event_id=source_event_id,
        http_status=http_status,
        captured_at=captured_at,
    )


def _build_runtime(db_path: Path, client: MagicMock, clock: FrozenClock) -> tuple[sqlite3.Connection, FootballHistoryService]:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    service = FootballHistoryService(
        conn,
        LiveAPIFootballAcquirer(client),
        FootballSyncEngine(conn),
        FootballHistoryRepository(conn),
        clock=clock,
    )
    return conn, service


def _bootstrap_cmd(max_fallback_stats_calls: int) -> BootstrapCommand:
    return BootstrapCommand(
        competition_provider_id="39",
        season=2023,
        from_date=date(2023, 1, 1),
        to_date=date(2023, 1, 1),
        max_fixtures=10,
        max_http_attempts=10,
        max_fallback_stats_calls=max_fallback_stats_calls,
    )


def _bundle_request_identities(evidence_root: Path, bundle_id: str) -> set[str]:
    manifest = load_bundle_manifest(bundle_id, evidence_root=evidence_root)
    return {entry.request_identity for entry in manifest["entries"]}


def test_f1_production_acceptance(tmp_path, monkeypatch):
    scope_key = compute_scope_key("39", 2023)

    scenario_a_root = tmp_path / "scenario_a"
    scenario_a_root.mkdir()
    scenario_a_evidence = scenario_a_root / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(scenario_a_evidence))
    client_a = MagicMock()
    disc_ref_a = _seed_evidence_ref(
        scenario_a_evidence,
        operation="history_discovery",
        request_identity="GET https://example.test/history/discovery?fixture=100",
        captured_at="2023-01-02T09:00:00Z",
        payload={"response": [_fixture_payload()]},
    )
    stats_ref_a = _seed_evidence_ref(
        scenario_a_evidence,
        operation="history_statistics",
        request_identity="GET https://example.test/history/statistics?fixture=100",
        captured_at="2023-01-02T09:05:00Z",
        payload={"response": [], "status": "PLAN_RESTRICTED"},
    )
    client_a.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [_fixture_payload()]},
        evidence_refs=(disc_ref_a,),
    )
    client_a.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None,
    )
    client_a.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None,
        evidence_refs=(stats_ref_a,),
    )
    conn_a, service_a = _build_runtime(scenario_a_root / "history.sqlite3", client_a, FrozenClock("2023-01-03T12:00:00Z"))

    try:
        result_a = service_a.bootstrap(_bootstrap_cmd(max_fallback_stats_calls=1))

        assert result_a.final_status == "DEGRADED"
        assert conn_a.execute("SELECT COUNT(*) FROM fixtures").fetchone()[0] == 1
        assert conn_a.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 2

        obs_rows_a = conn_a.execute(
            "SELECT status, parser_diagnostics_json FROM fixture_capability_observation ORDER BY id"
        ).fetchall()
        assert len(obs_rows_a) == 2
        for status, diag_json in obs_rows_a:
            diag = json.loads(diag_json)
            assert status == "PARTIAL"
            assert diag["completeness"] == "SCORE_ONLY"
            assert diag["reason"] == "STATISTICS_PLAN_RESTRICTED"

        sync_item_a = conn_a.execute(
            """SELECT state, fixture_evidence_bundle_id, statistics_evidence_bundle_id
               FROM sports_sync_item
               WHERE scope_key = ? AND provider_fixture_id = '100'""",
            (scope_key,),
        ).fetchone()
        assert sync_item_a[0] == "PERMANENTLY_UNAVAILABLE"
        assert sync_item_a[2] is not None
        assert _bundle_request_identities(scenario_a_evidence, sync_item_a[1]) == {
            disc_ref_a.request_identity,
            stats_ref_a.request_identity,
        }

        run_row_a = conn_a.execute(
            "SELECT status, error_code, permanently_unavailable_count FROM sports_sync_run WHERE id = ?",
            (result_a.sync_run_id,),
        ).fetchone()
        assert run_row_a == ("DEGRADED", "PARTIAL_COVERAGE", 1)
    finally:
        conn_a.close()

    scenario_b_root = tmp_path / "scenario_b"
    scenario_b_root.mkdir()
    scenario_b_evidence = scenario_b_root / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(scenario_b_evidence))
    client_b = MagicMock()
    disc_ref_b = _seed_evidence_ref(
        scenario_b_evidence,
        operation="history_discovery",
        request_identity="GET https://example.test/history/discovery?fixture=100&scenario=b",
        captured_at="2023-01-02T10:00:00Z",
        payload={"response": [_fixture_payload()]},
    )
    client_b.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [_fixture_payload()]},
        evidence_refs=(disc_ref_b,),
    )
    client_b.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None,
    )
    conn_b, service_b = _build_runtime(scenario_b_root / "history.sqlite3", client_b, FrozenClock("2023-01-03T12:00:00Z"))

    try:
        result_b = service_b.bootstrap(_bootstrap_cmd(max_fallback_stats_calls=0))

        assert result_b.final_status == "DEGRADED"
        assert client_b.get_history_statistics.call_count == 0

        obs_rows_b = conn_b.execute(
            "SELECT status, parser_diagnostics_json FROM fixture_capability_observation ORDER BY id"
        ).fetchall()
        assert len(obs_rows_b) == 2
        for status, diag_json in obs_rows_b:
            diag = json.loads(diag_json)
            assert status == "PARTIAL"
            assert diag["reason"] == "FALLBACK_STATISTICS_POLICY_LIMIT"

        sync_item_b = conn_b.execute(
            """SELECT state, fixture_evidence_bundle_id, statistics_evidence_bundle_id
               FROM sports_sync_item
               WHERE scope_key = ? AND provider_fixture_id = '100'""",
            (scope_key,),
        ).fetchone()
        assert sync_item_b[0] == "INGESTED_SCORE_ONLY"
        assert sync_item_b[2] is None
        assert _bundle_request_identities(scenario_b_evidence, sync_item_b[1]) == {disc_ref_b.request_identity}
    finally:
        conn_b.close()

    scenario_c_root = tmp_path / "scenario_c"
    scenario_c_root.mkdir()
    scenario_c_evidence = scenario_c_root / "evidence"
    monkeypatch.setenv("BET_EVIDENCE_ROOT", str(scenario_c_evidence))
    client_c1 = MagicMock()
    disc_ref_c1 = _seed_evidence_ref(
        scenario_c_evidence,
        operation="history_discovery",
        request_identity="GET https://example.test/history/discovery?fixture=100&scenario=c1",
        captured_at="2023-01-02T11:00:00Z",
        payload={"response": [_fixture_payload()]},
    )
    stats_ref_c1 = _seed_evidence_ref(
        scenario_c_evidence,
        operation="history_statistics",
        request_identity="GET https://example.test/history/statistics?fixture=100&scenario=c1",
        captured_at="2023-01-02T11:05:00Z",
        payload={"response": [], "status": "RATE_LIMITED"},
        http_status=429,
    )
    client_c1.get_history_discovery.return_value = SourceOperationResult(
        status=SourceResultStatus.SUCCESS,
        value={"response": [_fixture_payload()]},
        evidence_refs=(disc_ref_c1,),
    )
    client_c1.get_history_details.return_value = SourceOperationResult(
        status=SourceResultStatus.PLAN_RESTRICTED,
        value=None,
    )
    client_c1.get_history_statistics.return_value = SourceOperationResult(
        status=SourceResultStatus.RATE_LIMITED,
        value=None,
        evidence_refs=(stats_ref_c1,),
    )
    conn_c, service_c1 = _build_runtime(scenario_c_root / "history.sqlite3", client_c1, FrozenClock("2023-01-03T12:00:00Z"))

    try:
        result_c1 = service_c1.bootstrap(_bootstrap_cmd(max_fallback_stats_calls=1))

        assert result_c1.final_status == "RATE_LIMITED"
        fixture_row_c1 = conn_c.execute(
            "SELECT id, home_team_id, away_team_id FROM fixtures WHERE source = 'api-football'"
        ).fetchone()
        assert fixture_row_c1 is not None

        sync_item_c1 = conn_c.execute(
            """SELECT state, last_error_code, last_success_at, fixture_evidence_bundle_id
               FROM sports_sync_item
               WHERE scope_key = ? AND provider_fixture_id = '100'""",
            (scope_key,),
        ).fetchone()
        assert sync_item_c1[0] == "TRANSIENT_FAILED"
        assert sync_item_c1[1] == "RATE_LIMITED"
        assert sync_item_c1[2] is None
        assert _bundle_request_identities(scenario_c_evidence, sync_item_c1[3]) == {
            disc_ref_c1.request_identity,
            stats_ref_c1.request_identity,
        }

        obs_rows_c1 = conn_c.execute(
            "SELECT status, parser_diagnostics_json FROM fixture_capability_observation ORDER BY id"
        ).fetchall()
        assert len(obs_rows_c1) == 2
        for status, diag_json in obs_rows_c1:
            diag = json.loads(diag_json)
            assert status == "PARTIAL"
            assert diag["completeness"] == "SCORE_ONLY"
            assert diag["reason"] == "OPTIONAL_STATISTICS_PENDING"

        cursor_row_c1 = conn_c.execute(
            "SELECT committed_through_date FROM sports_sync_cursor WHERE scope_key = ?",
            (scope_key,),
        ).fetchone()
        assert cursor_row_c1[0] is None

        client_c2 = MagicMock()
        disc_ref_c2 = _seed_evidence_ref(
            scenario_c_evidence,
            operation="history_discovery",
            request_identity="GET https://example.test/history/discovery?fixture=100&scenario=c2",
            captured_at="2023-01-04T08:00:00Z",
            payload={"response": [_fixture_payload()]},
        )
        stats_ref_c2 = _seed_evidence_ref(
            scenario_c_evidence,
            operation="history_statistics",
            request_identity="GET https://example.test/history/statistics?fixture=100&scenario=c2",
            captured_at="2023-01-04T08:05:00Z",
            payload=_statistics_payload(home_shots=14, away_shots=9),
        )
        client_c2.get_history_discovery.return_value = SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value={"response": [_fixture_payload()]},
            evidence_refs=(disc_ref_c2,),
        )
        client_c2.get_history_details.return_value = SourceOperationResult(
            status=SourceResultStatus.PLAN_RESTRICTED,
            value=None,
        )
        client_c2.get_history_statistics.return_value = SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value=_statistics_payload(home_shots=14, away_shots=9),
            evidence_refs=(stats_ref_c2,),
        )
        service_c2 = FootballHistoryService(
            conn_c,
            LiveAPIFootballAcquirer(client_c2),
            FootballSyncEngine(conn_c),
            FootballHistoryRepository(conn_c),
            clock=FrozenClock("2023-01-04T12:00:00Z"),
        )

        result_c2 = service_c2.bootstrap(_bootstrap_cmd(max_fallback_stats_calls=1))

        assert result_c2.final_status == "COMPLETE"
        assert result_c2.cursor_after["committed_through_date"] == "2023-01-01"
        fixture_row_c2 = conn_c.execute(
            "SELECT id, home_team_id, away_team_id FROM fixtures WHERE source = 'api-football'"
        ).fetchone()
        assert fixture_row_c2 == fixture_row_c1
        assert conn_c.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 2
        assert conn_c.execute("SELECT COUNT(*) FROM fixture_capability_observation").fetchone()[0] == 4

        sync_item_c2 = conn_c.execute(
            """SELECT state, last_error_code, last_success_at
               FROM sports_sync_item
               WHERE scope_key = ? AND provider_fixture_id = '100'""",
            (scope_key,),
        ).fetchone()
        assert sync_item_c2[0] == "INGESTED_COMPLETE"
        assert sync_item_c2[1] is None
        assert sync_item_c2[2] == "2023-01-04T08:05:00.000000Z"

        statuses_c2 = conn_c.execute(
            "SELECT status FROM fixture_capability_observation ORDER BY id"
        ).fetchall()
        assert [row[0] for row in statuses_c2] == ["PARTIAL", "PARTIAL", "SUCCESS", "SUCCESS"]
    finally:
        conn_c.close()

    outcome = derive_run_outcome(
        discovery_status="COMPLETE",
        discovery_paging_completed=True,
        invalid_discovery_count=0,
        expected_fixture_ids=frozenset(["100"]),
        item_states={"100": "DISCOVERED"},
        acquisition_rate_limited=False,
        physical_budget_exhausted=False,
    )
    assert outcome.status == "FAILED"
    assert outcome.cursor_may_advance is False
    assert outcome.error_code == "NON_TERMINAL_SYNC_ITEM_STATE"

    scenario_d_db = tmp_path / "scenario_d.sqlite3"
    conn_d = sqlite3.connect(str(scenario_d_db))
    conn_d.execute("PRAGMA foreign_keys = ON")
    init_db(conn_d)
    engine_d = FootballSyncEngine(conn_d)

    try:
        conn_d.execute(
            """INSERT INTO sports_sync_cursor
               (provider, sport, operation, scope_key, committed_through_date, last_success_at, lock_version, created_at, updated_at)
               VALUES ('api-football', 'football', 'completed-fixture-history', 'scope_bad_existing', 'not-a-date', '2023-01-01T00:00:00Z', 7, '2023-01-01T00:00:00Z', '2023-01-01T00:00:00Z')
            """
        )
        bad_existing_id = conn_d.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn_d.execute(
            """INSERT INTO sports_sync_cursor
               (provider, sport, operation, scope_key, committed_through_date, last_success_at, lock_version, created_at, updated_at)
               VALUES ('api-football', 'football', 'completed-fixture-history', 'scope_bad_candidate', '2023-01-10', '2023-01-02T00:00:00Z', 11, '2023-01-02T00:00:00Z', '2023-01-02T00:00:00Z')
            """
        )
        bad_candidate_id = conn_d.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn_d.commit()

        before_existing = conn_d.execute("SELECT * FROM sports_sync_cursor WHERE id = ?", (bad_existing_id,)).fetchone()
        with pytest.raises(CursorCorruptionError, match="CURSOR_CORRUPTION"):
            engine_d.transition_cursor(bad_existing_id, "2023-01-05", "2023-01-06T00:00:00Z")
        after_existing = conn_d.execute("SELECT * FROM sports_sync_cursor WHERE id = ?", (bad_existing_id,)).fetchone()
        assert after_existing == before_existing

        before_candidate = conn_d.execute("SELECT * FROM sports_sync_cursor WHERE id = ?", (bad_candidate_id,)).fetchone()
        with pytest.raises(CursorCorruptionError, match="CURSOR_CORRUPTION"):
            engine_d.transition_cursor(bad_candidate_id, "bad-date", "2023-01-06T00:00:00Z")
        after_candidate = conn_d.execute("SELECT * FROM sports_sync_cursor WHERE id = ?", (bad_candidate_id,)).fetchone()
        assert after_candidate == before_candidate
    finally:
        conn_d.close()
