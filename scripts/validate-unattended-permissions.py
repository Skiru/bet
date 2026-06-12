#!/usr/bin/env python3
"""
Phase 4A unattended betting-agent permission validator.
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = PROJECT_ROOT / ".kilo" / "agents"

CANONICAL_AGENTS = [
    "bet-orchestrator",
    "bet-settler",
    "bet-db-analyst",
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-reconciler",
    "bet-builder",
    "bet-engineer",
    "bet-test-engineer",
]
SPECIALISTS = [name for name in CANONICAL_AGENTS if name != "bet-orchestrator"]
TASK_ALLOWLIST = set(SPECIALISTS)
ALL_MCP_TOOLS = ["webfetch", "websearch", "brave-search_*", "context7_*", "playwright_*", "kilo-playwright_*"]
FAIL_CLOSED_TOOLS = ["background_process", "agent_manager", "kilo_local_recall"]


def load_frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        raise ValueError(f"missing frontmatter: {path}")
    _, frontmatter, _ = content.split("---", 2)
    parsed = yaml.safe_load(frontmatter)
    if not isinstance(parsed, dict):
        raise ValueError(f"invalid frontmatter: {path}")
    return parsed


def resolved_permission(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if value.get("*") == "deny" and all(v == "deny" for v in value.values()):
            return "deny"
        if any(v == "ask" for v in value.values()):
            return "ask"
        if any(v == "allow" for v in value.values()):
            return "conditional_allow"
        return "conditional_deny"
    if value is None:
        return "unspecified"
    return f"unknown:{type(value).__name__}"


def require(results: list[tuple[str, str, str]], gate: str, condition: bool, detail: str) -> None:
    results.append((gate, "PASS" if condition else "FAIL", detail))


def validate_agent(agent_name: str, config: dict[str, Any]) -> list[tuple[str, str, str]]:
    permissions = config.get("permission", {})
    results: list[tuple[str, str, str]] = []

    require(results, "question_denied", resolved_permission(permissions.get("question")) == "deny", f"question={resolved_permission(permissions.get('question'))}")

    ask_tools = [name for name, value in permissions.items() if resolved_permission(value) == "ask"]
    require(results, "zero_ask_permissions", not ask_tools, f"ask_tools={ask_tools or 'none'}")

    require(results, "unknown_tools_fail_closed", all(resolved_permission(permissions.get(tool)) == "deny" for tool in ALL_MCP_TOOLS),
            "all web/MCP tools denied")

    require(results, "bash_denied", resolved_permission(permissions.get("bash")) == "deny", f"bash={resolved_permission(permissions.get('bash'))}")
    require(results, "edit_denied", resolved_permission(permissions.get("edit")) == "deny", f"edit={resolved_permission(permissions.get('edit'))}")
    require(results, "write_denied", resolved_permission(permissions.get("write")) == "deny", f"write={resolved_permission(permissions.get('write'))}")
    require(results, "apply_patch_denied", resolved_permission(permissions.get("apply_patch")) == "deny", f"apply_patch={resolved_permission(permissions.get('apply_patch'))}")
    require(results, "sqlite_denied", resolved_permission(permissions.get("bet_sqlite_query")) == "deny", f"bet_sqlite_query={resolved_permission(permissions.get('bet_sqlite_query'))}")
    require(results, "fail_closed_extras", all(resolved_permission(permissions.get(tool)) == "deny" for tool in FAIL_CLOSED_TOOLS),
            f"extras={{tool: resolved_permission(permissions.get(tool)) for tool in FAIL_CLOSED_TOOLS}}")

    if agent_name == "bet-orchestrator":
        task_perm = permissions.get("task")
        allowed = {key for key, value in (task_perm or {}).items() if value == "allow"}
        require(results, "task_allowlist_exact", isinstance(task_perm, dict) and allowed == TASK_ALLOWLIST and task_perm.get("*") == "deny",
                f"allowed={sorted(allowed)}")
        require(results, "artifact_writer_allowed", resolved_permission(permissions.get("bet_artifact_write")) == "allow", f"bet_artifact_write={resolved_permission(permissions.get('bet_artifact_write'))}")
        require(results, "script_runner_denied", resolved_permission(permissions.get("bet_script_run")) == "deny", f"bet_script_run={resolved_permission(permissions.get('bet_script_run'))}")
        require(results, "todowrite_allowed", resolved_permission(permissions.get("todowrite")) == "allow", f"todowrite={resolved_permission(permissions.get('todowrite'))}")
        require(results, "todoread_allowed", resolved_permission(permissions.get("todoread")) == "allow", f"todoread={resolved_permission(permissions.get('todoread'))}")
    else:
        require(results, "task_denied", resolved_permission(permissions.get("task")) == "deny", f"task={resolved_permission(permissions.get('task'))}")
        require(results, "todowrite_denied", resolved_permission(permissions.get("todowrite")) == "deny", f"todowrite={resolved_permission(permissions.get('todowrite'))}")
        require(results, "todoread_denied", resolved_permission(permissions.get("todoread")) == "deny", f"todoread={resolved_permission(permissions.get('todoread'))}")
        if agent_name == "bet-builder":
            require(results, "artifact_writer_allowed", resolved_permission(permissions.get("bet_artifact_write")) == "allow", f"bet_artifact_write={resolved_permission(permissions.get('bet_artifact_write'))}")
        else:
            require(results, "artifact_writer_absent_or_denied", resolved_permission(permissions.get("bet_artifact_write")) in {"deny", "unspecified"},
                    f"bet_artifact_write={resolved_permission(permissions.get('bet_artifact_write'))}")

    if agent_name == "bet-engineer":
        require(results, "fixture_executor_allowed", resolved_permission(permissions.get("bet_script_run")) == "allow", f"bet_script_run={resolved_permission(permissions.get('bet_script_run'))}")
    else:
        require(results, "fixture_executor_not_broadened", resolved_permission(permissions.get("bet_script_run")) in {"deny", "unspecified"},
                f"bet_script_run={resolved_permission(permissions.get('bet_script_run'))}")

    return results


NEGATIVE_MUTATIONS = {
    "question_ask": lambda cfg: cfg["permission"].__setitem__("question", "ask"),
    "bash_allow": lambda cfg: cfg["permission"].__setitem__("bash", "allow"),
    "sqlite_allow": lambda cfg: cfg["permission"].__setitem__("bet_sqlite_query", "allow"),
    "webfetch_allow": lambda cfg: cfg["permission"].__setitem__("webfetch", "allow"),
    "builder_write_allow": lambda cfg: cfg["permission"].__setitem__("write", "allow"),
    "specialist_task_allow": lambda cfg: cfg["permission"].__setitem__("task", "allow"),
}


def run_negative_tests() -> list[tuple[str, str, str]]:
    source = load_frontmatter(AGENTS_DIR / "bet-builder.md")
    specialist = load_frontmatter(AGENTS_DIR / "bet-scout.md")
    results: list[tuple[str, str, str]] = []

    for name, mutate in NEGATIVE_MUTATIONS.items():
        target = copy.deepcopy(specialist if name == "specialist_task_allow" else source)
        mutate(target)
        checked = validate_agent("bet-scout" if name == "specialist_task_allow" else "bet-builder", target)
        failed = any(status == "FAIL" for _, status, _ in checked)
        require(results, f"negative_{name}", failed, "mutation must be detected")
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--negative-tests", action="store_true")
    args = parser.parse_args()

    total_pass = 0
    total_fail = 0

    print("=" * 80)
    print("PHASE 4A UNATTENDED PERMISSION VALIDATOR")
    print("=" * 80)

    for agent_name in CANONICAL_AGENTS:
        path = AGENTS_DIR / f"{agent_name}.md"
        config = load_frontmatter(path)
        results = validate_agent(agent_name, config)
        print(f"\n## {agent_name}")
        for gate, status, detail in results:
            print(f"  [{status}] {gate}: {detail}")
            if status == "PASS":
                total_pass += 1
            else:
                total_fail += 1

    if args.negative_tests:
        print("\n## negative-mutation-tests")
        for gate, status, detail in run_negative_tests():
            print(f"  [{status}] {gate}: {detail}")
            if status == "PASS":
                total_pass += 1
            else:
                total_fail += 1

    print("\n" + "=" * 80)
    print(f"PASS: {total_pass}")
    print(f"FAIL: {total_fail}")
    print(f"VERDICT: {'PASS' if total_fail == 0 else 'FAIL'}")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
