#!/usr/bin/env python3
"""Depth check of an analyst's report (`bet.sofa.report_check`).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_analyst_report.py \\
        --report <md> [--report <md> ...] [--date <d>] [--read-set <json> ...]

Prints every finding (Polish) per report. Exit 0 = clean, 1 = findings
(rewrite the report), 2 = a report cannot be read. Offline, read-only.

A `RYNEK:` WATCH is checked against its leg's dossier row
(`report_check.market_findings`) when the day's run is known: `--date`, or
the report sitting in runs/sofa/<d>/ (`report_check.report_run`); the dossier
a `--read-set` leg names wins. merge_reads.py always checks it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bet.sofa.report_check import (  # noqa: E402
    findings,
    load_dossiers,
    market_reads,
    reads_block,
    report_day,
    report_kind,
    report_run,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="append", required=True)
    ap.add_argument("--date", default=None,
                    help="the run whose dossiers check a RYNEK WATCH")
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--read-set", action="append", type=Path, default=[])
    args = ap.parse_args(argv)
    try:
        set_legs = [leg for p in args.read_set
                    for leg in json.loads(p.read_text(encoding="utf-8"))]
    except (OSError, ValueError) as exc:
        print(f"--read-set: {exc}", file=sys.stderr)
        return 2
    worst = 0
    for raw in args.report:
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: nie do odczytu: {exc}", file=sys.stderr)
            return 2
        run = (Path(args.runs_dir) / args.date) if args.date else report_run(path)
        dossiers = None if run is None else load_dossiers(
            run, {r.get("sofascore_event_id") for r in market_reads(reads_block(text))},
            set_legs)
        found = findings(text, report_day(path.name), **report_kind(path.name),
                         dossiers=dossiers)
        if not found:
            print(f"{path}: OK")
            continue
        worst = 1
        print(f"{path}: {len(found)} do poprawy")
        for line in found:
            print(f"  - {line}")
    return worst


if __name__ == "__main__":
    sys.exit(main())
