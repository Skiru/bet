"""Shared sub-models and metadata components for step business contracts."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, field_validator
from bet.pipeline.contracts.base import StrictBaseModel


def _validate_sha256(v: str | None) -> str | None:
    if v is None:
        return v
    if not isinstance(v, str) or len(v) != 64 or not all(c in "0123456789abcdef" for c in v):
        raise ValueError(f"SHA256 hash must be a 64-character lowercase hex string, got {v!r}")
    return v


class SourceReferenceV1(StrictBaseModel):
    source_id: str
    source_name: str
    provenance_level: Literal["SYSTEM_VERIFIED_RECEIPT", "AGENT_ATTESTED_TOOL_RESULT", "SOURCE_REFERENCED_ONLY"] = "AGENT_ATTESTED_TOOL_RESULT"
    retrieved_at: str
    effective_at: str | None = None
    url_or_query: str | None = None
    raw_hash: str | None = None

    @field_validator("raw_hash")
    @classmethod
    def check_hash(cls, v: str | None) -> str | None:
        return _validate_sha256(v)


class EventRecordV1(StrictBaseModel):
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    event_start_time: str
    discovery_status: Literal["VERIFIED", "UNVERIFIED", "PREFILTERED", "BLOCKED"]
    terminal_status: str | None = None
    terminal_reason: str | None = None


class EvidenceClaimV1(StrictBaseModel):
    claim_id: str
    fact_type: str
    sport: str
    entity_id: str
    claim_value: str | float | int | bool | list[str] | list[float] | dict[str, str | float | int | bool]
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    sources: list[SourceReferenceV1] = Field(default_factory=list)
    observed_at: str
    effective_at: str | None = None


class PointInTimeLineageV1(StrictBaseModel):
    prediction_as_of: str
    sources_retrieved_before: str
    future_leakage_checked: bool = True
