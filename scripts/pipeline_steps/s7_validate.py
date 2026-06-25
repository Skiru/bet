#!/usr/bin/env python3
"""S7b — Market Availability Validation wrapper. Runs validate_betclic_markets.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._script_evidence import run_wrapper_scripts_with_evidence
    from scripts.pipeline_steps._runner import run_scripts

SCRIPTS = ["validate_betclic_markets.py"]
BLOCKED_REASON_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"upstream data", "BLOCKED_UPSTREAM_DATA_MISSING"),
    (r"manual verification required|betclic boundary", "BLOCKED_BETCLIC_MARKET_BOUNDARY"),
)


def _certification_targets() -> None:
    run_scripts(SCRIPTS)


def main() -> None:
    p = argparse.ArgumentParser(description="S7b — Market Availability Validation wrapper")
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    run_wrapper_scripts_with_evidence(
        step_id="S7b",
        wrapper_scripts=SCRIPTS,
        date=args.date,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
        blocked_reason_patterns=BLOCKED_REASON_PATTERNS,
        fallback_blocked_reason="BLOCKED_MARKET_AVAILABILITY_MISSING",
    )


if __name__ == "__main__":
    main()
