import os
import re
import json
import glob
import sys

def parse_jsonc(text):
    # Remove single line comments (but do not strip comments in http:// or https://)
    clean_text = re.sub(r'(?<!:)//.*$', '', text, flags=re.MULTILINE)
    # Remove trailing commas before closing braces/brackets
    clean_text = re.sub(r',(\s*[}\]])', r'\1', clean_text)
    return json.loads(clean_text)

def run_check():
    workspace_root = "/Users/mkoziol/projects/bet"
    
    report = {
        "agents_scanned": [],
        "missing_gemini_model_policy": [],
        "active_gpt_openai_routing": [],
        "gemini_alias_status": "UNKNOWN",
        "betting_boundaries_status": "UNKNOWN",
        "failures": []
    }
    
    # 1. Check Agents Frontmatter & Model Policy
    agents_dir = os.path.join(workspace_root, ".kilo/agents")
    agent_files = glob.glob(os.path.join(agents_dir, "*.md"))
    
    for filepath in agent_files:
        filename = os.path.basename(filepath)
        report["agents_scanned"].append(filename)
        
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Check active model field
        frontmatter_match = re.search(r'^model:\s*(.*)$', content, re.MULTILINE)
        if frontmatter_match:
            model_val = frontmatter_match.group(1).strip()
            if "gemini-3.5-flash-flex-high" not in model_val:
                report["failures"].append(f"Agent {filename} uses non-Gemini model: {model_val}")
            if "gpt" in model_val.lower() or "openai" in model_val.lower() or "qwen" in model_val.lower():
                report["active_gpt_openai_routing"].append(f"{filename}: {model_val}")
                report["failures"].append(f"Agent {filename} actively routes to GPT/OpenAI/Qwen: {model_val}")
        else:
            report["failures"].append(f"Agent {filename} is missing 'model:' field in frontmatter")
            
        # Check for Model Policy section
        if "## Model Policy" not in content:
            report["missing_gemini_model_policy"].append(filename)
            report["failures"].append(f"Agent {filename} is missing '## Model Policy' section")
            
    # 2. Check kilo.local.jsonc for GPT or Qwen active agent models
    profile_path = os.path.join(workspace_root, ".kilo/profiles/kilo.local.jsonc")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            try:
                profile_data = parse_jsonc(f.read())
                agents = profile_data.get("agent", {})
                for name, config in agents.items():
                    if name.startswith("bet-") or name == "browser-smoke" or name == "code-gpt54":
                        model = config.get("model", "")
                        if "gemini-3.5-flash-flex-high" not in model:
                            report["failures"].append(f"Profile agent {name} uses non-Gemini model: {model}")
                        if "gpt" in model.lower() or "openai" in model.lower():
                            report["active_gpt_openai_routing"].append(f"profile:{name}: {model}")
                            report["failures"].append(f"Profile agent {name} routes to GPT/OpenAI: {model}")
            except Exception as e:
                report["failures"].append(f"Failed to parse kilo.local.jsonc: {str(e)}")
                
    # 3. Check global kilo.json / kilo.jsonc
    global_config_path = "/Users/mkoziol/.config/kilo/kilo.json"
    if os.path.exists(global_config_path):
        with open(global_config_path, "r", encoding="utf-8") as f:
            try:
                g_data = json.load(f)
                vertex_models = g_data.get("provider", {}).get("google-vertex", {}).get("models", {})
                if "gemini-3.5-flash-flex-high" in vertex_models:
                    report["gemini_alias_status"] = "VERIFIED_PRESENT"
                else:
                    report["failures"].append("gemini-3.5-flash-flex-high alias is missing from global kilo.json provider models")
            except Exception as e:
                report["failures"].append(f"Failed to parse global kilo.json: {str(e)}")
                
    # 4. Check betting boundaries in AGENTS.md
    agents_md_path = os.path.join(workspace_root, "AGENTS.md")
    if os.path.exists(agents_md_path):
        with open(agents_md_path, "r", encoding="utf-8") as f:
            content = f.read()
        lower_content = content.lower()
        
        # Check for boundary keywords
        has_betclic = "betclic" in lower_content
        has_browser_auto = "browser automation" in lower_content or "playwright" in lower_content
        has_never_invent = "never invent odds" in lower_content or "anti-hallucination" in lower_content
        
        if has_betclic and has_browser_auto and has_never_invent:
            report["betting_boundaries_status"] = "VERIFIED_ENFORCED"
        else:
            report["failures"].append("Betting safety boundaries are missing from AGENTS.md")
            report["betting_boundaries_status"] = "FAILED"
            
    # Write report
    report_dir = os.path.dirname(os.path.join(workspace_root, ".kilo/artifacts/kilo_agent_model_contract_report.json"))
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(workspace_root, ".kilo/artifacts/kilo_agent_model_contract_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print(f"Contract check finished. Status: {'FAIL' if report['failures'] else 'PASS'}")
    if report["failures"]:
        print("Failures:")
        for fail in report["failures"]:
            print(f"- {fail}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(run_check())
