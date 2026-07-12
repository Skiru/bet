# TOOL VALIDATION PROMPT — Bet Orchestrator Smoke Test

@bet-orchestrator

Run a **comprehensive tool smoke test** to prove every tool in your permission profile is available and functional. Execute each test in order and report PASS/FAIL per tool.

## 1. MCP Connectivity Check

Before testing individual tools, confirm all MCP servers are connected:

- **sequentialthinking_sequentialthinking**: Call it once with the hypothesis "This is a smoke test."
- **sqlite_read_query**: Run `SELECT COUNT(*) as test FROM fixtures;`
- **brave-search_brave_web_search**: Search for `Premier League fixtures today` (count=3)

If ANY of these three returns "not connected" or timeout → **STOP immediately**. Return `verdict: FAILED_AUDIT`, list which MCP is down, and do not proceed.

## 2. Built-in Tool Checklist

Execute each and report result:

- **read**: Read the first 5 lines of `.kilocode/memory/session-state.md`. If it does not exist, read `AGENTS.md` instead.
- **glob**: Find all `bet-*.md` files in `.kilo/prompts/`.
- **grep**: Search for `verdict:` in `.kilo/prompts/bet-scanner.md`.
- **edit**: Write a 3-line checkpoint to `.kilocode/memory/session-state.md` (create if missing; `write` is acceptable only if the file does not yet exist):
  ```
  ## Smoke Test Checkpoint
  Date: 2026-06-05
  Status: TOOLS_VERIFIED
  ```
- **bash**: Run `echo "Fish shell OK"` and capture output.
- **task**: Delegate a **minimal** task to `bet-db-analyst`: ask it to run one `sqlite_read_query` and return whether it succeeded. Do NOT ask it to do full analysis.
- **webfetch**: Fetch `https://example.com` and confirm the title contains "Example Domain".

## 3. Permission Boundary Check

Verify these are correctly **blocked** by attempting to explain whether you can use them (do NOT actually run them):

- **sqlite_write_query**: Are you allowed? (Expected: NO / denied)
- **sqlite_create_table**: Are you allowed? (Expected: NO / denied)
- **playwright_***: Are you allowed? (Expected: NO / denied)

## 4. Task Delegation Matrix

Confirm `task` works for ALL 12 specialist agents by delegating a **minimal ping** to each (one `task` call with multiple agents is fine). Each agent should simply return `PONG` if their prompt loaded:

- bet-settler, bet-db-analyst, bet-scanner, bet-enricher
- bet-scout, bet-statistician, bet-valuator, bet-challenger
- bet-builder, bet-engineer, bet-reconciler, bet-test-engineer

If any agent fails to respond or throws "agent not found" → report it.

## Output Format

```
## Tool Smoke Test Verdict
verdict: ALL_PASS | PARTIAL | FAILED

| Tool | Status | Detail |
|------|--------|--------|
| sequentialthinking_sequentialthinking | PASS/FAIL | <one-line result> |
| sqlite_read_query | PASS/FAIL | <row count or error> |
| brave-search_brave_web_search | PASS/FAIL | <HTTP status or result count> |
| read | PASS/FAIL | <file read> |
| glob | PASS/FAIL | <files found> |
| grep | PASS/FAIL | <matches found> |
| edit | PASS/FAIL | <file written? Y/N> |
| bash | PASS/FAIL | <output or error> |
| task | PASS/FAIL | <delegated agents that responded> |
| webfetch | PASS/FAIL | <page title or error> |
| sqlite_write_query | BLOCKED | <correctly denied> |
| sqlite_create_table | BLOCKED | <correctly denied> |
| playwright_* | BLOCKED | <correctly denied> |

### Delegation Matrix
| Agent | PONG | Error |

### Critical Failures
- <list any tool that failed or was unexpectedly allowed>

### Next Action
- If ALL_PASS: "Toolchain ready for full pipeline run."
- If PARTIAL: "Fix [tool] before running pipeline."
- If FAILED: "Restart Kilo / check MCP / fix config before proceeding."
```

Begin now.
