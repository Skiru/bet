"""Tests for the paper-trading readiness harness."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from bet.pipeline.artifact_gate import load_artifact
from bet.pipeline.paper_trading import (
    OPEN_STATUS,
    SETTLED_LOSS_STATUS,
    SETTLED_WIN_STATUS,
    VOID_STATUS,
    PaperTradingConfig,
    build_paper_coupons_from_bound_s8_s9,
    create_paper_coupon,
    expected_paper_ledger_path,
    expected_paper_s8_draft_path,
    expected_paper_s9_artifact_path,
    load_latest_paper_coupons,
    read_ledger_events,
    run_paper_trading_readiness,
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
