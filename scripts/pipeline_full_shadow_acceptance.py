#!/usr/bin/env python3
"""CLI for full-pipeline shadow acceptance."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bet.pipeline.full_shadow_acceptance import (  # noqa: E402
    FullShadowAcceptanceConfig,
    run_full_shadow_acceptance,
)
from bet.pipeline.run_evidence import write_json_atomic  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full pipeline shadow acceptance.")
    parser.add_argument("--betting-day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--base-dir", required=True, help="Acceptance base directory")
    parser.add_argument("--runtime-mode", required=True, help="Runtime mode")
    parser.add_argument("--report-path", required=True, help="JSON report output path")
    args = parser.parse_args()

    config = FullShadowAcceptanceConfig(
        base_dir=Path(args.base_dir),
        betting_day=args.betting_day,
        run_id=args.run_id,
        runtime_mode=args.runtime_mode,
    )

    report_path = Path(args.report_path).resolve(strict=False)

    try:
        report = run_full_shadow_acceptance(config, report_path=report_path)
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    write_json_atomic(report_path, report.to_jsonable())

    print(f"STATUS={report.status}")
    print(f"PIPELINE_TERMINAL_STATUS={report.pipeline_terminal_status}")
    print(f"S8_COUPON_DRAFT_PATH={report.s8_coupon_draft_path}")
    print(f"REPORT_PATH={report_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
