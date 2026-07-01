import os
import json
import pytest

PROJECT_ROOT = "/Users/mkoziol/projects/bet"
AUDIT_REPORT_PATH = os.path.join(PROJECT_ROOT, ".kilo", "artifacts", "bet_agent_roster_audit_report.json")

def test_audit_report_conformance():
    # Make sure the audit script was run and produced a report
    assert os.path.exists(AUDIT_REPORT_PATH), "Audit report JSON does not exist. Run the audit script first!"

    with open(AUDIT_REPORT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check all key criteria
    assert data["all_required_agents_present"] is True, "Not all required agents are present."
    assert data["all_required_prompts_present"] is True, "Not all required prompts are present."
    assert data["all_required_agents_gemini_3_5_flash_flex"] is True, "Some required agents are not routed to Gemini 3.5 Flash Flex."
    assert data["forbidden_model_routing_detected"] is False, "Forbidden model routing (Qwen, OpenAI, Claude) was detected."
    assert data["agents_md_routing_conflict_resolved"] is True, "Model routing conflicts exist between md and profiles."
    assert data["prompts_updated_for_unified_analyst_flow"] is True, "Some prompts are missing mandatory unified analyst flow phrases."
    assert data["tipster_layer_prompt_verdict"] == "PASS", "Tipster layer validation failed on bet-scout."
    assert data["no_silent_omission_prompt_verdict"] == "PASS", "No-silent-omission validation failed."
    assert data["human_quote_safety_prompt_verdict"] == "PASS", "Human quote safety verification failed."
    assert data["subagent_manifest_contract_verdict"] == "PASS", "Subagent manifest contract validation failed."
    assert data["omission_ledger_contract_verdict"] == "PASS", "Omission ledger contract validation failed."
    assert data["audit_script_verdict"] == "PASS", "The overall audit script verdict did not pass."

    # Validate individual agent verdicts
    for agent, details in data["agent_details"].items():
        assert details["verdict"] == "PASS", f"Agent {agent} failed compliance checks. Details: {details}"
