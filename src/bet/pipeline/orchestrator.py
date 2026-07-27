"""Orchestrator for the S0-S10 manifest-driven betting pipeline."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from bet.pipeline.artifact_gate import (
    artifact_path_for,
    evaluate_gate_before_step,
    validate_pipeline_artifact,
    validate_s9_human_gate_artifact_for_run,
)
from bet.pipeline.event_accounting import (
    ACCOUNTING_BOUNDARY_STEPS,
    EventAccountingError,
    EventAccountingLedger,
)
from bet.pipeline.sharding.lifecycle import create_chunk_execution_plan, aggregate_chunks
from bet.pipeline.sharding.models import WorkOrderBudgetV1, ChunkArtifactV1, ChunkExecutionPlanV1
from bet.pipeline.integration_artifacts import (
    script_evidence_path,
    resolve_bound_step_output,
)
from bet.pipeline.contracts.registry import GLOBAL_CONTRACT_REGISTRY
from bet.pipeline.manifest import (
    discover_repo_root,
    load_pipeline_manifest,
    validate_pipeline_manifest,
)
from bet.pipeline.orchestrator_contracts import (
    TerminalNextAction,
    TerminalOutcome,
    TerminalOutcomeReason,
)
from bet.pipeline.readiness_contracts import (
    PipelineArtifactType,
    PipelineReadinessStatus,
)
from bet.pipeline.run_coordination import (
    LeaseRunLock,
    ResumeLedger,
    run_bounded_process,
)
from bet.pipeline.run_evidence import (
    manifest_hash,
    repo_head_sha,
    utc_now_iso,
    write_json_atomic,
)
from bet.pipeline.runtime_modes import (
    LIVE_ACK_KEY,
    LIVE_ACK_VALUE,
    RuntimeMode,
    parse_runtime_mode,
)
from bet.pipeline.runtime_paths import (
    build_runtime_env,
    resolve_run_root,
    runtime_artifact_dir,
    runtime_coupon_dir,
    runtime_data_dir,
    validate_run_identifiers,
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
        with open(Path(path), encoding="utf-8") as handle:
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
        manifest_path: Path | None = None,
        base_run_dir: Path | None = None,
        allow_live_network: bool = False,
        allow_write: bool = False,
        artifact_dir: Path | None = None,
        verbose: bool = False,
    ) -> None:
        self.betting_day, self.run_id = validate_run_identifiers(betting_day, run_id)
        self.runtime_mode = parse_runtime_mode(runtime_mode)
        self.repo_root = discover_repo_root()

        # Import-origin guard before orchestration
        import bet
        expected_bet_file = self.repo_root / "src" / "bet" / "__init__.py"
        if Path(bet.__file__).resolve() != expected_bet_file.resolve():
            raise RuntimeError(
                f"Import-origin violation: bet package imported from unexpected location: {bet.__file__} (expected {expected_bet_file})"
            )
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
        env_run_root = os.environ.get("BET_PIPELINE_RUN_ROOT")
        if env_run_root:
            raw_run_root = Path(env_run_root)
            current = raw_run_root
            while current != current.parent:
                if current.exists() and current.is_symlink():
                    raise ValueError("RUN_PATH_SYMLINK_FORBIDDEN")
                current = current.parent
            self.run_root = raw_run_root.resolve(strict=False)
            if self.run_root.name != self.run_id or self.run_root.parent.name != self.betting_day:
                raise ValueError("RUN_ROOT_IDENTITY_BINDING_MISMATCH")
            if base_run_dir is not None:
                expected_root = resolve_run_root(self.betting_day, self.run_id, base_run_dir)
                if self.run_root != expected_root:
                    raise ValueError("RUN_ROOT_CONFIGURED_BASE_MISMATCH")
            else:
                approved_roots = (
                    (self.repo_root / "reports" / "pipeline_runs").resolve(strict=False),
                    Path(tempfile.gettempdir()).resolve(strict=False),
                )
                if not any(
                    self.run_root == root or self.run_root.is_relative_to(root)
                    for root in approved_roots
                ):
                    raise ValueError("RUN_ROOT_OUTSIDE_APPROVED_BASE")
        else:
            self.run_root = resolve_run_root(self.betting_day, self.run_id, base_run_dir)
        self.run_data_dir = runtime_data_dir(self.run_root)
        self.run_coupon_dir = runtime_coupon_dir(self.run_root)

        # Override artifact directory if requested
        if artifact_dir is not None:
            self.run_artifact_dir = Path(artifact_dir).resolve(strict=False)
        else:
            self.run_artifact_dir = runtime_artifact_dir(self.run_root)
        if self.run_artifact_dir != runtime_artifact_dir(self.run_root).resolve(strict=False):
            raise ValueError("ARTIFACT_DIR_MUST_BE_CANONICAL_RUN_ARTIFACT_DIR")

        # Setup sandbox environment
        self.env = build_runtime_env(self.runtime_mode, self.betting_day, self.run_id, base_run_dir)
        self.env["BET_PIPELINE_RUN_ROOT"] = str(self.run_root)
        self.env["BET_PIPELINE_DATA_DIR"] = str(self.run_data_dir)
        self.env["BET_PIPELINE_COUPON_DIR"] = str(self.run_coupon_dir)
        self.env["BET_PIPELINE_ARTIFACT_DIR"] = str(self.run_artifact_dir)
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

        self.warnings: list[str] = []
        self.blockers: list[str] = []
        self.step_evidences: list[dict[str, Any]] = []
        self.command_request_count = 0
        self.executed_count = 0
        self.failed_count = 0
        self.unresolved_count = 0
        self._manifest_sha = manifest_hash(self.repo_root)
        self._main_sha = str(repo_head_sha(self.repo_root))
        lease_seconds = float(self.manifest.runtime_contract.get("lock_lease_seconds", 60))
        self._run_lock = LeaseRunLock(self.run_root, self.run_id, lease_seconds=lease_seconds)
        self._resume_ledger = ResumeLedger(
            self.run_root,
            run_id=self.run_id,
            betting_day=self.betting_day,
            main_sha=self._main_sha,
            manifest_sha=self._manifest_sha,
        )
        self.env["BET_PIPELINE_RUN_AS_OF_UTC"] = self._resume_ledger.binding["run_as_of_utc"]

    def _handle_sharded_agent_step(self, step_id: str, gate_base_dir: Path, parent_wo: Any) -> tuple[bool, str | None, Path | None]:
        """Check if S1e event scope requires sharding. If so, build chunk plan and aggregate chunks if available."""
        from bet.pipeline.sharding.models import WorkOrderBudgetV1, ChunkArtifactV1
        from bet.pipeline.sharding.lifecycle import create_chunk_execution_plan, aggregate_chunks
        from bet.pipeline.contracts.canonical_json import hash_canonical_json

        # 1. Derive event IDs from parent work order's input refs and active records
        event_ids: list[str] = []
        if hasattr(parent_wo, "input_refs") and parent_wo.input_refs:
            for ref in parent_wo.input_refs:
                ref_path_str = ref.path if hasattr(ref, "path") else ref.get("path", "") if isinstance(ref, dict) else ""
                ref_path = Path(ref_path_str) if ref_path_str else None
                if ref_path and ref_path.exists():
                    try:
                        ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
                        recs = (
                            ref_data.get("event_records")
                            or ref_data.get("candidates")
                            or ref_data.get("events")
                            or ref_data.get("deduplicated_events")
                            or []
                        )
                        for r in recs:
                            eid = r.get("canonical_event_id") if isinstance(r, dict) else str(r) if r else None
                            if eid and str(eid) not in event_ids:
                                event_ids.append(str(eid))
                    except Exception:
                        pass

        if not event_ids:
            s1e_path = self.run_root / "data" / f"{self.betting_day}_s1e_event_universe.json" if hasattr(self, "run_root") else gate_base_dir / "data" / f"{self.betting_day}_s1e_event_universe.json"
            if s1e_path.exists():
                try:
                    s1e_data = json.loads(s1e_path.read_text(encoding="utf-8"))
                    e_list = s1e_data.get("canonical_event_ids") or [
                        e["canonical_event_id"] for e in s1e_data.get("deduplicated_events", [])
                        if isinstance(e, dict) and "canonical_event_id" in e
                    ]
                    for eid in e_list:
                        s_eid = str(eid)
                        if s_eid not in event_ids:
                            event_ids.append(s_eid)
                except Exception:
                    pass

        if not event_ids:
            return False, None, None

        # Load policy-driven budget from manifest
        sharding_cfg = (
            self.manifest.runtime_contract.get("sharding_policy", {})
            if hasattr(self, "manifest") and self.manifest and isinstance(self.manifest.runtime_contract, dict)
            else {}
        )
        budget = WorkOrderBudgetV1(**sharding_cfg) if sharding_cfg else WorkOrderBudgetV1()

        if len(event_ids) <= budget.max_events_per_chunk:
            return False, None, None

        parent_wo_dict = parent_wo.to_jsonable() if hasattr(parent_wo, "to_jsonable") else (
            parent_wo.model_dump() if hasattr(parent_wo, "model_dump") else {}
        )
        parent_wo_sha = hash_canonical_json(parent_wo_dict) if parent_wo_dict else ""

        plan = create_chunk_execution_plan(
            parent_work_order_id=getattr(parent_wo, "work_order_id", f"WO-{step_id}"),
            parent_work_order_sha256=parent_wo_sha,
            step_id=step_id,
            betting_day=self.betting_day,
            run_id=self.run_id,
            runtime_mode=getattr(parent_wo, "runtime_mode", "STANDALONE_DETERMINISTIC"),
            source_head=getattr(parent_wo, "source_head", ""),
            source_tree=getattr(parent_wo, "source_tree", ""),
            manifest_sha256=getattr(parent_wo, "manifest_sha256", ""),
            event_ids=event_ids,
            agent_name=getattr(parent_wo, "agent", "bet-executor"),
            allowed_tools=getattr(parent_wo, "allowed_tools", ()),
            input_refs=[ref.to_jsonable() if hasattr(ref, "to_jsonable") else ref for ref in getattr(parent_wo, "input_refs", ())],
            task_allowlist=getattr(parent_wo, "task_allowlist", ()),
            acquisition_plan=getattr(parent_wo, "acquisition_plan", None),
            hard_rules=getattr(parent_wo, "hard_rules", ()),
            forbidden_outputs=getattr(parent_wo, "forbidden_outputs", ()),
            budget=budget,
        )

        plan_dir = gate_base_dir / "work_orders" / "chunks"
        plan_dir.mkdir(parents=True, exist_ok=True)
        plan_file = plan_dir / f"PLAN_{getattr(parent_wo, 'work_order_id', step_id)}.json"
        write_json_atomic(plan_file, plan.model_dump())

        chunks_dir = gate_base_dir / "artifacts" / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        chunk_artifacts = []
        missing_chunks = []
        first_pending_wo_path = None
        first_pending_wo_sha = None
        first_pending_expected_out = None

        for c_wo in plan.chunks:
            c_file = chunks_dir / f"{c_wo.chunk_id}.json"
            if not c_file.exists():
                missing_chunks.append(c_wo.chunk_id)
                c_wo_file = plan_dir / f"{c_wo.chunk_id}_work_order.json"
                c_wo_data = c_wo.model_dump()
                write_json_atomic(c_wo_file, c_wo_data)
                if first_pending_wo_path is None:
                    first_pending_wo_path = str(c_wo_file)
                    first_pending_wo_sha = hash_canonical_json(c_wo_data)
                    first_pending_expected_out = str(c_file)
            else:
                try:
                    c_art = ChunkArtifactV1(**json.loads(c_file.read_text(encoding="utf-8")))
                    chunk_artifacts.append(c_art)
                except Exception:
                    missing_chunks.append(c_wo.chunk_id)

        if missing_chunks:
            self.pending_chunk_work_order_path = first_pending_wo_path
            self.pending_chunk_work_order_sha256 = first_pending_wo_sha
            self.pending_chunk_expected_output_path = first_pending_expected_out
            return True, f"Sharded step {step_id} waiting on {len(missing_chunks)}/{len(plan.chunks)} chunks", plan_file

        receipt, agg_records = aggregate_chunks(plan, chunk_artifacts)
        target_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, step_id)

        manifest_step = self.manifest.get_step(step_id) if hasattr(self.manifest, "get_step") else None
        art_type = manifest_step.primary_produces_contract_id() if manifest_step else None
        if not art_type:
            for desc in GLOBAL_CONTRACT_REGISTRY.list_descriptors():
                if desc.producer_step == step_id:
                    art_type = desc.contract_id
                    break

        art_type = art_type or f"{step_id.replace('.', '_')}_AGGREGATED"
        agg_artifact = {
            "schema_version": 1,
            "artifact_type": art_type,
            "status": "PASS" if step_id != "S2.9" else "READY",
            "betting_day": self.betting_day,
            "run_id": self.run_id,
            "total_events": len(agg_records),
            "event_records": agg_records,
            "aggregation_receipt": receipt.model_dump(),
        }
        write_json_atomic(target_path, agg_artifact)
        return True, None, target_path

    def _step_timeout_seconds(self) -> int:
        default = int(self.manifest.runtime_contract.get("default_timeout_seconds", 900))
        maximum = int(self.manifest.runtime_contract.get("maximum_timeout_seconds", 3600))
        try:
            requested = int(self.env.get("BET_PIPELINE_STEP_TIMEOUT_SECONDS", default))
        except (TypeError, ValueError):
            requested = default
        return min(max(requested, 1), maximum)

    def derive_human_gate_readiness(
        self,
        gate_base_dir: Path,
        last_completed_step: str | None,
        overall_status: Any,
    ) -> tuple[bool, str | None]:
        import hashlib

        waiting_at_s9 = any(
            evidence.get("step_id") == "S9"
            and evidence.get("blocked_reason") == BlockedReason.BLOCKED_WAITING_FOR_HUMAN_APPROVAL
            for evidence in self.step_evidences
        )
        expected_s9_blocker = "Missing required human gate artifact for step S9"

        # 1. No unresolved command request or unexpected blocker exists. Waiting
        # for the S9 operator artifact is the intended human-gate state.
        unexpected_blockers = [
            blocker for blocker in self.blockers if not (waiting_at_s9 and blocker == expected_s9_blocker)
        ]
        if self.unresolved_count > 0 or unexpected_blockers:
            return False, None

        # 2. No S9 artifact exists
        s9_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, "S9")
        if s9_path.exists():
            self.blockers.append("Contamination: S9 human gate artifact is unexpectedly present during S0-S8")
            return False, None

        # 3. S8 completed successfully
        allowed_status = overall_status in (PipelineReadinessStatus.PASS, PipelineReadinessStatus.WARN)
        if waiting_at_s9 and overall_status == PipelineReadinessStatus.BLOCK:
            allowed_status = True
        if last_completed_step != "S8" or not allowed_status:
            return False, None

        # 4. S8 SCRIPT_EVIDENCE schema validation
        s8_path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, "S8")
        if not s8_path.exists():
            self.blockers.append("Missing required S8 script evidence")
            return False, None

        try:
            with open(s8_path, encoding="utf-8") as f:
                s8_ev = json.load(f)
        except Exception as e:
            self.blockers.append(f"Malformed S8 script evidence: {e}")
            return False, None

        if s8_ev.get("schema_version") != 1 or s8_ev.get("artifact_type") != "SCRIPT_EVIDENCE" or s8_ev.get("step_id") != "S8":
            self.blockers.append("Invalid S8 script evidence schema")
            return False, None

        if s8_ev.get("betting_day") != self.betting_day or s8_ev.get("run_id") != self.run_id:
            self.blockers.append("S8 evidence betting day or run ID mismatch")
            return False, None

        if s8_ev.get("status") != "PASS":
            return False, None

        payload = s8_ev.get("payload") or {}
        s8_quote_pack_path = payload.get("s8_quote_pack_path")
        s8_quote_pack_sha256 = payload.get("s8_quote_pack_sha256")

        if not s8_quote_pack_path or not s8_quote_pack_sha256:
            self.blockers.append("S8 evidence is missing output path or hash")
            return False, None

        # 5. Output path is current-run scoped
        try:
            Path(s8_quote_pack_path).resolve().relative_to(self.run_root.resolve())
        except ValueError:
            self.blockers.append("S8 output path is not current-run scoped")
            return False, None

        # 6. Output SHA-256 matches
        out_path = Path(s8_quote_pack_path)
        if not out_path.exists():
            self.blockers.append("S8 output file does not exist")
            return False, None

        try:
            h = hashlib.sha256()
            with open(out_path, "rb") as f:
                h.update(f.read())
            actual_sha = h.hexdigest()
        except Exception as e:
            self.blockers.append(f"Failed to compute S8 output hash: {e}")
            return False, None

        if actual_sha != s8_quote_pack_sha256:
            self.blockers.append("S8 output SHA-256 hash mismatch")
            return False, None

        # 7. S8 output artifact fields validation
        try:
            with open(out_path, encoding="utf-8") as f:
                out_art = json.load(f)
        except Exception as e:
            self.blockers.append(f"Malformed S8 output artifact: {e}")
            return False, None

        if out_art.get("schema_version") != 2 or out_art.get("artifact_type") != "S8_SUPERBET_MANUAL_QUOTE_PACK":
            self.blockers.append("Invalid S8 output artifact schema or type")
            return False, None

        if out_art.get("status") != "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW" or out_art.get("final_status") != "READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW":
            return False, None

        quote_card_count = out_art.get("quote_card_count")
        if not isinstance(quote_card_count, int) or quote_card_count <= 0:
            return False, None

        quote_cards = out_art.get("quote_cards") or []
        if quote_card_count != len(quote_cards):
            self.blockers.append("S8 output quote_card_count mismatch with list length")
            return False, None

        # 8. Every quote card satisfies manual operator boundary
        for idx, card in enumerate(quote_cards):
            if card.get("manual_operator") != "SUPERBET":
                self.blockers.append(f"Quote card {idx} manual_operator is not SUPERBET")
                return False, None
            if card.get("executable_coupon") is not False or card.get("betting_valid") is not False or card.get("can_place_bet_now") is not False:
                self.blockers.append(f"Quote card {idx} violates safety bounds")
                return False, None

        # 9. Extra safety fields in evidence payload & output artifact
        if out_art.get("ready_for_human_gate") is not True or payload.get("ready_for_human_gate") is not True:
            return False, None

        if out_art.get("executable_coupon") is not False or payload.get("executable_coupon") is not False:
            return False, None

        if out_art.get("betting_valid") is not False or payload.get("betting_valid") is not False:
            return False, None

        if out_art.get("can_place_bet_now") is not False or payload.get("can_place_bet_now") is not False:
            return False, None

        return True, "WAITING_FOR_HUMAN_APPROVAL"

    def run(
        self,
        start_step: str | None = None,
        stop_after_step: str | None = None,
    ) -> dict[str, Any]:
        self._resume_ledger.assert_resumable(start_step)
        with self._run_lock:
            return self._run_unlocked(start_step=start_step, stop_after_step=stop_after_step)

    def _run_unlocked(
        self,
        start_step: str | None = None,
        stop_after_step: str | None = None,
    ) -> dict[str, Any]:
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

        last_completed_step: str | None = None
        blocked_at_step: str | None = None
        overall_status = PipelineReadinessStatus.PASS
        gate_base_dir = self.run_artifact_dir.parent.parent.parent.parent

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

            work_order_path: str | None = None

            # 1. Enforce gates and check prerequisite artifacts
            # We construct a base_dir for the gate evaluator to work properly
            gate_base_dir = self.run_artifact_dir.parent.parent.parent.parent
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
            return_code: int | None = None
            stdout_path: str | None = None
            stderr_path: str | None = None
            evidence_path: str | None = None
            blocked_reason: str | None = None

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
                        res = run_bounded_process(
                            cmd,
                            env=self.env,
                            stdout=out_f,
                            stderr=err_f,
                            cwd=str(self.repo_root),
                            timeout_seconds=self._step_timeout_seconds(),
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
                        with open(canonical_evidence, encoding="utf-8") as f:
                            raw_ev = json.load(f)
                        if not isinstance(raw_ev, dict):
                            raise ValueError("SCRIPT_EVIDENCE must be a JSON object")
                        if raw_ev.get("artifact_type") != "SCRIPT_EVIDENCE":
                            raise ValueError(f"MISMATCH_ARTIFACT_TYPE: expected SCRIPT_EVIDENCE, got {raw_ev.get('artifact_type')}")
                        if raw_ev.get("step_id") != sid:
                            raise ValueError(f"MISMATCH_STEP_ID: expected {sid}, got {raw_ev.get('step_id')}")
                        if raw_ev.get("betting_day") != self.betting_day:
                            raise ValueError(f"MISMATCH_BETTING_DAY: expected {self.betting_day}, got {raw_ev.get('betting_day')}")
                        if raw_ev.get("run_id") != self.run_id:
                            raise ValueError(f"MISMATCH_RUN_ID: expected {self.run_id}, got {raw_ev.get('run_id')}")

                        from bet.pipeline.agent_artifact_contracts import _has_placeholder
                        placeholder_err = _has_placeholder(raw_ev, is_pass_status=(raw_ev.get("status") == "PASS"))
                        if placeholder_err:
                            raise ValueError(f"Script evidence contains placeholders: {placeholder_err}")

                        evidence_status = raw_ev.get("status")
                        evidence_blocked_reasons = raw_ev.get("blocked_reasons", [])
                    except Exception as e:
                        evidence_status = "BLOCK"
                        evidence_blocked_reasons = [f"SCRIPT_EVIDENCE_UNREADABLE: {e}"]

                # P0-7: Strict Script Evidence Contract
                is_valid_script_evidence = False
                if return_code == 0:
                    if evidence_exists:
                        try:
                            # 1. Full validate_pipeline_artifact contract passes
                            artifact, issues = validate_pipeline_artifact(raw_ev, sid)
                            block_issues = [i for i in issues if i.severity == PipelineReadinessStatus.BLOCK]

                            # 2. Strict status check: must be "PASS" exactly
                            status_is_pass = (evidence_status == "PASS")

                            # 3. Artifact type must be SCRIPT_EVIDENCE
                            type_is_ok = (raw_ev.get("artifact_type") == "SCRIPT_EVIDENCE")

                            # 4. Step ID, betting day, and run ID match
                            id_match = (raw_ev.get("step_id") == sid)
                            day_match = (raw_ev.get("betting_day") == self.betting_day)
                            run_match = (raw_ev.get("run_id") == self.run_id)

                            # 5. Placeholders/forbidden values check
                            from bet.pipeline.agent_artifact_contracts import _has_placeholder
                            placeholder_err = _has_placeholder(raw_ev, is_pass_status=True)

                            if (
                                not block_issues
                                and status_is_pass
                                and type_is_ok
                                and id_match
                                and day_match
                                and run_match
                                and not placeholder_err
                            ):
                                is_valid_script_evidence = True
                            else:
                                if block_issues:
                                    for issue in block_issues:
                                        self.blockers.append(f"Step {sid} structural issue: {issue.message}")
                                if not status_is_pass:
                                    if evidence_status == "BLOCK":
                                        if evidence_blocked_reasons:
                                            for r in evidence_blocked_reasons:
                                                self.blockers.append(f"Step {sid} blocked: {r}")
                                        else:
                                            self.blockers.append(f"Step {sid} completed with BLOCK status")
                                    else:
                                        self.blockers.append(f"Step {sid} has invalid status for script step: {evidence_status}")
                                if placeholder_err:
                                    self.blockers.append(f"Step {sid} contains placeholders: {placeholder_err}")
                        except Exception as exc:
                            self.blockers.append(f"Step {sid} validation error: {exc}")
                    else:
                        self.blockers.append(f"Canonical script evidence missing for step '{sid}'")
                        blocked_reason = BlockedReason.BLOCKED_SCRIPT_EVIDENCE_MISSING
                else:
                    if evidence_exists:
                        try:
                            artifact, issues = validate_pipeline_artifact(raw_ev, sid)
                            block_issues = [
                                i for i in issues
                                if i.severity == PipelineReadinessStatus.BLOCK
                                and i.code not in ("BLOCKING_STATUS", "INVALID_REQUIRED_ARTIFACT_STATUS")
                            ]
                            if not block_issues and evidence_status == "BLOCK":
                                if evidence_blocked_reasons:
                                    for r in evidence_blocked_reasons:
                                        self.blockers.append(f"Step {sid} blocked: {r}")
                                else:
                                    self.blockers.append(f"Step {sid} completed with {evidence_status} status")
                            else:
                                self.blockers.append(f"Wrapper script for step '{sid}' exited with non-zero code {return_code}")
                        except Exception:
                            self.blockers.append(f"Wrapper script for step '{sid}' exited with non-zero code {return_code}")
                    else:
                        self.blockers.append(f"Wrapper script for step '{sid}' exited with non-zero code {return_code}")

                if is_valid_script_evidence:
                    step_status = PipelineReadinessStatus.PASS
                    evidence_path = str(canonical_evidence)
                else:
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    if evidence_exists:
                        evidence_path = str(canonical_evidence)
                    if not blocked_reason:
                        blocked_reason = "SCRIPT_EVIDENCE_VALIDATION_FAILED"

            elif step.execution_mode == "agent_artifact":
                from bet.pipeline.agent_work_orders import (
                    build_agent_work_order,
                    write_agent_work_order,
                    work_order_path_for,
                )
                from bet.pipeline.sharding.models import WorkOrderBudgetV1

                wo = build_agent_work_order(
                    betting_day=self.betting_day,
                    run_id=self.run_id,
                    step_id=sid,
                    runtime_mode=self.runtime_mode.value,
                    base_dir=gate_base_dir,
                )
                written_wo_path = write_agent_work_order(wo, gate_base_dir)
                work_order_path = str(written_wo_path)

                # Check if event scope requires sharded execution
                is_sharded, shard_block_reason, agg_path = self._handle_sharded_agent_step(sid, gate_base_dir, wo)
                if is_sharded and shard_block_reason:
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                    self.blockers.append(shard_block_reason)
                    continue

                # Check for existing agent artifact
                expected_path = agg_path or artifact_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                if not expected_path.exists():
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                    self.blockers.append(f"Missing required agent artifact for step {sid}")
                else:
                    from bet.pipeline.agent_work_orders import (
                        build_agent_work_order,
                        write_agent_work_order,
                        work_order_path_for,
                    )
                    wo_path = work_order_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                    if not wo_path.is_file():
                        try:
                            wo = build_agent_work_order(
                                betting_day=self.betting_day,
                                run_id=self.run_id,
                                step_id=sid,
                                runtime_mode=self.runtime_mode.value,
                                base_dir=gate_base_dir,
                            )
                            write_agent_work_order(wo, gate_base_dir)
                        except Exception as e:
                            step_status = PipelineReadinessStatus.BLOCK
                            overall_status = PipelineReadinessStatus.BLOCK
                            blocked_at_step = sid
                            blocked_reason = BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT
                            self.blockers.append(f"Failed to generate work order for step {sid}: {e}")
                            continue

                    try:
                        with open(expected_path, encoding="utf-8") as f:
                            raw = json.load(f)
                        artifact, issues = validate_pipeline_artifact(
                            raw,
                            sid,
                            enforce_required_gate=False,
                            allow_block_status=True,
                        )

                        from bet.pipeline.agent_artifact_contracts import (
                            validate_agent_artifact_for_work_order,
                        )
                        from bet.pipeline.agent_work_orders import (
                            build_agent_work_order,
                            work_order_path_for,
                        )
                        from bet.pipeline.canonical_continuity import canonical_json_bytes

                        wo_path = work_order_path_for(gate_base_dir, self.betting_day, self.run_id, sid)
                        work_order_path = str(wo_path)
                        wo_errors = []
                        active_wo_data = None

                        if not wo_path.is_file():
                            wo_errors = [f"Work order missing at {wo_path}"]
                        else:
                            try:
                                wo_bytes = wo_path.read_bytes()
                                active_wo_data = json.loads(wo_bytes)
                                if active_wo_data.get("betting_day") != self.betting_day:
                                    wo_errors.append(f"Work order betting_day mismatch: {active_wo_data.get('betting_day')} vs {self.betting_day}")
                                if active_wo_data.get("run_id") != self.run_id:
                                    wo_errors.append(f"Work order run_id mismatch: {active_wo_data.get('run_id')} vs {self.run_id}")
                                if active_wo_data.get("step_id") != sid:
                                    wo_errors.append(f"Work order step_id mismatch: {active_wo_data.get('step_id')} vs {sid}")

                                if not wo_errors:
                                    def normalize_wo_paths(val):
                                        if isinstance(val, dict):
                                            return {
                                                k: (str(Path(v).expanduser().resolve(strict=False)) if k in ("path", "expected_path") and isinstance(v, str) else normalize_wo_paths(v))
                                                for k, v in val.items()
                                            }
                                        elif isinstance(val, list):
                                            return [normalize_wo_paths(item) for item in val]
                                        return val

                                    recomputed_wo = build_agent_work_order(
                                        betting_day=self.betting_day,
                                        run_id=self.run_id,
                                        step_id=sid,
                                        runtime_mode=self.runtime_mode.value,
                                        base_dir=gate_base_dir,
                                    )
                                    recomputed_wo_json = recomputed_wo.to_jsonable()
                                    recomputed_wo_json["created_at"] = active_wo_data.get("created_at")

                                    norm_recomputed = normalize_wo_paths(recomputed_wo_json)
                                    norm_persisted = normalize_wo_paths(active_wo_data)

                                    recomputed_bytes = canonical_json_bytes(norm_recomputed)
                                    persisted_canon_bytes = canonical_json_bytes(norm_persisted)

                                    if recomputed_bytes != persisted_canon_bytes:
                                        wo_errors.append("WORK_ORDER_DRIFT: Recomputed work order bytes differ from persisted work order bytes")
                                    else:
                                        if active_wo_data.get("manifest_sha256") != recomputed_wo.manifest_sha256:
                                            wo_errors.append("WORK_ORDER_DRIFT: manifest_sha256 mutated after work-order creation")
                                        elif active_wo_data.get("source_head") != recomputed_wo.source_head:
                                            wo_errors.append("WORK_ORDER_DRIFT: source_head mutated after work-order creation")
                                        else:
                                            wo_errors = validate_agent_artifact_for_work_order(raw, active_wo_data)
                            except Exception as e:
                                wo_errors = [f"Failed to load or validate persisted work order: {e}"]

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
                                from bet.pipeline.command_registry import (
                                    CommandRequestError,
                                    resolve_command_request,
                                )
                                argv: list[str] = []
                                timeout_seconds = 0.0
                                expected_exit_code = 0
                                postconditions = ["rerun_validate_agent_artifact"]
                                cwd_dir = str(self.repo_root)
                                is_valid = True
                                try:
                                    resolved_command = resolve_command_request(cmd_req)
                                    argv = resolved_command.argv
                                    timeout_seconds = resolved_command.timeout_seconds
                                    expected_exit_code = resolved_command.expected_exit_code
                                    postconditions = resolved_command.postconditions
                                except CommandRequestError as exc:
                                    self.blockers.append(str(exc))
                                    is_valid = False
                                if not is_valid or not argv:
                                    self.failed_count += 1
                                    self.unresolved_count += 1
                                    step_status = PipelineReadinessStatus.BLOCK
                                    overall_status = PipelineReadinessStatus.BLOCK
                                    blocked_at_step = sid
                                    blocked_reason = "COMMAND_REQUEST_VALIDATION_FAILED"
                                else:
                                    # Perform ledger transition validation BEFORE executing any bounded command
                                    wo_sha_pre = ""
                                    if wo_path.is_file():
                                        wo_sha_pre = hashlib.sha256(wo_path.read_bytes()).hexdigest()
                                    predecessor_hashes_pre = {}
                                    if active_wo_data:
                                        for ref in active_wo_data.get("input_refs", []):
                                            ref_step_id = ref.get("step_id")
                                            ref_sha = ref.get("sha256")
                                            if ref_step_id and ref_sha:
                                                predecessor_hashes_pre[f"predecessor_{ref_step_id}_sha256"] = ref_sha
                                    ledger_input_hashes_pre = {
                                        "manifest": self._manifest_sha,
                                        **predecessor_hashes_pre
                                    }
                                    if wo_sha_pre:
                                        ledger_input_hashes_pre["work_order_sha256"] = wo_sha_pre
                                    cmd_req_identity_pre = {
                                        "command_request_payload": cmd_req,
                                        "command_id": cmd_req.get("command_id", "UNKNOWN"),
                                        "argv": argv,
                                        "cwd": cwd_dir,
                                        "timeout_seconds": float(timeout_seconds),
                                        "expected_exit_code": expected_exit_code,
                                        "postconditions": postconditions,
                                        "runtime_mode": self.runtime_mode.value,
                                        "work_order_sha256": wo_sha_pre,
                                        "predecessor_hashes": predecessor_hashes_pre,
                                    }
                                    self._resume_ledger.append(
                                        step_id=sid,
                                        status="COMMAND_REQUEST_PENDING",
                                        command_request=cmd_req_identity_pre,
                                        input_hashes=ledger_input_hashes_pre,
                                        output_hashes={},
                                    )

                                    ledger_data = self._resume_ledger._load()
                                    step_entries = [e for e in ledger_data.get("entries", []) if e.get("step_id") == sid and e.get("status") == "COMMAND_REQUEST_PENDING"]
                                    attempt_num = len(step_entries)

                                    stdout_log_path = self.run_root / f"logs/{sid}_cmd_attempt_{attempt_num}_stdout.log"
                                    stderr_log_path = self.run_root / f"logs/{sid}_cmd_attempt_{attempt_num}_stderr.log"
                                    orig_artifact_path = expected_path.with_name(f"{sid}_command_request_attempt_{attempt_num}.json")
                                    write_json_atomic(orig_artifact_path, raw)
                                    # Non-authoritative pointer alias (convenience only; authoritative series is attempt-scoped)
                                    write_json_atomic(expected_path.with_name(f"{sid}_command_request.json"), raw)
                                    start_time = time.time()
                                    try:
                                        res = run_bounded_process(
                                            argv,
                                            cwd=cwd_dir,
                                            env=self.env,
                                            timeout_seconds=float(timeout_seconds),
                                        )
                                        duration = time.time() - start_time
                                        exit_code = res.returncode
                                        stdout_text = res.stdout
                                        stderr_text = res.stderr
                                        if res.timed_out:
                                            self.blockers.append(f"COMMAND_REQUEST execution timed out after {timeout_seconds}s")
                                    except Exception as e:
                                        duration = time.time() - start_time
                                        exit_code = -1
                                        stdout_text = ""
                                        stderr_text = str(e)
                                        self.blockers.append(f"COMMAND_REQUEST execution failed: {e}")
                                    for env_key, val in self.env.items():
                                        if any(x in env_key.lower() for x in ("key", "secret", "token", "password", "credential", "auth")):
                                            if val and len(val) > 4:
                                                stdout_text = stdout_text.replace(val, "[REDACTED]")
                                                stderr_text = stderr_text.replace(val, "[REDACTED]")
                                    stdout_log_path.write_text(stdout_text, encoding="utf-8")
                                    stderr_log_path.write_text(stderr_text, encoding="utf-8")
                                    try:
                                        (self.run_root / f"logs/{sid}_cmd_stdout.log").write_text(stdout_text, encoding="utf-8")
                                        (self.run_root / f"logs/{sid}_cmd_stderr.log").write_text(stderr_text, encoding="utf-8")
                                    except Exception:
                                        pass
                                    sha256_hash = hashlib.sha256(stdout_text.encode("utf-8")).hexdigest()
                                    evidence_artifact_path = expected_path.with_name(f"{sid}_command_evidence_attempt_{attempt_num}.json")
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
                                        "postconditions": postconditions,
                                        "attempt_number": attempt_num,
                                        "command_request_hash": hashlib.sha256(canonical_json_bytes(cmd_req_identity_pre)).hexdigest(),
                                        "cwd": cwd_dir,
                                        "timeout_seconds": timeout_seconds,
                                        "stdout_sha256": hashlib.sha256(stdout_text.encode("utf-8")).hexdigest(),
                                        "stderr_sha256": hashlib.sha256(stderr_text.encode("utf-8")).hexdigest(),
                                    }
                                    write_json_atomic(evidence_artifact_path, evidence_artifact)
                                    # Non-authoritative pointer alias (convenience only; authoritative series is attempt-scoped)
                                    write_json_atomic(expected_path.with_name(f"{sid}_command_evidence.json"), evidence_artifact)
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
                                        if active_wo_data:
                                            resolved_artifact["work_order_id"] = active_wo_data.get("work_order_id")
                                            from bet.pipeline.canonical_continuity import file_sha256
                                            resolved_artifact["work_order_sha256"] = file_sha256(wo_path)
                                            resolved_artifact["producer_agent_id"] = active_wo_data.get("agent")
                                        rel_evidence_path = str(evidence_artifact_path.relative_to(self.repo_root) if evidence_artifact_path.is_relative_to(self.repo_root) else evidence_artifact_path)
                                        std_ev_path = expected_path.with_name(f"{sid}_command_evidence.json")
                                        rel_std_ev = str(std_ev_path.relative_to(self.repo_root) if std_ev_path.is_relative_to(self.repo_root) else std_ev_path)
                                        refs = list(resolved_artifact.get("evidence_refs", []))
                                        if rel_evidence_path not in refs:
                                            refs.append(rel_evidence_path)
                                        if rel_std_ev not in refs:
                                            refs.append(rel_std_ev)
                                        resolved_artifact["evidence_refs"] = refs
                                        if "command_request" in resolved_artifact:
                                            resolved_artifact.pop("command_request")
                                        if "command_request" in resolved_artifact.get("payload", {}):
                                            resolved_artifact["payload"].pop("command_request")
                                        from bet.pipeline.agent_artifact_contracts import (
                                            validate_agent_artifact_for_work_order,
                                        )
                                        wo_errors = validate_agent_artifact_for_work_order(resolved_artifact, active_wo_data if active_wo_data else {})
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
                        with open(expected_path, encoding="utf-8") as f:
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

            accounting = EventAccountingLedger(
                self.run_root, betting_day=self.betting_day, run_id=self.run_id
            )
            if sid in ACCOUNTING_BOUNDARY_STEPS and accounting.path.exists():
                records = None
                if evidence_path:
                    evidence_payload = _load_json_object(evidence_path) or {}
                    candidate_records = (
                        (evidence_payload.get("payload") or {}).get("event_records")
                        or evidence_payload.get("event_records")
                    )
                    if candidate_records is None and sid in {"S2", "S3", "S4", "S6", "S7", "S7b", "S8"}:
                        manifest_step = self.manifest.get_step(sid) if hasattr(self.manifest, "get_step") else None
                        exp_type = manifest_step.primary_produces_contract_id() if manifest_step else None
                        if not exp_type:
                            for desc in GLOBAL_CONTRACT_REGISTRY.list_descriptors():
                                if desc.producer_step == sid:
                                    exp_type = desc.contract_id
                                    break
                        if exp_type:
                            _, out_data = resolve_bound_step_output(
                                run_root=self.run_root,
                                step_id=sid,
                                betting_day=self.betting_day,
                                run_id=self.run_id,
                                expected_artifact_type=exp_type,
                            )
                            candidate_records = (
                                out_data.get("event_records")
                                or out_data.get("candidates")
                                or out_data.get("analyses")
                                or out_data.get("events")
                                or (
                                    (out_data.get("analytical_approved") or [])
                                    + (out_data.get("priced_approved") or [])
                                    + (out_data.get("rejected") or [])
                                    if ("analytical_approved" in out_data or "priced_approved" in out_data or "rejected" in out_data)
                                    else None
                                )
                            )
                    if candidate_records is not None:
                        records = candidate_records
                try:
                    accounting.record_boundary(
                        sid,
                        records=records,
                    )
                except EventAccountingError as exc:
                    step_status = PipelineReadinessStatus.BLOCK
                    overall_status = PipelineReadinessStatus.BLOCK
                    blocked_at_step = sid
                    blocked_reason = str(exc)
                    self.blockers.append(f"Event accounting failed at {sid}: {exc}")

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
            output_hashes: dict[str, str] = {}
            if evidence_path and Path(evidence_path).is_file():
                output_hashes["evidence"] = hashlib.sha256(Path(evidence_path).read_bytes()).hexdigest()
            # Wire ledger states through orchestrator (P0-3)
            if step.execution_mode == "agent_artifact":
                if blocked_reason == BlockedReason.BLOCKED_WAITING_FOR_AGENT_ARTIFACT:
                    ledger_status = "WAITING_FOR_AGENT_ARTIFACT"
                elif blocked_reason in (
                    "COMMAND_REQUEST_VALIDATION_FAILED",
                    "COMMAND_REQUEST_POSTCONDITIONS_FAILED",
                    "COMMAND_REQUEST_MISSING_COMMAND"
                ) or (blocked_reason and "COMMAND_REQUEST" in str(blocked_reason)):
                    ledger_status = "COMMAND_REQUEST_UNRESOLVED"
                else:
                    status_val = None
                    if evidence_path and Path(evidence_path).is_file():
                        try:
                            raw_data = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
                            status_val = raw_data.get("status")
                        except Exception:
                            pass
                    if status_val == "PASS":
                        ledger_status = "PASS"
                    elif status_val == "NO_ACTION_TERMINAL":
                        ledger_status = "NO_ACTION_TERMINAL"
                    elif status_val == "BLOCK":
                        ledger_status = "AGENT_ARTIFACT_BLOCK"
                    else:
                        if blocked_reason and "drift" in str(blocked_reason).lower():
                            ledger_status = "WAITING_FOR_AGENT_ARTIFACT"
                        elif not evidence_path or not Path(evidence_path).is_file():
                            ledger_status = "WAITING_FOR_AGENT_ARTIFACT"
                        else:
                            ledger_status = "AGENT_ARTIFACT_BLOCK"
            else:
                # Script steps
                if return_code == 0:
                    status_val = None
                    if evidence_path and Path(evidence_path).is_file():
                        try:
                            raw_data = json.loads(Path(evidence_path).read_text(encoding="utf-8"))
                            status_val = raw_data.get("status")
                        except Exception:
                            pass
                    if status_val == "PASS":
                        ledger_status = "PASS"
                    elif status_val == "NO_ACTION_TERMINAL":
                        ledger_status = "NO_ACTION_TERMINAL"
                    else:
                        ledger_status = "COMMAND_REQUEST_UNRESOLVED"
                else:
                    ledger_status = "COMMAND_REQUEST_UNRESOLVED"
            wo_sha = ""
            predecessor_hashes = {}
            if work_order_path and Path(work_order_path).is_file():
                try:
                    wo_bytes = Path(work_order_path).read_bytes()
                    wo_sha = hashlib.sha256(wo_bytes).hexdigest()
                except Exception:
                    pass

            try:
                from bet.pipeline.manifest import load_pipeline_manifest, PipelineGraph
                from bet.pipeline.agent_work_orders import _script_evidence_candidates
                from bet.pipeline.canonical_continuity import file_sha256

                manifest = load_pipeline_manifest()
                step_obj = next((s for s in manifest.steps if s.id == sid), None)
                if step_obj:
                    deps = PipelineGraph.get_dependencies(sid)

                    for dep_id in deps:
                        dep_step = next((s for s in manifest.steps if s.id == dep_id), None)
                        if dep_step:
                            exec_mode = dep_step.execution_mode
                            if exec_mode == "script":
                                candidates = _script_evidence_candidates(gate_base_dir, self.betting_day, self.run_id, dep_id)
                                path = candidates[0]
                                for cand in candidates:
                                    if cand.is_file():
                                        path = cand
                                        break
                            else:
                                path = artifact_path_for(gate_base_dir, self.betting_day, self.run_id, dep_id)

                            if not path.is_file():
                                raise FileNotFoundError(f"Required predecessor artifact missing for {dep_id} at {path}")
                            try:
                                predecessor_hashes[f"predecessor_{dep_id}_sha256"] = file_sha256(path)
                            except Exception as exc:
                                raise ValueError(f"Failed to hash predecessor {dep_id} at {path}: {exc}")
            except Exception as e:
                step_status = PipelineReadinessStatus.BLOCK
                overall_status = PipelineReadinessStatus.BLOCK
                blocked_at_step = sid
                blocked_reason = f"Predecessor hashing failed: {e}"
                self.blockers.append(blocked_reason)

            ledger_input_hashes = {
                "manifest": self._manifest_sha,
                **predecessor_hashes
            }
            if wo_sha:
                ledger_input_hashes["work_order_sha256"] = wo_sha

            if step.execution_mode == "script":
                wrapper_path = self.repo_root / step.wrapper
                reconstructed_cmd = [sys.executable, str(wrapper_path), "--date", self.betting_day, "--run-id", self.run_id, "--runtime-mode", self.runtime_mode.value]
                if self.allow_live_network:
                    reconstructed_cmd.append("--allow-live-network")
                if self.allow_write:
                    reconstructed_cmd.append("--allow-write")

                cmd_req_identity = {
                    "interpreter": reconstructed_cmd[0],
                    "wrapper_path": reconstructed_cmd[1],
                    "date": self.betting_day,
                    "run_id": self.run_id,
                    "runtime_mode": self.runtime_mode.value,
                    "allow_live_network": self.allow_live_network,
                    "allow_write": self.allow_write,
                    "cwd": str(self.repo_root),
                    "timeout_seconds": self._step_timeout_seconds(),
                    "expected_exit_code": 0,
                    "postconditions": ["SCRIPT_EVIDENCE_PASS"],
                    "predecessor_hashes": predecessor_hashes,
                }
            else:
                cmd_req_identity = {
                    "wrapper": step.wrapper,
                    "execution_mode": step.execution_mode,
                    "runtime_mode": self.runtime_mode.value,
                    "cwd": str(self.repo_root),
                    "timeout": 900.0,
                    "expected_exit_code": 0,
                    "postconditions": ["SCRIPT_EVIDENCE_PASS"],
                    "work_order_sha256": wo_sha,
                    "argv": sys.argv,
                }

            self._resume_ledger.append(
                step_id=sid,
                status=ledger_status,
                command_request=cmd_req_identity,
                input_hashes=ledger_input_hashes,
                output_hashes=output_hashes,
            )
            self._run_lock.heartbeat()

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

        ready_for_human_gate, human_gate_status = self.derive_human_gate_readiness(
            gate_base_dir,
            last_completed_step,
            overall_status,
        )

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

        if getattr(self, "pending_chunk_work_order_path", None):
            summary["pending_chunk_work_order_path"] = self.pending_chunk_work_order_path
            summary["pending_chunk_work_order_sha256"] = getattr(self, "pending_chunk_work_order_sha256", None)
            summary["pending_chunk_expected_output_path"] = getattr(self, "pending_chunk_expected_output_path", None)

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
