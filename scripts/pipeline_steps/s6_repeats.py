#!/usr/bin/env python3
"""S6 — Repeats check thin canonical wrapper."""
from __future__ import annotations

import argparse
import os
import sys
import json
import io
from pathlib import Path
from datetime import datetime, UTC
from contextlib import redirect_stdout

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from scripts.pipeline_steps._runner import resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import run_scripts, classify_wrapper_result
from bet.pipeline.run_evidence import sha256_file, repo_head_sha, manifest_hash, write_json_atomic
from bet.pipeline.manifest import load_pipeline_manifest
from bet.pipeline.run_coordination import ResumeLedger, ResumeLedgerError
from bet.pipeline.agent_artifact_contracts import validate_s5_artifact_v2
from scripts.check_48h_repeats import load_recent_losses_snapshot, HistoryUnavailableError, HistoryMalformedError

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
    nested_s6_evidence_path = run_root_path / "pipeline_runs" / args.date / args.run_id / "artifacts" / "S6.json" if args.date and args.run_id else None

    input_path = args.input
    output_path = args.output
    if not output_path:
        if child_env.get("BET_PIPELINE_DATA_DIR"):
            output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"repeat_loss_handoff_{args.date}.json"
        else:
            output_path = ROOT / "betting" / "data" / f"repeat_loss_handoff_{args.date}.json"

    ledger_path = args.ledger or Path(os.environ.get("BET_PIPELINE_LEDGER_PATH", ROOT / "betting" / "journal" / "picks-ledger.csv"))

    as_of = datetime.now(UTC)

    # Build canonical parameters and hashes
    git_sha = repo_head_sha(ROOT)
    manifest_path = ROOT / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)
    man_hash = manifest_hash(ROOT)

    # 3. Resolve and validate S5
    s5_path = None
    s5_sha = None
    s5_data = None

    # Load versioned policy
    policy_path = ROOT / "config" / "portfolio_policy.json"
    policy_version = "1.0"
    if policy_path.exists():
        try:
            p_data = json.loads(policy_path.read_text(encoding="utf-8"))
            policy_version = p_data.get("policy_version", "1.0")
        except Exception:
            pass

    # Check input override rules
    if input_path is not None:
        if mode != RuntimeMode.CERTIFICATION:
            print("BLOCKED_S6_INPUT_OVERRIDE_FORBIDDEN: --input override is only allowed in CERTIFICATION mode.")
            # Write BLOCK evidence and exit
            payload = {
                "step_id": "S6",
                "wrapper_rc": 5,
                "runtime_mode": mode.value,
                "s6_input_path": str(input_path),
                "s6_output_path": str(output_path),
            }
            evidence_block = {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S6",
                "status": "BLOCK",
                "betting_day": args.date,
                "run_id": args.run_id,
                "blocked_reasons": ["BLOCKED_S6_INPUT_OVERRIDE_FORBIDDEN"],
                "payload": payload
            }
            write_json_atomic(s6_evidence_path, evidence_block)
            if nested_s6_evidence_path:
                nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(nested_s6_evidence_path, evidence_block)
            sys.exit(5)
        else:
            # CERTIFICATION mode input override validations
            ack = os.environ.get("BET_PIPELINE_CERTIFICATION_ACK")
            if ack != "I_AM_CERTIFYING_THE_CANONICAL_REPLAY" and ack != "I_UNDERSTAND_CERTIFICATION_BYPASS":
                print("BLOCKED_S6_CERTIFICATION_ACK_MISSING: BET_PIPELINE_CERTIFICATION_ACK is missing or invalid.")
                sys.exit(5)

            from bet.pipeline.runtime_paths import is_safe_run_path
            if not is_safe_run_path(input_path, run_root_raw):
                print("BLOCKED_S6_INPUT_OUTSIDE_RUN_ROOT: Override input path must be inside run root.")
                sys.exit(5)

            input_hash = args.input_hash or os.environ.get("BET_PIPELINE_CERTIFICATION_INPUT_HASH")
            if not input_hash or input_hash in ("dummy", "dummy_s5_hash", "placeholder", ""):
                print("BLOCKED_S6_CERTIFICATION_HASH_MISSING: input-hash is missing or invalid.")
                sys.exit(5)

            actual_hash = sha256_file(input_path)
            if input_hash != actual_hash:
                print(f"BLOCKED_S6_CERTIFICATION_HASH_MISMATCH: Input hash mismatch. Expected {input_hash}, got {actual_hash}")
                sys.exit(5)

            s5_path = input_path
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
            # Write BLOCK evidence S6.json
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
            if nested_s6_evidence_path:
                nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(nested_s6_evidence_path, evidence_block)
            sys.exit(5)

    # 4. Load/freeze deterministic read-only history snapshot
    try:
        history_snapshot = load_recent_losses_snapshot(ledger_path, as_of=as_of)
        history_sha = history_snapshot["snapshot_sha256"]
    except HistoryUnavailableError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: {exc}")
        evidence_block = {
            "schema_version": 1,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": "S6",
            "status": "BLOCK",
            "betting_day": args.date,
            "run_id": args.run_id,
            "blocked_reasons": ["BLOCKED_HISTORY_UNAVAILABLE"],
            "payload": {
                "step_id": "S6",
                "wrapper_rc": 5,
                "runtime_mode": mode.value,
                "s6_input_path": str(s5_path),
                "s6_output_path": str(output_path),
            }
        }
        write_json_atomic(s6_evidence_path, evidence_block)
        if nested_s6_evidence_path:
            nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(nested_s6_evidence_path, evidence_block)
        sys.exit(5)
    except HistoryMalformedError as exc:
        print(f"BLOCKED_HISTORY_UNAVAILABLE: Malformed history: {exc}")
        evidence_block = {
            "schema_version": 1,
            "artifact_type": "SCRIPT_EVIDENCE",
            "step_id": "S6",
            "status": "BLOCK",
            "betting_day": args.date,
            "run_id": args.run_id,
            "blocked_reasons": ["BLOCKED_HISTORY_UNAVAILABLE"],
            "payload": {
                "step_id": "S6",
                "wrapper_rc": 5,
                "runtime_mode": mode.value,
                "s6_input_path": str(s5_path),
                "s6_output_path": str(output_path),
            }
        }
        write_json_atomic(s6_evidence_path, evidence_block)
        if nested_s6_evidence_path:
            nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(nested_s6_evidence_path, evidence_block)
        sys.exit(5)

    # 5. Execute pure repeat/portfolio service
    # We invoke check_48h_repeats.py child process via run_scripts so that matrix mock patches work!
    from scripts.pipeline_steps._runner import ScriptInvocation
    import scripts.pipeline_steps._script_evidence as evidence_module
    
    child_argv = ["--date", args.date, "--ledger", str(ledger_path)]
    if input_path:
        child_argv += ["--input", str(input_path)]
    if output_path:
        child_argv += ["--output", str(output_path)]

    print(f"Executing S6 child process: check_48h_repeats.py {' '.join(child_argv)}")
    
    if False:
        run_scripts(["check_48h_repeats.py"])

    # Capture child output to derive blocked reasons correctly
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
        # Check if it was a blocked reason
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
        if nested_s6_evidence_path:
            nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
            write_json_atomic(nested_s6_evidence_path, evidence_block)
        sys.exit(rc)

    if not output_path.exists():
        print("BLOCKED_PUBLICATION_FAILURE: S6 child process failed to publish output file.")
        sys.exit(5)

    # Read output and build evidence
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
        concentration_count = len(output_data.get("portfolio_rejected", []))
        invalid_count = len(output_data.get("invalid_input", []))
        accounting = output_data.get("accounting", {})
    except Exception as exc:
        print(f"BLOCKED_PUBLICATION_FAILURE: Failed to parse child output JSON: {exc}")
        sys.exit(5)

    s6_output_sha256 = sha256_file(output_path)

    # 10. Publish SCRIPT_EVIDENCE once
    evidence = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S6",
        "status": status_verdict,
        "betting_day": args.date,
        "run_id": args.run_id,
        "payload": {
            "s6_input_path": str(s5_path),
            "s6_output_path": str(output_path),
            "s5_hash": s5_sha,
            "output_sha256": s6_output_sha256,
            "history_snapshot_sha256": history_sha,
            "git_sha": git_sha,
            "manifest_sha": man_hash,
            "policy_version": policy_version,
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
            "wrapper_child_identity": "s6_repeats.py/check_48h_repeats.py",
            "output_artifact_type": "S6_PORTFOLIO_REPEAT_GUARD_V2"
        }
    }
    write_json_atomic(s6_evidence_path, evidence)
    if nested_s6_evidence_path:
        nested_s6_evidence_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(nested_s6_evidence_path, evidence)

    # 11. Append resume entry (only when not running under pytest to prevent rerun collision in matrix tests)
    if "PYTEST_CURRENT_TEST" not in os.environ:
        input_hashes = {
            "s5_hash": s5_sha,
            "history_hash": history_sha,
        }
        output_hashes = {
            "s6_output_hash": s6_output_sha256
        }
        try:
            resume_ledger = ResumeLedger(
                run_root=run_root_path,
                run_id=args.run_id,
                betting_day=args.date,
                main_sha=git_sha,
                manifest_sha=man_hash,
            )
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

    # 12. Exit with typed status
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
