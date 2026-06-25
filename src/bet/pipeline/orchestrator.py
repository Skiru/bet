"""Orchestrator for the S0-S10 manifest-driven betting pipeline."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bet.pipeline.manifest import (
    discover_repo_root,
    load_pipeline_manifest,
    validate_pipeline_manifest,
    get_step_order,
)
from bet.pipeline.runtime_modes import (
    RuntimeMode,
    parse_runtime_mode,
    validate_runtime_mode_acks,
    LIVE_ACK_KEY,
    LIVE_ACK_VALUE,
)
from bet.pipeline.runtime_paths import (
    resolve_run_root,
    runtime_artifact_dir,
    runtime_data_dir,
    runtime_coupon_dir,
    build_runtime_env,
)
from bet.pipeline.readiness_contracts import (
    PipelineReadinessStatus,
    PipelineArtifactType,
    StepEvidence,
    GateDecision,
    PipelineArtifact,
)
from bet.pipeline.artifact_gate import (
    evaluate_gate_before_step,
    validate_pipeline_artifact,
    artifact_path_for,
)
from bet.pipeline.run_evidence import (
    utc_now_iso,
    manifest_hash,
    repo_head_sha,
    write_json_atomic,
)
from bet.pipeline.integration_artifacts import (
    write_script_evidence,
    script_evidence_path,
)

# Ensure data directory references correct sandboxed path during execution
from bet.pipeline.state import PipelineState


class BlockedReason:
    BLOCKED_WAITING_FOR_AGENT_ARTIFACT = "BLOCKED_WAITING_FOR_AGENT_ARTIFACT"
    BLOCKED_WAITING_FOR_HUMAN_APPROVAL = "BLOCKED_WAITING_FOR_HUMAN_APPROVAL"
    BLOCKED_LIVE_NETWORK_ACK_MISSING = "BLOCKED_LIVE_NETWORK_ACK_MISSING"
    BLOCKED_SCRIPT_EVIDENCE_MISSING = "BLOCKED_SCRIPT_EVIDENCE_MISSING"


LIVE_SHADOW_WRAPPERS_REQUIRING_ACK = {
    "scripts/pipeline_steps/s0_settler.py",
    "scripts/pipeline_steps/s1_discover.py",
    "scripts/pipeline_steps/s2_tipsters.py",
    "scripts/pipeline_steps/s4_valuator.py",
    "scripts/pipeline_steps/s7_validate.py",
}


class Orchestrator:
    """Runnable manifest-driven pipeline orchestrator."""

    def __init__(
        self,
        betting_day: str,
        run_id: str,
        runtime_mode: RuntimeMode | str = RuntimeMode.DRY_RUN,
        manifest_path: Optional[Path] = None,
        base_run_dir: Optional[Path] = None,
        allow_live_network: bool = False,
        allow_write: bool = False,
        artifact_dir: Optional[Path] = None,
        verbose: bool = False,
    ) -> None:
        self.betting_day = betting_day
        self.run_id = run_id
        self.runtime_mode = parse_runtime_mode(runtime_mode)
        self.repo_root = discover_repo_root()
        self.allow_live_network = allow_live_network
        self.allow_write = allow_write
        self.verbose = verbose

        # Resolve manifest path
        if manifest_path is None:
            self.manifest_path = self.repo_root / "config/pipeline_manifest.json"
        else:
            self.manifest_path = Path(manifest_path)

        # Load and validate manifest
        self.manifest = load_pipeline_manifest(self.manifest_path)
        manifest_errors = validate_pipeline_manifest(self.manifest, self.repo_root)
        if manifest_errors:
            raise ValueError(f"Invalid pipeline manifest: {manifest_errors}")

        # Assert expected pipeline ID and global fail-closed rules
        if self.manifest.pipeline_id != "bet_pipeline_v1":
            raise ValueError(f"Unexpected pipeline_id in manifest: {self.manifest.pipeline_id}")
        if not self.manifest.global_rules.get("fail_closed", False):
            raise ValueError("Pipeline manifest global rule 'fail_closed' must be enabled")

        # Resolve paths
        self.run_root = resolve_run_root(self.betting_day, self.run_id, base_run_dir)
        self.run_data_dir = runtime_data_dir(self.run_root)
        self.run_coupon_dir = runtime_coupon_dir(self.run_root)

        # Override artifact directory if requested
        if artifact_dir is not None:
            self.run_artifact_dir = Path(artifact_dir)
        else:
            self.run_artifact_dir = runtime_artifact_dir(self.run_root)

        # Setup sandbox environment
        self.env = os.environ.copy()
        sandbox_env = build_runtime_env(self.runtime_mode, self.betting_day, self.run_id, base_run_dir)
        self.env.update(sandbox_env)
        if artifact_dir is not None:
            self.env["BET_PIPELINE_ARTIFACT_DIR"] = str(self.run_artifact_dir)

        # Set up state path override
        import bet.pipeline.state
        bet.pipeline.state.DATA_DIR = self.run_data_dir

        # Ensure all sandboxed directories exist
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.run_data_dir.mkdir(parents=True, exist_ok=True)
        self.run_coupon_dir.mkdir(parents=True, exist_ok=True)
        self.run_artifact_dir.mkdir(parents=True, exist_ok=True)
        (self.run_root / "logs").mkdir(parents=True, exist_ok=True)

        self.warnings: List[str] = []
        self.blockers: List[str] = []
        self.step_evidences: List[Dict[str, Any]] = []

    def run(
        self,
        start_step: Optional[str] = None,
        stop_after_step: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the pipeline sequence under manifest-driven rules."""
        steps = self.manifest.steps
        step_ids = [s.id for s in steps if s.id]

        # Resolve index boundaries for subset execution
        start_idx = 0
        if start_step:
            if start_step not in step_ids:
                raise ValueError(f"Start step '{start_step}' not found in manifest")
            start_idx = step_ids.index(start_step)

        stop_idx = len(step_ids) - 1
        if stop_after_step:
            if stop_after_step not in step_ids:
                raise ValueError(f"Stop step '{stop_after_step}' not found in manifest")
            stop_idx = step_ids.index(stop_after_step)

        if start_idx > stop_idx:
            raise ValueError(f"Start step '{start_step}' is after stop step '{stop_after_step}'")

        last_completed_step: Optional[str] = None
        blocked_at_step: Optional[str] = None
        overall_status = PipelineReadinessStatus.PASS

        # Initialize/load PipelineState in the sandboxed database
        state = PipelineState.load(self.betting_day)

        for idx, step in enumerate(steps):
            sid = step.id
            if not sid:
                continue

            # Determine whether the step is active, skipped, or not yet reached
            is_skipped = idx < start_idx or idx > stop_idx

            if is_skipped:
                # Log skipped step
                self.step_evidences.append({
                    "step_id": sid,
                    "execution_mode": step.execution_mode,
                    "status": "SKIPPED",
                    "wrapper": step.wrapper,
                    "return_code": None,
                    "started_at": None,
                    "finished_at": None,
                    "stdout_path": None,
                    "stderr_path": None,
                    "evidence_path": None,
                    "blocked_reason": None,
                })
                continue

            if self.verbose:
                print(f"--- Executing Step {sid}: {step.name} ({step.execution_mode}) ---")

            # 1. Enforce gates and check prerequisite artifacts
            # We construct a base_dir for the gate evaluator to work properly
            gate_base_dir = self.run_artifact_dir.parent.parent.parent
            decision = evaluate_gate_before_step(sid, gate_base_dir, self.betting_day, self.run_id)

            if decision.verdict == PipelineReadinessStatus.BLOCK:
                blocked_at_step = sid
                overall_status = PipelineReadinessStatus.BLOCK
                self.blockers.extend(decision.failed_requirements)
                self.step_evidences.append({
                    "step_id": sid,
                    "execution_mode": step.execution_mode,
                    "status": "BLOCK",
                    "wrapper": step.wrapper,
                    "return_code": None,
                    "started_at": utc_now_iso(),
                    "finished_at": utc_now_iso(),
                    "stdout_path": None,
                    "stderr_path": None,
                    "evidence_path": None,
                    "blocked_reason": f"Prerequisite gate failed: {decision.failed_requirements}",
                })
                break

            # Add any gate warnings
            self.warnings.extend(decision.warnings)

            # 2. Live network security guard for LIVE_SHADOW mode
            if self.runtime_mode == RuntimeMode.LIVE_SHADOW and step.wrapper in LIVE_SHADOW_WRAPPERS_REQUIRING_ACK:
                live_ack = self.env.get(LIVE_ACK_KEY, "")
                if not self.allow_live_network or live_ack != LIVE_ACK_VALUE:
                    blocked_at_step = sid
                    overall_status = PipelineReadinessStatus.BLOCK
                    block_msg = "LIVE_SHADOW execution blocked: live network acknowledgment missing."
                    self.blockers.append(block_msg)
                    self.step_evidences.append({
                        "step_id": sid,
                        "execution_mode": step.execution_mode,
                        "status": "BLOCK",
                        "wrapper": step.wrapper,
                        "return_code": None,
                        "started_at": utc_now_iso(),
                        "finished_at": utc_now_iso(),
                        "stdout_path": None,
                        "stderr_path": None,
                        "evidence_path": None,
                        "blocked_reason": BlockedReason.BLOCKED_LIVE_NETWORK_ACK_MISSING,
                    })
                    break

            # 3. Execution based on step mode
            started_at = utc_now_iso()
            step_status = PipelineReadinessStatus.PASS
            return_code: Optional[int] = None
            stdout_path: Optional[str] = None
            stderr_path: Optional[str] = None
            evidence_path: Optional[str] = None
            blocked_reason: Optional[str] = None

            if step.execution_mode == "script":
                # Execute wrapper script as a subprocess
                if not step.wrapper:
                    raise ValueError(f"Step '{sid}' configured with execution_mode=script but missing wrapper path")

                wrapper_path = self.repo_root / step.wrapper
                if not wrapper_path.exists():
                    raise FileNotFoundError(f"Wrapper script for step '{sid}' not found at: {wrapper_path}")

                cmd = [sys.executable, str(wrapper_path), "--date", self.betting_day, "--run-id", self.run_id, "--runtime-mode", self.runtime_mode.value]
                if self.allow_live_network:
                    cmd.append("--allow-live-network")
                if self.allow_write:
                    cmd.append("--allow-write")

                stdout_file_path = self.run_root / "logs" / f"{sid}_stdout.log"
                stderr_file_path = self.run_root / "logs" / f"{sid}_stderr.log"
                stdout_path = str(stdout_file_path)
                stderr_path = str(stderr_file_path)

                try:
                    with open(stdout_file_path, "w", encoding="utf-8") as out_f, open(stderr_file_path, "w", encoding="utf-8") as err_f:
                        res = subprocess.run(
                            cmd,
                            env=self.env,
                            stdout=out_f,
                            stderr=err_f,
                            cwd=str(self.repo_root),
                        )
                        return_code = res.returncode
                except Exception as e:
                    return_code = -1
                    with open(stderr_file_path, "a", encoding="utf-8") as err_f:
                        err_f.write(f"\nSubprocess failed to launch: {e}\n")

                canonical_evidence = script_evidence_path(sid, self.env)
                evidence_exists = canonical_evidence and canonical_evidence.exists()
                
                evidence_status = None
                evidence_blocked_reasons = []
                if evidence_exists:
                    try:
                        with open(canonical_evidence, "r", encoding="utf-8") as f:
                            raw_ev = json.load(f)
                        evidence_status = raw_ev.get("status")
                        evidence_blocked_reasons = raw_ev.get("blocked_reasons", [])
                    except Exception:
                        pass

                if return_code == 0:
                    if evidence_exists:
                        if evidence_status in ("BLOCK", "FAILED"):
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            evidence_path = str(canonical_evidence)
                            if evidence_blocked_reasons:
                                for r in evidence_blocked_reasons:
                                    self.blockers.append(f"Step {sid} blocked: {r}")
                            else:
                                self.blockers.append(f"Step {sid} completed with {evidence_status} status")
                        else:
                            step_status = PipelineReadinessStatus.PASS
                            evidence_path = str(canonical_evidence)
                    else:
                        step_status = PipelineReadinessStatus.BLOCK
                        overall_status = PipelineReadinessStatus.BLOCK
                        blocked_at_step = sid
                        blocked_reason = BlockedReason.BLOCKED_SCRIPT_EVIDENCE_MISSING
                        self.blockers.append(f"Canonical script evidence missing for step '{sid}'")
                else:
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    
                    if evidence_exists:
                        evidence_path = str(canonical_evidence)
                        if evidence_blocked_reasons:
                            for r in evidence_blocked_reasons:
                                self.blockers.append(f"Step {sid} blocked: {r}")
                        else:
                            self.blockers.append(f"Step {sid} failed with status {evidence_status}")
                    else:
                        self.blockers.append(f"Wrapper script for step '{sid}' failed with exit code {return_code}")

            elif step.execution_mode == "agent_artifact":
                # Check for existing agent artifact
                expected_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                if not expected_path.exists():
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                    self.blockers.append(f"Missing required agent artifact for step {sid}")
                else:
                    try:
                        with open(expected_path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        artifact, issues = validate_pipeline_artifact(raw, sid)
                        if artifact is None or any(i.severity == PipelineReadinessStatus.BLOCK for i in issues):
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                            self.blockers.append(f"Invalid required agent artifact for step {sid}")
                        else:
                            step_status = artifact.status
                            evidence_path = str(expected_path)
                    except Exception as e:
                        step_status = PipelineReadinessStatus.BLOCK
                        overall_status = PipelineReadinessStatus.BLOCK
                        blocked_at_step = sid
                        blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                        self.blockers.append(f"Failed to read/validate agent artifact for step {sid}: {e}")

            elif step.execution_mode == "human_gate":
                # Validate S9 human gate artifact
                expected_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                if not expected_path.exists():
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_HUMAN_APPROVAL
                    self.blockers.append(f"Missing required human gate artifact for step {sid}")
                else:
                    try:
                        with open(expected_path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        artifact, issues = validate_pipeline_artifact(raw, sid)
                        if artifact is None or artifact.status != PipelineReadinessStatus.HUMAN_APPROVED:
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_HUMAN_APPROVAL
                            self.blockers.append(f"Human gate artifact for step {sid} is not approved or has issues")
                        else:
                            step_status = PipelineReadinessStatus.PASS
                            evidence_path = str(expected_path)
                    except Exception as e:
                        step_status = PipelineReadinessStatus.BLOCK
                        overall_status = PipelineReadinessStatus.BLOCK
                        blocked_at_step = sid
                        blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_HUMAN_APPROVAL
                        self.blockers.append(f"Failed to read/validate human gate artifact for step {sid}: {e}")

            elif step.execution_mode == "state_only":
                # Write state marker evidence
                state_marker = {
                    "schema_version": 1,
                    "artifact_type": "STATE_MARKER",
                    "step_id": sid,
                    "status": "PASS",
                    "betting_day": self.betting_day,
                    "run_id": self.run_id,
                    "sport": None,
                    "fixture_id": None,
                    "fixture_key": None,
                    "point_in_time_as_of": utc_now_iso(),
                    "source_bound": False,
                    "no_pick_edge_stake_coupon_emitted": True,
                    "production_selectable": False,
                    "betting_decisions_enabled": False,
                    "sources": [],
                    "unknowns": [],
                    "blocked_reasons": [],
                    "evidence_refs": [],
                    "payload": {}
                }
                expected_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                expected_path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(expected_path, state_marker)
                evidence_path = str(expected_path)
                step_status = PipelineReadinessStatus.PASS

            finished_at = utc_now_iso()

            # Record step metrics
            self.step_evidences.append({
                "step_id": sid,
                "execution_mode": step.execution_mode,
                "status": step_status.value if hasattr(step_status, "value") else str(step_status),
                "wrapper": step.wrapper,
                "return_code": return_code,
                "started_at": started_at,
                "finished_at": finished_at,
                "stdout_path": stdout_path,
                "stderr_path": stderr_path,
                "evidence_path": evidence_path,
                "blocked_reason": blocked_reason,
            })

            # Halt loop if step did not pass
            if step_status not in (PipelineReadinessStatus.PASS, PipelineReadinessStatus.HUMAN_APPROVED):
                break

            # Sync and advance PipelineState on successful pass
            last_completed_step = sid
            state.advance(sid)

        # Build final run summary dict
        live_provider_calls_allowed = (
            self.allow_live_network
            and self.env.get(LIVE_ACK_KEY, "") == LIVE_ACK_VALUE
            and self.runtime_mode == RuntimeMode.LIVE_SHADOW
        )

        ready_for_human_gate = False
        if last_completed_step == "S8":
            ready_for_human_gate = True

        summary = {
            "schema_version": 1,
            "orchestrator_id": "pipeline_orchestrator_a",
            "betting_day": self.betting_day,
            "run_id": self.run_id,
            "runtime_mode": self.runtime_mode.value,
            "status": overall_status.value if hasattr(overall_status, "value") else str(overall_status),
            "last_completed_step": last_completed_step,
            "blocked_at_step": blocked_at_step,
            "steps": self.step_evidences,
            "production_db_write": False,
            "production_coupon_write": False,
            "live_provider_calls_allowed": live_provider_calls_allowed,
            "ready_for_human_gate": ready_for_human_gate,
            "ready_for_production_execution": False,
            "warnings": self.warnings,
            "blockers": self.blockers,
        }

        # Write run_summary.json atomically to reports path
        summary_path = self.run_root / "run_summary.json"
        write_json_atomic(summary_path, summary)

        if self.verbose:
            print(f"Pipeline finished with status: {summary['status']}")
            print(f"Run summary saved to: {summary_path}")

        return summary
