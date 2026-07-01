import json
import re
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/mkoziol/projects/bet")
AGENT_DIR = WORKSPACE_ROOT / ".kilo/agents"
PROMPT_DIR = WORKSPACE_ROOT / ".kilo/prompts"
DOCS_DIR = WORKSPACE_ROOT / "docs/pipeline"
ARTIFACT_DIR = WORKSPACE_ROOT / ".kilo/artifacts"

REQUIRED_AGENTS = [
    "bet-orchestrator",
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-builder",
    "bet-test-engineer",
    "bet-engineer",
]
OPTIONAL_AGENTS = ["bet-reconciler", "bet-db-analyst", "bet-settler"]
REQUIRED_PROMPTS = {
    "bet-orchestrator": "bet-orchestrator-v2.md",
    "bet-scanner": "bet-scanner.md",
    "bet-scout": "bet-scout.md",
    "bet-enricher": "bet-enricher.md",
    "bet-statistician": "bet-statistician.md",
    "bet-valuator": "bet-valuator.md",
    "bet-challenger": "bet-challenger.md",
    "bet-builder": "bet-builder.md",
    "bet-test-engineer": "bet-test-engineer.md",
    "bet-engineer": "bet-engineer.md",
    "bet-reconciler": "bet-reconciler.md",
    "bet-db-analyst": "bet-db-analyst.md",
    "bet-settler": "bet-settler.md",
}
REQUIRED_DOCS = [
    DOCS_DIR / "UI Selected Runtime Model Inheritance Policy.md",
    DOCS_DIR / "Betting Agent Anti-Loop and Step Budget Contract.md",
    DOCS_DIR / "Orchestrated Session Continuation Protocol.md",
    DOCS_DIR / "Unified Orchestrated Analyst Session Contract.md",
]
REQUIRED_PROMPT_SECTIONS = [
    "Role mission:",
    "Exact inputs:",
    "Exact outputs and artifacts:",
    "Allowed tools:",
    "Forbidden behavior:",
    "Exact final response schema:",
]
STALE_PATTERNS = [
    "Do not route this agent to GPT/OpenAI models.",
    "Do not use GPT/OpenAI fallback.",
    "ALL_REQUIRED_SUBAGENTS_GEMINI_3_5_FLASH_FLEX",
    "ACTIVE_RUNTIME_IS_GOOGLE_VERTEX_GEMINI",
    "BLOCKED_WRONG_ACTIVE_RUNTIME_MODEL",
    "always use the local Qwen",
]
FRONTMATTER_MODEL_PATTERN = re.compile(r"^model:\s*(.+)$", re.MULTILINE)


def has_exact_permission(path: Path, key: str, value: str) -> bool:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*{re.escape(value)}\s*$", re.MULTILINE)
    return bool(pattern.search(read_text(path)))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def has_frontmatter_model(path: Path) -> bool:
    return bool(FRONTMATTER_MODEL_PATTERN.search(read_text(path)))


def require_contains(failures: list[str], path: Path, needle: str, label: str) -> None:
    if needle not in read_text(path):
        failures.append(f"{path.relative_to(WORKSPACE_ROOT)}: missing {label}")


def require_absent(failures: list[str], path: Path, needle: str, label: str) -> None:
    if needle in read_text(path):
        failures.append(f"{path.relative_to(WORKSPACE_ROOT)}: contains {label}")


def audit() -> dict:
    failures: list[str] = []

    agent_files = {name: AGENT_DIR / f"{name}.md" for name in REQUIRED_AGENTS + OPTIONAL_AGENTS}
    prompt_files = {name: PROMPT_DIR / filename for name, filename in REQUIRED_PROMPTS.items()}

    for name in REQUIRED_AGENTS:
        if not agent_files[name].exists():
            failures.append(f"missing required agent file: .kilo/agents/{name}.md")
    for name, path in prompt_files.items():
        if name in REQUIRED_AGENTS + OPTIONAL_AGENTS and not path.exists():
            failures.append(f"missing prompt file: {path.relative_to(WORKSPACE_ROOT)}")
    for path in REQUIRED_DOCS:
        if not path.exists():
            failures.append(f"missing required doc: {path.relative_to(WORKSPACE_ROOT)}")

    for path in agent_files.values():
        if path.exists() and has_frontmatter_model(path):
            failures.append(f"{path.relative_to(WORKSPACE_ROOT)}: required betting agent pins a model override")

    scan_paths = [WORKSPACE_ROOT / "AGENTS.md"] + list(agent_files.values()) + list(prompt_files.values()) + REQUIRED_DOCS
    for path in scan_paths:
        if not path.exists():
            continue
        for pattern in STALE_PATTERNS:
            require_absent(failures, path, pattern, f"stale policy string `{pattern}`")

    require_absent(failures, WORKSPACE_ROOT / "AGENTS.md", "odds in Betclic", "stale Betclic operator flow")

    orchestrator = agent_files["bet-orchestrator"]
    require_contains(failures, orchestrator, "edit: deny", "repo-mutation deny")
    require_contains(failures, orchestrator, "write: deny", "repo-write deny")
    require_contains(failures, orchestrator, "apply_patch: deny", "repo-patch deny")
    require_contains(failures, orchestrator, "bash: deny", "shell deny")
    require_contains(failures, orchestrator, "bet_sqlite_query: deny", "db deny")
    require_contains(failures, orchestrator, "webfetch: deny", "web deny")

    engineer = agent_files["bet-engineer"]
    require_contains(failures, engineer, "edit: allow", "repo edit allow")
    require_contains(failures, engineer, "write: allow", "repo write allow")
    require_contains(failures, engineer, "apply_patch: allow", "repo patch allow")
    require_contains(failures, engineer, "bash: allow", "shell allow")
    require_contains(failures, engineer, "Never perform sports analysis", "sports-analysis boundary")

    for name in REQUIRED_AGENTS + OPTIONAL_AGENTS:
        path = agent_files[name]
        if path.exists():
            require_contains(failures, path, "playwright_*: deny", "browser deny")
            require_contains(failures, path, "kilo-playwright_*: deny", "browser deny")

    require_contains(failures, prompt_files["bet-scout"], "source reliability", "source reliability rule")
    require_contains(failures, prompt_files["bet-scout"], "bias", "source bias rule")
    require_contains(failures, prompt_files["bet-statistician"], "No fake stats, sample sizes, or probabilities.", "fake-probability guard")
    require_contains(failures, prompt_files["bet-valuator"], "No EV calculation without both valid odds and model probability.", "valuation prerequisite guard")
    require_contains(failures, prompt_files["bet-builder"], "manual human Superbet quote", "human quote guard")
    require_contains(failures, prompt_files["bet-test-engineer"], "No false PASS from a partial phase.", "false-pass guard")

    for name in REQUIRED_AGENTS + OPTIONAL_AGENTS:
        prompt_path = prompt_files[name]
        if not prompt_path.exists():
            continue
        for section in REQUIRED_PROMPT_SECTIONS:
            require_contains(failures, prompt_path, section, f"prompt section `{section}`")
        require_contains(failures, prompt_path, "No hidden reasoning or thought-trace leakage.", "thought-trace guard")
        require_contains(failures, prompt_path, "checkpoint", "continuation checkpoint rule")

    anti_loop_doc = DOCS_DIR / "Betting Agent Anti-Loop and Step Budget Contract.md"
    require_contains(failures, anti_loop_doc, "No recursive subagent delegation is allowed.", "anti-loop recursion guard")
    require_contains(failures, anti_loop_doc, "No final PASS from a partial phase.", "anti-loop false-pass guard")

    ui_doc = DOCS_DIR / "UI Selected Runtime Model Inheritance Policy.md"
    require_contains(failures, ui_doc, "ACTIVE_KILO_UI_RUNTIME_MODEL", "UI runtime source-of-truth")
    require_contains(failures, ui_doc, "No required betting agent may pin a provider or model", "no default model pins policy")

    continuation_doc = DOCS_DIR / "Orchestrated Session Continuation Protocol.md"
    require_contains(failures, continuation_doc, "do not repeat model repair", "continuation gate")
    require_contains(failures, continuation_doc, "run J2 only", "resume gate")

    for name in REQUIRED_AGENTS + OPTIONAL_AGENTS:
        path = agent_files[name]
        if not path.exists():
            continue
        if name != "bet-orchestrator":
            require_contains(failures, path, "task: deny", "recursive-delegation guard")

    summary = {
        "required_agent_files_exist": all(agent_files[name].exists() for name in REQUIRED_AGENTS),
        "required_prompt_files_exist": all(prompt_files[name].exists() for name in REQUIRED_AGENTS),
        "required_docs_exist": all(path.exists() for path in REQUIRED_DOCS),
        "required_betting_agents_do_not_pin_model_overrides": all(
            not has_frontmatter_model(agent_files[name]) for name in REQUIRED_AGENTS if agent_files[name].exists()
        ),
        "ui_runtime_inheritance_policy_exists": ui_doc.exists(),
        "anti_loop_contract_exists": anti_loop_doc.exists(),
        "orchestrator_cannot_mutate_repo": all(
            has_exact_permission(orchestrator, key, "deny")
            for key in ["edit", "write", "apply_patch", "bash"]
        ),
        "engineer_can_mutate_repo": all(
            has_exact_permission(engineer, key, "allow")
            for key in ["edit", "write", "apply_patch", "bash"]
        ),
        "no_stale_policy_strings": not any("stale policy string" in failure for failure in failures),
        "no_stale_betclic_operator_flow": not any("stale Betclic operator flow" in failure for failure in failures),
        "output_schemas_present": not any("prompt section `Exact final response schema:`" in failure for failure in failures),
        "continuation_protocol_present": not any("continuation gate" in failure or "resume gate" in failure for failure in failures),
        "no_recursive_delegation": not any("recursive-delegation guard" in failure for failure in failures),
        "verdict": "FAIL" if failures else "PASS",
    }
    return {"status": summary["verdict"], "summary": summary, "failures": failures}


def write_outputs(payload: dict) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACT_DIR / "bet_agent_system_production_audit_report.json"
    md_path = ARTIFACT_DIR / "bet_agent_system_production_audit_report.md"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Bet Agent System Production Audit Report",
        "",
        f"- Status: `{payload['status']}`",
        f"- Required agent files exist: `{payload['summary']['required_agent_files_exist']}`",
        f"- Required prompt files exist: `{payload['summary']['required_prompt_files_exist']}`",
        f"- Required docs exist: `{payload['summary']['required_docs_exist']}`",
        f"- Required betting agents do not pin model overrides: `{payload['summary']['required_betting_agents_do_not_pin_model_overrides']}`",
        f"- UI runtime inheritance policy exists: `{payload['summary']['ui_runtime_inheritance_policy_exists']}`",
        f"- Anti-loop contract exists: `{payload['summary']['anti_loop_contract_exists']}`",
        f"- Orchestrator cannot mutate repo: `{payload['summary']['orchestrator_cannot_mutate_repo']}`",
        f"- Engineer can mutate repo: `{payload['summary']['engineer_can_mutate_repo']}`",
        f"- No stale policy strings: `{payload['summary']['no_stale_policy_strings']}`",
        f"- No stale Betclic operator flow: `{payload['summary']['no_stale_betclic_operator_flow']}`",
        f"- Output schemas present: `{payload['summary']['output_schemas_present']}`",
        f"- Continuation protocol present: `{payload['summary']['continuation_protocol_present']}`",
        f"- No recursive delegation: `{payload['summary']['no_recursive_delegation']}`",
        "",
        "## Failures",
    ]
    if payload["failures"]:
        lines.extend([f"- {failure}" for failure in payload["failures"]])
    else:
        lines.append("- None")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    payload = audit()
    write_outputs(payload)
    print(f"Bet agent system production audit: {payload['status']}")
    if payload["failures"]:
        for failure in payload["failures"]:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
