"""Test suite for LIVE_ANALYSIS_SHADOW runtime mode defects (B02, B03, B04, B05, B22)."""

import os
from pathlib import Path
import pytest

from bet.pipeline.runtime_modes import RuntimeMode, parse_runtime_mode
from bet.pipeline.runtime_paths import build_runtime_env


def test_b02_live_analysis_shadow_sets_dry_run():
    """B02: LIVE_ANALYSIS_SHADOW receives synthetic DRY_RUN semantics."""
    env = build_runtime_env(
        runtime_mode="LIVE_ANALYSIS_SHADOW",
        betting_day="2026-07-30",
        run_id="run_test_b02",
    )
    
    # B02 defect: build_runtime_env sets DRY_RUN="1" for any mode != PRODUCTION!
    assert "DRY_RUN" not in env or env.get("DRY_RUN") != "1", (
        f"B02 defect: build_runtime_env set DRY_RUN=1 for LIVE_ANALYSIS_SHADOW mode! env={env}"
    )


def test_b03_shadow_writes_conflict_with_allow_write():
    """B03: shadow writes conflict with generic --allow-write protection."""
    env = build_runtime_env(
        runtime_mode="LIVE_ANALYSIS_SHADOW",
        betting_day="2026-07-30",
        run_id="run_test_b03",
    )
    
    # Shadow writes must be allowed natively in LIVE_ANALYSIS_SHADOW mode without requiring generic production WRITE_ACK
    assert env.get("BET_PIPELINE_SHADOW_WRITE_ALLOWED") == "1", (
        f"B03 defect: BET_PIPELINE_SHADOW_WRITE_ALLOWED missing or not set to 1 in LIVE_ANALYSIS_SHADOW mode env"
    )
    assert env.get("BET_PIPELINE_CANONICAL_WRITE_ALLOWED") == "0", (
        f"B03 defect: BET_PIPELINE_CANONICAL_WRITE_ALLOWED must be 0 in shadow mode"
    )


def test_b04_live_network_ack_not_propagated_for_shadow(monkeypatch):
    """B04: live-network ACK is not consistently propagated for LIVE_ANALYSIS_SHADOW."""
    try:
        from bet.pipeline.runtime_modes import LIVE_ACK_KEY, LIVE_ACK_VALUE, validate_runtime_mode_acks
    except (ImportError, ModuleNotFoundError):
        pytest.fail("B04 defect: validate_runtime_mode_acks missing in bet.pipeline.runtime_modes", pytrace=False)

    monkeypatch.delenv(LIVE_ACK_KEY, raising=False)
    
    # LIVE_ANALYSIS_SHADOW mode requires LIVE_ACK to allow live network calls
    with pytest.raises(ValueError, match="LIVE_ACK_REQUIRED"):
        validate_runtime_mode_acks(mode=RuntimeMode.LIVE_SHADOW, env=os.environ)


def test_b05_child_process_loses_db_or_selection_identity():
    """B05: child processes can lose or drift DB path, run ID, run root, selection run ID, selection hash, runtime mode."""
    env = build_runtime_env(
        runtime_mode="LIVE_ANALYSIS_SHADOW",
        betting_day="2026-07-30",
        run_id="run_test_b05",
    )
    
    # Mandatory environment variables for child processes to avoid drift:
    mandatory_keys = [
        "BET_DB_PATH",
        "BET_PIPELINE_SELECTION_RUN_ID",
        "BET_PIPELINE_SELECTION_HASH",
        "BET_PIPELINE_STORAGE_SCOPE",
        "BET_PIPELINE_RUNTIME_MODE",
    ]
    
    missing = [k for k in mandatory_keys if k not in env]
    assert not missing, f"B05 defect: child environment missing critical variables: {missing}"


def test_b22_canonical_db_and_shadow_db_write_semantics(tmp_path):
    """B22: canonical DB and shadow DB write semantics are not strongly separated."""
    canonical_db_path = tmp_path / "canonical.db"
    canonical_db_path.write_text("canonical db content")
    
    shadow_db_path = tmp_path / "shadow.db"
    shadow_db_path.write_text("shadow db content")

    try:
        from bet.pipeline.runtime_paths import verify_db_write_isolation
    except (ImportError, ModuleNotFoundError):
        pytest.fail("B22 defect: verify_db_write_isolation missing in bet.pipeline.runtime_paths", pytrace=False)

    # Attempting to write to canonical DB path while operating in SHADOW mode must be blocked
    is_safe, error = verify_db_write_isolation(
        target_db_path=canonical_db_path,
        canonical_db_path=canonical_db_path,
        shadow_db_path=shadow_db_path,
        storage_scope="SHADOW",
    )
    assert not is_safe, "B22 defect: canonical DB path allowed write in SHADOW mode"
    assert "CANONICAL_DB_WRITE_PROHIBITED" in error
