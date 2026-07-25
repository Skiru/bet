#!/usr/bin/env python3
"""Validate the complete active seven-agent betting control plane."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENT_NAMES = (
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
)
SKILL_NAMES = (
    "betting-pipeline-contract",
    "betting-evidence-contract",
    "betting-pipeline-runtime",
    "context-safe-agentics",
)
LEGACY_PATTERN = re.compile(
    r"bet-(?:orchestrator|engineer|scanner|scout|enricher|statistician|valuator|"
    r"challenger|test-engineer|db-analyst|reconciler|settler(?!-postevent))"
)
TEXTUAL_CAP_PATTERN = re.compile(
    r"Maximum\s+\d+.*steps|one tool call per turn|one phase per session|"
    r"start (?:a )?fresh session after phase|do not cross a phase boundary",
    re.IGNORECASE,
)
ACTIVE_TEXT_FILES = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "config/pipeline_manifest.json",
    *sorted((ROOT / ".kilo/docs").glob("**/*.md")),
    *sorted((ROOT / ".kilo/rules").glob("*.md")),
    *sorted((ROOT / ".kilo/shared").glob("*.md")),
    *sorted((ROOT / ".kilo/prompts").glob("*.md")),
    *(ROOT / ".kilo/skills" / name / "SKILL.md" for name in SKILL_NAMES),
)


def frontmatter(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    if not raw.startswith(b"---\n") or b"\n---\n" not in raw:
        raise ValueError("frontmatter delimiters are not byte-valid")
    header, body = raw[4:].split(b"\n---\n", 1)
    parsed = yaml.safe_load(header.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("frontmatter is not a mapping")
    return parsed, body.decode("utf-8")


def git_changed_files() -> list[str]:
    # Exported source snapshots and release tarballs legitimately have no
    # local ``main`` ref.  Validation must remain deterministic in that
    # topology instead of crashing before it can inspect the control plane.
    committed: list[str] = []
    configured_base = os.environ.get("POWER_AGENT_VALIDATION_BASE_REF")
    base_candidates = tuple(
        candidate
        for candidate in (configured_base, "main", "origin/main")
        if candidate
    )
    for candidate in base_candidates:
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{candidate}^{{commit}}"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if resolved.returncode != 0:
            continue
        merge_base = subprocess.run(
            ["git", "merge-base", candidate, "HEAD"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if merge_base.returncode != 0:
            continue
        base = merge_base.stdout.strip()
        committed = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--diff-filter=ACMRTUXB",
                f"{base}..HEAD",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        break
    working: list[str] = []
    if not os.environ.get("POWER_AGENT_VALIDATION_SKIP_WORKTREE_REPORTS"):
        working = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    # This direct tracked-file check covers the single-commit snapshot case,
    # where there is no meaningful base against which to calculate a patch.
    tracked_reports = subprocess.run(
        ["git", "ls-files", "reports/pipeline_runs"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return sorted(set(committed + working + tracked_reports))


def contains_value(value: object, needle: str) -> bool:
    if isinstance(value, dict):
        return any(contains_value(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(contains_value(item, needle) for item in value)
    return value == needle


def validate() -> list[str]:
    errors: list[str] = []
    agent_paths = sorted((ROOT / ".kilo/agents").glob("bet-*.md"))
    if [p.stem for p in agent_paths] != sorted(AGENT_NAMES):
        errors.append(f"agent roster mismatch: {[p.stem for p in agent_paths]}")
    if list((ROOT / ".kilo/prompts").glob("bet-*.md")):
        errors.append("legacy bet-* prompt exists")

    permissions: dict[str, dict] = {}
    for name in AGENT_NAMES:
        path = ROOT / ".kilo/agents" / f"{name}.md"
        try:
            data, body = frontmatter(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        permissions[name] = data.get("permission", {})
        if "model" in data:
            errors.append(f"{name}: explicit model override")
        if "steps" in data:
            errors.append(f"{name}: explicit steps override")
        if data.get("permission", {}).get("question") != "deny":
            errors.append(f"{name}: question is not deny")
        if contains_value(data.get("permission", {}), "ask"):
            errors.append(f"{name}: ask permission present")
        if TEXTUAL_CAP_PATTERN.search(body):
            errors.append(f"{name}: textual step/session cap present")

    partner_names = set(AGENT_NAMES) - {"bet-executor"}
    executor_task = permissions.get("bet-executor", {}).get("task", {})
    if not isinstance(executor_task, dict) or executor_task.get("*") != "deny":
        errors.append("bet-executor: wildcard task deny missing")
    elif {
        k for k, v in executor_task.items() if k != "*" and v == "allow"
    } != partner_names:
        errors.append("bet-executor: task allowlist is not exactly six partners")

    for name, perms in permissions.items():
        expected_bash = "allow" if name in {"bet-executor", "bet-auditor"} else "deny"
        if perms.get("bash") != expected_bash:
            errors.append(f"{name}: bash permission mismatch")
        for mutation in ("edit", "write", "apply_patch"):
            if perms.get(mutation) != "deny":
                errors.append(f"{name}: {mutation} must be deny")

    for name in SKILL_NAMES:
        path = ROOT / ".kilo/skills" / name / "SKILL.md"
        try:
            data, _ = frontmatter(path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{name}: {exc}")
            continue
        if data.get("name") != name:
            errors.append(f"{name}: skill name does not match directory")
        if "model" in data or "permission" in data:
            errors.append(f"{name}: skill defines agent configuration")

    for path in ACTIVE_TEXT_FILES:
        text = path.read_text(encoding="utf-8")
        if LEGACY_PATTERN.search(text):
            errors.append(f"{path.relative_to(ROOT)}: legacy agent reference")
        if re.search("bet" + "clic", text, re.IGNORECASE):
            errors.append(
                f"{path.relative_to(ROOT)}: active retired-operator reference"
            )
        if TEXTUAL_CAP_PATTERN.search(text):
            errors.append(f"{path.relative_to(ROOT)}: textual step/session cap")

    manifest = json.loads(
        (ROOT / "config/pipeline_manifest.json").read_text(encoding="utf-8")
    )
    if {step["agent"] for step in manifest["steps"]} - set(AGENT_NAMES):
        errors.append("manifest uses a non-power agent")
    serialized_manifest = json.dumps(manifest)
    for forbidden in ("minimum_one_valid_tip",):
        if forbidden in serialized_manifest:
            errors.append(f"manifest contains {forbidden}")

    global_rules = manifest["global_rules"]
    for required in (
        "tipster_absence_does_not_block_core_analysis",
        "no_event_drop_due_only_to_tipster_absence",
        "every_discovered_event_requires_terminal_status_or_reason",
        "manual_operator_quote_required_before_bettable",
        "human_entered_quote_required",
        "final_coupon_blocked_without_visible_operator_quote",
    ):
        if global_rules.get(required) is not True:
            errors.append(f"manifest missing required global rule {required}")
    if global_rules.get("operator_workflow") != "SUPERBET_MANUAL_BET_BUILDER":
        errors.append("manifest operator workflow is not Superbet manual Bet Builder")

    all_active_text = "\n".join(
        path.read_text(encoding="utf-8") for path in ACTIVE_TEXT_FILES
    )
    for required_text in (
        "S9 is human-only",
        "NO_ACTION_TERMINAL",
        "safe checkpoint",
        "same worktree",
        "real operator odds",
    ):
        if required_text.lower() not in all_active_text.lower():
            errors.append(
                f"active control plane missing semantic contract: {required_text}"
            )

    matrix = (ROOT / ".kilo/docs/betting_agent_tool_matrix.md").read_text(
        encoding="utf-8"
    )
    matrix_rows = {
        "bet-executor": "| `bet-executor` | allow | deny | deny | allow | "
        "exactly six partner agents; wildcard deny |",
        "bet-researcher": "| `bet-researcher` | deny | allow | allow | allow | deny |",
        "bet-modeler": "| `bet-modeler` | deny | allow | deny | allow | deny |",
        "bet-risk-gatekeeper": "| `bet-risk-gatekeeper` | deny | allow | allow | "
        "allow | deny |",
        "bet-builder": "| `bet-builder` | deny | deny | deny | allow | deny |",
        "bet-auditor": "| `bet-auditor` | allow (verification only) | allow | deny | "
        "allow | deny |",
        "bet-settler-postevent": "| `bet-settler-postevent` | deny | allow | deny | "
        "allow | deny |",
    }
    for name, row in matrix_rows.items():
        if row not in matrix:
            errors.append(f"tool matrix capability row mismatch for {name}")

    for changed in git_changed_files():
        if changed.startswith("reports/pipeline_runs/"):
            errors.append(f"report artifact in source diff: {changed}")

    # 5. Work-order generation matrix and validation inside TemporaryDirectory
    import tempfile
    from bet.pipeline.manifest import load_pipeline_manifest
    from bet.pipeline.agent_work_orders import build_agent_work_order
    from bet.pipeline.artifact_gate import artifact_path_for

    try:
        manifest_obj = load_pipeline_manifest()

        with tempfile.TemporaryDirectory() as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            betting_day = "2026-07-25"
            run_id = "validate-run"

            # Determine dependency graph and steps to test
            from bet.pipeline.manifest import PipelineGraph

            # Seed valid, current-run predecessor artifacts dynamically
            all_steps = [s.id for s in manifest_obj.steps if s.id]
            for s_id in all_steps:
                path = tmp_dir / "pipeline_runs" / betting_day / run_id / "artifacts" / f"{s_id}.json"
                path.parent.mkdir(parents=True, exist_ok=True)

                m_step = next((s for s in manifest_obj.steps if s.id == s_id), None)
                if m_step and m_step.execution_mode == "script":
                    data = {
                        "schema_version": 1,
                        "artifact_type": "SCRIPT_EVIDENCE",
                        "step_id": s_id,
                        "status": "PASS",
                        "betting_day": betting_day,
                        "run_id": run_id,
                        "payload": {}
                    }
                else:
                    data = {
                        "schema_version": 1,
                        "artifact_type": "AGENT_ARTIFACT",
                        "step_id": s_id,
                        "status": "PASS",
                        "betting_day": betting_day,
                        "run_id": run_id,
                        "point_in_time_as_of": "2026-07-25T12:00:00Z",
                        "source_bound": True,
                        "no_pick_edge_stake_coupon_emitted": True,
                        "production_selectable": False,
                        "betting_decisions_enabled": False,
                        "sources": [],
                        "payload": {}
                    }
                path.write_text(json.dumps(data), encoding="utf-8")

            # Validate each agent_artifact step
            agent_artifact_steps = [
                s for s in manifest_obj.steps if s.execution_mode == "agent_artifact"
            ]
            for step in agent_artifact_steps:
                step_id = step.id
                wo = build_agent_work_order(
                    betting_day=betting_day,
                    run_id=run_id,
                    step_id=step_id,
                    runtime_mode="DRY_RUN",
                    base_dir=tmp_dir,
                )

                # Validate: generated agent == manifest agent
                if wo.agent != step.agent:
                    errors.append(f"{step_id}: generated agent {wo.agent} != manifest agent {step.agent}")

                # Validate: agent exists
                agent_path = ROOT / ".kilo/agents" / f"{wo.agent}.md"
                if not agent_path.exists():
                    errors.append(f"{step_id}: agent file does not exist: {agent_path}")

                # Validate: agent is task-allowed
                if wo.agent != "bet-executor":
                    executor_task = permissions.get("bet-executor", {}).get("task", {})
                    if executor_task.get(wo.agent) != "allow":
                        errors.append(f"{step_id}: agent {wo.agent} is not task-allowed by bet-executor")

                # Validate: hard_rules exactly match manifest
                if sorted(wo.hard_rules) != sorted(step.hard_rules):
                    errors.append(f"{step_id}: hard_rules mismatch: {wo.hard_rules} vs manifest {step.hard_rules}")

                # Validate: every required input exists and has non-empty SHA
                if not wo.input_refs:
                    expected_deps = PipelineGraph.get_dependencies(step_id)
                    if expected_deps:
                        errors.append(f"{step_id}: has expected dependencies {expected_deps} but no input_refs generated")
                for ref in wo.input_refs:
                    ref_path = Path(ref.path)
                    if not ref_path.exists():
                        errors.append(f"{step_id}: required input {ref.step_id} path does not exist: {ref.path}")
                    if not ref.sha256 or len(ref.sha256) != 64:
                        errors.append(f"{step_id}: required input {ref.step_id} has invalid or empty SHA-256: {ref.sha256}")

                # Validate: paths remain inside the temporary run root
                resolved_tmp = tmp_dir.resolve()
                if not Path(wo.required_output.expected_path).resolve().is_relative_to(resolved_tmp):
                    errors.append(f"{step_id}: expected output path escapes temporary run root: {wo.required_output.expected_path}")
                for ref in wo.input_refs:
                    if not Path(ref.path).resolve().is_relative_to(resolved_tmp):
                        errors.append(f"{step_id}: input ref path escapes temporary run root: {ref.path}")

    except Exception as exc:
        errors.append(f"Work-order matrix validation failed with exception: {exc}")

    return errors


def main() -> int:
    errors = validate()
    print(
        json.dumps({"status": "FAIL" if errors else "PASS", "errors": errors}, indent=2)
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
