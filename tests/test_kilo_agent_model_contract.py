import os
import re
import json
import glob
import pytest

def parse_jsonc(text):
    # Remove single line comments
    clean_text = re.sub(r'(?<!:)//.*$', '', text, flags=re.MULTILINE)
    # Remove trailing commas before closing braces/brackets
    clean_text = re.sub(r',(\s*[}\]])', r'\1', clean_text)
    return json.loads(clean_text)

@pytest.fixture
def workspace_root():
    return "/Users/mkoziol/projects/bet"

def test_agents_reference_gemini(workspace_root):
    agents_dir = os.path.join(workspace_root, ".kilo/agents")
    files = glob.glob(os.path.join(agents_dir, "*.md"))
    assert len(files) > 0, "No agent files found"
    
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Every agent file must reference the gemini-3.5-flash-flex-high model alias
        assert "gemini-3.5-flash-flex-high" in content, f"Agent {os.path.basename(filepath)} does not reference gemini-3.5-flash-flex-high"

def test_agents_no_active_gpt_openai(workspace_root):
    agents_dir = os.path.join(workspace_root, ".kilo/agents")
    files = glob.glob(os.path.join(agents_dir, "*.md"))
    
    # We allow historical compatibility explanations or mentions of GPT/OpenAI
    # only if clearly documented as forbidden/historical.
    # Active routing fails (e.g. model: openai-codex, model: gpt-x, model: openai-compatible/qwen...)
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check frontmatter model: line
        frontmatter_match = re.search(r'^model:\s*(.*)$', content, re.MULTILINE)
        if frontmatter_match:
            model_val = frontmatter_match.group(1).strip()
            # Must not be GPT/OpenAI or Rapid-MLX
            assert "gpt" not in model_val.lower(), f"Active model routing in {os.path.basename(filepath)} has GPT: {model_val}"
            assert "openai" not in model_val.lower(), f"Active model routing in {os.path.basename(filepath)} has OpenAI: {model_val}"
            assert "qwen" not in model_val.lower(), f"Active model routing in {os.path.basename(filepath)} has Qwen: {model_val}"

def test_prompts_no_active_gpt_openai_routing(workspace_root):
    prompts_dir = os.path.join(workspace_root, ".kilo/prompts")
    files = glob.glob(os.path.join(prompts_dir, "*.md"))
    
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if there is active routing like "model: gpt" or similar
        frontmatter_match = re.search(r'^model:\s*(.*)$', content, re.MULTILINE)
        if frontmatter_match:
            model_val = frontmatter_match.group(1).strip()
            assert "gpt" not in model_val.lower(), f"Active model routing in prompt {os.path.basename(filepath)} has GPT: {model_val}"
            assert "openai" not in model_val.lower(), f"Active model routing in prompt {os.path.basename(filepath)} has OpenAI: {model_val}"

def test_profile_contains_gemini_alias(workspace_root):
    profile_path = os.path.join(workspace_root, ".kilo/profiles/kilo.local.jsonc")
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = parse_jsonc(f.read())
        
        # Let's verify agent model definitions
        agents = profile_data.get("agent", {})
        for name, config in agents.items():
            if name.startswith("bet-") or name == "browser-smoke" or name == "code-gpt54":
                model = config.get("model", "")
                assert "gemini-3.5-flash-flex-high" in model, f"Profile agent {name} does not route to gemini-3.5-flash-flex-high"
                assert "gpt" not in model.lower(), f"Profile agent {name} uses GPT: {model}"
                assert "openai" not in model.lower(), f"Profile agent {name} uses OpenAI: {model}"

def test_agents_md_no_active_gpt_openai(workspace_root):
    agents_md_path = os.path.join(workspace_root, "AGENTS.md")
    with open(agents_md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check that any active routing points to Gemini
    # Check that code-gpt54 is marked as compatibility label
    match = re.search(r'code-gpt54.*historical compatibility label', content, re.IGNORECASE)
    assert match is not None, "AGENTS.md does not mark code-gpt54 as historical compatibility label"
    
    # Active specialists must point to Gemini
    specialists_line = re.search(r'bet-orchestrator.*bet-\*.*specialists.*gemini-3.5-flash-flex-high', content, re.IGNORECASE)
    assert specialists_line is not None, "AGENTS.md does not specify Gemini 3.5 Flash high flex for specialists"

def test_betting_safety_rules_exist(workspace_root):
    agents_dir = os.path.join(workspace_root, ".kilo/agents")
    files = glob.glob(os.path.join(agents_dir, "*.md"))
    
    # Compile-time/text check for betting safety constraints
    for filepath in files:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Ensure we don't allow live placement or browser automation
        # (all agents have constraints or policies)
        lower_content = content.lower()
        if "orchestrator" in filepath:
            assert "never use bash" in lower_content or "never use fish" in lower_content or "bash: deny" in lower_content
            assert "bet_artifact_write" in lower_content
            assert "never perform specialist analysis" in lower_content
        elif "builder" in filepath:
            assert "never" in lower_content
            assert "coupon" in lower_content
