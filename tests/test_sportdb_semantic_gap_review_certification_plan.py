from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "sportdb_p2e_semantic_gap_review_certification_plan.py"
)
SPEC = importlib.util.spec_from_file_location(
    "sportdb_p2e_semantic_gap_review_certification_plan", SCRIPT_PATH
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)
SCRIPT_SOURCE = SCRIPT_PATH.read_text(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
A9 = json.loads(
    (
        ROOT
        / "certification"
        / "football"
        / "p2e_sportdb_value_replay_against_accepted_provider_summary.json"
    ).read_text(encoding="utf-8")
)


def make_summary(*, a9: dict, drift: list[str] | None = None) -> dict:
    return module.build_summary(
        root=ROOT,
        a9=a9,
        a9_errors=module.validate_a9_value_replay_summary(a9),
        drift=drift or [],
    )


def test_validates_a9_summary_with_semantic_gaps_and_no_hard_mismatches() -> None:
    errors = module.validate_a9_value_replay_summary(A9)
    assert errors == []


def test_rejects_a9_if_same_match_proof_is_false() -> None:
    a9 = json.loads(json.dumps(A9))
    a9["same_match_proof"]["valid"] = False
    assert "same_match_proof_invalid" in module.validate_a9_value_replay_summary(a9)


def test_rejects_a9_if_team_side_alignment_is_false() -> None:
    a9 = json.loads(json.dumps(A9))
    a9["team_side_alignment"]["valid"] = False
    assert "team_side_alignment_invalid" in module.validate_a9_value_replay_summary(a9)


def test_rejects_a9_if_hard_mismatches_exist() -> None:
    a9 = json.loads(json.dumps(A9))
    a9["metric_replay"]["mismatched_metrics"] = ["corners"]
    assert "hard_mismatches_present" in module.validate_a9_value_replay_summary(a9)


def test_classifies_pass_count_rate_gaps_as_non_blocking_only_when_excluded() -> None:
    reviewed = module.derive_excluded_metric_scope(A9)
    by_metric = {item["metric"]: item for item in reviewed["reviewed_gaps"]}
    assert by_metric["successful_passes"]["non_blocking_if_excluded"] is True
    assert by_metric["successful_passes"]["exclude_from_certifiable_scope"] is True
    assert by_metric["total_passes"]["non_blocking_if_excluded"] is True
    assert by_metric["total_passes"]["exclude_from_certifiable_scope"] is True


def test_excludes_total_passes_and_successful_passes_from_certifiable_metric_scope() -> None:
    scope = module.derive_certifiable_metric_scope(A9)
    assert "total_passes" not in scope["certifiable_metric_scope"]
    assert "successful_passes" not in scope["certifiable_metric_scope"]
    excluded = module.derive_excluded_metric_scope(A9)
    assert excluded["excluded_metric_scope"] == ["successful_passes", "total_passes"]


def test_keeps_at_least_eight_safe_certifiable_metrics_from_a9() -> None:
    scope = module.derive_certifiable_metric_scope(A9)
    assert scope["count"] >= 8
    assert scope["certifiable_metric_scope"] == module.EXPECTED_CERTIFIABLE_METRICS


def test_blocks_if_fewer_than_eight_certifiable_metrics_remain() -> None:
    a9 = json.loads(json.dumps(A9))
    a9["metric_replay"]["matched_metrics"] = ["blocked_shots", "corners", "fouls", "offsides"]
    a9["metric_replay"]["tolerance_matched_metrics"] = ["expected_goals"]
    summary = make_summary(a9=a9)
    assert summary["certification_plan"]["plan_allowed"] is False
    assert summary["classification"] == "SPORTDB_SEMANTIC_GAP_REVIEW_REQUIRES_NORMALIZATION_CORRECTION"


def test_planned_route_is_detailed_metrics_shadow_only() -> None:
    summary = make_summary(a9=A9)
    assert summary["certification_plan"]["planned_routes"] == [
        "detailed_metrics/sportdb/football:eng.1/current-season-completed/shadow"
    ]


def test_summary_verdict_remains_not_certified_semantic_gap_review_only() -> None:
    summary = make_summary(a9=A9)
    assert summary["certification"]["verdict"] == "NOT_CERTIFIED_SEMANTIC_GAP_REVIEW_ONLY"


def test_source_contains_no_http_network_calls_and_no_api_key_reads() -> None:
    for forbidden in [
        "urllib.request",
        "requests.",
        "httpx.",
        "urlopen",
        "SPORTDB_API_KEY",
        "HIGHLIGHTLY_API_KEY",
        "from bet.api_clients.",
        "import bet.api_clients.",
    ]:
        assert forbidden not in SCRIPT_SOURCE
