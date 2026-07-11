"""Tests for mock odds production safety."""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from bet.pipeline.rich_coupon_package import (
    RichCouponPackageReport,
    generate_package_markdown,
    BetBuilderPackage,
    build_rich_coupon_package,
)


def test_mock_odds_production_safety_blocks():
    # Setup mock environment variable
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        packages, report = build_rich_coupon_package(
            betting_day="2026-07-11",
            session_id="session-test",
            session_ledger_path=Path("/tmp/mock_ledger.jsonl"),
            operator_name="Superbet",
        )
        assert report.classification == "TEST_ONLY_MOCK_ODDS"
        assert report.can_place_bet_now is False
        assert report.safe_user_action == "DO_NOT_PLACE_BET"
        assert report.bettable_count == 0
        assert report.ready_for_manual_operator_quote_review is False
        assert report.ready_for_production_coupon_building is False
        assert report.status == "FAIL"
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)


def test_mock_odds_markdown_title():
    pkg = BetBuilderPackage(
        package_id="test-pkg",
        betting_day="2026-07-11",
        session_id="session-test",
        package_type="ANALYTICAL_ONLY",
        event="Test Match",
        legs=[],
        combined_odds_decimal=Decimal("2.10"),
        stake_units=Decimal("1.0"),
        max_daily_risk_units=Decimal("5.0"),
        value_summary="Mock test",
        risk_summary="Mock test risk",
        correlation_risk="LOW",
        operator_screen_checklist=[],
        human_action_required=True,
        ready_for_human_manual_placement=True,
        ready_for_automated_bet_placement=False,
        ready_for_production_execution=False,
        blockers=[]
    )
    report = RichCouponPackageReport(
        task_id="PIPELINE_RICH_BET_BUILDER_PACKAGE_A",
        status="FAIL",
        betting_day="2026-07-11",
        session_id="session-test",
        candidate_count=0,
        no_bet_count=0,
        bettable_count=0,
        package_count=0,
        recommended_package_id=None,
        package_json_path=None,
        package_markdown_path=None,
        bet_builder_compatibility_verdict="PASS",
        market_completeness_verdict="PASS",
        multi_stat_package_verdict="PASS",
        correlation_review_verdict="PASS",
        operator_screen_required_verdict="PASS",
        no_automated_placement_verdict="PASS",
        ready_for_production_coupon_building=False,
        human_manual_placement_required=False,
        ready_for_automated_bet_placement=False,
        ready_for_production_execution=False,
        blockers=[],
        classification="TEST_ONLY_MOCK_ODDS",
        can_place_bet_now=False,
        safe_user_action="DO_NOT_PLACE_BET"
    )
    markdown = generate_package_markdown(pkg, report)
    assert "TEST/SMOKE ONLY" in markdown
    assert "MOCK ODDS ACTIVE" in markdown
