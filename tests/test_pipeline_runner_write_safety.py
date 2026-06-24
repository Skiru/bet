"""Tests for pipeline runner write safety and environment guarding."""
from __future__ import annotations

import os
from pathlib import Path
import pytest

from bet.pipeline.manifest import discover_repo_root
from scripts.pipeline_steps._runner import run_scripts


@pytest.fixture
def temp_probe_script():
    """Temporary test probe script to run through the runner."""
    root = discover_repo_root()
    probe_path = root / "scripts" / "_temp_write_safety_probe.py"
    probe_path.write_text(
        "import os\n"
        "import sys\n"
        "if os.environ.get('DRY_RUN') == '1' and 'bet_dryrun_' not in os.environ.get('DATABASE_URL', ''):\n"
        "    sys.exit(99)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    yield "_temp_write_safety_probe.py"
    if probe_path.exists():
        try:
            probe_path.unlink()
        except OSError:
            pass


def test_default_dry_run_uses_temp_db(monkeypatch, temp_probe_script):
    """Verify that the default dry-run run successfully executes and uses clean database url."""
    monkeypatch.delenv("FORCE_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)

    rc = run_scripts([temp_probe_script], dry_run=True, allow_write=False)
    assert rc == 0


def test_env_only_force_allow_write_blocks(monkeypatch, temp_probe_script, capsys):
    """Verify that FORCE_ALLOW_WRITE alone without allow_write and ack blocks with code 4."""
    monkeypatch.setenv("FORCE_ALLOW_WRITE", "true")
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)

    rc = run_scripts([temp_probe_script], dry_run=True, allow_write=False)
    assert rc == 4
    captured = capsys.readouterr()
    assert "BLOCKED_FORCE_ALLOW_WRITE_UNSAFE" in captured.out


def test_allow_write_without_ack_blocks(monkeypatch, temp_probe_script, capsys):
    """Verify that allow_write=True without write ack blocks with code 3."""
    monkeypatch.delenv("FORCE_ALLOW_WRITE", raising=False)
    monkeypatch.delenv("BET_PIPELINE_WRITE_ACK", raising=False)

    rc = run_scripts([temp_probe_script], dry_run=False, allow_write=True)
    assert rc == 3
    captured = capsys.readouterr()
    assert "BLOCKED_WRITE_ACK_MISSING" in captured.out


def test_allow_write_with_correct_ack_passes(monkeypatch, temp_probe_script):
    """Verify that allow_write=True with correct ack passes through without blocking."""
    monkeypatch.delenv("FORCE_ALLOW_WRITE", raising=False)
    monkeypatch.setenv("BET_PIPELINE_WRITE_ACK", "I_UNDERSTAND_PRODUCTION_WRITE")

    rc = run_scripts([temp_probe_script], dry_run=False, allow_write=True)
    assert rc == 0
