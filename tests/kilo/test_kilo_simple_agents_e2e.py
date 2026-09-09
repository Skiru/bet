"""Comprehensive end-to-end testing suite for Kilo simple agents ecosystem.

Validates:
1. Agent definitions, frontmatter schema, role modes, and strict permission governance.
2. Skill structures, frontmatter metadata, and referenced methodology documents.
3. Slash command definitions and agent routing bindings.
4. Feature parity between legacy Claude definitions and modular Kilo definitions.
5. Project configuration (kilo.json) validity and MCP server bindings.
6. Live Kilo CLI discovery and configuration checks.
7. Pipeline runtime script interface compatibility.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
KILO_DIR = ROOT / ".kilo"
KILO_AGENTS_DIR = KILO_DIR / "agent"
KILO_SKILLS_DIR = KILO_DIR / "skills"
KILO_COMMANDS_DIR = KILO_DIR / "command"
KILO_CONFIG_PATH = ROOT / "kilo.json"

CLAUDE_DIR = ROOT / ".claude"
CLAUDE_AGENTS_DIR = CLAUDE_DIR / "agents"
CLAUDE_SKILLS_DIR = CLAUDE_DIR / "skills"
CLAUDE_COMMANDS_DIR = CLAUDE_DIR / "commands"

SIMPLE_AGENTS = (
    "bet-simple",
    "bet-analyst-football",
    "bet-analyst-tennis",
    "superbet-market-matcher",
    "tipster-reader",
)

EXPECTED_MODES = {
    "bet-simple": "primary",
    "bet-analyst-football": "subagent",
    "bet-analyst-tennis": "subagent",
    "superbet-market-matcher": "subagent",
    "tipster-reader": "subagent",
}

EXPECTED_SKILLS = (
    "bet-analysis-core",
    "football-analysis",
    "tennis-analysis",
    "bet-slip-audit",
    "simple-stats-runtime",
)

EXPECTED_COMMANDS = (
    "run-day",
    "rebuild-coupon",
)


def _load_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    assert path.exists(), f"File does not exist: {path}"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("---"), f"{path.name} must start with frontmatter '---'"
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{path.name} does not contain complete frontmatter block"
    frontmatter = yaml.safe_load(parts[1])
    assert isinstance(frontmatter, dict), f"Frontmatter in {path.name} must be a dict"
    body = parts[2]
    return frontmatter, body


# ==============================================================================
# 1. Agent Definitions & Schema Validation
# ==============================================================================

@pytest.mark.parametrize("agent_name", SIMPLE_AGENTS)
def test_kilo_agent_file_exists_and_parses(agent_name: str) -> None:
    agent_file = KILO_AGENTS_DIR / f"{agent_name}.md"
    frontmatter, body = _load_frontmatter(agent_file)
    assert frontmatter.get("name") == agent_name
    assert isinstance(frontmatter.get("description"), str)
    assert len(frontmatter["description"].strip()) > 20
    assert len(body.strip()) > 100


@pytest.mark.parametrize("agent_name", SIMPLE_AGENTS)
def test_kilo_agent_mode_conforms(agent_name: str) -> None:
    agent_file = KILO_AGENTS_DIR / f"{agent_name}.md"
    frontmatter, _ = _load_frontmatter(agent_file)
    expected_mode = EXPECTED_MODES[agent_name]
    assert frontmatter.get("mode") == expected_mode, (
        f"{agent_name} mode is {frontmatter.get('mode')!r}, expected {expected_mode!r}"
    )


@pytest.mark.parametrize("agent_name", SIMPLE_AGENTS)
def test_kilo_agent_model_governance(agent_name: str) -> None:
    """Production betting agents must NOT pin an explicit model (inherits Kilo UI model)."""
    agent_file = KILO_AGENTS_DIR / f"{agent_name}.md"
    frontmatter, body = _load_frontmatter(agent_file)
    assert "model" not in frontmatter, f"{agent_name} defines explicit model pin, which violates AGENTS.md"
    assert "steps" not in frontmatter, f"{agent_name} defines explicit steps cap in frontmatter"
    forbidden_patterns = [
        re.compile(r"start (?:a )?fresh session after phase", re.I),
        re.compile(r"do not cross a phase boundary", re.I),
    ]
    for pattern in forbidden_patterns:
        assert pattern.search(body) is None, f"{agent_name} contains forbidden session cap: {pattern.pattern}"


@pytest.mark.parametrize("agent_name", SIMPLE_AGENTS)
def test_kilo_agent_permissions_fail_closed(agent_name: str) -> None:
    """Permissions must not contain 'ask' (unattended safety) and must deny interactive questions & file mutations."""
    agent_file = KILO_AGENTS_DIR / f"{agent_name}.md"
    frontmatter, _ = _load_frontmatter(agent_file)
    perms = frontmatter.get("permission", {})
    assert isinstance(perms, dict), f"{agent_name} permission block must be a dict"

    def _check_no_ask(v: Any, key_path: str = "") -> None:
        if isinstance(v, dict):
            for k, val in v.items():
                _check_no_ask(val, f"{key_path}.{k}" if key_path else k)
        else:
            assert v != "ask", f"{agent_name} has forbidden 'ask' permission at {key_path}"

    _check_no_ask(perms)
    assert perms.get("question") == "deny", f"{agent_name} must have question: deny"
    assert perms.get("edit") == "deny", f"{agent_name} must have edit: deny"
    assert perms.get("write") == "deny", f"{agent_name} must have write: deny"
    assert perms.get("apply_patch") == "deny", f"{agent_name} must have apply_patch: deny"


def test_bet_simple_orchestrator_capabilities() -> None:
    agent_file = KILO_AGENTS_DIR / "bet-simple.md"
    frontmatter, body = _load_frontmatter(agent_file)
    perms = frontmatter.get("permission", {})

    assert perms.get("bash") == "allow", "bet-simple must allow bash to run pipeline"
    assert perms.get("read") == "allow"
    assert perms.get("glob") == "allow"
    assert perms.get("grep") == "allow"

    task_policy = perms.get("task")
    assert isinstance(task_policy, dict), "bet-simple task policy must be a dict allowlist"
    assert task_policy.get("*") == "deny", "bet-simple task wildcard must deny unknown agents"

    subagents = {
        "bet-analyst-football",
        "bet-analyst-tennis",
        "superbet-market-matcher",
        "tipster-reader",
    }
    for sub in subagents:
        assert task_policy.get(sub) == "allow", f"bet-simple must allow task delegation to {sub}"

    assert "python3 scripts/simple/run_pipeline.py" in body


def test_analysts_and_subagents_capabilities() -> None:
    # 1. bet-analyst-football
    frontmatter, _ = _load_frontmatter(KILO_AGENTS_DIR / "bet-analyst-football.md")
    p_football = frontmatter.get("permission", {})
    assert p_football.get("bash") == "allow"
    assert p_football.get("webfetch") == "allow"
    assert p_football.get("websearch") == "allow"
    assert p_football.get("task") == "deny"
    assert p_football.get("bzzoiro_*") == "allow"

    # 2. bet-analyst-tennis
    frontmatter, _ = _load_frontmatter(KILO_AGENTS_DIR / "bet-analyst-tennis.md")
    p_tennis = frontmatter.get("permission", {})
    assert p_tennis.get("bash") == "allow"
    assert p_tennis.get("webfetch") == "allow"
    assert p_tennis.get("websearch") == "allow"
    assert p_tennis.get("task") == "deny"
    assert p_tennis.get("bzzoiro_*") == "deny", "Tennis analyst must deny bzzoiro MCP due to 402 addon"

    # 3. superbet-market-matcher
    frontmatter, _ = _load_frontmatter(KILO_AGENTS_DIR / "superbet-market-matcher.md")
    p_matcher = frontmatter.get("permission", {})
    assert p_matcher.get("bash") == "allow"
    assert p_matcher.get("webfetch") == "allow"
    assert p_matcher.get("task") == "deny"
    assert p_matcher.get("bzzoiro_*") == "allow"

    # 4. tipster-reader
    frontmatter, _ = _load_frontmatter(KILO_AGENTS_DIR / "tipster-reader.md")
    p_tipster = frontmatter.get("permission", {})
    assert p_tipster.get("bash") == "deny", "tipster-reader must have bash: deny"
    assert p_tipster.get("task") == "deny"


# ==============================================================================
# 2. Skills Structure & Integration Validation
# ==============================================================================

@pytest.mark.parametrize("skill_name", EXPECTED_SKILLS)
def test_kilo_skill_exists_and_parses(skill_name: str) -> None:
    skill_file = KILO_SKILLS_DIR / skill_name / "SKILL.md"
    frontmatter, body = _load_frontmatter(skill_file)
    assert frontmatter.get("name") == skill_name
    assert isinstance(frontmatter.get("description"), str)
    assert len(frontmatter["description"].strip()) > 10
    assert len(body.strip()) > 50


def test_kilo_skills_reference_documents_exist() -> None:
    required_references = [
        KILO_SKILLS_DIR / "bet-analysis-core" / "references" / "forecast-card.md",
        KILO_SKILLS_DIR / "bet-analysis-core" / "references" / "artifact-contract.md",
        KILO_SKILLS_DIR / "bet-analysis-core" / "references" / "veto-contract.md",
        KILO_SKILLS_DIR / "bet-analysis-core" / "references" / "evidence-rules.md",
        KILO_SKILLS_DIR / "football-analysis" / "references" / "data-inventory.md",
        KILO_SKILLS_DIR / "football-analysis" / "references" / "market-playbook.md",
        KILO_SKILLS_DIR / "football-analysis" / "references" / "methodology.md",
        KILO_SKILLS_DIR / "football-analysis" / "references" / "event-protocol.md",
        KILO_SKILLS_DIR / "tennis-analysis" / "references" / "data-inventory.md",
        KILO_SKILLS_DIR / "tennis-analysis" / "references" / "event-protocol.md",
        KILO_SKILLS_DIR / "tennis-analysis" / "references" / "market-playbook.md",
        KILO_SKILLS_DIR / "tennis-analysis" / "references" / "methodology.md",
        KILO_SKILLS_DIR / "bet-slip-audit" / "reference" / "base-rates.md",
        KILO_SKILLS_DIR / "bet-slip-audit" / "reference" / "ledger-2026-08-30-31.md",
        KILO_SKILLS_DIR / "bet-slip-audit" / "reference" / "coverage.md",
    ]
    for ref_path in required_references:
        assert ref_path.exists(), f"Reference file missing: {ref_path}"
        assert ref_path.stat().st_size > 50, f"Reference file empty: {ref_path}"


# ==============================================================================
# 3. Slash Commands Structure & Integration Validation
# ==============================================================================

@pytest.mark.parametrize("cmd_name", EXPECTED_COMMANDS)
def test_kilo_command_exists_and_routes(cmd_name: str) -> None:
    cmd_file = KILO_COMMANDS_DIR / f"{cmd_name}.md"
    frontmatter, body = _load_frontmatter(cmd_file)
    assert isinstance(frontmatter.get("description"), str)
    assert frontmatter.get("agent") == "bet-simple", f"{cmd_name} must route to agent: bet-simple"
    assert "$ARGUMENTS" in body, f"{cmd_name} must handle $ARGUMENTS"


# ==============================================================================
# 4. Feature Parity Between Claude and Kilo Environments
# ==============================================================================

@pytest.mark.parametrize("agent_name", SIMPLE_AGENTS)
def test_agent_body_parity(agent_name: str) -> None:
    claude_file = CLAUDE_AGENTS_DIR / f"{agent_name}.md"
    kilo_file = KILO_AGENTS_DIR / f"{agent_name}.md"
    if not claude_file.exists():
        pytest.skip(f"Claude agent file {agent_name}.md not found")

    _, claude_body = _load_frontmatter(claude_file)
    _, kilo_body = _load_frontmatter(kilo_file)

    assert claude_body.strip() == kilo_body.strip(), (
        f"Prompt body of {agent_name} diverged between Claude and Kilo definitions!"
    )


# ==============================================================================
# 5. Project Configuration (kilo.json) Validation
# ==============================================================================

def test_kilo_json_configuration() -> None:
    assert KILO_CONFIG_PATH.exists(), "kilo.json must exist in repository root"
    content = json.loads(KILO_CONFIG_PATH.read_text(encoding="utf-8"))
    assert content.get("$schema") == "https://app.kilo.ai/config.json"
    assert content.get("default_agent") == "bet-simple"

    mcp = content.get("mcp", {})
    assert "bzzoiro" in mcp, "bzzoiro MCP server must be configured"
    assert mcp["bzzoiro"].get("type") == "remote"
    assert mcp["bzzoiro"].get("enabled") is True
    assert "bzzoiro-tennis" in mcp
    assert mcp["bzzoiro-tennis"].get("enabled") is False


# ==============================================================================
# 6. Live Kilo CLI Integration Tests
# ==============================================================================

def test_kilo_cli_config_check() -> None:
    if not shutil.which("kilo"):
        pytest.skip("Kilo CLI binary not found in PATH")
    result = subprocess.run(
        ["kilo", "config", "check"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"kilo config check failed: {result.stderr or result.stdout}"
    assert "No config warnings." in result.stdout or result.returncode == 0


def test_kilo_cli_discovers_all_simple_agents() -> None:
    if not shutil.which("kilo"):
        pytest.skip("Kilo CLI binary not found in PATH")
    result = subprocess.run(
        ["kilo", "agent", "list"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"kilo agent list failed: {result.stderr or result.stdout}"
    output = result.stdout

    # Parse agents: e.g. "bet-simple (primary)"
    discovered_agents = dict(re.findall(r"^([a-zA-Z0-9_-]+)\s+\((primary|subagent|all)\)", output, re.MULTILINE))

    for agent_name, expected_mode in EXPECTED_MODES.items():
        assert agent_name in discovered_agents, (
            f"Agent {agent_name} was not discovered by Kilo CLI! Discovered: {list(discovered_agents.keys())}"
        )
        assert discovered_agents[agent_name] == expected_mode, (
            f"Agent {agent_name} discovered with mode {discovered_agents[agent_name]!r}, expected {expected_mode!r}"
        )


def test_kilo_cli_debug_config_resolution() -> None:
    if not shutil.which("kilo"):
        pytest.skip("Kilo CLI binary not found in PATH")
    result = subprocess.run(
        ["kilo", "debug", "config"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"kilo debug config failed: {result.stderr}"
    config = json.loads(result.stdout)
    assert config.get("default_agent") == "bet-simple"
    assert "bzzoiro" in config.get("mcp", {})


# ==============================================================================
# 7. Pipeline Script Interface Compatibility
# ==============================================================================

def test_pipeline_scripts_are_runnable_by_agents() -> None:
    python_bin = sys.executable
    scripts_dir = ROOT / "scripts" / "simple"

    # Test run_pipeline.py --help
    res_pipeline = subprocess.run(
        [python_bin, str(scripts_dir / "run_pipeline.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res_pipeline.returncode == 0
    assert "--date" in res_pipeline.stdout
    assert "--preflight" in res_pipeline.stdout

    # Test build_forecast.py --help
    res_forecast = subprocess.run(
        [python_bin, str(scripts_dir / "build_forecast.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res_forecast.returncode == 0
    assert "--date" in res_forecast.stdout

    # Test build_coupons.py --help
    res_coupons = subprocess.run(
        [python_bin, str(scripts_dir / "build_coupons.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res_coupons.returncode == 0
    assert "--date" in res_coupons.stdout
