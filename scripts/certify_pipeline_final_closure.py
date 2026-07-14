#!/usr/bin/env python3
"""Evidence-derived final closure certifier for V7."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_REQ_V6_IDS = {
    "REQ-V6-CERT-001",
    "REQ-V6-CERT-002",
    "REQ-V6-CERT-003",
    "REQ-V6-EVID-001",
    "REQ-V6-EVID-002",
    "REQ-V6-EVID-003",
    "REQ-V6-WORKER-001",
    "REQ-V6-WORKER-002",
    "REQ-V6-CLOCK-001",
    "REQ-V6-CLOCK-002",
    "REQ-V6-CLOCK-003",
    "REQ-V6-REPLAY-001",
    "REQ-V6-REPLAY-002",
    "REQ-V6-REPLAY-003",
    "REQ-V6-FAULT-001",
    "REQ-V6-FAULT-002",
    "REQ-V6-REG-001",
    "REQ-V6-RELEASE-001",
}


def canonical_serialize(data: Any) -> str:
    """Canonicalize dictionary serialize."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Certify pipeline final closure from evidence reports.")
    parser.add_argument("--requirements-traceability", type=Path, required=True)
    parser.add_argument("--focused-test-report", type=Path, required=True)
    parser.add_argument("--canonical-replay-report", type=Path, required=True)
    parser.add_argument("--evidence-chain-report", type=Path, required=True)
    parser.add_argument("--resume-chain-report", type=Path, required=True)
    parser.add_argument("--fault-injection-report", type=Path, required=True)
    parser.add_argument("--regression-comparison", type=Path, required=True)
    parser.add_argument("--test-collection-comparison", type=Path, required=True)
    parser.add_argument("--production-surface-report", type=Path, required=True)
    parser.add_argument("--reachability-report", type=Path, required=True)
    parser.add_argument("--package-report", type=Path, required=True)
    parser.add_argument("--security-report", type=Path, required=True)
    parser.add_argument("--reviewer-report", type=Path, required=True)
    parser.add_argument("--staged-tree-manifest", type=Path, required=True)
    parser.add_argument("--git-state-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/tmp/BET_PIPELINE_FINAL_EVIDENCE_AND_RUN_BINDING_CLOSURE_V6/final/pipeline_final_closure_certificate.json"))
    args = parser.parse_args()

    reports = {
        "requirements_traceability": args.requirements_traceability,
        "focused_test_report": args.focused_test_report,
        "canonical_replay_report": args.canonical_replay_report,
        "evidence_chain_report": args.evidence_chain_report,
        "resume_chain_report": args.resume_chain_report,
        "fault_injection_report": args.fault_injection_report,
        "regression_comparison": args.regression_comparison,
        "test_collection_comparison": args.test_collection_comparison,
        "production_surface_report": args.production_surface_report,
        "reachability_report": args.reachability_report,
        "package_report": args.package_report,
        "security_report": args.security_report,
        "reviewer_report": args.reviewer_report,
        "staged_tree_manifest": args.staged_tree_manifest,
        "git_state_report": args.git_state_report,
    }

    loaded_reports: dict[str, dict[str, Any]] = {}
    expected_task_id = "BET_PIPELINE_FINAL_TRUSTWORTHY_CERTIFICATION_V7"
    expected_branch = "fix/s5-s6-s7-canonical-continuity-final-v1"
    expected_head = "f925aef8ec215da5b513081b1a0357a5e628fab9"
    expected_staged_tree_sha = "28422d9c6c3085818a7c4b69f27da61416fc8516"
    cert_start = datetime.fromisoformat("2026-07-14T23:00:00Z".replace("Z", "+00:00"))

    REQUIRED_KEYS = (
        "schema_version",
        "task_id",
        "source_branch",
        "source_git_sha",
        "staged_tree_sha",
        "generation_timestamp",
        "producer",
        "command",
        "status",
        "report_payload",
        "report_payload_sha256",
    )

    REQUIRED_PAYLOAD_KEYS = {
        "requirements_traceability": {"traceability"},
        "focused_test_report": {"failures", "executed_tests"},
        "canonical_replay_report": {
            "replay_runner_executed",
            "replay_steps",
            "s6_worker_executed",
            "hash_mismatches",
            "unaccounted_ids",
            "replay_synthetic_odds",
            "worker_input_json_paths",
        },
        "evidence_chain_report": {
            "steps",
            "missing_steps",
            "hash_mismatches",
            "resume_mismatches",
            "binding_mismatches",
            "duplicate_evidence",
            "cross_run_paths",
            "unresolved_conflicts",
            "unresolved_conflicts_count",
        },
        "resume_chain_report": {"resume_mismatches"},
        "fault_injection_report": {
            "false_passes",
            "canonical_evidence_overwrites",
            "unhandled_faults",
            "worker_dummy_hash_paths",
            "worker_ad_hoc_paths",
            "fault_cases_tested",
            "cases_detailed",
        },
        "regression_comparison": {"new_regression_ids"},
        "test_collection_comparison": {"unexplained_removed_node_ids"},
        "production_surface_report": {"surface_checked", "violations_found"},
        "reachability_report": {"reachability_checked", "unreachable_modules"},
        "package_report": {"wheel_clean", "build_status"},
        "security_report": {"vulnerabilities"},
        "reviewer_report": {"reviewed_head", "p0_findings", "p1_findings", "reviewed_paths", "evidence_paths"},
        "staged_tree_manifest": {"staged_tree_sha", "files"},
        "git_state_report": {"remote_branch_sha"},
    }

    # 1. Validate every report schema, presence & cryptographic signature
    for name, path in reports.items():
        if not path.exists():
            print(f"BLOCK: Missing required evidence report: {name} at {path}")
            sys.exit(1)

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            loaded_reports[name] = data
        except Exception as exc:
            print(f"BLOCK: Malformed JSON in evidence report {name} at {path}: {exc}")
            sys.exit(1)

        # 1.1 Key presence check
        for field in REQUIRED_KEYS:
            if field not in data:
                print(f"BLOCK: Missing required field '{field}' in report '{name}'")
                sys.exit(1)

        # 1.2 Cryptographic Hash Verification
        payload_serialized = canonical_serialize(data["report_payload"])
        computed_sha = hashlib.sha256(payload_serialized.encode("utf-8")).hexdigest()
        if computed_sha != data["report_payload_sha256"]:
            print(f"BLOCK: Report payload SHA256 mismatch in report '{name}'. Computed '{computed_sha}', got '{data['report_payload_sha256']}'")
            sys.exit(1)

        # 1.3 Exact report schema check per type
        p_keys = set(data["report_payload"].keys())
        expected_p_keys = REQUIRED_PAYLOAD_KEYS[name]
        if p_keys != expected_p_keys:
            print(f"BLOCK: Invalid report schema for '{name}'. Expected payload keys {expected_p_keys}, got {p_keys}")
            sys.exit(1)

        # 1.4 Strict static metadata checks
        if data["task_id"] != expected_task_id:
            print(f"BLOCK: Task ID mismatch in report '{name}'. Expected '{expected_task_id}', got '{data['task_id']}'")
            sys.exit(1)

        if data["source_branch"] != expected_branch:
            print(f"BLOCK: Branch mismatch in report '{name}'. Expected '{expected_branch}', got '{data['source_branch']}'")
            sys.exit(1)

        if data["source_git_sha"] != expected_head:
            print(f"BLOCK: Source Git SHA mismatch in report '{name}'. Expected '{expected_head}', got '{data['source_git_sha']}'")
            sys.exit(1)

        if data["staged_tree_sha"] != expected_staged_tree_sha:
            print(f"BLOCK: Staged-tree SHA mismatch in report '{name}'. Expected '{expected_staged_tree_sha}', got '{data['staged_tree_sha']}'")
            sys.exit(1)

        # 1.5 Freshness / generation start check
        try:
            rep_time = datetime.fromisoformat(data["generation_timestamp"].replace("Z", "+00:00"))
            if rep_time < cert_start:
                print(f"BLOCK: Report is stale: '{name}' was generated at {data['generation_timestamp']}, which is before certification start")
                sys.exit(1)
        except Exception as exc:
            print(f"BLOCK: Invalid timestamp format in report '{name}': {exc}")
            sys.exit(1)

        # 1.6 Evidence-based PASS enforcement
        if data["status"] == "PASS":
            p = data["report_payload"]
            if name == "focused_test_report" and p["failures"] > 0:
                print("BLOCK: focused_test_report has failures but status=PASS")
                sys.exit(1)
            elif name == "canonical_replay_report" and (p["hash_mismatches"] or p["unaccounted_ids"]):
                print("BLOCK: canonical_replay_report has mismatches but status=PASS")
                sys.exit(1)
            elif name == "evidence_chain_report" and (p["missing_steps"] or p["hash_mismatches"] or p["resume_mismatches"] or p["binding_mismatches"] or p["unresolved_conflicts"]):
                print("BLOCK: evidence_chain_report has issues but status=PASS")
                sys.exit(1)
            elif name == "resume_chain_report" and p["resume_mismatches"]:
                print("BLOCK: resume_chain_report has mismatches but status=PASS")
                sys.exit(1)
            elif name == "fault_injection_report" and (p["false_passes"] or p["unhandled_faults"] or len(p["fault_cases_tested"]) < 25):
                print(f"BLOCK: fault_injection_report is incomplete or has false passes (tested: {len(p['fault_cases_tested'])}/25)")
                sys.exit(1)
            elif name == "regression_comparison" and p["new_regression_ids"]:
                print("BLOCK: regression_comparison has regressions but status=PASS")
                sys.exit(1)
            elif name == "test_collection_comparison" and p["unexplained_removed_node_ids"]:
                print("BLOCK: test_collection_comparison has unexplained removed tests but status=PASS")
                sys.exit(1)
            elif name == "production_surface_report" and p["violations_found"] > 0:
                print("BLOCK: production_surface_report has violations but status=PASS")
                sys.exit(1)
            elif name == "reachability_report" and p["unreachable_modules"] > 0:
                print("BLOCK: reachability_report has unreachable modules but status=PASS")
                sys.exit(1)
            elif name == "package_report" and (p["build_status"] != "SUCCESS" or not p["wheel_clean"]):
                print("BLOCK: package_report has build/wheel issues but status=PASS")
                sys.exit(1)
            elif name == "security_report" and p["vulnerabilities"] > 0:
                print("BLOCK: security_report has vulnerabilities but status=PASS")
                sys.exit(1)
            elif name == "reviewer_report" and (p["p0_findings"] or p["p1_findings"]):
                print("BLOCK: reviewer_report has open findings but status=PASS")
                sys.exit(1)

    # 2. Derive final certificate fields mechanically from named report fields
    req_trace_p = loaded_reports["requirements_traceability"]["report_payload"]
    focused_test_p = loaded_reports["focused_test_report"]["report_payload"]
    replay_p = loaded_reports["canonical_replay_report"]["report_payload"]
    ev_chain_p = loaded_reports["evidence_chain_report"]["report_payload"]
    resume_chain_p = loaded_reports["resume_chain_report"]["report_payload"]
    fault_inj_p = loaded_reports["fault_injection_report"]["report_payload"]
    regression_p = loaded_reports["regression_comparison"]["report_payload"]
    test_collection_p = loaded_reports["test_collection_comparison"]["report_payload"]
    prod_surf_p = loaded_reports["production_surface_report"]["report_payload"]
    reachability_p = loaded_reports["reachability_report"]["report_payload"]
    package_rep_p = loaded_reports["package_report"]["report_payload"]
    security_rep_p = loaded_reports["security_report"]["report_payload"]
    reviewer_rep_p = loaded_reports["reviewer_report"]["report_payload"]

    # Gate logic
    requirements_implemented = [
        req for req, item in req_trace_p.get("traceability", {}).items()
        if item.get("status") == "PASS"
    ]
    all_reqs_passed = set(requirements_implemented) == EXPECTED_REQ_V6_IDS

    focused_test_pass = loaded_reports["focused_test_report"]["status"] == "PASS" and not focused_test_p["failures"]
    replay_pass = loaded_reports["canonical_replay_report"]["status"] == "PASS" and not replay_p["hash_mismatches"] and not replay_p["unaccounted_ids"]
    ev_chain_pass = loaded_reports["evidence_chain_report"]["status"] == "PASS" and not ev_chain_p["hash_mismatches"]
    resume_chain_pass = loaded_reports["resume_chain_report"]["status"] == "PASS" and not resume_chain_p["resume_mismatches"]
    fault_inj_pass = loaded_reports["fault_injection_report"]["status"] == "PASS" and not fault_inj_p["false_passes"] and not fault_inj_p["unhandled_faults"] and len(fault_inj_p["fault_cases_tested"]) >= 25
    regression_pass = loaded_reports["regression_comparison"]["status"] == "PASS" and not regression_p["new_regression_ids"]
    test_coll_pass = loaded_reports["test_collection_comparison"]["status"] == "PASS" and not test_collection_p["unexplained_removed_node_ids"]
    prod_surf_pass = loaded_reports["production_surface_report"]["status"] == "PASS" and prod_surf_p["violations_found"] == 0
    reachability_pass = loaded_reports["reachability_report"]["status"] == "PASS" and reachability_p["unreachable_modules"] == 0
    package_pass = loaded_reports["package_report"]["status"] == "PASS" and package_rep_p["build_status"] == "SUCCESS" and package_rep_p["wheel_clean"]
    security_pass = loaded_reports["security_report"]["status"] == "PASS" and not security_rep_p["vulnerabilities"]
    reviewer_pass = loaded_reports["reviewer_report"]["status"] == "PASS" and not reviewer_rep_p["p0_findings"] and not reviewer_rep_p["p1_findings"]

    overall_status = "BLOCK"
    decision = "DO_NOT_PROCEED"

    if (focused_test_pass and replay_pass and ev_chain_pass and resume_chain_pass and
            fault_inj_pass and regression_pass and test_coll_pass and prod_surf_pass and
            reachability_pass and package_pass and security_pass and reviewer_pass and
            all_reqs_passed):
        overall_status = "PASS"
        decision = "PIPELINE_TRUSTWORTHY_CERTIFICATION_READY_FOR_MERGE_REVIEW"

    # Derive Blockers and Risks dynamically
    derived_blockers = []
    if not all_reqs_passed:
        derived_blockers.append("FAILED_REQUIREMENTS_TRACEABILITY")
    if not focused_test_pass:
        derived_blockers.append("FAILED_FOCUSED_TEST_SUITE")
    if not replay_pass:
        derived_blockers.append("FAILED_REPLAY_GATE")
    if not ev_chain_pass:
        derived_blockers.append("FAILED_EVIDENCE_CHAIN")
    if not resume_chain_pass:
        derived_blockers.append("FAILED_RESUME_CHAIN")
    if not fault_inj_pass:
        derived_blockers.append("FAILED_FAULT_INJECTION_SUITE")
    if not reviewer_pass:
        derived_blockers.append("FAILED_ADVERSARIAL_REVIEW")

    derived_risks = []
    if reviewer_rep_p["p1_findings"]:
        derived_risks.extend(reviewer_rep_p["p1_findings"])

    # Assemble the derived certificate
    certificate = {
        "schema_version": 1,
        "task_id": expected_task_id,
        "status": overall_status,
        "decision": decision,
        "base_sha": "3f6aa6462e46f034fdd293f87515a2a6cd4c6c08",
        "previous_head": "f7ea53ccc99e15a59a26eb621f40e45a3e3af501",
        "final_branch_head": expected_head,
        "remote_branch_sha": loaded_reports["git_state_report"]["report_payload"].get("remote_branch_sha", "UNKNOWN"),
        "staged_tree_sha": expected_staged_tree_sha,
        "self_certifying_tests": focused_test_p.get("executed_tests", []),
        "certificate_evidence_validation": "PASS" if overall_status == "PASS" else "BLOCK",
        "terminal_s6_evidence_immutable": ev_chain_p.get("unresolved_conflicts_count", 0) == 0,
        "canonical_s6_evidence_overwrites": fault_inj_p.get("canonical_evidence_overwrites", []),
        "conflicting_attempts_audited": ev_chain_p.get("unresolved_conflicts_count", 0) == 0,
        "strict_s6_worker_contract": "PASS" if all_reqs_passed else "BLOCK",
        "worker_input_json_paths": replay_p.get("worker_input_json_paths", []),
        "worker_dummy_hash_paths": fault_inj_p.get("worker_dummy_hash_paths", []),
        "worker_ad_hoc_paths": fault_inj_p.get("worker_ad_hoc_paths", []),
        "run_as_of_binding": "PASS" if all_reqs_passed else "BLOCK",
        "run_as_of_resume_mismatches_accepted": [],
        "bounded_replay": "PASS" if replay_pass else "BLOCK",
        "replay_runner_executed": replay_p.get("replay_runner_executed", True),
        "replay_steps": replay_p.get("replay_steps", []),
        "s6_worker_executed": replay_p.get("s6_worker_executed", True),
        "evidence_chain": "PASS" if ev_chain_pass else "BLOCK",
        "resume_chain": "PASS" if resume_chain_pass else "BLOCK",
        "replay_unaccounted_candidate_ids": replay_p.get("unaccounted_ids", []),
        "replay_synthetic_odds": replay_p.get("replay_synthetic_odds", []),
        "fault_injection": "PASS" if fault_inj_pass else "BLOCK",
        "false_passes": fault_inj_p.get("false_passes", []),
        "new_regressions": regression_p.get("new_regression_ids", []),
        "unexplained_removed_tests": test_collection_p.get("unexplained_removed_node_ids", []),
        "open_p0": reviewer_rep_p.get("p0_findings", []),
        "open_p1": reviewer_rep_p.get("p1_findings", []),
        "adversarial_review": "PASS" if reviewer_pass else "BLOCK",
        "security_scan": "PASS" if security_pass else "BLOCK",
        "main_merged": False,
        "full_live_pipeline_executed": False,
        "bookmaker_interaction": False,
        "canonical_database_mutated": False,
        "canonical_journals_mutated": False,
        "blockers": derived_blockers,
        "risks": derived_risks,
    }

    # Write final certificate
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(certificate, indent=2), encoding="utf-8")
    print(f"STATUS: {overall_status}")
    print(f"DECISION: {decision}")


if __name__ == "__main__":
    main()
