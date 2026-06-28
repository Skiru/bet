#!/usr/bin/env python3
"""CLI for production-grade Daily Manual Session Control."""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bet.pipeline.daily_manual_session import (  # noqa: E402
    DailyManualSessionConfig,
    review_s8_candidate_for_manual_session,
    append_ledger_event,
    load_session_state,
    generate_daily_session_report,
)
from bet.pipeline.run_evidence import write_json_atomic, utc_now_iso  # noqa: E402


def _decimal_arg(value: str) -> Decimal:
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal value: {value}") from exc


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Daily Manual Session Control")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common options for configuration
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--betting-day", required=True, help="Betting day YYYY-MM-DD")
    common.add_argument("--session-id", required=True, help="Session unique ID")
    common.add_argument("--base-dir", required=True, type=Path, help="Base directory")
    common.add_argument("--session-dir", required=True, type=Path, help="Session directory")
    common.add_argument("--session-ledger-path", required=True, type=Path, help="Session ledger JSONL file")
    common.add_argument("--max-session-coupons", type=int, default=1, help="Max prepared coupons in session")
    common.add_argument("--max-stake-units-per-coupon", type=_decimal_arg, default=Decimal("1"), help="Max stake per coupon")
    common.add_argument("--max-daily-risk-units", type=_decimal_arg, default=Decimal("1"), help="Max daily risk units")
    common.add_argument("--daily-stop-loss-units", type=_decimal_arg, default=Decimal("1"), help="Daily stop loss limit")
    common.add_argument("--legal-operator-attested", action="store_true", help="Attest legal operator usage")
    common.add_argument("--age-kyc-attested", action="store_true", help="Attest age / KYC verification")
    common.add_argument("--responsible-gambling-limits-attested", action="store_true", help="Attest responsible gambling limits set")
    common.add_argument("--report-path", required=True, type=Path, help="Session report JSON path")
    common.add_argument("--kill-switch", action="store_true", help="Enable emergency stop")
    common.add_argument("--allow-automated-bookmaker-placement", action="store_true", help=argparse.SUPPRESS)
    common.add_argument("--allow-betclic-api", action="store_true", help=argparse.SUPPRESS)
    common.add_argument("--allow-browser-automation", action="store_true", help=argparse.SUPPRESS)
    common.add_argument("--allow-repo-protected-writes", action="store_true", help=argparse.SUPPRESS)

    # 1. review-draft
    p_review = subparsers.add_parser("review-draft", parents=[common], help="Review S8 candidates")
    p_review.add_argument("--s8-coupon-draft-path", required=True, type=Path, help="S8 coupon draft JSON path")
    p_review.add_argument("--s8-coupon-draft-sha256", required=True, help="S8 coupon draft SHA-256")
    p_review.add_argument("--s9-artifact-path", type=Path, help="S9 artifact JSON path")
    p_review.add_argument("--s9-artifact-sha256", help="S9 artifact SHA-256")
    p_review.add_argument("--operator-name", required=True, help="Bookmaker operator name")

    # 2. prepare-first-bettable
    subparsers.add_parser("prepare-first-bettable", parents=[common], help="Prepare the first bettable candidate")

    # 3. close-session
    p_close = subparsers.add_parser("close-session", help="Close the daily manual session")
    p_close.add_argument("--session-ledger-path", required=True, type=Path, help="Session ledger JSONL file")
    p_close.add_argument("--report-path", required=True, type=Path, help="Session report JSON path")

    return parser.parse_args()


def _get_config(args: argparse.Namespace) -> DailyManualSessionConfig:
    return DailyManualSessionConfig(
        base_dir=Path(args.base_dir),
        betting_day=args.betting_day,
        session_id=args.session_id,
        session_dir=Path(args.session_dir),
        session_ledger_path=Path(args.session_ledger_path),
        max_session_coupons=args.max_session_coupons,
        max_stake_units_per_coupon=args.max_stake_units_per_coupon,
        max_daily_risk_units=args.max_daily_risk_units,
        daily_stop_loss_units=args.daily_stop_loss_units,
        kill_switch=args.kill_switch,
        legal_operator_attested=args.legal_operator_attested,
        age_kyc_attested=args.age_kyc_attested,
        responsible_gambling_limits_attested=args.responsible_gambling_limits_attested,
        allow_automated_bookmaker_placement=args.allow_automated_bookmaker_placement,
        allow_betclic_api=args.allow_betclic_api,
        allow_browser_automation=args.allow_browser_automation,
        allow_repo_protected_writes=args.allow_repo_protected_writes,
    )


def main() -> int:
    args = _parse_args()

    if args.command == "review-draft":
        config = _get_config(args)
        s9_path = Path(args.s9_artifact_path) if args.s9_artifact_path else None
        s9_sha = args.s9_artifact_sha256 if args.s9_artifact_sha256 else None

        try:
            reviews = review_s8_candidate_for_manual_session(
                config=config,
                s8_coupon_draft_path=Path(args.s8_coupon_draft_path),
                s8_coupon_draft_sha256=args.s8_coupon_draft_sha256,
                s9_artifact_path=s9_path,
                s9_artifact_sha256=s9_sha,
                operator_name=args.operator_name,
            )

            # Record to session ledger
            for rev in reviews:
                event_type = "candidate_reviewed" if rev.review_status == "BETTABLE_MANUAL_ONLY" else "candidate_rejected_no_bet"
                append_ledger_event(
                    ledger_path=config.session_ledger_path,
                    event_type=event_type,
                    betting_day=config.betting_day,
                    session_id=config.session_id,
                    payload=rev.to_jsonable(),
                )

            # Generate final report
            report = generate_daily_session_report(config)
            write_json_atomic(Path(args.report_path), report.to_jsonable())

            # Print single candidate smoke test output format if 1 candidate reviewed
            if len(reviews) == 1:
                rev = reviews[0]
                print(f"STATUS={rev.review_status}")
                print(f"DECISION_REASON={rev.decision_reason}")
                print(f"READY_FOR_HUMAN_MANUAL_PLACEMENT={'true' if rev.review_status == 'BETTABLE_MANUAL_ONLY' else 'false'}")
                print(f"READY_FOR_PRODUCTION_EXECUTION=false")
            else:
                print(f"STATUS={report.status}")
                print(f"READY_FOR_MANUAL_SESSION={'true' if report.ready_for_manual_session else 'false'}")
                print(f"READY_FOR_PRODUCTION_EXECUTION=false")

            return 0 if report.status == "PASS" else 1

        except Exception as exc:
            print(f"STATUS=FAIL", file=sys.stderr)
            print(f"ERROR={exc}", file=sys.stderr)
            return 1

    elif args.command == "prepare-first-bettable":
        config = _get_config(args)
        try:
            state = load_session_state(config.session_ledger_path)
            # Find first candidate reviewed as BETTABLE_MANUAL_ONLY
            bettable = None
            for c_id, cand in state["reviewed"].items():
                if cand.get("review_status") == "BETTABLE_MANUAL_ONLY":
                    # Check if already prepared
                    # Simple heuristic: is candidate_id or selection_id in prepared
                    already_prepared = False
                    for prep in state["prepared"].values():
                        if prep.get("source_paper_coupon_id") == c_id:
                            already_prepared = True
                            break
                    if not already_prepared:
                        bettable = cand
                        break

            if bettable is None:
                print("STATUS=FAIL", file=sys.stderr)
                print("ERROR=zero bettable candidates", file=sys.stderr)
                return 1

            prepared_count = len(state["prepared"])
            if prepared_count >= config.max_session_coupons:
                print("STATUS=FAIL", file=sys.stderr)
                print("ERROR=would exceed max prepared coupons limit", file=sys.stderr)
                return 1

            if config.kill_switch:
                print("STATUS=FAIL", file=sys.stderr)
                print("ERROR=kill_switch is active", file=sys.stderr)
                return 1

            # Prepare coupon
            coupon_id = f"{config.session_id}:manual:{bettable.get('event_id')}:{bettable.get('candidate_id')}"
            prepared_coupon = {
                "manual_pilot_coupon_id": coupon_id,
                "betting_day": config.betting_day,
                "run_id": config.session_id,
                "source_paper_coupon_id": bettable.get("candidate_id"),
                "source_s8_coupon_draft_path": bettable.get("source_s8_coupon_draft_path"),
                "source_s8_coupon_draft_sha256": bettable.get("source_s8_coupon_draft_sha256"),
                "source_s9_artifact_path": bettable.get("source_s9_artifact_path"),
                "source_s9_artifact_sha256": bettable.get("source_s9_artifact_sha256"),
                "source_paper_ledger_path": str(config.session_ledger_path),
                "selection_id": bettable.get("candidate_id").split(":")[-1],
                "event_id": bettable.get("event_id"),
                "market": bettable.get("market"),
                "pick": bettable.get("pick"),
                "odds_decimal": bettable.get("odds_decimal"),
                "stake_units": bettable.get("stake_units"),
                "expected_payout_units": str(Decimal(str(bettable.get("stake_units"))) * Decimal(str(bettable.get("odds_decimal")))),
                "created_at_utc": utc_now_iso(),
                "manual_bookmaker_name": bettable.get("operator_name"),
                "manual_bookmaker_ticket_id": "",
                "manual_placed_at_utc": "",
                "status": "PREPARED",
                "pnl_units": "0",
            }

            append_ledger_event(
                ledger_path=config.session_ledger_path,
                event_type="manual_coupon_prepared",
                betting_day=config.betting_day,
                session_id=config.session_id,
                payload=prepared_coupon,
            )

            # Generate final report
            report = generate_daily_session_report(config)
            write_json_atomic(Path(args.report_path), report.to_jsonable())

            print("STATUS=PASS")
            print(f"MANUAL_PILOT_COUPON_ID={coupon_id}")
            return 0

        except Exception as exc:
            print("STATUS=FAIL", file=sys.stderr)
            print(f"ERROR={exc}", file=sys.stderr)
            return 1

    elif args.command == "close-session":
        ledger_path = Path(args.session_ledger_path)
        report_path = Path(args.report_path)
        try:
            state = load_session_state(ledger_path)

            reviewed = len(state["reviewed"])
            rejected = sum(1 for c in state["reviewed"].values() if c.get("review_status") == "NO_BET")
            prepared = len(state["prepared"])
            placed = len(state["placed"])
            settled = len(state["settled"])
            pending = prepared - settled

            # Log close event
            # Retrieve day/id from first event or placeholder
            betting_day = "UNKNOWN"
            session_id = "UNKNOWN"
            for c in state["reviewed"].values():
                betting_day = c.get("betting_day")
                session_id = c.get("session_id")
                break

            append_ledger_event(
                ledger_path=ledger_path,
                event_type="session_closed",
                betting_day=betting_day,
                session_id=session_id,
                payload={
                    "reviewed_count": reviewed,
                    "rejected_count": rejected,
                    "prepared_count": prepared,
                    "placed_count": placed,
                    "settled_count": settled,
                    "pending_count": pending,
                    "closed_at_utc": utc_now_iso(),
                },
            )

            print("Daily Manual Session Summary:")
            print(f"Reviewed: {reviewed}")
            print(f"Rejected: {rejected}")
            print(f"Prepared: {prepared}")
            print(f"Placed:   {placed}")
            print(f"Settled:  {settled}")
            print(f"Pending:  {pending}")
            return 0

        except Exception as exc:
            print(f"STATUS=FAIL", file=sys.stderr)
            print(f"ERROR={exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
