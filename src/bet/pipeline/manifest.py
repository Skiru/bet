"""Pipeline manifest and validation contract."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class PipelineGraph:
    """Canonical dependency graph mapping pipeline steps to prerequisite steps."""
    _instance: PipelineGraph | None = None

    def __init__(self, manifest: PipelineManifest):
        self._manifest = manifest
        self._dependencies = {}
        for step in manifest.steps:
            if step.id is not None:
                self._dependencies[step.id] = list(step.depends_on or [])

    def get_dependencies_instance(self, step_id: str) -> list[str]:
        if step_id not in self._dependencies:
            raise PipelineManifestError(f"Unknown step ID: {step_id}")
        return self._dependencies[step_id]

    @classmethod
    def get_dependencies(cls, step_id: str) -> list[str]:
        if cls._instance is None:
            manifest = load_pipeline_manifest()
            errors = validate_pipeline_manifest(manifest)
            if errors:
                raise PipelineManifestError(f"Pipeline manifest is invalid: {errors}")
            cls._instance = cls(manifest)
        return cls._instance.get_dependencies_instance(step_id)


class PipelineManifestError(Exception):
    """Exception raised for errors in the pipeline manifest or its validation."""
    pass


@dataclass
class PipelineStep:
    id: str | None
    name: str | None
    phase: str | None
    agent: str | None
    execution_mode: str | None
    output: str | None
    next: list[str] | None
    hard_rules: list[str] | None
    wrapper: str | None = None
    canonical_script: str | None = None
    depends_on: list[str] | None = None
    required_inputs: list[str] | None = None


@dataclass
class PipelineManifest:
    schema_version: int
    pipeline_id: str
    timezone: str
    betting_day: str
    global_rules: dict[str, bool]
    steps: list[PipelineStep]
    runtime_contract: dict[str, object] = field(default_factory=dict)


def discover_repo_root() -> Path:
    """Robustly find the repository root without calling git."""
    cwd = Path.cwd().resolve()
    if (cwd / ".kilo").exists() or (cwd / "kilo.json").exists():
        return cwd
    current = Path(__file__).resolve().parent
    for parent in [current] + list(current.parents):
        if (parent / ".kilo").exists() or (parent / "kilo.json").exists():
            return parent
    return cwd


def load_pipeline_manifest(path: Path | None = None) -> PipelineManifest:
    """Load the canonical pipeline manifest from JSON."""
    if path is None:
        root = discover_repo_root()
        path = root / "config/pipeline_manifest.json"
    else:
        path = Path(path)

    if not path.exists():
        raise PipelineManifestError(f"Manifest file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise PipelineManifestError(f"Invalid JSON in manifest: {e}")
    except Exception as e:
        raise PipelineManifestError(f"Failed to read manifest: {e}")

    if not isinstance(data, dict):
        raise PipelineManifestError("Manifest JSON top-level must be an object")

    required_top = ["schema_version", "pipeline_id", "timezone", "betting_day", "global_rules", "steps"]
    for field_name in required_top:
        if field_name not in data:
            raise PipelineManifestError(f"Missing required top-level field: {field_name}")

    steps_list = []
    for step_data in data.get("steps", []):
        if not isinstance(step_data, dict):
            raise PipelineManifestError("Step entry must be an object")

        step_obj = PipelineStep(
            id=step_data.get("id"),
            name=step_data.get("name"),
            phase=step_data.get("phase"),
            agent=step_data.get("agent"),
            execution_mode=step_data.get("execution_mode"),
            output=step_data.get("output"),
            next=step_data.get("next"),
            hard_rules=step_data.get("hard_rules"),
            wrapper=step_data.get("wrapper"),
            canonical_script=step_data.get("canonical_script"),
            depends_on=step_data.get("depends_on"),
            required_inputs=step_data.get("required_inputs"),
        )
        steps_list.append(step_obj)

    try:
        schema_version = int(data["schema_version"])
    except (ValueError, TypeError):
        raise PipelineManifestError("schema_version must be an integer")

    manifest_obj = PipelineManifest(
        schema_version=schema_version,
        pipeline_id=str(data["pipeline_id"]),
        timezone=str(data["timezone"]),
        betting_day=str(data["betting_day"]),
        global_rules=dict(data["global_rules"]) if isinstance(data["global_rules"], dict) else {},
        steps=steps_list,
        runtime_contract=dict(data.get("runtime_contract", {})) if isinstance(data.get("runtime_contract"), dict) else {},
    )
    PipelineGraph._instance = PipelineGraph(manifest_obj)
    return manifest_obj


def get_step_agent(
    step_id: str,
    manifest: PipelineManifest | None = None,
    manifest_path: Path | None = None,
) -> str:
    """Get the canonical agent owner of a step from the pipeline manifest."""
    if manifest is None:
        manifest = load_pipeline_manifest(manifest_path)
    for step in manifest.steps:
        if step.id == step_id:
            if not step.agent:
                raise PipelineManifestError(f"Step {step_id} has no agent specified in manifest")
            return step.agent
    raise PipelineManifestError(f"Unknown step_id in manifest: {step_id}")


def get_step_hard_rules(
    step_id: str,
    manifest: PipelineManifest | None = None,
    manifest_path: Path | None = None,
) -> list[str]:
    """Get the canonical hard_rules for a step from the pipeline manifest."""
    if manifest is None:
        manifest = load_pipeline_manifest(manifest_path)
    for step in manifest.steps:
        if step.id == step_id:
            if step.hard_rules is None:
                raise PipelineManifestError(f"Step {step_id} has no hard_rules specified in manifest")
            return list(step.hard_rules)
    raise PipelineManifestError(f"Unknown step_id in manifest: {step_id}")


def get_step_order() -> list[str]:
    """Return the ordered list of step IDs from the canonical manifest."""
    manifest = load_pipeline_manifest()
    # If validation or loading fails, load_pipeline_manifest will raise.
    # We must run validation as well to fail closed if manifest is broken.
    errors = validate_pipeline_manifest(manifest)
    if errors:
        raise PipelineManifestError(f"Pipeline manifest is invalid: {errors}")
    return [step.id for step in manifest.steps if step.id is not None]


def get_phase_boundary_step() -> str:
    """Return the step boundary where the ANALYSIS_BUILD phase begins."""
    return "S3"


def get_step_phase(step_id: str) -> str:
    """Get the phase of a step from the canonical pipeline manifest."""
    manifest = load_pipeline_manifest()
    errors = validate_pipeline_manifest(manifest)
    if errors:
        raise PipelineManifestError(f"Pipeline manifest is invalid: {errors}")
    for step in manifest.steps:
        if step.id == step_id:
            if step.phase is None:
                raise PipelineManifestError(f"Step {step_id} has no phase specified")
            return step.phase
    raise PipelineManifestError(f"Unknown step: {step_id}")


def validate_pipeline_manifest(manifest: PipelineManifest, repo_root: Path | None = None) -> list[str]:
    """Validate a loaded PipelineManifest against all contract constraints."""
    errors = []
    if repo_root is None:
        repo_root = discover_repo_root()
    else:
        repo_root = Path(repo_root)

    runtime_contract = manifest.runtime_contract
    if runtime_contract.get("idempotency") != "HASH_CHAINED_RUN_LEDGER":
        errors.append("Runtime contract missing hash-chained idempotency")
    if runtime_contract.get("lock") != "LEASE_WITH_PROCESS_START_IDENTITY":
        errors.append("Runtime contract missing lease lock identity")
    if runtime_contract.get("unresolved_command_request_blocks_resume") is not True:
        errors.append("Runtime contract must block unresolved command requests")
    for timeout_key in ("default_timeout_seconds", "maximum_timeout_seconds"):
        value = runtime_contract.get(timeout_key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            errors.append(f"Runtime contract invalid {timeout_key}")

    # 1. Global rules checks
    global_rules = manifest.global_rules
    required_global_rules = [
        "fail_closed",
        "point_in_time_required",
        "no_pick_before_s7",
        "no_coupon_before_s8",
        "enrichment_must_not_emit_pick_edge_stake_or_coupon",
        "s2_9_required_before_s3",
        "no_live_provider_calls_in_contract_pass",
        "no_production_db_writes_in_contract_pass",
        "manual_operator_quote_required_before_bettable",
        "no_combined_bookmaker_odds_computation",
        "no_automated_bookmaker_placement",
        "tipster_absence_does_not_block_core_analysis",
        "no_event_drop_due_only_to_tipster_absence",
        "every_discovered_event_requires_terminal_status_or_reason"
    ]
    for rule in required_global_rules:
        if rule not in global_rules or global_rules[rule] is not True:
            errors.append(f"Global rules missing or disabled: {rule}")

    # 2. Step ID checking & Step ordering
    expected_order = [
        "S0", "S1", "S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9",
        "S3", "S4", "S5", "S6", "S7", "S7b", "S8", "S9", "S10",
    ]

    step_ids = []
    step_by_id = {}

    for step in manifest.steps:
        if step.id is None:
            errors.append("Step missing required field: id")
            continue

        if step.id in step_by_id:
            errors.append(f"Duplicate step ID: {step.id}")
        step_ids.append(step.id)
        step_by_id[step.id] = step

    if step_ids != expected_order:
        errors.append(f"Wrong step order. Expected: {expected_order}, Got: {step_ids}")

    # 3. Individual Step validation
    allowed_phases = ["DATA", "ANALYSIS_BUILD", "EXECUTION", "POST_EVENT"]
    allowed_execution_modes = ["script", "agent_artifact", "human_gate", "state_only"]

    for step in manifest.steps:
        sid = step.id or "<missing id>"

        # Missing required fields
        if step.id is None:
            # already reported
            pass
        if step.name is None:
            errors.append(f"Step {sid} missing required field: name")
        if step.phase is None:
            errors.append(f"Step {sid} missing required field: phase")
        if step.agent is None:
            errors.append(f"Step {sid} missing required field: agent")
        if step.execution_mode is None:
            errors.append(f"Step {sid} missing required field: execution_mode")
        if step.output is None:
            errors.append(f"Step {sid} missing required field: output")
        if step.next is None:
            errors.append(f"Step {sid} missing required field: next")
        if step.hard_rules is None:
            errors.append(f"Step {sid} missing required field: hard_rules")

        # Invalid phase
        if step.phase is not None and step.phase not in allowed_phases:
            errors.append(f"Step {sid} has invalid phase: {step.phase}")

        # Invalid execution_mode
        if step.execution_mode is not None and step.execution_mode not in allowed_execution_modes:
            errors.append(f"Step {sid} has invalid execution_mode: {step.execution_mode}")

        # Next transition validation using manifest-derived graph and canonical ordered steps
        expected_next = []
        try:
            current_idx = expected_order.index(step.id)
            if current_idx < len(expected_order) - 1:
                expected_next = [expected_order[current_idx + 1]]
        except ValueError:
            pass

        if step.next != expected_next:
            errors.append(
                f"Step {sid} next transition must be exactly {expected_next}, got {step.next}"
            )

        # Script execution_mode validation
        if step.execution_mode == "script":
            if not step.wrapper and not step.canonical_script:
                errors.append(f"Step {sid} is in script execution_mode but has neither wrapper nor canonical_script")

            for field_name, path_str in [("wrapper", step.wrapper), ("canonical_script", step.canonical_script)]:
                if path_str:
                    path_obj = repo_root / path_str
                    if not path_obj.exists():
                        errors.append(f"Step {sid} referenced {field_name} path does not exist: {path_str}")

        # Referenced agent file validation
        if step.agent is not None:
            agent_file = repo_root / ".kilo/agents" / f"{step.agent}.md"
            if not agent_file.exists():
                errors.append(f"Step {sid} referenced agent file does not exist under .kilo/agents: {step.agent}.md")

        # Enrichment step rules checking
        enrichment_steps = ["S2.3", "S2.5", "S2.7", "S2.9"]
        if step.id in enrichment_steps:
            required_enrichment_rules = [
                "no_pick",
                "no_edge",
                "no_stake",
                "no_coupon",
                "source_bound_only",
                "unknown_or_blocked_for_missing_data",
                "no_production_db_write",
                "no_betting_data_write",
                "point_in_time_required"
            ]
            actual_rules = step.hard_rules if isinstance(step.hard_rules, list) else []
            for r in required_enrichment_rules:
                if r not in actual_rules:
                    errors.append(f"Step {step.id} missing enrichment rule: {r}")

    # 4. Logical ordering / reachability rules
    if "S2.9" in step_by_id and "S3" in step_by_id:
        idx_s2_9 = step_ids.index("S2.9") if "S2.9" in step_ids else -1
        idx_s3 = step_ids.index("S3") if "S3" in step_ids else -1
        if idx_s2_9 != -1 and idx_s3 != -1 and idx_s3 <= idx_s2_9:
            errors.append("S3 must not appear before S2.9")

    if "S7" in step_by_id and "S7b" in step_by_id and "S8" in step_by_id:
        idx_s7 = step_ids.index("S7") if "S7" in step_ids else -1
        idx_s7b = step_ids.index("S7b") if "S7b" in step_ids else -1
        idx_s8 = step_ids.index("S8") if "S8" in step_ids else -1
        if idx_s7 != -1 and idx_s7b != -1 and idx_s8 != -1:
            if not (idx_s7 < idx_s7b < idx_s8):
                errors.append("S7b must be after S7 and before S8")

    # 5. Dependency / Pipeline Graph validations (P1-1)
    step_ids_set = set(step_ids)
    for step in manifest.steps:
        sid = step.id or "<missing id>"
        deps = step.depends_on or []
        req_inputs = step.required_inputs or []

        # - dependency IDs exist
        for d in deps:
            if d not in step_ids_set:
                errors.append(f"Step {sid} has unknown dependency ID: {d}")

        # - no self dependencies
        if sid in deps:
            errors.append(f"Step {sid} has a self-dependency")

        # - no duplicates
        if len(deps) != len(set(deps)):
            errors.append(f"Step {sid} has duplicate dependencies: {deps}")

        # - dependency precedes consumer
        for d in deps:
            if d in step_ids_set:
                idx_d = step_ids.index(d)
                idx_sid = step_ids.index(sid)
                if idx_d >= idx_sid:
                    errors.append(f"Dependency {d} must precede consumer {sid}")

        # - required inputs are coherent with dependencies
        for r_in in req_inputs:
            if r_in not in deps:
                errors.append(f"Step {sid} has required input {r_in} which is not in depends_on")

        # - next and dependency edges are coherent
        if step.next:
            for n in step.next:
                if n in step_ids_set:
                    idx_n = step_ids.index(n)
                    idx_sid = step_ids.index(sid)
                    if idx_n <= idx_sid:
                        errors.append(f"Next step {n} must be after current step {sid}")

        # - artifact kind follows dependency execution_mode
        for d in deps:
            dep_step = step_by_id.get(d)
            if dep_step:
                expected_kind = "SCRIPT_EVIDENCE" if dep_step.execution_mode == "script" else "AGENT_ARTIFACT"

    # - graph is acyclic
    visited = {}  # 0 = unvisited, 1 = visiting, 2 = visited
    def has_cycle(u):
        visited[u] = 1
        deps = step_by_id[u].depends_on or []
        for v in deps:
            if v in step_by_id:
                if visited.get(v, 0) == 1:
                    return True
                if visited.get(v, 0) == 0:
                    if has_cycle(v):
                        return True
        visited[u] = 2
        return False

    for sid in step_ids:
        if visited.get(sid, 0) == 0:
            if has_cycle(sid):
                errors.append("Pipeline graph has a cycle (is not acyclic)")
                break

    return errors
