# ruff: noqa: E501
import json
import sqlite3
from datetime import UTC, datetime

import pytest

from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    BuildSnapshotCommand,
    InspectCommand,
)
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService
from bet.enrichment.football.sync import FootballSyncEngine


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    conn.execute("INSERT INTO sports (id, name, tier) VALUES (1, 'football', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (1, 'Home', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (2, 'Away', 1)")
    conn.execute("INSERT INTO teams (id, name, sport_id) VALUES (3, 'Other', 1)")
    yield conn
    conn.close()

def test_point_in_time_windows_and_deterministic_drift(db_conn, tmp_path):
    import os
    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(tmp_path)

    try:
        from bet.integration.evidence import EvidenceRef, write_bundle_manifest

        from bet.integration.telemetry_wrapper import TransportResult
        from bet.integration.evidence import persist_response_evidence
        resp = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b"{\"response\":[]}"
        )
        ref_disc_raw = persist_response_evidence(
            operation="history_discovery",
            url="http://dummy",
            params={"fixture": "101"},
            response=resp,
            source_event_id="evt_1"
        )
        # Force captured_at to the exact date
        from dataclasses import replace
        ref_disc = replace(ref_disc_raw, captured_at="2023-01-01T12:00:00.000000Z")

        b_id1, _ = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="api-football-team-facts-v1",
            canonical_fixture_id=101,
            parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:F101"],
            evidence_refs=[ref_disc],
        )

        b_id2, _ = write_bundle_manifest(
            registered_source_key="api-football",
            projection_name="api-football-team-facts-v1",
            canonical_fixture_id=102,
            parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:F102"],
            evidence_refs=[ref_disc],
        )

        # Insert target fixture (ID 100)
        db_conn.execute("""INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at)
                           VALUES (100, 1, 1, 2, '2023-05-01T12:00:00Z', 'scheduled', '2023-05-01T00:00:00Z')""")
        db_conn.execute("""INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (100, 'api-football', 'F100', 1.0, '2023-05-01')""")

        # Active team mappings
        db_conn.execute("""INSERT INTO sports_entity (id, sport, entity_type, domain_table, domain_entity_id, created_at)
                           VALUES (10, 'football', 'TEAM', 'teams', 1, '2023')""")
        db_conn.execute("""INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method)
                           VALUES ('football', 'TEAM', 10, 'api-football', 'P1', '2023', 'VERIFIED', 'automatic')""")
        db_conn.execute("""INSERT INTO sports_entity (id, sport, entity_type, domain_table, domain_entity_id, created_at)
                           VALUES (20, 'football', 'TEAM', 'teams', 2, '2023')""")
        db_conn.execute("""INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method)
                           VALUES ('football', 'TEAM', 20, 'api-football', 'P2', '2023', 'VERIFIED', 'automatic')""")

        # Also require EVENT sports_entity for target fixture 100!
        db_conn.execute("""INSERT INTO sports_entity (id, sport, entity_type, domain_table, domain_entity_id, created_at)
                           VALUES (1000, 'football', 'EVENT', 'fixtures', 100, '2023')""")
        db_conn.execute("""INSERT INTO source_entity_reference (sport, entity_type, canonical_entity_id, provider, provider_entity_id, valid_from, verification_status, verification_method)
                           VALUES ('football', 'EVENT', 1000, 'api-football', 'F100', '2023', 'VERIFIED', 'automatic')""")

        # 1. Historical finished fixture before cutoff (observed before cutoff) -> should be included!
        db_conn.execute("""INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at)
                           VALUES (101, 1, 1, 3, '2023-04-10T12:00:00Z', 'finished', '2023-04-10T00:00:00Z')""")
        db_conn.execute("""INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (101, 'api-football', 'F101', 1.0, '2023-05-01')""")
        payload1 = {
            "provider_fixture_id": "F101", "provider_team_id": "P1", "provider_opponent_team_id": "P3", "side": "HOME",
            "goals": 2, "shots": 10, "shots_on_target": 5, "possession_pct": 50.0, "fouls": 12, "yellow_cards": 1, "red_cards": 0, "offsides": 1, "corners": 4, "goalkeeper_saves": 3,
            "available_metrics": ["corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"],
            "missing_metrics": [], "completeness": "COMPLETE"
        }
        db_conn.execute(
            """INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, status, observed_at, valid_at, logical_identity, payload_json, native_team_id, native_fixture_id, request_identity, evidence_bundle_id)
               VALUES (101, 1, 'TEAM_MATCH_FACTS', 'api-football', 'SUCCESS', '2023-04-11T12:00:00Z', '2023-04-10T12:00:00Z', 'log1', ?, 'P1', 'F101', 'req', ?)""",
            (json.dumps(payload1), b_id1)
        )

        # 2. Historical finished fixture (observed AFTER cutoff) -> should be excluded!
        db_conn.execute("""INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, status, fetched_at)
                           VALUES (102, 1, 1, 3, '2023-04-20T12:00:00Z', 'finished', '2023-04-20T00:00:00Z')""")
        db_conn.execute("""INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) VALUES (102, 'api-football', 'F102', 1.0, '2023-05-01')""")
        payload2 = {
            "provider_fixture_id": "F102", "provider_team_id": "P1", "provider_opponent_team_id": "P3", "side": "HOME",
            "goals": 4, "shots": 10, "shots_on_target": 5, "possession_pct": 50.0, "fouls": 12, "yellow_cards": 1, "red_cards": 0, "offsides": 1, "corners": 4, "goalkeeper_saves": 3,
            "available_metrics": ["corners", "fouls", "goalkeeper_saves", "offsides", "possession_pct", "red_cards", "shots", "shots_on_target", "yellow_cards"],
            "missing_metrics": [], "completeness": "COMPLETE"
        }
        db_conn.execute(
            """INSERT INTO fixture_capability_observation (canonical_fixture_id, team_id, capability, source, status, observed_at, valid_at, logical_identity, payload_json, native_team_id, native_fixture_id, request_identity, evidence_bundle_id)
               VALUES (102, 1, 'TEAM_MATCH_FACTS', 'api-football', 'SUCCESS', '2023-05-02T12:00:00Z', '2023-04-20T12:00:00Z', 'log2', ?, 'P1', 'F102', 'req', ?)""",
            (json.dumps(payload2), b_id2)
        )

        sync = FootballSyncEngine(db_conn)
        repo = FootballHistoryRepository(db_conn)
        service = FootballHistoryService(db_conn, None, sync, repo)

        cutoff = datetime(2023, 5, 1, tzinfo=UTC)
        cmd = BuildSnapshotCommand(
            canonical_target_fixture_id=100,
            analysis_cutoff_at=cutoff,
            policy_version="v1"
        )

        # Run Build Snapshot
        res = service.build_snapshot(cmd)
        assert res.snapshot_hash is not None
        assert len(res.snapshot_hash) == 64
        assert res.snapshot_hash.islower()

        # Verify DB row
        row = db_conn.execute("SELECT snapshot_hash, run_id FROM analysis_snapshot WHERE id = ?", (res.snapshot_id,)).fetchone()
        assert row is not None
        assert row[0] == res.snapshot_hash

        # Deterministic drift test
        db_conn.execute("UPDATE analysis_snapshot SET snapshot_hash = 'different_hash_to_trigger_drift_check_failure_value' WHERE run_id = ?", (res.run_id,))

        with pytest.raises(ValueError, match="DETERMINISTIC_DRIFT"):
            service.build_snapshot(cmd)

    finally:
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)


def test_inspect_fixture_and_team(db_conn):
    sync = FootballSyncEngine(db_conn)
    repo = FootballHistoryRepository(db_conn)
    service = FootballHistoryService(db_conn, None, sync, repo)

    # 1. Inspect non-existent fixture
    res1 = service.inspect_fixture(InspectCommand(fixture_id=999, team_id=None))
    assert res1.status == "NOT_FOUND"

    # 2. Inspect non-existent team
    res2 = service.inspect_team(InspectCommand(fixture_id=None, team_id=999))
    assert res2.status == "NOT_FOUND"
