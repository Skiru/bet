"""Tests for typed capability router."""

from __future__ import annotations

import pytest

from bet.api_clients.base_client import SourceOperationResult, SourceResultStatus
from bet.enrichment.capability_router import (
    Capability,
    CapabilityResolution,
    FallbackPolicy,
    SourceObservation,
    create_observation_from_result,
    get_fallback_policy,
    should_fallback,
)


class TestCapabilityRouter:
    """Test typed capability router."""

    def test_primary_success_stops_fallback(self):
        """Primary SUCCESS should stop fallback."""
        policy = get_fallback_policy(Capability.DISCOVERY_STATUS, SourceResultStatus.SUCCESS)
        assert policy == FallbackPolicy.STOP_ON_SUCCESS

    def test_plan_restricted_is_fallback_eligible(self):
        """PLAN_RESTRICTED should allow fallback."""
        policy = get_fallback_policy(Capability.CURRENT_RECENT_FORM, SourceResultStatus.PLAN_RESTRICTED)
        assert policy == FallbackPolicy.FALLBACK_ELIGIBLE

    def test_not_found_is_fallback_eligible_for_discovery(self):
        """NOT_FOUND should allow fallback for discovery."""
        policy = get_fallback_policy(Capability.DISCOVERY_STATUS, SourceResultStatus.NOT_FOUND)
        assert policy == FallbackPolicy.FALLBACK_ELIGIBLE

    def test_ambiguous_fails_closed(self):
        """AMBIGUOUS should fail closed."""
        policy = get_fallback_policy(Capability.CANONICAL_EVENT_TEAM_IDENTITY, SourceResultStatus.AMBIGUOUS)
        assert policy == FallbackPolicy.FAIL_CLOSED

    def test_auth_error_propagates(self):
        """AUTHENTICATION_ERROR should propagate."""
        policy = get_fallback_policy(Capability.FIXTURE_TEAM_STATISTICS, SourceResultStatus.AUTHENTICATION_ERROR)
        assert policy == FallbackPolicy.PROPAGATE_ERROR

    def test_rate_limited_propagates(self):
        """RATE_LIMITED should propagate."""
        policy = get_fallback_policy(Capability.DISCOVERY_STATUS, SourceResultStatus.RATE_LIMITED)
        assert policy == FallbackPolicy.PROPAGATE_ERROR

    def test_transport_error_propagates(self):
        """TRANSPORT_ERROR should propagate."""
        policy = get_fallback_policy(Capability.CURRENT_RECENT_FORM, SourceResultStatus.TRANSPORT_ERROR)
        assert policy == FallbackPolicy.PROPAGATE_ERROR

    def test_should_fallback_returns_true_for_plan_restricted(self):
        """should_fallback returns True for PLAN_RESTRICTED."""
        assert should_fallback(Capability.CURRENT_RECENT_FORM, SourceResultStatus.PLAN_RESTRICTED)

    def test_should_fallback_returns_false_for_success(self):
        """should_fallback returns False for SUCCESS."""
        assert not should_fallback(Capability.DISCOVERY_STATUS, SourceResultStatus.SUCCESS)

    def test_should_fallback_returns_false_for_ambiguous(self):
        """should_fallback returns False for AMBIGUOUS."""
        assert not should_fallback(Capability.CANONICAL_EVENT_TEAM_IDENTITY, SourceResultStatus.AMBIGUOUS)


class TestSourceObservation:
    """Test immutable source observation."""

    def test_observation_is_frozen(self):
        """SourceObservation should be frozen."""
        obs = SourceObservation(
            source="api-football",
            status=SourceResultStatus.SUCCESS,
            native_ids={"fixture_id": "123"},
        )
        with pytest.raises(AttributeError):
            obs.source = "espn"

    def test_create_observation_from_result(self):
        """Create observation from SourceOperationResult."""
        result = SourceOperationResult(
            status=SourceResultStatus.SUCCESS,
            value={"test": "data"},
            http_status=200,
            bundle_id="abc123",
        )
        obs = create_observation_from_result(
            source="api-football",
            result=result,
            native_ids={"fixture_id": "123"},
            parser_version="v1",
        )
        assert obs.source == "api-football"
        assert obs.status == SourceResultStatus.SUCCESS
        assert obs.http_status == 200
        assert obs.evidence_bundle_id == "abc123"


class TestCapabilityResolution:
    """Test capability resolution."""

    def test_add_observation(self):
        """Add observation to resolution."""
        resolution = CapabilityResolution(
            capability=Capability.DISCOVERY_STATUS,
            canonical_fixture_id=1,
        )
        obs = SourceObservation(
            source="api-football",
            status=SourceResultStatus.SUCCESS,
        )
        resolution.add_observation(obs)
        assert len(resolution.observations) == 1

    def test_select_result(self):
        """Select result from observations."""
        resolution = CapabilityResolution(
            capability=Capability.DISCOVERY_STATUS,
            canonical_fixture_id=1,
        )
        resolution.select_result(
            source="api-football",
            status=SourceResultStatus.SUCCESS,
            value={"test": "data"},
            bundle_id="abc123",
        )
        assert resolution.selected_source == "api-football"
        assert resolution.selected_status == SourceResultStatus.SUCCESS

    def test_fallback_success_preserves_primary_failure(self):
        """Fallback success should preserve primary failure."""
        resolution = CapabilityResolution(
            capability=Capability.CURRENT_RECENT_FORM,
            canonical_fixture_id=1,
            team_id=1,
        )
        # Primary failed
        primary_obs = SourceObservation(
            source="espn",
            status=SourceResultStatus.PLAN_RESTRICTED,
        )
        resolution.add_observation(primary_obs)

        # Fallback succeeded
        fallback_obs = SourceObservation(
            source="api-football",
            status=SourceResultStatus.SUCCESS,
        )
        resolution.add_observation(fallback_obs)

        resolution.select_result(
            source="api-football",
            status=SourceResultStatus.SUCCESS,
            fallback_reason="primary_plan_restricted",
        )

        assert resolution.primary_failed
        assert resolution.fallback_succeeded
        assert resolution.fallback_reason == "primary_plan_restricted"


class TestFallbackPolicyMatrix:
    """Test fallback policy matrix for all statuses."""

    @pytest.mark.parametrize("capability", list(Capability))
    @pytest.mark.parametrize("status", [
        SourceResultStatus.SUCCESS,
        SourceResultStatus.NOT_FOUND,
        SourceResultStatus.NOT_PUBLISHED_YET,
        SourceResultStatus.NOT_SUPPORTED,
        SourceResultStatus.PLAN_RESTRICTED,
        SourceResultStatus.AMBIGUOUS,
        SourceResultStatus.AUTHENTICATION_ERROR,
        SourceResultStatus.RATE_LIMITED,
        SourceResultStatus.TRANSPORT_ERROR,
        SourceResultStatus.UPSTREAM_ERROR,
        SourceResultStatus.PARSE_ERROR,
        SourceResultStatus.SCHEMA_ERROR,
        SourceResultStatus.EVIDENCE_ERROR,
        SourceResultStatus.BLOCKED,
    ])
    def test_all_capabilities_have_policy_for_all_statuses(self, capability, status):
        """Every capability must have a policy for every status."""
        policy = get_fallback_policy(capability, status)
        assert isinstance(policy, FallbackPolicy)
