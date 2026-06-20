from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
    CanonicalFixtureResolutionRequest,
    resolve_canonical_fixture,
    table_exists,
)
from bet.enrichment.football_data_foundation.canonical_observation_writer import (
    write_enrichment_observations,
)
from bet.enrichment.football_data_foundation.enrichment_freshness import (
    EvidenceFreshnessInput,
    EvidenceFreshnessPolicy,
    evaluate_freshness,
)
from bet.enrichment.football_data_foundation.persistence_bridge import (
    PersistedCompletenessState,
    PersistedEnrichmentFact,
)
from bet.enrichment.football_data_foundation.scanner_bridge import (
    ScannerEnrichmentRunRecord,
)
from bet.enrichment.football_data_foundation.scanner_contracts import (
    ScannerEventCandidate,
)
from bet.enrichment.football_data_foundation.temp_sqlite_harness import (
    create_temp_sqlite_store,
    get_table_counts,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNER_EVENT_PATH = (
    REPO_ROOT
    / "reports/football_data_foundation/active_enrichment_profiles/world-cup-2026/scanner_event_input.json"
)
BRIDGE_RESULT_PATH = (
    REPO_ROOT
    / "reports/football_data_foundation/production_bridge/world-cup-2026/scanner_enrich_reuse_store.json"
)
REAL_DB_PATH = REPO_ROOT / "betting/data/betting.db"


def load_acceptance_scanner_event() -> ScannerEventCandidate:
    return ScannerEventCandidate.from_dict(
        json.loads(SCANNER_EVENT_PATH.read_text(encoding="utf-8"))
    )


def load_acceptance_bridge_result() -> ScannerEnrichmentRunRecord:
    data = json.loads(BRIDGE_RESULT_PATH.read_text(encoding="utf-8"))
    res_data = data["result"]
    facts = tuple(PersistedEnrichmentFact.from_dict(f) for f in res_data["facts"])
    completeness = tuple(PersistedCompletenessState.from_dict(c) for c in res_data["completeness_state"])
    return ScannerEnrichmentRunRecord(
        profile_id=res_data["profile_id"],
        scanner_event_id=res_data["scanner_event_id"],
        provider_event_id=res_data.get("provider_event_id"),
        evidence_identity=res_data.get("evidence_identity"),
        provider_event_ids=tuple(res_data["provider_event_ids"]),
        evidence_identities=tuple(res_data["evidence_identities"]),
        facts=facts,
        completeness_state=completeness,
        fetch_decisions=tuple(res_data["fetch_decisions"]),
        status=res_data["status"],
        storage_kind=res_data["storage_kind"],
        db_activation_status=res_data["db_activation_status"],
        production_betting_decision=res_data["production_betting_decision"],
        force_refresh=res_data["force_refresh"],
    )


def test_temp_sqlite_harness_initializes_cleanly_without_touching_real_db() -> None:
    # Check modification time of real database beforehand if it exists
    before_exists = REAL_DB_PATH.exists()
    before_mtime = REAL_DB_PATH.stat().st_mtime if before_exists else None

    conn = create_temp_sqlite_store()
    assert isinstance(conn, sqlite3.Connection)

    # Check tables were initialized successfully
    assert table_exists(conn, "sports")
    assert table_exists(conn, "fixtures")
    assert table_exists(conn, "fixture_sources")
    assert table_exists(conn, "sports_entity")
    assert table_exists(conn, "source_entity_reference")

    counts = get_table_counts(conn)
    assert all(count == 0 for count in counts.values())

    # Ensure real DB was not touched/created
    after_exists = REAL_DB_PATH.exists()
    after_mtime = REAL_DB_PATH.stat().st_mtime if after_exists else None
    assert after_exists == before_exists
    assert after_mtime == before_mtime


def test_resolver_creates_sport_competition_team_fixture_rows_and_mappings() -> None:
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    result = resolve_canonical_fixture(conn, request)
    assert result.status == "CREATED_CANONICAL_FIXTURE"
    assert result.sport_id is not None
    assert result.competition_id is not None
    assert result.home_team_id is not None
    assert result.away_team_id is not None
    assert result.fixture_id is not None
    assert result.sports_entity_event_id is not None
    assert len(result.fixture_source_ids) == 2
    assert len(result.source_reference_ids) == 2

    # Verify separate mappings for scanner and provider
    assert result.scanner_event_id == "66456944"
    assert result.provider_event_id == "760442"
    assert result.scanner_event_id != result.provider_event_id


def test_resolver_is_idempotent() -> None:
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    result_1 = resolve_canonical_fixture(conn, request)
    assert result_1.status == "CREATED_CANONICAL_FIXTURE"

    result_2 = resolve_canonical_fixture(conn, request)
    assert result_2.status == "MATCHED_EXISTING_FIXTURE"
    assert result_1.fixture_id == result_2.fixture_id


def test_ambiguous_fixture_match_fails_closed() -> None:
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    request_1 = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="a" * 64,
        schema_fingerprint="fingerprint-1",
    )

    # First map provider event 760442 to some fixture
    resolve_canonical_fixture(conn, request_1)

    # Now create another scanner event with the same provider_event_id 760442
    # but different scanner event ID and team names to trigger ambiguity
    modified_event = ScannerEventCandidate(
        scanner_event_id="999999",
        profile_id="world-cup-2026",
        sport="football",
        canonical_competition_scope=scanner_event.canonical_competition_scope,
        canonical_season_scope=scanner_event.canonical_season_scope,
        kickoff_local=scanner_event.kickoff_local,
        kickoff_utc=scanner_event.kickoff_utc,
        home_team_name="Different Team A",
        home_team_code="DTA",
        away_team_name="Different Team B",
        away_team_code="DTB",
        group_label=None,
        scanner_source="test_scanner",
        scanner_truth_kind="schedule_snapshot",
        scanner_confidence="high",
    )

    request_2 = CanonicalFixtureResolutionRequest(
        scanner_event=modified_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442", # Reuses same provider ID
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="b" * 64,
        schema_fingerprint="fingerprint-2",
    )

    result_2 = resolve_canonical_fixture(conn, request_2)
    assert result_2.status == "AMBIGUOUS_FIXTURE_MATCH"
    assert result_2.fixture_id is None


def test_observation_writer_populates_tables_correctly_and_is_idempotent() -> None:
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()
    bridge_result = load_acceptance_bridge_result()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    resolution = resolve_canonical_fixture(conn, request)
    analysis_cutoff_at = "2026-06-19T22:00:00Z"

    # First write
    write_1 = write_enrichment_observations(conn, resolution, bridge_result, analysis_cutoff_at)
    assert write_1.status == "SUCCESS"
    assert write_1.run_id is not None
    assert len(write_1.observation_ids) == 6
    assert len(write_1.projection_ids) == 6
    assert len(write_1.attempt_ids) == 3

    # Second write (Idempotent)
    write_2 = write_enrichment_observations(conn, resolution, bridge_result, analysis_cutoff_at)
    assert write_2.status == "SUCCESS"
    assert write_1.run_id == write_2.run_id
    assert write_1.observation_ids == write_2.observation_ids
    assert write_1.projection_ids == write_2.projection_ids


def test_no_betting_decision_tables_are_written() -> None:
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()
    bridge_result = load_acceptance_bridge_result()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    resolution = resolve_canonical_fixture(conn, request)
    write_enrichment_observations(conn, resolution, bridge_result, "2026-06-19T22:00:00Z")

    # Verify decision tables are completely empty
    decision_tables = [
        "analysis_results",
        "gate_results",
        "coupons",
        "bets",
    ]
    for table in decision_tables:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        assert cursor.fetchone()[0] == 0


def test_future_non_world_cup_profile_integration() -> None:
    # Prove that the resolver is fully generic and handles any other league/profile
    conn = create_temp_sqlite_store()
    generic_event = ScannerEventCandidate(
        scanner_event_id="epl-8899",
        profile_id="epl-2024",
        sport="football",
        canonical_competition_scope="football:eng.1",
        canonical_season_scope="2024",
        kickoff_local="2024-08-17T15:00:00+01:00",
        kickoff_utc="2024-08-17T14:00:00Z",
        home_team_name="Man City",
        home_team_code="MCI",
        away_team_name="Ipswich Town",
        away_team_code="IPS",
        group_label=None,
        scanner_source="generic_scanner",
        scanner_truth_kind="schedule_snapshot",
        scanner_confidence="high",
    )

    request = CanonicalFixtureResolutionRequest(
        scanner_event=generic_event,
        provider_id="soccerdata-epl",
        provider_event_id="epl-990022",
        profile_id="epl-2024",
        competition_scope=generic_event.canonical_competition_scope,
        season_scope=generic_event.canonical_season_scope,
        evidence_identity="generic_evidence_hash",
        schema_fingerprint="generic_fingerprint",
    )

    result = resolve_canonical_fixture(conn, request)
    assert result.status == "CREATED_CANONICAL_FIXTURE"
    assert result.fixture_id is not None
    assert result.home_team_id is not None
    assert result.away_team_id is not None


# Tightened A5C1 Hardening Tests

def test_source_external_id_conflict_handling() -> None:
    """Validate that resolving a fixture with mismatched external_id returns conflict."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    # Insert parent rows to satisfy foreign keys
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute("INSERT INTO competitions (id, sport_id, name, season) VALUES (1, 1, 'comp-1', '2026')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (1, 1, 'United States')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (2, 1, 'Australia')")

    # Insert existing mapping
    cursor = conn.execute(
        "INSERT INTO fixtures (id, sport_id, competition_id, home_team_id, away_team_id, kickoff, status, fetched_at) "
        "VALUES (10, 1, 1, 1, 2, ?, 'scheduled', 'now')",
        (scanner_event.kickoff_utc,),
    )

    # Store conflicting fixture_source
    conn.execute(
        "INSERT INTO fixture_sources (fixture_id, source, external_id, confidence, fetched_at) "
        "VALUES (10, 'espn-fifa-worldcup', 'wrong_external_id', 1.0, 'now')",
    )

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="evidence-1",
        schema_fingerprint="fingerprint-1",
    )

    result = resolve_canonical_fixture(conn, request)
    assert result.status == "SOURCE_EXTERNAL_ID_CONFLICT"
    assert result.fixture_id is None


def test_team_alias_ambiguity_fails_closed() -> None:
    """Validate that team alias lookup ambiguity returns TEAM_ALIAS_AMBIGUOUS."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    # Insert parents with different canonical names
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (101, 1, 'Canonical Team USA')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (202, 1, 'Canonical Team Australia')")

    # Insert duplicate aliases for 'United States'
    conn.execute(
        "INSERT INTO team_source_aliases (team_id, sport_id, source, provider_team_name, status) "
        "VALUES (101, 1, 'espn-fifa-worldcup', 'United States', 'verified')",
    )
    conn.execute(
        "INSERT INTO team_source_aliases (team_id, sport_id, source, provider_team_name, status) "
        "VALUES (202, 1, 'espn-fifa-worldcup', 'United States', 'verified')",
    )

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="evidence-1",
        schema_fingerprint="fingerprint-1",
    )

    result = resolve_canonical_fixture(conn, request)
    assert result.status == "TEAM_ALIAS_AMBIGUOUS"


def test_competition_country_does_not_store_group_label() -> None:
    """Verify that competition.country stores country or null, never group label."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()
    # Confirm group_label starts with 'Group ' (e.g. Group D)
    assert scanner_event.group_label == "Group D"

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="evidence-1",
        schema_fingerprint="fingerprint-1",
    )

    result = resolve_canonical_fixture(conn, request)
    assert result.status == "CREATED_CANONICAL_FIXTURE"

    cursor = conn.execute("SELECT country FROM competitions WHERE id = ?", (result.competition_id,))
    country = cursor.fetchone()[0]
    # Should be None (null), not Group D
    assert country is None


class MockConnection:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, sql, *args):
        if "FROM fixtures" in sql and "home_team_id = ?" in sql:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [(10, 1), (20, 2)]
            return mock_cursor
        return self.conn.execute(sql, *args)
    def commit(self):
        self.conn.commit()
    def rollback(self):
        self.conn.rollback()
    def close(self):
        self.conn.close()


def test_natural_fixture_conflict_across_competition_returns_ambiguity() -> None:
    """Verify natural unique fixture conflicts map to AMBIGUOUS_FIXTURE_MATCH."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()

    mock_conn = MockConnection(conn)

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="evidence-1",
        schema_fingerprint="fingerprint-1",
    )

    result = resolve_canonical_fixture(mock_conn, request) # type: ignore
    assert result.status == "AMBIGUOUS_FIXTURE_MATCH"
    assert result.fixture_id is None


def test_fact_scoping_and_duplication_flagging() -> None:
    """Verify fixture-level facts are explicitly scoped and marked duplicated."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()
    bridge_result = load_acceptance_bridge_result()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    res = resolve_canonical_fixture(conn, request)
    write_res = write_enrichment_observations(conn, res, bridge_result, "2026-06-19T22:00:00Z")
    assert write_res.status == "SUCCESS"

    # Read observation payloads
    cursor = conn.execute("SELECT payload_json FROM fixture_capability_observation")
    payloads = [json.loads(row[0]) for row in cursor.fetchall()]

    # Verify each payload has explicit fact scopes and duplication flag
    for payload in payloads:
        assert "fact_scopes" in payload
        assert "duplicated_for_schema_team_id_constraint" in payload
        # Ensure correct scopes
        scopes = payload["fact_scopes"]
        for fact_name, scope in scopes.items():
            assert scope in ("TEAM_HOME", "TEAM_AWAY", "FIXTURE_LEVEL", "UNKNOWN")


def test_evidence_package_revision_member_count() -> None:
    """Verify member_count corresponds strictly to facts of that evidence_identity."""
    conn = create_temp_sqlite_store()
    scanner_event = load_acceptance_scanner_event()
    bridge_result = load_acceptance_bridge_result()

    request = CanonicalFixtureResolutionRequest(
        scanner_event=scanner_event,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        profile_id="world-cup-2026",
        competition_scope=scanner_event.canonical_competition_scope,
        season_scope=scanner_event.canonical_season_scope,
        evidence_identity="1f8cdb0748846c1cec8b312ad47f5607b116e3c17a56eb32a8f0ac6f537c73b0",
        schema_fingerprint="1adbcb1991fbe027d188ffc1f3241a1a555f26d209df871e6c58c36d47828839",
    )

    res = resolve_canonical_fixture(conn, request)
    write_enrichment_observations(conn, res, bridge_result, "2026-06-19T22:00:00Z")

    # Check member counts
    cursor = conn.execute("SELECT package_id, member_count FROM evidence_package_revision")
    rows = cursor.fetchall()
    for pkg_id, count in rows:
        # Pkg facts count from bridge_result should match member_count
        hash_seed = pkg_id[4:] # strip pkg_
        pkg_facts_count = len([f for f in bridge_result.facts if f.evidence_identity == hash_seed])
        assert count == pkg_facts_count


def test_live_to_final_status_drift() -> None:
    """Validate live-to-final drift evaluates to STATUS_DRIFT_REFRESH_REQUIRED."""
    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME",),
        status_sensitive=True,
    )

    # Cached matches in-progress (STATUS_SECOND_HALF) but live is final (STATUS_FULL_TIME)
    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        scanner_event_id="66456944",
        evidence_retrieved_at="2026-06-20T06:00:00Z",
        evidence_event_status_state="in",
        evidence_event_status_name="STATUS_SECOND_HALF",
        current_event_status_state="post",
        current_event_status_name="STATUS_FULL_TIME",
        now_utc="2026-06-20T06:01:00Z",
    )

    decision = evaluate_freshness(policy, input_data)
    assert decision.decision == "STATUS_DRIFT_REFRESH_REQUIRED"
    assert decision.must_refresh is True


def test_stale_status_sensitive_evidence_cannot_be_reused_blindly() -> None:
    """Verify expired TTL status-sensitive evidence requires refresh."""
    policy = EvidenceFreshnessPolicy(
        capability="current_discovery",
        ttl_seconds_pre_match=300,
        ttl_seconds_live=60,
        ttl_seconds_post_final=86400,
        final_state_locks=("STATUS_FULL_TIME",),
        status_sensitive=True,
    )

    input_data = EvidenceFreshnessInput(
        profile_id="world-cup-2026",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        scanner_event_id="66456944",
        evidence_retrieved_at="2026-06-20T06:00:00Z",
        evidence_event_status_state="pre",
        evidence_event_status_name="STATUS_SCHEDULED",
        current_event_status_state="pre",
        current_event_status_name="STATUS_SCHEDULED",
        now_utc="2026-06-20T06:10:00Z", # 10 minutes later (exceeds pre TTL 300s)
    )

    decision = evaluate_freshness(policy, input_data)
    assert decision.decision == "STALE_REFRESH_REQUIRED"
    assert decision.must_refresh is True
