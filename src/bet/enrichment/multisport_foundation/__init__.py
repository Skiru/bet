from __future__ import annotations

from importlib import import_module
from typing import Any

# Exports resolve lazily, one submodule at a time.
#
# This package used to import all 19 of its submodules eagerly, and one of
# them reaches `bet.api_clients.rate_limiter` -> `bet.api_clients.env` ->
# `dotenv`. That made *any* import from this package pull the provider client
# layer and a site-package, so the import-isolation test in
# `tests/enrichment/multisport_foundation/test_ms_b_import_isolation.py`
# -- which imports one leaf module under `python -S` -- could not pass, and the
# lean "Pass B" environment the parent package's own docstring promises did not
# exist below it. `bet/enrichment/__init__.py` already solves this the same
# way; this is that pattern applied one level down.
#
# The public surface is unchanged: every name below resolved to the same object
# before this change, which is asserted by comparing the exported names and
# their defining modules against the eager version.
_EXPORTS: dict[str, str] = {
    'ActivationCandidateArtifact': 'activation_candidate',
    'BLOCKED_STATUSES': 'fail_closed',
    'FactRequirement': 'contracts',
    'LiveObservationArtifact': 'live_observation',
    'MultisportPlan': 'contracts',
    'OutcomeStatus': 'contracts',
    'PASS_B_STATUSES': 'fail_closed',
    'PassBVerificationResult': 'verifier',
    'PassCVerificationResult': 'verifier',
    'PassDefinition': 'contracts',
    'PassKind': 'contracts',
    'ProofLevel': 'contracts',
    'ProviderAuthorizationArtifact': 'provider_authorization',
    'ProviderAuthorizationSpec': 'provider_authorization',
    'ProviderAuthorizationStatus': 'provider_authorization',
    'ProviderCorpusRecord': 'provider_corpus',
    'ProviderMappingArtifact': 'provider_mapping',
    'ProviderMappingStatus': 'provider_mapping',
    'ProviderProbeArtifact': 'provider_probe',
    'ProviderProbePolicy': 'provider_probe',
    'ProviderProbeStatus': 'provider_probe',
    'ProviderProfile': 'contracts',
    'ProviderRole': 'contracts',
    'ProviderRouteSpec': 'provider_mapping',
    'SingleFlightProbeArtifact': 'single_flight_probe',
    'SingleFlightProbePolicy': 'single_flight_probe',
    'SingleFlightProbeStatus': 'single_flight_probe',
    'SourceBoundShadowArtifact': 'source_bound_shadow',
    'SourceInventoryEntry': 'source_inventory',
    'SportKey': 'contracts',
    'SportProfile': 'contracts',
    'VALID_FAIL_CLOSED_STATUSES': 'fail_closed',
    'VerificationResult': 'verifier',
    'assert_no_forbidden_success_text': 'fail_closed',
    'authorize_probe': 'provider_authorization',
    'build_activation_candidate': 'activation_candidate',
    'build_authorization_report': 'provider_authorization',
    'build_blocked_corpus_record': 'provider_corpus',
    'build_default_single_flight_report': 'single_flight_probe',
    'build_live_observation': 'live_observation',
    'build_mapping_artifact': 'provider_mapping',
    'build_multisport_wave_plan': 'plan',
    'build_provider_mapping_plan': 'provider_mapping',
    'build_provider_profiles': 'providers',
    'build_source_bound_shadow': 'source_bound_shadow',
    'build_source_inventory': 'source_inventory',
    'build_sport_profiles': 'profiles',
    'contains_raw_secret': 'provider_corpus',
    'default_authorization_specs': 'provider_authorization',
    'default_route_specs': 'provider_mapping',
    'inventory_by_key': 'source_inventory',
    'is_valid_pass_b_status': 'fail_closed',
    'provider_matrix': 'providers',
    'run_provider_probe': 'provider_probe',
    'run_single_flight_probe': 'single_flight_probe',
    'sanitize_headers': 'provider_corpus',
    'source_inventory_report_payload': 'source_inventory',
    'stable_corpus_id': 'provider_corpus',
    'validate_authorization_report': 'provider_authorization',
    'validate_mapping_plan': 'provider_mapping',
    'validate_single_flight_report': 'single_flight_probe',
    'verify_activation_candidates': 'verifier',
    'verify_live_observations': 'verifier',
    'verify_plan': 'verifier',
    'verify_provider_access_gate': 'verifier',
    'verify_provider_corpus': 'verifier',
    'verify_provider_mapping': 'verifier',
    'verify_provider_probes': 'verifier',
    'verify_shadow_artifacts': 'verifier',
    'verify_single_flight_probes': 'verifier',
    'verify_source_inventory': 'verifier',
    'write_authorization_reports': 'provider_authorization_report',
    'write_pass_c_reports': 'live_observation',
    'write_pass_e_summary': 'provider_mapping_report',
    'write_pass_f_reports': 'provider_probe_report',
    'write_provider_mapping_plan': 'provider_mapping_report',
    'write_single_flight_reports': 'single_flight_probe_report',
    'write_source_inventory_report': 'source_inventory',
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        submodule = _EXPORTS[name]
    except KeyError:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from None
    module = import_module(f"{__name__}.{submodule}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
