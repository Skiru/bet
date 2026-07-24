"""Data contracts, schema generation, and disk writers for agent work orders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.run_evidence import utc_now_iso, write_json_atomic
from bet.pipeline.artifact_gate import artifact_path_for
from bet.pipeline.runtime_paths import resolve_run_root, runtime_artifact_dir


@dataclass
class AgentWorkOrderInputRef:
    step_id: str
    artifact_kind: str
    path: str
    required: bool
    sha256: str

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "artifact_kind": self.artifact_kind,
            "path": self.path,
            "required": self.required,
            "sha256": self.sha256,
        }


@dataclass
class AgentWorkOrderOutputContract:
    artifact_type: str
    step_id: str
    expected_path: str
    required_statuses: list[str]
    schema_requirements: dict[str, Any]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "step_id": self.step_id,
            "expected_path": self.expected_path,
            "required_statuses": self.required_statuses,
            "schema_requirements": self.schema_requirements,
        }


@dataclass
class AgentWorkOrderPolicy:
    agent: str
    hard_rules: list[str]
    forbidden_outputs: list[str]
    instructions: dict[str, Any]
    schema_requirements: dict[str, Any]


@dataclass
class AgentWorkOrder:
    schema_version: int
    work_order_id: str
    work_order_type: str
    pipeline_id: str
    betting_day: str
    run_id: str
    step_id: str
    agent: str
    runtime_mode: str
    created_at: str
    status: str
    input_refs: list[AgentWorkOrderInputRef]
    required_output: AgentWorkOrderOutputContract
    hard_rules: list[str]
    forbidden_outputs: list[str]
    instructions: dict[str, Any]
    manifest_sha256: str = "UNKNOWN"
    source_head: str = "UNKNOWN"

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "work_order_id": self.work_order_id,
            "work_order_type": self.work_order_type,
            "pipeline_id": self.pipeline_id,
            "betting_day": self.betting_day,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "agent": self.agent,
            "runtime_mode": self.runtime_mode,
            "created_at": self.created_at,
            "status": self.status,
            "input_refs": [ref.to_jsonable() for ref in self.input_refs],
            "required_output": self.required_output.to_jsonable(),
            "hard_rules": self.hard_rules,
            "forbidden_outputs": self.forbidden_outputs,
            "instructions": self.instructions,
            "manifest_sha256": self.manifest_sha256,
            "source_head": self.source_head,
        }


STEP_UPSTREAM_DEPENDENCIES: dict[str, list[str]] = {
    "S2.3": ["S2"],
    "S2.5": ["S2", "S2.3"],
    "S2.7": ["S2", "S2.3", "S2.5"],
    "S2.9": ["S2", "S2.3", "S2.5", "S2.7"],
    "S5": ["S3", "S4", "S2.9"],
}


OUTPUT_CONTRACT_NOTES = [
    "Template scaffolds are not accepted final output.",
    "Fill required evidence fields before returning an artifact.",
    "BLOCK is acceptable and preferred over guessing or implied approval.",
    "PASS requires full contract evidence for the specific step.",
]


POLICIES: dict[str, AgentWorkOrderPolicy] = {
    "S2.3": AgentWorkOrderPolicy(
        agent="bet-researcher",
        hard_rules=[
            "no_pick",
            "no_edge",
            "no_stake",
            "no_coupon",
            "source_bound_only",
            "unknown_or_blocked_for_missing_data",
            "no_production_db_write",
            "no_betting_data_write",
            "point_in_time_required",
        ],
        forbidden_outputs=[
            "internal_pick",
            "recommended_pick",
            "edge",
            "stake",
            "coupon",
            "parlay",
            "accumulator",
        ],
        instructions={
            "summary": "Detect enrichment gaps in input sources and flag missing required fields.",
            "must_do": [
                "Detect enrichment gaps.",
                "List unknowns and missing sources.",
                "May output PASS only if gaps are understood and bounded.",
                "May output BLOCK if required identity/source data is missing.",
            ],
            "must_not_do": [
                "Must not emit pick, edge, stake, coupon.",
                "Must not modify database or production data paths.",
            ],
            "unknown_policy": "Use UNKNOWN/BLOCK instead of guessing.",
            "output_contract": OUTPUT_CONTRACT_NOTES,
        },
        schema_requirements={
            "point_in_time_as_of": True,
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources_required": True,
        },
    ),
    "S2.5": AgentWorkOrderPolicy(
        agent="bet-researcher",
        hard_rules=[
            "no_pick",
            "no_edge",
            "no_stake",
            "no_coupon",
            "source_bound_only",
            "unknown_or_blocked_for_missing_data",
            "no_production_db_write",
            "no_betting_data_write",
            "point_in_time_required",
        ],
        forbidden_outputs=[
            "internal_pick",
            "recommended_pick",
            "edge",
            "stake",
            "coupon",
            "parlay",
            "accumulator",
        ],
        instructions={
            "summary": "Collect provider enrichment observations and store them source-bound.",
            "must_do": [
                "Collect provider enrichment observations.",
                "Must be source-bound.",
                "Include provider/source names and point-in-time timestamp.",
            ],
            "must_not_do": [
                "Must not promote providers or change provider selection.",
                "Must not emit pick, edge, stake, coupon.",
                "Must not modify database or production data paths.",
            ],
            "unknown_policy": "Use UNKNOWN/BLOCK instead of guessing.",
            "output_contract": OUTPUT_CONTRACT_NOTES,
        },
        schema_requirements={
            "point_in_time_as_of": True,
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources_required": True,
        },
    ),
    "S2.7": AgentWorkOrderPolicy(
        agent="bet-researcher",
        hard_rules=[
            "no_pick",
            "no_edge",
            "no_stake",
            "no_coupon",
            "source_bound_only",
            "unknown_or_blocked_for_missing_data",
            "no_production_db_write",
            "no_betting_data_write",
            "point_in_time_required",
        ],
        forbidden_outputs=[
            "internal_pick",
            "recommended_pick",
            "edge",
            "stake",
            "coupon",
            "parlay",
            "accumulator",
        ],
        instructions={
            "summary": "Reconcile facts across sources, explicitly marking disputed facts.",
            "must_do": [
                "Reconcile facts across sources.",
                "Mark disputed facts explicitly.",
                "Include evidence_refs.",
            ],
            "must_not_do": [
                "Must not resolve disputes by guessing.",
                "Must not emit pick, edge, stake, coupon.",
                "Must not modify database or production data paths.",
            ],
            "unknown_policy": "Use UNKNOWN/BLOCK instead of guessing.",
            "output_contract": OUTPUT_CONTRACT_NOTES,
        },
        schema_requirements={
            "point_in_time_as_of": True,
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources_required": True,
        },
    ),
    "S2.9": AgentWorkOrderPolicy(
        agent="bet-researcher",
        hard_rules=[
            "no_pick",
            "no_edge",
            "no_stake",
            "no_coupon",
            "source_bound_only",
            "unknown_or_blocked_for_missing_data",
            "no_production_db_write",
            "no_betting_data_write",
            "point_in_time_required",
        ],
        forbidden_outputs=[
            "internal_pick",
            "recommended_pick",
            "edge",
            "stake",
            "coupon",
            "parlay",
            "accumulator",
        ],
        instructions={
            "summary": "Data readiness gate checking whether subsequent analysis steps may proceed.",
            "must_do": [
                "Assess and say whether S3 stats & probability may proceed.",
                "PASS requires S2.3, S2.5, S2.7 artifacts valid.",
                "BLOCK if data remains insufficient.",
            ],
            "must_not_do": [
                "Must not emit pick, edge, stake, coupon.",
                "Must not modify database or production data paths.",
            ],
            "unknown_policy": "Use UNKNOWN/BLOCK instead of guessing.",
            "output_contract": OUTPUT_CONTRACT_NOTES,
        },
        schema_requirements={
            "point_in_time_as_of": True,
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources_required": True,
        },
    ),
    "S5": AgentWorkOrderPolicy(
        agent="bet-risk-gatekeeper",
        hard_rules=[
            "injury_lineup_context_required",
            "motivation_and_tournament_context_required",
            "travel_schedule_fatigue_checked",
            "morale_and_recent_result_context_checked",
            "volatility_or_upset_risk_checked",
        ],
        forbidden_outputs=[
            "internal_pick",
            "recommended_pick",
            "edge",
            "stake",
            "coupon",
            "parlay",
            "accumulator",
        ],
        instructions={
            "summary": "Evaluate context, motivation and volatility risk flags for shortlisted fixtures.",
            "must_do": [
                "Check injuries/lineups.",
                "Check motivation and tournament context.",
                "Check travel/fatigue.",
                "Check morale and recent results.",
                "Check upset/volatility risk.",
                "Use source-bound evidence and mark UNKNOWN if missing.",
                "Copy every S4 candidate without changing canonical event_id, selection_id, market, selection, line, or period.",
                "Partition every S4 selection_id exactly once into candidates or rejected_candidates.",
                "Bind source_s4_path and source_s4_sha256 exactly to the work-order S4 input ref.",
            ],
            "must_not_do": [
                "Must not emit coupon.",
                "May identify risk flags and conditional objections, but not bypass S7/S7b/S8.",
            ],
            "unknown_policy": "Use UNKNOWN/BLOCK instead of guessing.",
            "output_contract": OUTPUT_CONTRACT_NOTES,
        },
        schema_requirements={
            "point_in_time_as_of": True,
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources_required": True,
        },
    ),
}


def calculate_sha256(path: Path) -> str:
    """Calculate the sha256 hash of a file if it exists, else return empty string."""
    if not path.is_file():
        return ""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def work_order_path_for(
    base_dir: Path,
    betting_day: str,
    run_id: str,
    step_id: str,
) -> Path:
    """Get the canonical work order file path."""
    return (
        Path(base_dir)
        / "pipeline_runs"
        / betting_day
        / run_id
        / "artifacts"
        / f"{step_id}_work_order.json"
    )


def expected_agent_artifact_path_for(
    base_dir: Path,
    betting_day: str,
    run_id: str,
    step_id: str,
) -> Path:
    """Get the canonical expected agent artifact path."""
    return artifact_path_for(base_dir, betting_day, run_id, step_id)


def _script_evidence_candidates(
    base_dir: Path,
    betting_day: str,
    run_id: str,
    step_id: str,
) -> tuple[Path, ...]:
    run_root = resolve_run_root(betting_day, run_id, base_dir)
    runtime_artifacts = runtime_artifact_dir(run_root)
    return (
        runtime_artifacts / f"{step_id}.json",
        artifact_path_for(base_dir, betting_day, run_id, step_id),
    )


def _resolve_input_ref_path(
    step_id: str,
    artifact_kind: str,
    base_dir: Path,
    betting_day: str,
    run_id: str,
) -> Path:
    if artifact_kind == "SCRIPT_EVIDENCE":
        candidates = _script_evidence_candidates(base_dir, betting_day, run_id, step_id)
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return candidates[0]
    return artifact_path_for(base_dir, betting_day, run_id, step_id)


def discover_input_refs_for_step(
    step_id: str,
    base_dir: Path,
    betting_day: str,
    run_id: str,
    manifest: PipelineManifest | None = None,
) -> list[AgentWorkOrderInputRef]:
    """Find and hash files for upstream step dependencies."""
    if manifest is None:
        from bet.pipeline.manifest import load_pipeline_manifest
        manifest = load_pipeline_manifest()

    step = next((s for s in manifest.steps if s.id == step_id), None)

    if step and step.depends_on is not None:
        dependencies = step.depends_on
    else:
        dependencies = STEP_UPSTREAM_DEPENDENCIES.get(step_id, [])

    if step and step.required_inputs is not None and step.execution_mode != "agent_artifact":
        required_inputs = step.required_inputs
    else:
        required_inputs = dependencies

    # Build dependency map for transitive validation
    dep_map = {}
    for s in manifest.steps:
        s_id = s.id
        if s_id:
            if s.depends_on is not None:
                dep_map[s_id] = s.depends_on
            else:
                dep_map[s_id] = STEP_UPSTREAM_DEPENDENCIES.get(s_id, [])

    # Transitive closure helper
    def get_transitive_dependencies(sid: str, visited=None) -> set[str]:
        if visited is None:
            visited = set()
        visited.add(sid)
        result = set()
        for dep in dep_map.get(sid, []):
            if dep not in visited:
                result.add(dep)
                result.update(get_transitive_dependencies(dep, visited))
        return result

    transitive_deps = get_transitive_dependencies(step_id)

    # Validate semantic relationship: all required_inputs must be in transitive dependencies
    for req in required_inputs:
        if req not in transitive_deps:
            raise ValueError(
                f"Semantic relationship violation: required_input '{req}' for step '{step_id}' "
                f"is not a direct or transitive dependency."
            )

    run_root = resolve_run_root(betting_day, run_id, base_dir).resolve()

    input_refs = []
    for dep_id in dependencies:
        dep_step = next((s for s in manifest.steps if s.id == dep_id), None)
        if not dep_step:
            raise ValueError(f"Dependency step {dep_id} not found in manifest")

        # Resolve dynamic artifact kind from dependency step's execution_mode
        exec_mode = dep_step.execution_mode
        if exec_mode == "script":
            kind = "SCRIPT_EVIDENCE"
        elif exec_mode == "agent_artifact":
            kind = "AGENT_ARTIFACT"
        elif exec_mode == "human_gate":
            kind = "HUMAN_GATE"
        elif exec_mode == "state_only":
            kind = "STATE_MARKER"
        else:
            raise ValueError(f"Unsupported execution_mode '{exec_mode}' for dependency {dep_id}")

        is_required = dep_id in required_inputs

        # Resolve path
        path = _resolve_input_ref_path(
            dep_id, kind, Path(base_dir), betting_day, run_id
        )
        resolved_path = Path(path).resolve()

        # Enforce validations if the dependency is required
        if is_required:
            # 1. Check if file exists
            if not resolved_path.is_file():
                raise ValueError(f"Required dependency file is missing: {resolved_path}")

            # 2. Check if readable and parseable JSON
            try:
                with open(resolved_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
            except Exception as e:
                raise ValueError(f"Required dependency file {resolved_path} is unreadable or invalid JSON: {e}")

            # 3. Check empty SHA-256
            sha256 = calculate_sha256(resolved_path)
            if not sha256:
                raise ValueError(f"Required dependency file {resolved_path} has an empty SHA-256")

            # 4. Check outside current run or wrong day/run
            if not resolved_path.is_relative_to(run_root):
                raise ValueError(f"Required dependency file {resolved_path} is outside the current run root {run_root}")

            # 5. Check wrong artifact type / step_id / betting_day / run_id
            if content.get("artifact_type") != kind:
                raise ValueError(
                    f"Wrong artifact type for {resolved_path}: "
                    f"expected {kind}, got {content.get('artifact_type')}"
                )
            if content.get("step_id") != dep_id:
                raise ValueError(
                    f"Wrong step_id in artifact for {resolved_path}: "
                    f"expected {dep_id}, got {content.get('step_id')}"
                )
            if content.get("betting_day") != betting_day:
                raise ValueError(
                    f"Wrong betting_day in artifact for {resolved_path}: "
                    f"expected {betting_day}, got {content.get('betting_day')}"
                )
            if content.get("run_id") != run_id:
                raise ValueError(
                    f"Wrong run_id in artifact for {resolved_path}: "
                    f"expected {run_id}, got {content.get('run_id')}"
                )
        else:
            sha256 = calculate_sha256(resolved_path)

        input_refs.append(
            AgentWorkOrderInputRef(
                step_id=dep_id,
                artifact_kind=kind,
                path=str(resolved_path),
                required=is_required,
                sha256=sha256,
            )
        )
    return input_refs


def get_manifest_sha(base_dir: Path) -> str:
    manifest_path = base_dir / "config" / "pipeline_manifest.json"
    if not manifest_path.is_file():
        from bet.pipeline.manifest import discover_repo_root
        manifest_path = discover_repo_root() / "config" / "pipeline_manifest.json"
    return calculate_sha256(manifest_path)


def get_source_head(base_dir: Path) -> str:
    from bet.pipeline.manifest import discover_repo_root
    try:
        root = discover_repo_root()
    except Exception:
        root = base_dir
    git_head = root / ".git" / "HEAD"
    if git_head.is_file():
        try:
            content = git_head.read_text(encoding="utf-8").strip()
            if content.startswith("ref:"):
                parts = content.split(" ")
                if len(parts) >= 2:
                    ref_path = root / ".git" / parts[1]
                    if ref_path.is_file():
                        return ref_path.read_text(encoding="utf-8").strip()
            else:
                return content
        except Exception:
            pass
    return "UNKNOWN"


def build_agent_work_order(
    *,
    betting_day: str,
    run_id: str,
    step_id: str,
    runtime_mode: str,
    base_dir: Path,
    manifest: PipelineManifest | None = None,
    manifest_path: Path | None = None,
) -> AgentWorkOrder:
    """Construct an AgentWorkOrder matching schemas and policies."""
    if step_id not in POLICIES:
        raise ValueError(f"No agent work order policy defined for step_id: {step_id}")

    policy = POLICIES[step_id]
    import os
    target_wo_path = work_order_path_for(base_dir, betting_day, run_id, step_id)
    if target_wo_path.exists():
        try:
            existing_wo = json.loads(target_wo_path.read_text(encoding="utf-8"))
            created_at = existing_wo.get("created_at") or os.environ.get("BET_PIPELINE_RUN_AS_OF_UTC") or utc_now_iso()
        except Exception:
            created_at = os.environ.get("BET_PIPELINE_RUN_AS_OF_UTC") or utc_now_iso()
    else:
        created_at = os.environ.get("BET_PIPELINE_RUN_AS_OF_UTC") or utc_now_iso()

    if manifest is None:
        from bet.pipeline.manifest import load_pipeline_manifest
        if manifest_path is None:
            manifest_path = Path(base_dir) / "config" / "pipeline_manifest.json"
            if not manifest_path.is_file():
                from bet.pipeline.manifest import discover_repo_root
                manifest_path = discover_repo_root() / "config" / "pipeline_manifest.json"
        manifest = load_pipeline_manifest(manifest_path)

    input_refs = discover_input_refs_for_step(step_id, base_dir, betting_day, run_id, manifest=manifest)
    expected_path = expected_agent_artifact_path_for(
        base_dir, betting_day, run_id, step_id
    )

    required_output = AgentWorkOrderOutputContract(
        artifact_type="AGENT_ARTIFACT",
        step_id=step_id,
        expected_path=str(expected_path),
        required_statuses=["PASS", "BLOCK", "COMMAND_REQUEST"],
        schema_requirements=policy.schema_requirements,
    )

    work_order_id = f"WO-{run_id}-{step_id}"
    manifest_sha = get_manifest_sha(base_dir)
    source_head = get_source_head(base_dir)

    step_obj = next((s for s in manifest.steps if s.id == step_id), None)
    hard_rules = step_obj.hard_rules if step_obj and step_obj.hard_rules is not None else policy.hard_rules
    agent = step_obj.agent if step_obj and step_obj.agent is not None else policy.agent

    return AgentWorkOrder(
        schema_version=1,
        work_order_id=work_order_id,
        work_order_type="AGENT_ARTIFACT_REQUEST",
        pipeline_id="bet_pipeline_v1",
        betting_day=betting_day,
        run_id=run_id,
        step_id=step_id,
        agent=agent,
        runtime_mode=runtime_mode,
        created_at=created_at,
        status="PENDING_AGENT",
        input_refs=input_refs,
        required_output=required_output,
        hard_rules=hard_rules,
        forbidden_outputs=policy.forbidden_outputs,
        instructions=policy.instructions,
        manifest_sha256=manifest_sha,
        source_head=source_head,
    )


def write_agent_work_order(
    work_order: AgentWorkOrder,
    base_dir: Path,
) -> Path:
    """Atomically write an agent work order to its expected location."""
    target_path = work_order_path_for(
        base_dir,
        work_order.betting_day,
        work_order.run_id,
        work_order.step_id,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)

    payload = work_order.to_jsonable()
    from bet.pipeline.canonical_continuity import (
        canonical_json_bytes,
        ContinuityContractError,
    )

    new_bytes = canonical_json_bytes(payload)

    if target_path.exists():
        existing_bytes = target_path.read_bytes()
        try:
            existing_payload = json.loads(existing_bytes)
            existing_canon = canonical_json_bytes(existing_payload)
        except Exception:
            existing_canon = existing_bytes

        if existing_canon != new_bytes:
            raise ContinuityContractError(
                f"WORK_ORDER_CONFLICT: {target_path} already exists with different content"
            )
        return target_path

    write_json_atomic(target_path, payload)
    return target_path
