#!/usr/bin/env python3
"""
Machine-receipt backed final report generator for BET PIPELINE V5 closure.
Reads and cryptographically verifies receipts produced during the pipeline run to construct final decision report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from bet.pipeline.receipts import (
    get_git_commit_head,
    get_git_tree_sha,
    compute_source_manifest_sha256,
    verify_receipt_bindings,
)

DEFAULT_BASE_SHA = "fca79bfe9ca7690905f859a445a067d66b2b2520"
DEFAULT_START_HEAD = "9cab1eebd8ef9f0d6765858e735944139176fb7c"
EXPECTED_MUTATION_IDS = [
    "MUT-001", "MUT-002", "MUT-003", "MUT-004", "MUT-005", "MUT-006",
    "MUT-007", "MUT-008", "MUT-009", "MUT-010", "MUT-011", "MUT-012", "MUT-013"
]


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "UNKNOWN"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args():
    parser = argparse.ArgumentParser(description="V5 Final Report Generator")
    parser.add_argument("--repo-root", default=os.getcwd(), help="Repository root directory")
    parser.add_argument("--base-sha", default=DEFAULT_BASE_SHA, help="Base commit SHA")
    parser.add_argument("--start-head", default=DEFAULT_START_HEAD, help="Start commit HEAD")
    parser.add_argument("--acc-report", default="/tmp/v5_acc_report.json", help="Path to external acceptance report JSON")
    parser.add_argument("--mut-report", default="/tmp/v5_mutation_receipt.json", help="Path to mutation receipt JSON")
    parser.add_argument("--cert-report", default="/tmp/pipeline_cert.json", help="Path to certifier report JSON")
    parser.add_argument("--full-suite-report", default="/tmp/full_suite_report.json", help="Path to full suite pytest receipt JSON")
    parser.add_argument("--quality-report", default="/tmp/quality_checks_receipt.json", help="Path to lint/typecheck/validators receipt JSON")
    parser.add_argument("--baseline-red-report", default="/tmp/v5_baseline_red_report.json", help="Path to baseline RED receipt JSON")
    parser.add_argument("--output", help="Path to write final report JSON")
    return parser.parse_args()


def generate_report() -> dict[str, Any]:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve(strict=True)

    head = get_git_commit_head(repo_root)
    tree = get_git_tree_sha(repo_root)
    manifest_sha = compute_source_manifest_sha256(repo_root)
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo_root, capture_output=True, text=True).stdout.strip() or "DETACHED"

    # Git status clean check
    status_proc = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True)
    worktree_clean = (status_proc.returncode == 0 and len(status_proc.stdout.strip()) == 0)

    # Git diff check
    diff_check_proc = subprocess.run(["git", "diff", "--check", f"{args.base_sha}...HEAD"], cwd=repo_root, capture_output=True, text=True)
    diff_check_pass = (diff_check_proc.returncode == 0 and len(diff_check_proc.stdout.strip()) == 0)

    # Harness path & hash
    harness_path = repo_root / "tools" / "v5_acceptance" / "external_acceptance.py"
    harness_sha = sha256_file(harness_path)

    # Read Receipts
    acc_path = Path(args.acc_report)
    acc_data = json.loads(acc_path.read_text(encoding="utf-8")) if acc_path.is_file() else {}

    mut_path = Path(args.mut_report)
    mut_data = json.loads(mut_path.read_text(encoding="utf-8")) if mut_path.is_file() else {}

    cert_path = Path(args.cert_report)
    cert_data = json.loads(cert_path.read_text(encoding="utf-8")) if cert_path.is_file() else {}

    full_suite_path = Path(args.full_suite_report)
    full_suite_data = json.loads(full_suite_path.read_text(encoding="utf-8")) if full_suite_path.is_file() else {}

    quality_path = Path(args.quality_report)
    quality_data = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}

    baseline_red_path = Path(args.baseline_red_report)
    baseline_red_data = json.loads(baseline_red_path.read_text(encoding="utf-8")) if baseline_red_path.is_file() else {}

    # Verify receipt bindings
    acc_bound, acc_err = verify_receipt_bindings(acc_data, head, tree, manifest_sha)
    mut_bound, mut_err = verify_receipt_bindings(mut_data, head, tree, manifest_sha)
    cert_bound, cert_err = verify_receipt_bindings(cert_data, head, tree, manifest_sha)
    suite_bound, suite_err = verify_receipt_bindings(full_suite_data, head, tree, manifest_sha)
    quality_bound, quality_err = verify_receipt_bindings(quality_data, head, tree, manifest_sha)

    # Evaluate receipt statuses
    acc_pass = (
        acc_bound
        and acc_data.get("overall_status") == "PASS"
        and acc_data.get("passed_count", 0) == 38
        and acc_data.get("failed_count", 1) == 0
    )

    detected_mutations = mut_data.get("detected_mutation_set") or list((mut_data.get("results") or {}).keys())
    expected_set = set(EXPECTED_MUTATION_IDS)
    mut_pass = (
        mut_bound
        and mut_data.get("all_detected") is True
        and mut_data.get("detected_mutations", 0) == len(EXPECTED_MUTATION_IDS)
        and mut_data.get("total_mutations", 0) == len(EXPECTED_MUTATION_IDS)
        and set(detected_mutations) == expected_set
    )

    cert_pass = (
        cert_bound
        and cert_data.get("status") == "PASS"
        and cert_data.get("decision") == "READY_FOR_BET_EXECUTOR_SESSION"
        and cert_data.get("READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION") == "YES"
        and cert_data.get("READY_FOR_PRICED_COUPON_SESSION") == "NO"
    )

    full_suite_pass = (
        suite_bound
        and full_suite_data.get("exit_code") == 0
        and full_suite_data.get("failed", 1) == 0
        and full_suite_data.get("errors", 1) == 0
        and full_suite_data.get("passed", 0) > 0
    )

    quality_pass = (
        quality_bound
        and quality_data.get("status") == "PASS"
        and quality_data.get("format_lint_typecheck") == "PASS"
        and quality_data.get("focused_tests") == "PASS"
        and quality_data.get("pipeline_tests") == "PASS"
        and quality_data.get("validators") == "PASS"
        and quality_data.get("offline_e2e") == "PASS"
    )

    baseline_red_pass = (
        baseline_red_data.get("overall_status") == "FAIL" or baseline_red_data.get("baseline_red") is True
    )

    overall_pass = (
        acc_pass
        and mut_pass
        and cert_pass
        and full_suite_pass
        and quality_pass
        and worktree_clean
        and diff_check_pass
    )

    report = {
        "STATUS": "PASS" if overall_pass else "FAIL",
        "DECISION": "READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION" if overall_pass else "BLOCKED",
        "BASE_SHA": args.base_sha,
        "START_HEAD": args.start_head,
        "FINAL_HEAD": head,
        "GIT_TREE_SHA": tree,
        "SOURCE_MANIFEST_SHA256": manifest_sha,
        "BRANCH": branch,
        "WORKTREE": str(repo_root),
        "ACCEPTANCE_HARNESS_PATH": str(harness_path),
        "ACCEPTANCE_HARNESS_SHA256": harness_sha,
        "BASELINE_RED": baseline_red_pass,
        "EXTERNAL_ACCEPTANCE": "PASS" if acc_pass else "FAIL",
        "MUTATION_SCORE": mut_data.get("mutation_score", "0/0") if mut_pass else "FAIL",
        "MUTATION_RECEIPT_PATH": str(mut_path) if mut_path.is_file() else "MISSING",
        "READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION": "YES" if overall_pass else "NO",
        "READY_FOR_PRICED_COUPON_SESSION": "NO",
        "FORMAT_LINT_TYPECHECK": "PASS" if quality_data.get("format_lint_typecheck") == "PASS" else "FAIL",
        "FOCUSED_TESTS": "PASS" if quality_data.get("focused_tests") == "PASS" else "FAIL",
        "PIPELINE_TESTS": "PASS" if quality_data.get("pipeline_tests") == "PASS" else "FAIL",
        "FULL_SUITE": "PASS" if full_suite_pass else "FAIL",
        "VALIDATORS": "PASS" if quality_data.get("validators") == "PASS" else "FAIL",
        "CERTIFICATION": "PASS" if cert_pass else "FAIL",
        "OFFLINE_END_TO_END": "PASS" if quality_data.get("offline_e2e") == "PASS" else "FAIL",
        "DIFF_CHECK": "PASS" if diff_check_pass else "FAIL",
        "WORKTREE_CLEAN": worktree_clean,
        "UNRESOLVED_P0": 0 if overall_pass else 1,
        "UNRESOLVED_P1": 0 if overall_pass else 1,
        "RECEIPT_ERRORS": {
            "acc": acc_err if not acc_pass else "OK",
            "mut": mut_err if not mut_pass else "OK",
            "cert": cert_err if not cert_pass else "OK",
            "suite": suite_err if not full_suite_pass else "OK",
            "quality": quality_err if not quality_pass else "OK",
        },
    }

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


if __name__ == "__main__":
    rep = generate_report()
    print(json.dumps(rep, indent=2))
    if rep["STATUS"] != "PASS":
        sys.exit(1)
    sys.exit(0)
