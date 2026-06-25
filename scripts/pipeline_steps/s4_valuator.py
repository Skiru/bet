#!/usr/bin/env python3
"""S4 — Pricing & odds valuation wrapper. Runs `fetch_odds_multi.py` then `odds_evaluator.py`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.pipeline_steps._script_evidence import build_wrapper_payload, write_terminal_script_evidence_or_fail
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._script_evidence import build_wrapper_payload, write_terminal_script_evidence_or_fail
    from scripts.pipeline_steps._runner import run_scripts

SCRIPTS = ["fetch_odds_multi.py", "odds_evaluator.py"]


def main() -> None:
    p = argparse.ArgumentParser(description="S4 Valuator wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    from scripts.pipeline_steps._runner import resolve_child_runtime_env

    child_env, runtime_path_source = resolve_child_runtime_env(
        os.environ,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        run_root=None,
    )
    data_dir = Path(child_env.get("BET_PIPELINE_DATA_DIR", str(ROOT / "betting" / "data")))
    snapshot_path = data_dir / "odds_api_snapshot.json"

    def _payload(fetch_rc: int, eval_rc: int | None = None, error: str | None = None) -> dict[str, object]:
        extra: dict[str, object] = {"fetch_odds_rc": fetch_rc}
        if eval_rc is not None:
            extra["odds_evaluator_rc"] = eval_rc
        if error is not None:
            extra["error"] = error
        return build_wrapper_payload(
            step_id="S4",
            wrapper_scripts=SCRIPTS,
            wrapper_rc=eval_rc if eval_rc is not None else fetch_rc,
            runtime_mode=args.runtime_mode,
            dry_run=args.dry_run,
            allow_write=args.allow_write,
            allow_live_network=args.allow_live_network,
            child_env=child_env,
            runtime_path_source=runtime_path_source,
            extra=extra,
        )

    def _write(status: str, payload: dict[str, object], blocked_reasons: tuple[str, ...] = ()) -> None:
        write_terminal_script_evidence_or_fail(
            step_id="S4",
            status=status,
            payload=payload,
            sources=tuple(f"scripts/{script_name}" for script_name in SCRIPTS),
            child_env=child_env,
            blocked_reasons=blocked_reasons,
            no_pick_edge_stake_coupon_emitted=True,
        )

    # Step 1: Run fetch_odds_multi.py
    rc_fetch = run_scripts(
        ["fetch_odds_multi.py"],
        date=None,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
    )

    if rc_fetch != 0:
        if rc_fetch == 1:
            _write(
                status="BLOCK",
                payload=_payload(rc_fetch, error="fetch_returned_no_events"),
                blocked_reasons=("BLOCKED_LIVE_SOURCE_MISSING",),
            )
            sys.exit(rc_fetch)
        else:
            _write(
                status="FAILED",
                payload=_payload(rc_fetch, error=f"fetch_failed_unexpectedly_with_code_{rc_fetch}"),
                blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
            )
            sys.exit(rc_fetch)

    # Step 2: Run odds_evaluator.py
    rc_eval = run_scripts(
        ["odds_evaluator.py"],
        date=args.date,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
    )

    if rc_eval != 0:
        if rc_eval == 1:
            _write(
                status="BLOCK",
                payload=_payload(0, rc_eval, "evaluator_failed_no_candidates"),
                blocked_reasons=("BLOCKED_UPSTREAM_DATA_MISSING",),
            )
            sys.exit(rc_eval)
        else:
            _write(
                status="FAILED",
                payload=_payload(0, rc_eval, f"evaluator_failed_unexpectedly_with_code_{rc_eval}"),
                blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
            )
            sys.exit(rc_eval)

    # Both succeeded! Now check if expected output/evidence exist.
    if snapshot_path.exists():
        _write(
            status="PASS",
            payload=_payload(0, 0),
        )
        sys.exit(0)
    else:
        _write(
            status="BLOCK",
            payload=_payload(0, 0, "snapshot_missing"),
            blocked_reasons=("BLOCKED_LIVE_SOURCE_MISSING",),
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
