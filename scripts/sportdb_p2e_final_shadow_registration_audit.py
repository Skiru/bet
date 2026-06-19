#!/usr/bin/env python3
"""Final audit for the SportDB scope-limited shadow registration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


PHASE_ID = "P2E_A12_FINAL_SPORTDB_SHADOW_REGISTRATION_AUDIT"
PROMPT_VERSION = "v1_copy_safe_final_shadow_audit_hardened"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
DEFAULT_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_final_shadow_registration_audit_summary.json"
)
DEFAULT_A10_SHA = "a54bbf1fee0942821dc4ebe03f3ac3a65fd79543"
DEFAULT_A11_SHA = "e873dfde0211cf051f6c5f0e8cc1d554dd4e1f7b"
EXPECTED_A11_SUBJECT = "chore(football): register sportdb scope-limited shadow route"
MATRIX_PATH = "config/provider_capability_matrix.json"
ROUTING_PATH = "config/football_routing.yaml"
EXPECTED_A11_CHANGED_PATHS = [
    "certification/football/p2e_sportdb_scope_limited_shadow_registration_summary.json",
    "config/football_routing.yaml",
    "config/provider_capability_matrix.json",
    "scripts/sportdb_p2e_scope_limited_shadow_registration_validate.py",
    "tests/test_sportdb_scope_limited_shadow_registration.py",
]
EXPECTED_EXCLUDED_METRICS = ["successful_passes", "total_passes"]
REQUIRED_INPUT_PATHS = [
    "certification/football/p2e_sportdb_semantic_gap_review_certification_plan_summary.json",
    "certification/football/p2e_sportdb_scope_limited_shadow_registration_summary.json",
    MATRIX_PATH,
    ROUTING_PATH,
    "scripts/sportdb_p2e_scope_limited_shadow_registration_validate.py",
    "tests/test_sportdb_scope_limited_shadow_registration.py",
]
PASS_CLASSIFICATION = "SPORTDB_P2E_SHADOW_REGISTRATION_FINAL_AUDIT_PASS"
PASS_FINAL_VERDICT = "SPORTDB_P2E_CLOSED_AS_SCOPE_LIMITED_DETAILED_METRICS_SHADOW"
PASS_NEXT_STEP = (
    "NO_FURTHER_SPORTDB_P2E_ACTION_REQUIRED_UNLESS_USER_REQUESTS_PROMOTION_OR_ADDITIONAL_SCOPE"
)
REGISTERED_ROUTE = "detailed_metrics/sportdb/football:eng.1/current-season-completed/shadow"
REGISTERED_SCOPE = {
    "route": REGISTERED_ROUTE,
    "status": "CERTIFIED_SHADOW",
    "mode": "shadow",
    "certifiable_metric_scope": ["corners", "fouls", "offsides", "shots", "shots_on_target"],
    "excluded_metric_scope": EXPECTED_EXCLUDED_METRICS,
}


def a10_sha() -> str:
    return DEFAULT_A10_SHA


def a11_sha() -> str:
    return DEFAULT_A11_SHA


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return data


def git_text(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def load_text_at_revision(repo_root: Path, revision: str, relative_path: str) -> str:
    return git_text(repo_root, "show", f"{revision}:{relative_path}")


def load_json_at_revision(repo_root: Path, revision: str, relative_path: str) -> dict[str, Any]:
    data = json.loads(load_text_at_revision(repo_root, revision, relative_path))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object at {revision}:{relative_path}")
    return data


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "[]":
        return []
    return value


def parse_routing_text(text: str) -> dict[str, dict[str, list[dict[str, Any]]]]:
    routing: dict[str, dict[str, list[dict[str, Any]]]] = {}
    current_family = ""
    current_bucket = ""
    current_entry: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if stripped == "routing:":
            continue
        if indent == 2 and stripped.endswith(":"):
            current_family = stripped[:-1]
            routing.setdefault(current_family, {})
            current_bucket = ""
            current_entry = None
            continue
        if indent == 4 and stripped.endswith(":"):
            current_bucket = stripped[:-1]
            routing.setdefault(current_family, {})[current_bucket] = []
            current_entry = None
            continue
        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_bucket = key.strip()
            parsed_value = parse_scalar(value)
            routing.setdefault(current_family, {})[current_bucket] = (
                parsed_value if isinstance(parsed_value, list) else []
            )
            current_entry = None
            continue
        if indent == 6 and stripped == "[]":
            routing.setdefault(current_family, {})[current_bucket] = []
            current_entry = None
            continue
        if indent == 6 and stripped.startswith("- "):
            key, value = stripped[2:].split(":", 1)
            current_entry = {key.strip(): parse_scalar(value)}
            routing.setdefault(current_family, {}).setdefault(current_bucket, []).append(current_entry)
            continue
        if indent >= 8 and current_entry is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_entry[key.strip()] = parse_scalar(value)
    return routing


def validate_required_inputs(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_path in REQUIRED_INPUT_PATHS:
        if not (repo_root / relative_path).is_file():
            errors.append(f"required_input_missing:{relative_path}")
    for revision in [a10_sha(), a11_sha()]:
        try:
            git_text(repo_root, "rev-parse", "--verify", f"{revision}^{{commit}}")
        except Exception as exc:
            errors.append(f"required_commit_missing:{revision}:{type(exc).__name__}")
    return errors


def validate_a11_commit_identity(repo_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        parent = git_text(repo_root, "rev-parse", f"{a11_sha()}^").strip()
        if parent != a10_sha():
            errors.append(f"a11_parent_mismatch:expected={a10_sha()}:actual={parent}")
        subject = git_text(repo_root, "log", "-1", "--format=%s", a11_sha()).strip()
        if subject != EXPECTED_A11_SUBJECT:
            errors.append(f"a11_subject_mismatch:expected={EXPECTED_A11_SUBJECT}:actual={subject}")
    except Exception as exc:
        errors.append(f"a11_commit_identity_check_failed:{type(exc).__name__}")
    return errors


def validate_a11_changed_paths(repo_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        changed = sorted(
            line.strip()
            for line in git_text(repo_root, "show", "--name-only", "--format=", a11_sha()).splitlines()
            if line.strip()
        )
        if changed != sorted(EXPECTED_A11_CHANGED_PATHS):
            errors.append("a11_changed_paths_mismatch")
    except Exception as exc:
        errors.append(f"a11_changed_paths_check_failed:{type(exc).__name__}")
    return errors


def validate_a11_matrix_diff_no_accepted_provider_drift(repo_root: Path) -> list[str]:
    errors: list[str] = []
    try:
        before = load_json_at_revision(repo_root, a10_sha(), MATRIX_PATH)
        after = load_json_at_revision(repo_root, a11_sha(), MATRIX_PATH)
    except Exception as exc:
        return [f"a11_matrix_diff_read_failed:{type(exc).__name__}"]

    if set(before.keys()) != set(after.keys()):
        errors.append("a11_matrix_top_level_keys_mismatch")

    before_non_providers = {key: value for key, value in before.items() if key != "providers"}
    after_non_providers = {key: value for key, value in after.items() if key != "providers"}
    if before_non_providers != after_non_providers:
        errors.append("a11_matrix_non_provider_top_level_drift")

    before_providers = before.get("providers") if isinstance(before.get("providers"), dict) else {}
    after_providers = after.get("providers") if isinstance(after.get("providers"), dict) else {}
    if set(before_providers.keys()) != set(after_providers.keys()):
        errors.append("a11_matrix_provider_key_set_mismatch")

    changed_providers = [
        provider
        for provider in sorted(before_providers.keys())
        if before_providers.get(provider) != after_providers.get(provider)
    ]
    if changed_providers != ["sportdb"]:
        errors.append(
            "a11_matrix_changed_providers_invalid:" + ",".join(changed_providers or ["NONE"])
        )

    sportdb = after_providers.get("sportdb") if isinstance(after_providers.get("sportdb"), dict) else {}
    capabilities = sportdb.get("capabilities") if isinstance(sportdb.get("capabilities"), dict) else {}
    if set(capabilities.keys()) != {"detailed_metrics"}:
        errors.append("a11_matrix_capability_family_mismatch")

    entries = capabilities.get("detailed_metrics") if isinstance(capabilities.get("detailed_metrics"), list) else []
    if len(entries) != 1 or not isinstance(entries[0], dict):
        errors.append("a11_matrix_detailed_metrics_entry_invalid")
        return errors
    entry = entries[0]

    if entry.get("status") != "CERTIFIED_SHADOW":
        errors.append("a11_matrix_status_mismatch")
    if entry.get("competition_scope") != "football:eng.1":
        errors.append("a11_matrix_competition_scope_mismatch")
    if entry.get("season_scope") != "current-season-completed":
        errors.append("a11_matrix_season_scope_mismatch")
    if entry.get("mode") != "shadow":
        errors.append("a11_matrix_mode_mismatch")
    if entry.get("selectable_as_projection") is not False:
        errors.append("a11_matrix_selectable_as_projection_invalid")

    sportdb_text = json.dumps(sportdb, sort_keys=True)
    if "PRODUCTION_READY" in sportdb_text:
        errors.append("a11_matrix_production_ready_detected")
    if "CERTIFIED_SELECTABLE" in sportdb_text:
        errors.append("a11_matrix_certified_selectable_detected")
    if '"selectable_as_projection": true' in sportdb_text:
        errors.append("a11_matrix_selectable_as_projection_true_detected")

    certifiable_metric_scope = entry.get("certifiable_metric_scope") if isinstance(entry.get("certifiable_metric_scope"), list) else []
    for metric in EXPECTED_EXCLUDED_METRICS:
        if metric in certifiable_metric_scope:
            errors.append(f"a11_matrix_pass_metric_certifiable:{metric}")

    return errors


def _sportdb_locations(routing: dict[str, dict[str, list[dict[str, Any]]]]) -> list[tuple[str, str, dict[str, Any]]]:
    locations: list[tuple[str, str, dict[str, Any]]] = []
    for family, buckets in routing.items():
        for bucket, entries in buckets.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("provider") == "sportdb":
                    locations.append((family, bucket, entry))
    return locations


def validate_a11_routing_diff_no_production_promotion(repo_root: Path) -> list[str]:
    try:
        before_text = load_text_at_revision(repo_root, a10_sha(), ROUTING_PATH)
        after_text = load_text_at_revision(repo_root, a11_sha(), ROUTING_PATH)
        diff_text = git_text(repo_root, "diff", a10_sha(), a11_sha(), "--", ROUTING_PATH)
    except Exception as exc:
        return [f"a11_routing_diff_read_failed:{type(exc).__name__}"]

    errors: list[str] = []
    before = parse_routing_text(before_text)
    after = parse_routing_text(after_text)
    before_locations = _sportdb_locations(before)
    after_locations = _sportdb_locations(after)
    if before_locations:
        errors.append("a11_routing_diff_sportdb_present_before_a11")
    if len(after_locations) != 1:
        errors.append("a11_routing_diff_sportdb_entry_count_mismatch")
        return errors

    family, bucket, entry = after_locations[0]
    if family != "detailed_metrics":
        errors.append("a11_routing_diff_family_mismatch")
    if bucket not in {"shadow_routes", "candidate_routes"}:
        errors.append("a11_routing_diff_bucket_invalid")
    if entry.get("competition_scope") != "football:eng.1":
        errors.append("a11_routing_diff_competition_scope_mismatch")
    if entry.get("season_scope") != "current-season-completed":
        errors.append("a11_routing_diff_season_scope_mismatch")
    if entry.get("mode") != "shadow":
        errors.append("a11_routing_diff_mode_mismatch")
    if entry.get("selectable_status") != "CERTIFIED_SHADOW":
        errors.append("a11_routing_diff_selectable_status_mismatch")

    for routing_family, buckets in after.items():
        production_entries = buckets.get("production_routes") if isinstance(buckets, dict) else []
        if isinstance(production_entries, list) and any(
            isinstance(item, dict) and item.get("provider") == "sportdb" for item in production_entries
        ):
            errors.append(f"a11_routing_diff_production_route_detected:{routing_family}")

    added_lines = [
        line[1:].strip().lower()
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    added_text = "\n".join(added_lines)
    if "provider: sportdb" not in added_text:
        errors.append("a11_routing_diff_sportdb_route_not_added")
    for required_line in [
        "provider: sportdb",
        "competition_scope: football:eng.1",
        "season_scope: current-season-completed",
        "mode: shadow",
        "selectable_status: certified_shadow",
    ]:
        if required_line not in added_text:
            errors.append(f"a11_routing_diff_missing_added_line:{required_line}")

    return errors


def build_summary(
    *,
    required_input_errors: list[str],
    commit_identity_errors: list[str],
    changed_paths_errors: list[str],
    matrix_diff_errors: list[str],
    routing_diff_errors: list[str],
) -> dict[str, Any]:
    evidence_chain_complete = not (
        required_input_errors
        or commit_identity_errors
        or changed_paths_errors
        or matrix_diff_errors
        or routing_diff_errors
    )
    accepted_provider_drift_detected = any(
        "drift" in error or "changed_providers" in error for error in matrix_diff_errors
    )
    forbidden_promotion_detected = any(
        "production_route" in error or "certified_selectable" in error for error in routing_diff_errors
    ) or any("production_ready" in error or "certified_selectable" in error for error in matrix_diff_errors)
    selectable_as_projection = any("selectable_as_projection" in error for error in matrix_diff_errors)
    audit = {
        "evidence_chain_complete": evidence_chain_complete,
        "matrix_state_valid": not matrix_diff_errors,
        "routing_state_valid": not routing_diff_errors,
        "metric_scope_valid": not matrix_diff_errors,
        "accepted_provider_drift_detected": accepted_provider_drift_detected,
        "forbidden_promotion_detected": forbidden_promotion_detected,
        "production_route_added": any("production_route" in error for error in routing_diff_errors),
        "certified_selectable_added": any("certified_selectable" in error for error in matrix_diff_errors + routing_diff_errors),
        "selectable_as_projection": selectable_as_projection,
        "current_live_scope_added": False,
        "required_inputs_valid": not required_input_errors,
        "a11_commit_identity_valid": not commit_identity_errors,
        "a11_changed_paths_valid": not changed_paths_errors,
        "a11_matrix_diff_valid": not matrix_diff_errors,
        "a11_routing_diff_valid": not routing_diff_errors,
        "required_input_errors": required_input_errors,
        "a11_commit_identity_errors": commit_identity_errors,
        "a11_changed_paths_errors": changed_paths_errors,
        "a11_matrix_diff_errors": matrix_diff_errors,
        "a11_routing_diff_errors": routing_diff_errors,
    }
    blockers = [
        *required_input_errors,
        *commit_identity_errors,
        *changed_paths_errors,
        *matrix_diff_errors,
        *routing_diff_errors,
    ]
    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "protected_worktree": PROTECTED_WORKTREE,
        "provider": "sportdb",
        "mode": "final_audit_no_config_changes_no_live_calls",
        "previous_accepted_sha": a11_sha(),
        "a10_sha": a10_sha(),
        "a11_sha": a11_sha(),
        "audited_diff": f"{a10_sha()}..{a11_sha()}",
        "audit": audit,
        "classification": "UNKNOWN",
        "final_verdict": "BLOCKED",
        "registered_scope": REGISTERED_SCOPE,
        "certification": {
            "verdict": "BLOCKED_FINAL_SHADOW_REGISTRATION_AUDIT",
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
        },
        "blockers": blockers,
        "secret_safe": True,
        "final_review": "FAIL",
        "next_step": "BLOCKED_REVIEW_REQUIRED",
    }
    summary["classification"] = classify_summary(summary)
    if summary["classification"] == PASS_CLASSIFICATION:
        summary["final_verdict"] = PASS_FINAL_VERDICT
        summary["certification"]["verdict"] = "NOT_CERTIFIED_FINAL_SHADOW_REGISTRATION_AUDIT_ONLY"
        summary["final_review"] = "PASS"
        summary["next_step"] = PASS_NEXT_STEP
    return summary


def classify_summary(summary: dict[str, Any]) -> str:
    audit = summary.get("audit", {})
    if audit.get("required_inputs_valid") is not True:
        return "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_REQUIRED_INPUTS_INVALID"
    if audit.get("a11_commit_identity_valid") is not True:
        return "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_A11_COMMIT_IDENTITY_INVALID"
    if audit.get("a11_changed_paths_valid") is not True:
        return "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_A11_CHANGED_PATHS_INVALID"
    if audit.get("a11_matrix_diff_valid") is not True:
        return "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_A11_MATRIX_DIFF_INVALID"
    if audit.get("a11_routing_diff_valid") is not True:
        return "SPORTDB_P2E_FINAL_AUDIT_BLOCKED_A11_ROUTING_DIFF_INVALID"
    return PASS_CLASSIFICATION


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def audit_repository(repo_root: Path) -> dict[str, Any]:
    return build_summary(
        required_input_errors=validate_required_inputs(repo_root),
        commit_identity_errors=validate_a11_commit_identity(repo_root),
        changed_paths_errors=validate_a11_changed_paths(repo_root),
        matrix_diff_errors=validate_a11_matrix_diff_no_accepted_provider_drift(repo_root),
        routing_diff_errors=validate_a11_routing_diff_no_production_promotion(repo_root),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the hardened SportDB A11 shadow registration commit.")
    parser.add_argument("--out", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(PROTECTED_WORKTREE)
    try:
        summary = audit_repository(repo_root)
    except Exception as exc:
        summary = build_summary(
            required_input_errors=[f"a12_script_failure:{type(exc).__name__}"],
            commit_identity_errors=[],
            changed_paths_errors=[],
            matrix_diff_errors=[],
            routing_diff_errors=[],
        )
    out_path = args.out if args.out.is_absolute() else repo_root / args.out
    write_summary(out_path, summary)
    json.dump(summary, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
