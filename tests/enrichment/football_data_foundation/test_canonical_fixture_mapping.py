from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from bet.enrichment.football_data_foundation.temp_sqlite_harness import (
    create_temp_sqlite_store,
    get_table_counts,
)
from bet.enrichment.football_data_foundation.canonical_fixture_resolver import (
    resolve_canonical_fixture,
    CanonicalFixtureResolutionRequest,
    CanonicalFixtureResolutionResult,
    table_exists,
)
from bet.enrichment.football_data_foundation.canonical_observation_writer import (
    write_enrichment_observations,
    ObservationWriteResult,
)
from bet.enrichment.football_data_foundation.scanner_contracts import ScannerEventCandidate
from bet.enrichment.football_data_foundation.scanner_bridge import ScannerEnrichmentRunRecord
from bet.enrichment.football_data_foundation.persistence_bridge import (
    PersistedEnrichmentFact,
    PersistedCompletenessState,
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
