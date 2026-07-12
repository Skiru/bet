"""Production audit for the active seven-agent betting control plane."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / ".kilo/agents"
POWER_AGENTS = (
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
)
PARTNERS = POWER_AGENTS[1:]
LEGACY = re.compile(
    r"bet-(?:orchestrator|engineer|scanner|scout|enricher|statistician|valuator|"
    r"challenger|test-engineer|db-analyst|reconciler|settler(?!-postevent))"
)
REQUIRED_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / ".kilo/docs/betting_agent_tool_matrix.md",
    ROOT / ".kilo/docs/betting_run_primary_executor.md",
    ROOT / ".kilo/skills/betting-pipeline-runtime/SKILL.md",
    ROOT / ".kilo/skills/context-safe-agentics/SKILL.md",
)


def load_agent(name: str) -> tuple[dict, str]:
    raw = (AGENT_DIR / f"{name}.md").read_bytes()
    header, body = raw[4:].split(b"\n---\n", 1)
    return yaml.safe_load(header), body.decode("utf-8")


def audit(runtime_smoke_payload: dict | None = None) -> dict:
    payload = runtime_smoke_payload or {}
    failures: list[str] = []
    agent_data: dict[str, tuple[dict, str]] = {}
    for name in POWER_AGENTS:
        path = AGENT_DIR / f"{name}.md"
        if not path.is_file():
            failures.append(f"missing required agent file: {path.relative_to(ROOT)}")
            continue
        data, body = load_agent(name)
        agent_data[name] = (data, body)
        if "model" in data:
            failures.append(f"{name}: explicit model override detected")
        if "steps" in data:
            failures.append(f"{name}: explicit steps override detected")
        permission = data.get("permission", {})
        if permission.get("question") != "deny":
            failures.append(f"{name}: question must be deny")
        if any(value == "ask" for value in permission.values() if isinstance(value, str)):
            failures.append(f"{name}: ask permission detected")

    active_text = "\n".join(path.read_text(encoding="utf-8") for path in REQUIRED_DOCS if path.exists())
    if LEGACY.search(active_text):
        failures.append("legacy agent reference remains in active control plane")
    if re.search(r"betclic", active_text, re.IGNORECASE):
        failures.append("stale Betclic operator flow remains")

    parent_model = payload.get("active_parent_runtime_model")
    results = payload.get("results", [])
    primary = next((item for item in results if item.get("agent_name") == "bet-executor"), {})
    delegated = {item.get("agent_name"): item for item in results if item.get("agent_name") in PARTNERS}
    if payload:
        if primary.get("smoke_type") != "PRIMARY_AGENT_CONFIG_SMOKE":
            failures.append("bet-executor: invalid smoke type, expected PRIMARY_AGENT_CONFIG_SMOKE")
        if primary.get("invalid_smoke_test_detected"):
            failures.append("bet-executor: invalid primary-as-subagent smoke detected")
        for name in PARTNERS:
            item = delegated.get(name)
            if not item:
                failures.append(f"{name}: missing delegated runtime smoke")
                continue
            if item.get("smoke_type") != "DELEGATED_SUBAGENT_LAUNCH_SMOKE":
                failures.append(f"{name}: invalid smoke type")
            if item.get("provider_model_not_found_error"):
                failures.append(f"{name}: ProviderModelNotFoundError detected")
            if item.get("explicit_model_override_detected"):
                failures.append(f"{name}: explicit conflicting override detected")
            if not item.get("artifact_written"):
                failures.append(f"{name}: missing role-local artifact")
        if payload.get("conflicting_override_source") not in (None, "NONE"):
            source = payload["conflicting_override_source"]
            if source == "UNKNOWN":
                failures.append("conflicting override requires exact source")

    unknown_children = bool(delegated) and all(
        item.get("child_runtime_model") == "UNKNOWN_NOT_INTROSPECTABLE" for item in delegated.values()
    )
    inheritance_mode = "PASS_BY_CONTRACT" if delegated and all(
        item.get("inheritance_proof_mode") == "PASS_BY_CONTRACT" for item in delegated.values()
    ) else None

    executor_permission = agent_data.get("bet-executor", ({}, ""))[0].get("permission", {})
    summary = {
        "required_agent_files_exist": len(agent_data) == len(POWER_AGENTS),
        "required_prompt_files_exist": not list((ROOT / ".kilo/prompts").glob("bet-*.md")),
        "required_docs_exist": all(path.exists() for path in REQUIRED_DOCS),
        "required_betting_agents_do_not_pin_model_overrides": all("model" not in data for data, _ in agent_data.values()),
        "ui_runtime_inheritance_policy_exists": "active Kilo UI model" in active_text,
        "safe_checkpoint_contract_exists": "safe checkpoint" in active_text.lower(),
        "bet_executor_cannot_mutate_repo": all(executor_permission.get(key) == "deny" for key in ("edit", "write", "apply_patch")),
        "code_general_repair_path_exists": "Code/General" in active_text or "Code or General" in active_text,
        "no_stale_policy_strings": LEGACY.search(active_text) is None,
        "no_stale_betclic_operator_flow": re.search(r"betclic", active_text, re.IGNORECASE) is None,
        "output_schemas_present": all("STATUS:" in body and "NEXT_ACTION:" in body for _, body in agent_data.values()),
        "continuation_protocol_present": "same worktree" in active_text and "RUN_ID" in active_text,
        "no_recursive_delegation": all(
            data.get("permission", {}).get("task") == "deny" for name, (data, _) in agent_data.items() if name != "bet-executor"
        ),
        "primary_agent_config_smoke": primary,
        "delegated_subagent_launch_smoke": delegated,
        "invalid_smoke_test_detected": bool(primary.get("invalid_smoke_test_detected")),
        "inheritance_proof_mode": inheritance_mode,
        "unknown_child_runtime_model_accepted_by_contract": unknown_children and inheritance_mode == "PASS_BY_CONTRACT" and bool(parent_model),
        "conflicting_override_source": payload.get("conflicting_override_source", "NONE"),
    }
    for key, value in summary.items():
        if key.startswith(("required_", "ui_", "safe_", "bet_executor_", "code_general_", "no_", "output_", "continuation_")) and value is False:
            failures.append(f"production summary gate failed: {key}")
    return {"status": "FAIL" if failures else "PASS", "summary": summary, "failures": failures}
