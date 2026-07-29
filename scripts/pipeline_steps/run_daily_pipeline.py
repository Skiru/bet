#!/usr/bin/env python3
"""CLI entrypoint for running the daily betting pipeline orchestrator."""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

# Ensure repo root and src/ are importable for package imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
src_path = str(ROOT / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from bet.pipeline.orchestrator import Orchestrator
import bet.pipeline.contracts.base
import bet.pipeline.contracts.canonical_json
import bet.pipeline.contracts.common
import bet.pipeline.contracts.migration
import bet.pipeline.contracts.registry
import bet.pipeline.contracts.steps
import bet.pipeline.contracts.steps.s0_to_s2
import bet.pipeline.contracts.steps.s3_to_s10
import bet.pipeline.sharding.lifecycle
import bet.pipeline.sharding.models
import bet.pipeline.sports.models
import bet.pipeline.sports.protocols
import bet.pipeline.sports.registry
import bet.models.contracts
import bet.models.dixon_coles
import bet.models.registry
import bet.builder.engine
import bet.builder.models


def build_pipeline_parser() -> argparse.ArgumentParser:
    """Build and return ArgumentParser for run_daily_pipeline."""
    p = argparse.ArgumentParser(description="Run daily manifest-driven pipeline.")
    p.add_argument("--date", "--betting-day", required=True, help="YYYY-MM-DD")
    p.add_argument("--run-id", required=True, help="Run ID")
    p.add_argument(
        "--runtime-mode",
        choices=["CERTIFICATION", "DRY_RUN", "LIVE_SHADOW"],
        default="DRY_RUN",
        help="Pipeline runtime execution mode",
    )
    p.add_argument("--start-step", help="Optional step to start execution from")
    p.add_argument("--stop-after-step", help="Optional step to stop execution after")
    p.add_argument(
        "--manifest",
        default="config/pipeline_manifest.json",
        help="Path to pipeline manifest JSON configuration",
    )
    p.add_argument(
        "--base-run-dir",
        default="reports/pipeline_runs",
        help="Base directory for saving pipeline run outputs",
    )
    p.add_argument(
        "--allow-live-network",
        action="store_true",
        default=False,
        help="Explicit operator acknowledgment required for live network provider calls",
    )
    p.add_argument(
        "--allow-write",
        action="store_true",
        default=False,
        help="Explicit operator acknowledgment required for database/storage writes",
    )
    p.add_argument(
        "--source-run-root",
        help="Optional source run root directory for lineage-preserving restart from S2",
    )
    p.add_argument(
        "--restart-seed",
        type=Path,
        help="Path to exact immutable restart seed tar archive",
    )
    p.add_argument(
        "--restart-seed-sha256",
        help="Expected SHA256 digest of restart seed tar archive",
    )
    p.add_argument(
        "--restart-seed-manifest",
        type=Path,
        help="Path to restart seed manifest JSON file",
    )
    p.add_argument(
        "--restart-seed-manifest-sha256",
        help="Expected SHA256 digest of restart seed manifest JSON file",
    )
    p.add_argument(
        "--reuse-through-step",
        default="S1e",
        help="Step through which to reuse artifacts from source run (default S1e)",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose orchestrator logging",
    )
    return p


def parse_pipeline_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate CLI arguments for daily pipeline."""
    p = build_pipeline_parser()
    args = p.parse_args(argv)

    restart_seed = getattr(args, "restart_seed", None)
    restart_man = getattr(args, "restart_seed_manifest", None)
    if restart_seed:
        if args.reuse_through_step != "S1e":
            raise ValueError(f"RESTART_SEED_REQUIRES_REUSE_THROUGH_S1E: Only S1e reuse supported, got {args.reuse_through_step}")
        if args.start_step and args.start_step != "S2":
            raise ValueError(f"RESTART_SEED_REQUIRES_START_STEP_S2: Restart seed mode requires start step S2, got {args.start_step}")
        if not restart_man:
            raise ValueError("EXTERNAL_MANIFEST_MISSING: --restart-seed-manifest is required when using --restart-seed")

    return args


def main() -> None:
    args = parse_pipeline_args()

    target_run_root = Path(args.base_run_dir) / args.date / args.run_id

    seed_tar_to_import = args.restart_seed
    seed_man_to_import = args.restart_seed_manifest
    seed_tar_sha = args.restart_seed_sha256
    seed_man_sha = args.restart_seed_manifest_sha256

    if args.source_run_root and not seed_tar_to_import:
        if args.start_step == "S2":
            from scripts.pipeline_steps.export_s2_restart_seed import export_s2_restart_seed
            src_root = Path(args.source_run_root).resolve(strict=True)
            with tempfile.TemporaryDirectory(prefix="s2_export_") as tmp_dir:
                seed_tar_to_import, seed_man_to_import = export_s2_restart_seed(source_run_root=src_root, output_dir=Path(tmp_dir))

    if seed_tar_to_import and args.start_step == "S2":
        from scripts.pipeline_steps.import_s2_restart_seed import import_s2_restart_seed
        from bet.pipeline.receipts import get_git_commit_head, get_git_tree_sha, compute_source_manifest_sha256

        repo_root = ROOT
        cur_head = get_git_commit_head(repo_root)
        cur_tree = get_git_tree_sha(repo_root)
        cur_manifest = compute_source_manifest_sha256(repo_root)

        import_s2_restart_seed(
            seed_tar_path=seed_tar_to_import,
            target_run_root=target_run_root,
            target_run_id=args.run_id,
            target_head=cur_head,
            target_tree=cur_tree,
            target_manifest=cur_manifest,
            seed_manifest_path=seed_man_to_import,
            expected_seed_tar_sha256=seed_tar_sha,
            expected_seed_manifest_sha256=seed_man_sha,
            runtime_mode=args.runtime_mode,
        )

    orchestrator = Orchestrator(
        betting_day=args.date,
        run_id=args.run_id,
        runtime_mode=args.runtime_mode,
        manifest_path=Path(args.manifest),
        base_run_dir=Path(args.base_run_dir),
        allow_live_network=args.allow_live_network,
        allow_write=args.allow_write,
        verbose=args.verbose,
    )
    summary = orchestrator.run(
        start_step=args.start_step,
        stop_after_step=args.stop_after_step,
    )
    status_val = str(summary.get("status") or summary.get("overall_status") or "")
    valid_success_statuses = {
        "PASS",
        "READY",
        "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW",
        "READY_FOR_MANUAL_MAPPING",
        "NO_ACTION_TERMINAL",
    }
    sys.exit(0 if status_val in valid_success_statuses else 1)


if __name__ == "__main__":
    main()
