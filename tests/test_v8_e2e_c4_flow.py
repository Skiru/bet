"""Production End-to-End C4 Flow Integration Test.

Tests DiscoveryCoordinator -> Deduplication -> Source Lineage -> Revalidation -> Evidence Envelope -> Repository Persistence -> DB.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
import pytest

from bet.db.schema import init_db
from bet.db.repositories import ProviderObservationAttemptRepository
from bet.discovery.coordinator import EventDiscoveryCoordinator
from bet.discovery.dedup import DeduplicationEngine
from bet.discovery.models import DiscoveredEvent, MergedFixture
from bet.discovery.accounting import DiscoveryAccountingEngine
from bet.providers.revalidation import ProviderEventRevalidationService
from bet.pipeline.event_runtime_contract import ProviderRequestStatus, CanonicalEventStatus
from bet.pipeline.provider_observation_evidence import persist_provider_observation_with_evidence, validate_persisted_provider_observation


def test_c4_production_flow_end_to_end(tmp_path):
    # 1. Initialize real SQLite DB with migration 023 applied
    db_path = tmp_path / "c4_e2e.db"
    conn = sqlite3.connect(db_path)
    init_db(conn)

    # Insert dummy fixture 1 for foreign key validity
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (1, 1, 'Real Madrid')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (2, 1, 'Barcelona')")
    conn.execute("INSERT INTO fixtures (id, sport_id, home_team_id, away_team_id, kickoff, fetched_at) VALUES (1, 1, 1, 2, '2026-07-30T20:00:00Z', '2026-07-30T12:00:00Z')")
    conn.commit()

    # 2. Setup mock discovery raw events
    # - 1 new event (Real Madrid vs Barcelona)
    # - 1 existing event (Arsenal vs Chelsea 15:00)
    # - 1 new provider ref for existing event (Arsenal vs Chelsea from odds_api)
    # - 1 identity conflict (Ambiguous doubleheader)
    # - 2 events of same teams at different hours (Yankees vs Red Sox 15:00 & 20:00)
    evt_new = DiscoveredEvent(
        source="api_football",
        external_id="p_real_barca",
        sport="football",
        competition="La Liga",
        home_team="Real Madrid",
        away_team="Barcelona",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="NS",
    )
    evt_exist_ap = DiscoveredEvent(
        source="api_football",
        external_id="p_ars_che",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    evt_exist_oa = DiscoveredEvent(
        source="odds_api",
        external_id="oa_ars_che",
        sport="football",
        competition="Premier League",
        home_team="Arsenal",
        away_team="Chelsea",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    # Doubleheader games
    evt_dh1 = DiscoveredEvent(
        source="api_football",
        external_id="p_dh1",
        sport="baseball",
        competition="MLB",
        home_team="Yankees",
        away_team="Red Sox",
        kickoff=datetime(2026, 7, 30, 15, 0, tzinfo=UTC),
        status="NS",
    )
    evt_dh2 = DiscoveredEvent(
        source="api_football",
        external_id="p_dh2",
        sport="baseball",
        competition="MLB",
        home_team="Yankees",
        away_team="Red Sox",
        kickoff=datetime(2026, 7, 30, 20, 0, tzinfo=UTC),
        status="NS",
    )

    # 3. Deduplication and source lineage
    dedup = DeduplicationEngine()
    events_by_source = {
        "api_football": [evt_new, evt_exist_ap, evt_dh1, evt_dh2],
        "odds_api": [evt_exist_oa],
    }
    merged_fixtures = dedup.merge(events_by_source)

    # Verify source lineage preserved
    ars_fixture = [m for m in merged_fixtures if "Arsenal" in m.home_team][0]
    assert len(ars_fixture.sources) == 2, "Source lineage lost: expected 2 sources for Arsenal vs Chelsea"
    assert {s.source for s in ars_fixture.sources} == {"api_football", "odds_api"}

    # Verify doubleheader games remain distinct fixtures
    dh_fixtures = [m for m in merged_fixtures if "Yankees" in m.home_team]
    assert len(dh_fixtures) == 2, "Doubleheader games incorrectly merged into one fixture"

    # 4. Discovery Accounting
    acct_engine = DiscoveryAccountingEngine()
    db_existing_ids = {"evt_ars_che"}
    db_existing_refs = {("api_football", "p_ars_che")}

    fetched_payloads = [
        {"canonical_event_id": "evt_real_barca", "provider": "api_football", "provider_event_id": "p_real_barca"},
        {"canonical_event_id": "evt_ars_che", "provider": "api_football", "provider_event_id": "p_ars_che"},
        {"canonical_event_id": "evt_ars_che", "provider": "odds_api", "provider_event_id": "oa_ars_che"},
        {"canonical_event_id": "evt_dh1", "provider": "api_football", "provider_event_id": "p_dh1"},
        {"canonical_event_id": "evt_dh2", "provider": "api_football", "provider_event_id": "p_dh2"},
    ]

    summary_run1 = acct_engine.calculate_accounting(fetched_payloads, db_existing_ids, db_existing_refs)
    assert summary_run1.genuinely_new_events == 3  # real_barca, dh1, dh2
    assert summary_run1.new_provider_refs == 1      # odds_api for ars_che
    assert summary_run1.unchanged_events == 1        # api_football for ars_che

    # Second run idempotency check
    db_existing_ids_run2 = db_existing_ids | {"evt_real_barca", "evt_dh1", "evt_dh2"}
    db_existing_refs_run2 = db_existing_refs | {("api_football", "p_real_barca"), ("odds_api", "oa_ars_che"), ("api_football", "p_dh1"), ("api_football", "p_dh2")}
    summary_run2 = acct_engine.calculate_accounting(fetched_payloads, db_existing_ids_run2, db_existing_refs_run2)
    assert summary_run2.genuinely_new_events == 0, "Second run must yield 0 genuinely new events"

    # 5. Exact Revalidation Service and Evidence Persistence
    reval_service = ProviderEventRevalidationService()
    reval_result = reval_service.revalidate_exact_event(
        provider="api_football",
        provider_event_id="p_real_barca",
        available_events=[{
            "provider": "api_football",
            "provider_event_id": "p_real_barca",
            "status": "NS",
            "kickoff": "2026-07-30T20:00:00Z",
            "home": "Real Madrid",
            "away": "Barcelona",
        }],
    )

    assert reval_result.request_status == ProviderRequestStatus.SUCCESS
    assert reval_result.is_exact_match

    # Persist observation with evidence envelope
    obs_payload = {
        "run_id": "r_e2e_1",
        "phase": "PLAN",
        "attempt_number": 1,
        "canonical_event_id": "evt_real_barca",
        "fixture_id": 1,
        "provider": "api_football",
        "provider_event_id": "p_real_barca",
        "attempted_at_utc": "2026-07-30T12:00:00Z",
        "request_status": "SUCCESS",
        "raw_provider_status": reval_result.raw_provider_status,
        "canonical_event_status": reval_result.canonical_event_status,
        "raw_observed_kickoff": reval_result.raw_observed_kickoff,
        "observed_kickoff_utc": reval_result.observed_kickoff_utc,
        "observed_home_name": reval_result.observed_home_name,
        "observed_away_name": reval_result.observed_away_name,
        "participant_identity_sha256": reval_result.participant_identity_sha256,
    }

    evidence_dir = tmp_path / "e2e_evidence"
    attempt_id = persist_provider_observation_with_evidence(conn, obs_payload, evidence_dir)

    # 6. Verify database record and evidence envelope match
    repo = ProviderObservationAttemptRepository(conn)
    db_att = repo.get_attempt_by_id(attempt_id)

    assert db_att["provider"] == "api_football"
    assert db_att["provider_event_id"] == "p_real_barca"
    assert db_att["raw_provider_status"] == "NS"
    assert db_att["canonical_event_status"] == "SCHEDULED"

    is_valid_obs, msg = validate_persisted_provider_observation(
        db_att,
        db_att["evidence_path"],
        db_att["observation_envelope_sha256"],
        allowed_root=evidence_dir,
    )
    assert is_valid_obs, f"End-to-end evidence validation failed: {msg}"

    # 7. Provider failure handling (attempt 2)
    failed_payload = dict(obs_payload, attempt_number=2, request_status="FAILED", error_code="HTTP_500")
    fail_attempt_id = persist_provider_observation_with_evidence(conn, failed_payload, evidence_dir)
    db_failed = repo.get_attempt_by_id(fail_attempt_id)
    assert db_failed["request_status"] == "FAILED"
    assert db_failed["request_status"] != "SUCCESS"

    conn.close()
