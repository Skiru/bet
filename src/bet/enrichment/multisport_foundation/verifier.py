from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .fail_closed import PASS_B_STATUSES, assert_no_forbidden_success_text, is_valid_pass_b_status
from .provider_corpus import ProviderCorpusRecord, contains_raw_secret
from .source_bound_shadow import SourceBoundShadowArtifact
from .source_inventory import FOOTBALL_ERA_SOURCE_KEYS, TARGET_SPORTS, build_source_inventory
from .activation_candidate import ActivationCandidateArtifact
from .live_observation import LiveObservationArtifact


@dataclass
class VerificationResult:
    verdict: str
    failed_requirements: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "failed_requirements": self.failed_requirements,
            "metrics": self.metrics,
        }


@dataclass
class PassBVerificationResult:
    verdict: str
    failed_requirements: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "failed_requirements": self.failed_requirements,
            "metrics": self.metrics,
        }


REQUIRED_GUARDRAIL_FRAGMENTS = (
    "no production routing activation",
    "no betting decisions",
    "no production db writes",
    "no fake success",
    "public raw line table",
)

FORBIDDEN_SUCCESS_TEXT = (
    "fallback score accepted",
    "fallback provider id accepted",
    "production_ready",
    "betting decision allowed",
)


def verify_plan() -> VerificationResult:
    """Verify the accepted Pass A multisport wave plan.

    This function is intentionally kept backward-compatible with Pass A tests.
    Imports of Pass A modules are lazy so Pass B-only helpers can be imported
    without forcing unrelated modules during collection.
    """
    from .contracts import OutcomeStatus, SportKey
    from .plan import build_multisport_wave_plan

    required_sports = {sport for sport in SportKey}
    plan = build_multisport_wave_plan()
    failed: list[str] = []

    if set(plan.profiles) != required_sports:
        missing = sorted(sport.value for sport in required_sports - set(plan.profiles))
        failed.append(f"missing_sport_profiles:{missing}")

    if len(plan.passes) != 4:
        failed.append(f"expected_four_passes_found:{len(plan.passes)}")

    guardrail_blob = "\n".join(plan.global_guardrails).lower()
    for fragment in REQUIRED_GUARDRAIL_FRAGMENTS:
        if fragment not in guardrail_blob:
            failed.append(f"missing_global_guardrail:{fragment}")

    for sport, profile in plan.profiles.items():
        if profile.minimum_real_mapped_providers < 1:
            failed.append(f"invalid_minimum_providers:{sport.value}")
        if not profile.provider_candidates:
            failed.append(f"missing_provider_candidates:{sport.value}")
        if not any(fact.required_for_shadow_ready for fact in profile.required_facts):
            failed.append(f"missing_required_facts:{sport.value}")

    for provider_key, provider in plan.providers.items():
        if not provider.allowed_proof_levels:
            failed.append(f"missing_proof_levels:{provider_key}")
        if not provider.docs_url.startswith("https://"):
            failed.append(f"provider_docs_url_not_https:{provider_key}")

    plan_blob = str(plan.to_json()).lower()
    for forbidden in FORBIDDEN_SUCCESS_TEXT:
        if forbidden in plan_blob:
            failed.append(f"forbidden_success_text:{forbidden}")

    pass_statuses = {
        status
        for pass_definition in plan.passes
        for status in pass_definition.success_statuses
    }
    if OutcomeStatus.REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT not in pass_statuses:
        failed.append("fail_closed_observation_status_missing")

    metrics = {
        "sport_count": len(plan.profiles),
        "provider_count": len(plan.providers),
        "pass_count": len(plan.passes),
        "guardrail_count": len(plan.global_guardrails),
    }
    return VerificationResult(
        verdict="PASS" if not failed else "FAIL",
        failed_requirements=failed,
        metrics=metrics,
    )


def verify_source_inventory() -> PassBVerificationResult:
    failed: list[str] = []
    inventory = build_source_inventory()
    by_key = {entry.source_key: entry for entry in inventory}
    for key in FOOTBALL_ERA_SOURCE_KEYS:
        if key not in by_key:
            failed.append(f"missing_football_source:{key}")
    for entry in inventory:
        if not entry.transfer_decision:
            failed.append(f"missing_transfer_decision:{entry.source_key}")
        if not entry.allowed_proof_levels:
            failed.append(f"missing_proof_policy:{entry.source_key}")
        if entry.transfer_decision == "transfer_direct" and not entry.target_sports:
            failed.append(f"direct_source_without_target_sports:{entry.source_key}")
        if entry.transfer_decision in {"deferred_probe_only", "blocked_terms_or_access"} and "production_dependency_without_terms_review" not in entry.forbidden_uses:
            failed.append(f"probe_source_missing_production_forbidden_use:{entry.source_key}")
        if entry.source_family == "esports_multisport_addition" and not entry.terms_or_access_review_required:
            failed.append(f"esports_source_missing_terms_review:{entry.source_key}")
    return PassBVerificationResult(
        "PASS" if not failed else "FAIL",
        failed,
        {"source_count": len(inventory), "target_sports": list(TARGET_SPORTS)},
    )


def verify_provider_corpus(records: list[ProviderCorpusRecord]) -> PassBVerificationResult:
    failed: list[str] = []
    for record in records:
        if not is_valid_pass_b_status(record.status):
            failed.append(f"invalid_status:{record.corpus_id}:{record.status}")
        if contains_raw_secret(record.to_json()):
            failed.append(f"raw_secret_in_record:{record.corpus_id}")
        if record.status == "SOURCE_BOUND_SHADOW_READY" and not record.participant_evidence:
            failed.append(f"shadow_ready_without_participant_evidence:{record.corpus_id}")
        try:
            assert_no_forbidden_success_text(record.to_json())
        except AssertionError as exc:
            failed.append(f"forbidden_success_text:{record.corpus_id}:{exc}")
    return PassBVerificationResult("PASS" if not failed else "FAIL", failed, {"record_count": len(records)})


def verify_shadow_artifacts(artifacts: list[SourceBoundShadowArtifact]) -> PassBVerificationResult:
    failed: list[str] = []
    for artifact in artifacts:
        if artifact.status not in PASS_B_STATUSES:
            failed.append(f"invalid_shadow_status:{artifact.artifact_id}:{artifact.status}")
        if artifact.production_selectable:
            failed.append(f"production_selectable_forbidden:{artifact.artifact_id}")
        if artifact.betting_decisions_enabled:
            failed.append(f"betting_decisions_forbidden:{artifact.artifact_id}")
        if not artifact.manual_authorization_required:
            failed.append(f"manual_authorization_required_false:{artifact.artifact_id}")
        if artifact.status == "SOURCE_BOUND_SHADOW_READY" and not artifact.source_keys:
            failed.append(f"shadow_ready_without_sources:{artifact.artifact_id}")
        try:
            assert_no_forbidden_success_text(artifact.to_json())
        except AssertionError as exc:
            failed.append(f"forbidden_success_text:{artifact.artifact_id}:{exc}")
    return PassBVerificationResult("PASS" if not failed else "FAIL", failed, {"artifact_count": len(artifacts)})


@dataclass
class PassCVerificationResult:
    verdict: str
    failed_requirements: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "failed_requirements": self.failed_requirements,
            "metrics": self.metrics,
        }


def verify_activation_candidates(artifacts: list[ActivationCandidateArtifact]) -> PassCVerificationResult:
    failed: list[str] = []
    for artifact in artifacts:
        if not artifact.manual_authorization_required:
            failed.append(f"manual_authorization_required_false:{artifact.artifact_id}")
        if artifact.production_selectable:
            failed.append(f"production_selectable_forbidden:{artifact.artifact_id}")
        if artifact.betting_decisions_enabled:
            failed.append(f"betting_decisions_forbidden:{artifact.artifact_id}")

        if artifact.activation_candidate and artifact.status != "ACTIVATION_CANDIDATE_SHADOW_ONLY":
            failed.append(f"activation_candidate_true_without_shadow_only_status:{artifact.artifact_id}")

        if artifact.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY":
            if artifact.source_pass_b_status != "SOURCE_BOUND_SHADOW_READY":
                failed.append(f"activation_candidate_shadow_only_requires_pass_b_shadow_ready:{artifact.artifact_id}")
            if not artifact.source_keys or not artifact.corpus_ids:
                failed.append(f"activation_candidate_shadow_only_requires_sources_and_corpus_ids:{artifact.artifact_id}")

        if artifact.source_pass_b_status == "BLOCKED_PROVIDER_MAPPING_NOT_FOUND" and artifact.status != "BLOCKED_NO_REAL_PROVIDER_ACCESS":
            failed.append(f"mapping_not_found_must_map_to_blocked_no_real_provider_access:{artifact.artifact_id}")
        if artifact.source_pass_b_status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE" and artifact.status != "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
            failed.append(f"terms_or_scope_must_map_to_terms_or_scope:{artifact.artifact_id}")
        if artifact.source_pass_b_status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT" and artifact.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING":
            failed.append(f"mapping_insufficient_must_map_to_observed_but_live_shadow_blocked:{artifact.artifact_id}")

        payload = dict(artifact.to_json())
        payload.pop("manual_authorization_required", None)
        for key in ["status", "source_pass_b_status", "artifact_id", "blocked_reason", "required_manual_steps", "evidence_refs", "source_shadow_report_path"]:
            if key in payload:
                payload[key] = "<redacted>"
        if contains_raw_secret(payload):
            failed.append(f"raw_secret_in_record:{artifact.artifact_id}")
        try:
            assert_no_forbidden_success_text(artifact.to_json())
        except AssertionError as exc:
            failed.append(f"forbidden_success_text:{artifact.artifact_id}:{exc}")

    return PassCVerificationResult("PASS" if not failed else "FAIL", failed, {"artifact_count": len(artifacts)})


def verify_live_observations(artifacts: list[LiveObservationArtifact]) -> PassCVerificationResult:
    failed: list[str] = []
    for artifact in artifacts:
        if not artifact.manual_authorization_required:
            failed.append(f"manual_authorization_required_false:{artifact.artifact_id}")
        if artifact.production_selectable:
            failed.append(f"production_selectable_forbidden:{artifact.artifact_id}")
        if artifact.betting_decisions_enabled:
            failed.append(f"betting_decisions_forbidden:{artifact.artifact_id}")
        if artifact.live_call_made:
            failed.append(f"live_call_made_true_forbidden:{artifact.artifact_id}")
        if artifact.provider_access_attempted:
            failed.append(f"provider_access_attempted_true_forbidden:{artifact.artifact_id}")
        if artifact.observation_mode != "fail_closed_no_live_call":
            failed.append(f"observation_mode_not_fail_closed_no_live_call:{artifact.artifact_id}")

        if artifact.source_pass_b_status == "BLOCKED_PROVIDER_MAPPING_NOT_FOUND" and artifact.status != "BLOCKED_NO_REAL_PROVIDER_ACCESS":
            failed.append(f"mapping_not_found_must_map_to_blocked_no_real_provider_access:{artifact.artifact_id}")
        if artifact.source_pass_b_status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE" and artifact.status != "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
            failed.append(f"terms_or_scope_must_map_to_terms_or_scope:{artifact.artifact_id}")
        if artifact.source_pass_b_status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT" and artifact.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING":
            failed.append(f"mapping_insufficient_must_map_to_observed_but_live_shadow_blocked:{artifact.artifact_id}")

        payload = dict(artifact.to_json())
        payload.pop("manual_authorization_required", None)
        for key in ["status", "source_pass_b_status", "artifact_id", "blocked_reason", "required_manual_steps", "evidence_refs", "source_shadow_report_path"]:
            if key in payload:
                payload[key] = "<redacted>"
        if contains_raw_secret(payload):
            failed.append(f"raw_secret_in_record:{artifact.artifact_id}")
        try:
            assert_no_forbidden_success_text(artifact.to_json())
        except AssertionError as exc:
            failed.append(f"forbidden_success_text:{artifact.artifact_id}:{exc}")

    return PassCVerificationResult("PASS" if not failed else "FAIL", failed, {"artifact_count": len(artifacts)})


def verify_provider_mapping() -> VerificationResult:
    """Verify the provider mapping contracts and status derivation."""
    from .provider_mapping import (
        TARGET_SPORTS,
        ProviderMappingStatus,
        build_provider_mapping_plan,
        validate_mapping_plan,
        default_route_specs,
    )

    failed: list[str] = []

    # 1. Target sports must exactly match seven sports
    plan_empty = build_provider_mapping_plan({})
    sports = set(plan_empty.get("target_sports", []))
    if sports != set(TARGET_SPORTS):
        failed.append("target_sports_mismatch")

    # 2. No route has live_call_allowed=True, production_selectable=True, or betting_decisions_enabled=True
    for spec in default_route_specs():
        if spec.live_call_allowed:
            failed.append(f"spec_live_call_allowed_true:{spec.route_key}")
        if spec.production_selectable:
            failed.append(f"spec_production_selectable_true:{spec.route_key}")
        if spec.betting_decisions_enabled:
            failed.append(f"spec_betting_decisions_enabled_true:{spec.route_key}")
        # Odds/predictions/picks/stakes/recommendations/edges are forbidden in proof_fields_required
        for forbidden in ["odds", "prediction", "pick", "stake", "edge", "recommendation"]:
            if any(forbidden in f.lower() for f in spec.proof_fields_required):
                failed.append(f"forbidden_proof_field_in_spec:{spec.route_key}:{forbidden}")

    # Check status derivation invariants:
    # 3. Missing API-Sports env keys produce BLOCKED_NO_CREDENTIALS
    plan_no_keys = build_provider_mapping_plan({})
    for sport in ["basketball", "volleyball", "hockey", "tennis"]:
        items = plan_no_keys["provider_mapping_by_sport"].get(sport, [])
        if not items:
            failed.append(f"missing_mapping_for_sport:{sport}")
        for item in items:
            if item["status"] != ProviderMappingStatus.BLOCKED_NO_CREDENTIALS:
                failed.append(f"expected_blocked_no_credentials:{sport}:{item['status']}")

    # 4. PandaScore remains BLOCKED_PROVIDER_TERMS_OR_SCOPE even if PANDASCORE_TOKEN is present
    plan_pandascore_token = build_provider_mapping_plan({"PANDASCORE_TOKEN": "secret"})
    for sport in ["cs2", "dota2", "valorant"]:
        items = plan_pandascore_token["provider_mapping_by_sport"].get(sport, [])
        if not items:
            failed.append(f"missing_mapping_for_sport:{sport}")
        for item in items:
            if item["status"] != ProviderMappingStatus.BLOCKED_PROVIDER_TERMS_OR_SCOPE:
                failed.append(f"expected_blocked_provider_terms_or_scope:{sport}:{item['status']}")

    # 5. A sport-specific API-Sports env key can produce MAPPING_READY_FOR_SANITIZED_PROBE
    plan_basketball_key = build_provider_mapping_plan({"API_BASKETBALL_KEY": "secret"})
    basket_items = plan_basketball_key["provider_mapping_by_sport"].get("basketball", [])
    for item in basket_items:
        if item["status"] != ProviderMappingStatus.MAPPING_READY_FOR_SANITIZED_PROBE:
            failed.append(f"expected_mapping_ready_for_sanitized_probe:basketball:{item['status']}")
        if item["sanitized_probe_only"] is not True:
            failed.append("expected_sanitized_probe_only_true")
        if item["production_selectable"] is not False:
            failed.append("expected_production_selectable_false")

    # 6. Validate the plan structure itself
    errors = validate_mapping_plan(plan_empty)
    if errors:
        failed.extend(errors)

    metrics = {
        "target_sports_count": len(TARGET_SPORTS),
        "route_specs_count": len(default_route_specs()),
    }

    return VerificationResult(
        verdict="PASS" if not failed else "FAIL",
        failed_requirements=failed,
        metrics=metrics,
    )


def verify_provider_probes() -> VerificationResult:
    """Verify provider probe policy and runner invariants."""
    from .provider_mapping import (
        TARGET_SPORTS,
        build_mapping_artifact,
        default_route_specs,
    )
    from .provider_probe import (
        ProviderProbeArtifact,
        ProviderProbePolicy,
        ProviderProbeStatus,
        run_provider_probe,
    )
    from .provider_corpus import contains_raw_secret

    failed: list[str] = []

    # 1. Verify default policies have the required defaults
    for spec in default_route_specs():
        policy = ProviderProbePolicy(
            provider_key=spec.provider_key,
            sport=spec.sport,
            route_key=spec.route_key,
        )
        if policy.allow_real_network is not False:
            failed.append(f"default_allow_real_network_not_false:{spec.route_key}")
        if policy.max_requests > 1:
            failed.append(f"default_max_requests_gt_1:{spec.route_key}")
        if policy.sanitized_probe_only is not True:
            failed.append(f"default_sanitized_probe_only_not_true:{spec.route_key}")
        if policy.production_selectable is not False:
            failed.append(f"default_production_selectable_not_false:{spec.route_key}")
        if policy.betting_decisions_enabled is not False:
            failed.append(f"default_betting_decisions_enabled_not_false:{spec.route_key}")
        if policy.terms_review_approved is not False:
            failed.append(f"default_terms_review_approved_not_false:{spec.route_key}")

    # 2. Check strict validation limits of ProviderProbePolicy
    try:
        ProviderProbePolicy("key", "sport", "route", max_requests=2)
        failed.append("policy_did_not_reject_max_requests_gt_1")
    except ValueError:
        pass

    try:
        ProviderProbePolicy("key", "sport", "route", sanitized_probe_only=False)
        failed.append("policy_did_not_reject_sanitized_probe_only_false")
    except ValueError:
        pass

    try:
        ProviderProbePolicy("key", "sport", "route", production_selectable=True)
        failed.append("policy_did_not_reject_production_selectable_true")
    except ValueError:
        pass

    try:
        ProviderProbePolicy("key", "sport", "route", betting_decisions_enabled=True)
        failed.append("policy_did_not_reject_betting_decisions_enabled_true")
    except ValueError:
        pass

    # 3. Check strict validation of ProviderProbeArtifact
    try:
        ProviderProbeArtifact(
            artifact_id="id", sport="sport", provider_key="key", route_key="route",
            status=ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN,
            source_mapping_status="READY", request_method="GET", request_url_template="url",
            proof_fields_observed=("field",)
        )
        failed.append("artifact_did_not_reject_observed_fields_on_dry_run")
    except ValueError:
        pass

    # 4. Check runner execution for standard inputs
    # Without credentials or terms approval, runner maps appropriately
    for spec in default_route_specs():
        mapping = build_mapping_artifact(spec, {})
        policy = ProviderProbePolicy(
            provider_key=spec.provider_key,
            sport=spec.sport,
            route_key=spec.route_key,
            terms_review_approved=(spec.provider_key == "api-sports-family"),
        )
        artifact = run_provider_probe(mapping, policy, {})

        # Verify invariants
        if artifact.production_selectable:
            failed.append(f"artifact_production_selectable_true:{spec.route_key}")
        if artifact.betting_decisions_enabled:
            failed.append(f"artifact_betting_decisions_enabled_true:{spec.route_key}")
        if artifact.live_call_made:
            failed.append(f"artifact_live_call_made_true_by_default:{spec.route_key}")
        if artifact.provider_access_attempted:
            failed.append(f"artifact_provider_access_attempted_true_by_default:{spec.route_key}")

        # Verify secrets/tokens/headers checking
        payload = dict(artifact.to_jsonable())
        for key in ["status", "source_mapping_status", "artifact_id", "blocked_reason", "request_url_template", "evidence_refs"]:
            if key in payload:
                payload[key] = "<redacted>"
        if "sanitized_response_envelope" in payload:
            payload["sanitized_response_envelope"] = {"status": "<redacted>"}
        if contains_raw_secret(payload):
            failed.append(f"raw_secret_in_probe_artifact:{spec.route_key}")

        # Check status mapping
        if spec.provider_key == "api-sports-family":
            if artifact.status != ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS:
                failed.append(f"expected_blocked_no_credentials:{spec.route_key}:{artifact.status}")
        else: # pandascore
            if artifact.status != ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE:
                failed.append(f"expected_blocked_provider_terms_or_scope:{spec.route_key}:{artifact.status}")

    metrics = {
        "target_sports_count": len(TARGET_SPORTS),
        "route_specs_count": len(default_route_specs()),
    }

    return VerificationResult(
        verdict="PASS" if not failed else "FAIL",
        failed_requirements=failed,
        metrics=metrics,
    )


def verify_provider_access_gate() -> VerificationResult:
    """Verify provider access gate policies, status derivation, and invariants in Pass H."""
    from .provider_authorization import (
        TARGET_SPORTS,
        ProviderAuthorizationStatus,
        build_authorization_report,
        default_authorization_specs,
        validate_authorization_report,
    )

    failed: list[str] = []

    # 1. Check default authorization specs and their invariants
    specs = default_authorization_specs()
    sports_covered = {s.sport for s in specs}
    if sports_covered != set(TARGET_SPORTS):
        failed.append("target_sports_mismatch_in_specs")

    for spec in specs:
        if spec.allow_real_network:
            failed.append(f"spec_allow_real_network_true:{spec.sport}")
        if spec.max_requests > 1:
            failed.append(f"spec_max_requests_gt_1:{spec.sport}")
        if spec.production_selectable:
            failed.append(f"spec_production_selectable_true:{spec.sport}")
        if spec.betting_decisions_enabled:
            failed.append(f"spec_betting_decisions_enabled_true:{spec.sport}")

    # 2. Check default report state (empty env)
    report_empty = build_authorization_report({})
    if report_empty.get("live_calls_made") is not False:
        failed.append("live_calls_made_not_false_by_default")
    if report_empty.get("provider_access_attempted") is not False:
        failed.append("provider_access_attempted_not_false_by_default")

    # All sports must be BLOCKED_NO_CREDENTIALS in default state
    status_by_sport = report_empty.get("status_by_sport", {})
    for sport in TARGET_SPORTS:
        status = status_by_sport.get(sport)
        if status != ProviderAuthorizationStatus.BLOCKED_NO_CREDENTIALS:
            failed.append(f"expected_blocked_no_credentials:{sport}:{status}")

    # 3. Check report validation against default state
    errors = validate_authorization_report(report_empty)
    if errors:
        failed.extend(errors)

    metrics = {
        "target_sports_count": len(TARGET_SPORTS),
        "specs_count": len(specs),
    }

    return VerificationResult(
        verdict="PASS" if not failed else "FAIL",
        failed_requirements=failed,
        metrics=metrics,
    )


def verify_single_flight_probes() -> VerificationResult:
    """Verify single-flight probe contracts, status derivation, and report invariants."""
    from .single_flight_probe import (
        TARGET_SPORTS,
        SingleFlightProbeStatus,
        SingleFlightProbePolicy,
        SingleFlightProbeArtifact,
        default_policy_for_sport,
        build_default_single_flight_report,
        validate_single_flight_report,
    )

    failed: list[str] = []

    # 1. Target sports must cover exactly seven target sports
    if set(TARGET_SPORTS) != {"basketball", "volleyball", "hockey", "tennis", "cs2", "dota2", "valorant"}:
        failed.append("target_sports_mismatch")

    # 2. Check defaults in default policy
    for sport in TARGET_SPORTS:
        policy = default_policy_for_sport(sport)
        if policy.allow_real_network is not False:
            failed.append(f"default_allow_real_network_not_false:{sport}")
        if policy.max_requests != 1:
            failed.append(f"default_max_requests_not_1:{sport}")
        if policy.sanitized_probe_only is not True:
            failed.append(f"default_sanitized_probe_only_not_true:{sport}")
        if policy.production_selectable is not False:
            failed.append(f"default_production_selectable_not_false:{sport}")
        if policy.betting_decisions_enabled is not False:
            failed.append(f"default_betting_decisions_enabled_not_false:{sport}")

    # 3. Check strict policy validation limits
    try:
        SingleFlightProbePolicy("basketball", "api-sports-family", "api_basketball_games", "status", "status", max_requests=2)
        failed.append("policy_did_not_reject_max_requests_not_1")
    except ValueError:
        pass

    try:
        SingleFlightProbePolicy("basketball", "api-sports-family", "api_basketball_games", "status", "status", sanitized_probe_only=False)
        failed.append("policy_did_not_reject_sanitized_probe_only_false")
    except ValueError:
        pass

    try:
        SingleFlightProbePolicy("basketball", "api-sports-family", "api_basketball_games", "status", "status", production_selectable=True)
        failed.append("policy_did_not_reject_production_selectable_true")
    except ValueError:
        pass

    try:
        SingleFlightProbePolicy("basketball", "api-sports-family", "api_basketball_games", "status", "status", betting_decisions_enabled=True)
        failed.append("policy_did_not_reject_betting_decisions_enabled_true")
    except ValueError:
        pass

    # 4. Check strict artifact validation limits
    try:
        SingleFlightProbeArtifact(
            artifact_id="id", sport="basketball", provider_key="key", route_key="route",
            status=SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_ACCESS_GATE,
            source_access_status="BLOCKED", source_mapping_status="BLOCKED",
            request_method="GET", request_url_template="url",
            sanitized_request_metadata={}, sanitized_response_envelope={},
            proof_fields_observed=("fixture_id",), missing_proof_fields=(),
            live_call_made=False, provider_access_attempted=False, max_requests=1,
            blocked_reason="blocked", production_selectable=False, betting_decisions_enabled=False
        )
        failed.append("artifact_did_not_reject_observed_fields_when_blocked")
    except ValueError:
        pass

    try:
        SingleFlightProbeArtifact(
            artifact_id="id", sport="basketball", provider_key="key", route_key="route",
            status=SingleFlightProbeStatus.SINGLE_FLIGHT_RESULT_CAPTURED_SANITIZED,
            source_access_status="AUTHORIZED", source_mapping_status="READY",
            request_method="GET", request_url_template="url",
            sanitized_request_metadata={}, sanitized_response_envelope={},
            proof_fields_observed=("fixture_id",), missing_proof_fields=(),
            live_call_made=False, provider_access_attempted=True, max_requests=1,
            blocked_reason="", production_selectable=False, betting_decisions_enabled=False
        )
        failed.append("artifact_did_not_reject_captured_status_without_live_call")
    except ValueError:
        pass

    # 5. Validate the default report structure
    report = build_default_single_flight_report()
    errors = validate_single_flight_report(report)
    if errors:
        failed.extend(errors)

    # Validate detailed requirements:
    # - default reports cover exactly seven sports
    if len(report.get("target_sports", [])) != 7:
        failed.append("default_report_must_cover_exactly_seven_sports")

    # - default reports have no live calls and no provider access attempted
    if report.get("live_calls_made") is not False:
        failed.append("default_report_must_have_no_live_calls")
    if report.get("provider_access_attempted") is not False:
        failed.append("default_report_must_have_no_provider_access_attempted")

    # - no production activation and no betting decisions
    if report.get("production_activation") is not False:
        failed.append("production_activation_not_false")
    if report.get("betting_decisions") is not False:
        failed.append("betting_decisions_not_false")

    for sport, items in report.get("single_flight_probe_by_sport", {}).items():
        for item in items:
            # - source_probe_status is present in every artifact
            if "source_probe_status" not in item:
                failed.append(f"source_probe_status_missing:{sport}")

            # - no artifact can reach transport unless source_probe_status == SANITIZED_PROBE_READY_DRY_RUN
            # Transport is reached/attempted if live_call_made or provider_access_attempted is true
            if (item.get("live_call_made") or item.get("provider_access_attempted")):
                if item.get("source_probe_status") != "SANITIZED_PROBE_READY_DRY_RUN":
                    failed.append(f"transport_attempted_without_dry_run_ready:{sport}")

            # - raw_payload_persisted=false
            env = item.get("sanitized_response_envelope", {})
            if env.get("raw_payload_persisted") is not False:
                failed.append(f"raw_payload_persisted_not_false:{sport}")

            if item.get("production_selectable") is not False:
                failed.append(f"production_selectable_must_be_false:{sport}")
            if item.get("betting_decisions_enabled") is not False:
                failed.append(f"betting_decisions_enabled_must_be_false:{sport}")

    # 6. Verify default report maps all sports to SINGLE_FLIGHT_BLOCKED_ACCESS_GATE
    for sport in TARGET_SPORTS:
        status = report["status_by_sport"].get(sport)
        if status != SingleFlightProbeStatus.SINGLE_FLIGHT_BLOCKED_ACCESS_GATE:
            failed.append(f"default_report_sport_not_blocked_access_gate:{sport}:{status}")

    metrics = {
        "target_sports_count": len(TARGET_SPORTS),
        "total_policies_checked": len(TARGET_SPORTS),
    }

    return VerificationResult(
        verdict="PASS" if not failed else "FAIL",
        failed_requirements=failed,
        metrics=metrics,
    )




