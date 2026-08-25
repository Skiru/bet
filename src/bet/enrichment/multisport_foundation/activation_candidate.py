from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ActivationCandidateArtifact:
    artifact_id: str
    sport: str
    status: str
    source_pass_b_status: str
    source_shadow_report_path: str
    source_keys: tuple[str, ...]
    corpus_ids: tuple[str, ...]
    activation_candidate: bool
    manual_authorization_required: bool = True
    production_selectable: bool = False
    betting_decisions_enabled: bool = False
    blocked_reason: str | None = None
    required_manual_steps: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.manual_authorization_required:
            raise ValueError("manual_authorization_required must always be true.")
        if self.production_selectable:
            raise ValueError("production_selectable must always be false.")
        if self.betting_decisions_enabled:
            raise ValueError("betting_decisions_enabled must always be false.")
        if self.activation_candidate and self.status != "ACTIVATION_CANDIDATE_SHADOW_ONLY":
            raise ValueError("activation_candidate can only be true when status is ACTIVATION_CANDIDATE_SHADOW_ONLY.")

        if self.status == "ACTIVATION_CANDIDATE_SHADOW_ONLY":
            if self.source_pass_b_status != "SOURCE_BOUND_SHADOW_READY":
                raise ValueError("ACTIVATION_CANDIDATE_SHADOW_ONLY requires Pass B status to be SOURCE_BOUND_SHADOW_READY.")
            if not self.source_keys or not self.corpus_ids:
                raise ValueError("ACTIVATION_CANDIDATE_SHADOW_ONLY requires non-empty source_keys and corpus_ids.")

        if self.source_pass_b_status == "BLOCKED_PROVIDER_MAPPING_NOT_FOUND" and self.status != "BLOCKED_NO_REAL_PROVIDER_ACCESS":
            raise ValueError("BLOCKED_PROVIDER_MAPPING_NOT_FOUND must map to BLOCKED_NO_REAL_PROVIDER_ACCESS.")
        if self.source_pass_b_status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE" and self.status != "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
            raise ValueError("BLOCKED_PROVIDER_TERMS_OR_SCOPE must map to BLOCKED_PROVIDER_TERMS_OR_SCOPE.")
        if self.source_pass_b_status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT" and self.status != "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING":
            raise ValueError("REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT must map to REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING.")

    def to_json(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "sport": self.sport,
            "status": self.status,
            "source_pass_b_status": self.source_pass_b_status,
            "source_shadow_report_path": self.source_shadow_report_path,
            "source_keys": list(self.source_keys),
            "corpus_ids": list(self.corpus_ids),
            "activation_candidate": self.activation_candidate,
            "manual_authorization_required": self.manual_authorization_required,
            "production_selectable": self.production_selectable,
            "betting_decisions_enabled": self.betting_decisions_enabled,
            "blocked_reason": self.blocked_reason,
            "required_manual_steps": list(self.required_manual_steps),
            "evidence_refs": list(self.evidence_refs),
        }


def build_activation_candidate(
    sport: str,
    pass_b_status: str,
    source_keys: tuple[str, ...],
    corpus_ids: tuple[str, ...],
    source_shadow_report_path: str = "reports/multisport_foundation/pass_b/source_bound_shadow_status_by_sport.json",
    blocked_reason: str | None = None,
) -> ActivationCandidateArtifact:
    """Build an ActivationCandidateArtifact from Pass B status and inputs."""

    if pass_b_status == "SOURCE_BOUND_SHADOW_READY" and source_keys and corpus_ids:
        status = "ACTIVATION_CANDIDATE_SHADOW_ONLY"
        activation_candidate = True
        derived_blocked_reason = None
        required_manual_steps = (
            "Verify shadow performance and request owner manual authorization in admin dashboard.",
        )
    elif pass_b_status == "REAL_PROVIDER_ACCESS_OBSERVED_BUT_MAPPING_INSUFFICIENT":
        status = "REAL_PROVIDER_ACCESS_OBSERVED_BUT_LIVE_SHADOW_BLOCKED_INSUFFICIENT_MAPPING"
        activation_candidate = False
        derived_blocked_reason = blocked_reason or "Real provider access observed, but mapping is insufficient."
        required_manual_steps = (
            "Implement complete participant and event mapping in provider adapter.",
        )
    elif pass_b_status == "BLOCKED_PROVIDER_TERMS_OR_SCOPE":
        status = "BLOCKED_PROVIDER_TERMS_OR_SCOPE"
        activation_candidate = False
        derived_blocked_reason = blocked_reason or "Access blocked due to provider terms or scope."
        required_manual_steps = (
            "Perform legal and scope review for this provider.",
        )
    else:
        # Treats: BLOCKED_PROVIDER_MAPPING_NOT_FOUND, BLOCKED_NO_CREDENTIALS,
        # BLOCKED_PROVIDER_ACCESS, or missing/malformed status as BLOCKED_NO_REAL_PROVIDER_ACCESS
        status = "BLOCKED_NO_REAL_PROVIDER_ACCESS"
        activation_candidate = False
        derived_blocked_reason = blocked_reason or f"Access blocked because Pass B status is {pass_b_status}."
        required_manual_steps = (
            "Verify provider credentials, add sport endpoint mapping, or resolve access block.",
        )

    evidence_refs = (source_shadow_report_path,)

    return ActivationCandidateArtifact(
        artifact_id=f"msc-activation-{sport}",
        sport=sport,
        status=status,
        source_pass_b_status=pass_b_status,
        source_shadow_report_path=source_shadow_report_path,
        source_keys=source_keys,
        corpus_ids=corpus_ids,
        activation_candidate=activation_candidate,
        blocked_reason=derived_blocked_reason,
        required_manual_steps=required_manual_steps,
        evidence_refs=evidence_refs,
    )
