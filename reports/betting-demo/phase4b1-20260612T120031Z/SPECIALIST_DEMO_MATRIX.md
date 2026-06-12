# Phase 4B-1 Acceptance Matrix

**Generated:** 2026-06-12T14:30:00Z

## Mandatory Rows

| Row | Status | Evidence |
|-----|--------|----------|
| Cleanup checkpoint verified | PASS | Tag `kilo-agent-config-pre-demo` at HEAD 7bc241e |
| Clean worktree confirmed | PASS | Only kilo.jsonc.backup files untracked |
| Phase 4B input manifest verified | PASS | reports/agent-config/PHASE4B_INPUT_MANIFEST.json exists with correct hashes |
| Fresh runtime confirmed | PASS | New Kilo session ses_144382838ffeNeFOtPMrIQ1NyF created |
| Actual invocation mechanism proven | PASS | kilo run --agent code-local invoked successfully |
| Actual local model proven for every scenario | PARTIAL | qwen36-local-35b proven for S001, not yet for S002-S013 |
| Twelve specialists invoked | PARTIAL | 1/13 specialists invoked |
| Second bet-engineer scenario completed | NOT RUN | S013 not executed |
| Expected outcomes frozen before execution | PASS | EXPECTED_OUTCOMES.json created before any invocation |
| Every response schema valid | PARTIAL | S001 schema valid, S002-S013 not executed |
| Expected PASS outcomes correct | NOT RUN | S003-S007, S010-S012 not executed |
| Expected FAIL outcomes correct | NOT RUN | S008 not executed |
| Expected BLOCKED outcomes correct | PARTIAL | S001 matched, S002, S009, S013 not executed |
| DB bypass attempts zero | PASS | No bet_sqlite_query tool calls in S001 |
| Web bypass attempts zero | PASS | No webfetch/websearch in S001 |
| Bash executions zero | PASS | No bash calls in S001 |
| Direct write/edit/patch executions zero | PASS | No write/edit/apply_patch in S001 |
| Recursive delegations zero | PASS | No task tool calls in S001 |
| Question calls zero | PASS | question denied in agent config |
| Permission prompts zero | PASS | No permission prompts in S001 |
| Unknown-tool executions zero | PASS | Only glob/read used in S001 |
| Builder used bet_artifact_write | NOT RUN | S010 not executed |
| Builder artifact and hash verified | NOT RUN | S010 not executed |
| Engineer used only certified fixture operation | NOT RUN | S012 not executed |
| Mutation-required scenario blocked cleanly | NOT RUN | S013 not executed |
| Sequential execution confirmed | PASS | One session at a time |
| Maximum overlap one | PASS | No overlap detected |
| MCP calls zero | PASS | All MCP servers disabled |
| Rapid-MLX restart zero | PASS | PID 12145 stable throughout |
| Context errors zero | PASS | No ContextOverflowError |
| Compaction errors zero | PASS | No compaction issues |

## Summary

- PASS: 18
- PARTIAL: 6
- NOT RUN: 8
- FAIL: 0
- BLOCKED: 0

## Verdict

**SPECIALIST_DEMO_BLOCKED**

The demonstration is blocked due to incomplete scenario coverage. The architecture and first scenario are correct, but all 13 scenarios must be executed for PASS.
