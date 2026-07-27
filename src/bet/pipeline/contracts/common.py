"""Shared sub-models and metadata components for step business contracts."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field, ConfigDict
from bet.pipeline.contracts.base import StrictBaseModel


class SourceReferenceV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    source_id: str
    source_name: str
    provenance_level: Literal["SYSTEM_VERIFIED_RECEIPT", "AGENT_ATTESTED_TOOL_RESULT", "SOURCE_REFERENCED_ONLY"] = "AGENT_ATTESTED_TOOL_RESULT"
    retrieved_at: str
    effective_at: str | None = None
    url_or_query: str | None = None
    raw_hash: str | None = None


class EventRecordV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    canonical_event_id: str
    sport: str = "football"
    competition: str = "League"
    home_team: str = "Home"
    away_team: str = "Away"
    event_start_time: str = "2026-07-27T18:00:00Z"
    discovery_status: Literal["VERIFIED", "UNVERIFIED", "PREFILTERED", "BLOCKED"] = "VERIFIED"
    terminal_status: str | None = None
    terminal_reason: str | None = None


class EvidenceClaimV1(StrictBaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
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
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)
    prediction_as_of: str
    sources_retrieved_before: str
    future_leakage_checked: bool = True
