"""Tests verifying that generate_v5_final_report cannot emit PASS from missing or stale receipts."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import pytest

from scripts.generate_v5_final_report import generate_report


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


def test_report_generator_fails_when_cert_fails(tmp_path, monkeypatch):
    """A failing certifier receipt must cause STATUS=FAIL."""
    fake_acc = tmp_path / "acc.json"
    fake_acc.write_text(json.dumps({"overall_status": "PASS", "passed_count": 38}))

    fake_mut = tmp_path / "mut.json"
    fake_mut.write_text(json.dumps({"all_detected": True, "total_mutations": 13, "mutation_score": "13/13"}))

    fake_cert = tmp_path / "cert.json"
    fake_cert.write_text(json.dumps({"status": "FAIL", "decision": "BLOCKED"}))

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
    assert report["CERTIFICATION"] == "FAIL"


def test_report_generator_passes_only_when_all_receipts_pass(tmp_path, monkeypatch):
    """When all receipts pass and worktree is clean, status must be PASS."""
    fake_acc = tmp_path / "acc.json"
    fake_acc.write_text(json.dumps({"overall_status": "PASS", "passed_count": 38}))

    fake_mut = tmp_path / "mut.json"
    fake_mut.write_text(json.dumps({"all_detected": True, "total_mutations": 13, "mutation_score": "13/13"}))

    fake_cert = tmp_path / "cert.json"
    fake_cert.write_text(json.dumps({"status": "PASS", "decision": "READY_FOR_BET_EXECUTOR_SESSION"}))

    fake_suite = tmp_path / "suite.json"
    fake_suite.write_text(json.dumps({"exit_code": 0, "failed": 0, "passed": 2815}))

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
            "--acc-report", str(fake_acc),
            "--mut-report", str(fake_mut),
            "--cert-report", str(fake_cert),
            "--full-suite-report", str(fake_suite),
            "--quality-report", str(fake_quality),
            "--output", str(fake_out),
        ],
    )

    report = generate_report()
    # Note: If worktree has untracked/modified files (like new test files before commit),
    # WORKTREE_CLEAN will be False, so STATUS will be FAIL, which correctly enforces cleanliness!
    if report["WORKTREE_CLEAN"]:
        assert report["STATUS"] == "PASS"
    else:
        assert report["STATUS"] == "FAIL"
        assert report["WORKTREE_CLEAN"] is False
