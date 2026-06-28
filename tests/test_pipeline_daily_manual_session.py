"""Unit and integration tests for Daily Manual Session Control."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import pytest

from bet.pipeline.daily_manual_session import (
    DailyManualSessionConfig,
    review_s8_candidate_for_manual_session,
    generate_daily_session_report,
    append_ledger_event,
    load_session_state,
)


def _config(tmp_path: Path, **overrides: object) -> DailyManualSessionConfig:
    day = "2026-06-28"
    session_id = "run_20260628_manual_a"
    base_dir = tmp_path / "manual-base"
    session_dir = base_dir / day / session_id
    values = {
        "base_dir": base_dir,
        "betting_day": day,
        "session_id": session_id,
        "session_dir": session_dir,
        "session_ledger_path": session_dir / "daily_session_ledger.jsonl",
        "max_session_coupons": 1,
        "max_stake_units_per_coupon": Decimal("1"),
        "max_daily_risk_units": Decimal("1"),
        "daily_stop_loss_units": Decimal("1"),
        "kill_switch": False,
        "legal_operator_attested": True,
        "age_kyc_attested": True,
        "responsible_gambling_limits_attested": True,
    }
    values.update(overrides)
    return DailyManualSessionConfig(**values)


def _write_draft(path: Path, drafts: list[dict[str, Any]], **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "S8_COUPON_DRAFTS",
        "betting_day": "2026-06-28",
        "run_id": "run_20260628_manual_a",
        "requires_human_gate": True,
        "ready_for_human_gate": True,
        "ready_for_production_execution": False,
        "production_selectable": False,
        "production_coupon_write": False,
        "executable_coupon": False,
        "betclic_execution_enabled": False,
        "drafts": drafts,
    }
    payload.update(overrides)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _write_s9(path: Path, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "artifact_type": "HUMAN_GATE",
        "step_id": "S9",
        "status": "HUMAN_APPROVED",
        "manual_review": {
            "reviewed_by_user": "operator-user",
            "reviewed_at_utc": "2026-06-28T12:00:00Z",
            "betclic_manual_verification": True,
            "coupon_draft_path": "/tmp/dummy_s8.json",
            "coupon_draft_sha256": "dummy_sha",
        }
    }
    payload.update(overrides)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def test_daily_session_rejects_missing_aces_line(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Player B Aces O/U",
            "pick": "UNDER",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "line": "MISSING",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert len(reviews) == 1
    assert reviews[0].review_status == "NO_BET"
    assert "missing exact O/U line" in reviews[0].decision_reason


def test_daily_session_rejects_bare_under_without_line(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Player B Aces O/U",
            "pick": "UNDER",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert len(reviews) == 1
    assert reviews[0].review_status == "NO_BET"
    assert "missing exact O/U line" in reviews[0].decision_reason


def test_daily_session_rejects_fixture_selection_ids(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "selection-win",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "contains fixture/test labels" in reviews[0].decision_reason


def test_daily_session_accepts_complete_player_b_aces_under_line(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-real-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "player_b": "Luca Potenza",
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "BETTABLE_MANUAL_ONLY"


def test_daily_session_rejects_ambiguous_player_b_identity(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    # Player B-specific market, but no player_b field, and event cannot be parsed to get Player B
    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-real-1",
            "event": "Donald, M. W. vs ?",
            "market": "Player B Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "missing player_b for player-specific market" in reviews[0].decision_reason


def test_daily_session_rejects_missing_odds_timestamp(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "stake_units": 1.0,
            "player_b": "Luca Potenza",
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "missing odds captured at utc" in reviews[0].decision_reason


def test_daily_session_rejects_odds_decimal_lte_one(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 0.9,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "player_b": "Luca Potenza",
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "odds decimal must be > 1" in reviews[0].decision_reason


def test_daily_session_rejects_production_ready_artifact(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "player_b": "Luca Potenza",
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data, ready_for_production_execution=True)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "artifact has ready_for_production_execution=true" in reviews[0].decision_reason


def test_daily_session_rejects_betclic_execution_enabled_artifact(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Luca Potenza Player Aces O/U",
            "pick": "UNDER 2.5",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "stake_units": 1.0,
            "player_b": "Luca Potenza",
            "line": "2.5",
        }]
    }]
    _write_draft(draft_path, draft_data, betclic_execution_enabled=True)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "artifact has betclic_execution_enabled=true" in reviews[0].decision_reason


def test_daily_session_budget_guard_blocks_over_risk(tmp_path: Path):
    config = _config(tmp_path, max_daily_risk_units=Decimal("1.5"))

    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="candidate_reviewed",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"candidate_id": "cand-1", "review_status": "BETTABLE_MANUAL_ONLY"},
    )
    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="manual_coupon_prepared",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"manual_pilot_coupon_id": "coupon-1", "stake_units": "2.0"},
    )

    report = generate_daily_session_report(config)
    assert report.budget_guard_verdict == "FAIL"
    assert "exceeds max daily risk units" in "".join(report.blockers)


def test_daily_session_stop_loss_blocks_after_loss(tmp_path: Path):
    config = _config(tmp_path, daily_stop_loss_units=Decimal("1.0"))

    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="candidate_reviewed",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"candidate_id": "cand-1", "review_status": "BETTABLE_MANUAL_ONLY"},
    )
    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="manual_coupon_prepared",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"manual_pilot_coupon_id": "coupon-1", "stake_units": "1.0"},
    )
    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="manual_coupon_settled",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"manual_pilot_coupon_id": "coupon-1", "pnl_units": "-1.5"},
    )

    report = generate_daily_session_report(config)
    assert report.stop_loss_guard_verdict == "FAIL"
    assert "exceeds daily stop loss units" in "".join(report.blockers)


def test_daily_session_kill_switch_blocks_prepare(tmp_path: Path):
    config = _config(tmp_path, kill_switch=True)
    report = generate_daily_session_report(config)
    assert report.kill_switch_verdict == "FAIL"
    assert "kill_switch is active" in report.blockers


def test_daily_session_ledger_jsonl_schema_valid(tmp_path: Path):
    config = _config(tmp_path)
    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="candidate_reviewed",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"candidate_id": "cand-1", "review_status": "BETTABLE_MANUAL_ONLY"},
    )
    state = load_session_state(config.session_ledger_path)
    assert "cand-1" in state["reviewed"]


def test_daily_session_prepare_first_bettable_stops_before_placement(tmp_path: Path):
    config = _config(tmp_path)
    # Prepared coupon state status is PREPARED, no placement info should be present
    append_ledger_event(
        ledger_path=config.session_ledger_path,
        event_type="candidate_reviewed",
        betting_day=config.betting_day,
        session_id=config.session_id,
        payload={"candidate_id": "cand-1", "review_status": "BETTABLE_MANUAL_ONLY", "event_id": "evt-1", "stake_units": "1.0", "odds_decimal": "2.0"},
    )
    state = load_session_state(config.session_ledger_path)
    assert len(state["prepared"]) == 0


def test_daily_session_report_never_marks_production_ready(tmp_path: Path):
    config = _config(tmp_path)
    report = generate_daily_session_report(config)
    assert report.ready_for_production_execution is False


def test_daily_session_bad_donald_potenza_pick_returns_no_bet(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Donald, M. W. vs Potenza, Luca",
            "market": "Player B Aces O/U",
            "pick": "UNDER",
            "odds_decimal": 2.1,
            "odds_captured_at_utc": "2026-06-28T08:00:00Z",
            "line": "MISSING",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Betclic",
    )
    assert reviews[0].review_status == "NO_BET"
    assert "missing exact O/U line" in reviews[0].decision_reason


def test_regression_pipeline_daily_manual_session(tmp_path: Path):
    config = _config(tmp_path)
    assert config.betting_day == "2026-06-28"
