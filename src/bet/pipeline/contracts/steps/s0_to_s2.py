"""Business contracts for DATA phase steps (S0 to S2.9)."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, ConfigDict
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.contracts.common import EventRecordV1, SourceReferenceV1, EvidenceClaimV1


class SettledRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    bet_id: str
    canonical_event_id: str
    market_family: str
    selection: str
    stake: float = Field(ge=0.0)
    odds: float = Field(ge=1.0)
    pnl: float
    settled_at: str
    outcome: Literal["WIN", "LOSS", "VOID", "PUSH"]


# S0 Contract
class S0HistoricalPnlV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S0_HISTORICAL_PNL"] = "S0_HISTORICAL_PNL"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_settled_bets: int = Field(ge=0, default=0)
    total_pnl: float = 0.0
    settled_records: list[SettledRecordV1] = Field(default_factory=list)


# S1 Contract
class S1FixturesShortlistV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S1_FIXTURES_SHORTLIST"] = "S1_FIXTURES_SHORTLIST"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    discovered_event_count: int = Field(ge=0)
    events: list[EventRecordV1] = Field(default_factory=list)


# S1e Contract
class S1eCanonicalEventUniverseV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S1E_CANONICAL_EVENT_UNIVERSE"] = "S1E_CANONICAL_EVENT_UNIVERSE"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    source_s1_hash: str
    total_events: int = Field(ge=0)
    deduplicated_events: list[EventRecordV1] = Field(default_factory=list)


class ConsensusRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    canonical_event_id: str
    tipster_count: int = Field(ge=0, default=0)
    consensus_signal: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    opinion_summary: str | None = None


# S2 Contract
class S2TipsterConsensusV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S2_TIPSTER_CONSENSUS"] = "S2_TIPSTER_CONSENSUS"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    tipsters_analyzed_count: int = Field(ge=0, default=0)
    tipster_absence_labeled: bool = True
    consensus_records: list[ConsensusRecordV1] = Field(default_factory=list)


class EnrichmentGapRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    gap_id: str
    canonical_event_id: str
    required_field: str
    sport: str
    severity: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    status: Literal["OPEN", "RESOLVED", "UNRESOLVABLE"] = "OPEN"


# S2.3 Contract
class S23EnrichmentGapsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S2_3_ENRICHMENT_GAPS"] = "S2_3_ENRICHMENT_GAPS"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_gaps_identified: int = Field(ge=0)
    gaps: list[EnrichmentGapRecordV1] = Field(default_factory=list)


# S2.5 Contract
class S25ProviderObservationsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S2_5_PROVIDER_OBSERVATIONS"] = "S2_5_PROVIDER_OBSERVATIONS"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_observations: int = Field(ge=0)
    observations: list[EvidenceClaimV1] = Field(default_factory=list)


class UnresolvedConflictRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    conflict_id: str
    canonical_event_id: str
    field_name: str
    conflicting_values: list[Any] = Field(default_factory=list)
    status: Literal["UNRESOLVED", "RESOLVED_BY_TIER", "DISCARDED"] = "UNRESOLVED"


# S2.7 Contract
class S27ReconciledFactsV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S2_7_RECONCILED_FACTS"] = "S2_7_RECONCILED_FACTS"
    status: Literal["PASS", "NO_ACTION_TERMINAL", "BLOCK"] = "PASS"
    betting_day: str
    run_id: str
    total_reconciled: int = Field(ge=0)
    conflicts_detected: int = Field(ge=0, default=0)
    reconciled_facts: list[EvidenceClaimV1] = Field(default_factory=list)
    unresolved_conflicts: list[UnresolvedConflictRecordV1] = Field(default_factory=list)


class DataReadinessRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    canonical_event_id: str
    sport: str
    quality_grade: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"] = "HIGH"
    readiness_tier: Literal["READY_FOR_PRICING", "ANALYSIS_ONLY", "BLOCKED"] = "READY_FOR_PRICING"
    missing_fields: list[str] = Field(default_factory=list)


# S2.9 Contract
class S29DataReadinessV1(StrictBaseModel):
    schema_version: int = 1
    artifact_type: Literal["S2_9_DATA_READINESS"] = "S2_9_DATA_READINESS"
    status: Literal["READY", "NO_ACTION_TERMINAL", "BLOCK"] = "READY"
    betting_day: str
    run_id: str
    data_quality_label: Literal["HIGH", "MEDIUM", "LOW", "UNKNOWN"] = "HIGH"
    readiness_by_event: list[DataReadinessRecordV1] = Field(default_factory=list)
