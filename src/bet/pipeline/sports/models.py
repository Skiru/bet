"""Typed models for sport-specific intelligence, dossiers, and evidence gates."""
from __future__ import annotations

from typing import Any, Sequence
from pydantic import Field
from bet.pipeline.contracts.base import StrictBaseModel


class MarketEvidenceRequirementV1(StrictBaseModel):
    """Specific fact requirement for a sport/market family."""
    fact_type: str
    requirement_level: str = "REQUIRED_FOR_PRICING"  # REQUIRED_FOR_PRICING | REQUIRED_FOR_ANALYSIS | OPTIONAL_CONTEXT | UNAVAILABLE_FOR_SCOPE
    min_sample_size: int = Field(default=1, ge=0)
    max_age_hours: int = Field(default=48, ge=1)
    min_independent_sources: int = Field(default=1, ge=1)
    conflict_action: str = "DOWNGRADE"  # FAIL_CLOSED | DOWNGRADE | WIDEN_INTERVAL


class SourceFreshnessPolicyV1(StrictBaseModel):
    """Freshness policy for a fact type."""
    fact_type: str
    max_age_hours: int = 48
    stale_action: str = "DOWNGRADE"  # BLOCK | DOWNGRADE | WIDEN_INTERVAL


class ContextFactorV1(StrictBaseModel):
    """Structured contextual factor affecting market families."""
    factor_type: str
    value_unit: str | None = None
    observed_at: str
    effective_at: str | None = None
    source_claim_ids: tuple[str, ...] = ()
    direction: str = "NEUTRAL"  # POSITIVE | NEGATIVE | NEUTRAL | UNCERTAIN
    affected_market_families: tuple[str, ...] = ()
    category: str = "GENERAL"
    uncertainty: float = Field(default=0.1, ge=0.0, le=1.0)
    confidence_basis: str = "SINGLE_SOURCE"
    model_action: str = "FEATURE"  # FEATURE | WIDEN_INTERVAL | DOWNGRADE | BLOCK


class MarketImpactV1(StrictBaseModel):
    """Impact of a context factor or missing fact on a market family."""
    market_family: str
    impact_level: str = "NEUTRAL"  # HIGH | MEDIUM | LOW | BLOCK
    action: str = "CONTINUE"  # CONTINUE | DOWNGRADE | WIDEN_INTERVAL | BLOCK
    reason_codes: tuple[str, ...] = ()


class SportEventDossierV1(StrictBaseModel):
    """Complete typed sport event dossier."""
    dossier_id: str
    canonical_event_id: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    event_start_time: str
    context_factors: list[ContextFactorV1] = Field(default_factory=list)
    raw_facts: dict[str, Any] = Field(default_factory=dict)
    reconciled_claims: list[dict[str, Any]] = Field(default_factory=list)
    dossier_sha256: str = ""


class SportReadinessDecisionV1(StrictBaseModel):
    """Readiness decision for a sport event and market family."""
    canonical_event_id: str
    sport: str
    market_family: str
    quality_grade: str = "HIGH"  # HIGH | MEDIUM | LOW | UNKNOWN
    missing_requirements: tuple[str, ...] = ()
    stale_requirements: tuple[str, ...] = ()
    conflicting_requirements: tuple[str, ...] = ()
    allowed_action: str = "READY_FOR_PRICING"  # READY_FOR_PRICING | ANALYSIS_ONLY | BLOCKED
    reason_codes: tuple[str, ...] = ()
