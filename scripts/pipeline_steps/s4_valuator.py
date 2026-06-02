#!/usr/bin/env python3
"""S4 — Pricing & odds valuation wrapper. Runs `fetch_odds_multi.py` then `odds_evaluator.py`.
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
    p.add_argument("--date", help="YYYY-MM-DD", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=True)
    p.add_argument("--allow-write", dest="allow_write", action="store_true", default=False)
    args = p.parse_args()
    # fetch_odds_multi does not accept a --date flag (uses current window),
    # so run it without passing a date. Then run odds_evaluator with the date.
    rc = run_scripts(["fetch_odds_multi.py"], date=None, dry_run=args.dry_run, allow_write=args.allow_write)
    if rc != 0:
        raise SystemExit(rc)
    rc = run_scripts(["odds_evaluator.py"], date=args.date, dry_run=args.dry_run, allow_write=args.allow_write)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
