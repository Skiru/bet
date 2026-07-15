"""Tests for sandboxed runtime paths and environment building."""
from __future__ import annotations

from pathlib import Path

from bet.pipeline.runtime_modes import RuntimeMode
from bet.pipeline.runtime_paths import (
    build_runtime_env,
    is_system_temp_path,
    paths_refer_to_same_location,
    resolve_run_root,
    runtime_artifact_dir,
    runtime_coupon_dir,
    runtime_data_dir,
)


def test_resolve_run_root_default():
    run_root = resolve_run_root("2026-06-25", "run-123")
    assert run_root.name == "run-123"
    assert run_root.parent.name == "2026-06-25"
    assert "reports/pipeline_runs" in str(run_root)


def test_resolve_run_root_custom_base(tmp_path):
    run_root = resolve_run_root("2026-06-25", "run-123", base_dir=tmp_path)
    assert run_root == tmp_path / "pipeline_runs" / "2026-06-25" / "run-123"


def test_resolve_run_root_none_run_id():
    run_root = resolve_run_root("2026-06-25", None)
    assert run_root.name == "default"


def test_runtime_subdirs():
    root = Path("/tmp/run-123")
    assert runtime_data_dir(root) == root / "data"
    assert runtime_coupon_dir(root) == root / "coupons"
    assert runtime_artifact_dir(root) == root / "artifacts"


def test_build_runtime_env(tmp_path):
    env = build_runtime_env(RuntimeMode.DRY_RUN, "2026-06-25", "run-123", base_dir=tmp_path)
    assert env["BET_PIPELINE_RUN_ROOT"] == str(tmp_path / "pipeline_runs" / "2026-06-25" / "run-123")
    assert env["BET_PIPELINE_BETTING_DAY"] == "2026-06-25"
    assert env["BET_PIPELINE_RUN_ID"] == "run-123"
    assert env["BET_PIPELINE_DATA_DIR"] == str(tmp_path / "pipeline_runs" / "2026-06-25" / "run-123" / "data")
    assert env["BET_PIPELINE_COUPON_DIR"] == str(tmp_path / "pipeline_runs" / "2026-06-25" / "run-123" / "coupons")
    assert env["BET_PIPELINE_ARTIFACT_DIR"] == str(tmp_path / "pipeline_runs" / "2026-06-25" / "run-123" / "artifacts")
    assert env["BET_PIPELINE_RUNTIME_MODE"] == "DRY_RUN"
    assert env["DRY_RUN"] == "1"
    assert "betting/data" not in env["BET_PIPELINE_DATA_DIR"]
    assert "betting/coupons" not in env["BET_PIPELINE_COUPON_DIR"]


def test_build_runtime_env_production(tmp_path):
    env = build_runtime_env(RuntimeMode.PRODUCTION, "2026-06-25", "run-123", base_dir=tmp_path)
    assert env["BET_PIPELINE_RUNTIME_MODE"] == "PRODUCTION"
    assert "DRY_RUN" not in env
    assert "betting/data" not in env["BET_PIPELINE_DATA_DIR"]
    assert "betting/coupons" not in env["BET_PIPELINE_COUPON_DIR"]


def test_path_identity_accepts_platform_temp_alias(tmp_path: Path):
    real_root = tmp_path / "real-temp"
    real_root.mkdir()
    real_input = real_root / "input.json"
    real_input.write_text("{}", encoding="utf-8")
    alias_root = tmp_path / "temp-alias"
    alias_root.symlink_to(real_root, target_is_directory=True)

    assert paths_refer_to_same_location(alias_root / "input.json", real_input)


def test_path_identity_rejects_different_files(tmp_path: Path):
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    left.write_text("{}", encoding="utf-8")
    right.write_text("{}", encoding="utf-8")

    assert not paths_refer_to_same_location(left, right)


def test_system_temp_path_uses_canonical_location(tmp_path: Path):
    assert is_system_temp_path(tmp_path)
    assert not is_system_temp_path(Path("/"))
