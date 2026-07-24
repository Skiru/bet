"""Pipeline manifest and validation contract."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


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
    depends_on: list[str] | None = None
    required_inputs: list[str] | None = None
    wrapper: str | None = None
    canonical_script: str | None = None


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
            depends_on=step_data.get("depends_on"),
            required_inputs=step_data.get("required_inputs"),
            wrapper=step_data.get("wrapper"),
            canonical_script=step_data.get("canonical_script")
        )
        steps_list.append(step_obj)

    try:
        schema_version = int(data["schema_version"])
    except (ValueError, TypeError):
        raise PipelineManifestError("schema_version must be an integer")

    return PipelineManifest(
        schema_version=schema_version,
        pipeline_id=str(data["pipeline_id"]),
        timezone=str(data["timezone"]),
        betting_day=str(data["betting_day"]),
        global_rules=dict(data["global_rules"]) if isinstance(data["global_rules"], dict) else {},
        steps=steps_list,
        runtime_contract=dict(data.get("runtime_contract", {})) if isinstance(data.get("runtime_contract"), dict) else {},
    )


CANONICAL_POWER_AGENTS: tuple[str, ...] = (
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
)


def get_executor_allowed_tasks(repo_root: Path | None = None) -> set[str]:
    """Extract allowed task names from bet-executor.md frontmatter."""
    if repo_root is None:
        repo_root = discover_repo_root()
    executor_md = Path(repo_root) / ".kilo/agents" / "bet-executor.md"
    if not executor_md.exists():
        return set()
    try:
        import yaml
        content = executor_md.read_text(encoding="utf-8")
        if content.startswith("---\n") and "\n---\n" in content:
            header = content[4:].split("\n---\n", 1)[0]
            data = yaml.safe_load(header)
            if isinstance(data, dict):
                task = data.get("permission", {}).get("task", {})
                if isinstance(task, dict) and task.get("*") == "deny":
                    return {k for k, v in task.items() if k != "*" and v == "allow"}
    except Exception:
        pass
    return set()


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


class PipelineGraph:
    """Canonical validated pipeline graph built from manifest."""

    def __init__(self, manifest: PipelineManifest):
        self.manifest = manifest
        self.steps_by_id = {s.id: s for s in manifest.steps if s.id}
        self.order = [s.id for s in manifest.steps if s.id]

    def direct_dependencies(self, step_id: str) -> list[str]:
        step = self.steps_by_id.get(step_id)
        if not step:
            return []
        if step.depends_on is not None:
            return list(step.depends_on)
        return [s.id for s in self.manifest.steps if s.next and step_id in s.next and s.id]

    def all_upstream_dependencies(self, step_id: str) -> list[str]:
        visited: set[str] = set()
        def traverse(sid: str) -> None:
            for dep in self.direct_dependencies(sid):
                if dep not in visited:
                    visited.add(dep)
                    traverse(dep)
        traverse(step_id)
        return [sid for sid in self.order if sid in visited]

    def required_artifacts_before_step(self, step_id: str) -> tuple[str, ...]:
        step = self.steps_by_id.get(step_id)
        if step and step.required_inputs is not None:
            return tuple(step.required_inputs)
        return tuple(self.direct_dependencies(step_id))


def get_upstream_dependencies(
    step_id: str,
    manifest: PipelineManifest | None = None,
    manifest_path: Path | None = None,
) -> list[str]:
    """Get the canonical upstream dependency step IDs for a given step_id from the manifest graph."""
    if manifest is None:
        manifest = load_pipeline_manifest(manifest_path)
    graph = PipelineGraph(manifest)
    if step_id not in graph.steps_by_id:
        raise PipelineManifestError(f"Unknown step_id in manifest: {step_id}")
    return graph.direct_dependencies(step_id)


def get_required_artifacts_before_step(
    step_id: str,
    manifest: PipelineManifest | None = None,
) -> tuple[str, ...]:
    """Get prerequisite step IDs whose artifacts are required before step_id."""
    if manifest is None:
        manifest = load_pipeline_manifest()
    graph = PipelineGraph(manifest)
    return graph.required_artifacts_before_step(step_id)


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

        # Next transition validation
        expected_transitions = {
            "S0": ["S1"],
            "S1": ["S1e"],
            "S1e": ["S2"],
            "S2": ["S2.3"],
            "S2.3": ["S2.5"],
            "S2.5": ["S2.7"],
            "S2.7": ["S2.9"],
            "S2.9": ["S3"],
            "S3": ["S4"],
            "S4": ["S5"],
            "S5": ["S6"],
            "S6": ["S7"],
            "S7": ["S7b"],
            "S7b": ["S8"],
            "S8": ["S9"],
            "S9": ["S10"],
            "S10": [],
        }
        if step.id in expected_transitions:
            if step.next != expected_transitions[step.id]:
                errors.append(f"Step {sid} next transition must be exactly {expected_transitions[step.id]}, got {step.next}")

        # Script execution_mode validation
        if step.execution_mode == "script":
            if not step.wrapper and not step.canonical_script:
                errors.append(f"Step {sid} is in script execution_mode but has neither wrapper nor canonical_script")

            for field_name, path_str in [("wrapper", step.wrapper), ("canonical_script", step.canonical_script)]:
                if path_str:
                    path_obj = repo_root / path_str
                    if not path_obj.exists():
                        errors.append(f"Step {sid} referenced {field_name} path does not exist: {path_str}")

        # Referenced agent validation
        if step.agent is not None:
            if step.agent not in CANONICAL_POWER_AGENTS:
                errors.append(f"Step {sid} agent '{step.agent}' is not a canonical power agent")
            agent_file = repo_root / ".kilo/agents" / f"{step.agent}.md"
            if not agent_file.exists():
                errors.append(f"Step {sid} referenced agent file does not exist under .kilo/agents: {step.agent}.md")

        # Execution mode task allowlist validation
        if step.execution_mode == "agent_artifact" and step.agent is not None:
            allowed_tasks = get_executor_allowed_tasks(repo_root)
            if step.agent not in allowed_tasks:
                errors.append(
                    f"Step {sid} agent_artifact owner '{step.agent}' is not allowed in bet-executor task allowlist"
                )

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

    return errors
