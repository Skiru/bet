#!/usr/bin/env python3
"""Validate an agent artifact against its originating work order."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order
from bet.pipeline.agent_execution_prompts import load_work_order
from bet.pipeline.artifact_gate import load_artifact


def build_validation_result(work_order: dict, artifact_path: Path, errors: list[str]) -> dict:
    """Build a machine-readable validation result payload."""
    return {
        "schema_version": 1,
        "validator_id": "agent_artifact_validation_cli",
        "work_order_id": work_order.get("work_order_id"),
        "step_id": work_order.get("step_id"),
        "artifact_path": str(artifact_path),
        "verdict": "PASS" if not errors else "FAIL",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an agent artifact against a work order.")
    parser.add_argument("--work-order", required=True, help="Path to work order JSON")
    parser.add_argument("--artifact", required=True, help="Path to agent artifact JSON")
    parser.add_argument("--print-json", action="store_true", help="Print machine-readable JSON result")
    args = parser.parse_args()

    try:
        work_order = load_work_order(Path(args.work_order))
        artifact_path = Path(args.artifact)
        artifact = load_artifact(artifact_path)
        errors = validate_agent_artifact_for_work_order(artifact, work_order)
        result = build_validation_result(work_order, artifact_path, errors)
    except Exception as exc:  # pragma: no cover - covered through CLI assertions
        result = {
            "schema_version": 1,
            "validator_id": "agent_artifact_validation_cli",
            "work_order_id": None,
            "step_id": None,
            "artifact_path": str(Path(args.artifact)),
            "verdict": "FAIL",
            "errors": [str(exc)],
        }

    if args.print_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{result['verdict']}: {len(result['errors'])} error(s)")

    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
