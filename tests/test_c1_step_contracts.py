"""C1 acceptance tests for strict step contracts and contract registry."""
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from bet.pipeline.contracts.base import (
    StrictBaseModel,
    CompletionEnvelopeType,
    ArtifactRole,
    ValidatedPipelineDefinition,
    ValidatedRunContext,
)
from bet.pipeline.contracts.registry import GLOBAL_CONTRACT_REGISTRY, ContractDescriptor
from bet.pipeline.contracts.canonical_json import dumps_canonical_json, hash_canonical_json
from bet.pipeline.contracts.migration import migrate_artifact_payload, MigrationAdapterError
from bet.pipeline.contracts.steps.s0_to_s2 import (
    S0HistoricalPnlV1,
    S1FixturesShortlistV1,
    S1eCanonicalEventUniverseV1,
    S2TipsterConsensusV1,
    S23EnrichmentGapsV1,
    S25ProviderObservationsV1,
    S27ReconciledFactsV1,
    S29DataReadinessV1,
)
from bet.pipeline.contracts.steps.s3_to_s10 import (
    S3CalibratedProbabilitiesV1,
    S4ExpectedValueEstimatesV1,
    S5ContextMotivationRiskV1,
    S6PortfolioRepeatGuardV1,
    S7ApprovedPicksV1,
    S7bSuperbetManualMappingV1,
    S8SuperbetManualQuotePackV1,
    S9ExecutedBetsJournalV1,
    S10SettlementHandoffV1,
)


def test_registry_contains_all_17_steps():
    """Verify all 17 step contracts (S0 through S10) are registered in GLOBAL_CONTRACT_REGISTRY."""
    descriptors = GLOBAL_CONTRACT_REGISTRY.list_descriptors()
    contract_ids = {d.contract_id for d in descriptors}
    expected_ids = {
        "S0_HISTORICAL_PNL",
        "S1_FIXTURES_SHORTLIST",
        "S1E_CANONICAL_EVENT_UNIVERSE",
        "S2_TIPSTER_CONSENSUS",
        "S2_3_ENRICHMENT_GAPS",
        "S2_5_PROVIDER_OBSERVATIONS",
        "S2_7_RECONCILED_FACTS",
        "S2_9_DATA_READINESS",
        "S3_CALIBRATED_PROBABILITIES",
        "S4_EXPECTED_VALUE_ESTIMATES",
        "S5_CONTEXT_MOTIVATION_RISK",
        "S6_PORTFOLIO_REPEAT_GUARD",
        "S7_APPROVED_PICKS",
        "S7B_SUPERBET_MANUAL_MAPPING",
        "S8_SUPERBET_MANUAL_QUOTE_PACK",
        "S9_EXECUTED_BETS_JOURNAL",
        "S10_SETTLEMENT_HANDOFF",
    }
    assert expected_ids.issubset(contract_ids), f"Missing step contracts: {expected_ids - contract_ids}"


def test_strict_model_forbids_extra_fields():
    """Verify extra unknown fields cause validation error."""
    valid_s1 = {
        "schema_version": 1,
        "artifact_type": "S1_FIXTURES_SHORTLIST",
        "status": "PASS",
        "betting_day": "2026-07-27",
        "run_id": "TEST_RUN_001",
        "discovered_event_count": 0,
        "events": [],
    }
    # Parsing valid payload works
    obj = S1FixturesShortlistV1.model_validate(valid_s1)
    assert obj.status == "PASS"

    # Adding unknown field raises ValidationError
    invalid_s1 = dict(valid_s1, unknown_extra_field="ILLEGAL_PAYLOAD")
    with pytest.raises(ValidationError):
        S1FixturesShortlistV1.model_validate(invalid_s1)


def test_canonical_json_determinism():
    """Verify canonical JSON serializer is deterministic and produces stable hashes."""
    data_a = {"b": 2, "a": 1, "c": [3, 2, 1]}
    data_b = {"a": 1, "c": [3, 2, 1], "b": 2}

    json_a = dumps_canonical_json(data_a)
    json_b = dumps_canonical_json(data_b)

    assert json_a == json_b
    assert hash_canonical_json(data_a) == hash_canonical_json(data_b)


def test_explicit_migration_adapter():
    """Verify versioned migration adapter works explicitly and fails if missing adapter."""
    v1_s7b = {
        "schema_version": 1,
        "artifact_type": "S7B_SUPERBET_MANUAL_MAPPING",
        "status": "READY_FOR_MANUAL_MAPPING",
        "betting_day": "2026-07-27",
        "run_id": "TEST_RUN_001",
    }
    v2_s7b = migrate_artifact_payload("S7B_SUPERBET_MANUAL_MAPPING", 1, 2, v1_s7b)
    assert v2_s7b["schema_version"] == 2
    assert v2_s7b["operator_workflow"] == "SUPERBET_MANUAL_BET_BUILDER"

    with pytest.raises(MigrationAdapterError):
        migrate_artifact_payload("S7B_SUPERBET_MANUAL_MAPPING", 1, 99, v1_s7b)


def test_producer_consumer_chain_matrix():
    """Verify producer-to-consumer chain contracts pass strictly."""
    # S1 -> S1e
    s1_obj = S1FixturesShortlistV1(
        betting_day="2026-07-27",
        run_id="RUN_MATRIX_001",
        discovered_event_count=1,
        events=[
            {
                "canonical_event_id": "EVT_FOOTBALL_001",
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "event_start_time": "2026-07-27T15:00:00Z",
                "discovery_status": "VERIFIED",
            }
        ]
    )
    s1_bytes = dumps_canonical_json(s1_obj)
    s1_reloaded = S1FixturesShortlistV1.model_validate_json(s1_bytes)
    assert len(s1_reloaded.events) == 1

    # S1e produces canonical universe
    s1e_obj = S1eCanonicalEventUniverseV1(
        betting_day="2026-07-27",
        run_id="RUN_MATRIX_001",
        source_s1_hash=hash_canonical_json(s1_obj),
        total_events=1,
        deduplicated_events=s1_reloaded.events,
    )
    s1e_bytes = dumps_canonical_json(s1e_obj)
    s1e_reloaded = S1eCanonicalEventUniverseV1.model_validate_json(s1e_bytes)
    assert s1e_reloaded.total_events == 1
