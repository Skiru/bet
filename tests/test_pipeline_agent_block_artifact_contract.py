"""Focused tests for current-step agent BLOCK handling and canonical input refs."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order
from bet.pipeline.agent_work_orders import build_agent_work_order
from bet.pipeline.artifact_gate import artifact_path_for, evaluate_gate_before_step
from bet.pipeline.integration_artifacts import write_script_evidence
from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.readiness_contracts import PipelineReadinessStatus
from bet.pipeline.runtime_paths import (
    build_runtime_env,
    is_system_temp_path,
    resolve_run_root,
)
from bet.pipeline.run_evidence import write_json_atomic


BETTING_DAY = "2026-06-26"
RUN_ID = "run-agent-block-contract"


def _agent_artifact(step_id: str, status: str) -> dict[str, object]:
    payload: dict[str, object] = {}
    evidence_refs: list[str] = []
    sources: list[str] = []
    blocked_reasons: list[str] = []
    point_in_time_as_of = "2026-06-26T10:00:00Z"
    source_bound = True

    if step_id == "S2.9" and status == "PASS":
        payload = {
            "readiness": "PASS",
            "readiness_basis": "S2.3/S2.5/S2.7 validated",
            "s3_may_proceed": True,
        }
        evidence_refs = ["artifact_S2.3", "artifact_S2.5", "artifact_S2.7"]
        sources = ["source-bound-enrichment"]
    elif step_id == "S5" and status == "PASS":
        payload = {
            "injuries_lineups": {"status": "checked"},
            "motivation_tournament_context": {"status": "checked"},
            "travel_fatigue": {"status": "checked"},
            "morale_recent_form": {"status": "checked"},
            "upset_volatility_risk": {"status": "checked"},
        }
        evidence_refs = ["artifact_S3", "artifact_S4", "artifact_S2.9"]
        sources = ["injury-report", "travel-brief"]
    elif step_id == "S5" and status == "BLOCK":
        payload = {
            "risk_review": "source-bound blockers remain unresolved",
        }
        evidence_refs = ["artifact_S3", "artifact_S4", "artifact_S2.9"]
        blocked_reasons = [
            "BLOCKED_S3_EVIDENCE_MISSING",
            "BLOCKED_S4_EVIDENCE_MISSING",
        ]
        point_in_time_as_of = None
        source_bound = False
    else:
        sources = ["generic-source"]

    return {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": step_id,
        "status": status,
        "betting_day": BETTING_DAY,
        "run_id": RUN_ID,
        "sport": "Football",
        "fixture_id": None,
        "fixture_key": None,
        "point_in_time_as_of": point_in_time_as_of,
        "source_bound": source_bound,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": sources,
        "unknowns": [],
        "blocked_reasons": blocked_reasons,
        "evidence_refs": evidence_refs,
        "payload": payload,
    }


def _write_agent_artifact(base_dir: Path, step_id: str, status: str) -> Path:
    path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, step_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, _agent_artifact(step_id, status))
    return path


def _write_s5_prereqs(base_dir: Path) -> None:
    run_root = resolve_run_root(BETTING_DAY, RUN_ID, base_dir)
    env = build_runtime_env("LIVE_SHADOW", BETTING_DAY, RUN_ID, base_dir=base_dir)
    assert env["BET_PIPELINE_RUN_ROOT"] == str(run_root)

    write_script_evidence(
        "S3",
        status="PASS",
        payload={"stats": True},
        sources=("stats-source",),
        evidence_refs=("s2.9",),
        environ=env,
    )
    write_script_evidence(
        "S4",
        status="PASS",
        payload={"valuation": True},
        sources=("odds-source",),
        evidence_refs=("s3",),
        environ=env,
    )
    _write_agent_artifact(base_dir, "S2.9", "PASS")


def test_validate_agent_artifact_for_work_order_accepts_s5_block(tmp_path):
    work_order = build_agent_work_order(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        step_id="S5",
        runtime_mode="LIVE_SHADOW",
        base_dir=tmp_path,
    )

    errors = validate_agent_artifact_for_work_order(_agent_artifact("S5", "BLOCK"), work_order.to_jsonable())
    assert errors == []


def test_orchestrator_accepts_valid_s5_block_as_terminal_result(tmp_path):
    _write_s5_prereqs(tmp_path)
    artifact_path = _write_agent_artifact(tmp_path, "S5", "BLOCK")

    orch = Orchestrator(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        runtime_mode="LIVE_SHADOW",
        base_run_dir=tmp_path,
    )
    summary = orch.run(start_step="S5", stop_after_step="S5")

    s5_step = next(step for step in summary["steps"] if step["step_id"] == "S5")
    assert summary["status"] == "BLOCK"
    assert summary["blocked_at_step"] == "S5"
    assert s5_step["status"] == "BLOCK"
    assert s5_step["evidence_path"] == str(artifact_path)
    assert "BLOCKED_S3_EVIDENCE_MISSING" in summary["blockers"]
    assert "BLOCKED_S4_EVIDENCE_MISSING" in summary["blockers"]
    assert "Invalid required agent artifact for step S5" not in summary["blockers"]


def test_orchestrator_advances_past_s5_on_valid_pass(tmp_path):
    _write_s5_prereqs(tmp_path)
    _write_agent_artifact(tmp_path, "S5", "PASS")

    orch = Orchestrator(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
    )

    with patch("bet.pipeline.orchestrator.run_bounded_process") as mock_run:
        def side_effect(*args, **kwargs):
            write_script_evidence(
                "S6",
                status="PASS",
                payload={"repeat_guard": True},
                sources=("repeat-check",),
                evidence_refs=("s5",),
                environ=orch.env,
            )
            result = MagicMock()
            result.returncode = 0
            return result

        mock_run.side_effect = side_effect
        summary = orch.run(start_step="S5", stop_after_step="S6")

    assert summary["status"] == "PASS"
    assert summary["last_completed_step"] == "S6"
    assert next(step for step in summary["steps"] if step["step_id"] == "S5")["status"] == "PASS"


def test_s6_prerequisite_gate_blocks_on_s5_block(tmp_path):
    _write_agent_artifact(tmp_path, "S5", "BLOCK")
    decision = evaluate_gate_before_step("S6", tmp_path, BETTING_DAY, RUN_ID)

    assert decision.verdict == PipelineReadinessStatus.BLOCK
    assert "S5" in decision.blocked_artifacts


def test_s6_prerequisite_gate_accepts_s5_pass(tmp_path):
    _write_agent_artifact(tmp_path, "S5", "PASS")
    decision = evaluate_gate_before_step("S6", tmp_path, BETTING_DAY, RUN_ID)

    assert decision.verdict == PipelineReadinessStatus.PASS
    assert "S5" in decision.accepted_artifacts


def test_s5_work_order_uses_canonical_existing_input_refs(tmp_path):
    _write_s5_prereqs(tmp_path)

    work_order = build_agent_work_order(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        step_id="S5",
        runtime_mode="LIVE_SHADOW",
        base_dir=tmp_path,
    )

    refs = {ref.step_id: ref for ref in work_order.input_refs}
    assert set(refs) == {"S3", "S4", "S2.9"}

    assert refs["S3"].artifact_kind == "SCRIPT_EVIDENCE"
    assert refs["S4"].artifact_kind == "SCRIPT_EVIDENCE"
    assert refs["S2.9"].artifact_kind == "AGENT_ARTIFACT"

    for step_id in ("S3", "S4", "S2.9"):
        assert Path(refs[step_id].path).exists()
        assert refs[step_id].sha256

    assert refs["S3"].path.endswith(f"/pipeline_runs/{BETTING_DAY}/{RUN_ID}/artifacts/S3.json")
    assert refs["S4"].path.endswith(f"/pipeline_runs/{BETTING_DAY}/{RUN_ID}/artifacts/S4.json")
    assert refs["S2.9"].path.endswith(f"/pipeline_runs/{BETTING_DAY}/{RUN_ID}/artifacts/S2.9.json")


def test_live_shadow_canonical_paths_stay_under_tmp_and_avoid_production_dirs():
    base_dir = Path("/tmp") / "bet-agent-block-contract-live-shadow"
    work_order = build_agent_work_order(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        step_id="S5",
        runtime_mode="LIVE_SHADOW",
        base_dir=base_dir,
    )

    for ref in work_order.input_refs:
        assert is_system_temp_path(ref.path)
        assert "reports/" not in ref.path
        assert "betting/data/" not in ref.path
        assert "betting/coupons/" not in ref.path
