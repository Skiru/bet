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
    DOCS_DIR / "Betting Agent Runtime Smoke Contract.md",
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
RUNTIME_SMOKE_SECTION = "RUNTIME SMOKE MODE:"
PRIMARY_AGENT = "bet-orchestrator"
DELEGATED_SUBAGENTS = [
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-builder",
    "bet-test-engineer",
]
UNKNOWN_CHILD_RUNTIME_VALUES = {None, "", "UNKNOWN", "UNKNOWN_NOT_INTROSPECTABLE"}


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


def detect_latest_runtime_smoke_run() -> Path | None:
    runs_root = WORKSPACE_ROOT / "reports/pipeline_runs"
    if not runs_root.exists():
        return None
    candidates: list[Path] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        if (run_dir / "corrected_agent_system_runtime_smoke.json").exists() or (
            run_dir / "agent_system_runtime_smoke.json"
        ).exists():
            candidates.append(run_dir)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_runtime_smoke_payload(run_dir: Path | None = None) -> tuple[dict, Path | None]:
    run_dir = run_dir or detect_latest_runtime_smoke_run()
    if run_dir is None:
        return {}, None
    for filename in ("corrected_agent_system_runtime_smoke.json", "agent_system_runtime_smoke.json"):
        candidate = run_dir / filename
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8")), run_dir
    return {}, run_dir


def is_unknown_child_runtime(value: str | None) -> bool:
    return value in UNKNOWN_CHILD_RUNTIME_VALUES


def normalize_runtime_smoke(payload: dict) -> dict:
    results = payload.get("results") or []
    result_map: dict[str, dict] = {}
    for result in results:
        agent_name = result.get("agent_name") or result.get("agent") or result.get("name")
        if not agent_name:
            continue
        blockers = result.get("blockers") or []
        if isinstance(blockers, str):
            blockers = [blockers]
        explicit_source = (
            result.get("conflicting_override_source")
            or result.get("explicit_model_override_source")
            or result.get("override_source")
        )
        result_map[agent_name] = {
            "agent_name": agent_name,
            "smoke_type": result.get("smoke_type"),
            "launched": bool(result.get("launched")),
            "artifact_written": bool(result.get("artifact_written")),
            "artifact_path": result.get("artifact_path"),
            "provider_model_not_found_error": bool(result.get("provider_model_not_found_error")),
            "explicit_model_override_detected": bool(result.get("explicit_model_override_detected")),
            "active_parent_runtime_model": result.get("active_parent_runtime_model") or payload.get("active_parent_runtime_model"),
            "child_runtime_model": result.get("child_runtime_model") or result.get("active_runtime_model"),
            "inherited_parent_model": result.get("inherited_parent_model"),
            "inheritance_proof_mode": result.get("inheritance_proof_mode"),
            "silent_fallback_detected": bool(result.get("silent_fallback_detected")),
            "invalid_smoke_test_detected": bool(result.get("invalid_smoke_test_detected")),
            "verdict": result.get("verdict"),
            "blocker": result.get("blocker"),
            "blockers": blockers,
            "finding_category": result.get("finding_category"),
            "conflicting_override_source": explicit_source,
        }
    return {
        "run_id": payload.get("run_id"),
        "active_parent_runtime_model": payload.get("active_parent_runtime_model"),
        "result_map": result_map,
        "conflicting_override_source": payload.get("conflicting_override_source") or "NONE",
    }


def evaluate_orchestrator_smoke(entry: dict, failures: list[str]) -> dict:
    smoke_type = entry.get("smoke_type")
    verdict = "PASS"
    if smoke_type != "PRIMARY_AGENT_CONFIG_SMOKE":
        failures.append("bet-orchestrator: invalid smoke type, expected PRIMARY_AGENT_CONFIG_SMOKE")
        verdict = "FAIL"
    if entry.get("invalid_smoke_test_detected"):
        failures.append("bet-orchestrator: invalid primary-as-subagent smoke detected")
        verdict = "FAIL"
    if entry.get("explicit_model_override_detected"):
        failures.append("bet-orchestrator: explicit conflicting override detected")
        verdict = "FAIL"
    if entry.get("provider_model_not_found_error"):
        failures.append("bet-orchestrator: ProviderModelNotFoundError detected")
        verdict = "FAIL"
    if entry.get("silent_fallback_detected"):
        failures.append("bet-orchestrator: silent fallback detected")
        verdict = "FAIL"
    return {
        "smoke_type": smoke_type,
        "verdict": verdict,
        "invalid_smoke_test_detected": bool(entry.get("invalid_smoke_test_detected")),
        "finding_category": entry.get("finding_category") or ("PASS" if verdict == "PASS" else "PRIMARY_AGENT_CONFIG_SMOKE_FAILURE"),
    }


def evaluate_delegated_subagent(agent_name: str, entry: dict, failures: list[str]) -> dict:
    smoke_type = entry.get("smoke_type")
    if smoke_type != "DELEGATED_SUBAGENT_LAUNCH_SMOKE":
        failures.append(f"{agent_name}: invalid smoke type, expected DELEGATED_SUBAGENT_LAUNCH_SMOKE")
    if entry.get("provider_model_not_found_error"):
        failures.append(f"{agent_name}: ProviderModelNotFoundError detected")
    if entry.get("silent_fallback_detected"):
        failures.append(f"{agent_name}: silent fallback detected")
    if entry.get("explicit_model_override_detected"):
        failures.append(f"{agent_name}: explicit conflicting override detected")
    if not entry.get("launched"):
        failures.append(f"{agent_name}: delegated launch smoke did not launch")
    if not entry.get("artifact_written") or not entry.get("artifact_path"):
        failures.append(f"{agent_name}: delegated launch smoke missing role-local artifact")

    parent_model = entry.get("active_parent_runtime_model")
    parent_known = bool(parent_model)
    child_runtime_model = entry.get("child_runtime_model")
    raw_inheritance = entry.get("inherited_parent_model")
    inheritance_proof_mode = "FAIL"
    if raw_inheritance == "PROVEN_BY_RUNTIME" or raw_inheritance is True:
        inheritance_proof_mode = "PROVEN_BY_RUNTIME"
    elif (
        not entry.get("provider_model_not_found_error")
        and not entry.get("silent_fallback_detected")
        and not entry.get("explicit_model_override_detected")
        and entry.get("launched")
        and entry.get("artifact_written")
        and parent_known
    ):
        inheritance_proof_mode = "PASS_BY_CONTRACT"
    if inheritance_proof_mode == "FAIL":
        failures.append(f"{agent_name}: inheritance proof failed")

    verdict = "PASS" if not any(failure.startswith(f"{agent_name}:") for failure in failures) else "FAIL"
    if is_unknown_child_runtime(child_runtime_model) and inheritance_proof_mode == "FAIL":
        failures.append(f"{agent_name}: child runtime model unknown without contract-safe inheritance proof")
        verdict = "FAIL"
    return {
        "smoke_type": smoke_type,
        "verdict": verdict,
        "child_runtime_model": child_runtime_model,
        "inheritance_proof_mode": inheritance_proof_mode,
        "artifact_path": entry.get("artifact_path"),
        "finding_category": entry.get("finding_category") or ("PASS" if verdict == "PASS" else "DELEGATED_SUBAGENT_LAUNCH_SMOKE_FAILURE"),
    }


def audit(runtime_smoke_payload: dict | None = None, run_dir: Path | None = None) -> dict:
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
    for name in [PRIMARY_AGENT, "bet-valuator", "bet-challenger", "bet-builder", "bet-test-engineer"]:
        require_contains(failures, prompt_files[name], RUNTIME_SMOKE_SECTION, "runtime smoke mode section")

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

    runtime_doc = DOCS_DIR / "Betting Agent Runtime Smoke Contract.md"
    require_contains(failures, runtime_doc, "PRIMARY_AGENT_CONFIG_SMOKE", "primary smoke contract")
    require_contains(failures, runtime_doc, "DELEGATED_SUBAGENT_LAUNCH_SMOKE", "delegated smoke contract")
    require_contains(failures, runtime_doc, "DIRECT_ROLE_SMOKE", "direct role smoke contract")
    require_contains(failures, runtime_doc, "PASS_BY_CONTRACT", "pass-by-contract inheritance mode")

    payload, detected_run_dir = load_runtime_smoke_payload(run_dir) if runtime_smoke_payload is None else (runtime_smoke_payload, run_dir)
    normalized_smoke = normalize_runtime_smoke(payload) if payload else {"result_map": {}, "active_parent_runtime_model": None, "conflicting_override_source": "NONE"}
    result_map = normalized_smoke["result_map"]
    if not payload:
        failures.append("runtime smoke report missing")

    orchestrator_smoke = evaluate_orchestrator_smoke(result_map.get(PRIMARY_AGENT, {}), failures) if result_map.get(PRIMARY_AGENT) else {
        "smoke_type": None,
        "verdict": "FAIL",
        "invalid_smoke_test_detected": False,
        "finding_category": "MISSING_PRIMARY_AGENT_CONFIG_SMOKE",
    }
    if not result_map.get(PRIMARY_AGENT):
        failures.append("bet-orchestrator: missing primary agent config smoke record")

    delegated_smoke: dict[str, dict] = {}
    for agent_name in DELEGATED_SUBAGENTS:
        entry = result_map.get(agent_name)
        if not entry:
            delegated_smoke[agent_name] = {
                "smoke_type": None,
                "verdict": "FAIL",
                "child_runtime_model": None,
                "inheritance_proof_mode": "FAIL",
                "artifact_path": None,
                "finding_category": "MISSING_DELEGATED_SUBAGENT_LAUNCH_SMOKE",
            }
            failures.append(f"{agent_name}: missing delegated launch smoke record")
            continue
        delegated_smoke[agent_name] = evaluate_delegated_subagent(agent_name, entry, failures)

    conflicting_override_source = normalized_smoke["conflicting_override_source"]
    if any(result_map.get(name, {}).get("explicit_model_override_detected") for name in DELEGATED_SUBAGENTS):
        if conflicting_override_source in {None, "", "UNKNOWN"}:
            failures.append("runtime smoke: conflicting override requires exact source")
            conflicting_override_source = "UNKNOWN"
    else:
        conflicting_override_source = "NONE"

    subagents_inherit = all(entry["inheritance_proof_mode"] in {"PROVEN_BY_RUNTIME", "PASS_BY_CONTRACT"} for entry in delegated_smoke.values()) if delegated_smoke else False
    all_subagents_wrote_artifacts = all(bool(entry.get("artifact_path")) and entry["verdict"] == "PASS" for entry in delegated_smoke.values()) if delegated_smoke else False
    provider_model_not_found_error = any(result_map.get(name, {}).get("provider_model_not_found_error") for name in [PRIMARY_AGENT, *DELEGATED_SUBAGENTS])
    silent_fallback_detected = any(result_map.get(name, {}).get("silent_fallback_detected") for name in [PRIMARY_AGENT, *DELEGATED_SUBAGENTS])
    explicit_override_detected = any(result_map.get(name, {}).get("explicit_model_override_detected") for name in [PRIMARY_AGENT, *DELEGATED_SUBAGENTS])

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
        "runtime_smoke_run_dir": str(detected_run_dir) if detected_run_dir else None,
        "primary_agent_config_smoke": orchestrator_smoke,
        "delegated_subagent_launch_smoke": delegated_smoke,
        "direct_role_smoke": {},
        "inheritance_proof_mode": "PASS_BY_CONTRACT" if subagents_inherit else "FAIL",
        "invalid_smoke_test_detected": orchestrator_smoke.get("invalid_smoke_test_detected", False),
        "subagents_inherit_active_runtime_model": subagents_inherit,
        "unknown_child_runtime_model_accepted_by_contract": all(
            entry["inheritance_proof_mode"] in {"PROVEN_BY_RUNTIME", "PASS_BY_CONTRACT"}
            for entry in delegated_smoke.values()
            if is_unknown_child_runtime(entry.get("child_runtime_model"))
        ),
        "all_subagents_wrote_role_local_artifacts": all_subagents_wrote_artifacts,
        "explicit_model_override_detected": explicit_override_detected,
        "conflicting_override_source": conflicting_override_source,
        "provider_model_not_found_error": provider_model_not_found_error,
        "silent_fallback_detected": silent_fallback_detected,
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
        f"- Runtime smoke run dir: `{payload['summary']['runtime_smoke_run_dir']}`",
        f"- Orchestrator primary smoke: `{payload['summary']['primary_agent_config_smoke']['verdict']}`",
        f"- Inheritance proof mode: `{payload['summary']['inheritance_proof_mode']}`",
        f"- Subagents inherit active runtime model: `{payload['summary']['subagents_inherit_active_runtime_model']}`",
        f"- All subagents wrote role-local artifacts: `{payload['summary']['all_subagents_wrote_role_local_artifacts']}`",
        f"- Explicit model override detected: `{payload['summary']['explicit_model_override_detected']}`",
        f"- Conflicting override source: `{payload['summary']['conflicting_override_source']}`",
        f"- ProviderModelNotFoundError: `{payload['summary']['provider_model_not_found_error']}`",
        f"- Silent fallback detected: `{payload['summary']['silent_fallback_detected']}`",
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
