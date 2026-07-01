import json
import os
import re
from pathlib import Path


WORKSPACE_ROOT = Path("/Users/mkoziol/projects/bet")
GLOBAL_CONFIG_PATHS = [
    Path("/Users/mkoziol/.config/kilo/kilo.jsonc"),
    Path("/Users/mkoziol/.config/kilo/kilo.json"),
]
PROJECT_PROFILE_PATH = WORKSPACE_ROOT / ".kilo/profiles/kilo.local.jsonc"
AGENTS_MD_PATH = WORKSPACE_ROOT / "AGENTS.md"
AGENT_DIR = WORKSPACE_ROOT / ".kilo/agents"
ARTIFACT_DIR = WORKSPACE_ROOT / ".kilo/artifacts"
RUNS_DIR = WORKSPACE_ROOT / "reports/pipeline_runs"
ORCHESTRATOR = "bet-orchestrator"
TARGET_ALIAS = "google-vertex/gemini-3.5-flash-flex-high"
TARGET_PROVIDER = "google-vertex"
TARGET_MODEL_KEY = "gemini-3.5-flash-flex-high"
TARGET_BASE_MODEL = "gemini-3.5-flash"
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
REQUIRED_INHERITED_SUBAGENTS = [
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
SMOKE_REQUIRED = ["bet-enricher", "bet-statistician"]
FORBIDDEN_ROUTE_TOKENS = ("openai", "gpt", "claude", "qwen")


def parse_jsonc(text: str) -> dict:
    clean_text = re.sub(r"(?<!:)//.*$", "", text, flags=re.MULTILINE)
    clean_text = re.sub(r",(\s*[}\]])", r"\1", clean_text)
    return json.loads(clean_text)


def load_jsonc(path: Path) -> dict:
    return parse_jsonc(path.read_text(encoding="utf-8"))


def read_frontmatter_model(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8")
    match = re.search(r"^model:\s*(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else None


def load_global_provider_config() -> tuple[dict, str | None]:
    for path in GLOBAL_CONFIG_PATHS:
        if path.exists():
            return load_jsonc(path), str(path)
    return {}, None


def split_alias(model_value: str | None) -> tuple[str | None, str | None]:
    if not model_value or "/" not in model_value:
        return None, None
    provider_id, model_id = model_value.split("/", 1)
    return provider_id, model_id


def detect_latest_run() -> Path | None:
    env_run_id = os.environ.get("BET_AGENT_AUDIT_RUN_ID")
    if env_run_id:
        candidate = RUNS_DIR / env_run_id
        if candidate.exists():
            return candidate
    candidates = sorted(RUNS_DIR.glob("SUBAGENT_PROVIDER_MODEL_RESOLUTION_REPAIR_B_*"))
    return candidates[-1] if candidates else None


def load_smoke_results(run_dir: Path | None) -> dict:
    if run_dir is None:
        return {}
    smoke_path = run_dir / "subagent_launch_smoke_tests.json"
    if not smoke_path.exists():
        return {}
    return json.loads(smoke_path.read_text(encoding="utf-8"))


def build_matrix() -> tuple[dict, dict, list[str]]:
    failures: list[str] = []
    profile = load_jsonc(PROJECT_PROFILE_PATH)
    global_config, global_config_path = load_global_provider_config()
    agents_cfg = profile.get("agent", {})
    providers = global_config.get("provider", {})
    vertex_models = providers.get(TARGET_PROVIDER, {}).get("models", {})
    orchestrator_profile_model = agents_cfg.get(ORCHESTRATOR, {}).get("model")
    orchestrator_agent_model = read_frontmatter_model(AGENT_DIR / f"{ORCHESTRATOR}.md")
    orchestrator_resolvable = orchestrator_profile_model == TARGET_ALIAS and TARGET_MODEL_KEY in vertex_models
    smoke_run_dir = detect_latest_run()
    smoke_results = load_smoke_results(smoke_run_dir)
    smoke_map = {entry["subagent_name"]: entry for entry in smoke_results.get("results", [])}

    matrix: dict[str, dict] = {}
    for agent_name in REQUIRED_AGENTS:
        agent_path = AGENT_DIR / f"{agent_name}.md"
        frontmatter_model = read_frontmatter_model(agent_path)
        profile_model = agents_cfg.get(agent_name, {}).get("model")
        explicit_model_value = profile_model or frontmatter_model
        provider_id, model_id = split_alias(explicit_model_value)

        if agent_name == ORCHESTRATOR:
            model_source = "profile|agent_frontmatter"
            effective_model = orchestrator_profile_model or orchestrator_agent_model
            explicit_present = True
            launch_smoke_required = False
        elif explicit_model_value:
            model_source = "profile" if profile_model else "agent_frontmatter"
            effective_model = explicit_model_value
            explicit_present = True
            launch_smoke_required = True
        else:
            model_source = "inherited_parent"
            effective_model = orchestrator_profile_model
            provider_id, model_id = split_alias(effective_model)
            explicit_present = False
            launch_smoke_required = agent_name in SMOKE_REQUIRED

        provider_defined = provider_id in providers if provider_id else False
        model_defined = model_id in providers.get(provider_id, {}).get("models", {}) if provider_id else False
        resolved_config = providers.get(provider_id, {}).get("models", {}).get(model_id, {}) if provider_id else {}
        api_model_id = resolved_config.get("id")
        resolvable = bool(provider_defined and model_defined and api_model_id == TARGET_BASE_MODEL)
        smoke_entry = smoke_map.get(agent_name, {})
        smoke_pass = smoke_entry.get("verdict") == "PASS"
        forbidden_route = bool(effective_model and any(token in effective_model.lower() for token in FORBIDDEN_ROUTE_TOKENS))

        suspected_failure_reason = ""
        if forbidden_route:
            suspected_failure_reason = "forbidden_non_gemini_routing"
        elif agent_name != ORCHESTRATOR and explicit_present:
            suspected_failure_reason = "broken_explicit_subagent_model_override"
        elif not resolvable:
            suspected_failure_reason = "unresolvable_provider_or_model"
        elif launch_smoke_required and not smoke_pass:
            suspected_failure_reason = "missing_or_failed_launch_smoke"
        elif agent_name != ORCHESTRATOR:
            suspected_failure_reason = ""

        entry = {
            "agent_name": agent_name,
            "config_file": f".kilo/agents/{agent_name}.md",
            "explicit_model_field_present": explicit_present,
            "explicit_model_value": explicit_model_value,
            "provider_id": provider_id,
            "model_id": model_id,
            "model_source": model_source,
            "provider_defined": provider_defined,
            "model_id_defined_under_provider": model_defined,
            "catalog_or_config_resolvable": resolvable,
            "launch_smoke_required": launch_smoke_required,
            "smoke_verdict": smoke_entry.get("verdict"),
            "smoke_artifact_path": smoke_entry.get("artifact_path"),
            "suspected_failure_reason": suspected_failure_reason,
        }
        matrix[agent_name] = entry

        if forbidden_route:
            failures.append(f"{agent_name}: forbidden routing detected: {effective_model}")
        if agent_name == ORCHESTRATOR and not resolvable:
            failures.append(f"{agent_name}: orchestrator model is not resolvable to {TARGET_ALIAS}")
        if agent_name in REQUIRED_INHERITED_SUBAGENTS and explicit_present:
            failures.append(f"{agent_name}: explicit model override remains present")
        if agent_name in REQUIRED_INHERITED_SUBAGENTS and not resolvable:
            failures.append(f"{agent_name}: inherited/explicit model is not resolvable")
        if agent_name in SMOKE_REQUIRED and not smoke_pass:
            failures.append(f"{agent_name}: required launch smoke did not PASS")

    summary = {
        "global_config_path": global_config_path,
        "project_profile_path": str(PROJECT_PROFILE_PATH),
        "agents_md_path": str(AGENTS_MD_PATH),
        "env_override_present": bool(os.environ.get("KILO_CONFIG_CONTENT")),
        "orchestrator_model_resolvable": orchestrator_resolvable,
        "subagents_inherit_parent_model": all(not matrix[name]["explicit_model_field_present"] for name in REQUIRED_INHERITED_SUBAGENTS),
        "explicit_subagent_model_overrides_removed": all(not matrix[name]["explicit_model_field_present"] for name in REQUIRED_INHERITED_SUBAGENTS),
        "forbidden_model_routing_detected": any(any(token in (matrix[name]["explicit_model_value"] or "").lower() for token in FORBIDDEN_ROUTE_TOKENS) for name in matrix),
        "smoke_run_dir": str(smoke_run_dir) if smoke_run_dir else None,
        "required_smoke_agents": SMOKE_REQUIRED,
        "verdict": "FAIL" if failures else "PASS",
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
        f"- Orchestrator resolvable: {summary['orchestrator_model_resolvable']}",
        f"- Subagents inherit parent model: {summary['subagents_inherit_parent_model']}",
        f"- Explicit subagent overrides removed: {summary['explicit_subagent_model_overrides_removed']}",
        f"- Forbidden model routing detected: {summary['forbidden_model_routing_detected']}",
        f"- Smoke run dir: {summary['smoke_run_dir']}",
        "",
        "## Failures",
    ]
    if failures:
        lines.extend(f"- {failure}" for failure in failures)
    else:
        lines.append("- None")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    matrix, summary, failures = build_matrix()
    write_outputs(matrix, summary, failures)
    print(f"Bet agent roster audit: {summary['verdict']}")
    if failures:
        for failure in failures:
            print(f"- {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
