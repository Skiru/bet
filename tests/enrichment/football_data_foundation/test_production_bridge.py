from __future__ import annotations

import json
from pathlib import Path

from bet.enrichment.football_data_foundation.enrichment_state import (
    EnrichmentCompletenessRecord,
)
from bet.enrichment.football_data_foundation.persistence_bridge import (
    InMemoryProductionEnrichmentStore,
    PersistedCompletenessState,
    PersistedEnrichmentEvidence,
    PersistedEnrichmentFact,
    PersistedScannerEvent,
    ProductionStoreStateAdapter,
    seed_store_from_a3c1_state,
    summarize_db_schema_discovery,
)
from bet.enrichment.football_data_foundation.scanner_bridge import (
    run_scanner_batch_enrichment,
    run_scanner_event_enrichment,
    scanner_batch_from_events,
)
from bet.enrichment.football_data_foundation.scanner_contracts import (
    ScannerEventCandidate,
)
from bet.integration.source_result import SourceResultStatus

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILE_ROOT = (
    REPO_ROOT
    / "tests/fixtures/football_data_foundation/active_enrichment_profiles/world-cup-2026"
)
SCANNER_EVENT_PATH = PROFILE_ROOT / "scanner_event_input.json"
REAL_DB_PATH = REPO_ROOT / "betting/data/betting.db"


def load_scanner_event() -> ScannerEventCandidate:
    return ScannerEventCandidate.from_dict(
        json.loads(SCANNER_EVENT_PATH.read_text(encoding="utf-8"))
    )


def build_generic_profile_scanner_event() -> ScannerEventCandidate:
    return ScannerEventCandidate(
        scanner_event_id="example-1001",
        profile_id="example-football-league-profile",
        sport="football",
        canonical_competition_scope="football:eng.1",
        canonical_season_scope="2024",
        kickoff_local="2024-08-16T20:00:00+01:00",
        kickoff_utc="2024-08-16T19:00:00Z",
        home_team_name="Arsenal",
        home_team_code="ARS",
        away_team_name="Chelsea",
        away_team_code="CHE",
        group_label=None,
        scanner_source="test_scanner",
        scanner_truth_kind="schedule_snapshot",
        scanner_confidence="high",
    )


def seed_generic_cached_evidence(
    store: InMemoryProductionEnrichmentStore, scanner_event: ScannerEventCandidate
) -> None:
    adapter = ProductionStoreStateAdapter(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
    )
    evidence_identity = "a" * 64
    adapter.put_evidence(
        evidence_identity,
        {
            "provider_id": "espn-epl",
            "provider_event_id": "epl-4455",
            "capability": "current_discovery",
            "schema_fingerprint": "schema-example-1",
            "retrieved_at": "2024-08-16T18:30:00+00:00",
            "event": {
                "provider_event_id": "epl-4455",
                "event_date_utc": "2024-08-16T19:00:00Z",
                "event_date_local": "2024-08-16T20:00:00+01:00",
                "home_team_name": "Arsenal",
                "home_team_code": "ARS",
                "away_team_name": "Chelsea",
                "away_team_code": "CHE",
                "status_name": "STATUS_SCHEDULED",
                "status_state": "pre",
                "venue_name": "Emirates Stadium",
                "venue_city": "London",
                "score_home": None,
                "score_away": None,
                "broadcasts": ["Sky Sports"],
                "retrieval_timestamp_utc": "2024-08-16T18:30:00+00:00",
            },
        },
    )
    store.upsert_completeness(
        PersistedCompletenessState.from_enrichment_record(
            EnrichmentCompletenessRecord(
                profile_id=scanner_event.profile_id,
                canonical_entity_id=scanner_event.scanner_event_id,
                entity_type="fixture",
                capability="current_discovery",
                provider_id="espn-epl",
                evidence_identity=evidence_identity,
                schema_fingerprint="schema-example-1",
                last_verified_at="2024-08-16T18:30:00+00:00",
                last_enriched_at="2024-08-16T18:30:00+00:00",
                completeness_status="COMPLETE_FRESH",
            ),
            scanner_event_id=scanner_event.scanner_event_id,
        )
    )


def test_inmemory_store_persists_scanner_evidence_facts_and_completeness() -> None:
    store = InMemoryProductionEnrichmentStore()
    scanner_event = load_scanner_event()
    store.upsert_scanner_event(PersistedScannerEvent.from_candidate(scanner_event))
    assert store.get_scanner_event(scanner_event.scanner_event_id) is not None

    evidence = PersistedEnrichmentEvidence(
        evidence_identity="b" * 64,
        profile_id=scanner_event.profile_id,
        provider_id="espn-fifa-worldcup",
        provider_event_id="760442",
        scanner_event_id=scanner_event.scanner_event_id,
        capability="current_discovery",
        schema_fingerprint="schema-1",
        retrieved_at="2026-06-19T20:18:51+00:00",
        source_truth_kind="provider_verified_payload",
        storage_ref="memory://evidence/test.json",
    )
    store.upsert_evidence(evidence)
    assert store.get_evidence(evidence.evidence_identity) == evidence

    fact = PersistedEnrichmentFact(
        fact_id="fact-1",
        evidence_identity=evidence.evidence_identity,
        scanner_event_id=scanner_event.scanner_event_id,
        provider_event_id="760442",
        profile_id=scanner_event.profile_id,
        capability="current_discovery",
        fact_name="event_status_state",
        fact_value_num=None,
        fact_value_text="in",
        source_consensus="single_source_verified",
        schema_fingerprint="schema-1",
        created_at="2026-06-19T20:18:51+00:00",
    )
    store.upsert_fact(fact)
    assert store.list_facts(scanner_event.scanner_event_id) == (fact,)

    completeness = PersistedCompletenessState(
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        entity_type="fixture",
        capability="current_discovery",
        provider_id="espn-fifa-worldcup",
        completeness_status="COMPLETE_FRESH",
        evidence_identity=evidence.evidence_identity,
        schema_fingerprint="schema-1",
        last_verified_at="2026-06-19T20:18:51+00:00",
        last_enriched_at="2026-06-19T20:18:51+00:00",
    )
    store.upsert_completeness(completeness)
    assert (
        store.get_completeness(
            scanner_event.profile_id,
            scanner_event.scanner_event_id,
            "current_discovery",
        )
        == completeness
    )


def test_empty_store_fails_closed_with_zero_facts() -> None:
    scanner_event = load_scanner_event()
    result = run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        InMemoryProductionEnrichmentStore(),
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
    )
    assert result.status == SourceResultStatus.EVIDENCE_ERROR
    assert result.error_code == "fetch_required"
    assert result.value is not None
    assert result.value.status == "ENRICH_FAILED_CLOSED"
    assert result.value.facts == ()


def test_seeded_store_returns_real_facts_with_separate_scanner_and_provider_ids(
) -> None:
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    result = run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
    )
    assert result.status == SourceResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.status == "ENRICHED_COMPLETE"
    assert result.value.scanner_event_id == "66456944"
    assert result.value.provider_event_id == "760442"
    assert result.value.provider_event_id != result.value.scanner_event_id
    assert all(fact.provider_event_id == "760442" for fact in result.value.facts)
    assert all(
        fact.evidence_identity != scanner_event.scanner_event_id
        for fact in result.value.facts
    )
    assert {decision["decision"] for decision in result.value.fetch_decisions} == {
        "REUSE_CACHED"
    }


def test_scanner_event_is_not_treated_as_provider_evidence() -> None:
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=("current_discovery",),
    )
    assert store.get_evidence(scanner_event.scanner_event_id) is None


def test_force_refresh_bypasses_cached_completeness_and_requires_fresh_evidence(
) -> None:
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    result = run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=(
            "current_discovery",
            "detailed_metrics",
            "current_form",
        ),
        force_refresh=True,
    )
    assert result.status == SourceResultStatus.EVIDENCE_ERROR
    assert result.error_code == "fresh_evidence_required"
    assert result.value is not None
    assert result.value.status == "ENRICH_FAILED_CLOSED"
    assert result.value.facts == ()
    assert {decision["decision"] for decision in result.value.fetch_decisions} == {
        "FETCH_FORCED"
    }


def test_persisted_facts_include_evidence_identity_and_schema_fingerprint() -> None:
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    result = run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=("current_discovery",),
    )
    assert result.value is not None
    assert result.value.facts
    assert all(fact.evidence_identity for fact in result.value.facts)
    assert all(fact.schema_fingerprint for fact in result.value.facts)


def test_scanner_batch_enrichment_accepts_batch() -> None:
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    batch = scanner_batch_from_events(scanner_event.profile_id, [scanner_event])
    results = run_scanner_batch_enrichment(
        batch,
        store,
        requested_capabilities=("current_discovery",),
    )
    assert len(results) == 1
    assert results[0].status == SourceResultStatus.SUCCESS


def test_db_activation_remains_deferred_without_safe_scanner_event_mapping() -> None:
    discovery = summarize_db_schema_discovery(REPO_ROOT)
    assert discovery["production_sqlite_convention"]["status"] == "SUPPORTED_IN_CODE"
    assert discovery["activation_decision"]["status"] == "DB_ACTIVATION_DEFERRED"
    assert discovery["activation_decision"]["safe_existing_table_mapping"] is False


def test_scanner_bridge_does_not_create_or_write_real_betting_db() -> None:
    before_exists = REAL_DB_PATH.exists()
    before_mtime = REAL_DB_PATH.stat().st_mtime if before_exists else None
    scanner_event = load_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_store_from_a3c1_state(
        store,
        profile_id=scanner_event.profile_id,
        scanner_event_id=scanner_event.scanner_event_id,
        state_root=PROFILE_ROOT / "state_store",
    )
    run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=("current_discovery",),
    )
    after_exists = REAL_DB_PATH.exists()
    after_mtime = REAL_DB_PATH.stat().st_mtime if after_exists else None
    assert after_exists == before_exists
    assert after_mtime == before_mtime


def test_future_profile_can_reuse_persistence_contract_without_world_cup_hardcoding(
) -> None:
    scanner_event = build_generic_profile_scanner_event()
    store = InMemoryProductionEnrichmentStore()
    seed_generic_cached_evidence(store, scanner_event)
    result = run_scanner_event_enrichment(
        scanner_event,
        scanner_event.profile_id,
        store,
        requested_capabilities=("current_discovery",),
    )
    assert result.status == SourceResultStatus.SUCCESS
    assert result.value is not None
    assert result.value.provider_event_id == "epl-4455"
    assert result.value.scanner_event_id == "example-1001"
    assert result.value.storage_kind == "temp"
