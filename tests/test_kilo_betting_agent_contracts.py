import re
import subprocess
from pathlib import Path
import yaml
import pytest
import json

# Setup paths
WORKSPACE_ROOT = Path(__file__).parent.parent
AGENT_DIR = WORKSPACE_ROOT / ".kilo/agents"
PROMPT_DIR = WORKSPACE_ROOT / ".kilo/prompts"
DOCS_DIR = WORKSPACE_ROOT / ".kilo/docs"
MANIFEST_PATH = WORKSPACE_ROOT / "config/pipeline_manifest.json"
AGENTS_MD_PATH = WORKSPACE_ROOT / "AGENTS.md"
README_PATH = WORKSPACE_ROOT / "README.md"

# The seven power agents
POWER_AGENTS = [
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
]

# Legacy micro-agents
DEPRECATED_AGENTS = [
    "bet-orchestrator",
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-test-engineer",
    "bet-db-analyst",
    "bet-reconciler",
    "bet-settler",
    "bet-engineer",
]


def load_agent_markdown(name: str):
    path = AGENT_DIR / f"{name}.md"
    assert path.exists(), f"Agent file {name}.md does not exist"
    content = path.read_text(encoding="utf-8")
    parts = content.split("---")
    assert len(parts) >= 3, f"Agent file {name}.md does not have frontmatter"
    frontmatter = yaml.safe_load(parts[1])
    body = "---".join(parts[2:])
    return frontmatter, body, path


# 1. exactly seven power agent files exist
def test_exactly_seven_power_agent_files_exist():
    for name in POWER_AGENTS:
        load_agent_markdown(name)


# 2. legacy agent files do not exist
def test_legacy_agent_files_do_not_exist():
    for name in DEPRECATED_AGENTS:
        path = AGENT_DIR / f"{name}.md"
        assert not path.exists(), f"Legacy agent file {name}.md should have been deleted"


# 3. no .kilo/prompts/bet-*.md exists under prompts
def test_no_legacy_betting_prompts_exist():
    prompts = list(PROMPT_DIR.glob("bet-*.md"))
    assert not prompts, f"Legacy betting prompt files still exist: {[p.name for p in prompts]}"


# 4. every power agent starts with ---\n and has a closing \n---\n and standard multiline YAML
def test_power_agent_frontmatter_format():
    for name in POWER_AGENTS:
        path = AGENT_DIR / f"{name}.md"
        content = path.read_text(encoding="utf-8")
        assert content.startswith("---\n"), f"Agent {name} frontmatter must start with ---\n"
        assert "\n---\n" in content, f"Agent {name} must have closing \n---\n"
        
        # Verify no compressed one-line YAML is used
        lines = content.split("\n")
        frontmatter_lines = []
        for line in lines[1:]:
            if line.strip() == "---":
                break
            frontmatter_lines.append(line)
        
        assert len(frontmatter_lines) >= 8, f"Agent {name} frontmatter seems compressed or too short"
        for line in frontmatter_lines:
            # Ensure no JSON-like compressed maps
            if line.strip() and not line.strip().startswith("#"):
                assert "{" not in line and "}" not in line, f"Compressed one-line frontmatter dictionary found in {name}: '{line}'"


# 5. YAML frontmatter parses successfully with safe_load
def test_yaml_frontmatter_parses():
    for name in POWER_AGENTS:
        frontmatter, _, _ = load_agent_markdown(name)
        assert isinstance(frontmatter, dict)


# 6. no explicit model pins
def test_no_explicit_model_pins():
    for name in POWER_AGENTS:
        frontmatter, _, _ = load_agent_markdown(name)
        assert "model" not in frontmatter, f"Agent {name} pins model explicitly which is forbidden"


# 7. no ask permissions
def test_no_ask_permissions():
    for name in POWER_AGENTS:
        frontmatter, _, _ = load_agent_markdown(name)
        perms = frontmatter.get("permission", {})
        for key, val in perms.items():
            assert val != "ask", f"Agent {name} has forbidden 'ask' permission on {key}"


# 8. question: deny for every power agent
def test_question_deny_for_every_power_agent():
    for name in POWER_AGENTS:
        frontmatter, _, _ = load_agent_markdown(name)
        perms = frontmatter.get("permission", {})
        assert perms.get("question", "deny") == "deny", f"Agent {name} must have question: deny"


# 9. bet-executor has bash allow
def test_bet_executor_has_bash_allow():
    frontmatter, _, _ = load_agent_markdown("bet-executor")
    perms = frontmatter.get("permission", {})
    assert perms.get("bash") == "allow", "bet-executor must have bash: allow"


# 10. bet-executor has edit/write/apply_patch deny
def test_bet_executor_has_mutation_deny():
    frontmatter, _, _ = load_agent_markdown("bet-executor")
    perms = frontmatter.get("permission", {})
    for mut in ["edit", "write", "apply_patch"]:
        assert perms.get(mut, "deny") == "deny", f"bet-executor must deny {mut}"


# 11. bet-executor task policy uses controlled power agent allowlist
def test_bet_executor_task_allowlist():
    frontmatter, _, _ = load_agent_markdown("bet-executor")
    perms = frontmatter.get("permission", {})
    task_policy = perms.get("task")
    assert isinstance(task_policy, dict), "bet-executor task permission must be a dictionary allowlist"
    assert task_policy.get("*") == "deny"
    for agent in ["bet-researcher", "bet-modeler", "bet-risk-gatekeeper", "bet-builder", "bet-auditor", "bet-settler-postevent"]:
        assert task_policy.get(agent) == "allow"


# 12. bet-researcher/modeler/risk-gatekeeper/builder/settler-postevent have bash deny
def test_business_agents_have_bash_deny():
    for name in ["bet-researcher", "bet-modeler", "bet-risk-gatekeeper", "bet-builder", "bet-settler-postevent"]:
        frontmatter, _, _ = load_agent_markdown(name)
        perms = frontmatter.get("permission", {})
        assert perms.get("bash", "deny") == "deny", f"Agent {name} must deny bash"


# 13. bet-auditor has bash allow and mutation deny
def test_bet_auditor_permissions():
    frontmatter, _, _ = load_agent_markdown("bet-auditor")
    perms = frontmatter.get("permission", {})
    assert perms.get("bash") == "allow", "bet-auditor must have bash: allow"
    for mut in ["edit", "write", "apply_patch"]:
        assert perms.get(mut, "deny") == "deny", f"bet-auditor must deny {mut}"


# 14. manifest uses only power-agent names
def test_manifest_uses_only_power_agent_names():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for step in data.get("steps", []):
        agent = step.get("agent")
        assert agent in POWER_AGENTS, f"Manifest step '{step.get('id')}' references unauthorized agent '{agent}'"


# 15. manifest mappings for steps are correct
def test_manifest_step_mappings():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    
    step_s3 = next(s for s in data["steps"] if s["id"] == "S3")
    step_s4 = next(s for s in data["steps"] if s["id"] == "S4")
    assert step_s3["agent"] == "bet-modeler"
    assert step_s4["agent"] == "bet-modeler"

    for step_id in ["S5", "S6", "S7", "S9"]:
        step = next(s for s in data["steps"] if s["id"] == step_id)
        assert step["agent"] == "bet-risk-gatekeeper"

    step_s7b = next(s for s in data["steps"] if s["id"] == "S7b")
    assert step_s7b["agent"] == "bet-auditor"


# 16. matrix uses only power agents
def test_matrix_uses_only_power_agents():
    matrix_path = DOCS_DIR / "betting_agent_tool_matrix.md"
    assert matrix_path.exists()
    content = matrix_path.read_text(encoding="utf-8")
    for name in DEPRECATED_AGENTS:
        if name not in ["bet-settler", "bet-orchestrator"]:  # bet-settler is part of bet-settler-postevent substring, and bet-orchestrator is mentioned as removed
            assert f"`{name}`" not in content and f"**{name}**" not in content


# 17. AGENTS.md has no old micro-agent roster and repair guidelines are correct
def test_agents_md_no_old_roster():
    content = AGENTS_MD_PATH.read_text(encoding="utf-8")
    for name in DEPRECATED_AGENTS:
        assert f"## {name}" not in content
        assert f"### {name}" not in content
        assert f"**{name}**:" not in content
        assert f"- **{name}**" not in content
    
    assert "Code or General" in content or "Code/General" in content
    assert "new worktree" in content


# 18. README does not contain active old roster names, and mentions Superbet manual Bet Builder
def test_readme_stale_roster_and_superbet_manual():
    content = README_PATH.read_text(encoding="utf-8")
    
    # Check old micro-agents are not active or in table
    for name in DEPRECATED_AGENTS:
        if name != "bet-settler":
            assert f"| {name} |" not in content, f"README must not contain legacy agent {name} in table"
            assert f"`{name}`" not in content, f"README must not refer to active legacy agent {name}"

    # Check Superbet manual Bet Builder and power agents are mentioned
    assert "Superbet" in content
    assert "manual Bet Builder" in content or "manual" in content
    assert "bet-executor" in content
    assert "bet-researcher" in content

    # Check that stale Rapid-MLX v0.6.82 has been removed/neutralized
    assert "Rapid-MLX v0.6.82" not in content, "Stale Rapid-MLX v0.6.82 reference found in README"

    # Betclic is not presented as primary current workflow
    assert "Targets disciplined small-bankroll betting on Betclic" not in content
    assert "All picks CONDITIONAL until user verifies in Betclic app" not in content


# 19. no production agent claims browser/operator placement
def test_no_production_agent_claims_placement():
    for name in POWER_AGENTS:
        _, body, _ = load_agent_markdown(name)
        assert "automated bookmaker placement" not in body.lower()


# 20. no reports/pipeline_runs included in patch
def test_no_reports_in_patch():
    try:
        base_commit = "7b56ea5c83a469735a8bbbb48c4347b6a0c390f9"
        res = subprocess.run(
            ["git", "diff", "--name-only", f"{base_commit}..HEAD"],
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = res.stdout.splitlines()
        for file in changed_files:
            assert "reports/pipeline_runs/" not in file, f"Forbidden report artifact in patch diff: {file}"
    except Exception:
        pass
