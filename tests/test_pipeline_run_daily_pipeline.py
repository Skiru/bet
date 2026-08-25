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


def _seed_dependencies(base_dir: Path, date: str, run_id: str) -> None:
    run_dir = base_dir / "pipeline_runs" / date / run_id
    art_dir = run_dir / "artifacts"
    data_dir = run_dir / "data"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # S1e
    (data_dir / f"{date}_s1e_event_universe.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": date, "run_id": run_id, "canonical_event_ids": ["evt_1"]
    }), encoding="utf-8")
    (art_dir / "S1e.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S1e",
        "betting_day": date, "run_id": run_id, "status": "PASS",
        "payload": {"s1e_output_path": str(data_dir / f"{date}_s1e_event_universe.json")}
    }), encoding="utf-8")

    # S2
    s2_path = data_dir / f"{date}_s2_shortlist.json"
    s2_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S2_SHORTLIST",
        "betting_day": date, "run_id": run_id, "total_candidates": 1, "candidates": [{"sport": "football"}]
    }), encoding="utf-8")
    (art_dir / "S2.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S2",
        "betting_day": date, "run_id": run_id, "status": "PASS",
        "payload": {"s2_output_path": str(s2_path)}
    }), encoding="utf-8")

    # S2.3, S2.5, S2.7, S2.9
    for sub in ["S2.3", "S2.5", "S2.7", "S2.9"]:
        (art_dir / f"{sub}.json").write_text(json.dumps({
            "schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": sub,
            "betting_day": date, "run_id": run_id, "status": "PASS", "payload": {}
        }), encoding="utf-8")

    # S3
    s3_path = data_dir / f"{date}_s3_deep_stats.json"
    s3_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S3_DEEP_STATS",
        "betting_day": date, "run_id": run_id, "analyses": []
    }), encoding="utf-8")
    (art_dir / "S3.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S3",
        "betting_day": date, "run_id": run_id, "status": "PASS",
        "payload": {"s3_output_path": str(s3_path)}
    }), encoding="utf-8")

    # S4
    s4_path = data_dir / f"{date}_s4_valuation_candidates.json"
    s4_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
        "betting_day": date, "run_id": run_id, "valuation_candidates": []
    }), encoding="utf-8")
    (art_dir / "S4.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S4",
        "betting_day": date, "run_id": run_id, "status": "PASS",
        "payload": {"s4_output_path": str(s4_path)}
    }), encoding="utf-8")


def test_create_agent_work_order_writes_json(tmp_path):
    """Verify create_agent_work_order.py execution writes a valid JSON file to the standard path."""
    _seed_dependencies(tmp_path, "2026-06-25", "run-cli-test")
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
    _seed_dependencies(tmp_path, "2026-06-25", "run-cli-test-print")
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
