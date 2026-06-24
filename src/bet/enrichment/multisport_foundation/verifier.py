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
