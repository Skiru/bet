"""Tests for full pipeline shadow acceptance harness."""
from __future__ import annotations

from pathlib import Path

import pytest

from bet.pipeline.artifact_gate import sha256_file
from bet.pipeline.full_shadow_acceptance import (
    FullShadowAcceptanceConfig,
    build_s9_human_gate_artifact,
    compare_path_snapshots,
    evaluate_s10_gate,
    expected_acceptance_s8_draft_path,
    is_run_scoped_s8_draft_path,
    run_full_shadow_acceptance,
    snapshot_paths,
    write_fixture_s8_coupon_draft,
    write_s9_human_gate_artifact,
)


def _config(tmp_path: Path, **overrides: object) -> FullShadowAcceptanceConfig:
    values = {
        "base_dir": tmp_path / "shadow-acceptance",
        "betting_day": "2026-06-27",
        "run_id": "run-shadow-001",
        "runtime_mode": "DRY_RUN",
    }
    values.update(overrides)
    return FullShadowAcceptanceConfig(**values)


def test_full_shadow_acceptance_rejects_production_mode(tmp_path: Path):
    with pytest.raises(ValueError, match="PRODUCTION mode is forbidden"):
        run_full_shadow_acceptance(_config(tmp_path, runtime_mode="PRODUCTION"))


def test_full_shadow_acceptance_rejects_repo_local_base_dir(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    with pytest.raises(ValueError, match="base_dir must be outside repo root"):
        run_full_shadow_acceptance(
            FullShadowAcceptanceConfig(
                base_dir=repo_root / ".tmp-shadow-acceptance",
                betting_day="2026-06-27",
                run_id="run-shadow-002",
                runtime_mode="DRY_RUN",
            )
        )


def test_full_shadow_acceptance_detects_protected_repo_writes(tmp_path: Path):
    protected_root = tmp_path / "reports"
    protected_root.mkdir(parents=True, exist_ok=True)

    before = snapshot_paths((protected_root,))
    (protected_root / "changed.json").write_text("{}", encoding="utf-8")
    after = snapshot_paths((protected_root,))

    changes = compare_path_snapshots(before, after)
    assert changes == [f"CREATED:{(protected_root / 'changed.json').resolve(strict=False)}"]


def test_full_shadow_acceptance_accepts_only_run_scoped_s8_draft(tmp_path: Path):
    config = _config(tmp_path)
    valid_path = expected_acceptance_s8_draft_path(config)

    assert is_run_scoped_s8_draft_path(valid_path, config) is True
    assert is_run_scoped_s8_draft_path(Path("/tmp") / f"{config.betting_day}_s8_coupon_drafts.json", config) is False


def test_full_shadow_acceptance_s9_bound_approval_unblocks_only_s10_gate(tmp_path: Path):
    config = _config(tmp_path)
    draft_path = write_fixture_s8_coupon_draft(config)

    assert evaluate_s10_gate(config).verdict.value == "BLOCK"

    valid_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=draft_path,
        coupon_draft_sha256=sha256_file(draft_path),
    )
    write_s9_human_gate_artifact(config, valid_artifact)
    assert evaluate_s10_gate(config).verdict.value == "PASS"

    wrong_sha_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=draft_path,
        coupon_draft_sha256="0" * 64,
    )
    write_s9_human_gate_artifact(config, wrong_sha_artifact)
    assert evaluate_s10_gate(config).verdict.value == "BLOCK"

    wrong_path_artifact = build_s9_human_gate_artifact(
        config,
        coupon_draft_path=Path("/tmp") / f"{config.betting_day}_s8_coupon_drafts.json",
        coupon_draft_sha256=sha256_file(draft_path),
    )
    write_s9_human_gate_artifact(config, wrong_path_artifact)
    assert evaluate_s10_gate(config).verdict.value == "BLOCK"


def test_full_shadow_acceptance_report_never_marks_production_ready(tmp_path: Path):
    report = run_full_shadow_acceptance(_config(tmp_path))

    assert report.ready_for_production_execution is False
    assert report.s8_ready_for_production_execution is False


def test_full_shadow_acceptance_fixture_positive_path_reaches_s9_block(tmp_path: Path):
    report = run_full_shadow_acceptance(_config(tmp_path))

    assert report.status == "PASS"
    assert report.pipeline_terminal_status == "S9_BLOCK_WAITING_FOR_HUMAN_GATE"
    assert report.terminal_step == "S9"
    assert report.s8_coupon_draft_count > 0
    assert report.s8_requires_human_gate is True
    assert report.s8_ready_for_human_gate is True
    assert report.s8_production_coupon_write is False
    assert report.s8_executable_coupon is False
    assert report.s8_betclic_execution_enabled is False
    assert report.s9_missing_blocks is True
    assert report.s9_bound_approval_unblocks_s10_gate is True
    assert report.s9_bare_tmp_approval_blocks is True
    assert report.s9_wrong_sha_blocks is True
    assert report.protected_repo_write_verdict == "PASS"
    assert report.ready_for_paper_trading is True
