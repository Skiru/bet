# Agent Python Tool Integration — 2026-05-11

## What Changed
- All 15 `bet-*` agent definitions now include 4 `ms-python.python/*` tools:
  - `ms-python.python/configurePythonEnvironment` — activate .venv
  - `ms-python.python/getPythonExecutableCommand` — get proper Python path
  - `ms-python.python/getPythonEnvironmentInfo` — check env details
  - `ms-python.python/installPythonPackage` — install missing deps
- `agent-execution-protocol.instructions.md` v5 updated:
  - Boot sequence step 0: configure Python env
  - New `🐍 Python Environment Setup` section before 4-Step Cycle
  - "Set up Python env" row in ALWAYS DO INSTEAD table

## Tool ID Format (from tsh-engineering-manager.agent.md)
- `ms-python.python/{toolName}` — this is the correct namespace
- NOT `python/configurePythonEnvironment` (wrong)

## Agents Updated (all 15)
bet-orchestrator, bet-scanner, bet-scanner-{football,tennis,basketball,volleyball,hockey},
bet-enricher, bet-statistician, bet-scout, bet-valuator, bet-challenger, bet-builder,
bet-settler, bet-db-analyst

## MCP Sequential Thinking
- Already present in all 15 agents as both `sequentialthinking/sequentialthinking` AND `sequential-thinking/sequentialthinking`
- No changes needed — both namespace variants already covered

## Async + Live Monitoring
- Already well-defined in execution protocol v5 (4-Step Cycle, THINK-WHILE-WAITING pattern)
- Per-agent productive async work table already exists
- No changes needed — protocol already covers this comprehensively
