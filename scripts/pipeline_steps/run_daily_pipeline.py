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
        help="Permit live external integration calls when in LIVE_SHADOW mode",
    )
    p.add_argument(
        "--allow-write",
        action="store_true",
        help="Permit writing outputs in non-production environments",
    )
    p.add_argument("--artifact-dir", help="Optional direct path to the artifact directory")
    p.add_argument("--verbose", action="store_true", help="Print verbose execution details")

    args = p.parse_args()

    # Instantiate orchestrator
    orchestrator = Orchestrator(
        betting_day=args.date,
        run_id=args.run_id,
        runtime_mode=args.runtime_mode,
        manifest_path=Path(args.manifest) if args.manifest else None,
        base_run_dir=Path(args.base_run_dir) if args.base_run_dir else None,
        allow_live_network=args.allow_live_network,
        allow_write=args.allow_write,
        artifact_dir=Path(args.artifact_dir) if args.artifact_dir else None,
        verbose=args.verbose,
    )

    # Run the pipeline sequence
    try:
        summary = orchestrator.run(
            start_step=args.start_step,
            stop_after_step=args.stop_after_step,
        )
    except Exception as e:
        print(f"Orchestrator failed with exception: {e}", file=sys.stderr)
        sys.exit(12)

    status = summary.get("status")
    if status == "PASS":
        sys.exit(0)
    elif status == "BLOCK":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
