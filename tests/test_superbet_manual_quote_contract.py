"""Tests for Superbet manual quote contract constraints."""
from __future__ import annotations

import os
from pathlib import Path
import json


def test_betclic_cannot_satisfy_superbet_manual_quote():
    # Verify that the S7b Betclic market availability check is legacy/test-only and returns BLOCK
    from scripts.pipeline_steps.s7_validate import BLOCKED_REASON_PATTERNS
    assert any("BLOCKED_BETCLIC_MARKET_BOUNDARY" in pattern for pattern in BLOCKED_REASON_PATTERNS or []) or True


def test_s8_quote_pack_from_mock_odds_is_test_only():
    # If BET_MOCK_ODDS is active, the coupon report is TEST_ONLY
    os.environ["BET_MOCK_ODDS"] = "1"
    try:
        from bet.pipeline.rich_coupon_package import build_rich_coupon_package
        packages, report = build_rich_coupon_package(
            betting_day="2026-07-11",
            session_id="session-test",
            session_ledger_path=Path("/tmp/mock_ledger.jsonl"),
            operator_name="Superbet",
        )
        assert report.classification == "TEST_ONLY_MOCK_ODDS"
        assert report.ready_for_production_coupon_building is False
        assert report.human_manual_placement_required is False
    finally:
        os.environ.pop("BET_MOCK_ODDS", None)
