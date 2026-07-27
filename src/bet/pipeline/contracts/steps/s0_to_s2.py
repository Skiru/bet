"""Business contracts for DATA phase steps (S0 to S2.9)."""
from __future__ import annotations

from typing import Any
from pydantic import Field
from src.bet.pipeline.contracts.base import StrictBaseModel
from src.bet.pipeline.contracts.common import EventRecordV1, SourceReferenceV1, EvidenceClaimV1


# S0 Contract
class S0HistoricalPnlV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S0_HISTORICAL_PNL"
    status: str = "PASS"
    betting_day: str
    run_id: str
    total_settled_bets: int = Field(ge=0, default=0)
    total_pnl: float = 0.0
    settled_records: list[dict[str, Any]] = Field(default_factory=list)


# S1 Contract
class S1FixturesShortlistV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S1_FIXTURES_SHORTLIST"
    status: str = "PASS"
    betting_day: str
    run_id: str
    discovered_event_count: int = Field(ge=0)
    events: list[EventRecordV1] = Field(default_factory=list)


# S1e Contract
class S1eCanonicalEventUniverseV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S1E_CANONICAL_EVENT_UNIVERSE"
    status: str = "PASS"
    betting_day: str
    run_id: str
    source_s1_hash: str
    total_events: int = Field(ge=0)
    deduplicated_events: list[EventRecordV1] = Field(default_factory=list)


# S2 Contract
class S2TipsterConsensusV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S2_TIPSTER_CONSENSUS"
    status: str = "PASS"
    betting_day: str
    run_id: str
    tipsters_analyzed_count: int = Field(ge=0, default=0)
    tipster_absence_labeled: bool = True
    consensus_records: list[dict[str, Any]] = Field(default_factory=list)


# S2.3 Contract
class S23EnrichmentGapsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S2_3_ENRICHMENT_GAPS"
    status: str = "PASS"
    betting_day: str
    run_id: str
    total_gaps_identified: int = Field(ge=0)
    gaps: list[dict[str, Any]] = Field(default_factory=list)


# S2.5 Contract
class S25ProviderObservationsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S2_5_PROVIDER_OBSERVATIONS"
    status: str = "PASS"
    betting_day: str
    run_id: str
    total_observations: int = Field(ge=0)
    observations: list[EvidenceClaimV1] = Field(default_factory=list)


# S2.7 Contract
class S27ReconciledFactsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S2_7_RECONCILED_FACTS"
    status: str = "PASS"
    betting_day: str
    run_id: str
    total_reconciled: int = Field(ge=0)
    conflicts_detected: int = Field(ge=0, default=0)
    reconciled_facts: list[EvidenceClaimV1] = Field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any]] = Field(default_factory=list)


# S2.9 Contract
class S29DataReadinessV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: str = "S2_9_DATA_READINESS"
    status: str = "READY"  # READY | NO_ACTION_TERMINAL | BLOCK
    betting_day: str
    run_id: str
    data_quality_label: str = "HIGH"
    readiness_by_event: list[dict[str, Any]] = Field(default_factory=list)
