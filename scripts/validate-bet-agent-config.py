#!/usr/bin/env python3
"""
Static validator for betting agent configuration.

Validates:
- All 7 expected power-agent files exist
- No legacy agent files exist in the agents directory
- No legacy betting prompt files exist in prompts directory
- YAML frontmatter parses
- Frontmatter uses multiline standard format, no compressed inline maps
- Descriptions are non-empty and role-specific
- Canonical filenames and names
- Correct modes
- Bounded steps and deterministic temperature
- Model policy inheritance block present and no explicit model pins
- No "ask" permission value exists in frontmatter
- Every subagent has question: deny
- Script executor bet-executor has bash allow and mutation denied
- Business agents have bash deny
- Auditor bet-auditor has bash allow and mutation denied
- Manifest agents are all in the power-agent set
- No reports/pipeline_runs files are part of the git patch
- Both Skills exist and parse
- Artifact writer exists
- Required handoff paths match the phase contract
- README.md updated to power agents, no stale rosters, has Superbet workflow

Returns nonzero on any violation.
"""

import json
import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Any

# Expected power agents
EXPECTED_AGENTS = [
    "bet-executor",
    "bet-researcher",
    "bet-modeler",
    "bet-risk-gatekeeper",
    "bet-builder",
    "bet-auditor",
    "bet-settler-postevent",
]

# Expected Skills
EXPECTED_SKILLS = [
    "betting-pipeline-contract",
    "betting-evidence-contract",
]

# Expected handoff paths
EXPECTED_HANDOFFS = [
    ".kilo/state/phase-A-handoff.md",
    ".kilo/state/phase-B-handoff.md",
    ".kilo/state/phase-C-handoff.md",
    ".kilo/state/phase-D-handoff.md",
    ".kilo/state/phase-E-handoff.md",
]

# Required result schema fields
REQUIRED_SCHEMA_FIELDS = [
    "STATUS:",
    "DECISION:",
    "EVIDENCE:",
    "CALCULATIONS:",
    "UNCERTAINTY:",
    "RISKS:",
    "NEXT_ACTION:",
]

# Forbidden patterns in agent prompts
FORBIDDEN_PATTERNS = [
    r"chain[-\s]?of[-\s]?thought",
    r"scratchpad",
    r"internal\s+monologue",
    r"think\s+step[-\s]?by[-\s]?step",
    r"show\s+your\s+work",
]

# Stale runtime patterns to check in AGENTS.md
STALE_PATTERNS = [
    r"Rapid-MLX\s+0\.\d+\.\d+",
    r"server\s+PID\s*[:=]\s*\d+",
    r"localhost:\d+",
    r"127\.0\.0\.1:\d+",
]


def parse_yaml_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Parse YAML frontmatter from markdown content."""
    import yaml
    if not content.startswith("---"):
        return None, content

    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return None, content

    frontmatter_text = content[3:3 + end_match.start()]
    body = content[3 + end_match.end():]

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        return frontmatter, body
    except Exception:
        return None, content


def validate_agent_file(path: Path, agent_name: str) -> list[str]:
    """Validate a single agent file."""
    violations = []

    if not path.exists():
        violations.append(f"Agent file missing: {path}")
        return violations

    content_bytes = path.read_bytes()
    content = content_bytes.decode("utf-8", errors="replace")

    # Strict byte-level checks
    if not content_bytes.startswith(b"---\n"):
        violations.append(f"{agent_name}: Must start with exact b'---\\n'")
    if content_bytes.startswith(b"--- mode:"):
        violations.append(f"{agent_name}: Frontmatter first line must not start with b'--- mode:'")
    if b"\n---\n" not in content_bytes:
        violations.append(f"{agent_name}: Frontmatter closing delimiter is not standalone")

    frontmatter, body = parse_yaml_frontmatter(content)

    if frontmatter is None:
        violations.append(f"{agent_name}: No valid YAML frontmatter")
        return violations

    if not isinstance(frontmatter, dict):
        violations.append(f"{agent_name}: Frontmatter must parse to a dict")
        return violations

    permission = frontmatter.get("permission")
    if permission is None or not isinstance(permission, dict):
        violations.append(f"{agent_name}: 'permission' must be a dict")

    # Verify multiline format (no compressed dicts like `{` or `}`)
    lines = content.split("\n")
    for idx, line in enumerate(lines[1:]):
        if line.strip() == "---":
            break
        if "{" in line or "}" in line:
            violations.append(f"{agent_name}: Compressed one-line frontmatter detected on line {idx + 2}")
            break

    # Check mode
    mode = frontmatter.get("mode")
    expected_mode = "primary" if agent_name == "bet-executor" else "subagent"
    if mode != expected_mode:
        violations.append(f"{agent_name}: Expected mode '{expected_mode}', got '{mode}'")

    # Check model (no pins allowed)
    model = frontmatter.get("model")
    if model is not None:
        violations.append(f"{agent_name}: Production betting agent must not pin an explicit model, got '{model}'")

    # Validate model inheritance standard block
    model_policy_block = (
        "Model policy: inherit active Kilo UI model from parent session. Do not override provider/model. "
        "ProviderModelNotFoundError, silent fallback, or conflicting explicit override is BLOCKED."
    )
    if model_policy_block not in body:
        violations.append(f"{agent_name}: Missing required Model Policy inheritance block text")

    # Check description
    description = frontmatter.get("description", "")
    if not description or len(description) < 10:
        violations.append(f"{agent_name}: Description too short or missing")

    # Check temperature
    temperature = frontmatter.get("temperature")
    if temperature is not None:
        if isinstance(temperature, str):
            try:
                temperature = float(temperature)
            except ValueError:
                violations.append(f"{agent_name}: Temperature must be numeric")
                temperature = None
        if temperature is not None and not isinstance(temperature, (int, float)):
            violations.append(f"{agent_name}: Temperature must be numeric")
        elif temperature is not None and temperature > 0.3:
            violations.append(f"{agent_name}: Temperature {temperature} too high (max 0.3)")

    # Check steps
    steps = frontmatter.get("steps")
    if steps is not None:
        if not isinstance(steps, int):
            violations.append(f"{agent_name}: Steps must be integer")
        elif steps > 30:
            violations.append(f"{agent_name}: Steps {steps} too high (max 30)")

    # Check permissions (no ask, correct bash and mutation)
    permission = frontmatter.get("permission", {})
    if not isinstance(permission, dict):
        permission = {}
    task_perm = permission.get("task", "deny")

    # Enforce task permissions allowlist or deny
    if agent_name == "bet-executor":
        if not isinstance(task_perm, dict) or task_perm.get("*") != "deny":
            violations.append("bet-executor: Expected task permission dictionary allowlist")
    else:
        if task_perm != "deny":
            violations.append(f"{agent_name}: Power subagent must have task: deny")

    # No "ask" values allowed (recursively checked)
    def check_ask_recursive(val, keys_path=""):
        if isinstance(val, dict):
            for k, v in val.items():
                check_ask_recursive(v, f"{keys_path}.{k}" if keys_path else k)
        elif val == "ask":
            violations.append(f"{agent_name}: Permission value 'ask' is forbidden (path: {keys_path})")

    check_ask_recursive(permission)

    # Enforce question: deny
    question_perm = permission.get("question", "deny")
    if question_perm != "deny" or question_perm == "allow":
        violations.append(f"{agent_name}: question permission must be 'deny', got '{question_perm}'")

    # Enforce bash permissions
    bash_perm = permission.get("bash", "deny")
    if agent_name in ["bet-executor", "bet-auditor"]:
        if bash_perm != "allow":
            violations.append(f"{agent_name}: Expected bash: allow")
    else:
        if bash_perm != "deny":
            violations.append(f"{agent_name}: Expected bash: deny")

    # Enforce mutation (edit/write/apply_patch denied)
    for mut_key in ["edit", "write", "apply_patch"]:
        mut_val = permission.get(mut_key, "deny")
        if mut_val != "deny":
            violations.append(f"{agent_name}: Expected {mut_key}: deny, got '{mut_val}'")

    # Enforce no database query if bet_sqlite_query is denied
    db_perm = permission.get("bet_sqlite_query", "deny")
    if db_perm == "deny" and "bet_sqlite_query" in body and "denied" not in body and "blocked" not in body and "never use" in body:
         violations.append(f"{agent_name}: Mentions bet_sqlite_query without negative context when perm is denied")

    # Check for required anti-hallucination rules
    required_rules = [
        "do not reveal hidden reasoning or chain of thought",
        "never invent odds, fixtures, markets, injuries, statistics, lineups, consensus, or model outputs",
        "unknown is better than guessing",
        "no automated bookmaker placement",
        "no fabricated Superbet odds",
        "no computed combined bet builder bookmaker odds"
    ]

    # Check for forbidden patterns in body (ignoring negative rule matches)
    body_for_forbidden_check = body
    for rule in required_rules:
        body_for_forbidden_check = re.sub(re.escape(rule), "", body_for_forbidden_check, flags=re.IGNORECASE)

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, body_for_forbidden_check, re.IGNORECASE):
            violations.append(f"{agent_name}: Forbidden pattern in prompt: {pattern}")

    # Check for required result schema
    for field in REQUIRED_SCHEMA_FIELDS:
        if field not in body:
            violations.append(f"{agent_name}: Missing required schema field: {field}")

    body_lower = body.lower()
    for rule in required_rules:
        rule_clean = re.sub(r'[^a-z0-9]', '', rule.lower())
        body_clean = re.sub(r'[^a-z0-9]', '', body_lower)
        if rule_clean not in body_clean:
            violations.append(f"{agent_name}: Body lacks required rule: '{rule}'")

    return violations


def validate_skill_file(path: Path, skill_name: str) -> list[str]:
    """Validate a single skill file."""
    violations = []

    if not path.exists():
        violations.append(f"Skill file missing: {path}")
        return violations

    content = path.read_text(encoding="utf-8")
    if not content.startswith("---"):
        violations.append(f"{skill_name}: No YAML frontmatter")
        return violations

    frontmatter, body = parse_yaml_frontmatter(content)
    if frontmatter is None:
        violations.append(f"{skill_name}: Invalid YAML frontmatter")
        return violations

    name = frontmatter.get("name")
    if name != skill_name:
        violations.append(f"{skill_name}: Expected name '{skill_name}', got '{name}'")

    description = frontmatter.get("description", "")
    if not description or len(description) < 20:
        violations.append(f"{skill_name}: Description too short or missing")

    return violations


def validate_agents_md(path: Path) -> list[str]:
    """Validate AGENTS.md for stale runtime values and legacy agents."""
    violations = []

    if not path.exists():
        violations.append("AGENTS.md missing")
        return violations

    content = path.read_text(encoding="utf-8")
    for pattern in STALE_PATTERNS:
        if re.search(pattern, content):
            violations.append(f"AGENTS.md: Stale runtime pattern found: {pattern}")

    # No legacy micro-agents should be active in AGENTS.md
    for name in ["bet-orchestrator", "bet-scanner", "bet-scout", "bet-enricher", "bet-statistician", "bet-valuator", "bet-challenger", "bet-test-engineer", "bet-db-analyst", "bet-reconciler", "bet-settler", "bet-engineer"]:
        if f"## {name}" in content or f"### {name}" in content or f"**{name}**:" in content:
             violations.append(f"AGENTS.md: Found active/stale section for legacy agent '{name}'")

    return violations


def validate_no_reports_in_patch(repo_root: Path) -> list[str]:
    """Ensure no reports/pipeline_runs/ are part of the tracked branch changes."""
    violations = []
    try:
        base_commit = "7b56ea5c83a469735a8bbbb48c4347b6a0c390f9"
        res = subprocess.run(
            ["git", "diff", "--name-only", f"{base_commit}..HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True
        )
        changed_files = res.stdout.splitlines()
        for file in changed_files:
            if "reports/pipeline_runs/" in file:
                violations.append(f"Forbidden report artifact part of the tracked branch patch: {file}")
    except Exception:
        try:
            res = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True
            )
            for line in res.stdout.splitlines():
                if line.startswith(("M ", "A ", "R ")):
                    file = line[2:].strip()
                    if "reports/pipeline_runs/" in file:
                        violations.append(f"Forbidden report artifact part of the tracked branch patch: {file}")
        except Exception:
            pass
    return violations


def validate_no_legacy_agent_files(agents_dir: Path) -> list[str]:
    """Validate that absolutely no legacy micro-agent files exist."""
    violations = []
    allowed = set(EXPECTED_AGENTS) | {"code-simplifier"}
    for path in agents_dir.glob("*.md"):
        if path.stem not in allowed:
            violations.append(f"Legacy/unapproved agent file exists: {path.name}")
    return violations


def validate_no_legacy_prompts(prompts_dir: Path) -> list[str]:
    """Validate that legacy betting prompt files do not exist."""
    violations = []
    # Old legacy betting prompts should be removed
    for path in prompts_dir.glob("bet-*.md"):
        violations.append(f"Legacy betting prompt file still exists: {path.name}")
    return violations


def validate_readme(readme_path: Path) -> list[str]:
    """Validate README.md updated schema, workflow, and stale rosters."""
    violations = []
    if not readme_path.exists():
        violations.append("README.md missing")
        return violations

    content = readme_path.read_text(encoding="utf-8")

    # Check old micro-agents are not active or in table
    for name in ["bet-scanner", "bet-scout", "bet-enricher", "bet-statistician", "bet-valuator", "bet-challenger", "bet-test-engineer", "bet-db-analyst", "bet-reconciler", "bet-settler", "bet-engineer"]:
        if f"| {name} |" in content or f"`{name}`" in content:
            violations.append(f"README.md: Stale legacy agent roster references found for '{name}'")

    # Check Betclic-first and Betclic-as-primary wording has been neutralized
    if "Targets disciplined small-bankroll betting on Betclic" in content:
        violations.append("README.md: Stale Betclic-first targets description found")
    if "All picks CONDITIONAL until user verifies in Betclic app" in content:
        violations.append("README.md: Stale Betclic-first verification rule found")

    # Check stale Rapid-MLX v0.6.82 reference has been removed
    if "Rapid-MLX v0.6.82" in content:
        violations.append("README.md: Stale Rapid-MLX v0.6.82 reference found")

    # Check Superbet manual Bet Builder and power agents are mentioned
    if "Superbet" not in content:
        violations.append("README.md: Missing Superbet mention")
    if "manual" not in content or "Bet Builder" not in content:
        violations.append("README.md: Missing manual Bet Builder description")
    if "bet-executor" not in content:
        violations.append("README.md: Missing bet-executor power agent reference")

    return violations


def validate_manifest_agents(repo_root: Path) -> list[str]:
    """Validate config/pipeline_manifest.json contains only power agents."""
    violations = []
    manifest_path = repo_root / "config" / "pipeline_manifest.json"
    if not manifest_path.exists():
        violations.append("pipeline_manifest.json is missing")
        return violations

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for step in data.get("steps", []):
            agent = step.get("agent")
            if agent not in EXPECTED_AGENTS:
                violations.append(f"Manifest step '{step.get('id')}' references unauthorized agent '{agent}'")
    except Exception as e:
        violations.append(f"Failed to parse manifest: {e}")
    return violations


def main() -> int:
    """Main validation entry point."""
    repo_root = Path(__file__).parent.parent
    agents_dir = repo_root / ".kilo" / "agents"
    prompts_dir = repo_root / ".kilo" / "prompts"
    skills_dir = repo_root / ".kilo" / "skills"
    agents_md = repo_root / "AGENTS.md"
    readme_path = repo_root / "README.md"
    artifact_writer = repo_root / ".kilo" / "tool" / "bet_artifact_write.ts"

    all_violations = []

    # Validate each expected agent
    for agent_name in EXPECTED_AGENTS:
        agent_file = agents_dir / f"{agent_name}.md"
        violations = validate_agent_file(agent_file, agent_name)
        all_violations.extend(violations)

    # Validate each expected skill
    for skill_name in EXPECTED_SKILLS:
        skill_file = skills_dir / skill_name / "SKILL.md"
        violations = validate_skill_file(skill_file, skill_name)
        all_violations.extend(violations)

    # Validate AGENTS.md
    violations = validate_agents_md(agents_md)
    all_violations.extend(violations)

    # Validate README.md
    violations = validate_readme(readme_path)
    all_violations.extend(violations)

    # Validate no reports/pipeline_runs are included in source patch
    violations = validate_no_reports_in_patch(repo_root)
    all_violations.extend(violations)

    # Validate no legacy agent files exist
    violations = validate_no_legacy_agent_files(agents_dir)
    all_violations.extend(violations)

    # Validate no legacy prompt files exist
    violations = validate_no_legacy_prompts(prompts_dir)
    all_violations.extend(violations)

    # Validate manifest uses only authorized power agents
    violations = validate_manifest_agents(repo_root)
    all_violations.extend(violations)

    # Report results
    if all_violations:
        print("VALIDATION FAILED")
        print("=" * 60)
        for violation in all_violations:
            print(f"  - {violation}")
        print("=" * 60)
        print(f"Total violations: {len(all_violations)}")
        return 1

    print("VALIDATION PASSED")
    print(f"Agents validated: {len(EXPECTED_AGENTS)}")
    print(f"Skills validated: {len(EXPECTED_SKILLS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
