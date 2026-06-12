"""Typed capability router for football enrichment.

Replaces Boolean orchestration with a typed resolution containing:
- capability
- target fixture/team
- cutoff
- attempted sources and statuses
- native IDs
- evidence bundles
- temporal/staleness flags
- conflicts
- selected result
- fallback reason

Rules:
- primary success stops fallback
- PLAN_RESTRICTED may fall back
- NOT_FOUND, NOT_SUPPORTED, NOT_PUBLISHED_YET follow explicit per-capability policy
- auth/rate/transport/parse/schema errors remain visible
- fallback success never erases primary failure
- ambiguity fails closed
- source observations are immutable
- selected projection is separate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus


class Capability(StrEnum):
    """P0 capabilities for football enrichment."""
    DISCOVERY_STATUS = "discovery_status"
    CANONICAL_EVENT_TEAM_IDENTITY = "canonical_event_team_identity"
    CURRENT_RECENT_FORM = "current_recent_form"
    H2H_HEAD_TO_HEAD = "h2h_head_to_head"
    STANDINGS_COMPETITION_CONTEXT = "standings_competition_context"
    FIXTURE_TEAM_STATISTICS = "fixture_team_statistics"
    CROSS_PROVIDER_IDENTITY = "cross_provider_identity"


class FallbackPolicy(StrEnum):
    """Policy for fallback behavior based on primary status."""
    STOP_ON_SUCCESS = "stop_on_success"
    FALLBACK_ELIGIBLE = "fallback_eligible"
    FAIL_CLOSED = "fail_closed"
    PROPAGATE_ERROR = "propagate_error"


@dataclass(frozen=True)
class SourceObservation:
    """Immutable record of a source attempt."""
    source: str
    status: SourceResultStatus
    native_ids: dict[str, str] = field(default_factory=dict)
    evidence_bundle_id: str = ""
    http_status: int | None = None
    error_code: str = ""
    retryable: bool = False
    observed_at: str = ""
    parser_version: str = ""
    staleness_flag: bool = False
    temporal_eligibility: str = ""


@dataclass
class CapabilityResolution:
    """Typed resolution for a capability request."""
    capability: Capability
    canonical_fixture_id: int | None = None
    team_id: int | None = None
    analysis_cutoff_at: str = ""

    # Attempted sources (immutable observations)
    observations: list[SourceObservation] = field(default_factory=list)

    # Selected result
    selected_source: str = ""
    selected_status: SourceResultStatus = SourceResultStatus.NOT_FOUND
    selected_value: Any = None
    selected_bundle_id: str = ""

    # Fallback metadata
    fallback_reason: str = ""
    primary_failed: bool = False
    fallback_succeeded: bool = False

    # Conflict handling
    has_conflict: bool = False
    conflict_details: str = ""

    # Temporal state
    is_stale: bool = False
    temporal_scope: str = ""

    def add_observation(self, obs: SourceObservation) -> None:
        """Add an immutable source observation."""
        self.observations.append(obs)

    def select_result(
        self,
        source: str,
        status: SourceResultStatus,
        value: Any = None,
        bundle_id: str = "",
        fallback_reason: str = "",
    ) -> None:
        """Select the final result from attempted sources."""
        self.selected_source = source
        self.selected_status = status
        self.selected_value = value
        self.selected_bundle_id = bundle_id
        self.fallback_reason = fallback_reason

        # Track if this was a fallback success
        if len(self.observations) > 1 and source == self.observations[-1].source:
            if self.observations[0].status != SourceResultStatus.SUCCESS:
                self.primary_failed = True
                self.fallback_succeeded = status == SourceResultStatus.SUCCESS


# Per-capability fallback policies
CAPABILITY_FALLBACK_POLICIES: dict[
    Capability, dict[SourceResultStatus, FallbackPolicy]
] = {
    Capability.DISCOVERY_STATUS: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.CURRENT_RECENT_FORM: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.FIXTURE_TEAM_STATISTICS: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.CANONICAL_EVENT_TEAM_IDENTITY: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.H2H_HEAD_TO_HEAD: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FALLBACK_ELIGIBLE,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.STANDINGS_COMPETITION_CONTEXT: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
    Capability.CROSS_PROVIDER_IDENTITY: {
        SourceResultStatus.SUCCESS: FallbackPolicy.STOP_ON_SUCCESS,
        SourceResultStatus.NOT_FOUND: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_PUBLISHED_YET: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.NOT_SUPPORTED: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.PLAN_RESTRICTED: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AMBIGUOUS: FallbackPolicy.FAIL_CLOSED,
        SourceResultStatus.AUTHENTICATION_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.RATE_LIMITED: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.TRANSPORT_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.UPSTREAM_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.PARSE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.SCHEMA_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.EVIDENCE_ERROR: FallbackPolicy.PROPAGATE_ERROR,
        SourceResultStatus.BLOCKED: FallbackPolicy.PROPAGATE_ERROR,
    },
}


def get_fallback_policy(
    capability: Capability, status: SourceResultStatus
) -> FallbackPolicy:
    """Get the fallback policy for a capability and status."""
    capability_policies = CAPABILITY_FALLBACK_POLICIES.get(capability, {})
    return capability_policies.get(status, FallbackPolicy.FAIL_CLOSED)


def should_fallback(capability: Capability, primary_status: SourceResultStatus) -> bool:
    """Determine if fallback should be attempted after primary result."""
    policy = get_fallback_policy(capability, primary_status)
    return policy == FallbackPolicy.FALLBACK_ELIGIBLE


def create_observation_from_result(
    source: str,
    result: SourceOperationResult,
    native_ids: dict[str, str] | None = None,
    parser_version: str = "",
    temporal_eligibility: str = "",
) -> SourceObservation:
    """Create an immutable observation from a source operation result."""
    return SourceObservation(
        source=source,
        status=result.status,
        native_ids=native_ids or {},
        evidence_bundle_id=result.bundle_id,
        http_status=result.http_status,
        error_code=result.error_code,
        retryable=result.retryable,
        observed_at=datetime.now(UTC).isoformat(),
        parser_version=parser_version,
        staleness_flag=False,
        temporal_eligibility=temporal_eligibility,
    )
