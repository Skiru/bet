"""Tests for the paper-trading readiness harness."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from bet.pipeline.manual_low_stake_pilot import (
    PREPARED_STATUS,
    ManualLowStakePilotConfig,
    load_latest_manual_pilot_coupons,
    prepare_manual_pilot_from_paper_coupon,
)
from bet.pipeline.artifact_gate import load_artifact
from bet.pipeline.paper_trading import (
    OPEN_STATUS,
    SKIPPED_OPERATIONAL_OPEN_COUPON,
    SETTLED_LOSS_STATUS,
    SETTLED_WIN_STATUS,
    VOID_STATUS,
    PaperTradingConfig,
    build_paper_coupons_from_bound_s8_s9,
    create_paper_coupon,
    expected_paper_ledger_path,
    load_latest_paper_coupons,
    read_ledger_events,
    run_paper_trading_readiness,
    run_paper_trading_single_coupon_source,
    settle_paper_coupon,
    validate_ledger_jsonl_schema,
    write_fixture_paper_trading_artifacts,
)
from bet.pipeline.run_evidence import write_json_atomic


def _config(tmp_path: Path, **overrides: object) -> PaperTradingConfig:
    values = {
        "base_dir": tmp_path / "paper-trading-base",
        "betting_day": "2026-06-27",
        "run_id": "paper-ready-001",
        "ledger_dir": tmp_path / "paper-ledger",
        "runtime_mode": "DRY_RUN",
        "bankroll_units": Decimal("100"),
        "max_stake_units_per_coupon": Decimal("1"),
        "max_daily_risk_units": Decimal("3"),
    }
    values.update(overrides)
    return PaperTradingConfig(**values)


def _bound_coupons(config: PaperTradingConfig):
    draft_path, s9_path = write_fixture_paper_trading_artifacts(config)
    return build_paper_coupons_from_bound_s8_s9(
        config=config,
        s8_coupon_draft_path=draft_path,
        s9_human_gate_artifact_path=s9_path,
    )


def _manual_config(tmp_path: Path, **overrides: object) -> ManualLowStakePilotConfig:
    values = {
        "base_dir": tmp_path / "manual-base",
        "betting_day": "2026-06-27",
        "run_id": "manual-pilot-from-paper-ready-001",
        "pilot_dir": tmp_path / "manual-base" / "2026-06-27" / "manual-pilot-from-paper-ready-001",
        "ledger_path": tmp_path / "manual-base" / "2026-06-27" / "manual-pilot-from-paper-ready-001" / "manual_pilot_ledger.jsonl",
        "runtime_mode": "DRY_RUN",
        "max_manual_coupons_per_day": 1,
        "max_stake_units_per_coupon": Decimal("1"),
        "max_daily_risk_units": Decimal("1"),
        "daily_stop_loss_units": Decimal("1"),
        "legal_operator_attested": True,
        "age_kyc_attested": True,
        "responsible_gambling_limits_attested": True,
        "manual_click_attested": True,
    }
    values.update(overrides)
    return ManualLowStakePilotConfig(**values)


def test_paper_trading_rejects_production_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="PRODUCTION mode is forbidden"):
        run_paper_trading_readiness(_config(tmp_path, runtime_mode="PRODUCTION"))


def test_paper_trading_rejects_real_bet_execution_flag(tmp_path: Path):
    with pytest.raises(ValueError, match="real bet execution must remain disabled"):
        run_paper_trading_readiness(_config(tmp_path, allow_real_bet_execution=True))


def test_paper_trading_rejects_betclic_execution_flag(tmp_path: Path):
    with pytest.raises(ValueError, match="Betclic execution must remain disabled"):
        run_paper_trading_readiness(_config(tmp_path, allow_betclic_execution=True))


def test_paper_trading_kill_switch_blocks_coupon_creation(tmp_path: Path):
    base_config = _config(tmp_path)
    coupon = _bound_coupons(base_config)[0]

    with pytest.raises(ValueError, match="kill_switch is active"):
        create_paper_coupon(replace(base_config, kill_switch=True), coupon)


def test_paper_trading_rejects_repo_local_ledger_dir(tmp_path: Path):
    fake_repo_root = tmp_path / "fake-repo"
    fake_repo_root.mkdir(parents=True, exist_ok=True)
    config = _config(
        tmp_path,
        base_dir=tmp_path / "external-base",
        ledger_dir=fake_repo_root / "paper-ledger",
    )

    with pytest.raises(ValueError, match="ledger_dir must be outside repo root"):
        run_paper_trading_readiness(config, repo_root=fake_repo_root)


def test_paper_trading_budget_guard_blocks_over_max_stake(tmp_path: Path):
    config = _config(tmp_path)
    coupon = _bound_coupons(config)[0]
    over_max = replace(
        coupon,
        paper_coupon_id=f"{coupon.paper_coupon_id}:over-max",
        stake_units=Decimal("1.01"),
        expected_payout_units=Decimal("1.01") * coupon.odds_decimal,
    )

    with pytest.raises(ValueError, match="max_stake_units_per_coupon"):
        create_paper_coupon(config, over_max)


def test_paper_trading_budget_guard_blocks_over_daily_risk(tmp_path: Path):
    config = _config(tmp_path)
    coupons = _bound_coupons(config)
    for coupon in coupons:
        create_paper_coupon(config, coupon)

    over_risk = replace(
        coupons[0],
        paper_coupon_id=f"{coupons[0].paper_coupon_id}:over-risk",
        selection_id=f"{coupons[0].selection_id}-over-risk",
        event_id=f"{coupons[0].event_id}-over-risk",
    )

    with pytest.raises(ValueError, match="max_daily_risk_units"):
        create_paper_coupon(config, over_risk)


def test_paper_trading_duplicate_coupon_id_is_blocked_idempotently(tmp_path: Path):
    config = _config(tmp_path)
    coupon = _bound_coupons(config)[0]
    create_paper_coupon(config, coupon)
    ledger_path = expected_paper_ledger_path(config)
    before = ledger_path.read_bytes()

    with pytest.raises(ValueError, match="duplicate paper_coupon_id blocked"):
        create_paper_coupon(config, coupon)

    assert ledger_path.read_bytes() == before
    assert len(read_ledger_events(ledger_path)) == 1


def test_paper_trading_ledger_jsonl_schema_is_valid(tmp_path: Path):
    config = _config(tmp_path)
    coupon = _bound_coupons(config)[0]
    create_paper_coupon(config, coupon)
    settle_paper_coupon(config, coupon.paper_coupon_id, SETTLED_WIN_STATUS)

    assert validate_ledger_jsonl_schema(expected_paper_ledger_path(config)) == []


def test_paper_trading_settlement_win_loss_void_pnl(tmp_path: Path):
    config = _config(tmp_path)
    coupons = _bound_coupons(config)
    for coupon in coupons:
        create_paper_coupon(config, coupon)

    settle_paper_coupon(config, coupons[0].paper_coupon_id, SETTLED_WIN_STATUS)
    settle_paper_coupon(config, coupons[1].paper_coupon_id, SETTLED_LOSS_STATUS)
    settle_paper_coupon(config, coupons[2].paper_coupon_id, VOID_STATUS)
    latest = load_latest_paper_coupons(expected_paper_ledger_path(config))

    assert latest[coupons[0].paper_coupon_id].pnl_units == Decimal("0.95")
    assert latest[coupons[0].paper_coupon_id].status == SETTLED_WIN_STATUS
    assert latest[coupons[1].paper_coupon_id].pnl_units == Decimal("-1")
    assert latest[coupons[1].paper_coupon_id].status == SETTLED_LOSS_STATUS
    assert latest[coupons[2].paper_coupon_id].pnl_units == Decimal("0")
    assert latest[coupons[2].paper_coupon_id].status == VOID_STATUS


def test_paper_trading_requires_bound_s8_s9_artifacts(tmp_path: Path):
    config = _config(tmp_path)
    draft_path, s9_path = write_fixture_paper_trading_artifacts(config)
    raw = load_artifact(s9_path)
    raw["manual_review"]["coupon_draft_sha256"] = "0" * 64
    write_json_atomic(s9_path, raw)

    with pytest.raises(ValueError, match="S9 artifact is not bound"):
        build_paper_coupons_from_bound_s8_s9(
            config=config,
            s8_coupon_draft_path=draft_path,
            s9_human_gate_artifact_path=s9_path,
        )


def test_paper_trading_report_never_marks_production_ready(tmp_path: Path):
    report = run_paper_trading_readiness(_config(tmp_path))

    assert report.status == "PASS"
    assert report.ready_for_manual_low_stake_pilot is True
    assert report.ready_for_production_execution is False
    assert report.no_real_bet_execution_verdict == "PASS"
    assert report.no_betclic_execution_verdict == "PASS"
    assert report.protected_repo_write_verdict == "PASS"
    assert report.budget_guard_verdict == "PASS"
    assert report.ledger_schema_verdict == "PASS"
    assert report.settlement_verdict == "PASS"
    assert report.duplicate_blocked is True


def test_paper_readiness_default_still_uses_three_coupon_settlement_proof(tmp_path: Path):
    report = run_paper_trading_readiness(_config(tmp_path, max_daily_risk_units=Decimal("3")))

    assert report.status == "PASS"
    assert report.coupon_count == 3
    assert report.settlement_verdict == "PASS"
    assert report.ready_for_production_execution is False


def test_single_coupon_source_passes_under_one_unit_daily_cap(tmp_path: Path):
    config = _config(tmp_path, run_id="paper-single-source-001", max_daily_risk_units=Decimal("1"))

    report = run_paper_trading_single_coupon_source(config)
    latest = load_latest_paper_coupons(expected_paper_ledger_path(config))
    open_coupons = [coupon for coupon in latest.values() if coupon.status == OPEN_STATUS]

    assert report.status == "PASS"
    assert report.coupon_count == 1
    assert report.total_stake_units == Decimal("1")
    assert report.max_daily_risk_units == Decimal("1")
    assert report.budget_guard_verdict == "PASS"
    assert report.settlement_verdict == SKIPPED_OPERATIONAL_OPEN_COUPON
    assert report.ready_for_manual_low_stake_pilot is True
    assert report.ready_for_production_execution is False
    assert report.blockers == []
    assert len(open_coupons) == 1
    assert open_coupons[0].source_s8_coupon_draft_path
    assert open_coupons[0].source_s8_coupon_draft_sha256
    assert open_coupons[0].source_s9_artifact_path
    assert open_coupons[0].source_s9_artifact_sha256
    assert Path(open_coupons[0].source_s8_coupon_draft_path).exists()
    assert Path(open_coupons[0].source_s9_artifact_path).exists()


def test_single_coupon_source_proves_over_risk_blocking_without_writing_second_coupon(tmp_path: Path):
    config = _config(tmp_path, run_id="paper-single-source-over-risk-001", max_daily_risk_units=Decimal("1"))

    report = run_paper_trading_single_coupon_source(config)
    ledger_path = expected_paper_ledger_path(config)
    latest = load_latest_paper_coupons(ledger_path)
    open_coupons = [coupon for coupon in latest.values() if coupon.status == OPEN_STATUS]

    assert report.status == "PASS"
    assert len(read_ledger_events(ledger_path)) == 1
    assert len(latest) == 1
    assert len(open_coupons) == 1


def test_single_coupon_source_rejects_production_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="PRODUCTION mode is forbidden"):
        run_paper_trading_single_coupon_source(
            _config(
                tmp_path,
                run_id="paper-single-source-production-001",
                runtime_mode="PRODUCTION",
                max_daily_risk_units=Decimal("1"),
            )
        )


def test_single_coupon_source_rejects_repo_local_paths(tmp_path: Path):
    fake_repo_root = tmp_path / "fake-repo"
    fake_repo_root.mkdir(parents=True, exist_ok=True)
    config = _config(
        tmp_path,
        base_dir=tmp_path / "external-base",
        ledger_dir=fake_repo_root / "paper-ledger",
        run_id="paper-single-source-repo-path-001",
        max_daily_risk_units=Decimal("1"),
    )

    with pytest.raises(ValueError, match="ledger_dir must be outside repo root"):
        run_paper_trading_single_coupon_source(config, repo_root=fake_repo_root)


def test_single_coupon_source_cli_smoke_writes_valid_report(tmp_path: Path):
    day = "2026-06-27"
    run_id = "paper-single-source-cli-smoke"
    base_dir = tmp_path / "base"
    ledger_dir = tmp_path / "ledger"
    report_path = tmp_path / "paper_single_coupon_source_report.json"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline_paper_trading_readiness.py",
            "--mode",
            "single-coupon-source",
            "--betting-day",
            day,
            "--run-id",
            run_id,
            "--base-dir",
            str(base_dir),
            "--ledger-dir",
            str(ledger_dir),
            "--runtime-mode",
            "DRY_RUN",
            "--bankroll-units",
            "100",
            "--max-stake-units-per-coupon",
            "1",
            "--max-daily-risk-units",
            "1",
            "--report-path",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    ledger_path = Path(report["ledger_path"])
    latest = load_latest_paper_coupons(ledger_path)
    assert report["status"] == "PASS"
    assert report["coupon_count"] == 1
    assert report["total_stake_units"] == "1"
    assert report["settlement_verdict"] == SKIPPED_OPERATIONAL_OPEN_COUPON
    assert report["ready_for_manual_low_stake_pilot"] is True
    assert report["ready_for_production_execution"] is False
    assert validate_ledger_jsonl_schema(ledger_path) == []
    assert len(latest) == 1
    assert len([coupon for coupon in latest.values() if coupon.status == OPEN_STATUS]) == 1


def test_manual_pilot_observation_sequence_can_prepare_after_single_coupon_source(tmp_path: Path):
    paper_config = _config(tmp_path, run_id="paper-single-source-manual-001", max_daily_risk_units=Decimal("1"))
    paper_report = run_paper_trading_single_coupon_source(paper_config)
    paper_ledger_path = expected_paper_ledger_path(paper_config)
    open_coupons = [
        coupon
        for coupon in load_latest_paper_coupons(paper_ledger_path).values()
        if coupon.status == OPEN_STATUS
    ]
    manual_config = _manual_config(tmp_path)

    prepared = prepare_manual_pilot_from_paper_coupon(
        config=manual_config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=open_coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual-human-confirmed",
    )
    manual_latest = load_latest_manual_pilot_coupons(manual_config.ledger_path)

    assert paper_report.status == "PASS"
    assert len(open_coupons) == 1
    assert prepared.status == PREPARED_STATUS
    assert prepared.manual_bookmaker_ticket_id == ""
    assert prepared.manual_placed_at_utc == ""
    assert prepared.source_paper_coupon_id == open_coupons[0].paper_coupon_id
    assert len(manual_latest) == 1
    assert list(manual_latest.values())[0].status == PREPARED_STATUS
    assert [event["event_type"] for event in read_ledger_events(manual_config.ledger_path)] == ["manual_coupon_prepared"]


def test_paper_trading_cli_smoke_writes_report_outside_repo(tmp_path: Path):
    day = "2026-06-27"
    run_id = "paper-ready-cli-smoke"
    base_dir = tmp_path / "base"
    ledger_dir = tmp_path / "ledger"
    report_path = tmp_path / "paper_trading_readiness_report.json"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline_paper_trading_readiness.py",
            "--betting-day",
            day,
            "--run-id",
            run_id,
            "--base-dir",
            str(base_dir),
            "--ledger-dir",
            str(ledger_dir),
            "--runtime-mode",
            "DRY_RUN",
            "--bankroll-units",
            "100",
            "--max-stake-units-per-coupon",
            "1",
            "--max-daily-risk-units",
            "3",
            "--report-path",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    ledger_path = Path(report["ledger_path"])
    assert report["status"] == "PASS"
    assert report["ready_for_manual_low_stake_pilot"] is True
    assert report["ready_for_production_execution"] is False
    assert report["no_real_bet_execution_verdict"] == "PASS"
    assert report["no_betclic_execution_verdict"] == "PASS"
    assert report["protected_repo_write_verdict"] == "PASS"
    assert ledger_path.exists()
    assert validate_ledger_jsonl_schema(ledger_path) == []
    assert str(ledger_path).startswith(str(tmp_path.resolve()))
    assert str(report_path.resolve()).startswith(str(tmp_path.resolve()))
