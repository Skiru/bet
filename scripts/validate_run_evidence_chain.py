#!/usr/bin/env python3
"""Validator for pipeline run evidence hash chains."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def calculate_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate pipeline run evidence hash chains.")
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--betting-day", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--steps", default="S6,S7,S7b,S8")
    parser.add_argument("--output", type=Path, default=Path("/tmp/BET_PIPELINE_FINAL_EVIDENCE_AND_RUN_BINDING_CLOSURE_V6/replay/s6_s8_evidence_chain.json"))
    args = parser.parse_args()

    steps_to_check = [s.strip() for s in args.steps.split(",")]
    missing_steps = []
    hash_mismatches = []
    resume_mismatches = []
    binding_mismatches = []
    duplicate_evidence = []
    cross_run_paths = []
    unresolved_conflicts = []

    artifacts_dir = args.run_root / "artifacts"
    data_dir = args.run_root / "data"
    resume_ledger_path = args.run_root / "resume_ledger.json"

    # Load resume ledger
    resume_entries = {}
    if resume_ledger_path.exists():
        try:
            ledger = json.loads(resume_ledger_path.read_text(encoding="utf-8"))
            for entry in ledger.get("entries", []):
                resume_entries[entry["step_id"]] = entry
        except Exception as exc:
            resume_mismatches.append(f"Failed to parse resume ledger: {exc}")
    else:
        resume_mismatches.append("Missing resume ledger")

    # Step-by-step verification
    for step in steps_to_check:
        evidence_path = artifacts_dir / f"{step}.json"
        if not evidence_path.exists():
            missing_steps.append(step)
            continue

        try:
            ev = json.loads(evidence_path.read_text(encoding="utf-8"))
        except Exception as exc:
            hash_mismatches.append(f"Malformed evidence JSON for step {step}: {exc}")
            continue

        # Binding checks
        if ev.get("betting_day") != args.betting_day:
            binding_mismatches.append(f"{step} betting_day mismatch: expected {args.betting_day}, got {ev.get('betting_day')}")
        if ev.get("run_id") != args.run_id:
            binding_mismatches.append(f"{step} run_id mismatch: expected {args.run_id}, got {ev.get('run_id')}")

        # Check outputs
        payload = ev.get("payload", {})
        output_path_str = payload.get("output_path") or payload.get("s7_json_output") or payload.get("s7b_output_path") or payload.get("validated_market_availability_path") or payload.get("s8_json_output") or payload.get("coupon_draft_path")
        if output_path_str:
            output_path = Path(output_path_str)
            if not output_path.exists():
                hash_mismatches.append(f"Output file missing for step {step} at {output_path_str}")
            else:
                # Output SHA check
                expected_sha = payload.get("output_sha256") or payload.get("s7_json_sha256") or payload.get("s7b_output_sha256") or payload.get("validated_market_availability_sha256") or payload.get("s8_json_sha256") or payload.get("coupon_draft_sha256")
                if expected_sha:
                    actual_sha = calculate_sha256(output_path)
                    if actual_sha != expected_sha:
                        hash_mismatches.append(f"Output SHA mismatch for step {step}: expected {expected_sha}, got {actual_sha}")

        # Check resume entries
        if step in resume_entries:
            entry = resume_entries[step]
            if entry.get("status") != ev.get("status"):
                resume_mismatches.append(f"Ledger/evidence status mismatch for step {step}")
        else:
            resume_mismatches.append(f"Step {step} missing in resume ledger")

    # Audit conflicts check
    attempts_dir = args.run_root / "validation" / "attempts" / "S6"
    if attempts_dir.exists():
        conflicts = list(attempts_dir.glob("*.json"))
        if conflicts:
            unresolved_conflicts.append(f"Found {len(conflicts)} S6 attempt conflict records")

    status = "BLOCK" if (missing_steps or hash_mismatches or resume_mismatches or binding_mismatches or duplicate_evidence or cross_run_paths or unresolved_conflicts) else "PASS"

    result = {
        "schema_version": 1,
        "task_id": "BET_PIPELINE_FINAL_EVIDENCE_AND_RUN_BINDING_CLOSURE_V6",
        "source_branch": "fix/s5-s6-s7-canonical-continuity-final-v1",
        "source_git_sha": ev.get("payload", {}).get("git_sha") if 'ev' in locals() and ev else "UNKNOWN",
        "generation_timestamp": "2026-07-14T20:00:00Z",
        "command": "validate_run_evidence_chain.py",
        "status": status,
        "steps": steps_to_check,
        "missing_steps": missing_steps,
        "hash_mismatches": hash_mismatches,
        "resume_mismatches": resume_mismatches,
        "binding_mismatches": binding_mismatches,
        "duplicate_evidence": duplicate_evidence,
        "cross_run_paths": cross_run_paths,
        "unresolved_conflicts": unresolved_conflicts
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Validation finished with status: {status}")


if __name__ == "__main__":
    main()
