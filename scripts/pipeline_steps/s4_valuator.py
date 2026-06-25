#!/usr/bin/env python3
"""S4 — Pricing & odds valuation wrapper. Runs `fetch_odds_multi.py` then `odds_evaluator.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

try:
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import run_scripts


def main() -> None:
    p = argparse.ArgumentParser(description="S4 Valuator wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    from bet.pipeline.integration_artifacts import write_script_evidence
    import os

    data_dir = Path(os.environ.get("BET_PIPELINE_DATA_DIR", str(ROOT / "betting" / "data")))
    snapshot_path = data_dir / "odds_api_snapshot.json"

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
            write_script_evidence(
                "S4",
                status="BLOCK",
                payload={"fetch_odds_rc": rc_fetch, "error": "fetch_returned_no_events"},
                sources=(),
                evidence_refs=(),
                blocked_reasons=("BLOCKED_LIVE_SOURCE_MISSING",),
                environ=os.environ,
            )
            sys.exit(rc_fetch)
        else:
            write_script_evidence(
                "S4",
                status="FAILED",
                payload={"fetch_odds_rc": rc_fetch, "error": f"fetch_failed_unexpectedly_with_code_{rc_fetch}"},
                sources=(),
                evidence_refs=(),
                blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
                environ=os.environ,
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
            write_script_evidence(
                "S4",
                status="BLOCK",
                payload={"fetch_odds_rc": 0, "odds_evaluator_rc": rc_eval, "error": "evaluator_failed_no_candidates"},
                sources=(),
                evidence_refs=(),
                blocked_reasons=("BLOCKED_UPSTREAM_DATA_MISSING",),
                environ=os.environ,
            )
            sys.exit(rc_eval)
        else:
            write_script_evidence(
                "S4",
                status="FAILED",
                payload={"fetch_odds_rc": 0, "odds_evaluator_rc": rc_eval, "error": f"evaluator_failed_unexpectedly_with_code_{rc_eval}"},
                sources=(),
                evidence_refs=(),
                blocked_reasons=("FAILED_UNEXPECTED_SUBPROCESS_ERROR",),
                environ=os.environ,
            )
            sys.exit(rc_eval)

    # Both succeeded! Now check if expected output/evidence exist.
    if snapshot_path.exists():
        write_script_evidence(
            "S4",
            status="PASS",
            payload={"fetch_odds_rc": 0, "odds_evaluator_rc": 0},
            sources=(),
            evidence_refs=(),
            environ=os.environ,
        )
        sys.exit(0)
    else:
        write_script_evidence(
            "S4",
            status="BLOCK",
            payload={"fetch_odds_rc": 0, "odds_evaluator_rc": 0, "error": "snapshot_missing"},
            sources=(),
            evidence_refs=(),
            blocked_reasons=("BLOCKED_LIVE_SOURCE_MISSING",),
            environ=os.environ,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
