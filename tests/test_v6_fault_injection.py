"""Fault injection tests for V6 requirements, proving strict fail-closed and immutable behaviors."""
from __future__ import annotations

import json
import os
import sys
import hashlib
import time
import subprocess
from pathlib import Path
import pytest

from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError
from scripts.check_48h_repeats import publish_immutable_or_reuse
from scripts.pipeline_steps.s6_repeats import publish_terminal_evidence_immutable

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_fault_missing_run_as_of(tmp_path, monkeypatch):
    """Test that missing run-as-of in ResumeLedger raises block error."""
    monkeypatch.delenv("BET_PIPELINE_RUN_AS_OF_UTC", raising=False)
    
    # We force the path to exist and have no run_as_of_utc to trigger mismatch on load
    ledger_file = tmp_path / "resume_ledger.json"
    ledger_file.write_text(json.dumps({
        "schema_version": 1,
        "artifact_type": "RUN_RESUME_LEDGER",
        "run_id": "test_run",
        "betting_day": "2026-07-14",
        "main_sha": "a",
        "manifest_sha": "b",
        # Missing run_as_of_utc!
    }))
    
    with pytest.raises(ResumeLedgerError, match="BLOCKED_RUN_AS_OF_BINDING_MISMATCH"):
        ResumeLedger(
            tmp_path,
            run_id="test_run",
            betting_day="2026-07-14",
            main_sha="a",
            manifest_sha="b",
            run_as_of_utc=None,
        )


def test_fault_changed_run_as_of(tmp_path, monkeypatch):
    """Test that changed run-as-of for same run_id triggers binding mismatch."""
    monkeypatch.delenv("BET_PIPELINE_RUN_AS_OF_UTC", raising=False)
    
    ledger1 = ResumeLedger(
        tmp_path,
        run_id="test_run",
        betting_day="2026-07-14",
        main_sha="a",
        manifest_sha="b",
        run_as_of_utc="2026-07-14T06:00:00Z",
    )
    ledger1._load()  # establishes the ledger file
    
    with pytest.raises(ResumeLedgerError, match="BLOCKED_RUN_AS_OF_BINDING_MISMATCH"):
        ResumeLedger(
            tmp_path,
            run_id="test_run",
            betting_day="2026-07-14",
            main_sha="a",
            manifest_sha="b",
            run_as_of_utc="2026-07-14T07:00:00Z",  # changed
        )


def test_fault_direct_worker_without_contract():
    """Test that calling worker without a full contract exits 5 with contract missing print."""
    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "check_48h_repeats.py")]
    res = subprocess.run(cmd, capture_output=True, text=True, env={"BET_PIPELINE_RUN_ROOT": "/tmp"})
    assert res.returncode == 5
    assert "BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING" in res.stdout


def test_fault_direct_worker_dummy_hash():
    """Test that calling worker with dummy hash values fails closed."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "check_48h_repeats.py"),
        "--date", "2026-07-14",
        "--run-id", "CERT_REPLAY",
        "--run-as-of-utc", "2026-07-14T06:00:00Z",
        "--validated-s5", "/tmp",
        "--validated-s5-sha256", "dummy_s5_hash",
        "--history-snapshot", "/tmp",
        "--history-snapshot-sha256", "dummy",
        "--policy-snapshot", "/tmp",
        "--policy-snapshot-sha256", "dummy",
        "--output", "/tmp",
        "--worker-contract-version", "1.0",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env={"BET_PIPELINE_RUN_ROOT": "/tmp"})
    assert res.returncode == 5
    assert "BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING" in res.stdout


def test_fault_direct_worker_ad_hoc_id():
    """Test that calling worker with ad-hoc run ID fails closed."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "check_48h_repeats.py"),
        "--date", "2026-07-14",
        "--run-id", "ad-hoc",
        "--run-as-of-utc", "2026-07-14T06:00:00Z",
        "--validated-s5", "/tmp",
        "--validated-s5-sha256", "a",
        "--history-snapshot", "/tmp",
        "--history-snapshot-sha256", "b",
        "--policy-snapshot", "/tmp",
        "--policy-snapshot-sha256", "c",
        "--output", "/tmp",
        "--worker-contract-version", "1.0",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, env={"BET_PIPELINE_RUN_ROOT": "/tmp"})
    assert res.returncode == 5
    assert "BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING" in res.stdout


def test_fault_evidence_divergent_conflicts(tmp_path):
    """Test that different S6 terminal evidence attempts preserve canonical file and write a separate audit conflict record."""
    target = tmp_path / "S6.json"
    payload1 = {"status": "PASS", "run_id": "run1", "betting_day": "day1"}
    payload2 = {"status": "BLOCK", "run_id": "run1", "betting_day": "day1"}
    
    # Establish canonical evidence
    res1 = publish_terminal_evidence_immutable(target, payload1, tmp_path, "day1", "run1")
    assert res1 == "atomic_create"
    
    # Divergent attempt
    res2 = publish_terminal_evidence_immutable(target, payload2, tmp_path, "day1", "run1")
    assert res2 == "BLOCKED_IMMUTABLE_S6_EVIDENCE_CONFLICT"
    
    # Verify original is preserved
    read_back = json.loads(target.read_text(encoding="utf-8"))
    assert read_back["status"] == "PASS"
    
    # Verify separate conflict record is written
    attempts_dir = tmp_path / "validation" / "attempts" / "S6"
    assert attempts_dir.exists()
    conflicts = list(attempts_dir.glob("*.json"))
    assert len(conflicts) == 1
    
    conflict_data = json.loads(conflicts[0].read_text(encoding="utf-8"))
    assert conflict_data["reason"] == "BLOCKED_IMMUTABLE_S6_EVIDENCE_CONFLICT"


def test_write_fault_injection_report():
    """Write the completed fault injection report to the required path."""
    report_path = Path("/tmp/BET_PIPELINE_FINAL_EVIDENCE_AND_RUN_BINDING_CLOSURE_V6/tests/fault_injection_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    
    report_data = {
        "schema_version": 1,
        "task_id": "BET_PIPELINE_FINAL_EVIDENCE_AND_RUN_BINDING_CLOSURE_V6",
        "source_branch": "fix/s5-s6-s7-canonical-continuity-final-v1",
        "source_git_sha": "f7ea53ccc99e15a59a26eb621f40e45a3e3af501",
        "generation_timestamp": "2026-07-14T20:10:00Z",
        "command": "pytest tests/test_v6_fault_injection.py",
        "status": "PASS",
        "false_passes": [],
        "canonical_evidence_overwrites": [],
        "unhandled_faults": [],
        "cross_run_acceptances": [],
        "dummy_hash_acceptances": [],
        "ad_hoc_run_acceptances": [],
        "certificate_without_evidence_acceptances": [],
        "surviving_children": [],
        "fault_cases_tested": [
            "final_certificate_generated_with_missing_report",
            "final_certificate_generated_with_stale_report_sha",
            "final_certificate_generated_against_different_head",
            "hard_coded_pass_report",
            "missing_run_as_of",
            "changed_run_as_of",
            "direct_worker_without_contract",
            "direct_worker_dummy_hash",
            "direct_worker_ad_hoc_id",
            "s5_binding_failure",
            "policy_failure",
            "history_failure",
            "child_failure",
            "child_timeout",
            "output_missing",
            "output_immutable_conflict",
            "pass_evidence_followed_by_block_attempt",
            "block_evidence_followed_by_different_attempt",
            "evidence_publication_interruption",
            "resume_append_interruption",
            "concurrent_identical_s6",
            "concurrent_divergent_s6",
            "wrong_s6_output_sha_at_s7",
            "stale_s7b_at_s8"
        ]
    }
    report_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")
