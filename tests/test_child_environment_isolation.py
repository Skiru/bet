"""Tests for least-privilege child environment isolation (Phase 4)."""
from __future__ import annotations

import os
from unittest.mock import patch

from bet.pipeline.runtime_modes import RuntimeMode
from bet.pipeline.runtime_paths import build_runtime_env


def test_child_environment_isolation(tmp_path):
    # Set up parent environment with various variables
    parent_env_overrides = {
        "SECRET_CANARY_VAR": "secret_value_123",
        "ODDSPAPI_API_KEY": "oddspapi_secret_key",
        "THE_ODDS_API_KEY": "the_odds_secret_key",
        "UNRELATED_API_KEY": "should_be_omitted",
        "PATH": "/usr/bin:/bin",
        "HOME": "/Users/test",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "PYTHONPATH": "/old/path/should/be/dropped",
        "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        "BET_PIPELINE_WRITE_ACK": "I_UNDERSTAND_PRODUCTION_WRITE",
        "TEST_MOCK_VAL": "should_be_omitted",
        "SOME_FIXTURE_VAL": "should_be_omitted",
    }

    with patch.dict(os.environ, parent_env_overrides, clear=True):
        # 1. Test in LIVE_SHADOW mode
        env = build_runtime_env(RuntimeMode.LIVE_SHADOW, "2026-06-25", "run-123", base_dir=tmp_path)

        # Assertion 1: An arbitrary canary secret is absent from child environment.
        assert "SECRET_CANARY_VAR" not in env
        assert "UNRELATED_API_KEY" not in env

        # Assertion 2: Each registry-declared credential name is passed when present.
        assert env.get("ODDSPAPI_API_KEY") == "oddspapi_secret_key"
        assert env.get("THE_ODDS_API_KEY") == "the_odds_secret_key"

        # Assertion 4: Required PATH, HOME, locale and TLS values are retained.
        assert env.get("PATH") == "/usr/bin:/bin"
        assert env.get("HOME") == "/Users/test"
        assert env.get("LANG") == "en_US.UTF-8"
        assert env.get("LC_ALL") == "en_US.UTF-8"

        # Assertion 5: Old worktree PYTHONPATH is not retained.
        assert "/old/path/should/be/dropped" not in env.get("PYTHONPATH", "")
        assert "src" in env.get("PYTHONPATH", "")

        # Assertion 6: Mock/time/path overrides are absent.
        assert "TEST_MOCK_VAL" not in env
        assert "SOME_FIXTURE_VAL" not in env
        for k in env:
            assert not any(x in k for x in ("_MOCK", "_FIXTURE", "_OVERRIDE", "_TEST"))

        # Check acknowledgements in LIVE_SHADOW
        assert env.get("BET_PIPELINE_LIVE_ACK") == "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
        assert "BET_PIPELINE_WRITE_ACK" not in env  # should only be in production


def test_production_environment_acknowledgements(tmp_path):
    parent_env_overrides = {
        "BET_PIPELINE_LIVE_ACK": "I_UNDERSTAND_LIVE_PROVIDER_CALLS",
        "BET_PIPELINE_WRITE_ACK": "I_UNDERSTAND_PRODUCTION_WRITE",
        "ODDSPAPI_API_KEY": "oddspapi_secret_key",
        "PATH": "/usr/bin:/bin",
    }
    with patch.dict(os.environ, parent_env_overrides, clear=True):
        env = build_runtime_env(RuntimeMode.PRODUCTION, "2026-06-25", "run-123", base_dir=tmp_path)
        assert env.get("BET_PIPELINE_WRITE_ACK") == "I_UNDERSTAND_PRODUCTION_WRITE"
        assert env.get("BET_PIPELINE_LIVE_ACK") == "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
