from typing import Any

from .contracts import (
    ACTIVATION_CANDIDATE_STATUS,
    SHADOW_READY_STATUS,
    ActivationCandidate,
    ActivationDecision,
    ActivationPolicy,
)


def _source_verifier_verdict(verifier: dict[str, Any]) -> str:
    value = verifier.get("verdict") or verifier.get("VERIFIER_VERDICT")
    if isinstance(value, str):
        return value.upper()
    return "UNKNOWN"


def _snapshot_conflicts(snapshot: dict[str, Any]) -> list[Any]:
    value = snapshot.get("conflicts")
    if isinstance(value, list):
        return value
    return []


def _snapshot_provider_ids(snapshot: dict[str, Any]) -> dict[str, str]:
    value = snapshot.get("provider_ids")
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _snapshot_score(snapshot: dict[str, Any]) -> dict[str, int]:
    value = snapshot.get("score")
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key in ("home", "away"):
        if isinstance(value.get(key), int):
            result[key] = int(value[key])
    return result


def evaluate_activation_gate(
    *,
    fixture_slug: str,
    snapshot: dict[str, Any],
    verifier: dict[str, Any],
    provider_fact_counts: dict[str, int],
    sqlite_summary: dict[str, Any],
    policy: ActivationPolicy,
) -> tuple[ActivationDecision, list[str]]:
    failures: list[str] = []
    provider_ids = _snapshot_provider_ids(snapshot)
    score = _snapshot_score(snapshot)
    conflicts = _snapshot_conflicts(snapshot)
    shadow_status = str(snapshot.get("shadow_status") or "")
    source_verdict = _source_verifier_verdict(verifier)

    if policy.expected_fixture_slug is not None and fixture_slug != policy.expected_fixture_slug:
        failures.append("fixture_slug_mismatch")
    if shadow_status != SHADOW_READY_STATUS:
        failures.append("shadow_status_not_ready")
    if source_verdict != "PASS":
        failures.append("source_bound_verifier_not_pass")
    if policy.expected_score is not None and score != policy.expected_score:
        failures.append("score_mismatch")
    if conflicts:
        failures.append("conflicts_present")
    if snapshot.get("production_selectable") is not False:
        failures.append("production_selectable_not_false")
    if snapshot.get("manual_authorization_required") is not True:
        failures.append("manual_authorization_required_not_true")

    for provider in policy.required_providers:
        if provider not in provider_ids:
            failures.append(f"missing_provider_id:{provider}")
        if provider_fact_counts.get(provider, 0) <= 0:
            failures.append(f"missing_provider_fact_count:{provider}")
        if sqlite_summary.get("provider_fact_rows", {}).get(provider, 0) <= 0:
            failures.append(f"sqlite_missing_provider_rows:{provider}")

    if policy.allow_production_selectable:
        failures.append("policy_must_not_allow_production_selectable")
    if policy.allow_production_db_writes:
        failures.append("policy_must_not_allow_production_db_writes")
    if policy.allow_betting_decisions:
        failures.append("policy_must_not_allow_betting_decisions")
    if policy.allow_live_network:
        failures.append("policy_must_not_allow_live_network")

    if failures:
        return (
            ActivationDecision.shadow_only("Activation candidate blocked: " + "; ".join(failures)),
            failures,
        )

    return (
        ActivationDecision.shadow_only(
            "Accepted five-provider source-bound shadow bundle exposed as a shadow-only activation candidate."
        ),
        [],
    )


def assert_candidate_is_shadow_only(candidate: ActivationCandidate) -> None:
    payload = candidate.to_json()
    decision = payload["decision"]
    if decision["status"] != ACTIVATION_CANDIDATE_STATUS:
        raise ValueError("Activation candidate has invalid status")
    if decision["selectable_for_production"] is not False:
        raise ValueError("Activation candidate became selectable for production")
    if decision["manual_authorization_required"] is not True:
        raise ValueError("Activation candidate dropped manual authorization")
    if decision["production_db_write_allowed"] is not False:
        raise ValueError("Activation candidate allows production DB writes")
    if decision["betting_decision_allowed"] is not False:
        raise ValueError("Activation candidate allows betting decisions")
    if decision["live_network_allowed"] is not False:
        raise ValueError("Activation candidate allows live network")
