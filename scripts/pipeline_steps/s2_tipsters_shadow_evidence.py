#!/usr/bin/env python3
"""S2 — Tipsters Shadow Evidence Wrapper (Model B).

This wrapper invokes the compliance-first s2_tipsters_v2_live_dry_run.py
while enforcing sandboxed paths, terms reviews, and writing canonical script evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env
    from scripts.pipeline_steps._script_evidence import (
        _assert_non_production_sandbox_safety,
        build_wrapper_payload,
        classify_wrapper_result,
        write_terminal_script_evidence_or_fail,
    )
except Exception:
    sys.path.insert(0, str(ROOT))
    from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
    from scripts.pipeline_steps._runner import resolve_child_runtime_env
    from scripts.pipeline_steps._script_evidence import (
        _assert_non_production_sandbox_safety,
        build_wrapper_payload,
        classify_wrapper_result,
        write_terminal_script_evidence_or_fail,
    )

SCRIPTS = ["s2_tipsters_v2_live_dry_run.py"]
BLOCKED_REASON_PATTERNS = (
    (r"INVALID_REVIEW_ATTESTATION", "BLOCKED_INVALID_REVIEW_ATTESTATION"),
    (r"missing_required_review_flags", "BLOCKED_MISSING_REVIEW_FLAGS"),
    (r"no_fetch_attempts_or_no_entrypoints", "BLOCKED_NO_FETCH_ATTEMPTS"),
)


def main() -> None:
    p = argparse.ArgumentParser(description="S2 Shadow Evidence Wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", required=True)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="LIVE_SHADOW")
    p.add_argument("--terms-reviewed-json", dest="terms_reviewed_json", type=Path, default=None, help="Path to local review JSON")
    p.add_argument("--source", action="append", help="Specific sources to scrape")
    p.add_argument("--include-certified-shadow", action="store_true", help="Include certified shadow sources (like zawodtyper)")
    p.add_argument("--max-pages-per-source", type=int, default=1)
    p.add_argument("--allow-live-network", action="store_true", default=False)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--handoff-out", type=Path, default=None)
    p.add_argument("--sqlite-db", type=Path, default=None)
    args = p.parse_args()

    runtime_mode = parse_runtime_mode(args.runtime_mode)
    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    _assert_non_production_sandbox_safety(runtime_mode=runtime_mode, child_env=child_env)

    # Resolve output paths to default to sandbox directories if not explicitly provided
    # BET_PIPELINE_DATA_DIR or BET_PIPELINE_ARTIFACT_DIR
    data_dir_str = child_env.get("BET_PIPELINE_DATA_DIR")
    artifact_dir_str = child_env.get("BET_PIPELINE_ARTIFACT_DIR")

    if args.out:
        out_path = args.out
    elif data_dir_str:
        out_path = Path(data_dir_str) / f"{args.date}_tipster_consensus_shadow.json"
    else:
        out_path = ROOT / "betting" / "data" / f"{args.date}_tipster_consensus_shadow.json"

    if args.handoff_out:
        handoff_path = args.handoff_out
    elif artifact_dir_str:
        handoff_path = Path(artifact_dir_str) / f"{args.date}_tipster_handoff.json"
    else:
        handoff_path = ROOT / "betting" / "data" / f"{args.date}_tipster_handoff.json"

    if args.sqlite_db:
        sqlite_path = args.sqlite_db
    elif data_dir_str:
        sqlite_path = Path(data_dir_str) / f"tipsters_shadow_sidecar.sqlite"
    else:
        sqlite_path = ROOT / "betting" / "data" / f"tipsters_shadow_sidecar.sqlite"

    # Enforce Fail-closed: terms review is mandatory
    if not args.terms_reviewed_json:
        print("BLOCKED_TERMS_REVIEW_FILE_MISSING: --terms-reviewed-json is required")
        payload = build_wrapper_payload(
            step_id="S2_SHADOW",
            wrapper_scripts=SCRIPTS,
            wrapper_rc=10,
            runtime_mode=runtime_mode,
            dry_run=True,
            allow_write=False,
            allow_live_network=args.allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra={"error": "terms_reviewed_json_missing"},
        )
        write_terminal_script_evidence_or_fail(
            step_id="S2_SHADOW",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/pipeline_steps/{s}" for s in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_TERMS_REVIEW_FILE_MISSING",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        sys.exit(10)

    if not args.terms_reviewed_json.exists():
        print(f"BLOCKED_TERMS_REVIEW_FILE_NOT_FOUND: {args.terms_reviewed_json}")
        payload = build_wrapper_payload(
            step_id="S2_SHADOW",
            wrapper_scripts=SCRIPTS,
            wrapper_rc=11,
            runtime_mode=runtime_mode,
            dry_run=True,
            allow_write=False,
            allow_live_network=args.allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra={"error": "terms_reviewed_json_not_found"},
        )
        write_terminal_script_evidence_or_fail(
            step_id="S2_SHADOW",
            status="BLOCK",
            payload=payload,
            sources=tuple(f"scripts/pipeline_steps/{s}" for s in SCRIPTS),
            child_env=child_env,
            blocked_reasons=("BLOCKED_TERMS_REVIEW_FILE_NOT_FOUND",),
            no_pick_edge_stake_coupon_emitted=True,
        )
        sys.exit(11)

    # Construct and call s2_tipsters_v2_live_dry_run.py
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "pipeline_steps" / "s2_tipsters_v2_live_dry_run.py"),
        "--date", args.date,
        "--terms-reviewed-json", str(args.terms_reviewed_json),
        "--max-pages-per-source", str(args.max_pages_per_source),
        "--out", str(out_path),
        "--handoff-out", str(handoff_path),
    ]

    # Non-production sqlite DB write safety
    if runtime_mode != RuntimeMode.PRODUCTION or sqlite_path:
        cmd.extend(["--sqlite-db", str(sqlite_path)])

    if args.include_certified_shadow:
        cmd.append("--include-certified-shadow")

    if args.source:
        for s in args.source:
            cmd.extend(["--source", s])

    print("Running shadow runner:", " ".join(cmd))
    
    # Set up environments
    env = child_env.copy()
    if args.allow_live_network:
        env["BET_PIPELINE_LIVE_ACK"] = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"

    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    
    output_parts = [part for part in (res.stdout, res.stderr) if part]
    output = "".join(output_parts)
    if output:
        sys.stdout.write(output)
        if not output.endswith("\n"):
            sys.stdout.write("\n")

    # Parse total_picks and check for results
    total_picks = 0
    match = re.search(r"total_picks=(\d+)", output)
    if match:
        total_picks = int(match.group(1))

    # Read handoff file to print details if successful
    handoff_details = {
        "allowed_consumers": ["S3 contextual cross-check", "S4 market sanity", "manual Superbet quote review"],
        "forbidden_actions": ["EV", "stake", "coupon", "final bet", "Superbet combined odds"],
        "contract": "evidence_only_not_betting_decision"
    }

    # Print output contract requirements
    print("\n--- SHADOW EVIDENCE PIPELINE INTEGRATION CONTRACT ---")
    print(f"total_picks: {total_picks}")
    print(f"handoff_path: {handoff_path}")
    print(f"allowed_consumers: {handoff_details['allowed_consumers']}")
    print(f"forbidden_actions: {handoff_details['forbidden_actions']}")
    print(f"evidence_only_not_betting_decision: True")
    print("-----------------------------------------------------\n")

    extra_fields = {
        "total_picks": total_picks,
        "handoff_path": str(handoff_path),
        "allowed_consumers": handoff_details["allowed_consumers"],
        "forbidden_actions": handoff_details["forbidden_actions"],
        "evidence_only_not_betting_decision": True,
    }

    payload = build_wrapper_payload(
        step_id="S2_SHADOW",
        wrapper_scripts=SCRIPTS,
        wrapper_rc=res.returncode,
        runtime_mode=runtime_mode,
        dry_run=True,
        allow_write=False,
        allow_live_network=args.allow_live_network,
        child_env=child_env,
        runtime_path_source=runtime_path_source,
        extra=extra_fields,
    )

    status, blocked_reasons = classify_wrapper_result(
        rc=res.returncode,
        output=output,
        blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
        fallback_blocked_reason="BLOCKED_TIPSTER_DATA_MISSING",
    )

    write_terminal_script_evidence_or_fail(
        step_id="S2_SHADOW",
        status=status,
        payload=payload,
        sources=tuple(f"scripts/pipeline_steps/{s}" for s in SCRIPTS),
        child_env=child_env,
        blocked_reasons=blocked_reasons,
        no_pick_edge_stake_coupon_emitted=True,
        extra_top_level_fields=extra_fields,
    )

    sys.exit(0 if status == "PASS" else res.returncode)


if __name__ == "__main__":
    main()
