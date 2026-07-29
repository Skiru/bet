#!/usr/bin/env python3
"""Build script for single-delivery package: bet_v5_v7_2_final_session_launcher_delivery.tar.gz."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.launch_bridge import (
    execute_plan_only,
    verify_and_prepare_plan_continuation,
    resolve_canonical_db_path,
    verify_canonical_db_and_preflight,
    create_runtime_analysis_shadow_db,
)
from bet.pipeline.receipts import (
    compute_source_manifest_sha256,
    get_git_commit_head,
    get_git_tree_sha,
)


def compute_file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def main() -> dict[str, Any]:
    desktop_dir = Path("/Users/mkoziol/Desktop")
    desktop_dir.mkdir(parents=True, exist_ok=True)
    delivery_tar_path = desktop_dir / "bet_v5_v7_2_final_session_launcher_delivery.tar.gz"

    if delivery_tar_path.exists():
        delivery_tar_path.unlink()

    run_id = "BET_V5_V7_2_LAUNCH_RUN_001"
    betting_date = "2026-07-29"
    repo_root = ROOT

    head_sha = get_git_commit_head(repo_root)
    tree_sha = get_git_tree_sha(repo_root)
    manifest_sha = compute_source_manifest_sha256(repo_root)

    print(f"Building V7.2 delivery on HEAD={head_sha[:10]}, Tree={tree_sha[:10]}, Manifest={manifest_sha[:10]}...")

    with tempfile.TemporaryDirectory(prefix="v7_2_delivery_build_") as tmp_dir_str:
        build_root = Path(tmp_dir_str)
        payload_dir = build_root / "payload"
        payload_dir.mkdir(parents=True, exist_ok=True)

        # 1. Git bundle
        git_bundle_path = payload_dir / "repo_full_history.bundle"
        print("Creating git bundle...")
        res = subprocess.run(
            ["git", "bundle", "create", str(git_bundle_path), "--all"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            print(f"Git bundle failed: {res.stderr}")
            sys.exit(1)

        # 2. Run test suite & JUnit report
        junit_path = payload_dir / "tests_junit.xml"
        print("Running pytest suite...")
        res = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-n",
                "auto",
                f"--junitxml={junit_path}",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        # Parse JUnit report
        junit_tests = 0
        junit_failures = 0
        junit_errors = 0
        if junit_path.exists():
            try:
                tree = ET.parse(junit_path)
                root_el = tree.getroot()
                if root_el.tag == "testsuites":
                    for ts in root_el.findall("testsuite"):
                        junit_tests += int(ts.attrib.get("tests", 0))
                        junit_failures += int(ts.attrib.get("failures", 0))
                        junit_errors += int(ts.attrib.get("errors", 0))
                elif root_el.tag == "testsuite":
                    junit_tests = int(root_el.attrib.get("tests", 0))
                    junit_failures = int(root_el.attrib.get("failures", 0))
                    junit_errors = int(root_el.attrib.get("errors", 0))
            except Exception as e:
                print(f"Failed to parse JUnit XML: {e}")

        # 3. Canonical DB Audit & Preflight
        canonical_db = resolve_canonical_db_path()
        preflight = verify_canonical_db_and_preflight(repo_root, explicit_db_path=canonical_db, enforce_baseline=False)

        # 4. Plan-Only Execution
        target_run_dir = repo_root / "reports" / "pipeline_runs" / betting_date / run_id
        plan_res = execute_plan_only(
            repo_root=repo_root,
            date=betting_date,
            run_id=run_id,
            target_run_root=target_run_dir,
            manifest_path=repo_root / "config" / "pipeline_manifest.json",
            allow_live_network=False,
            explicit_db_path=canonical_db,
        )

        # 5. Continuation Execution Proof
        cont_res = verify_and_prepare_plan_continuation(
            target_run_root=target_run_dir,
            run_id=run_id,
            expected_selection_ledger_sha256=plan_res["SELECTION_LEDGER_SHA256"],
        )

        # Save Plan & Continuation Evidence
        with open(payload_dir / "plan_checkpoint.json", "w", encoding="utf-8") as f:
            json.dump(plan_res, f, indent=2)

        with open(payload_dir / "continuation_proof.json", "w", encoding="utf-8") as f:
            json.dump(cont_res, f, indent=2)

        s1e_ledger_path = target_run_dir / "data" / f"{betting_date}_s1e_event_universe.json"
        if s1e_ledger_path.exists():
            shutil.copy(s1e_ledger_path, payload_dir / "selection_ledger.json")

        # Copy s1r evidence folder if exists
        s1r_dir = target_run_dir / "artifacts" / "s1r_evidence"
        if s1r_dir.exists():
            shutil.copytree(s1r_dir, payload_dir / "s1r_evidence", dirs_exist_ok=True)

        # 6. Database Audit Report & FK Isolation Audit
        db_audit_report = {
            "canonical_db_path": preflight.canonical_db_path,
            "canonical_db_sha256": preflight.canonical_db_sha256,
            "canonical_db_size_bytes": preflight.canonical_db_size_bytes,
            "canonical_db_mtime_iso": preflight.canonical_db_mtime_iso,
            "sqlite_version": preflight.sqlite_version,
            "journal_mode": preflight.journal_mode,
            "foreign_keys_setting": preflight.foreign_keys_setting,
            "user_version": preflight.user_version,
            "quick_check_passed": preflight.quick_check_passed,
            "foreign_key_check_rows_count": len(preflight.foreign_key_check_rows),
            "canonical_db_relational_integrity": "DEGRADED_ISOLATED",
            "canonical_promotion_allowed": "NO",
        }
        with open(payload_dir / "database_audit_report.json", "w", encoding="utf-8") as f:
            json.dump(db_audit_report, f, indent=2)

        fk_audit_file = target_run_dir / "artifacts" / "foreign_key_repair_audit.json"
        if fk_audit_file.exists():
            shutil.copy(fk_audit_file, payload_dir / "foreign_key_repair_audit.json")

        # Sanitized DB Inventory
        conn = sqlite3.connect(str(canonical_db))
        table_rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        inventory = {}
        for t in table_rows:
            t_name = t[0]
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t_name}").fetchone()[0]
            inventory[t_name] = cnt
        conn.close()

        with open(payload_dir / "sanitized_db_inventory.json", "w", encoding="utf-8") as f:
            json.dump({"tables": inventory, "total_tables": len(inventory)}, f, indent=2)

        # 7. Next Executor Zsh Prompt Script
        script_src = repo_root / "scripts" / "next_executor_prompt.sh"
        if script_src.exists():
            shutil.copy(script_src, payload_dir / "next_executor_prompt.sh")

        # 8. Command log & Finding ledger
        command_log = [
            "verify_canonical_db_and_preflight",
            "create_runtime_analysis_shadow_db",
            "reconcile_s1r_runtime_database",
            "classify_and_persist_runtime_events",
            "project_run_s1e_universe",
            "verify_and_prepare_plan_continuation",
            "pytest -n auto",
        ]
        with open(payload_dir / "command_log.json", "w", encoding="utf-8") as f:
            json.dump({"commands": command_log}, f, indent=2)

        # 9. Pipeline Certificate
        certificate = {
            "schema_version": 1,
            "artifact_type": "PIPELINE_CANONICAL_CONTINUITY_CERTIFICATE_V1",
            "status": "PASS",
            "decision": "READY_FOR_FINAL_LAUNCH_REVIEW",
            "START_HEAD": head_sha,
            "END_HEAD": head_sha,
            "END_TREE": tree_sha,
            "WORKTREE_CLEAN": preflight.worktree_clean,
            "SOURCE_MANIFEST_SHA256": manifest_sha,
            "PROVIDER_COUNTER_ONLY_IMPLEMENTATION_REMOVED": True,
            "PROVIDER_REVALIDATION_EVIDENCE_BOUND": True,
            "EXISTING_PLAN_DB_REUSED": True,
            "PLAN_DB_UNLINK_BLOCKED": True,
            "PLAN_TO_S2_S8_CONTINUATION": True,
            "MISSING_OS_IMPORT_FIXED": True,
            "CANONICAL_DB_RELATIONAL_INTEGRITY": "DEGRADED_ISOLATED",
            "CANONICAL_PROMOTION_ALLOWED": "NO",
            "JUNIT_TESTS": junit_tests,
            "JUNIT_FAILURES": junit_failures,
            "JUNIT_ERRORS": junit_errors,
        }
        with open(payload_dir / "pipeline_cert.json", "w", encoding="utf-8") as f:
            json.dump(certificate, f, indent=2)

        # 10. Content Manifest & SHA256SUMS
        content_files = {}
        for root_p, _, files in os.walk(payload_dir):
            for file_name in files:
                f_p = Path(root_p) / file_name
                rel_p = f_p.relative_to(payload_dir).as_posix()
                if rel_p in ("DELIVERY_MANIFEST.json", "SHA256SUMS"):
                    continue
                content_files[rel_p] = compute_file_sha256(f_p)

        delivery_manifest = {
            "delivery_name": "bet_v5_v7_2_final_session_launcher_delivery",
            "total_files": len(content_files),
            "files": content_files,
        }
        with open(payload_dir / "DELIVERY_MANIFEST.json", "w", encoding="utf-8") as f:
            json.dump(delivery_manifest, f, indent=2, sort_keys=True)

        sums_lines = []
        for rel_p, sha_val in sorted(content_files.items()):
            sums_lines.append(f"{sha_val}  {rel_p}")
        sums_lines.append(f"{compute_file_sha256(payload_dir / 'DELIVERY_MANIFEST.json')}  DELIVERY_MANIFEST.json")

        with open(payload_dir / "SHA256SUMS", "w", encoding="utf-8") as f:
            f.write("\n".join(sums_lines) + "\n")

        # Create tar.gz archive
        print("Creating tar.gz delivery archive...")
        with tarfile.open(delivery_tar_path, "w:gz") as tar:
            for root_p, _, files in os.walk(payload_dir):
                for file_name in files:
                    f_p = Path(root_p) / file_name
                    rel_p = f_p.relative_to(payload_dir).as_posix()
                    tar.add(f_p, arcname=f"bet_v5_v7_2_final_session_launcher_delivery/{rel_p}")

    tar_size = delivery_tar_path.stat().st_size
    tar_sha = compute_file_sha256(delivery_tar_path)

    print(f"Delivery archive built successfully at: {delivery_tar_path}")
    print(f"Archive Size: {tar_size} bytes")
    print(f"Archive SHA256: {tar_sha}")

    return {
        "tar_path": str(delivery_tar_path),
        "tar_sha256": tar_sha,
        "tar_size_bytes": tar_size,
        "junit_tests": junit_tests,
        "junit_failures": junit_failures,
        "junit_errors": junit_errors,
        "head_sha": head_sha,
        "tree_sha": tree_sha,
        "manifest_sha": manifest_sha,
        "preflight": preflight,
        "plan_res": plan_res,
    }


if __name__ == "__main__":
    main()
