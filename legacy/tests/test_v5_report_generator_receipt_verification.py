"""Tests verifying that generate_v5_final_report cannot emit PASS from missing, unbound or stale receipts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest

from scripts.generate_v5_final_report import generate_report
from bet.pipeline.receipts import (
    get_git_commit_head,
    get_git_tree_sha,
    compute_source_manifest_sha256,
)


def test_report_generator_fails_when_all_receipts_missing(tmp_path, monkeypatch):
    """Missing receipts must result in STATUS=FAIL."""
    fake_acc = tmp_path / "missing_acc.json"
    fake_mut = tmp_path / "missing_mut.json"
    fake_cert = tmp_path / "missing_cert.json"
    fake_suite = tmp_path / "missing_suite.json"
    fake_quality = tmp_path / "missing_quality.json"
    fake_out = tmp_path / "report_out.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_v5_final_report.py",
            "--repo-root", str(Path(__file__).resolve().parents[1]),
            "--acc-report", str(fake_acc),
            "--mut-report", str(fake_mut),
            "--cert-report", str(fake_cert),
            "--full-suite-report", str(fake_suite),
            "--quality-report", str(fake_quality),
            "--output", str(fake_out),
        ],
    )

    report = generate_report()
    assert report["STATUS"] == "FAIL"
    assert report["EXTERNAL_ACCEPTANCE"] == "FAIL"
    assert report["FULL_SUITE"] == "FAIL"
    assert report["CERTIFICATION"] == "FAIL"


def test_report_generator_fails_when_receipt_lacks_sha_bindings(tmp_path, monkeypatch):
    """Receipts lacking cryptographic SHA bindings must cause STATUS=FAIL."""
    repo_root = Path(__file__).resolve().parents[1]

    fake_acc = tmp_path / "acc.json"
    fake_acc.write_text(json.dumps({"overall_status": "PASS", "passed_count": 38}))

    fake_mut = tmp_path / "mut.json"
    fake_mut.write_text(json.dumps({"all_detected": True, "total_mutations": 13, "mutation_score": "13/13"}))

    fake_cert = tmp_path / "cert.json"
    fake_cert.write_text(json.dumps({"status": "PASS", "decision": "READY_FOR_BET_EXECUTOR_SESSION"}))

    fake_suite = tmp_path / "suite.json"
    fake_suite.write_text(json.dumps({"exit_code": 0, "failed": 0, "passed": 100}))

    fake_quality = tmp_path / "quality.json"
    fake_quality.write_text(json.dumps({
        "status": "PASS",
        "format_lint_typecheck": "PASS",
        "focused_tests": "PASS",
        "pipeline_tests": "PASS",
        "validators": "PASS",
        "offline_e2e": "PASS",
    }))

    fake_out = tmp_path / "report_out.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_v5_final_report.py",
            "--repo-root", str(repo_root),
            "--acc-report", str(fake_acc),
            "--mut-report", str(fake_mut),
            "--cert-report", str(fake_cert),
            "--full-suite-report", str(fake_suite),
            "--quality-report", str(fake_quality),
            "--output", str(fake_out),
        ],
    )

    report = generate_report()
    assert report["STATUS"] == "FAIL"
    assert report["EXTERNAL_ACCEPTANCE"] == "FAIL"


def test_report_generator_passes_when_receipts_are_fully_bound(tmp_path, monkeypatch):
    """When all receipts carry valid matching SHA bindings and pass, report generator evaluates correctly."""
    repo_root = Path(__file__).resolve().parents[1]
    head = get_git_commit_head(repo_root)
    tree = get_git_tree_sha(repo_root)
    manifest_sha = compute_source_manifest_sha256(repo_root)
    now = "2026-07-28T12:00:00Z"

    base_fields = {
        "head_sha": head,
        "git_tree_sha": tree,
        "source_manifest_sha256": manifest_sha,
        "command_argv": ["cmd"],
        "cwd": str(repo_root),
        "started_at": now,
        "finished_at": now,
        "exit_code": 0,
    }

    mut_ids = [
        "MUT-001", "MUT-002", "MUT-003", "MUT-004", "MUT-005", "MUT-006",
        "MUT-007", "MUT-008", "MUT-009", "MUT-010", "MUT-011", "MUT-012", "MUT-013"
    ]

    fake_acc = tmp_path / "acc.json"
    fake_acc.write_text(json.dumps({**base_fields, "overall_status": "PASS", "passed_count": 38, "failed_count": 0, "total_count": 38}))

    fake_mut = tmp_path / "mut.json"
    fake_mut.write_text(json.dumps({
        **base_fields,
        "all_detected": True,
        "total_mutations": 13,
        "detected_mutations": 13,
        "mutation_score": "13/13",
        "expected_mutation_set": mut_ids,
        "detected_mutation_set": mut_ids,
    }))

    fake_cert = tmp_path / "cert.json"
    fake_cert.write_text(json.dumps({
        **base_fields,
        "status": "PASS",
        "decision": "READY_FOR_BET_EXECUTOR_SESSION",
        "READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION": "YES",
        "READY_FOR_PRICED_COUPON_SESSION": "NO",
    }))

    fake_suite = tmp_path / "suite.json"
    fake_suite.write_text(json.dumps({
        **base_fields,
        "exit_code": 0,
        "failed": 0,
        "errors": 0,
        "passed": 100,
        "collected": 100,
    }))

    fake_quality = tmp_path / "quality.json"
    fake_quality.write_text(json.dumps({
        **base_fields,
        "status": "PASS",
        "format_lint_typecheck": "PASS",
        "focused_tests": "PASS",
        "pipeline_tests": "PASS",
        "validators": "PASS",
        "offline_e2e": "PASS",
    }))

    fake_out = tmp_path / "report_out.json"

    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_v5_final_report.py",
            "--repo-root", str(repo_root),
            "--acc-report", str(fake_acc),
            "--mut-report", str(fake_mut),
            "--cert-report", str(fake_cert),
            "--full-suite-report", str(fake_suite),
            "--quality-report", str(fake_quality),
            "--output", str(fake_out),
        ],
    )

    report = generate_report()
    if report["WORKTREE_CLEAN"]:
        assert report["STATUS"] == "PASS"
        assert report["READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION"] == "YES"
    else:
        assert report["STATUS"] == "FAIL"
        assert report["WORKTREE_CLEAN"] is False
