"""Thin CLI wrapper for running the pipeline. Requires explicit --adapter and --allow-write to persist.

This script intentionally defaults to dry-run. Use with caution.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from importlib import import_module
import sys

from bet.orchestrator import run_pipeline_for_date


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", help="Date to run pipeline for (YYYY-MM-DD)", required=True)
    p.add_argument("--allow-write", action="store_true", help="Allow writes to DB")
    p.add_argument("--adapter", help="Dotted path to concrete adapter class (e.g. mypkg.adapters.BetclicAdapter)")
    args = p.parse_args()

    if not args.adapter:
        print("Error: --adapter is required. Provide a dotted path to a concrete adapter class.")
        sys.exit(2)

    # dynamically import adapter
    try:
        module_path, class_name = args.adapter.rsplit(".", 1)
        module = import_module(module_path)
        AdapterClass = getattr(module, class_name)
        adapter = AdapterClass()
    except Exception as e:
        print(f"Failed to import adapter {args.adapter}: {e}")
        sys.exit(3)

    run_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    res = run_pipeline_for_date(run_date, adapter, dry_run=not args.allow_write, allow_write=args.allow_write)
    print("Pipeline run complete.")


if __name__ == "__main__":
    main()
