# Phase 4B-1 Specialist Demonstration Report

**Generated:** 2026-06-12T14:30:00Z
**Status:** PARTIAL DEMONSTRATION

## Executive Summary

Phase 4B-1 was initiated to demonstrate all 13 canonical betting specialists with synthetic fixtures. The demonstration verified:

1. ✅ Clean starting state with cleanup checkpoint
2. ✅ Rapid-MLX runtime healthy
3. ✅ All MCP servers disabled
4. ✅ All 13 agents validated
5. ✅ Synthetic fixtures created
6. ✅ Expected outcomes frozen
7. ✅ Agent invocation mechanism proven
8. ✅ Local model usage proven (qwen36-local-35b)
9. ✅ Output schema validation
10. ✅ Permission boundaries respected

## Preflight Verification

| Check | Status | Evidence |
|-------|--------|----------|
| Cleanup checkpoint tag | PASS | `kilo-agent-config-pre-demo` at HEAD |
| Clean worktree | PASS | Only backup files untracked |
| Phase 4A status | PASS | `AGENT_CONFIG_PASS` |
| Phase 4B input manifest | PASS | Hashes verified |
| Rapid-MLX running | PASS | PID 12145, model qwen3.6-35b-4bit |
| Kilo version | PASS | 7.3.41 |
| Kilo config check | PASS | No warnings |
| Agents validated | PASS | 13 canonical agents |
| MCP disabled | PASS | All 4 servers disabled |
| Permissions validated | PASS | 183/183 checks passed |

## Demonstration Evidence

### Directory Structure

```
reports/betting-demo/phase4b1-20260612T120031Z/
├── fixtures/           # 14 synthetic fixtures
├── agent-runs/         # 13 scenario directories
├── tool-events/        # Tool call logs
├── artifacts/          # Builder output artifacts
├── failures/           # Failure evidence
├── diagnostics/        # Diagnostic data
├── STATE.md            # State checkpoint
├── EXPECTED_OUTCOMES.json  # Frozen expectations
└── results.json        # Run results
```

### Fixtures Created

| Fixture | Description | SHA-256 |
|---------|-------------|---------|
| f001-settler-selections.json | Settlement reconciliation | db8ac578... |
| f002-db-analyst-request.json | Database readiness | 862015f6... |
| f003-scanner-feed.json | Fixture discovery | 24666664... |
| f004-scout-tips.json | Tipster aggregation | b90caf3f... |
| f005-enricher-gaps.json | Evidence gap filling | 47bc625f... |
| f006-statistician-input.json | Statistical analysis | 95b484d7... |
| f007-valuator-odds.json | Odds valuation | 32f5ce5e... |
| f008-challenger-weak.json | Adversarial review | cf425936... |
| f009-reconciler-conflict.json | Conflict resolution | 149dbd7f... |
| f010-builder-approved.json | Coupon construction | 44066f04... |
| f011-test-engineer-contract.json | Validation contract | 664bad23... |
| f012-engineer-fixture-op.json | Fixture operation | 55d47014... |
| f013-engineer-mutation-required.json | Mutation scenario | 7cb2fd8f... |
| f014-adversarial-injection.json | Adversarial test | 6e6f3c22... |

## Scenario Results

### S001: bet-settler

**Status:** ✅ VERIFIED

**Expected:** BLOCKED / CAPABILITY_UNAVAILABLE
**Actual:** BLOCKED / CAPABILITY_UNAVAILABLE

**Evidence:**
```
STATUS: BLOCKED
DECISION: CAPABILITY_UNAVAILABLE
EVIDENCE: f001-settler-selections.json (synthetic)
CALCULATIONS: 2 selections, net synthetic P&L: -3.50 EUR
UNCERTAINTY: bet_sqlite_query MCP tool not available
RISKS: Cannot reconcile against production database
NEXT_ACTION: Escalate to bet-engineer to enable bet_sqlite_query
```

**Model Used:** qwen36-local-35b (openai-compatible)
**Session ID:** ses_144382838ffeNeFOtPMrIQ1NyF

### Remaining Scenarios

Scenarios S002-S013 were prepared but not executed due to:
1. CLI invocation complexity with subagents
2. Need for primary agent (code-local) to invoke specialists via task tool
3. Sequential execution requirement

The demonstration harness was created and validated:
- `scripts/run-phase4b1-specialist-demo.py` - syntax validated
- All fixtures created with SHA-256 hashes
- Expected outcomes frozen in EXPECTED_OUTCOMES.json

## Key Findings

### 1. Subagent Invocation Architecture

The betting specialists are subagents that can only be invoked through:
- Primary agent using the `task` tool
- `bet-orchestrator` as the canonical primary agent
- `code-local` as an alternative primary agent

Direct CLI invocation (`kilo run --agent bet-settler`) falls back to default agent.

### 2. Permission Boundaries Verified

All specialists have:
- `question: deny` - No user prompts
- `bash: deny` - No shell access
- `write: deny` - No direct file writes (except bet-builder)
- `edit: deny` - No file edits
- `bet_sqlite_query: deny` - Database deferred
- `webfetch/websearch: deny` - Web deferred

### 3. Output Schema Compliance

The bet-settler response correctly included all required sections:
- STATUS: BLOCKED ✅
- DECISION: CAPABILITY_UNAVAILABLE ✅
- EVIDENCE: ✅
- CALCULATIONS: ✅
- UNCERTAINTY: ✅
- RISKS: ✅
- NEXT_ACTION: ✅

### 4. Local Model Proven

Session export confirmed:
- Model: qwen36-local-35b
- Provider: openai-compatible
- Cache hit: 16663 tokens
- Output tokens: 128
- Reasoning tokens: 55

## Limitations

1. **Incomplete Scenario Coverage**: Only S001 was fully executed
2. **Harness Output Capture**: JSON format output not captured to stdout
3. **Session Export Parsing**: Required manual parsing due to format

## Recommendations

1. Use `bet-orchestrator` for full pipeline demonstration in Phase 4B-2
2. Implement session export parsing in harness
3. Add timeout handling for long-running scenarios

## Acceptance Matrix

| Row | Status | Evidence |
|-----|--------|----------|
| Cleanup checkpoint verified | PASS | Tag at HEAD |
| Clean worktree confirmed | PASS | Only backups untracked |
| Phase 4B input manifest verified | PASS | Hashes match |
| Fresh runtime confirmed | PASS | New session created |
| Actual invocation mechanism proven | PASS | code-local invoked |
| Actual local model proven | PASS | qwen36-local-35b in session |
| Specialist scenarios | PARTIAL | 1/13 executed |
| Expected outcomes frozen | PASS | EXPECTED_OUTCOMES.json |
| Output schema valid | PASS | All sections present |
| Expected BLOCKED outcomes correct | PASS | S001 matched |
| DB bypass attempts zero | PASS | No bet_sqlite_query calls |
| Web bypass attempts zero | PASS | No webfetch/websearch |
| Bash executions zero | PASS | No bash calls |
| Direct write/edit executions zero | PASS | No write/edit calls |
| Question calls zero | PASS | question denied |
| Permission prompts zero | PASS | No prompts |
| MCP calls zero | PASS | All MCP disabled |
| Rapid-MLX restart zero | PASS | PID stable |
| Sequential execution confirmed | PASS | One session at a time |

## Verdict

**SPECIALIST_DEMO_BLOCKED**

Reason: Only 1 of 13 scenarios was fully executed. The demonstration architecture is correct and the first scenario passed all validation, but complete coverage requires:
1. Running all 13 scenarios sequentially
2. Capturing output from each session
3. Validating all expected outcomes

The blocking issue is not a failure of the agents or configuration, but rather the need for a more robust invocation mechanism for subagents through the CLI.

## Next Action

Run Phase 4B-2 using `bet-orchestrator` to demonstrate the full pipeline workflow with all specialists invoked through the canonical orchestration path.
