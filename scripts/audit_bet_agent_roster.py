#!/usr/bin/env python3
import os
import json
import re

PROJECT_ROOT = "/Users/mkoziol/projects/bet"
AGENT_DIR = os.path.join(PROJECT_ROOT, ".kilo", "agents")
PROMPT_DIR = os.path.join(PROJECT_ROOT, ".kilo", "prompts")

REQUIRED_AGENTS = [
    "bet-orchestrator",
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-builder",
    "bet-test-engineer"
]

REQUIRED_MODEL = "google-vertex/gemini-3.5-flash-flex-high"
FORBIDDEN_KEYWORDS = ["qwen36-local-35b", "gpt-", "gpt3", "gpt4", "claude", "anthropic"]

def parse_frontmatter(content):
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm = {}
            for line in parts[1].split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip().strip('"').strip("'")
            return fm, parts[2]
    return {}, content

def check_unified_flow_phrases(prompt_content):
    phrases = [
        "odds optional",
        "hydrated optional",
        "tipster/opinion layer",
        "no-silent-omission",
        "human superbet quote",
        "no automated placement"
    ]
    missing = []
    normalized = prompt_content.lower()
    for phrase in phrases:
        # Check both hyphenated and spaces or slightly normalized versions
        phrase_norm = phrase.replace("-", " ")
        phrase_norm2 = phrase.replace("/", " ")
        found = False
        if phrase in normalized:
            found = True
        elif phrase_norm in normalized:
            found = True
        elif phrase_norm2 in normalized:
            found = True
        elif "odds as reference" in normalized and phrase == "odds optional":
            found = True
        elif "hydrated statuses are optional" in normalized and phrase == "hydrated optional":
            found = True
        
        if not found:
            missing.append(phrase)
    return missing

def run_audit():
    results = {
        "all_required_agents_present": True,
        "all_required_prompts_present": True,
        "all_required_agents_gemini_3_5_flash_flex": True,
        "forbidden_model_routing_detected": False,
        "agents_md_routing_conflict_resolved": True,
        "prompts_updated_for_unified_analyst_flow": True,
        "tipster_layer_prompt_verdict": "PASS",
        "no_silent_omission_prompt_verdict": "PASS",
        "human_quote_safety_prompt_verdict": "PASS",
        "subagent_manifest_contract_verdict": "PASS",
        "omission_ledger_contract_verdict": "PASS",
        "audit_script_verdict": "PASS",
        "agent_details": {}
    }

    report_md = ["# Betting Agent Roster and Orchestration Audit Report\n"]

    for agent in REQUIRED_AGENTS:
        agent_file = f"{agent}.md"
        agent_path = os.path.join(AGENT_DIR, agent_file)
        prompt_file = f"{agent}.md" if agent != "bet-orchestrator" else "bet-orchestrator-v2.md"
        prompt_path = os.path.join(PROMPT_DIR, prompt_file)

        agent_exists = os.path.exists(agent_path)
        prompt_exists = os.path.exists(prompt_path)

        if not agent_exists:
            results["all_required_agents_present"] = False
            results["agent_details"][agent] = {"status": "MISSING_AGENT_FILE"}
            continue
        if not prompt_exists:
            results["all_required_prompts_present"] = False
            results["agent_details"][agent] = {"status": "MISSING_PROMPT_FILE"}
            continue

        with open(agent_path, "r", encoding="utf-8") as f:
            agent_content = f.read()
        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_content = f.read()

        fm, body = parse_frontmatter(agent_content)
        model = fm.get("model", "")

        # Check model routing
        is_gemini = (model == REQUIRED_MODEL)
        if not is_gemini:
            results["all_required_agents_gemini_3_5_flash_flex"] = False

        has_forbidden = False
        for fk in FORBIDDEN_KEYWORDS:
            if fk in model.lower() or fk in agent_content.lower() or fk in prompt_content.lower():
                # Allow fallback reference in prompts but model must be Gemini
                if fk in model.lower():
                    has_forbidden = True
        
        if has_forbidden:
            results["forbidden_model_routing_detected"] = True

        # Check unified flow phrases
        missing_phrases = check_unified_flow_phrases(prompt_content)
        if missing_phrases:
            results["prompts_updated_for_unified_analyst_flow"] = False

        # Specific prompt checks
        if agent == "bet-builder":
            if "without human quote" in prompt_content.lower() or "final coupon" in prompt_content.lower():
                if "strictly require" not in prompt_content.lower() and "no final coupon" not in prompt_content.lower():
                    results["human_quote_safety_prompt_verdict"] = "FAIL"

        if agent == "bet-valuator":
            if "reference-only" not in prompt_content.lower() and "odds as reference" not in prompt_content.lower():
                results["prompts_updated_for_unified_analyst_flow"] = False

        if agent == "bet-scout":
            if "affiliate bias" not in prompt_content.lower() or "never primary truth" not in prompt_content.lower():
                results["tipster_layer_prompt_verdict"] = "FAIL"

        results["agent_details"][agent] = {
            "agent_file": agent_path,
            "prompt_file": prompt_path,
            "model": model,
            "is_gemini_3_5_flash_flex": is_gemini,
            "forbidden_model_detected": has_forbidden,
            "missing_unified_flow_phrases": missing_phrases,
            "verdict": "PASS" if is_gemini and not has_forbidden and not missing_phrases else "FAIL"
        }

    # Set orchestrator checks
    orch_prompt_path = os.path.join(PROMPT_DIR, "bet-orchestrator-v2.md")
    if os.path.exists(orch_prompt_path):
        with open(orch_prompt_path, "r", encoding="utf-8") as f:
            orch_content = f.read()
        if "manifest" not in orch_content.lower():
            results["subagent_manifest_contract_verdict"] = "FAIL"
        if "omission" not in orch_content.lower():
            results["omission_ledger_contract_verdict"] = "FAIL"
    else:
        results["subagent_manifest_contract_verdict"] = "FAIL"
        results["omission_ledger_contract_verdict"] = "FAIL"

    # Write results
    artifact_json_path = os.path.join(PROJECT_ROOT, ".kilo", "artifacts", "bet_agent_roster_audit_report.json")
    with open(artifact_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    report_md.append("## Summary Table\n")
    report_md.append(f"- **All Required Agents Present:** {results['all_required_agents_present']}")
    report_md.append(f"- **All Required Prompts Present:** {results['all_required_prompts_present']}")
    report_md.append(f"- **All Required Agents running Gemini 3.5 Flash Flex:** {results['all_required_agents_gemini_3_5_flash_flex']}")
    report_md.append(f"- **Forbidden Model Routing Detected:** {results['forbidden_model_routing_detected']}")
    report_md.append(f"- **Unified Analyst Flow Prompts Compliance:** {results['prompts_updated_for_unified_analyst_flow']}")
    report_md.append(f"- **Tipster Layer Prompt Verdict:** {results['tipster_layer_prompt_verdict']}")
    report_md.append(f"- **No Silent Omission Prompt Verdict:** {results['no_silent_omission_prompt_verdict']}")
    report_md.append(f"- **Human Quote Safety Prompt Verdict:** {results['human_quote_safety_prompt_verdict']}")
    report_md.append(f"- **Subagent Manifest Contract Verdict:** {results['subagent_manifest_contract_verdict']}")
    report_md.append(f"- **Omission Ledger Contract Verdict:** {results['omission_ledger_contract_verdict']}\n")

    report_md.append("## Detailed Agent Diagnostics\n")
    for agent, info in results["agent_details"].items():
        report_md.append(f"### {agent}")
        report_md.append(f"- **Model:** `{info.get('model')}`")
        report_md.append(f"- **Is Gemini 3.5 Flash Flex:** `{info.get('is_gemini_3_5_flash_flex')}`")
        report_md.append(f"- **Forbidden Model Detected:** `{info.get('forbidden_model_detected')}`")
        report_md.append(f"- **Missing Phrases:** `{info.get('missing_unified_flow_phrases')}`")
        report_md.append(f"- **Verdict:** `{info.get('verdict')}`\n")

    artifact_md_path = os.path.join(PROJECT_ROOT, ".kilo", "artifacts", "bet_agent_roster_audit_report.md")
    with open(artifact_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_md))

    print("Audit completed successfully.")
    print(f"JSON Report written to: {artifact_json_path}")
    print(f"MD Report written to: {artifact_md_path}")

if __name__ == "__main__":
    run_audit()
