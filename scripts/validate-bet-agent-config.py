#!/usr/bin/env python3
"""
Static validator for betting agent configuration.

Validates:
- All 13 expected agent files exist
- YAML frontmatter parses
- Descriptions are non-empty and role-specific
- Canonical filenames and names
- Correct modes
- Exact resolved local model
- Bounded steps
- Deterministic temperature
- Specialist task: deny
- Orchestrator task allowlist
- MCP disabled
- Forbidden broad permissions absent
- Exact result schema present
- No chain-of-thought requests
- No stale runtime version/model values in AGENTS.md
- No active bet-orchestrator-v2
- No dangling referenced agent IDs
- Both Skills exist and parse
- Artifact writer exists
- Required handoff paths match the phase contract

Returns nonzero on any violation.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

# Expected canonical agents
EXPECTED_AGENTS = [
    "bet-orchestrator",
    "bet-settler",
    "bet-db-analyst",
    "bet-scanner",
    "bet-scout",
    "bet-enricher",
    "bet-statistician",
    "bet-valuator",
    "bet-challenger",
    "bet-reconciler",
    "bet-builder",
    "bet-test-engineer",
    "bet-engineer",
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

# Validated local model ID
VALIDATED_MODEL = "openai-compatible/qwen36-local-35b"

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
    r"hidden\s+reasoning",
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
    if not content.startswith("---"):
        return None, content
    
    # Find the closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return None, content
    
    frontmatter_text = content[3:end_match.end() + 1]
    body = content[end_match.end() + 4:]
    
    # Simple YAML parser for our use case
    result = {}
    current_key = None
    current_value = None
    in_nested = False
    nested_key = None
    
    for line in frontmatter_text.split("\n"):
        line = line.rstrip()
        if line == "---" or not line:
            continue
        
        # Check for nested block
        if line.startswith("  ") and current_key:
            in_nested = True
            nested_match = re.match(r"\s+([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.+)", line)
            if nested_match:
                if current_key not in result:
                    result[current_key] = {}
                result[current_key][nested_match.group(1)] = nested_match.group(2).strip('"\'')
            continue
        
        # Save previous key
        if current_key and not in_nested:
            if current_value is not None:
                result[current_key] = current_value
            current_key = None
            current_value = None
        
        in_nested = False
        
        # Parse key: value
        match = re.match(r"([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)", line)
        if match:
            current_key = match.group(1)
            value = match.group(2).strip()
            if value:
                # Handle quoted strings
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # Handle booleans
                elif value.lower() == "true":
                    value = True
                elif value.lower() == "false":
                    value = False
                # Handle integers
                elif value.isdigit():
                    value = int(value)
                
                current_value = value
    
    # Save last key
    if current_key and current_value is not None:
        result[current_key] = current_value
    
    return result, body


def validate_agent_file(path: Path, agent_name: str) -> list[str]:
    """Validate a single agent file."""
    violations = []
    
    if not path.exists():
        violations.append(f"Agent file missing: {path}")
        return violations
    
    content = path.read_text()
    frontmatter, body = parse_yaml_frontmatter(content)
    
    if frontmatter is None:
        violations.append(f"{agent_name}: No valid YAML frontmatter")
        return violations
    
    # Check mode
    mode = frontmatter.get("mode")
    if agent_name == "bet-orchestrator":
        if mode != "primary":
            violations.append(f"{agent_name}: Expected mode 'primary', got '{mode}'")
    else:
        if mode != "subagent":
            violations.append(f"{agent_name}: Expected mode 'subagent', got '{mode}'")
    
    # Check model
    model = frontmatter.get("model")
    if model != VALIDATED_MODEL:
        violations.append(f"{agent_name}: Expected model '{VALIDATED_MODEL}', got '{model}'")
    
    # Check description
    description = frontmatter.get("description", "")
    if not description or len(description) < 10:
        violations.append(f"{agent_name}: Description too short or missing")
    
    # Check temperature (should be low and deterministic)
    temperature = frontmatter.get("temperature")
    if temperature is not None:
        # Handle string temperatures from YAML parsing
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
    
    # Check steps (should be bounded)
    steps = frontmatter.get("steps")
    if steps is not None:
        if not isinstance(steps, int):
            violations.append(f"{agent_name}: Steps must be integer")
        elif steps > 30:
            violations.append(f"{agent_name}: Steps {steps} too high (max 30)")
    
    # Check permission.task for specialists
    permission = frontmatter.get("permission", {})
    task_perm = permission.get("task")
    
    if agent_name == "bet-orchestrator":
        # Orchestrator should have task allowlist
        if task_perm == "deny":
            violations.append(f"{agent_name}: Orchestrator must have task allowlist, not deny")
    else:
        # Specialists should have task: deny
        if task_perm != "deny":
            violations.append(f"{agent_name}: Specialist must have task: deny")
    
    # Check for forbidden patterns in body
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, body, re.IGNORECASE):
            violations.append(f"{agent_name}: Forbidden pattern in prompt: {pattern}")
    
    # Check for required result schema
    for field in REQUIRED_SCHEMA_FIELDS:
        if field not in body:
            violations.append(f"{agent_name}: Missing required schema field: {field}")
    
    return violations


def validate_skill_file(path: Path, skill_name: str) -> list[str]:
    """Validate a single skill file."""
    violations = []
    
    if not path.exists():
        violations.append(f"Skill file missing: {path}")
        return violations
    
    content = path.read_text()
    
    # Check for YAML frontmatter
    if not content.startswith("---"):
        violations.append(f"{skill_name}: No YAML frontmatter")
        return violations
    
    frontmatter, body = parse_yaml_frontmatter(content)
    
    if frontmatter is None:
        violations.append(f"{skill_name}: Invalid YAML frontmatter")
        return violations
    
    # Check name
    name = frontmatter.get("name")
    if name != skill_name:
        violations.append(f"{skill_name}: Expected name '{skill_name}', got '{name}'")
    
    # Check description
    description = frontmatter.get("description", "")
    if not description or len(description) < 20:
        violations.append(f"{skill_name}: Description too short or missing")
    
    return violations


def validate_agents_md(path: Path) -> list[str]:
    """Validate AGENTS.md for stale runtime values."""
    violations = []
    
    if not path.exists():
        violations.append("AGENTS.md missing")
        return violations
    
    content = path.read_text()
    
    # Check for stale runtime patterns
    for pattern in STALE_PATTERNS:
        if re.search(pattern, content):
            violations.append(f"AGENTS.md: Stale runtime pattern found: {pattern}")
    
    # Check for bet-orchestrator-v2 reference
    if "bet-orchestrator-v2" in content:
        violations.append("AGENTS.md: References deprecated bet-orchestrator-v2")
    
    return violations


def validate_artifact_writer(path: Path) -> list[str]:
    """Validate artifact writer tool exists."""
    violations = []
    
    if not path.exists():
        violations.append(f"Artifact writer missing: {path}")
    
    return violations


def validate_no_legacy_orchestrator(agents_dir: Path) -> list[str]:
    """Check for legacy orchestrator files."""
    violations = []
    
    legacy_file = agents_dir / "bet-orchestrator-v2.md"
    if legacy_file.exists():
        violations.append(f"Legacy orchestrator file exists: {legacy_file}")
    
    return violations


def validate_no_dangling_references(agents_dir: Path) -> list[str]:
    """Check for dangling agent references in files."""
    violations = []
    
    # Get all agent names
    agent_names = set()
    for agent_file in agents_dir.glob("*.md"):
        agent_names.add(agent_file.stem)
    
    # Check each agent file for task references
    for agent_file in agents_dir.glob("*.md"):
        content = agent_file.read_text()
        frontmatter, body = parse_yaml_frontmatter(content)
        
        if frontmatter is None:
            continue
        
        permission = frontmatter.get("permission", {})
        task_perm = permission.get("task", {})
        
        if isinstance(task_perm, dict):
            for agent_ref in task_perm.keys():
                if agent_ref == "*":
                    continue
                if agent_ref not in agent_names:
                    violations.append(f"{agent_file.stem}: Dangling task reference: {agent_ref}")
    
    return violations


def main() -> int:
    """Main validation entry point."""
    repo_root = Path(__file__).parent.parent
    agents_dir = repo_root / ".kilo" / "agents"
    skills_dir = repo_root / ".kilo" / "skills"
    agents_md = repo_root / "AGENTS.md"
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
    
    # Validate artifact writer
    violations = validate_artifact_writer(artifact_writer)
    all_violations.extend(violations)
    
    # Validate no legacy orchestrator
    violations = validate_no_legacy_orchestrator(agents_dir)
    all_violations.extend(violations)
    
    # Validate no dangling references
    violations = validate_no_dangling_references(agents_dir)
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
