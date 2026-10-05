#!/usr/bin/env python3
"""Validate the pre-registered tests (config/sofa_test_registry.json, plan
docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md F5.1).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/check_test_registry.py \\
        [--registry <path>]

The one rule that makes a registry worth having: a test is judged only on
data that did not exist when it was written down. So every test's
`data_window.from` must be strictly AFTER its `registered_on`, a window that
ends must end on or after it starts, ids are unique, and every field a
reader needs is present. Offline. Exit 0 = valid, 1 = a finding (all listed),
2 = the file cannot be read.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = _REPO / "config" / "sofa_test_registry.json"
REQUIRED = ("id", "registered_on", "status", "hypothesis", "rule", "population",
            "data_window", "required_n", "stop_criterion", "evidence")


def _day(raw: object) -> date | None:
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def findings(doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    statuses = set(doc.get("statuses") or [])
    seen: set[str] = set()
    tests = doc.get("tests")
    if not isinstance(tests, list) or not tests:
        return ["no tests"]
    for i, t in enumerate(tests):
        tid = str(t.get("id") or f"#{i}")
        missing = [k for k in REQUIRED if not t.get(k)]
        if missing:
            out.append(f"{tid}: missing {', '.join(missing)}")
        if tid in seen:
            out.append(f"{tid}: duplicate id")
        seen.add(tid)
        if statuses and t.get("status") not in statuses:
            out.append(f"{tid}: status {t.get('status')!r} not in {sorted(statuses)}")
        registered = _day(t.get("registered_on"))
        window = t.get("data_window") or {}
        start = _day(window.get("from"))
        if registered is None:
            out.append(f"{tid}: registered_on {t.get('registered_on')!r} is not a date")
        if start is None:
            out.append(f"{tid}: data_window.from {window.get('from')!r} is not a date")
        if registered is not None and start is not None and start <= registered:
            out.append(
                f"{tid}: REFUSED - data window starts {start}, not after its "
                f"registration {registered}: the test would be judged on data "
                "that existed when it was written"
            )
        if window.get("to") is not None:
            end = _day(window["to"])
            if end is None:
                out.append(f"{tid}: data_window.to {window['to']!r} is not a date")
            elif start is not None and end < start:
                out.append(f"{tid}: data window ends {end} before it starts {start}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    args = ap.parse_args()
    try:
        doc = json.loads(Path(args.registry).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAILED: {args.registry}: {exc}", file=sys.stderr)
        return 2
    found = findings(doc)
    for line in found:
        print(line)
    n = len(doc.get("tests") or [])
    print(f"{n} test(s), {len(found)} finding(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
