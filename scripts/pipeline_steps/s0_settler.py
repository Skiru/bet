#!/usr/bin/env python3
"""S0 — Settlement step wrapper. Runs `scripts/settle_on_finish.py`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from scripts.pipeline_steps._runner import run_scripts
except Exception:
    # Allow running this file directly (not as a package module)
    ROOT = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(ROOT))
    from scripts.pipeline_steps._runner import run_scripts


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="YYYY-MM-DD", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    args = p.parse_args()
    rc = run_scripts(["settle_on_finish.py"], date=args.date, dry_run=args.dry_run, allow_write=args.allow_write, date_arg="--betting-day")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
