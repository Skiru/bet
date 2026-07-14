"""Tests for V7 certifier report hashes, exact schemas, and validation gates."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def test_cluster_a_certifier_schema_validation(tmp_path):
    """Test that the certifier enforces report schema, hash checks, correct branch/HEAD, and staged-tree SHA."""
    # We will invoke certify_pipeline_final_closure.py in a subprocess with manipulated reports
    cert_script = REPO_ROOT / "scripts" / "certify_pipeline_final_closure.py"

    # We create a temporary reports directory with 15 valid-looking reports first
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()

    # Helper to write a valid base report
    def write_report(name, path, payload, status="PASS", task_id="BET_PIPELINE_FINAL_TRUSTWORTHY_CERTIFICATION_V7", branch="fix/s5-s6-s7-canonical-continuity-final-v1", git_sha="f925aef8ec215da5b513081b1a0357a5e628fab9", staged_tree_sha="28422d9c6c3085818a7c4b69f27da61416fc8516", timestamp="2026-07-14T23:30:00Z", hash_val=None):
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        p_hash = hash_val or json.dumps(payload_str) # wait, let's calculate real sha256 or use provided
        import hashlib
        calc_hash = hash_val or hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        report = {
            "schema_version": 1,
            "task_id": task_id,
            "source_branch": branch,
            "source_git_sha": git_sha,
            "staged_tree_sha": staged_tree_sha,
            "generation_timestamp": timestamp,
            "producer": f"{name}_producer",
            "command": f"run_{name}",
            "status": status,
            "report_payload": payload,
            "report_payload_sha256": calc_hash
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    # Define paths for all 15 reports
    report_paths = {
        "requirements_traceability": reports_dir / "requirements_traceability.json",
        "focused_test_report": reports_dir / "focused_test_report.json",
        "canonical_replay_report": reports_dir / "canonical_replay_report.json",
        "evidence_chain_report": reports_dir / "evidence_chain_report.json",
        "resume_chain_report": reports_dir / "resume_chain_report.json",
        "fault_injection_report": reports_dir / "fault_injection_report.json",
        "regression_comparison": reports_dir / "regression_comparison.json",
        "test_collection_comparison": reports_dir / "test_collection_comparison.json",
        "production_surface_report": reports_dir / "production_surface_report.json",
        "reachability_report": reports_dir / "reachability_report.json",
        "package_report": reports_dir / "package_report.json",
        "security_report": reports_dir / "security_report.json",
        "reviewer_report": reports_dir / "reviewer_report.json",
        "staged_tree_manifest": reports_dir / "staged_tree_manifest.json",
        "git_state_report": reports_dir / "git_state_report.json",
    }

    # 1. Base payloads
    payloads = {
        "requirements_traceability": {
            "traceability": {
                req_id: {"status": "PASS"} for req_id in (
                    "REQ-V6-CERT-001", "REQ-V6-CERT-002", "REQ-V6-CERT-003",
                    "REQ-V6-EVID-001", "REQ-V6-EVID-002", "REQ-V6-EVID-003",
                    "REQ-V6-WORKER-001", "REQ-V6-WORKER-002",
                    "REQ-V6-CLOCK-001", "REQ-V6-CLOCK-002", "REQ-V6-CLOCK-003",
                    "REQ-V6-REPLAY-001", "REQ-V6-REPLAY-002", "REQ-V6-REPLAY-003",
                    "REQ-V6-FAULT-001", "REQ-V6-FAULT-002",
                    "REQ-V6-REG-001", "REQ-V6-RELEASE-001"
                )
            }
        },
        "focused_test_report": {"failures": 0, "executed_tests": ["test_a", "test_b"]},
        "canonical_replay_report": {"replay_runner_executed": True, "replay_steps": ["S6", "S7", "S7b", "S8"], "s6_worker_executed": True, "hash_mismatches": [], "unaccounted_ids": [], "replay_synthetic_odds": [], "worker_input_json_paths": []},
        "evidence_chain_report": {"steps": ["S6", "S7", "S7b", "S8"], "missing_steps": [], "hash_mismatches": [], "resume_mismatches": [], "binding_mismatches": [], "duplicate_evidence": [], "cross_run_paths": [], "unresolved_conflicts": [], "unresolved_conflicts_count": 0},
        "resume_chain_report": {"resume_mismatches": []},
        "fault_injection_report": {"false_passes": [], "canonical_evidence_overwrites": [], "unhandled_faults": [], "worker_dummy_hash_paths": [], "worker_ad_hoc_paths": [], "fault_cases_tested": ["case1"]},
        "regression_comparison": {"new_regression_ids": []},
        "test_collection_comparison": {"unexplained_removed_node_ids": []},
        "production_surface_report": {"surface_checked": True, "violations_found": 0},
        "reachability_report": {"reachability_checked": True, "unreachable_modules": 0},
        "package_report": {"wheel_clean": True, "build_status": "SUCCESS"},
        "security_report": {"vulnerabilities": 0},
        "reviewer_report": {"reviewed_head": "f925aef8ec215da5b513081b1a0357a5e628fab9", "p0_findings": [], "p1_findings": [], "reviewed_paths": [], "evidence_paths": []},
        "staged_tree_manifest": {"staged_tree_sha": "28422d9c6c3085818a7c4b69f27da61416fc8516", "files": []},
        "git_state_report": {"remote_branch_sha": "f925aef8ec215da5b513081b1a0357a5e628fab9"}
    }

    def write_all(hash_override=None, git_sha_override=None, staged_tree_sha_override=None, timestamp_override=None):
        for name, path in report_paths.items():
            write_report(
                name, path, payloads[name],
                git_sha=git_sha_override or "f925aef8ec215da5b513081b1a0357a5e628fab9",
                staged_tree_sha=staged_tree_sha_override or "28422d9c6c3085818a7c4b69f27da61416fc8516",
                timestamp=timestamp_override or "2026-07-14T23:30:00Z",
                hash_val=hash_override if name == "focused_test_report" else None
            )

    # 1. Test wrong payload hash rejection
    write_all(hash_override="wrong_hash")
    cmd = [sys.executable, str(cert_script)]
    for name, path in report_paths.items():
        cmd.extend([f"--{name.replace('_', '-')}", str(path)])

    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "BLOCK: Report payload SHA256 mismatch" in res.stdout or "BLOCK: Report payload SHA256 mismatch" in res.stderr

    # 2. Test wrong Git HEAD rejection
    write_all(git_sha_override="wrong_git_sha")
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "BLOCK: Source Git SHA mismatch" in res.stdout or "BLOCK: Source Git SHA mismatch" in res.stderr

    # 3. Test wrong staged-tree SHA rejection
    write_all(staged_tree_sha_override="wrong_staged_tree_sha")
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "BLOCK: Staged-tree SHA mismatch" in res.stdout or "BLOCK: Staged-tree SHA mismatch" in res.stderr

    # 4. Test stale generation timestamp rejection
    write_all(timestamp_override="2026-07-14T22:00:00Z") # before 23:00 start
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 1
    assert "BLOCK: Report is stale" in res.stdout or "BLOCK: Report is stale" in res.stderr
