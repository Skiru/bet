from pathlib import Path

from .contracts import ActivationArtifactPaths, ActivationCandidate, ActivationPolicy
from .gate import assert_candidate_is_shadow_only, evaluate_activation_gate
from .loader import load_source_bundle


DEFAULT_SHADOW_ROOT = Path("reports/football_data_foundation/source_bound_shadow")


def build_football_source_bound_activation_candidate(
    project_root: Path,
    fixture_slug: str,
    policy: ActivationPolicy | None = None,
    shadow_root: Path | None = None,
) -> ActivationCandidate:
    effective_policy = policy or ActivationPolicy.strict_worldcup_acceptance()
    effective_shadow_root = shadow_root or project_root / DEFAULT_SHADOW_ROOT
    artifacts = ActivationArtifactPaths.from_shadow_root(effective_shadow_root, fixture_slug)
    bundle = load_source_bundle(artifacts, effective_policy.required_providers)
    snapshot = bundle["snapshot"]
    source_verifier = bundle["verifier"]
    provider_fact_counts = bundle["provider_fact_counts"]
    sqlite_summary = bundle["sqlite_summary"]
    decision, failures = evaluate_activation_gate(
        fixture_slug=fixture_slug,
        snapshot=snapshot,
        verifier=source_verifier,
        provider_fact_counts=provider_fact_counts,
        sqlite_summary=sqlite_summary,
        policy=effective_policy,
    )
    provider_ids = {str(k): str(v) for k, v in dict(snapshot.get("provider_ids") or {}).items()}
    score = {str(k): int(v) for k, v in dict(snapshot.get("score") or {}).items() if isinstance(v, int)}
    conflicts = list(snapshot.get("conflicts") or [])
    candidate = ActivationCandidate(
        fixture_slug=fixture_slug,
        source_artifacts=artifacts,
        provider_ids=provider_ids,
        provider_fact_counts=provider_fact_counts,
        score=score,
        conflicts=conflicts,
        shadow_status=str(snapshot.get("shadow_status") or ""),
        source_bound_verifier_verdict=str(source_verifier.get("verdict") or "UNKNOWN"),
        sqlite_summary=sqlite_summary,
        decision=decision,
        policy=effective_policy,
    )
    if failures:
        raise ValueError("Activation candidate gate failed: " + "; ".join(failures))
    assert_candidate_is_shadow_only(candidate)
    return candidate
