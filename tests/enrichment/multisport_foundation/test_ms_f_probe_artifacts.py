from __future__ import annotations

import pytest
from bet.enrichment.multisport_foundation import (
    ProviderMappingStatus,
    ProviderMappingArtifact,
    ProviderProbeArtifact,
    ProviderProbePolicy,
    ProviderProbeStatus,
    run_provider_probe,
)

def test_no_credentials_maps_api_sports_family() -> None:
    mapping = ProviderMappingArtifact(
        artifact_id="pass_e:basketball:api-sports-family:api_basketball_games",
        sport="basketball",
        provider_key="api-sports-family",
        status=str(ProviderMappingStatus.BLOCKED_NO_CREDENTIALS),
        route_key="api_basketball_games",
        endpoint_family="games",
        required_env_keys=("API_BASKETBALL_KEY",),
        missing_env_keys=("API_BASKETBALL_KEY",),
        proof_fields_required=("fixture_id",),
        forbidden_fields=("odds",),
        blocked_reason="no_credentials",
        live_call_allowed=False,
        production_selectable=False,
        betting_decisions_enabled=False,
        sanitized_probe_only=True,
    )
    policy = ProviderProbePolicy(
        provider_key="api-sports-family",
        sport="basketball",
        route_key="api_basketball_games",
        terms_review_approved=True,
    )
    artifact = run_provider_probe(mapping, policy, {})
    assert artifact.status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS
    assert artifact.live_call_made is False
    assert artifact.provider_access_attempted is False

def test_pandascore_terms_gate_maps_esports() -> None:
    mapping = ProviderMappingArtifact(
        artifact_id="pass_e:cs2:pandascore:pandascore_cs2_matches",
        sport="cs2",
        provider_key="pandascore",
        status=str(ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE),
        route_key="pandascore_cs2_matches",
        endpoint_family="matches",
        required_env_keys=("PANDASCORE_TOKEN",),
        missing_env_keys=("PANDASCORE_TOKEN",),
        proof_fields_required=("match_id",),
        forbidden_fields=("odds",),
        blocked_reason="terms_required",
        live_call_allowed=False,
        production_selectable=False,
        betting_decisions_enabled=False,
        sanitized_probe_only=True,
    )
    # terms_review_approved is False by default in the policy
    policy = ProviderProbePolicy(
        provider_key="pandascore",
        sport="cs2",
        route_key="pandascore_cs2_matches",
    )
    artifact = run_provider_probe(mapping, policy, {"PANDASCORE_TOKEN": "present"})
    assert artifact.status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE
    assert artifact.live_call_made is False
    assert artifact.provider_access_attempted is False

def test_mapping_not_ready_maps() -> None:
    mapping = ProviderMappingArtifact(
        artifact_id="pass_e:cs2:pandascore:pandascore_cs2_matches",
        sport="cs2",
        provider_key="pandascore",
        status="SOME_OTHER_STATUS_NOT_READY",
        route_key="pandascore_cs2_matches",
        endpoint_family="matches",
        required_env_keys=(),
        missing_env_keys=(),
        proof_fields_required=("match_id",),
        forbidden_fields=(),
        blocked_reason="not_ready",
        live_call_allowed=False,
        production_selectable=False,
        betting_decisions_enabled=False,
        sanitized_probe_only=True,
    )
    policy = ProviderProbePolicy(
        provider_key="pandascore",
        sport="cs2",
        route_key="pandascore_cs2_matches",
    )
    artifact = run_provider_probe(mapping, policy, {})
    assert artifact.status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY
    assert artifact.live_call_made is False
    assert artifact.provider_access_attempted is False

def test_captured_sanitized_requires_allow_real_network() -> None:
    mapping = ProviderMappingArtifact(
        artifact_id="pass_e:basketball:api-sports-family:api_basketball_games",
        sport="basketball",
        provider_key="api-sports-family",
        status=str(ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE),
        route_key="api_basketball_games",
        endpoint_family="games",
        required_env_keys=("API_BASKETBALL_KEY",),
        missing_env_keys=(),
        proof_fields_required=("fixture_id",),
        forbidden_fields=("odds",),
        blocked_reason="",
        live_call_allowed=False,
        production_selectable=False,
        betting_decisions_enabled=False,
        sanitized_probe_only=True,
    )
    # 1. With allow_real_network=False in policy, it is dry-run
    policy_dry = ProviderProbePolicy(
        provider_key="api-sports-family",
        sport="basketball",
        route_key="api_basketball_games",
        allow_real_network=False,
        terms_review_approved=True,
    )
    artifact_dry = run_provider_probe(mapping, policy_dry, {"API_BASKETBALL_KEY": "secret"})
    assert artifact_dry.status == ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN
    assert artifact_dry.live_call_made is False
    assert artifact_dry.provider_access_attempted is False

    # 2. Even with allow_real_network=True in policy, without MULTISPORT_PASS_F_ALLOW_REAL_NETWORK=1 in env, it remains dry-run
    policy_real = ProviderProbePolicy(
        provider_key="api-sports-family",
        sport="basketball",
        route_key="api_basketball_games",
        allow_real_network=True,
        terms_review_approved=True,
    )
    artifact_real = run_provider_probe(mapping, policy_real, {"API_BASKETBALL_KEY": "secret"})
    assert artifact_real.status == ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN

def test_artifact_invariants_raise_value_errors() -> None:
    # Cannot have proof_fields_observed in dry run
    with pytest.raises(ValueError, match="proof_fields_observed must be empty unless status is SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED"):
        ProviderProbeArtifact(
            artifact_id="id", sport="basketball", provider_key="api-sports", route_key="route",
            status=str(ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN),
            source_mapping_status="READY", request_method="GET", request_url_template="url",
            proof_fields_observed=("fixture_id",)
        )

    # production_selectable must be false
    with pytest.raises(ValueError, match="production_selectable must be false"):
        ProviderProbeArtifact(
            artifact_id="id", sport="basketball", provider_key="api-sports", route_key="route",
            status=str(ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN),
            source_mapping_status="READY", request_method="GET", request_url_template="url",
            production_selectable=True
        )

    # betting_decisions_enabled must be false
    with pytest.raises(ValueError, match="betting_decisions_enabled must be false"):
        ProviderProbeArtifact(
            artifact_id="id", sport="basketball", provider_key="api-sports", route_key="route",
            status=str(ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN),
            source_mapping_status="READY", request_method="GET", request_url_template="url",
            betting_decisions_enabled=True
        )
