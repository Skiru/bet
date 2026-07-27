"""Shared sub-models and metadata components for step business contracts."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel


class SourceReferenceV1(StrictBaseModel):
    """Refers to an external data source or tool result."""
    source_id: str
    source_name: str
    provenance_level: Literal["SYSTEM_VERIFIED_RECEIPT", "AGENT_ATTESTED_TOOL_RESULT", "SOURCE_REFERENCED_ONLY"] = "AGENT_ATTESTED_TOOL_RESULT"
    retrieved_at: str
    effective_at: str | None = None
    url_or_query: str | None = None
    raw_hash: str | None = None


class EventRecordV1(StrictBaseModel):
    """Canonical event record representation across step outputs."""
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    event_start_time: str
    discovery_status: Literal["VERIFIED", "UNVERIFIED", "PREFILTERED", "BLOCKED"] = "VERIFIED"
    terminal_status: str | None = None
    terminal_reason: str | None = None


class EvidenceClaimV1(StrictBaseModel):
    """Fact or contextual evidence claim with provenance and confidence."""
    claim_id: str
    fact_type: str
    sport: str
    entity_id: str
    claim_value: Any
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    sources: list[SourceReferenceV1] = Field(default_factory=list)
    observed_at: str
    effective_at: str | None = None


class PointInTimeLineageV1(StrictBaseModel):
    """Point-in-time timestamp and source lineage metadata."""
    prediction_as_of: str
    sources_retrieved_before: str
    future_leakage_checked: bool = True
