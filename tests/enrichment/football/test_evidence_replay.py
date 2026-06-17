# ruff: noqa: E501
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.enrichment.football.contracts import (
    AcquisitionMode,
    BatchIdsCapability,
)
from bet.enrichment.football.replay import EvidenceReplayAcquirer
from bet.integration.evidence import (
    persist_response_evidence,
    write_bundle_manifest,
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
        assert fix.observed_at == datetime(2023, 1, 1, 15, 30, tzinfo=UTC)
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


def test_object_sha_rejected_when_used_as_bundle_id(temp_evidence_root):
    import os

    from bet.integration.evidence import load_bundle_manifest, persist_response_evidence
    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(temp_evidence_root)
    try:
        response_disc = TransportResult(
            success=True,
            status_code=200,
            headers={"Content-Type": "application/json"},
            body=b'{"response":[]}'
        )
        ref = persist_response_evidence(
            operation="history_discovery",
            url="https://v3.football.api-sports.io/fixtures",
            params={"league": "39", "season": "2023"},
            response=response_disc,
        )
        object_sha = ref.object_sha256
        with pytest.raises(FileNotFoundError):
            load_bundle_manifest(object_sha)
    finally:
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)


def test_mixed_replay_scopes_rejected(temp_evidence_root):
    import os

    from bet.enrichment.football.replay import EvidenceReplayAcquirer
    from bet.integration.evidence import (
        persist_response_evidence,
        write_bundle_manifest,
    )
    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(temp_evidence_root)
    try:
        resp1 = TransportResult(
            success=True, status_code=200, body=json.dumps({"response": [
                {"fixture": {"id": 101, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                 "league": {"id": 39, "name": "EPL", "season": 2023},
                 "teams": {"home": {"id": 1, "name": "A"}, "away": {"id": 2, "name": "B"}},
                 "goals": {"home": 1, "away": 0}, "score": {"penalty": {"home": None, "away": None}}}
            ]}).encode("utf-8")
        )
        ref1 = persist_response_evidence(operation="history_discovery", url="http://x", params=None, response=resp1)
        b1, _ = write_bundle_manifest(
            registered_source_key="api-football", projection_name="TEAM_MATCH_FACTS",
            canonical_fixture_id=1, parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:101"], evidence_refs=[ref1]
        )

        resp2 = TransportResult(
            success=True, status_code=200, body=json.dumps({"response": [
                {"fixture": {"id": 102, "status": {"short": "FT"}, "date": "2023-01-01T12:00:00Z"},
                 "league": {"id": 140, "name": "La Liga", "season": 2023},
                 "teams": {"home": {"id": 3, "name": "C"}, "away": {"id": 4, "name": "D"}},
                 "goals": {"home": 1, "away": 0}, "score": {"penalty": {"home": None, "away": None}}}
            ]}).encode("utf-8")
        )
        ref2 = persist_response_evidence(operation="history_discovery", url="http://y", params=None, response=resp2)
        b2, _ = write_bundle_manifest(
            registered_source_key="api-football", projection_name="TEAM_MATCH_FACTS",
            canonical_fixture_id=2, parser_version="api-football-team-facts-v1",
            source_event_refs=["api-football:102"], evidence_refs=[ref2]
        )

        acq = EvidenceReplayAcquirer(bundle_ids=(b1, b2))
        with pytest.raises(ValueError, match="ReplayCommand contains mixed scope identities"):
            acq.acquire(
                competition_provider_id="", season=0, from_date=None, to_date=None,
                max_fixtures=100, max_fallback_stats_calls=0, attempt_budget=None,
                ids_capability=BatchIdsCapability.UNKNOWN
            )
    finally:
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)


def test_persistence_order_manifests_observations_and_replay_scenarios(temp_evidence_root):
    import sqlite3

    from bet.db.schema import init_db
    db_conn = sqlite3.connect(":memory:")
    db_conn.execute("PRAGMA foreign_keys = ON")
    init_db(db_conn)
    db_conn.execute("INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, created_at, updated_at) VALUES (1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', '2023', '2023')")
    db_conn.execute("INSERT INTO sports_sync_run (id, run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json) VALUES (1, 'run_1', 1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', 'bootstrap', '2023', '2023', 'RUNNING', '2023', '{}')")
    db_conn.execute("INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at) VALUES ('api-football', 'football', 'scope_1', '101', '2023', '2023', 'DISCOVERED', '2023', '2023')")

    import os
    from datetime import datetime

    from bet.enrichment.football.contracts import (
        AcquiredFixture,
        AcquisitionMode,
        FootballFixtureIdentity,
        FootballProviderStatus,
    )
    from bet.enrichment.football.persistence import CanonicalPersistence
    from bet.integration.evidence import (
        persist_response_evidence,
    )

    orig_env = os.environ.get("BET_EVIDENCE_ROOT")
    os.environ["BET_EVIDENCE_ROOT"] = str(temp_evidence_root)

    try:
        resp = TransportResult(
            success=True, status_code=200, body=json.dumps({"response": []}).encode("utf-8")
        )
        ref = persist_response_evidence(operation="history_discovery", url="http://x", params=None, response=resp)

        fixture_id_obj = FootballFixtureIdentity(
            provider_fixture_id="101",
            provider_competition_id="39",
            competition_name="Premier League",
            country="England",
            season=2023,
            round_name="Regular Season",
            kickoff_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC),
            provider_status=FootballProviderStatus.FT,
            canonical_status="finished",
            home_provider_team_id="10",
            away_provider_team_id="20",
            home_team_name="Home Team",
            away_team_name="Away Team",
            home_score=2,
            away_score=1,
            home_penalty_score=None,
            away_penalty_score=None,
            parser_version="api-football-team-facts-v1",
            schema_version="1"
        )

        acq = AcquiredFixture(
            fixture=fixture_id_obj,
            statistics_by_provider_team_id={},
            fixture_evidence_refs=(ref,),
            statistics_evidence_refs=(),
            observed_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=UTC),
            acquisition_mode=AcquisitionMode.DISCOVERY_ENVELOPE,
            warnings=()
        )

        pers = CanonicalPersistence(db_conn)
        res = pers.persist_acquired_fixture(acquired_fixture=acq, scope_key="scope_1", sync_run_id=1)

        local_bundle_id = res.fixture_bundle_id
        assert local_bundle_id is not None
        assert len(local_bundle_id) == 64

        obs = db_conn.execute("SELECT evidence_bundle_id, status, parser_diagnostics_json FROM fixture_capability_observation").fetchall()
        assert len(obs) == 2
        for row in obs:
            assert row[0] == local_bundle_id
            assert row[1] == "PARTIAL"
            diag = json.loads(row[2])
            assert diag.get("completeness") == "SCORE_ONLY"

        item = db_conn.execute("SELECT fixture_evidence_bundle_id, statistics_evidence_bundle_id, state FROM sports_sync_item").fetchone()
        assert item[0] == local_bundle_id
        assert item[1] == local_bundle_id
        assert item[2] == "INGESTED_SCORE_ONLY"

        db_conn2 = sqlite3.connect(":memory:")
        db_conn2.execute("PRAGMA foreign_keys = ON")
        init_db(db_conn2)
        db_conn2.execute("INSERT INTO sports_sync_cursor (id, provider, sport, operation, scope_key, created_at, updated_at) VALUES (1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', '2023', '2023')")
        db_conn2.execute("INSERT INTO sports_sync_run (id, run_identity, cursor_id, provider, sport, operation, scope_key, mode, window_from, window_to, status, started_at, cursor_before_json) VALUES (1, 'run_1', 1, 'api-football', 'football', 'completed-fixture-history', 'scope_1', 'bootstrap', '2023', '2023', 'RUNNING', '2023', '{}')")
        db_conn2.execute("INSERT INTO sports_sync_item (provider, sport, scope_key, provider_fixture_id, first_seen_at, last_checked_at, state, created_at, updated_at) VALUES ('api-football', 'football', 'scope_1', '101', '2023', '2023', 'DISCOVERED', '2023', '2023')")

        pers2 = CanonicalPersistence(db_conn2)
        acq_replay = AcquiredFixture(
            fixture=fixture_id_obj,
            statistics_by_provider_team_id={},
            fixture_evidence_refs=(ref,),
            statistics_evidence_refs=(),
            observed_at=datetime(2023, 1, 1, 15, 0, 0, tzinfo=UTC),
            acquisition_mode=AcquisitionMode.REPLAY,
            warnings=(),
            originating_bundle_id=local_bundle_id
        )

        res2 = pers2.persist_acquired_fixture(acquired_fixture=acq_replay, scope_key="scope_1", sync_run_id=1)
        assert res2.fixture_bundle_id is not None

    finally:
        db_conn.close()
        if orig_env is not None:
            os.environ["BET_EVIDENCE_ROOT"] = orig_env
        else:
            os.environ.pop("BET_EVIDENCE_ROOT", None)
