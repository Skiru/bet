#!/usr/bin/env python3
"""CLI for paper-trading readiness."""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bet.pipeline.paper_trading import (  # noqa: E402
    PaperTradingConfig,
    run_paper_trading_readiness,
    run_paper_trading_single_coupon_source,
)
from bet.pipeline.run_evidence import write_json_atomic  # noqa: E402


def _decimal_arg(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal value: {value}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run paper trading readiness.")
    parser.add_argument(
        "--mode",
        choices=("readiness", "single-coupon-source"),
        default="readiness",
        help="Execution mode",
    )
    parser.add_argument("--betting-day", required=True, help="YYYY-MM-DD")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--base-dir", required=True, help="Base directory for fixture artifacts")
    parser.add_argument("--ledger-dir", required=True, help="Ledger directory outside the repo")
    parser.add_argument("--runtime-mode", required=True, help="Runtime mode")
    parser.add_argument("--bankroll-units", required=True, type=_decimal_arg, help="Paper bankroll units")
    parser.add_argument("--max-stake-units-per-coupon", required=True, type=_decimal_arg, help="Max stake per paper coupon")
    parser.add_argument("--max-daily-risk-units", required=True, type=_decimal_arg, help="Max total open risk units")
    parser.add_argument("--report-path", required=True, help="JSON report output path")
    args = parser.parse_args()

    config = PaperTradingConfig(
        base_dir=Path(args.base_dir),
        betting_day=args.betting_day,
        run_id=args.run_id,
        ledger_dir=Path(args.ledger_dir),
        runtime_mode=args.runtime_mode,
        bankroll_units=args.bankroll_units,
        max_stake_units_per_coupon=args.max_stake_units_per_coupon,
        max_daily_risk_units=args.max_daily_risk_units,
    )
    report_path = Path(args.report_path).resolve(strict=False)

    try:
        if args.mode == "single-coupon-source":
            if args.max_stake_units_per_coupon != Decimal("1"):
                raise ValueError("single-coupon-source mode requires --max-stake-units-per-coupon 1")
            if args.max_daily_risk_units != Decimal("1"):
                raise ValueError("single-coupon-source mode requires --max-daily-risk-units 1")
            report = run_paper_trading_single_coupon_source(config, report_path=report_path)
        else:
            report = run_paper_trading_readiness(config, report_path=report_path)
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    write_json_atomic(report_path, report.to_jsonable())
    print(f"STATUS={report.status}")
    print(f"LEDGER_PATH={report.ledger_path}")
    print(f"PAPER_COUPON_COUNT={report.coupon_count}")
    print(f"TOTAL_STAKE_UNITS={report.total_stake_units}")
    print(f"READY_FOR_MANUAL_LOW_STAKE_PILOT={report.ready_for_manual_low_stake_pilot}")
    print(f"REPORT_PATH={report_path}")
    return 0 if report.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
