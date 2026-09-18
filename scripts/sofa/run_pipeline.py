#!/usr/bin/env python3
"""The `sofa` pipeline, end to end (PLAN §A3, §A4).

Runs BOARD -> RESOLVE -> OFFER -> SAMPLES -> OFFER -> SHEET -> COUPON.

The offer is read **twice on purpose** (A4): once before sampling, so we only
pay for metrics somebody actually prices, and once immediately before the coupon
so the price the bar is compared against is fresh. Leaving that to "whoever runs
the stages in the right order" is how a morning price ends up on an evening
coupon, so the order lives in code.

Each stage is still runnable on its own against the artifact on disk; this
script only sequences them.

Exit: 0 = OK, 1 = PARTIAL, 2 = FAILED.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from bet.sofa.config import SofaConfig
from bet.sofa.timeutil import now

# Stage entry points are imported lazily inside run_stage so that a broken
# stage module fails that stage, not the whole run.
STAGE_MODULES: dict[str, str] = {
    "BOARD": "scripts.sofa.run_board",
    "RESOLVE": "scripts.sofa.run_resolve",
    "OFFER": "scripts.sofa.run_offer",
    "SAMPLES": "scripts.sofa.run_samples",
    "SHEET": "scripts.sofa.run_sheet",
    "COUPON": "scripts.sofa.run_coupon",
}

# (stage, label) — OFFER appears twice by design.
DEFAULT_SEQUENCE: list[tuple[str, str]] = [
    ("BOARD", "BOARD"),
    ("RESOLVE", "RESOLVE"),
    ("OFFER", "OFFER (pre-sample: which markets have a price at all)"),
    ("SAMPLES", "SAMPLES"),
    ("OFFER", "OFFER (refresh: the price the bar is measured against)"),
    ("SHEET", "SHEET"),
    ("COUPON", "COUPON"),
]


@dataclass
class StageResult:
    stage: str
    label: str
    exit_code: int

    @property
    def verdict(self) -> str:
        return {0: "OK", 1: "PARTIAL"}.get(self.exit_code, "FAILED")


def run_stage(stage: str, date: str) -> int:
    """Invoke one stage's main() with the date argument it expects."""
    import importlib

    module = importlib.import_module(STAGE_MODULES[stage])
    main: Callable[[], int | None] = module.main

    argv = sys.argv
    sys.argv = [STAGE_MODULES[stage], "--date", date]
    try:
        result = main()
    except SystemExit as exc:  # stages that still exit rather than return
        code = exc.code
        return code if isinstance(code, int) else 0
    finally:
        sys.argv = argv
    return result if isinstance(result, int) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=now().strftime("%Y-%m-%d"), help="YYYY-MM-DD")
    parser.add_argument(
        "--from-stage",
        choices=list(STAGE_MODULES),
        help="resume at this stage, reusing the artifacts already on disk",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="abort the run at the first FAILED stage instead of continuing",
    )
    args = parser.parse_args()

    sequence = DEFAULT_SEQUENCE
    if args.from_stage:
        start = next(
            (i for i, (s, _) in enumerate(sequence) if s == args.from_stage), None
        )
        if start is None:
            print(f"unknown stage {args.from_stage}", file=sys.stderr)
            return 2
        sequence = sequence[start:]

    results: list[StageResult] = []
    for stage, label in sequence:
        print(f"--- {label} ---", file=sys.stderr)
        code = run_stage(stage, args.date)
        results.append(StageResult(stage, label, code))
        if code >= 2:
            print(f"{label}: FAILED (exit {code})", file=sys.stderr)
            if args.stop_on_failure:
                break

    worst = max((r.exit_code for r in results), default=0)
    verdict = {0: "OK", 1: "PARTIAL"}.get(worst, "FAILED")

    # One id for the whole sequence, so a single run's rows can be pulled
    # out of the log without guessing timestamps (F8).
    os.environ.setdefault("SOFA_RUN_ID", uuid.uuid4().hex[:12])

    config = SofaConfig.from_env()
    summary = {
        "stage": "PIPELINE",
        "verdict": verdict,
        "metrics": {
            "stages": [
                {"stage": r.stage, "label": r.label, "verdict": r.verdict}
                for r in results
            ]
        },
        "output_path": str(Path(config.runs_dir) / args.date),
    }
    print(f"SOFA_SUMMARY: {json.dumps(summary)}")
    return 0 if verdict == "OK" else (1 if verdict == "PARTIAL" else 2)


if __name__ == "__main__":
    sys.exit(main())
