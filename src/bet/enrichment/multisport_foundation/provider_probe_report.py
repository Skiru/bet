from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

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

def default_probe_policies(env: dict[str, str] | None = None) -> list[ProviderProbePolicy]:
    # Create probe policies for all route specs
    policies = []
    for spec in default_route_specs():
        # terms_review_approved: True for api-sports-family (no review needed, only credentials), False for pandascore (terms/access review needed)
        terms_approved = (spec.provider_key == "api-sports-family")
        policies.append(ProviderProbePolicy(
            provider_key=spec.provider_key,
            sport=spec.sport,
            route_key=spec.route_key,
            allow_real_network=False,
            terms_review_approved=terms_approved,
            max_requests=1,
            timeout_seconds=10.0,
            sanitized_probe_only=True,
            production_selectable=False,
            betting_decisions_enabled=False,
            notes=f"Default probe policy for {spec.sport} on {spec.provider_key}"
        ))
    return policies

def build_probe_plan_payload(policies: list[ProviderProbePolicy] | None = None) -> dict[str, Any]:
    if policies is None:
        policies = default_probe_policies()

    by_sport: dict[str, list[dict[str, Any]]] = {sport: [] for sport in TARGET_SPORTS}
    for policy in policies:
        # Covert policy to a dict
        policy_dict = {
            "provider_key": policy.provider_key,
            "sport": policy.sport,
            "route_key": policy.route_key,
            "allow_real_network": policy.allow_real_network,
            "terms_review_approved": policy.terms_review_approved,
            "max_requests": policy.max_requests,
            "timeout_seconds": policy.timeout_seconds,
            "sanitized_probe_only": policy.sanitized_probe_only,
            "production_selectable": policy.production_selectable,
            "betting_decisions_enabled": policy.betting_decisions_enabled,
            "notes": policy.notes,
        }
        by_sport[policy.sport].append(policy_dict)

    return {
        "phase_id": "MULTISPORT_PASS_F_BOUNDED_SANITIZED_PROBE_RUNNER",
        "target_sports": list(TARGET_SPORTS),
        "live_calls_allowed": False,
        "production_activation": False,
        "betting_decisions": False,
        "provider_probe_policies_by_sport": by_sport,
    }

def build_probe_results_payload(
    policies: list[ProviderProbePolicy] | None = None,
    env: dict[str, str] | None = None
) -> dict[str, Any]:
    if env is None:
        # Use only presence of keys in os.environ, mock values for safety,
        # never actual secrets in env.
        env = {k: "present" for k in os.environ if os.environ.get(k)}

    if policies is None:
        policies = default_probe_policies()

    by_sport: dict[str, list[dict[str, Any]]] = {sport: [] for sport in TARGET_SPORTS}

    policy_by_route = {p.route_key: p for p in policies}

    for spec in default_route_specs():
        mapping = build_mapping_artifact(spec, env)
        policy = policy_by_route.get(spec.route_key)
        if policy is None:
            # Fallback
            policy = ProviderProbePolicy(
                provider_key=spec.provider_key,
                sport=spec.sport,
                route_key=spec.route_key,
                allow_real_network=False,
                terms_review_approved=(spec.provider_key == "api-sports-family"),
            )

        artifact = run_provider_probe(mapping, policy, env)
        by_sport[spec.sport].append(artifact.to_jsonable())

    return {
        "phase_id": "MULTISPORT_PASS_F_BOUNDED_SANITIZED_PROBE_RUNNER",
        "target_sports": list(TARGET_SPORTS),
        "live_calls_allowed": False,
        "production_activation": False,
        "betting_decisions": False,
        "provider_probe_results_by_sport": by_sport,
    }

def build_pass_f_summary_payload(
    results_payload: dict[str, Any]
) -> dict[str, Any]:
    statuses: dict[str, str] = {}
    metrics = {
        "total_target_sports": len(TARGET_SPORTS),
        "sanitized_probe_ready_dry_run_count": 0,
        "sanitized_probe_blocked_no_credentials_count": 0,
        "sanitized_probe_blocked_provider_terms_or_scope_count": 0,
        "sanitized_probe_blocked_mapping_not_ready_count": 0,
        "sanitized_probe_blocked_provider_access_count": 0,
        "sanitized_probe_result_captured_sanitized_count": 0,
        "live_calls_allowed": False,
        "production_activation": False,
        "betting_decisions": False,
    }

    results_by_sport = results_payload.get("provider_probe_results_by_sport", {})
    for sport in TARGET_SPORTS:
        items = results_by_sport.get(sport, [])
        if items:
            primary_status = items[0]["status"]
            statuses[sport] = primary_status
        else:
            statuses[sport] = "SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY"

        for item in items:
            status = item["status"]
            if status == ProviderProbeStatus.SANITIZED_PROBE_READY_DRY_RUN:
                metrics["sanitized_probe_ready_dry_run_count"] += 1
            elif status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_NO_CREDENTIALS:
                metrics["sanitized_probe_blocked_no_credentials_count"] += 1
            elif status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_TERMS_OR_SCOPE:
                metrics["sanitized_probe_blocked_provider_terms_or_scope_count"] += 1
            elif status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_MAPPING_NOT_READY:
                metrics["sanitized_probe_blocked_mapping_not_ready_count"] += 1
            elif status == ProviderProbeStatus.SANITIZED_PROBE_BLOCKED_PROVIDER_ACCESS:
                metrics["sanitized_probe_blocked_provider_access_count"] += 1
            elif status == ProviderProbeStatus.SANITIZED_PROBE_RESULT_CAPTURED_SANITIZED:
                metrics["sanitized_probe_result_captured_sanitized_count"] += 1

    return {
        "summary_version": "ms-f-summary-v1",
        "target_sports": list(TARGET_SPORTS),
        "provider_probe_statuses": statuses,
        "metrics": metrics,
    }

def write_pass_f_reports(output_dir: str | Path, env: dict[str, str] | None = None) -> None:
    base_path = Path(output_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    if env is None:
        env = {k: "present" for k in os.environ if os.environ.get(k)}

    policies = default_probe_policies()
    plan_payload = build_probe_plan_payload(policies)
    results_payload = build_probe_results_payload(policies, env)
    summary_payload = build_pass_f_summary_payload(results_payload)

    # Validate output plan
    plan_file = base_path / "provider_probe_plan.json"
    plan_file.write_text(json.dumps(plan_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    results_file = base_path / "provider_probe_results_by_sport.json"
    results_file.write_text(json.dumps(results_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary_file = base_path / "pass_f_summary.json"
    summary_file.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
