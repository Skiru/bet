"""Tests for run_daily_pipeline.py CLI compiling and execution."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cli_compiles():
    """Verify that run_daily_pipeline.py compiles and runs help output without error."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/run_daily_pipeline.py"
    assert cli_path.exists()

    res = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Run daily manifest-driven pipeline" in res.stdout


def test_cli_requires_arguments():
    """Verify that run_daily_pipeline.py fails and displays usage on missing required arguments."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/run_daily_pipeline.py"
    res = subprocess.run([sys.executable, str(cli_path)], capture_output=True, text=True)
    assert res.returncode != 0
    assert "error:" in res.stderr
