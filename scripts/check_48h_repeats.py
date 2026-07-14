#!/usr/bin/env python3
"""48-hour repeat pick detector — finds same team+market losses in recent history.

Reads s6_history_snapshot.json and identifies picks in the last 48 hours with the same
team+market combination that resulted in a loss. These are flagged for the S7 gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.pipeline.portfolio_repeat_guard import (
    PortfolioRepeatGuardInput,
    evaluate_portfolio_repeat_guard,
    validate_history_snapshot_schema,
    validate_portfolio_policy_schema,
)
from bet.pipeline.run_evidence import (
    manifest_hash,
    repo_head_sha,
    sha256_file,
)
from bet.pipeline.runtime_paths import is_safe_run_path


class HistoryUnavailableError(Exception):
    pass


class HistoryMalformedError(Exception):
    pass


def publish_immutable_or_reuse(target: Path, canonical_payload: dict[str, Any]) -> str:
    """Publishes a payload atomically and immutably, or reuses it if identical."""
    proposed_str = json.dumps(canonical_payload, sort_keys=True)
    proposed_hash = hashlib.sha256(proposed_str.encode("utf-8")).hexdigest()

    if target.exists():
        try:
            existing_data = json.loads(target.read_text(encoding="utf-8"))
            existing_str = json.dumps(existing_data, sort_keys=True)
            existing_hash = hashlib.sha256(existing_str.encode("utf-8")).hexdigest()
        except Exception:
            existing_hash = ""

        if existing_hash == proposed_hash:
            return "idempotent_reuse"
        else:
            raise ValueError(f"IMMUTABLE_ARTIFACT_CONFLICT: Conflicting immutable file exists at '{target}'")

    # Use atomic write from run_evidence
    from bet.pipeline.run_evidence import write_json_atomic
    write_json_atomic(target, canonical_payload)
    return "atomic_create"


def main():
    parser = argparse.ArgumentParser(description="Strict S6 Repeat Detector Worker.")
    parser.add_argument("--date", help="Betting day YYYY-MM-DD")
    parser.add_argument("--run-id")
    parser.add_argument("--run-as-of-utc")
    parser.add_argument("--validated-s5", type=Path)
    parser.add_argument("--validated-s5-sha256")
    parser.add_argument("--history-snapshot", type=Path)
    parser.add_argument("--history-snapshot-sha256")
    parser.add_argument("--policy-snapshot", type=Path)
    parser.add_argument("--policy-snapshot-sha256")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker-contract-version")

    # If any required arg is missing or invalid, fail closed as of REQ-V6-WORKER-001
    try:
        args = parser.parse_args()
    except SystemExit:
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING")
        sys.exit(5)

    run_root_raw = os.environ.get("BET_PIPELINE_RUN_ROOT")
    if not run_root_raw:
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Missing run root environment")
        sys.exit(5)

    # Validate that run ID is not ad-hoc
    if not args.run_id or args.run_id in ("ad-hoc", "dummy", "placeholder", ""):
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Invalid or ad-hoc run ID")
        sys.exit(5)

    # Check that all strict arguments are populated and valid
    for name, val in [
        ("date", args.date),
        ("run_as_of_utc", args.run_as_of_utc),
        ("validated_s5", args.validated_s5),
        ("validated_s5_sha256", args.validated_s5_sha256),
        ("history_snapshot", args.history_snapshot),
        ("history_snapshot_sha256", args.history_snapshot_sha256),
        ("policy_snapshot", args.policy_snapshot),
        ("policy_snapshot_sha256", args.policy_snapshot_sha256),
        ("output", args.output),
        ("worker_contract_version", args.worker_contract_version),
    ]:
        if not val or val in ("dummy", "dummy_s5_hash", "placeholder", ""):
            print(f"BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: {name} is missing or has dummy value")
            sys.exit(5)

    if args.worker_contract_version != "1.0":
        print("BLOCKED_INTERNAL_WORKER_CONTRACT_MISSING: Invalid worker contract version")
        sys.exit(5)

    # Require every path to be inside the exact current run root
    for path_arg in (args.validated_s5, args.history_snapshot, args.policy_snapshot, args.output):
        if not is_safe_run_path(path_arg, run_root_raw):
            print(f"BLOCK: path is outside run root: {path_arg}")
            sys.exit(5)

    # Validate all supplied hashes
    for path, expected_hash, name in [
        (args.validated_s5, args.validated_s5_sha256, "S5"),
        (args.history_snapshot, args.history_snapshot_sha256, "History snapshot"),
        (args.policy_snapshot, args.policy_snapshot_sha256, "Policy snapshot"),
    ]:
        if not path.exists():
            print(f"BLOCK: {name} path does not exist")
            sys.exit(5)
        actual = sha256_file(path)
        if actual != expected_hash:
            print(f"BLOCK: {name} hash mismatch. Expected {expected_hash}, got {actual}")
            sys.exit(5)

    # Load S5 candidates
    try:
        s5_data = json.loads(args.validated_s5.read_text(encoding="utf-8"))
        candidates = s5_data.get("payload", {}).get("candidates") or s5_data.get("candidates") or []
        if not candidates:
            print("repeat guard input empty: candidate list is empty")
            sys.exit(5)
    except Exception as exc:
        print(f"BLOCKED_INVALID_INPUT: Failed to parse S5: {exc}")
        sys.exit(5)

    # Load frozen snapshots
    try:
        recent_losses_snapshot = json.loads(args.history_snapshot.read_text(encoding="utf-8"))
        history_obj = validate_history_snapshot_schema(recent_losses_snapshot)
    except Exception as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: Failed to validate history snapshot: {exc}")
        sys.exit(5)

    try:
        p_data = json.loads(args.policy_snapshot.read_text(encoding="utf-8"))
        policy_obj = validate_portfolio_policy_schema(p_data, args.policy_snapshot_sha256)
    except Exception as exc:
        print(f"BLOCKED_POLICY_INVALID: Failed to validate policy: {exc}")
        sys.exit(5)

    # Calculate run clock
    try:
        as_of = datetime.fromisoformat(args.run_as_of_utc.replace("Z", "+00:00"))
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=UTC)
    except Exception:
        print("BLOCK: Invalid --run-as-of-utc format")
        sys.exit(5)

    guard_input = PortfolioRepeatGuardInput(
        candidates=candidates,
        history_snapshot=history_obj,
        policy=policy_obj,
        betting_day=args.date,
        run_id=args.run_id,
        source_s5_hash=args.validated_s5_sha256,
    )

    try:
        guard_result = evaluate_portfolio_repeat_guard(guard_input)
    except Exception as exc:
        print(f"BLOCKED_INVALID_INPUT: {exc}")
        sys.exit(5)

    # Determine status
    if guard_result.invalid_input:
        status_verdict = "BLOCK"
        concrete_status = "BLOCKED_INVALID_INPUT"
    elif len(guard_result.accepted) > 0:
        status_verdict = "PASS"
        concrete_status = "READY_FOR_S7"
    else:
        status_verdict = "PASS"
        concrete_status = "NO_ACTION_TERMINAL"

    # Build S6 output dictionary with strict worker fields
    s6_output_data = {
        "schema_version": 1,
        "artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2",
        "status": status_verdict,
        "concrete_status": concrete_status,
        "betting_day": args.date,
        "run_id": args.run_id,
        "created_at_utc": as_of.isoformat().replace("+00:00", "Z"),
        "source_step": "S5",
        "source_s5_path": str(args.validated_s5),
        "source_s5_hash": args.validated_s5_sha256,
        "source_git_sha": repo_head_sha(ROOT_DIR),
        "manifest_sha": manifest_hash(ROOT_DIR),
        "policy_version": policy_obj.policy_version,
        "history_snapshot_metadata": guard_result.history_snapshot_metadata,
        "input_candidate_count": len(candidates),
        "accepted": guard_result.accepted,
        "repeat_rejected": guard_result.repeat_rejected,
        "duplicate_rejected": guard_result.duplicate_rejected,
        "conflict_rejected": guard_result.conflict_rejected,
        "correlation_rejected": guard_result.correlation_rejected,
        "portfolio_rejected": guard_result.portfolio_rejected,
        "concentration_rejected": guard_result.concentration_rejected,
        "invalid_input": guard_result.invalid_input,
        "accounting": guard_result.accounting,

        # New contract-mandated fields
        "worker_contract_version": args.worker_contract_version,
        "worker_script_sha256": sha256_file(Path(__file__)),
        "validated_inputs": {
            "s5_hash": args.validated_s5_sha256,
            "history_hash": args.history_snapshot_sha256,
            "policy_hash": args.policy_snapshot_sha256,
        },
        "run_as_of_utc": args.run_as_of_utc,
        "result_sha256_precursor": hashlib.sha256(json.dumps(guard_result.accepted, sort_keys=True).encode("utf-8")).hexdigest(),
    }

    # Immutable conflict detection and atomic publication
    try:
        publish_immutable_or_reuse(args.output, s6_output_data)
    except Exception as exc:
        print(f"BLOCK: Conflicting immutable output exists: {exc}")
        sys.exit(5)

    if guard_result.repeat_rejected:
        print("repeat signal conflict: same team+market lost within 48h — HARD REJECT")

    sys.exit(0 if concrete_status == "READY_FOR_S7" else 1)


if __name__ == "__main__":
    main()
