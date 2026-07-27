#!/usr/bin/env python3
"""CLI entrypoint for running the daily betting pipeline orchestrator."""
from __future__ import annotations

import argparse
import sys
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


def main() -> None:
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
        "--verbose",
        "-v",
        action="store_true",
        default=False,
        help="Enable verbose orchestrator logging",
    )
    args = p.parse_args()

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
