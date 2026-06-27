"""Tests for the manual low-stake pilot guard."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from bet.pipeline.manual_low_stake_pilot import (
    MANUALLY_PLACED_STATUS,
    PREPARED_STATUS,
    SETTLED_LOSS_STATUS,
    SETTLED_WIN_STATUS,
    VOID_STATUS,
    ManualLowStakePilotConfig,
    build_manual_low_stake_pilot_report,
    load_latest_manual_pilot_coupons,
    prepare_manual_pilot_from_paper_coupon,
    read_ledger_events,
    record_manual_bookmaker_placement,
    settle_manual_pilot_coupon,
    validate_ledger_jsonl_schema,
    validate_manual_low_stake_pilot_config,
)
from bet.pipeline.paper_trading import (
    PaperTradingConfig,
    build_paper_coupons_from_bound_s8_s9,
    create_paper_coupon,
    expected_paper_ledger_path,
    load_latest_paper_coupons,
    settle_paper_coupon as settle_source_paper_coupon,
    write_fixture_paper_trading_artifacts,
)


def _config(tmp_path: Path, **overrides: object) -> ManualLowStakePilotConfig:
    day = "2026-06-27"
    run_id = "manual-pilot-001"
    base_dir = tmp_path / "manual-base"
    pilot_dir = base_dir / day / run_id
    values = {
        "base_dir": base_dir,
        "betting_day": day,
        "run_id": run_id,
        "pilot_dir": pilot_dir,
        "ledger_path": pilot_dir / "manual_pilot_ledger.jsonl",
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


def _paper_source(tmp_path: Path, *, betting_day: str = "2026-06-27"):
    config = PaperTradingConfig(
        base_dir=tmp_path / "paper-base",
        betting_day=betting_day,
        run_id="paper-source-001",
        ledger_dir=tmp_path / "paper-ledger",
        runtime_mode="DRY_RUN",
        bankroll_units=Decimal("100"),
        max_stake_units_per_coupon=Decimal("1"),
        max_daily_risk_units=Decimal("3"),
    )
    draft_path, s9_path = write_fixture_paper_trading_artifacts(config)
    coupons = build_paper_coupons_from_bound_s8_s9(
        config=config,
        s8_coupon_draft_path=draft_path,
        s9_human_gate_artifact_path=s9_path,
    )
    for coupon in coupons:
        create_paper_coupon(config, coupon)
    return config, expected_paper_ledger_path(config), coupons


def _prepare(tmp_path: Path, **config_overrides: object):
    config = _config(tmp_path, **config_overrides)
    _, paper_ledger_path, coupons = _paper_source(tmp_path, betting_day=config.betting_day)
    coupon = prepare_manual_pilot_from_paper_coupon(
        config=config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
    )
    return config, paper_ledger_path, coupons, coupon


def _place(config: ManualLowStakePilotConfig, manual_pilot_coupon_id: str):
    return record_manual_bookmaker_placement(
        config=config,
        manual_pilot_coupon_id=manual_pilot_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
        manual_bookmaker_ticket_id="MANUAL-TEST-TICKET-001",
        manual_placed_at_utc="2026-06-27T10:00:00Z",
    )


def test_manual_pilot_rejects_production_mode(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="PRODUCTION mode is forbidden"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, runtime_mode="PRODUCTION"),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_rejects_automated_bookmaker_placement(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="automated bookmaker placement must remain disabled"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, allow_automated_bookmaker_placement=True),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_rejects_betclic_api_flag(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="Betclic API execution must remain disabled"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, allow_betclic_api=True),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_rejects_browser_automation_flag(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="browser automation must remain disabled"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, allow_browser_automation=True),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_kill_switch_blocks_prepare(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="kill_switch is active"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, kill_switch=True),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_requires_legal_operator_attestation(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="legal_operator_attested must be true"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, legal_operator_attested=False),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_requires_age_kyc_attestation(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="age_kyc_attested must be true"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, age_kyc_attested=False),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_requires_responsible_gambling_attestation(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="responsible_gambling_limits_attested must be true"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, responsible_gambling_limits_attested=False),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_requires_manual_click_attestation(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="manual_click_attested must be true"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, manual_click_attested=False),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_rejects_repo_local_paths(tmp_path: Path):
    fake_repo_root = tmp_path / "fake-repo"
    pilot_dir = fake_repo_root / "betting" / "coupons" / "pilot"
    config = _config(
        tmp_path,
        base_dir=fake_repo_root / "external-base",
        pilot_dir=pilot_dir,
        ledger_path=pilot_dir / "manual_pilot_ledger.jsonl",
    )

    blockers = validate_manual_low_stake_pilot_config(config, repo_root=fake_repo_root)

    assert any("protected repo-local paths" in blocker for blocker in blockers)


def test_manual_pilot_allows_only_one_coupon_per_day(tmp_path: Path):
    config = _config(tmp_path)
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    prepare_manual_pilot_from_paper_coupon(
        config=config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
    )

    with pytest.raises(ValueError, match="max_manual_coupons_per_day"):
        prepare_manual_pilot_from_paper_coupon(
            config=config,
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[1].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_budget_guard_blocks_over_stake(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)

    with pytest.raises(ValueError, match="max_stake_units_per_coupon"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path, max_stake_units_per_coupon=Decimal("0.5")),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_budget_guard_blocks_over_daily_risk(tmp_path: Path):
    config = _config(tmp_path, max_manual_coupons_per_day=2, max_daily_risk_units=Decimal("1.5"), daily_stop_loss_units=Decimal("2"))
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    prepare_manual_pilot_from_paper_coupon(
        config=config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
    )

    with pytest.raises(ValueError, match="max_daily_risk_units"):
        prepare_manual_pilot_from_paper_coupon(
            config=config,
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[1].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_stop_loss_blocks_after_loss_limit(tmp_path: Path):
    config = _config(tmp_path, max_manual_coupons_per_day=2, max_daily_risk_units=Decimal("2"), daily_stop_loss_units=Decimal("1"))
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    prepared = prepare_manual_pilot_from_paper_coupon(
        config=config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
    )
    _place(config, prepared.manual_pilot_coupon_id)
    settle_manual_pilot_coupon(
        config=config,
        manual_pilot_coupon_id=prepared.manual_pilot_coupon_id,
        result="LOSS",
    )

    with pytest.raises(ValueError, match="daily_stop_loss_units"):
        prepare_manual_pilot_from_paper_coupon(
            config=config,
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[1].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_duplicate_coupon_id_is_blocked_idempotently(tmp_path: Path):
    config = _config(tmp_path, max_manual_coupons_per_day=2, max_daily_risk_units=Decimal("2"), daily_stop_loss_units=Decimal("2"))
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    prepare_manual_pilot_from_paper_coupon(
        config=config,
        paper_ledger_path=paper_ledger_path,
        source_paper_coupon_id=coupons[0].paper_coupon_id,
        manual_bookmaker_name="licensed-operator-manual",
    )
    before = config.ledger_path.read_bytes()

    with pytest.raises(ValueError, match="duplicate manual_pilot_coupon_id blocked"):
        prepare_manual_pilot_from_paper_coupon(
            config=config,
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )

    assert config.ledger_path.read_bytes() == before
    assert len(read_ledger_events(config.ledger_path)) == 1


def test_manual_pilot_requires_open_paper_coupon(tmp_path: Path):
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    paper_config = PaperTradingConfig(
        base_dir=tmp_path / "paper-base",
        betting_day="2026-06-27",
        run_id="paper-source-001",
        ledger_dir=tmp_path / "paper-ledger",
        runtime_mode="DRY_RUN",
        bankroll_units=Decimal("100"),
        max_stake_units_per_coupon=Decimal("1"),
        max_daily_risk_units=Decimal("3"),
    )
    settle_source_paper_coupon(paper_config, coupons[0].paper_coupon_id, SETTLED_WIN_STATUS)

    with pytest.raises(ValueError, match="paper coupon must be OPEN"):
        prepare_manual_pilot_from_paper_coupon(
            config=_config(tmp_path),
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=coupons[0].paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )


def test_manual_pilot_prepares_without_marking_placed(tmp_path: Path):
    config, _, _, prepared = _prepare(tmp_path)
    latest = load_latest_manual_pilot_coupons(config.ledger_path)

    assert prepared.status == PREPARED_STATUS
    assert prepared.manual_bookmaker_ticket_id == ""
    assert prepared.manual_placed_at_utc == ""
    assert latest[prepared.manual_pilot_coupon_id].status == PREPARED_STATUS
    assert read_ledger_events(config.ledger_path)[0]["event_type"] == "manual_coupon_prepared"


def test_manual_pilot_record_placement_requires_ticket_id(tmp_path: Path):
    config, _, _, prepared = _prepare(tmp_path)

    with pytest.raises(ValueError, match="manual_bookmaker_ticket_id must be non-empty"):
        record_manual_bookmaker_placement(
            config=config,
            manual_pilot_coupon_id=prepared.manual_pilot_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
            manual_bookmaker_ticket_id="",
            manual_placed_at_utc="2026-06-27T10:00:00Z",
        )


def test_manual_pilot_record_placement_does_not_call_bookmaker(tmp_path: Path):
    config, paper_ledger_path, _, prepared = _prepare(tmp_path)
    source_before = Path(paper_ledger_path).read_bytes()
    placed = _place(config, prepared.manual_pilot_coupon_id)

    assert placed.status == MANUALLY_PLACED_STATUS
    assert Path(paper_ledger_path).read_bytes() == source_before
    assert [event["event_type"] for event in read_ledger_events(config.ledger_path)] == [
        "manual_coupon_prepared",
        "manual_coupon_placed",
    ]


def test_manual_pilot_settlement_win_loss_void_pnl(tmp_path: Path):
    config = _config(tmp_path, max_manual_coupons_per_day=3, max_daily_risk_units=Decimal("3"), daily_stop_loss_units=Decimal("3"))
    _, paper_ledger_path, coupons = _paper_source(tmp_path)
    prepared = [
        prepare_manual_pilot_from_paper_coupon(
            config=config,
            paper_ledger_path=paper_ledger_path,
            source_paper_coupon_id=source_coupon.paper_coupon_id,
            manual_bookmaker_name="licensed-operator-manual",
        )
        for source_coupon in coupons
    ]
    for coupon in prepared:
        _place(config, coupon.manual_pilot_coupon_id)

    settle_manual_pilot_coupon(config=config, manual_pilot_coupon_id=prepared[0].manual_pilot_coupon_id, result="WIN")
    settle_manual_pilot_coupon(config=config, manual_pilot_coupon_id=prepared[1].manual_pilot_coupon_id, result="LOSS")
    settle_manual_pilot_coupon(config=config, manual_pilot_coupon_id=prepared[2].manual_pilot_coupon_id, result="VOID")
    latest = load_latest_manual_pilot_coupons(config.ledger_path)

    assert latest[prepared[0].manual_pilot_coupon_id].pnl_units == Decimal("0.95")
    assert latest[prepared[0].manual_pilot_coupon_id].status == SETTLED_WIN_STATUS
    assert latest[prepared[1].manual_pilot_coupon_id].pnl_units == Decimal("-1")
    assert latest[prepared[1].manual_pilot_coupon_id].status == SETTLED_LOSS_STATUS
    assert latest[prepared[2].manual_pilot_coupon_id].pnl_units == Decimal("0")
    assert latest[prepared[2].manual_pilot_coupon_id].status == VOID_STATUS


def test_manual_pilot_report_never_marks_production_ready(tmp_path: Path):
    config, _, _, prepared = _prepare(tmp_path)
    _place(config, prepared.manual_pilot_coupon_id)
    settle_manual_pilot_coupon(config=config, manual_pilot_coupon_id=prepared.manual_pilot_coupon_id, result="WIN")

    report = build_manual_low_stake_pilot_report(config)

    assert report.status == "PASS"
    assert report.ready_for_controlled_manual_pilot is True
    assert report.ready_for_production_execution is False
    assert report.legal_operator_attestation_verdict == "PASS"
    assert report.age_kyc_attestation_verdict == "PASS"
    assert report.responsible_gambling_limits_verdict == "PASS"
    assert report.manual_click_required_verdict == "PASS"
    assert report.no_automated_bookmaker_placement_verdict == "PASS"
    assert report.no_betclic_api_verdict == "PASS"
    assert report.no_browser_automation_verdict == "PASS"
    assert report.ledger_schema_verdict == "PASS"


def test_manual_pilot_cli_prepare_record_settle_smoke(tmp_path: Path):
    day = "2026-06-27"
    run_id = "manual-pilot-cli-smoke"
    base_dir = tmp_path / "manual-base"
    pilot_dir = base_dir / day / run_id
    ledger_path = pilot_dir / "manual_pilot_ledger.jsonl"
    report_path = pilot_dir / "manual_low_stake_pilot_report.json"
    pilot_dir.mkdir(parents=True, exist_ok=True)

    _, paper_ledger_path, coupons = _paper_source(tmp_path, betting_day=day)
    source_coupon = load_latest_paper_coupons(paper_ledger_path)[coupons[0].paper_coupon_id]

    prepare = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline_manual_low_stake_pilot.py",
            "prepare",
            "--betting-day",
            day,
            "--run-id",
            run_id,
            "--base-dir",
            str(base_dir),
            "--pilot-dir",
            str(pilot_dir),
            "--ledger-path",
            str(ledger_path),
            "--paper-ledger-path",
            str(paper_ledger_path),
            "--source-paper-coupon-id",
            coupons[0].paper_coupon_id,
            "--manual-bookmaker-name",
            "licensed-operator-manual",
            "--stake-units",
            str(source_coupon.stake_units),
            "--max-stake-units-per-coupon",
            "1",
            "--max-daily-risk-units",
            "1",
            "--daily-stop-loss-units",
            "1",
            "--legal-operator-attested",
            "--age-kyc-attested",
            "--responsible-gambling-limits-attested",
            "--manual-click-attested",
            "--report-path",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert prepare.returncode == 0, prepare.stderr
    prepare_report = json.loads(report_path.read_text(encoding="utf-8"))
    coupon_id = next(line.split("=", 1)[1] for line in prepare.stdout.splitlines() if line.startswith("MANUAL_PILOT_COUPON_ID="))

    record = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline_manual_low_stake_pilot.py",
            "record-placement",
            "--betting-day",
            day,
            "--run-id",
            run_id,
            "--pilot-dir",
            str(pilot_dir),
            "--ledger-path",
            str(ledger_path),
            "--manual-pilot-coupon-id",
            coupon_id,
            "--manual-bookmaker-name",
            "licensed-operator-manual",
            "--manual-bookmaker-ticket-id",
            "MANUAL-TEST-TICKET-001",
            "--manual-placed-at-utc",
            "2026-06-27T10:00:00Z",
            "--manual-click-attested",
            "--report-path",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert record.returncode == 0, record.stderr

    settle = subprocess.run(
        [
            sys.executable,
            "scripts/pipeline_manual_low_stake_pilot.py",
            "settle",
            "--betting-day",
            day,
            "--run-id",
            run_id,
            "--pilot-dir",
            str(pilot_dir),
            "--ledger-path",
            str(ledger_path),
            "--manual-pilot-coupon-id",
            coupon_id,
            "--result",
            "WIN",
            "--report-path",
            str(report_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert settle.returncode == 0, settle.stderr

    final_report = json.loads(report_path.read_text(encoding="utf-8"))
    ledger_events = read_ledger_events(ledger_path)
    assert prepare_report["status"] == "PASS"
    assert final_report["status"] == "PASS"
    assert final_report["ready_for_controlled_manual_pilot"] is True
    assert final_report["ready_for_production_execution"] is False
    assert final_report["manual_coupon_count"] == 1
    assert validate_ledger_jsonl_schema(ledger_path) == []
    assert [event["event_type"] for event in ledger_events] == [
        "manual_coupon_prepared",
        "manual_coupon_placed",
        "manual_coupon_settled",
    ]
