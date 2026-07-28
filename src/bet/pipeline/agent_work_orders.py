"""Data contracts, schema generation, and disk writers for agent work orders."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bet.pipeline.run_evidence import utc_now_iso, write_json_atomic
from bet.pipeline.artifact_gate import artifact_path_for
from bet.pipeline.runtime_paths import resolve_run_root, runtime_artifact_dir


from pydantic import Field, field_validator, model_validator
from bet.pipeline.contracts.base import StrictBaseModel
from bet.pipeline.sharding.models import FactAcquisitionPlanV1


class AgentWorkOrderInputRefV1(StrictBaseModel):
    step_id: str
    artifact_kind: str
    path: str
    required: bool
    sha256: str

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump()


class AgentWorkOrderOutputContractV1(StrictBaseModel):
    artifact_type: str
    step_id: str
    expected_path: str
    required_statuses: list[str]
    schema_requirements: dict[str, Any] = Field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump()


class AgentWorkOrderPolicy(StrictBaseModel):
    forbidden_outputs: list[str]
    instructions: dict[str, Any] = Field(default_factory=dict)
    schema_requirements: dict[str, Any] = Field(default_factory=dict)


class AgentWorkOrderV1(StrictBaseModel):
    schema_version: int = 1
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
    input_refs: list[AgentWorkOrderInputRefV1] = Field(default_factory=list)
    required_output: AgentWorkOrderOutputContractV1
    hard_rules: list[str] = Field(default_factory=list)
    forbidden_outputs: list[str] = Field(default_factory=list)
    instructions: dict[str, Any] = Field(default_factory=dict)
    manifest_sha256: str = "UNKNOWN"
    source_head: str = "UNKNOWN"
    allowed_tools: list[str] = Field(default_factory=list)
    task_allowlist: list[str] = Field(default_factory=list)
    acquisition_plan: FactAcquisitionPlanV1 | None = None
    parent_work_order_id: str | None = None
    parent_work_order_sha256: str | None = None
    plan_id: str | None = None
    plan_sha256: str | None = None

    def to_jsonable(self) -> dict[str, Any]:
        return self.model_dump()


AgentWorkOrderInputRef = AgentWorkOrderInputRefV1
AgentWorkOrderOutputContract = AgentWorkOrderOutputContractV1
AgentWorkOrder = AgentWorkOrderV1


VALID_PROJECT_TOOLS = frozenset({
    "bet_sqlite_query",
    "webfetch",
    "websearch",
    "brave-search_brave_web_search",
    "read",
    "glob",
    "grep",
})


def compute_allowed_tools(plan_tools: list[str] | None, agent_profile_tools: list[str]) -> list[str]:
    """Compute allowed tools as intersection of plan requirements and agent profile tools."""
    if not plan_tools:
        browsing_tools = {"webfetch", "websearch", "brave-search_brave_web_search"}
        return sorted([t for t in agent_profile_tools if t in VALID_PROJECT_TOOLS and t not in browsing_tools])
    return sorted(list(set(plan_tools) & set(agent_profile_tools) & VALID_PROJECT_TOOLS))


OUTPUT_CONTRACT_NOTES = [
    "Template scaffolds are not accepted final output.",
    "Fill required evidence fields before returning an artifact.",
    "BLOCK is acceptable and preferred over guessing or implied approval.",
    "PASS requires full contract evidence for the specific step.",
]


POLICIES: dict[str, AgentWorkOrderPolicy] = {
    "S2.3": AgentWorkOrderPolicy(
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
        runtime_artifacts / step_id / f"{step_id}_artifact.json",
        run_root / "artifacts" / f"{step_id}.json",
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
    manifest: PipelineManifest,
) -> list[AgentWorkOrderInputRef]:
    """Find and hash files for upstream step dependencies."""
    target_step = next((s for s in manifest.steps if s.id == step_id), None)
    if not target_step:
        raise ValueError(f"Step {step_id} not found in manifest")

    dependencies = list(target_step.depends_on or [])
    input_refs = []
    for dep_id in dependencies:
        dep_step = next((s for s in manifest.steps if s.id == dep_id), None)
        if not dep_step:
            raise ValueError(f"Dependency step {dep_id} not found in manifest")

        if dep_step.execution_mode == "script":
            kind = "SCRIPT_EVIDENCE"
        elif dep_step.execution_mode == "agent_artifact":
            kind = "AGENT_ARTIFACT"
        else:
            raise ValueError(f"Unsupported execution mode '{dep_step.execution_mode}' for dependency {dep_id}")

        path = _resolve_input_ref_path(
            dep_id, kind, Path(base_dir), betting_day, run_id
        )

        if not path.is_file():
            raise ValueError(f"Required dependency file is missing: {path}")

        try:
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                raise ValueError("Empty file")
            data = json.loads(content)
        except Exception:
            raise ValueError(f"Dependency {dep_id} file is unreadable or invalid JSON")

        if data.get("betting_day") != betting_day:
            raise ValueError(f"Wrong betting_day in artifact: {data.get('betting_day')} vs {betting_day}")

        if data.get("run_id") != run_id:
            raise ValueError(f"Wrong run_id in artifact: {data.get('run_id')} vs {run_id}")

        if data.get("artifact_type") != kind:
            raise ValueError(f"Wrong artifact type: {data.get('artifact_type')} vs {kind}")

        sha256 = calculate_sha256(path)

        input_refs.append(
            AgentWorkOrderInputRef(
                step_id=dep_id,
                artifact_kind=kind,
                path=str(path),
                required=True,
                sha256=sha256,
            )
        )
    return input_refs


def get_manifest_sha(base_dir: Path, manifest_path: Path | None = None) -> str:
    if manifest_path is None:
        manifest_path = base_dir / "config" / "pipeline_manifest.json"
        if not manifest_path.is_file():
            from bet.pipeline.manifest import discover_repo_root
            manifest_path = discover_repo_root() / "config" / "pipeline_manifest.json"
    return calculate_sha256(manifest_path)


def get_source_head(base_dir: Path) -> str:
    from bet.pipeline.manifest import discover_repo_root
    import subprocess
    try:
        root = discover_repo_root()
    except Exception:
        root = base_dir
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        sha = res.stdout.strip()
        if sha:
            return sha
    except Exception:
        pass
    return "UNKNOWN"


def load_agent_work_order_from_dict(data: dict[str, Any]) -> AgentWorkOrder:
    input_refs = [
        AgentWorkOrderInputRef(
            step_id=ref["step_id"],
            artifact_kind=ref["artifact_kind"],
            path=ref["path"],
            required=ref["required"],
            sha256=ref["sha256"],
        )
        for ref in data["input_refs"]
    ]
    req_out = data["required_output"]
    required_output = AgentWorkOrderOutputContract(
        artifact_type=req_out["artifact_type"],
        step_id=req_out["step_id"],
        expected_path=req_out["expected_path"],
        required_statuses=req_out["required_statuses"],
        schema_requirements=req_out["schema_requirements"],
    )
    return AgentWorkOrder(
        schema_version=data["schema_version"],
        work_order_id=data["work_order_id"],
        work_order_type=data["work_order_type"],
        pipeline_id=data["pipeline_id"],
        betting_day=data["betting_day"],
        run_id=data["run_id"],
        step_id=data["step_id"],
        agent=data["agent"],
        runtime_mode=data["runtime_mode"],
        created_at=data["created_at"],
        status=data["status"],
        input_refs=input_refs,
        required_output=required_output,
        hard_rules=data["hard_rules"],
        forbidden_outputs=data["forbidden_outputs"],
        instructions=data["instructions"],
        manifest_sha256=data.get("manifest_sha256", "UNKNOWN"),
        source_head=data.get("source_head", "UNKNOWN"),
        allowed_tools=data.get("allowed_tools", []),
        task_allowlist=data.get("task_allowlist", []),
        acquisition_plan=data.get("acquisition_plan"),
        parent_work_order_id=data.get("parent_work_order_id"),
        parent_work_order_sha256=data.get("parent_work_order_sha256"),
        plan_id=data.get("plan_id"),
        plan_sha256=data.get("plan_sha256"),
    )


def build_agent_work_order(
    *,
    betting_day: str,
    run_id: str,
    step_id: str,
    runtime_mode: str,
    base_dir: Path,
    manifest: Any | None = None,
    manifest_path: Any | None = None,
    **kwargs: Any,
) -> AgentWorkOrder:
    """Construct an AgentWorkOrder matching schemas and policies."""
    from bet.pipeline.canonical_continuity import ContinuityContractError

    if step_id not in POLICIES:
        raise ValueError(f"No agent work order policy defined for step_id: {step_id}")

    policy = POLICIES[step_id]
    target_path = work_order_path_for(base_dir, betting_day, run_id, step_id)
    if target_path.is_file():
        try:
            content = target_path.read_text(encoding="utf-8")
            existing_data = json.loads(content)
            existing_wo = load_agent_work_order_from_dict(existing_data)
        except Exception:
            existing_wo = None

        if existing_wo is not None:
            if (
                existing_wo.betting_day != betting_day
                or existing_wo.run_id != run_id
                or existing_wo.step_id != step_id
                or existing_wo.runtime_mode != runtime_mode
            ):
                raise ContinuityContractError(f"WORK_ORDER_DRIFT: Identifiers mismatched in existing work order at {target_path}")

            if manifest is None:
                from bet.pipeline.manifest import load_pipeline_manifest
                manifest = load_pipeline_manifest(manifest_path)
            manifest_step = next((s for s in manifest.steps if s.id == step_id), None)
            if not manifest_step:
                raise ValueError(f"Step {step_id} not found in manifest")
            if not manifest_step.agent:
                raise ValueError(f"Step {step_id} has no agent specified in manifest")
            if manifest_step.hard_rules is None:
                raise ValueError(f"Step {step_id} has no hard_rules specified in manifest")

            candidate_agent = manifest_step.agent
            candidate_hard_rules = manifest_step.hard_rules
            candidate_inputs = discover_input_refs_for_step(step_id, base_dir, betting_day, run_id, manifest)
            candidate_manifest_sha = get_manifest_sha(base_dir, manifest_path=manifest_path)
            candidate_source_head = get_source_head(base_dir)
            expected_path = expected_agent_artifact_path_for(base_dir, betting_day, run_id, step_id)

            if existing_wo.agent != candidate_agent:
                raise ContinuityContractError(f"WORK_ORDER_DRIFT: owner changed from {existing_wo.agent} to {candidate_agent}")

            if existing_wo.hard_rules != candidate_hard_rules:
                raise ContinuityContractError(f"WORK_ORDER_DRIFT: hard_rules changed")

            if len(existing_wo.input_refs) != len(candidate_inputs):
                raise ContinuityContractError("WORK_ORDER_DRIFT: inputs count changed")
            for ref_existing, ref_candidate in zip(existing_wo.input_refs, candidate_inputs):
                if (
                    ref_existing.step_id != ref_candidate.step_id
                    or ref_existing.artifact_kind != ref_candidate.artifact_kind
                    or Path(ref_existing.path).resolve() != Path(ref_candidate.path).resolve()
                    or ref_existing.required != ref_candidate.required
                    or ref_existing.sha256 != ref_candidate.sha256
                ):
                    raise ContinuityContractError("WORK_ORDER_DRIFT: inputs changed")

            if existing_wo.manifest_sha256 != candidate_manifest_sha:
                raise ContinuityContractError("WORK_ORDER_DRIFT: manifest_sha256 changed")

            if existing_wo.source_head != candidate_source_head:
                raise ContinuityContractError("WORK_ORDER_DRIFT: source_head changed")

            if Path(existing_wo.required_output.expected_path).resolve() != Path(expected_path).resolve():
                raise ContinuityContractError("WORK_ORDER_DRIFT: expected output path changed")

            if existing_wo.required_output.schema_requirements != policy.schema_requirements:
                raise ContinuityContractError("WORK_ORDER_DRIFT: schema_requirements changed")

            return existing_wo

    created_at = utc_now_iso()

    if manifest is None:
        from bet.pipeline.manifest import load_pipeline_manifest
        manifest = load_pipeline_manifest(manifest_path)

    input_refs = discover_input_refs_for_step(step_id, base_dir, betting_day, run_id, manifest)
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

    manifest_step = next((s for s in manifest.steps if s.id == step_id), None)
    if not manifest_step:
        raise ValueError(f"Step {step_id} not found in manifest")
    if not manifest_step.agent:
        raise ValueError(f"Step {step_id} has no agent specified in manifest")
    if manifest_step.hard_rules is None:
        raise ValueError(f"Step {step_id} has no hard_rules specified in manifest")

    manifest_sha = get_manifest_sha(base_dir, manifest_path=manifest_path)
    source_head = get_source_head(base_dir)
    if source_head == "UNKNOWN" or not source_head:
        raise ContinuityContractError("Git source_head is UNKNOWN which is forbidden for persisted work orders")

    acq_plan_data = kwargs.get("acquisition_plan")
    allowed_tools = kwargs.get("allowed_tools", [])
    if acq_plan_data is None and step_id in {"S2.3", "S2.5", "S2.7", "S2.9", "S5"}:
        allowed_tools = ["bet_sqlite_query", "webfetch", "read", "glob", "grep"]
        eid = kwargs.get("canonical_event_id") or "event_scope_shortlist"
        acq_plan_data = {
            "plan_id": f"PLAN-{work_order_id}",
            "canonical_event_id": eid,
            "sport": kwargs.get("sport") or "football",
            "max_queries": 10,
            "requirements": [
                {
                    "requirement_id": f"REQ-{step_id}-01",
                    "fact_type": "LINEUP_INJURY_FORM_FACTS",
                    "sport": kwargs.get("sport") or "football",
                    "market_families_affected": ["result", "corners", "goals"],
                    "requirement_level": "REQUIRED_FOR_PRICING",
                    "allowed_tools": list(allowed_tools),
                    "max_age_hours": 48,
                    "min_independent_sources": 2,
                }
            ],
        }

    parsed_plan = None
    if isinstance(acq_plan_data, dict):
        # Remove extra dict fields like query_budget
        acq_plan_data.pop("query_budget", None)
        parsed_plan = FactAcquisitionPlanV1.model_validate(acq_plan_data)
    elif isinstance(acq_plan_data, FactAcquisitionPlanV1):
        parsed_plan = acq_plan_data

    return AgentWorkOrder(
        schema_version=1,
        work_order_id=work_order_id,
        work_order_type="AGENT_ARTIFACT_REQUEST",
        pipeline_id="bet_pipeline_v1",
        betting_day=betting_day,
        run_id=run_id,
        step_id=step_id,
        agent=manifest_step.agent,
        runtime_mode=runtime_mode,
        created_at=created_at,
        status="PENDING_AGENT",
        input_refs=input_refs,
        required_output=required_output,
        hard_rules=manifest_step.hard_rules,
        forbidden_outputs=policy.forbidden_outputs,
        instructions=policy.instructions,
        manifest_sha256=manifest_sha,
        source_head=source_head,
        allowed_tools=allowed_tools,
        task_allowlist=kwargs.get("task_allowlist", []),
        acquisition_plan=parsed_plan,
        parent_work_order_id=kwargs.get("parent_work_order_id"),
        parent_work_order_sha256=kwargs.get("parent_work_order_sha256"),
        plan_id=kwargs.get("plan_id"),
        plan_sha256=kwargs.get("plan_sha256"),
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
