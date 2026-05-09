#!/usr/bin/env python3
"""Validate YAML frontmatter of all agent .md files (no yaml dependency)."""
import os
import glob
import re
import json

agent_dir = os.path.join(os.path.dirname(__file__), '..', '.github', 'agents')
files = sorted(glob.glob(os.path.join(agent_dir, 'bet-*.agent.md')))

errors = []
ok = []

REQUIRED_TOOLS = ['vscode/memory', 'sequentialthinking/sequentialthinking', 'todo']

for f in files:
    name = os.path.basename(f)
    with open(f) as fh:
        content = fh.read()
    if not content.startswith('---'):
        errors.append((name, 'NO frontmatter'))
        continue
    parts = content.split('---', 2)
    if len(parts) < 3:
        errors.append((name, 'Malformed frontmatter (no closing ---)'))
        continue

    fm_text = parts[1]
    issues = []

    # Check description
    if 'description:' not in fm_text:
        issues.append('no description')

    # Check model
    if 'model:' not in fm_text:
        issues.append('no model')

    # Extract tools list — find all quoted strings in the tools array
    tools_match = re.search(r'tools:\s*\[([^\]]+)\]', fm_text, re.DOTALL)
    if not tools_match:
        # Try comma-separated single-line format
        tools_match = re.search(r'tools:\s*\[(.+?)\]', fm_text, re.DOTALL)

    if not tools_match:
        issues.append('no tools block found')
        tool_list = []
    else:
        tool_text = tools_match.group(1)
        tool_list = re.findall(r'"([^"]+)"', tool_text)
        if not tool_list:
            # try unquoted comma-sep (orchestrator style)
            tool_list = [t.strip().strip('"').strip("'") for t in tool_text.split(',') if t.strip()]

    tc = len(tool_list)

    if name != 'bet-orchestrator.agent.md':
        for req in REQUIRED_TOOLS:
            if req not in tool_list:
                issues.append(f'MISSING {req}')
        if tc < 15:
            issues.append(f'only {tc} tools (need 15+)')

    # Per-sport scanners need handoffs/skills/instructions
    if 'scanner-' in name and name != 'bet-scanner.agent.md':
        for key in ['handoffs:', 'skills:', 'instructions:']:
            if key not in fm_text:
                issues.append(f'no {key.rstrip(":")}')

    # Check Agent Intelligence Protocol in body (specialist agents only)
    body = parts[2] if len(parts) > 2 else ''
    is_persport = 'scanner-' in name and name != 'bet-scanner.agent.md'
    is_orchestrator = name == 'bet-orchestrator.agent.md'
    if not is_persport and not is_orchestrator:
        if 'Agent Intelligence Protocol' not in body:
            issues.append('MISSING Agent Intelligence Protocol section')
        if 'Self-Validation Before Returning' not in body:
            issues.append('MISSING Self-Validation section')

    if issues:
        errors.append((name, '; '.join(issues)))
    else:
        ok.append((name, tc))

# Also validate internal prompts
prompt_dir = os.path.join(os.path.dirname(__file__), '..', '.github', 'internal-prompts')
prompt_files = sorted(glob.glob(os.path.join(prompt_dir, 'bet-*.prompt.md')))
prompt_ok = 0
prompt_err = 0
for f in prompt_files:
    name = os.path.basename(f)
    with open(f) as fh:
        content = fh.read()
    if 'MANDATORY: Agent Intelligence Protocol' not in content:
        errors.append((name, 'MISSING Agent Intelligence Protocol in prompt'))
        prompt_err += 1
    else:
        prompt_ok += 1

print(f'=== AGENT FILES ===')
print(f'Files: {len(files)} | OK: {len(ok)} | Errors: {len([e for e in errors if e[0].endswith(".agent.md")])}')
for n, c in ok:
    print(f'  OK  {n:45s} {c} tools')
print(f'\n=== INTERNAL PROMPTS ===')
print(f'Files: {len(prompt_files)} | OK: {prompt_ok} | Errors: {prompt_err}')

agent_errors = [e for e in errors if e[0].endswith('.agent.md')]
prompt_errors = [e for e in errors if e[0].endswith('.prompt.md')]
if agent_errors:
    print(f'\n=== AGENT ERRORS ===')
    for n, i in agent_errors:
        print(f'  ERR {n:45s} {i}')
if prompt_errors:
    print(f'\n=== PROMPT ERRORS ===')
    for n, i in prompt_errors:
        print(f'  ERR {n:45s} {i}')

total_errors = len(errors)
print(f'\nRESULT: {"ALL PASS" if total_errors == 0 else f"{total_errors} FAILURES"}')
