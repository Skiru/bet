import json
import os
import re
from pathlib import Path


WORKSPACE_ROOT = Path(
    os.environ.get("BET_WORKSPACE_ROOT", Path(__file__).resolve().parents[1])
).resolve()
GLOBAL_CONFIG_PATHS = [
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kilo/kilo.jsonc",
    Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kilo/kilo.json",
]
PROJECT_PROFILE_PATH = WORKSPACE_ROOT / ".kilo/profiles/kilo.local.jsonc"
AGENTS_MD_PATH = WORKSPACE_ROOT / "AGENTS.md"
AGENT_DIR = WORKSPACE_ROOT / ".kilo/agents"
PROMPT_DIR = AGENT_DIR
ARTIFACT_DIR = WORKSPACE_ROOT / ".kilo/artifacts"
RUNS_DIR = WORKSPACE_ROOT / "reports/pipeline_runs"
ORCHESTRATOR = "bet-executor"
REPAIR_RUN_PREFIX = "UI_SELECTED_RUNTIME_MODEL_INHERITANCE_REPAIR_D_"
REQUIRED_AGENTS = [
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
]
REQUIRED_INHERITED_SUBAGENTS = [
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
]
REQUIRED_PROMPTS = {
    "bet-executor": "bet-executor.md",
    "bet-researcher": "bet-researcher.md",
    "bet-modeler": "bet-modeler.md",
    "bet-risk-gatekeeper": "bet-risk-gatekeeper.md",
    "bet-builder": "bet-builder.md",
    "bet-auditor": "bet-auditor.md",
    "bet-settler-postevent": "bet-settler-postevent.md",
}
SMOKE_REQUIRED = list(REQUIRED_INHERITED_SUBAGENTS)
UNKNOWN_RUNTIME_VALUES = {None, "", "unknown", "UNKNOWN", "UNVERIFIED", "UNVERIFIED_BLOCKED_BY_PARENT_RUNTIME"}
HARD_CODED_GEMINI_GATE_PATTERNS = (
    "ACTIVE_PROVIDER=google-vertex",
    "ACTIVE_RUNTIME_IS_GOOGLE_VERTEX_GEMINI",
    "ALL_REQUIRED_SUBAGENTS_GEMINI_3_5_FLASH_FLEX",
    "BLOCKED_WRONG_ACTIVE_RUNTIME_MODEL",
    "must resolve to `google-vertex/gemini-3.5-flash-flex-high`",
    "inherit that verified Gemini 3.5 Flash Flex model",
    "Do not route this agent to GPT/OpenAI models.",
    "Do not use GPT/OpenAI fallback.",
    '"model": "google-vertex/gemini-3.5-flash-flex-high"',
    "model: google-vertex/gemini-3.5-flash-flex-high",
)
POLICY_SCAN_PATHS = [
    AGENTS_MD_PATH,
    WORKSPACE_ROOT / "docs/pipeline/Unified Orchestrated Analyst Session Contract.md",
    WORKSPACE_ROOT / "docs/pipeline/Orchestrated Session Continuation Protocol.md",
    WORKSPACE_ROOT / ".kilo/agents/bet-executor.md",
    WORKSPACE_ROOT / ".kilo/agents/bet-auditor.md",
]


def parse_jsonc(text: str) -> dict:
    clean_text = re.sub(r"(?<!:)//.*$", "", text, flags=re.MULTILINE)
    clean_text = re.sub(r",(\s*[}\]])", r"\1", clean_text)
    return json.loads(clean_text)


def load_jsonc(path: Path) -> dict:
    return parse_jsonc(path.read_text(encoding="utf-8"))


def read_frontmatter_model(path: Path) -> str | None:
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^model:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def load_global_provider_config() -> tuple[dict, str | None]:
    for path in GLOBAL_CONFIG_PATHS:
        if path.exists():
            return load_jsonc(path), str(path)
    return {}, None


def detect_latest_run() -> Path | None:
    env_run_id = os.environ.get("BET_AGENT_AUDIT_RUN_ID")
    if env_run_id:
        candidate = RUNS_DIR / env_run_id
        if candidate.exists():
            return candidate
    candidates = sorted(RUNS_DIR.glob(f"{REPAIR_RUN_PREFIX}*"))
    return candidates[-1] if candidates else None


def load_smoke_results(run_dir: Path | None) -> dict:
    if run_dir is None:
        return {}
    for name in (
        "runtime_inheritance_smoke.json",
        "subagent_launch_smoke_tests.json",
        "subagent_launch_smoke_after_refresh.json",
        "strict_gemini_subagent_launch_smoke.json",
    ):
        candidate = run_dir / name
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return {}


def is_unknown_runtime(value: str | None) -> bool:
    return value in UNKNOWN_RUNTIME_VALUES


def normalize_smoke_results(smoke_payload: dict) -> dict:
    results = smoke_payload.get("results") or smoke_payload.get("subagents") or []
    active_runtime_model = (
        smoke_payload.get("active_runtime_model")
        or smoke_payload.get("active_ui_model")
        or smoke_payload.get("active_model_visible_to_this_session")
    )
    provider_model_not_found_error = bool(smoke_payload.get("provider_model_not_found_error"))
    silent_fallback_detected = bool(smoke_payload.get("silent_fallback_detected"))
    smoke_map: dict[str, dict] = {}

    for result in results:
        name = result.get("subagent_name") or result.get("name")
        if not name:
            continue
        result_provider_model_not_found = bool(result.get("provider_model_not_found_error"))
        result_silent_fallback = bool(
            result.get("silent_fallback_detected")
            or result.get("fallback_to_openai_detected")
            or result.get("fallback_to_claude_detected")
            or result.get("fallback_to_qwen_detected")
        )
        provider_model_not_found_error = provider_model_not_found_error or result_provider_model_not_found
        silent_fallback_detected = silent_fallback_detected or result_silent_fallback
        smoke_map[name] = {
            "subagent_name": name,
            "verdict": result.get("verdict"),
            "launched": bool(result.get("launched") or result.get("task_id") or result.get("verdict") == "PASS"),
            "artifact_path": result.get("artifact_path") or result.get("artifact"),
            "active_runtime_model": result.get("active_runtime_model") or active_runtime_model,
            "inherited_parent_model": result.get("inherited_parent_model"),
            "explicit_override_used": bool(result.get("explicit_override_used")),
            "explicit_override_approved": bool(result.get("explicit_override_approved")),
            "conflicting_explicit_override": bool(
                result.get("conflicting_explicit_override") or result.get("explicit_override_conflicts_parent")
            ),
            "provider_model_not_found_error": result_provider_model_not_found,
            "silent_fallback_detected": result_silent_fallback,
        }

    return {
        "active_runtime_model": active_runtime_model,
        "active_runtime_unknown": is_unknown_runtime(active_runtime_model),
        "provider_model_not_found_error": provider_model_not_found_error,
        "silent_fallback_detected": silent_fallback_detected,
        "smoke_map": smoke_map,
    }


def scan_for_hardcoded_gemini_gates() -> list[str]:
    hits: list[str] = []
    profile = load_jsonc(PROJECT_PROFILE_PATH) if PROJECT_PROFILE_PATH.is_file() else {}
    if "model" in profile:
        hits.append(".kilo/profiles/kilo.local.jsonc: top-level model pin remains present")
    for agent_name in REQUIRED_AGENTS:
        if "model" in profile.get("agent", {}).get(agent_name, {}):
            hits.append(f".kilo/profiles/kilo.local.jsonc: {agent_name} model pin remains present")
    for path in POLICY_SCAN_PATHS:
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for pattern in HARD_CODED_GEMINI_GATE_PATTERNS:
            if pattern in content:
                hits.append(f"{path.relative_to(WORKSPACE_ROOT)}: {pattern}")
    return hits


def build_matrix(smoke_payload: dict | None = None, run_dir: Path | None = None) -> tuple[dict, dict, list[str]]:
    failures: list[str] = []
    profile = load_jsonc(PROJECT_PROFILE_PATH) if PROJECT_PROFILE_PATH.is_file() else {}
    agents_cfg = profile.get("agent", {})
    if smoke_payload is None:
        run_dir = run_dir or detect_latest_run()
        smoke_payload = load_smoke_results(run_dir)
    normalized_smoke = normalize_smoke_results(smoke_payload)
    smoke_map = normalized_smoke["smoke_map"]
    hardcoded_gate_hits = scan_for_hardcoded_gemini_gates()

    matrix: dict[str, dict] = {}
    for agent_name in REQUIRED_AGENTS:
        agent_path = AGENT_DIR / f"{agent_name}.md"
        prompt_path = PROMPT_DIR / REQUIRED_PROMPTS[agent_name]
        frontmatter_model = read_frontmatter_model(agent_path)
        profile_model = agents_cfg.get(agent_name, {}).get("model")
        explicit_model_value = profile_model or frontmatter_model
        explicit_present = bool(explicit_model_value)
        smoke_entry = smoke_map.get(agent_name, {})
        smoke_required = agent_name in SMOKE_REQUIRED

        suspected_failure_reason = ""
        if not agent_path.exists():
            suspected_failure_reason = "missing_agent_file"
        elif not prompt_path.exists():
            suspected_failure_reason = "missing_prompt_file"
        elif explicit_present:
            suspected_failure_reason = "explicit_model_override_present"
        elif smoke_required and normalized_smoke["active_runtime_unknown"]:
            suspected_failure_reason = "unknown_active_runtime_model"
        elif smoke_required and normalized_smoke["provider_model_not_found_error"]:
            suspected_failure_reason = "provider_model_not_found_error"
        elif smoke_required and normalized_smoke["silent_fallback_detected"]:
            suspected_failure_reason = "silent_fallback_detected"
        elif smoke_required and smoke_entry.get("verdict") != "PASS":
            suspected_failure_reason = "missing_or_failed_launch_smoke"
        elif smoke_required and smoke_entry.get("conflicting_explicit_override"):
            suspected_failure_reason = "conflicting_explicit_override"
        elif smoke_required and smoke_entry.get("explicit_override_used") and not smoke_entry.get("explicit_override_approved"):
            suspected_failure_reason = "unapproved_explicit_override"
        elif smoke_required and smoke_entry.get("inherited_parent_model") is False:
            suspected_failure_reason = "subagent_did_not_inherit_parent_model"

        matrix[agent_name] = {
            "agent_name": agent_name,
            "config_file": f".kilo/agents/{agent_name}.md",
            "prompt_file": f".kilo/prompts/{REQUIRED_PROMPTS[agent_name]}",
            "agent_file_exists": agent_path.exists(),
            "prompt_file_exists": prompt_path.exists(),
            "frontmatter_model": frontmatter_model,
            "profile_model": profile_model,
            "explicit_model_field_present": explicit_present,
            "explicit_model_value": explicit_model_value,
            "model_source": "explicit_override" if explicit_present else "inherit_parent",
            "launch_smoke_required": smoke_required,
            "smoke_verdict": smoke_entry.get("verdict"),
            "smoke_artifact_path": smoke_entry.get("artifact_path"),
            "smoke_launched": smoke_entry.get("launched"),
            "active_runtime_model": smoke_entry.get("active_runtime_model") or normalized_smoke["active_runtime_model"],
            "inherited_parent_model": smoke_entry.get("inherited_parent_model"),
            "explicit_override_used": smoke_entry.get("explicit_override_used"),
            "explicit_override_approved": smoke_entry.get("explicit_override_approved"),
            "conflicting_explicit_override": smoke_entry.get("conflicting_explicit_override"),
            "provider_model_not_found_error": smoke_entry.get("provider_model_not_found_error", False),
            "silent_fallback_detected": smoke_entry.get("silent_fallback_detected", False),
            "suspected_failure_reason": suspected_failure_reason,
        }

        if not agent_path.exists():
            failures.append(f"{agent_name}: missing agent file")
        if not prompt_path.exists():
            failures.append(f"{agent_name}: missing prompt file")
        if explicit_present:
            failures.append(f"{agent_name}: explicit model override remains present")
        if smoke_required and normalized_smoke["active_runtime_unknown"]:
            failures.append(f"{agent_name}: active runtime model is unknown")
        if smoke_required and normalized_smoke["provider_model_not_found_error"]:
            failures.append(f"{agent_name}: ProviderModelNotFoundError detected")
        if smoke_required and normalized_smoke["silent_fallback_detected"]:
            failures.append(f"{agent_name}: silent fallback detected")
        if smoke_required and smoke_entry.get("verdict") != "PASS":
            failures.append(f"{agent_name}: required launch smoke did not PASS")
        if smoke_required and smoke_entry.get("conflicting_explicit_override"):
            failures.append(f"{agent_name}: conflicting explicit override detected")
        if smoke_required and smoke_entry.get("explicit_override_used") and not smoke_entry.get("explicit_override_approved"):
            failures.append(f"{agent_name}: explicit override used without user approval")
        if smoke_required and smoke_entry.get("inherited_parent_model") is False:
            failures.append(f"{agent_name}: subagent did not inherit active parent runtime model")

    summary = {
        "project_profile_path": str(PROJECT_PROFILE_PATH),
        "agents_md_path": str(AGENTS_MD_PATH),
        "env_override_present": bool(os.environ.get("KILO_CONFIG_CONTENT")),
        "smoke_run_dir": str(run_dir) if run_dir else None,
        "required_smoke_agents": SMOKE_REQUIRED,
        "active_runtime_model": normalized_smoke["active_runtime_model"],
        "active_runtime_unknown": normalized_smoke["active_runtime_unknown"],
        "provider_model_not_found_error": normalized_smoke["provider_model_not_found_error"],
        "silent_fallback_detected": normalized_smoke["silent_fallback_detected"],
        "required_agent_files_exist": all(matrix[name]["agent_file_exists"] for name in REQUIRED_AGENTS),
        "required_prompt_files_exist": all(matrix[name]["prompt_file_exists"] for name in REQUIRED_AGENTS),
        "required_agents_model_overrides_removed": all(not matrix[name]["explicit_model_field_present"] for name in REQUIRED_AGENTS),
        "subagents_inherit_active_runtime_model": all(
            matrix[name]["inherited_parent_model"] is True for name in SMOKE_REQUIRED
        ),
        "forbidden_model_override_detected": any(matrix[name]["explicit_model_field_present"] for name in REQUIRED_AGENTS),
        "hard_coded_gemini_gate_removed": not hardcoded_gate_hits,
        "hard_coded_gemini_gate_hits": hardcoded_gate_hits,
        "verdict": "FAIL" if failures or hardcoded_gate_hits else "PASS",
    }
    return matrix, summary, failures


def write_outputs(matrix: dict, summary: dict, failures: list[str]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    matrix_path = ARTIFACT_DIR / "agent_model_routing_matrix.json"
    report_path = ARTIFACT_DIR / "bet_agent_roster_audit_report.json"
    md_path = ARTIFACT_DIR / "bet_agent_roster_audit_report.md"

    matrix_payload = {"matrix": matrix, "summary": summary}
    report_payload = {
        "status": summary["verdict"],
        "summary": summary,
        "failures": failures,
    }
    matrix_path.write_text(json.dumps(matrix_payload, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report_payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Bet Agent Roster Audit",
        "",
        f"- Verdict: {summary['verdict']}",
        f"- Active runtime model: {summary['active_runtime_model']}",
        f"- Active runtime unknown: {summary['active_runtime_unknown']}",
        f"- ProviderModelNotFoundError: {summary['provider_model_not_found_error']}",
        f"- Silent fallback detected: {summary['silent_fallback_detected']}",
        f"- Required agent files exist: {summary['required_agent_files_exist']}",
        f"- Required prompt files exist: {summary['required_prompt_files_exist']}",
        f"- Required agents model overrides removed: {summary['required_agents_model_overrides_removed']}",
        f"- Subagents inherit active runtime model: {summary['subagents_inherit_active_runtime_model']}",
        f"- Hard-coded Gemini gate removed: {summary['hard_coded_gemini_gate_removed']}",
        f"- Smoke run dir: {summary['smoke_run_dir']}",
        "",
        "## Failures",
    ]
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- None")
    lines.extend(["", "## Hard-coded Gemini Gate Hits"])
    if summary["hard_coded_gemini_gate_hits"]:
        lines.extend(f"- {hit}" for hit in summary["hard_coded_gemini_gate_hits"])
    else:
        lines.append("- None")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    run_dir = detect_latest_run()
    matrix, summary, failures = build_matrix(run_dir=run_dir)
    write_outputs(matrix, summary, failures)
    print(f"Bet agent roster audit: {summary['verdict']}")
    if failures:
        for failure in failures:
            print(f"- {failure}")
    if summary["hard_coded_gemini_gate_hits"]:
        for hit in summary["hard_coded_gemini_gate_hits"]:
            print(f"- hard-coded gate: {hit}")
    return 1 if summary["verdict"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
