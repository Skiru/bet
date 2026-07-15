"""Tests for run_daily_pipeline.py and create_agent_work_order.py CLI compiling and execution."""
from __future__ import annotations

import json
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


def test_create_agent_work_order_compiles():
    """Verify that create_agent_work_order.py compiles and runs help output without error."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/create_agent_work_order.py"
    assert cli_path.exists()

    res = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Create an agent work order" in res.stdout


def test_render_agent_execution_prompt_compiles():
    """Verify render_agent_execution_prompt.py compiles and runs help output without error."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/render_agent_execution_prompt.py"
    assert cli_path.exists()

    res = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Render an agent execution prompt" in res.stdout


def test_validate_agent_artifact_compiles():
    """Verify validate_agent_artifact.py compiles and runs help output without error."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/validate_agent_artifact.py"
    assert cli_path.exists()

    res = subprocess.run([sys.executable, str(cli_path), "--help"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "Validate an agent artifact against a work order" in res.stdout


def test_create_agent_work_order_writes_json(tmp_path):
    """Verify create_agent_work_order.py execution writes a valid JSON file to the standard path."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/create_agent_work_order.py"
    manifest_path = Path(__file__).resolve().parents[1] / "config/pipeline_manifest.json"
    
    cmd = [
        sys.executable,
        str(cli_path),
        "--date", "2026-06-25",
        "--run-id", "run-cli-test",
        "--step-id", "S2.3",
        "--runtime-mode", "DRY_RUN",
        "--base-run-dir", str(tmp_path),
        "--manifest", str(manifest_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI execution failed: {res.stderr}"
    assert "Agent work order successfully written" in res.stdout
    
    # Assert JSON file actually written
    from bet.pipeline.agent_work_orders import work_order_path_for
    wo_path = work_order_path_for(tmp_path, "2026-06-25", "run-cli-test", "S2.3")
    assert wo_path.exists()
    
    with open(wo_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["step_id"] == "S2.3"
    assert data["run_id"] == "run-cli-test"


def test_create_agent_work_order_print_json(tmp_path):
    """Verify create_agent_work_order.py prints valid JSON to stdout when --print-json is passed."""
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/create_agent_work_order.py"
    manifest_path = Path(__file__).resolve().parents[1] / "config/pipeline_manifest.json"
    
    cmd = [
        sys.executable,
        str(cli_path),
        "--date", "2026-06-25",
        "--run-id", "run-cli-test-print",
        "--step-id", "S5",
        "--runtime-mode", "LIVE_SHADOW",
        "--base-run-dir", str(tmp_path),
        "--manifest", str(manifest_path),
        "--print-json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"CLI execution failed: {res.stderr}"
    
    # stdout must be valid JSON
    data = json.loads(res.stdout)
    assert data["step_id"] == "S5"
    assert data["runtime_mode"] == "LIVE_SHADOW"
    assert data["agent"] == "bet-risk-gatekeeper"
