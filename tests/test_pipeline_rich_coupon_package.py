"""Unit and regression tests for the rich coupon package builder system."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import pytest

from bet.pipeline.rich_coupon_package import (
    build_rich_coupon_package,
    generate_package_markdown,
    CouponLeg,
    BetBuilderPackage,
    RichCouponPackageReport,
)


def _write_ledger_event(path: Path, event_type: str, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "schema_version": 1,
        "event_type": event_type,
        "recorded_at_utc": "2026-06-28T12:00:00Z",
        "betting_day": "2026-06-28",
        "session_id": "session-1",
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _valid_candidate(candidate_id: str, **overrides) -> dict[str, Any]:
    cand = {
        "candidate_id": candidate_id,
        "review_status": "BETTABLE_MANUAL_ONLY",
        "event": "Donald, M. W. vs Potenza, Luca",
        "event_id": "evt-1",
        "player_a": "Donald, M. W.",
        "player_b": "Potenza, Luca",
        "market": "Luca Potenza Player Aces O/U",
        "pick": "UNDER 2.5",
        "line": "2.5",
        "odds_decimal": "2.10",
        "odds_captured_at_utc": "2026-06-28T08:00:00Z",
        "operator_name": "Betclic",
        "stake_units": "1.0",
        "source_s8_coupon_draft_path": "/tmp/s8_draft.json",
        "source_s8_coupon_draft_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        "source_s9_artifact_path": "/tmp/s9_gate.json",
        "source_s9_artifact_sha256": "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        "hydration_status": "HYDRATED",
        "promotion_status": "ANALYZABLE",
        "promotion_safe_model_probability": True,
        "ready_for_manual_operator_quote_review": True,
    }
    cand.update(overrides)
    return cand


def test_package_rejects_no_bet_only_session(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_rejected_no_bet", _valid_candidate("c-1", review_status="NO_BET"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].package_type == "NO_BET_PACKAGE"
    assert report.status == "FAIL"


def test_package_builds_single_leg_package_when_one_bettable_candidate(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].package_type == "SINGLE"
    assert report.status == "PASS"
    assert len(packages[0].legs) == 1


def test_package_builds_bet_builder_when_two_same_event_legs_complete(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", market="Total Aces O/U", pick="OVER 6.5", line="6.5"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].package_type == "BET_BUILDER"
    assert len(packages[0].legs) == 2


def test_package_rejects_bet_builder_missing_line(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    # O/U market with line=MISSING
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", market="Total Aces O/U", pick="OVER", line="MISSING"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].package_type == "NO_BET_PACKAGE"
    assert "missing numeric line for O/U market" in packages[0].blockers


def test_package_rejects_fixture_leg(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-fixture"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].package_type == "NO_BET_PACKAGE"
    assert report.status == "FAIL"


def test_package_does_not_invent_combined_odds(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", market="Total Aces O/U", pick="OVER 6.5", line="6.5"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].combined_odds_decimal is None


def test_package_marks_operator_screen_combined_odds_required(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert len(packages) == 1
    assert packages[0].operator_screen_combined_odds_required is True


def test_package_includes_supporting_and_counter_stats_sections(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    # Provide custom stats
    stats = [{"metric": "Win rate", "value": "75%", "source": "ATP", "as_of": "2026-06-28"}]
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1", supporting_stats=stats, counter_stats=stats))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    leg = packages[0].legs[0]
    assert len(leg.supporting_stats) == 1
    assert leg.supporting_stats[0]["metric"] == "Win rate"
    assert len(leg.counter_stats) == 1
    assert leg.counter_stats[0]["source"] == "ATP"


def test_package_classifies_correlation_risk(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    # Highly correlated player + total market
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1", market="Luca Potenza Player Aces O/U"))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", market="Total Match Aces O/U", pick="OVER 6.5", line="6.5"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert packages[0].correlation_risk == "HIGH"


def test_package_human_checklist_required(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    checklist = packages[0].operator_screen_checklist
    assert len(checklist) > 0
    assert any("Verify local odds" in item for item in checklist)


def test_package_never_marks_automated_placement_ready(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    assert report.ready_for_automated_bet_placement is False
    assert report.ready_for_production_execution is False
    assert report.human_manual_placement_required is True


def test_package_markdown_contains_event_market_pick_line_odds_sources(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    
    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )
    
    md = generate_package_markdown(packages[0], report)
    assert "Donald, M. W. vs Potenza, Luca" in md
    assert "Luca Potenza Player Aces O/U" in md
    assert "UNDER 2.5" in md
    assert "Line: 2.5" in md
    assert "**Captured Odds**: 2.10" in md
    assert "/tmp/s8_draft.json" in md


def test_regression_daily_manual_session():
    # Import daily manual session and ensure it doesn't break
    from bet.pipeline.daily_manual_session import DailyManualSessionConfig
    cfg = DailyManualSessionConfig(
        base_dir=Path("/tmp"),
        betting_day="2026-06-28",
        session_id="run-1",
        session_dir=Path("/tmp/session"),
        session_ledger_path=Path("/tmp/ledger.jsonl")
    )
    assert cfg.betting_day == "2026-06-28"


def test_regression_manual_low_stake_pilot():
    # Import manual pilot config and verify fields
    from bet.pipeline.manual_low_stake_pilot import ManualLowStakePilotConfig
    cfg = ManualLowStakePilotConfig(
        base_dir=Path("/tmp"),
        betting_day="2026-06-28",
        run_id="run-1",
        pilot_dir=Path("/tmp/pilot"),
        ledger_path=Path("/tmp/ledger.csv")
    )
    assert cfg.run_id == "run-1"


def test_regression_paper_trading_readiness():
    # Import paper trading functions to ensure imports are stable
    from bet.pipeline.paper_trading import load_latest_paper_coupons
    # Verification of import
    assert load_latest_paper_coupons is not None


def test_rich_package_separates_analytical_suggestions_from_bettable_legs(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", review_status="PRICE_PENDING_OPERATOR_CHECK", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )

    assert len(packages) == 1
    assert len(packages[0].bettable_manual_legs) == 1
    assert len(packages[0].analytical_suggestions) == 1
    assert packages[0].analytical_suggestions[0]["status"] == "PRICE_PENDING_OPERATOR_CHECK"


def test_analytical_only_package_not_ready_for_manual_placement(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1", review_status="PRICE_PENDING_OPERATOR_CHECK", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )

    assert len(packages) == 1
    assert packages[0].package_type == "ANALYTICAL_ONLY"
    assert packages[0].ready_for_human_manual_placement is False
    assert packages[0].ready_for_manual_operator_quote_review is True


def test_no_automated_placement_readiness(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1"))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )

    assert packages[0].ready_for_automated_bet_placement is False
    assert report.ready_for_automated_bet_placement is False


def test_package_has_separate_analytical_and_bettable_sections(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1", review_status="BETTABLE_MANUAL_ONLY"))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-2", review_status="PRICE_PENDING_OPERATOR_CHECK", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-3", review_status="PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-4", review_status="REJECTED_BY_PRICE", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-5", review_status="LINE_MISMATCH_REQUIRES_REMODEL", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )

    assert len(packages) == 1
    pkg = packages[0]
    
    assert len(pkg.bettable_manual_legs) == 1
    assert pkg.bettable_manual_legs[0]["candidate_id"] == "c-1"
    
    assert len(pkg.manual_quote_required_candidates) == 1
    assert pkg.manual_quote_required_candidates[0]["candidate_id"] == "c-2"
    
    assert len(pkg.price_acceptable_pending_evidence_review) == 1
    assert pkg.price_acceptable_pending_evidence_review[0]["candidate_id"] == "c-3"
    
    assert len(pkg.rejected_by_price) == 1
    assert pkg.rejected_by_price[0]["candidate_id"] == "c-4"
    
    assert len(pkg.line_mismatch_requires_remodel) == 1
    assert pkg.line_mismatch_requires_remodel[0]["candidate_id"] == "c-5"
    
    assert len(pkg.analytical_suggestions) == 4


def test_analytical_only_package_not_coupon_package(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-1", review_status="PRICE_PENDING_OPERATOR_CHECK", odds_decimal="0.0", odds_captured_at_utc="", model_probability=0.65))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Superbet",
    )

    assert len(packages) == 1
    assert packages[0].package_type == "ANALYTICAL_ONLY"
    assert packages[0].ready_for_human_manual_placement is False
    assert packages[0].ready_for_manual_operator_quote_review is True


def test_low_confidence_probability_label_is_visible_in_package(tmp_path: Path):
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_ledger_event(ledger_p, "candidate_reviewed", _valid_candidate("c-low", confidence_label="LOW"))

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Betclic",
    )

    markdown = generate_package_markdown(packages[0], report)

    assert packages[0].legs[0].confidence_label == "LOW"
    assert "**Confidence**: LOW" in markdown
