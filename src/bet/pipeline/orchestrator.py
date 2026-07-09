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
    validate_s9_human_gate_artifact_for_run,
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
from bet.pipeline.orchestrator_contracts import (
    TerminalNextAction,
    TerminalOutcome,
    TerminalOutcomeReason,
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

S7_HARD_APPROVAL_BLOCK_REASON = "BLOCKED_HARD_APPROVAL_GATE"


def _load_json_object(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None

    try:
        with open(Path(path), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None

    return payload if isinstance(payload, dict) else None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced


def _classify_s7_no_action_terminal(
    *,
    blocked_at_step: str | None,
    overall_status: PipelineReadinessStatus,
    step_evidences: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if blocked_at_step != "S7" or overall_status != PipelineReadinessStatus.BLOCK:
        return None

    s7_step = next((step for step in reversed(step_evidences) if step.get("step_id") == "S7"), None)
    if not s7_step or s7_step.get("status") != PipelineReadinessStatus.BLOCK.value:
        return None

    raw_evidence = _load_json_object(s7_step.get("evidence_path"))
    if raw_evidence is None:
        return None

    if raw_evidence.get("artifact_type") != PipelineArtifactType.SCRIPT_EVIDENCE.value:
        return None
    if raw_evidence.get("step_id") != "S7":
        return None
    if raw_evidence.get("status") != PipelineReadinessStatus.BLOCK.value:
        return None

    blocked_reasons = raw_evidence.get("blocked_reasons")
    if not isinstance(blocked_reasons, list) or S7_HARD_APPROVAL_BLOCK_REASON not in blocked_reasons:
        return None

    if raw_evidence.get("production_selectable") is not False:
        return None
    if raw_evidence.get("betting_decisions_enabled") is not False:
        return None
    if raw_evidence.get("no_pick_edge_stake_coupon_emitted") is not True:
        return None

    payload = raw_evidence.get("payload")
    if not isinstance(payload, dict):
        return None

    total_candidates = _coerce_int(payload.get("total_candidates"))
    approved_count = _coerce_int(payload.get("approved_count"))
    rejected_count = _coerce_int(payload.get("rejected_count"))
    if total_candidates is None or approved_count is None or rejected_count is None:
        return None
    if total_candidates <= 0:
        return None
    if approved_count != 0 or rejected_count != total_candidates:
        return None
    if payload.get("s7_input_source_step") != "S4":
        return None

    payload_production_selectable = payload.get("production_selectable")
    if payload_production_selectable is not None and payload_production_selectable is not False:
        return None

    payload_betting_decisions_enabled = payload.get("betting_decisions_enabled")
    if payload_betting_decisions_enabled is not None and payload_betting_decisions_enabled is not False:
        return None

    payload_no_coupon = payload.get("no_pick_edge_stake_coupon_emitted")
    if payload_no_coupon is not None and payload_no_coupon is not True:
        return None

    return {
        "terminal_outcome": TerminalOutcome.NO_ACTION.value,
        "terminal_outcome_reason": TerminalOutcomeReason.S7_HARD_GATE_NO_APPROVED_CANDIDATES.value,
        "valid_no_action_terminal": True,
        "no_bet_day": True,
        "no_action_step": "S7",
        "no_action_candidate_count": total_candidates,
        "no_action_rejected_count": rejected_count,
        "ready_for_human_gate_test": False,
        "ready_for_production_execution": False,
        "next_action": TerminalNextAction.NO_BET_REVIEW_OR_UPSTREAM_DATA_ENRICHMENT.value,
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
        self.command_request_count = 0
        self.executed_count = 0
        self.failed_count = 0
        self.unresolved_count = 0

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

            work_order_path: Optional[str] = None

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
                    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
                    # Generate work order JSON under run artifact directory
                    wo = build_agent_work_order(
                        betting_day=self.betting_day,
                        run_id=self.run_id,
                        step_id=sid,
                        runtime_mode=self.runtime_mode.value,
                        base_dir=gate_base_dir,
                    )
                    written_wo_path = write_agent_work_order(wo, gate_base_dir)
                    work_order_path = str(written_wo_path)

                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                    self.blockers.append(f"Missing required agent artifact for step {sid}")
                else:
                    try:
                        with open(expected_path, "r", encoding="utf-8") as f:
                            raw = json.load(f)
                        artifact, issues = validate_pipeline_artifact(
                            raw,
                            sid,
                            enforce_required_gate=False,
                            allow_block_status=True,
                        )

                        from bet.pipeline.agent_work_orders import build_agent_work_order
                        from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order

                        wo = build_agent_work_order(
                            betting_day=self.betting_day,
                            run_id=self.run_id,
                            step_id=sid,
                            runtime_mode=self.runtime_mode.value,
                            base_dir=gate_base_dir,
                        )
                        wo_errors = validate_agent_artifact_for_work_order(raw, wo.to_jsonable())

                        if wo_errors:
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                            for err in wo_errors:
                                self.blockers.append(f"Step {sid} contract validation failure: {err}")
                        elif raw.get("status") == "COMMAND_REQUEST":
                            self.command_request_count += 1
                            cmd_req = raw.get("command_request") or raw.get("payload", {}).get("command_request")
                            if cmd_req:
                                if self.verbose:
                                    print(f"Intercepted COMMAND_REQUEST from subagent: {cmd_req}")
                                import shlex
                                import hashlib
                                argv = []
                                timeout_seconds = 300
                                expected_exit_code = 0
                                postconditions = ["rerun_validate_agent_artifact"]
                                cwd_dir = str(self.repo_root)
                                is_valid = True
                                if isinstance(cmd_req, dict):
                                    argv = cmd_req.get("argv")
                                    if not isinstance(argv, list) or not argv:
                                        self.blockers.append("COMMAND_REQUEST structured object missing non-empty 'argv'")
                                        is_valid = False
                                    timeout_seconds = cmd_req.get("timeout_seconds", 300)
                                    expected_exit_code = cmd_req.get("expected_exit_code", 0)
                                    postconditions = cmd_req.get("postconditions", ["rerun_validate_agent_artifact"])
                                    if cmd_req.get("cwd") == "REPO_ROOT":
                                        cwd_dir = str(self.repo_root)
                                elif isinstance(cmd_req, str):
                                    meta = [";", "&", "|", "<", ">", "$", "(", ")", "*", "?", "[", "]", "\\", "!", "{", "}"]
                                    if any(m in cmd_req for m in meta):
                                        self.blockers.append(f"COMMAND_REQUEST string contains disallowed shell metacharacters: {cmd_req}")
                                        is_valid = False
                                    else:
                                        try:
                                            argv = shlex.split(cmd_req)
                                        except Exception as e:
                                            self.blockers.append(f"Failed to split command string: {e}")
                                            is_valid = False
                                else:
                                    self.blockers.append("COMMAND_REQUEST must be a string or structured dict")
                                    is_valid = False
                                if is_valid and argv:
                                    executable = argv[0]
                                    allowed_execs = {"python", "python3", "pytest", ".venv/bin/python3", ".venv/bin/python", ".venv/bin/pytest", "sleep", "/bin/sleep"}
                                    is_safe_exec = False
                                    base_exec = os.path.basename(executable)
                                    if base_exec in allowed_execs or executable in allowed_execs:
                                        is_safe_exec = True
                                    elif executable.endswith(".py") and ("scripts/" in executable or "tools/" in executable):
                                        is_safe_exec = True
                                    if not is_safe_exec:
                                        self.blockers.append(f"COMMAND_REQUEST executable '{executable}' is not in the allowlist of safe executables")
                                        is_valid = False
                                if not is_valid or not argv:
                                    self.failed_count += 1
                                    self.unresolved_count += 1
                                    step_status = PipelineReadinessStatus.BLOCK
                                    overall_status = PipelineReadinessStatus.BLOCK
                                    blocked_at_step = sid
                                    blocked_reason = "COMMAND_REQUEST_VALIDATION_FAILED"
                                else:
                                    stdout_log_path = self.run_root / f"logs/{sid}_cmd_stdout.log"
                                    stderr_log_path = self.run_root / f"logs/{sid}_cmd_stderr.log"
                                    orig_artifact_path = expected_path.with_name(f"{sid}_command_request.json")
                                    write_json_atomic(orig_artifact_path, raw)
                                    start_time = time.time()
                                    try:
                                        res = subprocess.run(
                                            argv,
                                            shell=False,
                                            capture_output=True,
                                            text=True,
                                            cwd=cwd_dir,
                                            env=self.env,
                                            timeout=timeout_seconds,
                                        )
                                        duration = time.time() - start_time
                                        exit_code = res.returncode
                                        stdout_text = res.stdout or ""
                                        stderr_text = res.stderr or ""
                                    except subprocess.TimeoutExpired as te:
                                        duration = time.time() - start_time
                                        exit_code = -1
                                        stdout_text = te.stdout or ""
                                        stderr_text = te.stderr or ""
                                        self.blockers.append(f"COMMAND_REQUEST execution timed out after {timeout_seconds}s")
                                    except Exception as e:
                                        duration = time.time() - start_time
                                        exit_code = -1
                                        stdout_text = ""
                                        stderr_text = str(e)
                                        self.blockers.append(f"COMMAND_REQUEST execution failed: {e}")
                                    for key in ("key", "secret", "token", "password", "credential", "auth"):
                                        if key in self.env:
                                            val = self.env[key]
                                            if val and len(val) > 4:
                                                stdout_text = stdout_text.replace(val, "[REDACTED]")
                                                stderr_text = stderr_text.replace(val, "[REDACTED]")
                                    stdout_log_path.write_text(stdout_text, encoding="utf-8")
                                    stderr_log_path.write_text(stderr_text, encoding="utf-8")
                                    sha256_hash = hashlib.sha256(stdout_text.encode("utf-8")).hexdigest()
                                    evidence_artifact_path = expected_path.with_name(f"{sid}_command_evidence.json")
                                    evidence_artifact = {
                                        "schema_version": 1,
                                        "artifact_type": "SCRIPT_EVIDENCE",
                                        "step_id": f"{sid}_EXECUTION_EVIDENCE",
                                        "status": "PASS" if exit_code == expected_exit_code else "BLOCK",
                                        "betting_day": self.betting_day,
                                        "run_id": self.run_id,
                                        "exit_code": exit_code,
                                        "expected_exit_code": expected_exit_code,
                                        "duration_seconds": duration,
                                        "stdout_path": str(stdout_log_path.relative_to(self.repo_root) if stdout_log_path.is_relative_to(self.repo_root) else stdout_log_path),
                                        "stderr_path": str(stderr_log_path.relative_to(self.repo_root) if stderr_log_path.is_relative_to(self.repo_root) else stderr_log_path),
                                        "sha256": sha256_hash,
                                        "argv": argv,
                                        "postconditions": postconditions
                                    }
                                    write_json_atomic(evidence_artifact_path, evidence_artifact)
                                    postconditions_passed = True
                                    if exit_code != expected_exit_code:
                                        postconditions_passed = False
                                        self.blockers.append(f"COMMAND_REQUEST exited with code {exit_code}, expected {expected_exit_code}")
                                    if postconditions_passed:
                                        for post in postconditions:
                                            if post.startswith("artifact_exists:"):
                                                path_str = post.split(":", 1)[1]
                                                full_path = self.repo_root / path_str
                                                if not full_path.exists():
                                                    postconditions_passed = False
                                                    self.blockers.append(f"Postcondition failed: expected artifact {path_str} does not exist")
                                    if postconditions_passed:
                                        resolved_artifact = raw.copy()
                                        resolved_artifact["status"] = "PASS"
                                        rel_evidence_path = str(evidence_artifact_path.relative_to(self.repo_root) if evidence_artifact_path.is_relative_to(self.repo_root) else evidence_artifact_path)
                                        refs = list(resolved_artifact.get("evidence_refs", []))
                                        if rel_evidence_path not in refs:
                                            refs.append(rel_evidence_path)
                                        resolved_artifact["evidence_refs"] = refs
                                        if "command_request" in resolved_artifact:
                                            resolved_artifact.pop("command_request")
                                        if "command_request" in resolved_artifact.get("payload", {}):
                                            resolved_artifact["payload"].pop("command_request")
                                        from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order
                                        wo_errors = validate_agent_artifact_for_work_order(resolved_artifact, wo.to_jsonable())
                                        if wo_errors:
                                            postconditions_passed = False
                                            for err in wo_errors:
                                                self.blockers.append(f"Autopromotion validation failure: {err}")
                                        else:
                                            write_json_atomic(expected_path, resolved_artifact)
                                            self.executed_count += 1
                                            step_status = PipelineReadinessStatus.PASS
                                            evidence_path = str(expected_path)
                                    if not postconditions_passed:
                                        self.failed_count += 1
                                        self.unresolved_count += 1
                                        step_status = PipelineReadinessStatus.BLOCK
                                        overall_status = PipelineReadinessStatus.BLOCK
                                        blocked_at_step = sid
                                        blocked_reason = "COMMAND_REQUEST_POSTCONDITIONS_FAILED"
                            else:
                                self.failed_count += 1
                                self.unresolved_count += 1
                                step_status = PipelineReadinessStatus.BLOCK
                                overall_status = PipelineReadinessStatus.BLOCK
                                blocked_at_step = sid
                                blocked_reason = "COMMAND_REQUEST_MISSING_COMMAND"
                                self.blockers.append("COMMAND_REQUEST status returned but command_request is missing")
                        elif artifact is None or any(i.severity == PipelineReadinessStatus.BLOCK for i in issues):
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                            self.blockers.append(f"Invalid required agent artifact for step {sid}")
                        elif artifact.status == PipelineReadinessStatus.BLOCK:
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            evidence_path = str(expected_path)
                            blocked_reason = (
                                artifact.blocked_reasons[0]
                                if artifact.blocked_reasons
                                else BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                            )
                            if artifact.blocked_reasons:
                                self.blockers.extend(artifact.blocked_reasons)
                            else:
                                self.blockers.append(f"Step {sid} returned BLOCK without explicit reasons")
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
                        issues.extend(
                            validate_s9_human_gate_artifact_for_run(
                                raw,
                                base_dir=gate_base_dir,
                                betting_day=self.betting_day,
                                run_id=self.run_id,
                            )
                        )
                        block_issues = [issue for issue in issues if issue.severity == PipelineReadinessStatus.BLOCK]
                        if artifact is None or artifact.status != PipelineReadinessStatus.HUMAN_APPROVED or block_issues:
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_HUMAN_APPROVAL
                            if block_issues:
                                for issue in block_issues:
                                    self.blockers.append(
                                        f"Human gate artifact for step {sid} failed validation: {issue.message} [{issue.code}]"
                                    )
                            else:
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
                "work_order_path": work_order_path,
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

        human_gate_status = None
        if last_completed_step == "S8" or blocked_at_step == "S9":
            human_gate_status = "WAITING_FOR_HUMAN_APPROVAL"

        if self.unresolved_count > 0:
            overall_status = PipelineReadinessStatus.BLOCK

        no_action_terminal = _classify_s7_no_action_terminal(
            blocked_at_step=blocked_at_step,
            overall_status=overall_status,
            step_evidences=self.step_evidences,
        )

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
            "ready_for_human_gate_test": ready_for_human_gate,
            "ready_for_production_execution": False,
            "human_gate_status": human_gate_status,
            "terminal_outcome": None,
            "terminal_outcome_reason": None,
            "valid_no_action_terminal": False,
            "no_bet_day": False,
            "no_action_step": None,
            "no_action_candidate_count": None,
            "no_action_rejected_count": None,
            "next_action": None,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "command_request_count": self.command_request_count,
            "executed_count": self.executed_count,
            "failed_count": self.failed_count,
            "unresolved_count": self.unresolved_count,
        }

        if no_action_terminal is not None:
            summary.update(no_action_terminal)

        for s_ev in self.step_evidences:
            if s_ev.get("work_order_path"):
                summary["work_order_path"] = s_ev["work_order_path"]
                break

        # Write run_summary.json atomically to reports path
        summary_path = self.run_root / "run_summary.json"
        write_json_atomic(summary_path, summary)

        if self.verbose:
            print(f"Pipeline finished with status: {summary['status']}")
            print(f"Run summary saved to: {summary_path}")

        return summary
