#!/usr/bin/env python3
"""Validate execution-spine.md against the actual codebase.

Checks:
1. Every script referenced in the spine exists on disk
2. CLI flags in spine commands match argparse definitions
3. All delegation targets are defined in routing.md
4. DB dependency chain: every PRE requirement has a PRODUCES upstream
5. Step numbering has no gaps
6. PIPELINE_STEPS in agent_protocol.py covers spine steps

Usage:
    PYTHONPATH=src .venv/bin/python3 scripts/validate_spine.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPINE_PATH = ROOT / ".roo" / "rules-bet-orchestrator" / "execution-spine.md"
ROUTING_PATH = ROOT / ".roo" / "rules-bet-orchestrator" / "routing.md"
SCRIPTS_DIR = ROOT / "scripts"

errors = []
warnings = []


def check_script_existence(spine: str):
    """1. Every script referenced must exist."""
    print("\n=== 1. SCRIPT EXISTENCE ===")
    refs = sorted(set(re.findall(r"scripts/([\w_]+\.py)", spine)))
    missing = [s for s in refs if not (SCRIPTS_DIR / s).exists()]
    for s in refs:
        exists = (SCRIPTS_DIR / s).exists()
        print(f"  {'✅' if exists else '❌'}  {s}")
        if not exists:
            errors.append(f"Script missing: scripts/{s}")
    print(f"\n  {len(refs)} scripts referenced, {len(missing)} missing")


def check_cli_flags(spine: str):
    """2. CLI flags must match script argparse definitions."""
    print("\n=== 2. CLI FLAG VALIDATION ===")
    # Extract all commands: script_name + flags
    cmds = re.findall(
        r"\.venv/bin/python3\s+scripts/([\w_]+\.py)\s*(.*?)(?:\s*>|\s*>>|\s*2>&1|\s*$)",
        spine,
        re.MULTILINE,
    )
    issues = []
    for script_name, args_str in cmds:
        path = SCRIPTS_DIR / script_name
        if not path.exists():
            continue
        flags_used = set(re.findall(r"(--[\w-]+)", args_str))
        if not flags_used:
            continue
        code = path.read_text()
        defined = set(re.findall(r'add_argument\(\s*["\'].*?(--[\w-]+)', code))
        # Also match short-form: add_argument("-v", "--verbose", ...)
        defined.update(re.findall(r'add_argument\([^)]*["\']+(--[\w-]+)', code))
        # add_agent_args adds --verbose and --stop-on-error
        if "add_agent_args" in code:
            defined.update({"--verbose", "--stop-on-error"})
        for f in flags_used:
            if f not in defined:
                issues.append(f"  ❌ {script_name}: --{f.lstrip('-')} not in argparse")
                errors.append(f"Unknown flag {f} for {script_name}")

    if issues:
        print("\n".join(issues))
    else:
        print("  ✅ All CLI flags match argparse definitions")


def check_delegation_targets(spine: str):
    """3. All delegation targets must be in routing.md."""
    print("\n=== 3. DELEGATION TARGETS ===")
    if not ROUTING_PATH.exists():
        errors.append("routing.md not found")
        print("  ❌ routing.md not found")
        return

    routing = ROUTING_PATH.read_text()
    defined_agents = set(re.findall(r"\|\s*(bet-[\w-]+)\s*\|", routing))
    spine_delegates = set(re.findall(r"DELEGATE:.*?→\s*(bet-[\w-]+)", spine))

    unrouted = spine_delegates - defined_agents
    if unrouted:
        for a in sorted(unrouted):
            print(f"  ❌ {a} — delegated in spine but NOT defined in routing.md")
            errors.append(f"Unrouted agent: {a}")
    else:
        print(f"  ✅ All {len(spine_delegates)} delegation targets found in routing.md")


def check_dependency_chain(spine: str):
    """4. Every DB requirement in PRE must be produced by an earlier step."""
    print("\n=== 4. DEPENDENCY CHAIN ===")
    steps = re.split(r"^## STEP \d+:", spine, flags=re.MULTILINE)
    step_headers = re.findall(r"^## STEP (\d+): (.+)", spine, re.MULTILINE)

    all_produced = set()
    chain_issues = []

    for i, (num, title) in enumerate(step_headers):
        step_text = steps[i + 1] if i + 1 < len(steps) else ""

        # Extract PRODUCES DB tables (handles comma-separated: "DB: a, b, c")
        produces_section = ""
        if "PRODUCES:" in step_text:
            produces_start = step_text.index("PRODUCES:")
            produces_end = step_text.find("\n\n", produces_start)
            if produces_end == -1:
                produces_end = step_text.find("DELEGATE", produces_start)
            produces_section = step_text[produces_start:produces_end] if produces_end > 0 else step_text[produces_start:]
        # Match "DB: table1, table2, table3" patterns
        db_lines = re.findall(r"DB:\s*(.+?)(?:\s*\(|$)", produces_section, re.MULTILINE)
        produced = set()
        for line in db_lines:
            produced.update(t.strip() for t in re.findall(r"([\w_]+)", line))
        all_produced.update(produced)

        # Extract PRE DB requirements
        pre_section = ""
        if "PRE:" in step_text:
            pre_start = step_text.index("PRE:")
            pre_end = step_text.find("CMD:", pre_start)
            if pre_end == -1:
                pre_end = step_text.find("\n\n", pre_start)
            pre_section = step_text[pre_start:pre_end] if pre_end and pre_end > 0 else step_text[pre_start:]
        required = set(re.findall(r"DB:\s*([\w_]+)\s+has\s*>0", pre_section))

        for r in required:
            if r not in all_produced:
                chain_issues.append(f"  ⚠️  STEP {num} ({title}) requires DB:{r} — no earlier PRODUCES declares it")
                warnings.append(f"STEP {num} requires DB:{r} without explicit producer")

    if chain_issues:
        print("\n".join(chain_issues))
    else:
        print(f"  ✅ All DB requirements have upstream producers")
    print(f"  📋 Tables produced across pipeline: {sorted(all_produced)}")


def check_step_numbering(spine: str):
    """5. Step numbers must be sequential with no gaps."""
    print("\n=== 5. STEP NUMBERING ===")
    step_numbers = [int(n) for n in re.findall(r"^## STEP (\d+):", spine, re.MULTILINE)]
    if not step_numbers:
        errors.append("No steps found in spine")
        print("  ❌ No steps found")
        return

    print(f"  Steps: {step_numbers[0]} through {step_numbers[-1]} ({len(step_numbers)} total)")
    expected = set(range(step_numbers[0], step_numbers[-1] + 1))
    actual = set(step_numbers)
    gaps = sorted(expected - actual)
    dupes = [n for n in step_numbers if step_numbers.count(n) > 1]

    if gaps:
        print(f"  ❌ Missing step numbers: {gaps}")
        errors.append(f"Missing steps: {gaps}")
    if dupes:
        print(f"  ❌ Duplicate step numbers: {set(dupes)}")
        errors.append(f"Duplicate steps: {set(dupes)}")
    if not gaps and not dupes:
        print("  ✅ Sequential, no gaps or duplicates")


def check_protocol_coverage(spine: str):
    """6. PIPELINE_STEPS in agent_protocol.py covers all spine phases."""
    print("\n=== 6. PIPELINE_STEPS COVERAGE ===")
    sys.path.insert(0, str(SCRIPTS_DIR))
    sys.path.insert(0, str(ROOT / "src"))

    try:
        from agent_protocol import PIPELINE_STEPS
    except ImportError as e:
        print(f"  ⚠️  Cannot import agent_protocol: {e}")
        warnings.append(f"agent_protocol import failed: {e}")
        return

    # Extract phase labels from spine (e.g., "S0", "S1", "S2")
    spine_phases = set(re.findall(r"## STEP \d+: (S[\d.]+\w*)", spine))
    protocol_phases = set(PIPELINE_STEPS.keys())

    missing_in_protocol = spine_phases - protocol_phases
    extra_in_protocol = protocol_phases - spine_phases

    if missing_in_protocol:
        for p in sorted(missing_in_protocol):
            print(f"  ⚠️  {p} in spine but NOT in PIPELINE_STEPS")
            warnings.append(f"{p} missing from PIPELINE_STEPS")

    if extra_in_protocol:
        for p in sorted(extra_in_protocol):
            print(f"  ℹ️  {p} in PIPELINE_STEPS but not explicitly in spine (may be sub-phase)")

    covered = spine_phases & protocol_phases
    print(f"  ✅ {len(covered)}/{len(spine_phases)} spine phases have PIPELINE_STEPS entries")


def main():
    if not SPINE_PATH.exists():
        print(f"❌ Execution spine not found: {SPINE_PATH}")
        sys.exit(1)

    spine = SPINE_PATH.read_text()
    print(f"Validating: {SPINE_PATH.relative_to(ROOT)}")
    print(f"{'=' * 60}")

    check_script_existence(spine)
    check_cli_flags(spine)
    check_delegation_targets(spine)
    check_dependency_chain(spine)
    check_step_numbering(spine)
    check_protocol_coverage(spine)

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {len(errors)} errors, {len(warnings)} warnings")
    if errors:
        print("\n❌ ERRORS (must fix):")
        for e in errors:
            print(f"   • {e}")
    if warnings:
        print("\n⚠️  WARNINGS (review):")
        for w in warnings:
            print(f"   • {w}")

    if not errors and not warnings:
        print("\n🎯 Execution spine is VALID — orchestrator has complete step coverage.")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
