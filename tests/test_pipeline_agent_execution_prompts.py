"""Tests for agent execution prompt rendering and validation CLIs."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from bet.pipeline.agent_artifact_contracts import agent_artifact_template_for_step
from bet.pipeline.agent_execution_prompts import (
    expected_artifact_path_from_work_order,
    load_work_order,
    render_agent_artifact_skeleton,
    render_agent_execution_prompt,
    validate_rendered_prompt,
)
from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order


def _seed_dependencies(tmp_path: Path, betting_day: str = "2026-06-25", run_id: str = "run-agent-prompt") -> None:
    run_dir = tmp_path / "pipeline_runs" / betting_day / run_id
    art_dir = run_dir / "artifacts"
    data_dir = run_dir / "data"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # S1e
    (art_dir / "S1e.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S1e",
        "betting_day": betting_day, "run_id": run_id, "status": "PASS",
        "payload": {"s1e_output_path": str(data_dir / f"{betting_day}_s1e_event_universe.json")}
    }), encoding="utf-8")
    (data_dir / f"{betting_day}_s1e_event_universe.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": betting_day, "run_id": run_id, "canonical_event_ids": ["evt_1"]
    }), encoding="utf-8")

    # S2
    s2_path = data_dir / f"{betting_day}_s2_shortlist.json"
    s2_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S2_SHORTLIST",
        "betting_day": betting_day, "run_id": run_id, "total_candidates": 1, "candidates": [{"sport": "football"}]
    }), encoding="utf-8")
    (art_dir / "S2.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S2",
        "betting_day": betting_day, "run_id": run_id, "status": "PASS",
        "payload": {"s2_output_path": str(s2_path)}
    }), encoding="utf-8")

    # S2.3, S2.5, S2.7, S2.9
    for sub in ["S2.3", "S2.5", "S2.7", "S2.9"]:
        (art_dir / f"{sub}.json").write_text(json.dumps({
            "schema_version": 1, "artifact_type": "AGENT_ARTIFACT", "step_id": sub,
            "betting_day": betting_day, "run_id": run_id, "status": "PASS", "payload": {}
        }), encoding="utf-8")

    # S3
    s3_path = data_dir / f"{betting_day}_s3_deep_stats.json"
    s3_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S3_DEEP_STATS",
        "betting_day": betting_day, "run_id": run_id, "analyses": []
    }), encoding="utf-8")
    (art_dir / "S3.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S3",
        "betting_day": betting_day, "run_id": run_id, "status": "PASS",
        "payload": {"s3_output_path": str(s3_path)}
    }), encoding="utf-8")

    # S4
    s4_path = data_dir / f"{betting_day}_s4_valuation_candidates.json"
    s4_path.write_text(json.dumps({
        "schema_version": 1, "artifact_type": "S4_VALUATION_CANDIDATE_SET_V2",
        "betting_day": betting_day, "run_id": run_id, "valuation_candidates": []
    }), encoding="utf-8")
    (art_dir / "S4.json").write_text(json.dumps({
        "schema_version": 1, "artifact_type": "SCRIPT_EVIDENCE", "step_id": "S4",
        "betting_day": betting_day, "run_id": run_id, "status": "PASS",
        "payload": {"s4_output_path": str(s4_path)}
    }), encoding="utf-8")


def _build_work_order(tmp_path: Path, step_id: str) -> dict:
    _seed_dependencies(tmp_path)
    work_order = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-agent-prompt",
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    return work_order.to_jsonable()


def _write_work_order(tmp_path: Path, step_id: str) -> Path:
    _seed_dependencies(tmp_path)
    work_order = build_agent_work_order(
        betting_day="2026-06-25",
        run_id="run-agent-prompt",
        step_id=step_id,
        runtime_mode="DRY_RUN",
        base_dir=tmp_path,
    )
    return write_agent_work_order(work_order, tmp_path)


def test_load_work_order_and_expected_artifact_path(tmp_path):
    """Verify work orders load from disk and expose the expected artifact path."""
    work_order_path = _write_work_order(tmp_path, "S2.3")
    work_order = load_work_order(work_order_path)

    assert work_order["step_id"] == "S2.3"
    assert expected_artifact_path_from_work_order(work_order) == Path(work_order["required_output"]["expected_path"])


def test_prompt_rendering_for_all_agent_steps(tmp_path):
    """Verify prompt rendering covers deterministic step-specific focus for all agent steps."""
    expected_focus = {
        "S2.3": "Focus on enrichment gaps, unknowns, missing sources, and whether gaps are bounded or blocking.",
        "S2.5": "Focus on provider observations only as source-bound enrichment evidence.",
        "S2.7": "Focus on fact reconciliation, disputed facts, unknowns, and evidence refs.",
        "S2.9": "Focus on readiness only and whether S3 may proceed.",
        "S5": "Focus on injuries/lineups, motivation/tournament context, travel/fatigue, morale/recent form, and upset/volatility risk.",
    }

    for step_id, focus_line in expected_focus.items():
        work_order = _build_work_order(tmp_path, step_id)
        prompt = render_agent_execution_prompt(work_order)
        assert focus_line in prompt
        assert validate_rendered_prompt(prompt, work_order) == []


def test_rendered_prompt_includes_input_refs_expected_path_and_forbidden_outputs(tmp_path):
    """Verify the rendered prompt includes all input refs, expected output path, and forbidden outputs."""
    work_order = _build_work_order(tmp_path, "S2.9")
    prompt = render_agent_execution_prompt(work_order)

    for ref in work_order["input_refs"]:
        assert f"step_id={ref['step_id']}" in prompt
        assert f"path={ref['path']}" in prompt
        assert f"required={ref['required']}" in prompt
        assert f"sha256={ref['sha256']}" in prompt

    assert str(expected_artifact_path_from_work_order(work_order)) in prompt
    for forbidden_output in work_order["forbidden_outputs"]:
        assert forbidden_output in prompt


def test_rendered_prompt_contains_required_safety_language_and_no_live_ack(tmp_path):
    """Verify rendered prompt includes required safety instructions and excludes live/production acknowledgments."""
    work_order = _build_work_order(tmp_path, "S5")
    prompt = render_agent_execution_prompt(work_order)

    assert "Return BLOCK instead of guessing." in prompt
    assert "Do not emit pick, edge, stake, coupon, parlay or accumulator." in prompt
    assert "Do not write to betting/data, betting/coupons, reports or production DB." in prompt
    assert "Do not call external APIs or browse externally; use only the evidence provided in the input artifacts." in prompt
    assert "BET_PIPELINE_WRITE_ACK" not in prompt
    assert "I_UNDERSTAND_LIVE_PROVIDER_CALLS" not in prompt
    assert "git push" not in prompt
    assert "production execution" not in prompt.lower()


def test_artifact_skeleton_is_safe_non_pass_and_non_approving(tmp_path):
    """Verify rendered skeleton remains a safe non-final BLOCK scaffold."""
    work_order = _build_work_order(tmp_path, "S2.9")
    skeleton = render_agent_artifact_skeleton(work_order)

    assert skeleton["status"] == "BLOCK"
    assert skeleton["blocked_reasons"] == ["TEMPLATE_NOT_FILLED"]
    assert skeleton["production_selectable"] is False
    assert skeleton["betting_decisions_enabled"] is False
    assert skeleton["no_pick_edge_stake_coupon_emitted"] is True
    assert skeleton["payload"]["approval_state"] == "NOT_FINAL_TEMPLATE"
    assert skeleton["payload"]["s3_may_proceed"] is False


def test_render_prompt_cli_prints_prompt(tmp_path):
    """Verify render_agent_execution_prompt.py prints a prompt to stdout."""
    work_order_path = _write_work_order(tmp_path, "S2.3")
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/render_agent_execution_prompt.py"

    result = subprocess.run(
        [sys.executable, str(cli_path), "--work-order", str(work_order_path), "--print"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "TASK_ID=AGENT_ARTIFACT_EXECUTION_S2.3" in result.stdout
    assert "Return BLOCK instead of guessing." in result.stdout


def test_render_prompt_cli_writes_safe_skeleton_json(tmp_path):
    """Verify render_agent_execution_prompt.py writes a safe artifact skeleton JSON."""
    work_order_path = _write_work_order(tmp_path, "S2.9")
    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/render_agent_execution_prompt.py"
    prompt_path = tmp_path / "S2.9_agent_prompt.md"
    skeleton_path = tmp_path / "S2.9_agent_artifact_skeleton.json"

    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "--work-order",
            str(work_order_path),
            "--output",
            str(prompt_path),
            "--skeleton-json",
            str(skeleton_path),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert prompt_path.exists()
    assert skeleton_path.exists()
    skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
    assert skeleton["status"] == "BLOCK"
    assert skeleton["payload"]["approval_state"] == "NOT_FINAL_TEMPLATE"
    assert str(prompt_path).startswith(str(tmp_path))
    assert str(skeleton_path).startswith(str(tmp_path))


def test_validate_agent_artifact_cli_passes_for_valid_block_artifact(tmp_path):
    """Verify validate_agent_artifact.py returns PASS for a valid BLOCK artifact."""
    work_order_path = _write_work_order(tmp_path, "S2.3")
    work_order = load_work_order(work_order_path)
    artifact_path = tmp_path / "S2.3_artifact.json"
    artifact = agent_artifact_template_for_step("S2.3", "2026-06-25", "run-agent-prompt")
    artifact["blocked_reasons"] = ["UPSTREAM_DATA_MISSING"]
    artifact["unknowns"] = []
    artifact["payload"] = {
        "enrichment_gaps": ["missing_fixture_identity"],
        "gaps_status": "blocking",
        "approval_state": "S2.3_BLOCK_OUTPUT",
    }
    artifact["work_order_id"] = work_order["work_order_id"]
    from bet.pipeline.run_evidence import sha256_file
    artifact["work_order_sha256"] = sha256_file(work_order_path)
    artifact["producer_agent_id"] = work_order["agent"]
    artifact["agent_id"] = work_order["agent"]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/validate_agent_artifact.py"
    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "--work-order",
            str(work_order_path),
            "--artifact",
            str(artifact_path),
            "--print-json",
        ],
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stderr
    assert payload["verdict"] == "PASS"
    assert payload["errors"] == []
    assert payload["work_order_id"] == work_order["work_order_id"]


def test_validate_agent_artifact_cli_fails_for_template_forced_to_pass(tmp_path):
    """Verify validate_agent_artifact.py returns FAIL for a template forced to PASS."""
    work_order_path = _write_work_order(tmp_path, "S2.9")
    artifact_path = tmp_path / "S2.9_forced_pass.json"
    artifact = agent_artifact_template_for_step("S2.9", "2026-06-25", "run-agent-prompt")
    artifact["status"] = "PASS"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/validate_agent_artifact.py"
    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "--work-order",
            str(work_order_path),
            "--artifact",
            str(artifact_path),
            "--print-json",
        ],
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode != 0
    assert payload["verdict"] == "FAIL"
    assert any("point_in_time_as_of" in error for error in payload["errors"])


def test_validate_agent_artifact_cli_fails_for_s29_pass_with_only_s3_may_proceed(tmp_path):
    """Verify validate_agent_artifact.py returns FAIL when S2.9 PASS only sets s3_may_proceed=true."""
    work_order_path = _write_work_order(tmp_path, "S2.9")
    artifact_path = tmp_path / "S2.9_invalid_pass.json"
    artifact = agent_artifact_template_for_step("S2.9", "2026-06-25", "run-agent-prompt")
    artifact.update(
        {
            "status": "PASS",
            "point_in_time_as_of": "2026-06-25T14:00:00Z",
            "source_bound": True,
            "sources": ["validated-source"],
            "blocked_reasons": [],
            "evidence_refs": [
                "artifact_S2.3_run-agent-prompt",
                "artifact_S2.5_run-agent-prompt",
                "artifact_S2.7_run-agent-prompt",
            ],
            "payload": {"s3_may_proceed": True},
            "unknowns": [],
        }
    )
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    cli_path = Path(__file__).resolve().parents[1] / "scripts/pipeline_steps/validate_agent_artifact.py"
    result = subprocess.run(
        [
            sys.executable,
            str(cli_path),
            "--work-order",
            str(work_order_path),
            "--artifact",
            str(artifact_path),
            "--print-json",
        ],
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode != 0
    assert payload["verdict"] == "FAIL"
    assert any("readiness verdict" in error for error in payload["errors"])
    assert any("must not rely on s3_may_proceed alone" in error for error in payload["errors"])
