#!/usr/bin/env python3
"""Depth check of an analyst's report (`bet.sofa.report_check`).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_analyst_report.py \\
        --report <md> [--report <md> ...]

Prints every finding (Polish) per report. Exit 0 = clean, 1 = findings
(rewrite the report), 2 = a report cannot be read. Offline, read-only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bet.sofa.report_check import (  # noqa: E402
    findings,
    report_day,
    report_kind,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="append", required=True)
    args = ap.parse_args(argv)
    worst = 0
    for raw in args.report:
        path = Path(raw)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{path}: nie do odczytu: {exc}", file=sys.stderr)
            return 2
        found = findings(text, report_day(path.name), **report_kind(path.name))
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
