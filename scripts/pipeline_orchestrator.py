"""Thin CLI wrapper for running the pipeline. Requires explicit --allow-write to persist.

This script intentionally defaults to dry-run. Use with caution.
"""
from __future__ import annotations

import argparse
from datetime import datetime

from bet.orchestrator import run_pipeline_for_date
from bet.adapters.base import BookmakerAdapter


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Date to run pipeline for (YYYY-MM-DD)", required=True)
    p.add_argument("--allow-write", action="store_true", help="Allow writes to DB")
    args = p.parse_args()
    run_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    adapter = BookmakerAdapter()  # placeholder: replace with real adapter implementation
    res = run_pipeline_for_date(run_date, adapter, dry_run=not args.allow_write, allow_write=args.allow_write)
    print("Pipeline run complete.")


if __name__ == "__main__":
    main()
