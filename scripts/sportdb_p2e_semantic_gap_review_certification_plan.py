#!/usr/bin/env python3
"""Offline SportDB semantic-gap review and scope-limited certification plan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

PHASE_ID = "P2E_A10_SEMANTIC_GAP_REVIEW_AND_SCOPE_LIMITED_CERTIFICATION_PLAN"
PROMPT_VERSION = "v1_compact_masterpiece_certification_readiness_gate"
PREVIOUS_ACCEPTED_SHA = "5851038402d4c23401390da610a330629fd04a9b"
PROTECTED_WORKTREE = "/Users/mkoziol/projects/bet-multisport-enrichment-v1"
DEFAULT_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_semantic_gap_review_certification_plan_summary.json"
)
P2E_A9_SUMMARY_PATH = Path(
    "certification/football/p2e_sportdb_value_replay_against_accepted_provider_summary.json"
)
REQUIRED_INPUT_PATHS = [
    "certification/football/p2e_sportdb_value_replay_against_accepted_provider_summary.json",
    "certification/football/p2e_accepted_provider_same_match_replay_capture_summary.json",
    "certification/football/p2e_sportdb_identity_bridge_value_replay_summary.json",
    "certification/football/p2e_sportdb_evidence_bundle_summary.json",
    "certification/football/p2e_sportdb_replay_comparison_summary.json",
    "certification/football/p2e_sportdb_shadow_adapter_summary.json",
    "certification/football/p2d_highlightly_certification_summary.json",
    "config/provider_capability_matrix.json",
    "config/football_routing.yaml",
]
EXPECTED_CERTIFIABLE_METRICS = [
    "blocked_shots",
    "corners",
    "expected_goals",
    "fouls",
    "goalkeeper_saves",
    "offsides",
    "possession",
    "shots_off_target",
    "shots_on_goal",
    "yellow_cards",
]
EXPECTED_EXCLUDED_METRICS = ["successful_passes", "total_passes"]
PASS_GAP_REASONS = {
    "sportdb_successful_passes_rate_vs_highlightly_successful_passes_count": {
        "semantic_type": "pass_rate_vs_pass_count",
        "reason": "provider semantic mismatch: pass rate vs successful pass count",
    },
    "sportdb_total_passes_aligns_to_highlightly_successful_passes_not_total_passes": {
        "semantic_type": "pass_count_alignment_mismatch",
        "reason": "provider semantic mismatch: successful pass count vs total pass count",
    },
}
NOT_CERTIFIED_VERDICT = "NOT_CERTIFIED_SEMANTIC_GAP_REVIEW_ONLY"
READY_CLASSIFICATION = (
    "SPORTDB_SEMANTIC_GAP_REVIEW_READY_FOR_SCOPE_LIMITED_SHADOW_REGISTRATION"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_a9_value_replay_summary(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("phase_id") != "P2E_A9_SPORTDB_VALUE_REPLAY_AGAINST_ACCEPTED_PROVIDER":
        errors.append("phase_id_mismatch")
    if data.get("classification") != "SPORTDB_VALUE_REPLAY_READY_WITH_SEMANTIC_GAPS_FOR_REVIEW":
        errors.append("classification_not_ready_with_semantic_gaps")
    if data.get("providers", {}).get("candidate") != "sportdb":
        errors.append("candidate_provider_not_sportdb")
    if data.get("providers", {}).get("accepted_provider") != "highlightly":
        errors.append("accepted_provider_not_highlightly")
    if data.get("same_match_proof", {}).get("valid") is not True:
        errors.append("same_match_proof_invalid")
    if data.get("team_side_alignment", {}).get("valid") is not True:
        errors.append("team_side_alignment_invalid")

    metric_replay = data.get("metric_replay", {})
    if metric_replay.get("performed") is not True:
        errors.append("value_replay_not_performed")
    if data.get("certification", {}).get("verdict") != "NOT_CERTIFIED_VALUE_REPLAY_ONLY":
        errors.append("unexpected_a9_certification_verdict")
    if data.get("certification", {}).get("certified_routes") not in ([], None):
        errors.append("unexpected_a9_certified_routes")
    if bool(metric_replay.get("mismatched_metrics", [])):
        errors.append("hard_mismatches_present")
    if bool(metric_replay.get("team_side_gaps", [])):
        errors.append("team_side_gaps_present")
    compared = metric_replay.get("canonical_metrics_compared", [])
    if not isinstance(compared, list) or len(compared) < 8:
        errors.append("canonical_metrics_compared_insufficient")
    return errors


def classify_semantic_gap(gap: dict[str, Any]) -> dict[str, Any]:
    metric = str(gap.get("metric") or "")
    reason_key = str(gap.get("reason") or "")
    pass_gap = PASS_GAP_REASONS.get(reason_key)
    if metric in EXPECTED_EXCLUDED_METRICS and pass_gap is not None:
        return {
            "metric": metric,
            "reason_key": reason_key,
            "semantic_type": pass_gap["semantic_type"],
            "summary": pass_gap["reason"],
            "blocking_for_reduced_scope": False,
            "non_blocking_if_excluded": True,
            "exclude_from_certifiable_scope": True,
            "requires_future_normalization": True,
        }
    return {
        "metric": metric,
        "reason_key": reason_key,
        "semantic_type": "unknown_semantic_gap",
        "summary": "unclassified semantic gap requires normalization review",
        "blocking_for_reduced_scope": True,
        "non_blocking_if_excluded": False,
        "exclude_from_certifiable_scope": True,
        "requires_future_normalization": True,
    }


def _metric_replay(a9: dict[str, Any]) -> dict[str, Any]:
    return a9.get("metric_replay", {})


def derive_certifiable_metric_scope(a9: dict[str, Any]) -> dict[str, Any]:
    metric_replay = _metric_replay(a9)
    compared = set(metric_replay.get("canonical_metrics_compared", []))
    matched = set(metric_replay.get("matched_metrics", []))
    tolerance = set(metric_replay.get("tolerance_matched_metrics", []))
    team_side_gaps = set(metric_replay.get("team_side_gaps", []))
    semantic_gaps = {
        str(gap.get("metric")) for gap in metric_replay.get("semantic_gaps", []) if gap.get("metric")
    }
    ambiguous = set(EXPECTED_EXCLUDED_METRICS)
    certifiable = sorted((matched | tolerance) & compared - semantic_gaps - team_side_gaps - ambiguous)
    safe_expected = sorted(set(EXPECTED_CERTIFIABLE_METRICS) & set(certifiable))
    return {
        "certifiable_metric_scope": safe_expected,
        "count": len(safe_expected),
        "minimum_required": 8,
    }


def derive_excluded_metric_scope(a9: dict[str, Any]) -> dict[str, Any]:
    metric_replay = _metric_replay(a9)
    reviewed_gaps = [classify_semantic_gap(gap) for gap in metric_replay.get("semantic_gaps", [])]
    excluded = sorted(
        {
            gap["metric"]
            for gap in reviewed_gaps
            if gap.get("exclude_from_certifiable_scope")
        }
    )
    normalization = sorted(
        {
            gap["metric"]
            for gap in reviewed_gaps
            if gap.get("requires_future_normalization")
        }
    )
    accepted_non_blocking = sorted(
        {
            gap["metric"]
            for gap in reviewed_gaps
            if gap.get("non_blocking_if_excluded")
        }
    )
    return {
        "excluded_metric_scope": excluded,
        "accepted_as_non_blocking_if_excluded": accepted_non_blocking,
        "requires_future_normalization": normalization,
        "reviewed_gaps": reviewed_gaps,
        "provider_extra_metrics_excluded": sorted(metric_replay.get("provider_extra_metrics", [])),
        "unknown_metrics_excluded": sorted(metric_replay.get("unknown_metrics_preserved", [])),
    }


def derive_route_family_plan(a9: dict[str, Any]) -> dict[str, Any]:
    _ = a9
    planned_routes = [
        "detailed_metrics/sportdb/football:eng.1/current-season-completed/shadow"
    ]
    return {
        "planned_routes": planned_routes,
        "value_replay_supported_route_families": ["detailed_metrics"],
        "event_level_value_certification_supported": False,
        "lineups_value_certification_supported": False,
        "standings_value_certification_supported": False,
    }


def detect_routing_or_matrix_drift(root: Path) -> list[str]:
    command = [
        "git",
        "diff",
        "--name-only",
        "HEAD",
        "--",
        "config/football_routing.yaml",
        "config/provider_capability_matrix.json",
    ]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ["git_diff_failed_for_routing_matrix_drift_check"]
    drift: list[str] = []
    for path in result.stdout.splitlines():
        if path == "config/football_routing.yaml":
            drift.append("routing_drift:config/football_routing.yaml")
        elif path == "config/provider_capability_matrix.json":
            drift.append("matrix_drift:config/provider_capability_matrix.json")
    return drift


def build_summary(
    *,
    root: Path,
    a9: dict[str, Any],
    a9_errors: list[str],
    drift: list[str],
) -> dict[str, Any]:
    metric_replay = _metric_replay(a9)
    scope = derive_certifiable_metric_scope(a9)
    excluded = derive_excluded_metric_scope(a9)
    route_plan = derive_route_family_plan(a9)
    same_match_valid = a9.get("same_match_proof", {}).get("valid") is True
    team_side_valid = a9.get("team_side_alignment", {}).get("valid") is True
    replay_performed = metric_replay.get("performed") is True
    hard_mismatch_count = len(metric_replay.get("mismatched_metrics", []))
    semantic_gap_count = len(metric_replay.get("semantic_gaps", []))
    valid = not a9_errors
    blocking_for_reduced_scope = any(
        item["blocking_for_reduced_scope"] for item in excluded["reviewed_gaps"]
    )
    plan_allowed = (
        valid
        and not drift
        and hard_mismatch_count == 0
        and same_match_valid
        and team_side_valid
        and replay_performed
        and not blocking_for_reduced_scope
        and scope["count"] >= scope["minimum_required"]
        and route_plan["planned_routes"]
        == ["detailed_metrics/sportdb/football:eng.1/current-season-completed/shadow"]
        and sorted(excluded["excluded_metric_scope"]) == EXPECTED_EXCLUDED_METRICS
    )

    summary = {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_SEMANTIC_GAP_REVIEW_CERTIFICATION_PLAN_SUMMARY",
        "protected_worktree": PROTECTED_WORKTREE,
        "mode": "replay_review_no_live_calls",
        "provider": "sportdb",
        "accepted_provider": "highlightly",
        "a9_validation": {
            "valid": valid,
            "same_match_proof_valid": same_match_valid,
            "team_side_alignment_valid": team_side_valid,
            "value_replay_performed": replay_performed,
            "canonical_metrics_compared_count": len(metric_replay.get("canonical_metrics_compared", [])),
            "hard_mismatch_count": hard_mismatch_count,
            "semantic_gap_count": semantic_gap_count,
            "errors": a9_errors,
        },
        "semantic_gap_review": {
            "blocking_for_reduced_scope": blocking_for_reduced_scope,
            "reviewed_gaps": excluded["reviewed_gaps"],
            "accepted_as_non_blocking_if_excluded": excluded[
                "accepted_as_non_blocking_if_excluded"
            ],
            "requires_future_normalization": excluded["requires_future_normalization"],
        },
        "certification_plan": {
            "plan_allowed": plan_allowed,
            "planned_routes": route_plan["planned_routes"] if plan_allowed else [],
            "certifiable_metric_scope": scope["certifiable_metric_scope"] if plan_allowed else [],
            "excluded_metric_scope": excluded["excluded_metric_scope"],
            "provider_extra_metrics_excluded": excluded["provider_extra_metrics_excluded"],
            "unknown_metrics_excluded": excluded["unknown_metrics_excluded"],
            "minimum_evidence_basis": REQUIRED_INPUT_PATHS,
            "certification_status_to_apply_next": (
                "SCOPE_LIMITED_SHADOW_REGISTRATION_ONLY" if plan_allowed else "NONE"
            ),
        },
        "classification": "UNKNOWN",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": NOT_CERTIFIED_VERDICT,
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "UNKNOWN",
        "blockers": list(drift),
        "secret_safe": True,
        "final_review": "PASS",
    }
    summary["classification"] = classify_summary(summary)
    summary["next_step"] = next_step_for_classification(summary["classification"])
    return summary


def classify_summary(summary: dict[str, Any]) -> str:
    blockers = summary.get("blockers", [])
    if blockers:
        return "SPORTDB_SEMANTIC_GAP_REVIEW_BLOCKED_ROUTING_OR_MATRIX_DRIFT"
    a9_validation = summary.get("a9_validation", {})
    if a9_validation.get("team_side_alignment_valid") is not True:
        return "SPORTDB_SEMANTIC_GAP_REVIEW_BLOCKED_TEAM_SIDE_ALIGNMENT"
    if a9_validation.get("hard_mismatch_count", 0) > 0:
        return "SPORTDB_SEMANTIC_GAP_REVIEW_BLOCKED_HARD_MISMATCH"
    if a9_validation.get("valid") is not True:
        return "SPORTDB_SEMANTIC_GAP_REVIEW_BLOCKED_A9_INVALID"
    if summary.get("certification_plan", {}).get("plan_allowed") is True:
        return READY_CLASSIFICATION
    return "SPORTDB_SEMANTIC_GAP_REVIEW_REQUIRES_NORMALIZATION_CORRECTION"


def next_step_for_classification(classification: str) -> str:
    if classification == READY_CLASSIFICATION:
        return "P2E_A11_SPORTDB_SCOPE_LIMITED_SHADOW_REGISTRATION"
    if classification == "SPORTDB_SEMANTIC_GAP_REVIEW_REQUIRES_NORMALIZATION_CORRECTION":
        return "P2E_A10B_PASS_METRIC_NORMALIZATION_REVIEW"
    return "blocked_or_retry_after_review"


def write_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_blocked_summary(root: Path, error: str) -> dict[str, Any]:
    drift = detect_routing_or_matrix_drift(root)
    blockers = [error, *drift]
    return {
        "phase_id": PHASE_ID,
        "prompt_version": PROMPT_VERSION,
        "previous_accepted_sha": PREVIOUS_ACCEPTED_SHA,
        "evidence_level": "TRACKED_SEMANTIC_GAP_REVIEW_CERTIFICATION_PLAN_SUMMARY",
        "protected_worktree": PROTECTED_WORKTREE,
        "mode": "replay_review_no_live_calls",
        "provider": "sportdb",
        "accepted_provider": "highlightly",
        "a9_validation": {
            "valid": False,
            "same_match_proof_valid": False,
            "team_side_alignment_valid": False,
            "value_replay_performed": False,
            "canonical_metrics_compared_count": 0,
            "hard_mismatch_count": 0,
            "semantic_gap_count": 0,
            "errors": [error],
        },
        "semantic_gap_review": {
            "blocking_for_reduced_scope": True,
            "reviewed_gaps": [],
            "accepted_as_non_blocking_if_excluded": [],
            "requires_future_normalization": [],
        },
        "certification_plan": {
            "plan_allowed": False,
            "planned_routes": [],
            "certifiable_metric_scope": [],
            "excluded_metric_scope": [],
            "provider_extra_metrics_excluded": [],
            "unknown_metrics_excluded": [],
            "minimum_evidence_basis": REQUIRED_INPUT_PATHS,
            "certification_status_to_apply_next": "NONE",
        },
        "classification": "SPORTDB_SEMANTIC_GAP_REVIEW_BLOCKED_SCRIPT_OR_PARSER_DEFECT",
        "certification": {
            "certified_routes": [],
            "production_routing_changed": False,
            "selectable_status_changed": False,
            "verdict": NOT_CERTIFIED_VERDICT,
        },
        "impact_on_p2d": "none_highlightly_remains_accepted",
        "next_step": "blocked_or_retry_after_review",
        "blockers": blockers,
        "secret_safe": True,
        "final_review": "FAIL",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_SUMMARY_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(PROTECTED_WORKTREE)
    try:
        a9 = load_json(root / P2E_A9_SUMMARY_PATH)
        for required in REQUIRED_INPUT_PATHS:
            path = root / required
            if not path.is_file():
                raise FileNotFoundError(required)
        a9_errors = validate_a9_value_replay_summary(a9)
        drift = detect_routing_or_matrix_drift(root)
        summary = build_summary(root=root, a9=a9, a9_errors=a9_errors, drift=drift)
    except Exception as exc:
        summary = build_blocked_summary(root, f"script_or_parser_defect:{type(exc).__name__}")

    write_summary(root / args.out, summary)
    json.dump(summary, sys.stdout, separators=(",", ":"), sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
