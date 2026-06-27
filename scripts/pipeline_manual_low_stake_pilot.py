#!/usr/bin/env python3
"""CLI for manual low-stake pilot preparation, placement recording, and settlement."""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bet.pipeline.manual_low_stake_pilot import (  # noqa: E402
    ManualLowStakePilotConfig,
    build_manual_low_stake_pilot_report,
    execute_with_report,
    load_latest_manual_pilot_coupons,
    prepare_manual_pilot_from_paper_coupon,
    read_ledger_events,
    record_manual_bookmaker_placement,
    settle_manual_pilot_coupon,
    validate_ledger_jsonl_schema,
    _load_open_paper_coupon,
)
from bet.pipeline.run_evidence import write_json_atomic  # noqa: E402


def _decimal_arg(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal value: {value}") from exc


def _infer_base_dir(pilot_dir: Path, betting_day: str, run_id: str) -> Path:
    resolved = Path(pilot_dir).resolve(strict=False)
    if resolved.name == run_id and resolved.parent.name == betting_day:
        return resolved.parent.parent
    return resolved.parent


def _add_hidden_forbidden_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-automated-bookmaker-placement", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-betclic-api", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--allow-browser-automation", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--runtime-mode", default="DRY_RUN", help=argparse.SUPPRESS)
    parser.add_argument("--kill-switch", action="store_true", help=argparse.SUPPRESS)


def _write_report(report_path: Path, report) -> None:
    write_json_atomic(report_path, report.to_jsonable())


def _print_report(report_path: Path, report, *, coupon_id: str | None = None) -> int:
    print(f"STATUS={report.status}")
    print(f"REPORT_PATH={report_path}")
    print(f"LEDGER_PATH={report.ledger_path}")
    print(f"MANUAL_COUPON_COUNT={report.manual_coupon_count}")
    if coupon_id is not None:
        print(f"MANUAL_PILOT_COUPON_ID={coupon_id}")
    return 0 if report.status == "PASS" else 1


def _prepare_command(args: argparse.Namespace) -> int:
    base_dir = Path(args.base_dir).resolve(strict=False)
    pilot_dir = Path(args.pilot_dir).resolve(strict=False)
    ledger_path = Path(args.ledger_path).resolve(strict=False)
    report_path = Path(args.report_path).resolve(strict=False)
    paper_ledger_path = Path(args.paper_ledger_path).resolve(strict=False)
    config = ManualLowStakePilotConfig(
        base_dir=base_dir,
        betting_day=args.betting_day,
        run_id=args.run_id,
        pilot_dir=pilot_dir,
        ledger_path=ledger_path,
        runtime_mode=args.runtime_mode,
        max_stake_units_per_coupon=args.max_stake_units_per_coupon,
        max_daily_risk_units=args.max_daily_risk_units,
        daily_stop_loss_units=args.daily_stop_loss_units,
        legal_operator_attested=args.legal_operator_attested,
        age_kyc_attested=args.age_kyc_attested,
        responsible_gambling_limits_attested=args.responsible_gambling_limits_attested,
        manual_click_attested=args.manual_click_attested,
        kill_switch=args.kill_switch,
        allow_automated_bookmaker_placement=args.allow_automated_bookmaker_placement,
        allow_betclic_api=args.allow_betclic_api,
        allow_browser_automation=args.allow_browser_automation,
    )

    try:
        source_coupon = _load_open_paper_coupon(paper_ledger_path, args.source_paper_coupon_id)
        if source_coupon.stake_units != args.stake_units:
            raise ValueError(
                f"stake_units must match source paper coupon stake ({source_coupon.stake_units})"
            )
        coupon, report = execute_with_report(
            config=config,
            report_path=report_path,
            operation=lambda: prepare_manual_pilot_from_paper_coupon(
                config=config,
                paper_ledger_path=paper_ledger_path,
                source_paper_coupon_id=args.source_paper_coupon_id,
                manual_bookmaker_name=args.manual_bookmaker_name,
            ),
        )
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    _write_report(report_path, report)
    return _print_report(report_path, report, coupon_id=coupon.manual_pilot_coupon_id)


def _record_placement_command(args: argparse.Namespace) -> int:
    pilot_dir = Path(args.pilot_dir).resolve(strict=False)
    ledger_path = Path(args.ledger_path).resolve(strict=False)
    report_path = Path(args.report_path).resolve(strict=False)
    config = ManualLowStakePilotConfig(
        base_dir=_infer_base_dir(pilot_dir, args.betting_day, args.run_id),
        betting_day=args.betting_day,
        run_id=args.run_id,
        pilot_dir=pilot_dir,
        ledger_path=ledger_path,
        runtime_mode=args.runtime_mode,
        manual_click_attested=args.manual_click_attested,
        kill_switch=args.kill_switch,
        allow_automated_bookmaker_placement=args.allow_automated_bookmaker_placement,
        allow_betclic_api=args.allow_betclic_api,
        allow_browser_automation=args.allow_browser_automation,
    )

    try:
        coupon, report = execute_with_report(
            config=config,
            report_path=report_path,
            operation=lambda: record_manual_bookmaker_placement(
                config=config,
                manual_pilot_coupon_id=args.manual_pilot_coupon_id,
                manual_bookmaker_name=args.manual_bookmaker_name,
                manual_bookmaker_ticket_id=args.manual_bookmaker_ticket_id,
                manual_placed_at_utc=args.manual_placed_at_utc,
            ),
        )
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    _write_report(report_path, report)
    return _print_report(report_path, report, coupon_id=coupon.manual_pilot_coupon_id)


def _settle_command(args: argparse.Namespace) -> int:
    pilot_dir = Path(args.pilot_dir).resolve(strict=False)
    ledger_path = Path(args.ledger_path).resolve(strict=False)
    report_path = Path(args.report_path).resolve(strict=False)
    existing = load_latest_manual_pilot_coupons(ledger_path)
    current = existing.get(args.manual_pilot_coupon_id)
    config = ManualLowStakePilotConfig(
        base_dir=_infer_base_dir(pilot_dir, args.betting_day, args.run_id),
        betting_day=args.betting_day,
        run_id=args.run_id,
        pilot_dir=pilot_dir,
        ledger_path=ledger_path,
        runtime_mode=args.runtime_mode,
        max_manual_coupons_per_day=max(len(existing), 1),
        max_stake_units_per_coupon=(current.stake_units if current is not None else Decimal("1")),
        max_daily_risk_units=sum((coupon.stake_units for coupon in existing.values()), start=Decimal("1")),
        daily_stop_loss_units=max(
            sum((-coupon.pnl_units for coupon in existing.values() if coupon.pnl_units < 0), start=Decimal("0")),
            Decimal("1"),
        ),
        kill_switch=args.kill_switch,
        allow_automated_bookmaker_placement=args.allow_automated_bookmaker_placement,
        allow_betclic_api=args.allow_betclic_api,
        allow_browser_automation=args.allow_browser_automation,
    )

    try:
        coupon, report = execute_with_report(
            config=config,
            report_path=report_path,
            operation=lambda: settle_manual_pilot_coupon(
                config=config,
                manual_pilot_coupon_id=args.manual_pilot_coupon_id,
                result=args.result,
            ),
        )
    except ValueError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2

    _write_report(report_path, report)
    return _print_report(report_path, report, coupon_id=coupon.manual_pilot_coupon_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual low-stake pilot safeguards.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Prepare a manual pilot coupon from a paper coupon")
    prepare_parser.add_argument("--betting-day", required=True, help="YYYY-MM-DD")
    prepare_parser.add_argument("--run-id", required=True, help="Run identifier")
    prepare_parser.add_argument("--base-dir", required=True, help="Base directory outside the repo")
    prepare_parser.add_argument("--pilot-dir", required=True, help="Pilot directory outside the repo")
    prepare_parser.add_argument("--ledger-path", required=True, help="Manual pilot ledger JSONL path")
    prepare_parser.add_argument("--paper-ledger-path", required=True, help="Paper ledger JSONL path")
    prepare_parser.add_argument("--source-paper-coupon-id", required=True, help="Source paper coupon ID")
    prepare_parser.add_argument("--manual-bookmaker-name", required=True, help="Human operator name for manual placement")
    prepare_parser.add_argument("--stake-units", required=True, type=_decimal_arg, help="Manual stake units")
    prepare_parser.add_argument("--max-stake-units-per-coupon", required=True, type=_decimal_arg, help="Max stake per coupon")
    prepare_parser.add_argument("--max-daily-risk-units", required=True, type=_decimal_arg, help="Max total daily risk")
    prepare_parser.add_argument("--daily-stop-loss-units", required=True, type=_decimal_arg, help="Daily stop-loss limit")
    prepare_parser.add_argument("--legal-operator-attested", action="store_true", help="Confirm legal operator use")
    prepare_parser.add_argument("--age-kyc-attested", action="store_true", help="Confirm age/KYC attestation")
    prepare_parser.add_argument("--responsible-gambling-limits-attested", action="store_true", help="Confirm responsible gambling limits")
    prepare_parser.add_argument("--manual-click-attested", action="store_true", help="Confirm manual human click placement")
    prepare_parser.add_argument("--report-path", required=True, help="JSON report output path")
    _add_hidden_forbidden_flags(prepare_parser)
    prepare_parser.set_defaults(func=_prepare_command)

    record_parser = subparsers.add_parser("record-placement", help="Record a manual human placement")
    record_parser.add_argument("--betting-day", required=True, help="YYYY-MM-DD")
    record_parser.add_argument("--run-id", required=True, help="Run identifier")
    record_parser.add_argument("--pilot-dir", required=True, help="Pilot directory outside the repo")
    record_parser.add_argument("--ledger-path", required=True, help="Manual pilot ledger JSONL path")
    record_parser.add_argument("--manual-pilot-coupon-id", required=True, help="Prepared manual pilot coupon ID")
    record_parser.add_argument("--manual-bookmaker-name", required=True, help="Human operator name for manual placement")
    record_parser.add_argument("--manual-bookmaker-ticket-id", required=True, help="Bookmaker ticket ID recorded by the human")
    record_parser.add_argument("--manual-placed-at-utc", required=True, help="Manual placement UTC ISO timestamp")
    record_parser.add_argument("--manual-click-attested", action="store_true", help="Confirm manual human click placement")
    record_parser.add_argument("--report-path", required=True, help="JSON report output path")
    _add_hidden_forbidden_flags(record_parser)
    record_parser.set_defaults(func=_record_placement_command)

    settle_parser = subparsers.add_parser("settle", help="Settle a recorded manual pilot coupon")
    settle_parser.add_argument("--betting-day", required=True, help="YYYY-MM-DD")
    settle_parser.add_argument("--run-id", required=True, help="Run identifier")
    settle_parser.add_argument("--pilot-dir", required=True, help="Pilot directory outside the repo")
    settle_parser.add_argument("--ledger-path", required=True, help="Manual pilot ledger JSONL path")
    settle_parser.add_argument("--manual-pilot-coupon-id", required=True, help="Prepared manual pilot coupon ID")
    settle_parser.add_argument("--result", required=True, choices=["WIN", "LOSS", "VOID"], help="Settlement result")
    settle_parser.add_argument("--report-path", required=True, help="JSON report output path")
    _add_hidden_forbidden_flags(settle_parser)
    settle_parser.set_defaults(func=_settle_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
