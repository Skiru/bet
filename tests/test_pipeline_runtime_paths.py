"""Tests for sandboxed runtime paths and environment building."""
from __future__ import annotations

import os
from pathlib import Path
import pytest
from bet.pipeline.runtime_paths import (
    resolve_run_root,
    runtime_data_dir,
    runtime_coupon_dir,
    runtime_artifact_dir,
    build_runtime_env,
)
from bet.pipeline.runtime_modes import RuntimeMode


def test_resolve_run_root_default():
    run_root = resolve_run_root("2026-06-25", "run-123")
    assert run_root.name == "run-123"
    assert run_root.parent.name == "2026-06-25"
    assert "reports/pipeline_runs" in str(run_root)


def test_resolve_run_root_custom_base(tmp_path):
    run_root = resolve_run_root("2026-06-25", "run-123", base_dir=tmp_path)
    assert run_root == tmp_path / "2026-06-25" / "run-123"


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
    assert env["BET_PIPELINE_RUN_ROOT"] == str(tmp_path / "2026-06-25" / "run-123")
    assert env["BET_PIPELINE_DATA_DIR"] == str(tmp_path / "2026-06-25" / "run-123" / "data")
    assert env["BET_PIPELINE_COUPON_DIR"] == str(tmp_path / "2026-06-25" / "run-123" / "coupons")
    assert env["BET_PIPELINE_ARTIFACT_DIR"] == str(tmp_path / "2026-06-25" / "run-123" / "artifacts")
    assert env["BET_PIPELINE_RUNTIME_MODE"] == "DRY_RUN"
    assert env["DRY_RUN"] == "1"


def test_build_runtime_env_production(tmp_path):
    env = build_runtime_env(RuntimeMode.PRODUCTION, "2026-06-25", "run-123", base_dir=tmp_path)
    assert env["BET_PIPELINE_RUNTIME_MODE"] == "PRODUCTION"
    assert "DRY_RUN" not in env
