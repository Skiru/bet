"""Focused tests for current-step agent BLOCK handling and canonical input refs."""
from __future__ import annotations

import json
import shutil
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


def _seed_all_up_to_step(base_dir: Path, target_step: str) -> None:
    from bet.pipeline.agent_work_orders import get_source_head, get_manifest_sha
    import hashlib
    curr_source_head = get_source_head(base_dir)
    curr_manifest_sha = get_manifest_sha(base_dir)

    steps_execution_modes = {
        "S0": "script",
        "S1": "script",
        "S1e": "script",
        "S2": "script",
        "S2.3": "agent_artifact",
        "S2.5": "agent_artifact",
        "S2.7": "agent_artifact",
        "S2.9": "agent_artifact",
        "S3": "script",
        "S4": "script",
        "S5": "agent_artifact",
        "S6": "script",
        "S7": "script",
        "S7b": "script",
        "S8": "script",
        "S9": "human_gate"
    }

    all_steps = ["S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5", "S6"]
    limit_idx = all_steps.index(target_step)

    for sid in all_steps[:limit_idx]:
        mode = steps_execution_modes[sid]
        path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, sid)
        path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "script":
            payload = {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": sid,
                "status": "PASS",
                "betting_day": BETTING_DAY,
                "run_id": RUN_ID,
                "payload": {}
            }
            write_json_atomic(path, payload)
        elif mode == "agent_artifact":
            from bet.pipeline.manifest import load_pipeline_manifest
            from bet.pipeline.agent_work_orders import discover_input_refs_for_step
            manifest = load_pipeline_manifest()
            refs = discover_input_refs_for_step(sid, base_dir, BETTING_DAY, RUN_ID, manifest)
            input_refs_json = [r.to_jsonable() for r in refs]

            p_wo_path = base_dir / "pipeline_runs" / BETTING_DAY / RUN_ID / "artifacts" / f"{sid}_work_order.json"
            p_wo_data = {
                "schema_version": 1,
                "work_order_id": f"WO-{RUN_ID}-{sid}",
                "work_order_type": "AGENT_WORK_ORDER",
                "pipeline_id": "daily-pipeline",
                "betting_day": BETTING_DAY,
                "run_id": RUN_ID,
                "step_id": sid,
                "agent": "bet-researcher" if "S2" in sid else "bet-risk-gatekeeper",
                "runtime_mode": "DRY_RUN",
                "created_at": "2026-06-25T12:00:00Z",
                "status": "PASS",
                "input_refs": input_refs_json,
                "required_output": {
                    "expected_path": str(path),
                    "required_statuses": ["PASS", "BLOCK"],
                    "schema_requirements": {},
                    "forbidden_outputs": [],
                    "hard_rules": [],
                },
                "hard_rules": [],
                "forbidden_outputs": [],
                "instructions": {},
                "source_head": curr_source_head,
                "manifest_sha256": curr_manifest_sha,
            }
            write_json_atomic(p_wo_path, p_wo_data)
            wo_sha = hashlib.sha256(p_wo_path.read_bytes()).hexdigest()

            payload = _agent_artifact(sid, "PASS", base_dir)
            payload["producer_agent_id"] = "bet-researcher" if "S2" in sid else "bet-risk-gatekeeper"
            payload["work_order_id"] = f"WO-{RUN_ID}-{sid}"
            payload["work_order_sha256"] = wo_sha
            write_json_atomic(path, payload)


def _agent_artifact(step_id: str, status: str, base_dir: Path | None = None) -> dict[str, object]:
    payload: dict[str, object] = {}
    evidence_refs: list[str] = []
    sources: list[str] = []
    blocked_reasons: list[str] = []
    point_in_time_as_of = "2026-06-26T10:00:00Z"
    source_bound = True

    if step_id == "S2.9" and status == "PASS":
        s2_3_sha = "dummy"
        s2_5_sha = "dummy"
        s2_7_sha = "dummy"
        if base_dir is not None:
            from bet.pipeline.agent_work_orders import calculate_sha256
            s2_3_path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, "S2.3")
            s2_5_path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, "S2.5")
            s2_7_path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, "S2.7")
            s2_3_sha = calculate_sha256(s2_3_path) or "dummy"
            s2_5_sha = calculate_sha256(s2_5_path) or "dummy"
            s2_7_sha = calculate_sha256(s2_7_path) or "dummy"

        payload = {
            "readiness": "PASS",
            "readiness_basis": "S2.3/S2.5/S2.7 validated",
            "s3_may_proceed": True,
            "predecessor_bindings": [
                {"step_id": "S2.3", "path": "artifacts/S2.3.json", "sha256": s2_3_sha, "artifact_type": "AGENT_ARTIFACT", "betting_day": BETTING_DAY, "run_id": RUN_ID, "status": "PASS"},
                {"step_id": "S2.5", "path": "artifacts/S2.5.json", "sha256": s2_5_sha, "artifact_type": "AGENT_ARTIFACT", "betting_day": BETTING_DAY, "run_id": RUN_ID, "status": "PASS"},
                {"step_id": "S2.7", "path": "artifacts/S2.7.json", "sha256": s2_7_sha, "artifact_type": "AGENT_ARTIFACT", "betting_day": BETTING_DAY, "run_id": RUN_ID, "status": "PASS"},
            ]
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


def _write_agent_artifact(base_dir: Path, step_id: str, status: str, runtime_mode: str = "LIVE_SHADOW") -> Path:
    _seed_all_up_to_step(base_dir, step_id)
    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
    import hashlib
    wo = build_agent_work_order(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        step_id=step_id,
        runtime_mode=runtime_mode,
        base_dir=base_dir,
    )
    wo_path = write_agent_work_order(wo, base_dir)
    wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

    art = _agent_artifact(step_id, status, base_dir)
    art["producer_agent_id"] = wo.agent
    art["work_order_id"] = wo.work_order_id
    art["work_order_sha256"] = wo_sha

    path = artifact_path_for(base_dir, BETTING_DAY, RUN_ID, step_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, art)
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
    _seed_all_up_to_step(tmp_path, "S5")
    work_order = build_agent_work_order(
        betting_day=BETTING_DAY,
        run_id=RUN_ID,
        step_id="S5",
        runtime_mode="LIVE_SHADOW",
        base_dir=tmp_path,
    )

    import hashlib
    from bet.pipeline.agent_work_orders import write_agent_work_order
    wo_path = write_agent_work_order(work_order, tmp_path)
    wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

    art = _agent_artifact("S5", "BLOCK", tmp_path)
    art["producer_agent_id"] = "bet-risk-gatekeeper"
    art["work_order_id"] = work_order.work_order_id
    art["work_order_sha256"] = wo_sha

    errors = validate_agent_artifact_for_work_order(art, work_order.to_jsonable())
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
    print("\nS5 BLOCK BLOCKERS:", summary["blockers"])

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
    _write_agent_artifact(tmp_path, "S5", "PASS", runtime_mode="DRY_RUN")

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
        print("\nS5 PASS BLOCKERS:", summary["blockers"])

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
    shutil.rmtree(base_dir, ignore_errors=True)
    _write_s5_prereqs(base_dir)
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
