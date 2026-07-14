#!/usr/bin/env python3
"""S6 — Repeats check thin canonical wrapper."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from scripts.pipeline_steps._runner import resolve_child_runtime_env
from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence

SCRIPTS = ["check_48h_repeats.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"repeat guard input missing|missing repeat guard|repeat guard.*missing|repeat guard.*not found", "BLOCKED_REPEAT_GUARD_INPUT_MISSING"),
    (r"repeat guard input empty|empty candidate list|zero candidates|no candidates|empty candidate input", "BLOCKED_REPEAT_GUARD_INPUT_EMPTY"),
    (r"repeat signal|signal conflict|repeat guard conflict|repeat guard triggered|repeat conflict|repeat-loss exclusions found", "BLOCKED_REPEAT_SIGNAL_CONFLICT"),
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--input", type=Path, default=None, help="Input override")
    p.add_argument("--output", type=Path, default=None, help="Output override")
    args = p.parse_args()

    mode = parse_runtime_mode(args.runtime_mode)

    # Setup ScriptInvocations
    from scripts.pipeline_steps._runner import ScriptInvocation

    input_path = args.input
    output_path = args.output

    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )

    if not output_path:
        if child_env.get("BET_PIPELINE_DATA_DIR"):
            output_path = Path(child_env["BET_PIPELINE_DATA_DIR"]) / f"repeat_loss_handoff_{args.date}.json"
        else:
            output_path = ROOT / "betting" / "data" / f"repeat_loss_handoff_{args.date}.json"

    extra_payload = {
        "s6_input_path": str(input_path) if input_path else None,
        "s6_output_path": str(output_path) if output_path else None,
        "checked_candidates_count": 0,
        "recent_losses_count": 0,
        "repeat_loss_count": 0,
        "candidate_source": "input_json",
    }

    argv = ["--date", args.date] if args.date else []
    if args.input:
        argv += ["--input", str(args.input)]
    if args.output:
        argv += ["--output", str(args.output)]

    invocations = [
        ScriptInvocation(
            script="check_48h_repeats.py",
            argv=argv,
        )
    ]

    try:
        run_wrapper_scripts_with_evidence(
            step_id="S6",
            wrapper_scripts=invocations,
            date=args.date,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            runtime_mode=args.runtime_mode,
            betting_day=args.date,
            run_id=args.run_id,
            allow_live_network=args.allow_live_network,
            blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
            fallback_blocked_reason="BLOCKED_REPEAT_GUARD_INPUT_MISSING",
            extra_payload=extra_payload,
        )
    except SystemExit as exc:
        sys.exit(exc.code)


if __name__ == "__main__":
    main()
