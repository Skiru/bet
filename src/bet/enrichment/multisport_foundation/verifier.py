from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import OutcomeStatus, SportKey
from .plan import build_multisport_wave_plan

REQUIRED_SPORTS = {sport for sport in SportKey}
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


def verify_plan() -> VerificationResult:
    plan = build_multisport_wave_plan()
    failed: list[str] = []

    if set(plan.profiles) != REQUIRED_SPORTS:
        missing = sorted(sport.value for sport in REQUIRED_SPORTS - set(plan.profiles))
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
