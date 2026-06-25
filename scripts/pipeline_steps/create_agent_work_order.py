#!/usr/bin/env python3
"""CLI script to generate an Agent Work Order for a specific step."""
import argparse
import json
import sys
from pathlib import Path

from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
from bet.pipeline.run_evidence import write_json_atomic


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an agent work order.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-id", required=True, help="Run ID")
    parser.add_argument("--step-id", required=True, choices=["S2.3", "S2.5", "S2.7", "S2.9", "S5"], help="Step ID")
    parser.add_argument("--runtime-mode", required=True, choices=["DRY_RUN", "LIVE_SHADOW", "CERTIFICATION"], help="Runtime Mode")
    parser.add_argument("--base-run-dir", required=True, help="Base run directory")
    parser.add_argument("--manifest", default="config/pipeline_manifest.json", help="Manifest path")
    parser.add_argument("--artifact-dir", help="Optional artifact directory override")
    parser.add_argument("--print-json", action="store_true", help="Print work order JSON to stdout")

    args = parser.parse_args()

    # Load and validate manifest to ensure everything is correct
    manifest_path = Path(args.manifest)
    try:
        load_pipeline_manifest(manifest_path)
    except Exception as e:
        print(f"Error loading manifest: {e}", file=sys.stderr)
        sys.exit(1)

    base_dir = Path(args.base_run_dir)
    
    # Build work order
    try:
        wo = build_agent_work_order(
            betting_day=args.date,
            run_id=args.run_id,
            step_id=args.step_id,
            runtime_mode=args.runtime_mode,
            base_dir=base_dir,
        )
    except Exception as e:
        print(f"Error building work order: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine where to write
    if args.artifact_dir:
        art_dir = Path(args.artifact_dir)
        art_dir.mkdir(parents=True, exist_ok=True)
        target_path = art_dir / f"{args.step_id}_work_order.json"
        write_json_atomic(target_path, wo.to_jsonable())
    else:
        # Resolve standard path and write
        target_path = write_agent_work_order(wo, base_dir)

    # Print if requested
    if args.print_json:
        print(json.dumps(wo.to_jsonable(), indent=2))
    else:
        print(f"Agent work order successfully written to: {target_path}")


if __name__ == "__main__":
    main()
