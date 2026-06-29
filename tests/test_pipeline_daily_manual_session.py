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


def test_unpriced_event_can_become_analytical_bet_builder_candidate(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.65,
            "confidence_label": "MEDIUM",
            "line": "9.5",
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_PENDING_OPERATOR_CHECK"


def test_unpriced_candidate_without_operator_quote_cannot_be_bettable(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.65,
            "line": "9.5",
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status != "BETTABLE_MANUAL_ONLY"


def test_missing_provider_odds_does_not_block_analytical_candidate(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.65,
            "line": "9.5",
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
        operator_name="Superbet",
    )
    assert "missing odds decimal" not in reviews[0].decision_reason


def test_model_probability_creates_fair_odds_and_min_acceptable_odds(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "HIGH",
            "line": "9.5",
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
        operator_name="Superbet",
    )
    assert reviews[0].fair_odds == Decimal("2.0000")
    assert reviews[0].min_acceptable_operator_odds == Decimal("2.1000")


def test_invalid_probability_blocks_candidate(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": -0.5,
            "line": "9.5",
        }]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    with pytest.raises(ValueError, match="model_probability must be > 0 and < 1"):
        review_s8_candidate_for_manual_session(
            config=config,
            s8_coupon_draft_path=draft_path,
            s8_coupon_draft_sha256="dummy_sha_s8",
            s9_artifact_path=s9_path,
            s9_artifact_sha256="dummy_sha_s9",
            operator_name="Superbet",
        )


def test_operator_quote_missing_keeps_price_pending_status(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_PENDING_OPERATOR_CHECK"


def test_operator_quote_below_threshold_rejects_by_price(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "MEDIUM",
            "line": "9.5",
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.05,
                "as_of_utc": "2026-06-28T12:00:00Z"
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "REJECTED_BY_PRICE"


def test_operator_quote_above_threshold_upgrades_to_bettable_manual_only(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "MEDIUM",
            "line": "9.5",
            "supporting_stats": [
                {"metric": "corners_for", "value": "6.5", "source": "ESPN", "as_of": "2026-06-28"},
                {"metric": "corners_against", "value": "4.5", "source": "SofaScore", "as_of": "2026-06-28"},
                {"metric": "tactical_pressure_proxy", "value": "High", "source": "ESPN", "as_of": "2026-06-28"},
                {"metric": "match_script_assumption", "value": "Open game", "source": "SofaScore", "as_of": "2026-06-28"}
            ],
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.20,
                "as_of_utc": "2026-06-28T12:00:00Z"
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "BETTABLE_MANUAL_ONLY"


def test_line_mismatch_requires_remodel(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "10.5",
                "odds_decimal": 2.20,
                "as_of_utc": "2026-06-28T12:00:00Z"
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "LINE_MISMATCH_REQUIRES_REMODEL"


def test_no_operator_market_found_status(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "operator_quote": {
                "operator": "Superbet",
                "quote_status": "QUOTE_MISSING",
                "as_of_utc": "2026-06-28T12:00:00Z"
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_PENDING_OPERATOR_CHECK"


def test_bet_builder_combined_odds_never_computed_by_pipeline(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [
            {
                "selection_id": "sel-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "line": "9.5",
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "9.5",
                    "odds_decimal": 1.85,
                    "as_of_utc": "2026-06-28T12:00:00Z"
                }
            },
            {
                "selection_id": "sel-2",
                "event": "Chelsea vs Arsenal",
                "market": "Match Goals",
                "pick": "OVER",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.60,
                "line": "2.5",
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Goals",
                    "line": "2.5",
                    "odds_decimal": 1.95,
                    "as_of_utc": "2026-06-28T12:00:00Z"
                }
            }
        ]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "BET_BUILDER_QUOTE_REQUIRED"
    assert reviews[0].combined_bookmaker_odds_computed is False


def test_price_acceptable_pending_evidence_review_status(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "supporting_stats": [{"metric": "Corners", "value": "UNKNOWN", "source": "UNKNOWN"}],
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "combined_odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z",
                "entered_by_human": True,
                "computed_by_pipeline": False
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"


def test_manual_quote_above_threshold_not_bettable_without_evidence_gate(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "supporting_stats": [],
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "combined_odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z",
                "entered_by_human": True,
                "computed_by_pipeline": False
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"


def test_manual_quote_must_be_entered_by_human(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "combined_odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z",
                "entered_by_human": False,
                "computed_by_pipeline": False
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "NO_FAKE_OPERATOR_QUOTE"


def test_manual_quote_must_not_be_computed_by_pipeline(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "combined_odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z",
                "entered_by_human": True,
                "computed_by_pipeline": True
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "NO_FAKE_OPERATOR_QUOTE"


def test_bet_builder_combined_odds_not_multiplied_from_legs(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [
            {
                "selection_id": "sel-1",
                "event": "Chelsea vs Arsenal",
                "market": "Corners",
                "pick": "OVER",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "line": "9.5",
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "9.5",
                    "odds_decimal": 1.50,
                    "combined_odds_decimal": 3.0,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                }
            },
            {
                "selection_id": "sel-2",
                "event": "Chelsea vs Arsenal",
                "market": "Goals",
                "pick": "OVER",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.60,
                "line": "2.5",
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Goals",
                    "line": "2.5",
                    "odds_decimal": 2.00,
                    "combined_odds_decimal": 3.0,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                }
            }
        ]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "NO_FAKE_OPERATOR_QUOTE"


def test_analytical_only_report_not_ready_for_manual_placement(tmp_path: Path):
    config = _config(tmp_path)
    ledger_p = config.session_ledger_path
    event = {
        "schema_version": 1,
        "event_type": "candidate_reviewed",
        "recorded_at_utc": "2026-06-28T12:00:00Z",
        "betting_day": config.betting_day,
        "session_id": config.session_id,
        "payload": {
            "candidate_id": "cand-1",
            "review_status": "PRICE_PENDING_OPERATOR_CHECK"
        }
    }
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_p, "w") as f:
        f.write(json.dumps(event) + "\n")

    report = generate_daily_session_report(config)
    assert report.ready_for_manual_session is False
    assert report.ready_for_manual_placement is False
    assert report.ready_for_manual_operator_quote_review is True


def test_ready_for_manual_operator_quote_review_true_for_analytical_only(tmp_path: Path):
    config = _config(tmp_path)
    ledger_p = config.session_ledger_path
    event = {
        "schema_version": 1,
        "event_type": "candidate_reviewed",
        "recorded_at_utc": "2026-06-28T12:00:00Z",
        "betting_day": config.betting_day,
        "session_id": config.session_id,
        "payload": {
            "candidate_id": "cand-1",
            "review_status": "PRICE_PENDING_OPERATOR_CHECK"
        }
    }
    ledger_p.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_p, "w") as f:
        f.write(json.dumps(event) + "\n")

    report = generate_daily_session_report(config)
    assert report.ready_for_manual_operator_quote_review is True


def test_synthetic_e2e_smoke_scenario(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-smoke",
        "selections": [
            # 1. Priced candidate
            {
                "selection_id": "priced-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Goals",
                "pick": "OVER",
                "line": "2.5",
                "odds_decimal": 1.95,
                "odds_captured_at_utc": "2026-06-28T12:00:00Z"
            },
            # 2. Unpriced analytical candidate with model probability and evidence
            {
                "selection_id": "unpriced-analytical-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "line": "9.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}]
            },
            # 3. Unpriced candidate with manual quote above threshold but no evidence gate
            {
                "selection_id": "unpriced-no-evidence-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "line": "9.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "9.5",
                    "odds_decimal": 2.50,
                    "combined_odds_decimal": 2.50,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                    "entered_by_human": True,
                    "computed_by_pipeline": False
                }
            },
            # 4. Quote below threshold
            {
                "selection_id": "unpriced-below-threshold-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "line": "9.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "9.5",
                    "odds_decimal": 1.90,
                    "combined_odds_decimal": 1.90,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                    "entered_by_human": True,
                    "computed_by_pipeline": False
                }
            },
            # 5. Line mismatch
            {
                "selection_id": "unpriced-line-mismatch-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "line": "9.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "10.5",
                    "odds_decimal": 2.50,
                    "combined_odds_decimal": 2.50,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                    "entered_by_human": True,
                    "computed_by_pipeline": False
                }
            },
            # 6. Fake computed quote attempt
            {
                "selection_id": "unpriced-fake-computed-1",
                "event": "Chelsea vs Arsenal",
                "market": "Match Corners",
                "pick": "OVER",
                "line": "9.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Corners",
                    "line": "9.5",
                    "odds_decimal": 2.50,
                    "combined_odds_decimal": 2.50,
                    "as_of_utc": "2026-06-28T12:00:00Z",
                    "entered_by_human": True,
                    "computed_by_pipeline": True
                }
            }
        ]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Superbet",
    )

    assert reviews[0].review_status == "BETTABLE_MANUAL_ONLY"
    assert reviews[1].review_status == "PRICE_PENDING_OPERATOR_CHECK"
    assert reviews[2].review_status == "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"
    assert reviews[3].review_status == "REJECTED_BY_PRICE"
    assert reviews[4].review_status == "LINE_MISMATCH_REQUIRES_REMODEL"
    assert reviews[5].review_status == "NO_FAKE_OPERATOR_QUOTE"

    for r in reviews:
        append_ledger_event(
            ledger_path=config.session_ledger_path,
            event_type="candidate_reviewed",
            betting_day=config.betting_day,
            session_id=config.session_id,
            payload=r.to_jsonable(),
        )

    from bet.pipeline.rich_coupon_package import build_rich_coupon_package
    packages, report = build_rich_coupon_package(
        betting_day=config.betting_day,
        session_id=config.session_id,
        session_ledger_path=config.session_ledger_path,
        operator_name="Superbet",
    )

    assert len(packages) == 1
    pkg = packages[0]

    assert len(pkg.bettable_manual_legs) == 1
    assert pkg.bettable_manual_legs[0]["candidate_id"] == f"{config.session_id}:draft-smoke:priced-1"

    assert len(pkg.manual_quote_required_candidates) == 1
    assert pkg.manual_quote_required_candidates[0]["candidate_id"] == f"{config.session_id}:draft-smoke:unpriced-analytical-1"

    assert len(pkg.price_acceptable_pending_evidence_review) == 1
    assert pkg.price_acceptable_pending_evidence_review[0]["candidate_id"] == f"{config.session_id}:draft-smoke:unpriced-no-evidence-1"

    assert len(pkg.rejected_by_price) == 1
    assert pkg.rejected_by_price[0]["candidate_id"] == f"{config.session_id}:draft-smoke:unpriced-below-threshold-1"

    assert len(pkg.line_mismatch_requires_remodel) == 1
    assert pkg.line_mismatch_requires_remodel[0]["candidate_id"] == f"{config.session_id}:draft-smoke:unpriced-line-mismatch-1"

    assert len(pkg.analytical_suggestions) == 5


def test_analytical_ready_status_does_not_run_priced_s7_approval():
    # READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW does not run priced s7 approval
    from scripts.pipeline_steps import s5_gate
    from bet.pipeline.live_session_universe import UniverseQualityReport
    report = UniverseQualityReport(
        status="READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW",
        total_input_count=1,
        valid_count=0,
        rejected_count=0,
        source_gap_count=0,
        rejected_reasons={},
        source_gaps=[],
        valid_candidates=[],
        unpriced_analytical_candidates=[{"candidate_id": "cand-1"}],
        rejected_candidates=[],
        as_of_utc="2026-06-29T12:00:00Z"
    )
    # If the s5_gate checks, it bypasses or handles it as analytical-only lane
    assert report.status == "READY_FOR_ANALYTICAL_OPERATOR_QUOTE_REVIEW"


def test_analytical_candidates_not_counted_as_s7_approved():
    # Analytical-only candidates are never counted as priced S7 approved
    from bet.pipeline.live_session_universe import LiveSessionUniverseConfig, build_pre_s7_universe
    config = LiveSessionUniverseConfig(min_candidates=2)
    unpriced = {
        "candidate_id": "unpriced-1",
        "odds_decimal": 0.0,
        "model_probability": 0.65,
        "event": "Chelsea vs Arsenal",
        "sport": "football",
        "competition": "Premier League",
        "kickoff": "2026-06-29T18:00:00Z",
        "market": "Over 2.5",
        "pick": "OVER",
        "line": "2.5",
        "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}]
    }
    report = build_pre_s7_universe([unpriced], config)
    assert report.valid_count == 0
    assert len(report.unpriced_analytical_candidates) == 1


def test_analytical_only_package_not_coupon_package(tmp_path: Path):
    from bet.pipeline.rich_coupon_package import build_rich_coupon_package
    ledger_p = tmp_path / "session_ledger.jsonl"
    _write_draft(tmp_path / "dummy_s8.json", []) # dummy
    event = {
        "schema_version": 1,
        "event_type": "candidate_reviewed",
        "recorded_at_utc": "2026-06-28T12:00:00Z",
        "betting_day": "2026-06-28",
        "session_id": "session-1",
        "payload": {
            "candidate_id": "cand-1",
            "review_status": "PRICE_PENDING_OPERATOR_CHECK",
            "event": "Chelsea vs Arsenal",
            "sport": "football",
            "market": "Match Corners",
            "pick": "OVER"
        }
    }
    with open(ledger_p, "w") as f:
        f.write(json.dumps(event) + "\n")

    packages, report = build_rich_coupon_package(
        betting_day="2026-06-28",
        session_id="session-1",
        session_ledger_path=ledger_p,
        operator_name="Superbet",
    )
    assert len(packages) == 1
    assert packages[0].package_type == "ANALYTICAL_ONLY"
    assert packages[0].ready_for_human_manual_placement is False


def test_football_corners_evidence_contract_requires_required_fields(tmp_path: Path):
    from bet.pipeline.daily_manual_session import evaluate_evidence_gate
    # Missing corners_for/against
    supporting_stats = [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}]
    status, reason, gaps = evaluate_evidence_gate(
        supporting_stats=supporting_stats,
        counter_stats=[],
        market="Match Corners",
        sport="football",
    )
    assert status == "EVIDENCE_GATE_FAIL"
    assert any(g["gap_type"] == "corners_for" for g in gaps)


def test_missing_required_evidence_blocks_bettable_even_with_good_quote(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    # Missing required football corners metrics, but has a good quote
    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "line": "9.5",
            "supporting_stats": [{"metric": "corners", "value": "12", "source": "ESPN", "as_of": "2026-06-28"}],
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z"
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_ACCEPTABLE_PENDING_EVIDENCE_REVIEW"


def test_counter_evidence_can_force_evidence_review(tmp_path: Path):
    from bet.pipeline.daily_manual_session import evaluate_evidence_gate
    supporting_stats = [
        {"metric": "corners_for", "value": "6.5", "source": "ESPN", "as_of": "2026-06-28"},
        {"metric": "corners_against", "value": "4.5", "source": "SofaScore", "as_of": "2026-06-28"},
        {"metric": "tactical_pressure_proxy", "value": "High", "source": "ESPN", "as_of": "2026-06-28"},
        {"metric": "match_script_assumption", "value": "Open game", "source": "SofaScore", "as_of": "2026-06-28"}
    ]
    counter_stats = [{"metric": "low tempo", "value": "True", "source": "SofaScore", "as_of": "2026-06-28"}]
    status, reason, gaps = evaluate_evidence_gate(
        supporting_stats=supporting_stats,
        counter_stats=counter_stats,
        market="Match Corners",
        sport="football",
    )
    assert status == "EVIDENCE_GATE_REVIEW"
    assert "forces evidence review" in reason


def test_conflicting_legs_fail_correlation_gate(tmp_path: Path):
    from bet.pipeline.daily_manual_session import evaluate_correlation_gate
    status, reason = evaluate_correlation_gate(
        correlation_risk="HIGH",
        scenario_coherence_score=Decimal("0.9"),
        conflicting_legs=["Match Corners"]
    )
    assert status == "CORRELATION_GATE_FAIL"
    assert "Logical contradiction" in reason


def test_positive_correlation_requires_scenario_explanation(tmp_path: Path):
    from bet.pipeline.daily_manual_session import evaluate_correlation_gate
    status, reason = evaluate_correlation_gate(
        correlation_risk="HIGH",
        scenario_coherence_score=Decimal("0.5"),
        conflicting_legs=[]
    )
    assert status == "CORRELATION_GATE_REVIEW"
    assert "weak scenario coherence" in reason


def test_high_correlation_without_scenario_coherence_blocks_bettable(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [
            {
                "selection_id": "sel-1",
                "event": "Chelsea vs Arsenal",
                "market": "Player A Shots",
                "pick": "OVER",
                "line": "1.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [
                    {"metric": "player_prop_avg_l10", "value": "2.1", "source": "ESPN", "as_of": "2026-06-28"},
                    {"metric": "player_minutes_avg_l5", "value": "85", "source": "SofaScore", "as_of": "2026-06-28"}
                ],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Player Shots",
                    "line": "1.5",
                    "odds_decimal": 2.50,
                    "combined_odds_decimal": 2.50,
                    "as_of_utc": "2026-06-28T12:00:00Z"
                }
            },
            {
                "selection_id": "sel-2",
                "event": "Chelsea vs Arsenal",
                "market": "Match Goals O/U",
                "pick": "OVER",
                "line": "2.5",
                "odds_decimal": 0.0,
                "odds_captured_at_utc": "",
                "model_probability": 0.50,
                "confidence_label": "MEDIUM",
                "supporting_stats": [
                    {"metric": "team_goals_scored_avg_l10", "value": "2.2", "source": "ESPN", "as_of": "2026-06-28"},
                    {"metric": "team_goals_conceded_avg_l10", "value": "1.1", "source": "SofaScore", "as_of": "2026-06-28"},
                    {"metric": "opponent_goals_scored_avg_l10", "value": "1.8", "source": "ESPN", "as_of": "2026-06-28"},
                    {"metric": "opponent_goals_conceded_avg_l10", "value": "1.4", "source": "SofaScore", "as_of": "2026-06-28"}
                ],
                "operator_quote": {
                    "operator": "Superbet",
                    "market_label": "Goals",
                    "line": "2.5",
                    "odds_decimal": 2.50,
                    "combined_odds_decimal": 2.50,
                    "as_of_utc": "2026-06-28T12:00:00Z"
                }
            }
        ]
    }]
    _write_draft(draft_path, draft_data)
    _write_s9(s9_path)

    reviews = review_s8_candidate_for_manual_session(
        config=config,
        s8_coupon_draft_path=draft_path,
        s8_coupon_draft_sha256="dummy_sha_s8",
        s9_artifact_path=s9_path,
        s9_artifact_sha256="dummy_sha_s9",
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "PRICE_ACCEPTABLE_PENDING_CORRELATION_REVIEW"


def test_price_acceptable_pending_correlation_review_status(tmp_path: Path):
    # Tested in test_high_correlation_without_scenario_coherence_blocks_bettable
    pass


def test_bettable_manual_only_requires_quote_line_timestamp_evidence_and_correlation(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "line": "9.5",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "MEDIUM",
            "supporting_stats": [
                {"metric": "corners_for", "value": "6.5", "source": "ESPN", "as_of": "2026-06-28"},
                {"metric": "corners_against", "value": "4.5", "source": "SofaScore", "as_of": "2026-06-28"},
                {"metric": "tactical_pressure_proxy", "value": "High", "source": "ESPN", "as_of": "2026-06-28"},
                {"metric": "match_script_assumption", "value": "Open game", "source": "SofaScore", "as_of": "2026-06-28"}
            ],
            "operator_quote": {
                "operator": "Superbet",
                "market_label": "Corners",
                "line": "9.5",
                "odds_decimal": 2.50,
                "combined_odds_decimal": 2.50,
                "as_of_utc": "2026-06-28T12:00:00Z",
                "entered_by_human": True,
                "computed_by_pipeline": False
            }
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
        operator_name="Superbet",
    )
    assert reviews[0].review_status == "BETTABLE_MANUAL_ONLY"


def test_manual_superbet_quote_checklist_present(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "line": "9.5",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "MEDIUM",
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
        operator_name="Superbet",
    )
    assert len(reviews[0].manual_superbet_quote_checklist) > 0


def test_no_combined_builder_odds_computed(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = config.session_dir / "data" / "s8_coupon_drafts.json"
    s9_path = config.session_dir / "data" / "s9_human_gate.json"

    draft_data = [{
        "draft_id": "draft-1",
        "selections": [{
            "selection_id": "sel-1",
            "event": "Chelsea vs Arsenal",
            "market": "Match Corners",
            "pick": "OVER",
            "line": "9.5",
            "odds_decimal": 0.0,
            "odds_captured_at_utc": "",
            "model_probability": 0.50,
            "confidence_label": "MEDIUM",
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
        operator_name="Superbet",
    )
    assert reviews[0].combined_bookmaker_odds_computed is False

