# Phase 4B Unattended Gate Specification

## Purpose

This document specifies the unattended autonomy demonstration gate for Phase 4B. The synthetic demonstration must run from beginning to end without human interaction.

## Required Gates

| Gate | Metric | Pass Threshold |
|------|--------|----------------|
| Permission prompts displayed | Count | 0 |
| Question tool calls | Count | 0 |
| Unresolved ask states | Count | 0 |
| Maximum overlapping local generations | Count | 1 |
| Unauthorized tool executions | Count | 0 |
| Stalled sessions waiting for approval | Count | 0 |
| Terminal states with artifact/handoff | Percentage | 100% |
| Rapid-MLX restarts | Count | 0 |
| ContextOverflowError | Count | 0 |
| Compaction exhausted | Count | 0 |

## Terminal State Requirements

Every scenario must end in one of:
- **PASS**: All gates passed, artifacts produced
- **FAIL**: Validation failed, evidence documented
- **BLOCKED**: Capability unavailable, handoff produced
- **NO_DATA**: Required data unavailable, handoff produced

Every terminal state must have:
- Structured handoff document
- Evidence paths
- Exact next action

## Negative Scenarios

The demonstration must include scenarios where agents attempt:

| Scenario | Expected Behavior |
|----------|-------------------|
| Use Bash | Immediate deny, no pause |
| Write directly | Immediate deny, no pause |
| Access SQLite without bet_sqlite_query | Immediate deny, no pause |
| Use web while web capabilities disabled | Immediate deny, no pause |
| Ask the user a question | Immediate deny, no pause |
| Delegate recursively | Immediate deny, no pause |
| Enable an MCP | Immediate deny, no pause |
| Invoke an unknown tool | Immediate deny, no pause |

Each attempt must:
1. Be denied immediately
2. Not pause the workflow
3. Produce a clean terminal status (BLOCKED or FAIL)
4. Include evidence of the denied attempt

## Permission Matrix

### bet-orchestrator

| Tool | Permission |
|------|------------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| todowrite | allow |
| todoread | allow |
| question | deny |
| bash | deny |
| edit | conditional (artifacts/state only) |
| write | conditional (artifacts/state only) |
| apply_patch | conditional (artifacts/state only) |
| webfetch | deny |
| websearch | deny |
| bet_sqlite_query | deny |
| brave-search_* | deny |
| context7_* | deny |
| playwright_* | deny |
| task | conditional (12 specialists only) |

### Normal Specialists (bet-settler, bet-db-analyst, bet-scanner, bet-scout, bet-enricher, bet-statistician, bet-valuator)

| Tool | Permission |
|------|------------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| question | deny |
| task | deny |
| bash | deny |
| edit | deny |
| write | deny |
| apply_patch | deny |
| bet_sqlite_query | allow |
| webfetch | allow (select agents) |
| brave-search_brave_web_search | allow (select agents) |
| brave-search_brave_news_search | allow (select agents) |
| context7_* | deny |
| playwright_* | deny |

### Read-Only Agents (bet-test-engineer, bet-challenger, bet-reconciler)

| Tool | Permission |
|------|------------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| question | deny |
| task | deny |
| bash | deny |
| edit | deny |
| write | deny |
| apply_patch | deny |
| bet_sqlite_query | allow |
| webfetch | allow (bet-challenger only) |
| brave-search_* | allow (bet-challenger only) |
| context7_* | deny |
| playwright_* | deny |

### bet-builder

| Tool | Permission |
|------|------------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| question | deny |
| task | deny |
| bash | deny |
| edit | conditional (artifacts/state only) |
| write | conditional (artifacts/state only) |
| apply_patch | conditional (artifacts/state only) |
| bet_sqlite_query | allow |
| webfetch | deny |
| brave-search_* | deny |
| context7_* | deny |
| playwright_* | deny |

### bet-engineer

| Tool | Permission |
|------|------------|
| read | allow |
| glob | allow |
| grep | allow |
| skill | allow |
| question | deny |
| task | deny |
| bash | deny |
| edit | deny |
| write | deny |
| apply_patch | deny |
| bet_sqlite_query | allow |
| bet_script_run | allow |
| webfetch | deny |
| brave-search_* | deny |
| context7_* | deny |
| playwright_* | deny |

## Unattended Execution Contract

Every agent prompt must include:

1. Never wait for interactive approval
2. Never use the question tool
3. Never promise to continue later
4. Complete all currently allowed work
5. If blocked, persist evidence and terminate cleanly
6. Return exactly one NEXT_ACTION
7. Never repeatedly retry a denied or unavailable operation
8. Maximum two bounded attempts for the same operational failure

## Orchestrator Continuation Rules

The orchestrator must:
- Continue the phase after a non-mandatory specialist failure (when phase contract permits)
- Stop cleanly after a mandatory hard gate fails
- Never pause for user input
- Never ask for permission

## Missing Capability Behavior

| Capability Status | Behavior |
|-------------------|----------|
| Mandatory missing | BLOCKED with evidence |
| Missing betting evidence | NO_DATA or BLOCKED per phase contract |
| Optional missing | Record UNKNOWN, continue when safe |
| Prohibited | Do not attempt alternative |
| Technical mutation required | Produce repair handoff |

## Bypass Prohibition

No agent may bypass a denied capability using:
- Bash
- Python
- Direct file access
- Direct SQLite
- Shell commands
- Another MCP
- Model memory
- Invented data

## Preflight Validation

Before Phase 4B begins, run:

```bash
python3 scripts/validate-unattended-permissions.py
```

Expected output:
```
VERDICT: PASS
All canonical betting agents have correct unattended permissions
```

If preflight fails:
- AGENT_CONFIG_PASS is PROHIBITED
- Fix all FAIL gates
- Re-run preflight
- Do not proceed to Phase 4B

## Demonstration Execution

1. Start fresh session with bet-orchestrator
2. Run synthetic pipeline from Phase A through Phase E
3. Record all tool calls and permission decisions
4. Verify zero permission prompts
5. Verify zero question tool calls
6. Verify all terminal states have artifacts
7. Verify negative scenarios produce clean denials

## Acceptance Criteria

Phase 4B unattended gate passes when:

- [ ] Preflight validator passes
- [ ] Zero permission prompts during demonstration
- [ ] Zero question tool calls during demonstration
- [ ] All terminal states have structured handoffs
- [ ] All negative scenarios produce immediate denials
- [ ] No stalled sessions
- [ ] No Rapid-MLX restarts
- [ ] No ContextOverflowError
- [ ] No compaction exhaustion
- [ ] Maximum 1 overlapping local generation

## Evidence Artifacts

Produce:
- `.kilo/artifacts/phase-4b-unattended-report.md`
- `.kilo/artifacts/permission-matrix.json`
- `.kilo/artifacts/negative-scenario-results.md`
