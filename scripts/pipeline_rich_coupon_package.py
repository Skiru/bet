#!/usr/bin/env python3
"""CLI utility to build rich manual coupon packages from daily session ledgers."""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from bet.pipeline.rich_coupon_package import (
    build_rich_coupon_package,
    generate_package_markdown,
    _serialize_jsonable,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Rich Coupon Package Builder CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-from-session", help="Build rich package from session ledger")
    build_parser.add_argument("--betting-day", required=True, help="Betting day, e.g. 2026-06-28")
    build_parser.add_argument("--session-id", required=True, help="Session / Run ID")
    build_parser.add_argument("--session-ledger-path", required=True, help="Path to daily_session_ledger.jsonl")
    build_parser.add_argument("--output-dir", required=True, help="Directory to save rich package artifacts")
    build_parser.add_argument("--operator-name", required=True, help="Target bookmaker name, e.g. Betclic")
    build_parser.add_argument("--stake-units", type=float, default=1.0, help="Stake units per coupon")
    build_parser.add_argument("--max-daily-risk-units", type=float, default=1.0, help="Max daily risk units")
    build_parser.add_argument("--prefer-bet-builder", action="store_true", default=True, help="Prefer Bet Builder for same-event legs")
    build_parser.add_argument("--max-legs", type=int, default=10, help="Maximum number of legs per package")
    build_parser.add_argument("--report-path", required=True, help="Path to write RichCouponPackageReport JSON")

    args = parser.parse_args()

    if args.command == "build-from-session":
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = Path(args.report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)

        stake = Decimal(str(args.stake_units))
        max_risk = Decimal(str(args.max_daily_risk_units))

        # Build package
        packages, report = build_rich_coupon_package(
            betting_day=args.betting_day,
            session_id=args.session_id,
            session_ledger_path=Path(args.session_ledger_path),
            operator_name=args.operator_name,
            stake_units=stake,
            max_daily_risk_units=max_risk,
            prefer_bet_builder=args.prefer_bet_builder,
            max_legs=args.max_legs,
        )

        recommended_pkg = packages[0] if packages else None

        package_json_p = None
        package_md_p = None

        if recommended_pkg:
            package_json_p = output_dir / f"{args.betting_day}_rich_coupon_package.json"
            package_md_p = output_dir / f"{args.betting_day}_rich_coupon_package.md"

            with open(package_json_p, "w", encoding="utf-8") as f:
                json.dump(recommended_pkg.to_jsonable(), f, indent=2, ensure_ascii=False)

            markdown_content = generate_package_markdown(recommended_pkg, report)
            with open(package_md_p, "w", encoding="utf-8") as f:
                f.write(markdown_content)

        final_report_data = {
            "task_id": report.task_id,
            "status": report.status,
            "betting_day": report.betting_day,
            "session_id": report.session_id,
            "candidate_count": report.candidate_count,
            "no_bet_count": report.no_bet_count,
            "bettable_count": report.bettable_count,
            "package_count": report.package_count,
            "recommended_package_id": report.recommended_package_id,
            "package_json_path": str(package_json_p) if package_json_p else None,
            "package_markdown_path": str(package_md_p) if package_md_p else None,
            "bet_builder_compatibility_verdict": report.bet_builder_compatibility_verdict,
            "market_completeness_verdict": report.market_completeness_verdict,
            "multi_stat_package_verdict": report.multi_stat_package_verdict,
            "correlation_review_verdict": report.correlation_review_verdict,
            "operator_screen_required_verdict": report.operator_screen_required_verdict,
            "no_automated_placement_verdict": report.no_automated_placement_verdict,
            "ready_for_production_coupon_building": report.ready_for_production_coupon_building,
            "human_manual_placement_required": report.human_manual_placement_required,
            "ready_for_automated_bet_placement": report.ready_for_automated_bet_placement,
            "ready_for_production_execution": report.ready_for_production_execution,
            "blockers": report.blockers,
            "analytical_suggestion_count": report.analytical_suggestion_count,
            "ready_for_manual_operator_quote_review": report.ready_for_manual_operator_quote_review,
            "classification": report.classification,
            "can_place_bet_now": report.can_place_bet_now,
            "safe_user_action": report.safe_user_action,
            "positive_ev_with_operator_odds_count": report.positive_ev_with_operator_odds_count,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(_serialize_jsonable(final_report_data), f, indent=2, ensure_ascii=False)

        import os
        is_mock = os.environ.get("BET_MOCK_ODDS") or os.environ.get("BET_PIPELINE_SKIP_FETCH") or (report.classification == "TEST_ONLY_MOCK_ODDS")

        if is_mock:
            print("STATUS=TEST_ONLY_MOCK_ODDS")
            return 0
        elif recommended_pkg and recommended_pkg.package_type == "ANALYTICAL_ONLY" and not report.blockers:
            print("STATUS=READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW")
            return 0
        elif recommended_pkg and recommended_pkg.package_type != "NO_BET_PACKAGE" and not report.blockers:
            print("STATUS=READY_FOR_HUMAN_REVIEW")
            return 0
        else:
            print("STATUS=NO_BET_PACKAGE")
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
