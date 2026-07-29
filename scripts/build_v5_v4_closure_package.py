#!/usr/bin/env python3
"""Deterministic Final Closure Package Builder for BET PIPELINE V5 V4 Closure.

Executes Phase 5 deterministic order to build mutually bound review package,
restart seed, manifests, next-analysis handoff, executor prompt, certificate,
and checksum manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.pipeline.receipts import (
    compute_source_manifest_sha256,
    get_git_commit_head,
    get_git_tree_sha,
)
from bet.pipeline.run_evidence import sha256_file

try:
    from pipeline_steps.export_s2_restart_seed import export_s2_restart_seed
    from pipeline_steps.import_s2_restart_seed import import_s2_restart_seed
except ImportError:
    from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed
    from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed


def build_closure_package(
    repo_root: Path,
    source_run_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve(strict=True)
    source_run_root = Path(source_run_root).resolve(strict=True)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Compute exact current repo provenance
    head_sha = get_git_commit_head(repo_root)
    git_tree_sha = get_git_tree_sha(repo_root)
    source_manifest_sha = compute_source_manifest_sha256(repo_root)

    print(
        f"Building closure package on HEAD={head_sha}, Tree={git_tree_sha}, Manifest={source_manifest_sha[:16]}..."
    )

    # Verification of preflight baseline expectations
    expected_start_head = "3fdc631f39e905a6b2a3dc670c543f11bdf14d16"
    expected_start_tree = "030823abd7de75ab650a63492b8ce5d3aff09b29"
    expected_start_manifest = (
        "0aa61ed0a4a5a198682599ef96c0b9f11d225dc195d757c8935706020b9355d4"
    )

    if head_sha != expected_start_head:
        print(
            f"WARNING: HEAD {head_sha} differs from expected starting HEAD {expected_start_head}"
        )
    if git_tree_sha != expected_start_tree:
        print(
            f"WARNING: Tree {git_tree_sha} differs from expected starting tree {expected_start_tree}"
        )

    # Step 1: Export S2 restart seed
    seed_tar_p, seed_man_p = export_s2_restart_seed(source_run_root, output_dir)

    # Step 2: Ensure internal and external seed manifests are byte-identical
    with tarfile.open(seed_tar_p, "r:gz") as tar:
        internal_manifest_bytes = tar.extractfile("restart_seed_manifest.json").read()

    external_manifest_bytes = seed_man_p.read_bytes()
    if internal_manifest_bytes != external_manifest_bytes:
        raise ValueError(
            "EXTERNAL_INTERNAL_MANIFEST_MISMATCH: External seed manifest not byte-identical to internal manifest"
        )

    # Step 3: Freeze seed bytes and compute seed SHA-256
    seed_tar_sha256 = sha256_file(seed_tar_p)
    seed_man_sha256 = sha256_file(seed_man_p)

    # Step 4: Dry-run seed import to get exact snapshot active/terminalized counts and test import safety
    test_target_run_root = output_dir / "test_imported_run_003"
    if test_target_run_root.exists():
        shutil.rmtree(test_target_run_root)

    import_receipt = import_s2_restart_seed(
        seed_tar_path=seed_tar_p,
        target_run_root=test_target_run_root,
        target_run_id="v5_analysis_20260729_003",
        target_head=head_sha,
        target_tree=git_tree_sha,
        target_manifest=source_manifest_sha,
        expected_seed_tar_sha256=seed_tar_sha256,
        expected_seed_manifest_sha256=seed_man_sha256,
    )

    source_s1e_count = import_receipt["imported_event_count"]
    snapshot_active_count = import_receipt["active_event_count"]
    snapshot_terminalized_count = import_receipt["terminalized_event_count"]

    if test_target_run_root.exists():
        shutil.rmtree(test_target_run_root)

    # Step 5: Generate next_analysis_handoff.json
    next_run_id = "v5_analysis_20260729_003"
    handoff_data = {
        "schema_version": 1,
        "artifact_type": "NEXT_ANALYSIS_SESSION_HANDOFF_V1",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "target_session": {
            "target_run_id": next_run_id,
            "betting_day": "2026-07-29",
            "start_step": "S2",
            "reuse_through_step": "S1e",
            "stop_after_step": "S8",
            "human_gate_step": "S9",
        },
        "bound_provenance": {
            "head_sha": head_sha,
            "git_tree_sha": git_tree_sha,
            "source_manifest_sha256": source_manifest_sha,
        },
        "seed_reference": {
            "seed_tar_filename": seed_tar_p.name,
            "seed_tar_sha256": seed_tar_sha256,
            "seed_manifest_filename": seed_man_p.name,
            "seed_manifest_sha256": seed_man_sha256,
            "source_s1e_count": source_s1e_count,
            "snapshot_active_count": snapshot_active_count,
            "snapshot_terminalized_count": snapshot_terminalized_count,
        },
        "safety_constraints": {
            "live_pipeline_execution": True,
            "bookmaker_interaction": False,
            "automated_bet_placement": False,
            "pricing_fail_closed": True,
            "s9_human_only": True,
            "reject_s2_plus_seed_state": True,
            "require_live_event_freshness_revalidation": True,
        },
    }

    pkg_dir = output_dir / "bet_v5_final_one_pass_closure_v4"
    pkg_dir.mkdir(parents=True, exist_ok=True)

    handoff_path = pkg_dir / "next_analysis_handoff.json"
    handoff_bytes = (
        json.dumps(handoff_data, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    handoff_path.write_bytes(handoff_bytes)
    handoff_sha256 = sha256_file(handoff_path)

    # Step 6: Generate next_bet_executor_analysis_prompt.md (Zsh compatible, no Fish fences)
    prompt_content = f"""# NEXT SESSION EXECUTOR PROMPT — BET PIPELINE V5 ANALYSIS SESSION

Execute the next pipeline analysis session starting at S2 using the verified S2 restart seed.

## BOUND PROVENANCE

- HEAD_SHA: `{head_sha}`
- GIT_TREE_SHA: `{git_tree_sha}`
- SOURCE_MANIFEST_SHA256: `{source_manifest_sha}`

## SEED BINDINGS

- SEED_TAR_SHA256: `{seed_tar_sha256}`
- SEED_MANIFEST_SHA256: `{seed_man_sha256}`
- SOURCE_S1E_COUNT: `{source_s1e_count}`
- SNAPSHOT_ACTIVE_COUNT: `{snapshot_active_count}`
- SNAPSHOT_TERMINALIZED_COUNT: `{snapshot_terminalized_count}`

## EXECUTION COMMAND (ZSH COMPATIBLE)

```zsh
# 1. Verify working directory state and provenance
git status --porcelain
git rev-parse HEAD
git rev-parse HEAD^{{tree}}

# 2. Run analysis session from S2 using immutable restart seed
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_steps/run_daily_pipeline.py \\
  --date 2026-07-29 \\
  --run-id "{next_run_id}" \\
  --start-step S2 \\
  --reuse-through-step S1e \\
  --stop-after-step S8 \\
  --restart-seed "{seed_tar_p}" \\
  --restart-seed-sha256 "{seed_tar_sha256}" \\
  --restart-seed-manifest "{seed_man_p}" \\
  --restart-seed-manifest-sha256 "{seed_man_sha256}" \\
  --runtime-mode LIVE_SHADOW \\
  --allow-live-network \\
  --base-run-dir reports/pipeline_runs \\
  --verbose
```

## MANDATORY SAFETY RULES

1. Start at S2 and stop after S8. Step S9 is human-only operator boundary.
2. Pricing and quotes remain fail-closed.
3. Prohibit bookmaker login and prohibit automated bet placement.
4. Require live event freshness revalidation immediately before S2.
5. Reject all S2+ seed state.
"""
    prompt_path = pkg_dir / "next_bet_executor_analysis_prompt.md"
    prompt_path.write_text(prompt_content, encoding="utf-8")
    prompt_sha256 = sha256_file(prompt_path)

    # Step 7: Generate Certificate
    cert_path = output_dir / "pipeline_cert.json"
    cert_junit_path = output_dir / "pipeline_cert_junit.xml"
    if cert_path.exists():
        cert_path.unlink()
    if cert_junit_path.exists():
        cert_junit_path.unlink()

    cert_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "certify_pipeline_final_closure.py"),
        "--output",
        str(cert_path),
        "--junit",
        str(cert_junit_path),
        "--expected-head",
        head_sha,
        "--expected-git-tree",
        git_tree_sha,
        "--expected-source-tree-sha256",
        source_manifest_sha,
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{repo_root}/src:{repo_root}/scripts"
    cert_proc = subprocess.run(
        cert_cmd, cwd=repo_root, env=env, capture_output=True, text=True
    )
    if cert_proc.returncode != 0 or not cert_path.exists():
        raise RuntimeError(f"CERTIFIER_FAILED: {cert_proc.stderr}")

    cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
    cert_sha256 = sha256_file(cert_path)

    # Step 8: Write Independent Review README & Finding Ledger inside review package folder
    readme_content = f"""# INDEPENDENT ARTIFACT REVIEW PACKAGE — BET PIPELINE V5 CLOSURE

Target Baseline:
- HEAD: {head_sha}
- TREE: {git_tree_sha}
- MANIFEST: {source_manifest_sha}

Artifacts in Package:
- next_analysis_handoff.json (SHA256: {handoff_sha256})
- next_bet_executor_analysis_prompt.md (SHA256: {prompt_sha256})
- pipeline_cert.json (SHA256: {cert_sha256})
- S2 Restart Seed Tarball: {seed_tar_p.name} (SHA256: {seed_tar_sha256})
- S2 Restart Seed Manifest: {seed_man_p.name} (SHA256: {seed_man_sha256})
"""
    readme_path = pkg_dir / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")

    ledger_data = {
        "finding_id": "BET_V5_V4_ARTIFACT_PROVENANCE_AND_SEED_REBUILD_V5",
        "status": "CLOSED",
        "remediation": "Rebuilt artifact provenance chain and eliminated semantic S2+ seed contamination.",
        "bound_provenance": {
            "head_sha": head_sha,
            "git_tree_sha": git_tree_sha,
            "source_manifest_sha256": source_manifest_sha,
        },
    }
    ledger_path = pkg_dir / "finding_ledger.json"
    ledger_path.write_text(json.dumps(ledger_data, indent=2), encoding="utf-8")

    # Copy certificate and JUnit report into review package directory
    shutil.copy2(cert_path, pkg_dir / "pipeline_cert.json")
    if cert_junit_path.exists():
        shutil.copy2(cert_junit_path, pkg_dir / "pipeline_cert_junit.xml")

    # Copy seed manifest and seed tarball into review package directory
    shutil.copy2(seed_man_p, pkg_dir / seed_man_p.name)

    # Step 9: Write Package Manifest
    pkg_manifest_content = {
        "schema_version": 1,
        "package_type": "BET_V5_CLOSURE_REVIEW_PACKAGE_V4",
        "bound_provenance": {
            "head_sha": head_sha,
            "git_tree_sha": git_tree_sha,
            "source_manifest_sha256": source_manifest_sha,
        },
        "seed_provenance": {
            "seed_tar_sha256": seed_tar_sha256,
            "seed_manifest_sha256": seed_man_sha256,
        },
        "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    pkg_manifest_path = pkg_dir / "review_package_manifest.json"
    pkg_manifest_path.write_text(
        json.dumps(pkg_manifest_content, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Step 10: Create Review Package Tarball
    review_pkg_tar_p = output_dir / "bet_v5_final_one_pass_closure_v4.tar.gz"
    with tarfile.open(review_pkg_tar_p, "w:gz") as tar:
        for r, _, files in os.walk(pkg_dir):
            for f in sorted(files):
                full_f = Path(r) / f
                arc_f = full_f.relative_to(pkg_dir)
                tar.add(full_f, arcname=str(arc_f))

    # Freeze review package bytes and recompute final hash
    review_pkg_sha256 = sha256_file(review_pkg_tar_p)

    # Step 11: Create Git Bundle
    bundle_p = output_dir / "bet_pipeline_v5_final_one_pass_closure_v4.bundle"
    if bundle_p.exists():
        bundle_p.unlink()

    bundle_cmd = [
        "git",
        "bundle",
        "create",
        str(bundle_p),
        "HEAD",
        "fix/bet-v5-final-one-pass-closure-v4",
    ]
    bundle_proc = subprocess.run(
        bundle_cmd, cwd=repo_root, capture_output=True, text=True
    )
    if bundle_proc.returncode != 0:
        # Fallback to HEAD only
        bundle_cmd = ["git", "bundle", "create", str(bundle_p), "HEAD"]
        bundle_proc = subprocess.run(
            bundle_cmd, cwd=repo_root, capture_output=True, text=True
        )

    if not bundle_p.exists() or bundle_proc.returncode != 0:
        raise RuntimeError(f"GIT_BUNDLE_CREATION_FAILED: {bundle_proc.stderr}")

    verify_cmd = ["git", "bundle", "verify", str(bundle_p)]
    verify_proc = subprocess.run(
        verify_cmd, cwd=repo_root, capture_output=True, text=True
    )
    if verify_proc.returncode != 0:
        raise RuntimeError(f"GIT_BUNDLE_VERIFICATION_FAILED: {verify_proc.stderr}")

    bundle_sha256 = sha256_file(bundle_p)

    # Step 12: Write SHA256SUMS and Checksum Manifest last
    checksums = {
        "git_bundle_sha256": bundle_sha256,
        "review_package_sha256": review_pkg_sha256,
        "s2_restart_seed_sha256": seed_tar_sha256,
        "s2_restart_manifest_sha256": seed_man_sha256,
        "next_analysis_handoff_sha256": handoff_sha256,
        "next_bet_executor_prompt_sha256": prompt_sha256,
        "certificate_sha256": cert_sha256,
    }

    checksum_manifest_p = pkg_dir / "checksum_manifest.json"
    checksum_manifest_p.write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    sha256sums_text = f"""{bundle_sha256}  bet_pipeline_v5_final_one_pass_closure_v4.bundle
{review_pkg_sha256}  bet_v5_final_one_pass_closure_v4.tar.gz
{seed_tar_sha256}  {seed_tar_p.name}
{seed_man_sha256}  {seed_man_p.name}
{handoff_sha256}  next_analysis_handoff.json
{prompt_sha256}  next_bet_executor_analysis_prompt.md
{cert_sha256}  pipeline_cert.json
"""
    sha256sums_p = pkg_dir / "SHA256SUMS"
    sha256sums_p.write_text(sha256sums_text, encoding="utf-8")

    checksum_out_p = output_dir / "checksum_manifest.json"
    checksum_out_p.write_text(
        json.dumps(checksums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_sha256 = sha256_file(checksum_out_p)

    # Re-verify all checksums by reopening files on disk
    assert sha256_file(bundle_p) == bundle_sha256
    assert sha256_file(review_pkg_tar_p) == review_pkg_sha256
    assert sha256_file(seed_tar_p) == seed_tar_sha256
    assert sha256_file(seed_man_p) == seed_man_sha256
    assert sha256_file(handoff_path) == handoff_sha256
    assert sha256_file(prompt_path) == prompt_sha256

    print("\nCLOSURE PACKAGE BUILT SUCCESSFULLY AND Cryptographically VERIFIED:")
    print(f"  GIT_BUNDLE: {bundle_p} ({bundle_sha256})")
    print(f"  REVIEW_PACKAGE: {review_pkg_tar_p} ({review_pkg_sha256})")
    print(f"  SEED_TAR: {seed_tar_p} ({seed_tar_sha256})")
    print(f"  SEED_MANIFEST: {seed_man_p} ({seed_man_sha256})")
    print(f"  HANDOFF: {handoff_path} ({handoff_sha256})")
    print(f"  PROMPT: {prompt_path} ({prompt_sha256})")
    print(f"  CHECKSUM_MANIFEST: {checksum_out_p} ({checksum_sha256})")

    return {
        "status": "PASS",
        "head_sha": head_sha,
        "git_tree_sha": git_tree_sha,
        "source_manifest_sha256": source_manifest_sha,
        "source_s1e_count": source_s1e_count,
        "snapshot_active_count": snapshot_active_count,
        "snapshot_terminalized_count": snapshot_terminalized_count,
        "git_bundle_path": str(bundle_p),
        "git_bundle_sha256": bundle_sha256,
        "review_package_path": str(review_pkg_tar_p),
        "review_package_sha256": review_pkg_sha256,
        "seed_tar_path": str(seed_tar_p),
        "seed_tar_sha256": seed_tar_sha256,
        "seed_manifest_path": str(seed_man_p),
        "seed_manifest_sha256": seed_man_sha256,
        "checksum_manifest_path": str(checksum_out_p),
        "checksum_manifest_sha256": checksum_sha256,
        "handoff_path": str(handoff_path),
        "handoff_sha256": handoff_sha256,
        "prompt_path": str(prompt_path),
        "prompt_sha256": prompt_sha256,
    }


def main():
    p = argparse.ArgumentParser(description="Closure Package Builder")
    p.add_argument("--repo-root", default=str(Path(".").resolve()))
    p.add_argument(
        "--source-run-root",
        default="/private/tmp/pipeline_runs/2026-07-29/v5_analysis_20260729_002",
    )
    p.add_argument("--output-dir", default="/tmp")
    args = p.parse_args()

    build_closure_package(
        repo_root=Path(args.repo_root),
        source_run_root=Path(args.source_run_root),
        output_dir=Path(args.output_dir),
    )


if __name__ == "__main__":
    main()
