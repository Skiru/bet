#!/usr/bin/env python3
"""S3 — Feature derivation / deep stats wrapper. Runs `deep_stats_report.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import run_scripts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", "--betting-day", dest="date", help="YYYY-MM-DD", default=None)
    p.add_argument("--run-id", dest="run_id", help="Run ID", default=None)
    p.add_argument("--runtime-mode", dest="runtime_mode", help="Runtime mode", default="DRY_RUN")
    p.add_argument("--allow-live-network", dest="allow_live_network", action="store_true", default=False)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    args = p.parse_args()

    rc = run_scripts(
        ["deep_stats_report.py"],
        date=args.date,
        dry_run=args.dry_run,
        allow_write=args.allow_write,
        runtime_mode=args.runtime_mode,
        betting_day=args.date,
        run_id=args.run_id,
        allow_live_network=args.allow_live_network,
    )
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
