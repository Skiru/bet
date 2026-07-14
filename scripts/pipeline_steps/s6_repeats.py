#!/usr/bin/env python3
"""S6 — Repeats check thin canonical wrapper."""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.pipeline_steps._script_evidence as evidence_module
from bet.pipeline.agent_artifact_contracts import validate_s5_artifact_v2
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError
from bet.pipeline.run_evidence import (
    manifest_hash,
    repo_head_sha,
    sha256_file,
    write_json_atomic,
)
from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from bet.pipeline.runtime_paths import is_safe_run_path
from scripts.check_48h_repeats import (
    HistoryMalformedError,
    HistoryUnavailableError,
    load_recent_losses_snapshot,
    publish_immutable_or_reuse,
)
from scripts.pipeline_steps._runner import ScriptInvocation, resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import classify_wrapper_result

SCRIPTS = ["check_48h_repeats.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"repeat guard input missing|missing repeat guard|repeat guard.*missing|repeat guard.*not found", "BLOCKED_REPEAT_GUARD_INPUT_MISSING"),
    (r"repeat guard input empty|empty candidate list|zero candidates|no candidates|empty candidate input", "BLOCKED_REPEAT_GUARD_INPUT_EMPTY"),
    (r"repeat signal|signal conflict|repeat guard conflict|repeat guard triggered|repeat conflict|repeat-loss exclusions found", "BLOCKED_REPEAT_SIGNAL_CONFLICT"),
)


def main() -> None:
    # 1. Parse runtime arguments
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--input", type=Path, default=None, help="Input override")
    p.add_argument("--output", type=Path, default=None, help="Output override")
    p.add_argument("--ledger", type=Path, default=None, help="Path to picks-ledger.csv")
    p.add_argument("--input-hash", dest="input_hash", default=None, help="Explicit certification input hash")
    args = p.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)

    # 2. Resolve canonical run layout
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    for key in ("BET_PIPELINE_RUN_ROOT", "BET_PIPELINE_DATA_DIR", "BET_PIPELINE_COUPON_DIR", "BET_PIPELINE_ARTIFACT_DIR", "BET_PIPELINE_BETTING_DAY", "BET_PIPELINE_RUN_ID", "BET_PIPELINE_RUNTIME_MODE"):
        if child_env.get(key):
            os.environ[key] = child_env[key]

    run_root_raw = child_env.get("BET_PIPELINE_RUN_ROOT")
    if not run_root_raw:
        print("BLOCKED_BINDING_FAILURE: BET_PIPELINE_RUN_ROOT is missing.")
        sys.exit(5)
    run_root_path = Path(run_root_raw)

    artifact_dir = Path(child_env["BET_PIPELINE_ARTIFACT_DIR"])
    s6_evidence_path = artifact_dir / "S6.json"

    # Only single canonical evidence is permitted. Remove nested evidence.
    nested_s6_evidence_path = None

    # Resolve output path canonically
    output_path = args.output
    if not output_path:
        if child_env.get("BET_PIPELINE_DATA_DIR"):
            output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"repeat_loss_handoff_{args.date}.json"
        else:
            output_path = ROOT / "betting" / "data" / f"repeat_loss_handoff_{args.date}.json"

    ledger_path = args.ledger or Path(os.environ.get("BET_PIPELINE_LEDGER_PATH", ROOT / "betting" / "journal" / "picks-ledger.csv"))

    # Injected timezone-aware as_of
    as_of = datetime.now(UTC)

    # Resolve manifest and hashes
    git_sha = repo_head_sha(ROOT)
    manifest_path = ROOT / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)
    man_hash = manifest_hash(ROOT)

    # 3. Resolve and Validate S5 input
    s5_path = None
    s5_sha = None
    s5_data = None

    if args.input is not None:
        if mode != RuntimeMode.CERTIFICATION:
            print("BLOCKED_S6_INPUT_OVERRIDE_FORBIDDEN: --input override is only allowed in CERTIFICATION mode.")
            # Write BLOCK evidence and exit
            evidence_block = {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S6",
                "status": "BLOCK",
                "betting_day": args.date,
                "run_id": args.run_id,
                "blocked_reasons": ["BLOCKED_S6_INPUT_OVERRIDE_FORBIDDEN"],
                "payload": {
                    "step_id": "S6",
                    "wrapper_rc": 5,
                    "runtime_mode": mode.value,
                    "s6_input_path": str(args.input),
                    "s6_output_path": str(output_path),
                }
            }
            write_json_atomic(s6_evidence_path, evidence_block)
            sys.exit(5)
        else:
            # CERTIFICATION mode input override validations
            ack = os.environ.get("BET_PIPELINE_CERTIFICATION_ACK")
            if ack != "I_AM_CERTIFYING_THE_CANONICAL_REPLAY" and ack != "I_UNDERSTAND_CERTIFICATION_BYPASS":
                print("BLOCKED_S6_CERTIFICATION_ACK_MISSING: BET_PIPELINE_CERTIFICATION_ACK is missing or invalid.")
                sys.exit(5)

            if not is_safe_run_path(args.input, run_root_raw):
                print("BLOCKED_S6_INPUT_OUTSIDE_RUN_ROOT: Override input path must be inside run root.")
                sys.exit(5)

            input_hash = args.input_hash or os.environ.get("BET_PIPELINE_CERTIFICATION_INPUT_HASH")
            if not input_hash or input_hash in ("dummy", "dummy_s5_hash", "placeholder", ""):
                print("BLOCKED_S6_CERTIFICATION_HASH_MISSING: input-hash is missing or invalid.")
                sys.exit(5)

            actual_hash = sha256_file(args.input)
            if input_hash != actual_hash:
                print(f"BLOCKED_S6_CERTIFICATION_HASH_MISMATCH: Input hash mismatch. Expected {input_hash}, got {actual_hash}")
                sys.exit(5)

            s5_path = args.input
            s5_sha = actual_hash
            try:
                s5_data = json.loads(s5_path.read_text(encoding="utf-8"))
                validate_s5_artifact_v2(s5_data, run_root_path, args.date, args.run_id, manifest)
            except Exception as exc:
                print(f"BLOCKED_S6_INPUT_INVALID: S5 validation failed: {exc}")
                sys.exit(5)
    else:
        # Normal canonical resolution
        from bet.pipeline.integration_artifacts import resolve_manifest_step_output
        try:
            s5_path, s5_data = resolve_manifest_step_output(
                manifest=manifest,
                run_root=run_root_path,
                step_id="S5",
                betting_day=args.date,
                run_id=args.run_id,
                expected_artifact_type="S5_CONTEXT_RISK_CANDIDATE_SET_V2",
            )
            s5_sha = sha256_file(s5_path)
        except Exception as exc:
            print(f"BLOCKED_BINDING_FAILURE: Failed to resolve prerequisite S5 output: {exc}")
            evidence_block = {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S6",
                "status": "BLOCK",
                "betting_day": args.date,
                "run_id": args.run_id,
                "blocked_reasons": ["BLOCKED_REPEAT_GUARD_INPUT_MISSING"],
                "payload": {
                    "step_id": "S6",
                    "wrapper_rc": 5,
                    "runtime_mode": mode.value,
                    "s6_input_path": None,
                    "s6_output_path": str(output_path),
                }
            }
            write_json_atomic(s6_evidence_path, evidence_block)
            sys.exit(5)

    # 4. Freeze Policy & History Snapshots into Run-Root Data folder
    policy_path = ROOT / "config" / "portfolio_policy.json"
    if not policy_path.exists():
        print("BLOCKED_POLICY_INVALID: portfolio_policy.json is missing")
        sys.exit(5)

    policy_sha = sha256_file(policy_path)
    policy_data = json.loads(policy_path.read_text(encoding="utf-8"))

    # Write validated policy copy to run root
    run_policy_path = run_root_path / "data" / "s6_policy.json"
    try:
        publish_immutable_or_reuse(run_policy_path, policy_data)
    except Exception as exc:
        print(f"BLOCKED_POLICY_INVALID: Failed to freeze policy: {exc}")
        sys.exit(5)

    # Freeze history read once using the injected as_of
    try:
        history_snapshot = load_recent_losses_snapshot(ledger_path, as_of=as_of)
    except HistoryUnavailableError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
        sys.exit(5)
    except HistoryMalformedError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
        sys.exit(5)

    # Write history snapshot copy to run root
    run_history_path = run_root_path / "data" / "s6_history_snapshot.json"
    try:
        publish_immutable_or_reuse(run_history_path, history_snapshot)
    except Exception as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: Failed to freeze history: {exc}")
        sys.exit(5)

    # Calculate exact file SHA of the frozen history snapshot JSON
    history_sha = sha256_file(run_history_path)

    # 5. Resume and Rerun Checks (Must always be executed, no PYTEST bypass)
    resume_ledger = None
    try:
        resume_ledger = ResumeLedger(
            run_root=run_root_path,
            run_id=args.run_id,
            betting_day=args.date,
            main_sha=git_sha,
            manifest_sha=man_hash,
        )
    except ResumeLedgerError as exc:
        print(f"BLOCKED_BINDING_FAILURE: Resume ledger initialization failed: {exc}")
        sys.exit(5)

    # Load and check existing entries
    try:
        ledger_data = resume_ledger._load()
    except Exception as exc:
        print(f"BLOCKED_BINDING_FAILURE: Resume ledger binding conflict: {exc}")
        sys.exit(5)

    existing_s6 = [e for e in ledger_data.get("entries", []) if e.get("step_id") == "S6"]
    if existing_s6:
        last_entry = existing_s6[-1]
        last_inputs = last_entry.get("input_hashes", {})
        last_outputs = last_entry.get("output_hashes", {})

        # Verify exact input hashes match
        if last_inputs.get("s5_hash") != s5_sha:
            print("BLOCK: S5 SHA change detected vs resume ledger")
            sys.exit(5)
        if last_inputs.get("history_hash") != history_sha:
            print("BLOCK: History SHA change detected vs resume ledger")
            sys.exit(5)
        if last_inputs.get("policy_hash") != policy_sha:
            print("BLOCK: Policy SHA change detected vs resume ledger")
            sys.exit(5)

        # Verify exact output hashes match
        if output_path.exists():
            current_output_sha = sha256_file(output_path)
            if last_outputs.get("s6_output_hash") != current_output_sha:
                print("BLOCK: Existing output has different bytes")
                sys.exit(5)
        else:
            # Output was deleted before complete, so let's continue and recreate it
            pass

        # Verify evidence matches
        if s6_evidence_path.exists():
            try:
                ev_data = json.loads(s6_evidence_path.read_text(encoding="utf-8"))
                if ev_data.get("payload", {}).get("output_sha256") != last_outputs.get("s6_output_hash"):
                    print("BLOCK: Existing S6 evidence has different bytes")
                    sys.exit(5)
                # Idempotent return code if identical run completely matches
                print("READY_FOR_S7: S6 completed successfully (Idempotent Resume).")
                sys.exit(0)
            except SystemExit:
                raise
            except Exception:
                print("BLOCK: Existing S6 evidence is malformed")
                sys.exit(5)

    # 6. Execute child process using the frozen configurations
    child_argv = [
        "--date", args.date,
        "--history-snapshot", str(run_history_path),
        "--history-snapshot-sha256", history_sha,
        "--as-of-utc", as_of.isoformat(),
        "--policy", str(run_policy_path),
        "--policy-sha256", policy_sha,
    ]
    if s5_path:
        child_argv += ["--input", str(s5_path)]
    if output_path:
        child_argv += ["--output", str(output_path)]

    print(f"Executing S6 child process: check_48h_repeats.py {' '.join(child_argv)}")

    f_out = io.StringIO()
    with redirect_stdout(f_out):
        rc = evidence_module.run_scripts(
            [ScriptInvocation(script="check_48h_repeats.py", argv=child_argv)],
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            run_id=args.run_id,
        )
    child_output = f_out.getvalue()
    print(child_output)

    if rc != 0:
        status_verdict, blocked_reasons = classify_wrapper_result(
            rc=rc,
            output=child_output,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_REPEAT_GUARD_INPUT_MISSING",
        )
        evidence_block = {
            "schema_version": 1,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": "S6",
            "status": "BLOCK",
            "betting_day": args.date,
            "run_id": args.run_id,
            "blocked_reasons": list(blocked_reasons),
            "payload": {
                "step_id": "S6",
                "wrapper_rc": rc,
                "runtime_mode": mode.value,
                "s6_input_path": str(s5_path),
                "s6_output_path": str(output_path),
                "wrapper_scripts": SCRIPTS,
            }
        }
        write_json_atomic(s6_evidence_path, evidence_block)
        sys.exit(rc)

    if not output_path.exists():
        print("BLOCKED_PUBLICATION_FAILURE: S6 child process failed to publish output file.")
        sys.exit(5)

    # 7. Read back output & parse
    try:
        output_data = json.loads(output_path.read_text(encoding="utf-8"))
        status_verdict = output_data.get("status") or "PASS"
        concrete_status = output_data.get("concrete_status") or "READY_FOR_S7"

        input_candidate_count = output_data.get("input_candidate_count", 0)
        accepted_count = len(output_data.get("accepted", []))
        repeat_count = len(output_data.get("repeat_rejected", []))
        duplicate_count = len(output_data.get("duplicate_rejected", []))
        conflict_count = len(output_data.get("conflict_rejected", []))
        correlation_count = len(output_data.get("correlation_rejected", []))
        concentration_count = len(output_data.get("concentration_rejected", []))
        invalid_count = len(output_data.get("invalid_input", []))
        accounting = output_data.get("accounting", {})
    except Exception as exc:
        print(f"BLOCKED_PUBLICATION_FAILURE: Failed to parse child output JSON: {exc}")
        sys.exit(5)

    s6_output_sha256 = sha256_file(output_path)

    # 8. Build complete, immutable evidence once
    evidence = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "status": status_verdict,
        "betting_day": args.date,
        "run_id": args.run_id,
        "payload": {
            "s5_path": str(s5_path),
            "s5_sha": s5_sha,
            "policy_path": str(run_policy_path),
            "policy_version": policy_data.get("policy_version", "1.0"),
            "policy_sha": policy_sha,
            "history_snapshot_path": str(run_history_path),
            "history_snapshot_sha": history_sha,
            "history_as_of": as_of.isoformat() + "Z",
            "output_path": str(output_path),
            "output_sha256": s6_output_sha256,
            "git_sha": git_sha,
            "manifest_sha": man_hash,
            "as_of_timestamp": as_of.isoformat() + "Z",
            "input_candidate_count": input_candidate_count,
            "accepted_count": accepted_count,
            "repeat_rejected_count": repeat_count,
            "duplicate_rejected_count": duplicate_count,
            "conflict_rejected_count": conflict_count,
            "correlation_rejected_count": correlation_count,
            "concentration_rejected_count": concentration_count,
            "invalid_input_count": invalid_count,
            "accounting_summary": accounting,
            "child_argv_fingerprint": child_argv,
            "child_executable_identity": sys.executable,
            "concrete_status": concrete_status,
            "wrapper_child_identity": "s6_repeats.py/check_48h_repeats.py",
            "output_artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2"
        }
    }

    # Write single canonical evidence immutably and verify bytes
    try:
        publish_immutable_or_reuse(s6_evidence_path, evidence)
    except Exception as exc:
        print(f"BLOCK: Conflicting immutable S6 evidence exists: {exc}")
        sys.exit(5)

    # 9. Append entry to ResumeLedger
    input_hashes = {
        "s5_hash": s5_sha,
        "history_hash": history_sha,
        "policy_hash": policy_sha,
    }
    output_hashes = {
        "s6_output_hash": s6_output_sha256
    }
    try:
        resume_ledger.append(
            step_id="S6",
            status=status_verdict,
            command_request={"argv": child_argv},
            input_hashes=input_hashes,
            output_hashes=output_hashes,
        )
    except ResumeLedgerError as exc:
        print(f"BLOCKED_BINDING_FAILURE: Resume ledger append failure: {exc}")
        sys.exit(5)

    # 10. Exit with typed status
    if concrete_status == "NO_ACTION_TERMINAL":
        print("NO_ACTION_TERMINAL: All candidates legitimately filtered.")
        sys.exit(0)
    elif status_verdict == "PASS":
        print("READY_FOR_S7: S6 completed successfully.")
        sys.exit(0)
    else:
        print(f"BLOCKED: {concrete_status}")
        sys.exit(1)


if __name__ == "__main__":
    main()
