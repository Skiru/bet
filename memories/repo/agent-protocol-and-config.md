# Agent Protocol & Configuration — Current State

## Protocol Version: v7 (2026-05-14)

### 21 Rules in copilot-instructions.md (R1-R21)
- R1-R16: Core pipeline rules (unchanged)
- R17: LIVE SCRIPT MONITORING — async for >120s, think-while-waiting
- R18: DATA FLOW VERIFICATION — read code before running
- R19: STRUCTURED SCRIPT OUTPUT — AGENT_SUMMARY:{json}
- R20: FISH SHELL — no inline Python, no bash syntax
- R21: PYLANCE-FIRST — pylanceRunCodeSnippet for ALL data inspection (NEW 2026-05-14)

### Streamlined copilot-instructions.md (2026-05-14)
- R13/R17/R18/R19/R20 compressed to 1-2 lines + protocol reference
- Core Rules section de-duplicated (was repeating R3/R4/R6)
- ~120 lines → ~100 lines

### 6-Step Cycle (per pipeline step)
1. **INSPECT**: Use `pylanceRunCodeSnippet` to verify input data BEFORE running script
2. **RUN**: ALWAYS `mode=async` — no sync exceptions, not even for short scripts
3. **THINK**: `sequentialthinking` while script runs (analyze previous step data)
4. **ANALYZE**: Parse `AGENT_SUMMARY:{json}` line, extract metrics
5. **VALIDATE**: Use `pylanceRunCodeSnippet` to verify output data
6. **ACT**: If issues found → FIX before proceeding. Then return verdict.

### Tool Selection
- `pylanceRunCodeSnippet` = PRIMARY for data inspection (DB queries, JSON reads)
- `run_in_terminal mode=async` = ALL pipeline scripts (no sync mode, no exceptions)
- Agent ALWAYS thinks while waiting — even short scripts give time to review data

### ALL 10 Agents — Mandatory Tool Set (2026-05-14)
Every bet-*.agent.md MUST have ALL of these tools (34 total):
- `vscode/memory`, `vscode/resolveMemoryFileUri`, `vscode/askQuestions`, `vscode/runCommand`, `vscode/toolSearch`
- `execute/runInTerminal`, `execute/getTerminalOutput`, `execute/sendToTerminal`, `execute/killTerminal`
- `read/readFile`, `read/problems`, `read/terminalLastCommand`, `read/terminalSelection`, `read/viewImage`, `read/getNotebookSummary`
- `edit/editFiles`, `edit/createFile`
- `search/textSearch`, `search/fileSearch`, `search/listDirectory`, `search/codebase`, `search/changes`, `search/usages`
- `web/fetch`, `browser/*`, `playwright/*`
- `agent/runSubagent`
- `sequential-thinking/sequentialthinking` (EXACTLY ONCE — no duplicates!)
- `pylance-mcp-server/*`
- `ms-python.python/configurePythonEnvironment`, `getPythonExecutableCommand`, `getPythonEnvironmentInfo`, `installPythonPackage`
- `todo`

### Bugs Fixed 2026-05-14
- bet-scout, bet-settler, bet-scanner were MISSING `pylance-mcp-server/*` → added
- bet-db-analyst was missing: vscode/askQuestions, vscode/runCommand, web/fetch, browser/*, playwright/*, agent/runSubagent → added
- bet-scanner was missing browser/* → added
- bet-settler, bet-builder were missing playwright/* → added
- 7 agents (all except orchestrator, scanner, db-analyst) were missing agent/runSubagent → added
- 8 agents had DUPLICATE sequential-thinking/sequentialthinking → removed duplicates
- 9 agents missing: read/viewImage, read/terminalSelection, read/getNotebookSummary → added
- 9 agents missing: search/usages → added. 8 agents missing: search/changes → added
- 8 agents missing: vscode/runCommand → added
- Rule count header said "20" but R21 was added → fixed to "21"
- R17/R21 async threshold removed — ALL scripts now async, no exceptions

### Per-Agent THINK-WHILE-WAITING Work
| Agent | Long Script | What to do during wait |
|-------|-------------|----------------------|
| bet-scanner | scan_events (600s) | Query DB for source health, check fixture counts |
| bet-enricher | data_enrichment_agent (600s) | Read shortlist, check team form data |
| bet-statistician | deep_stats_report (600s) | Review enrichment quality, pre-load sport protocols |
| bet-challenger | context/upset/gate (300s each) | Review deep stats, draft bear cases |
| bet-valuator | odds_evaluator (300s) | Read S3 stats, pre-load safety scores |
| bet-scout | tipster_aggregator (300s) | Read scan results, check pre-fetched HTML |
| bet-builder | coupon_builder (300s) | Review gate results, check bankroll config |
| bet-settler | settle_on_finish (300s) | Read coupon files, review Betclic history |

## Python Tool IDs for Agents
All 10 agents include: `ms-python.python/*` (configure, executable, info, install).

## MCP Tools Present
- `sequential-thinking/sequentialthinking` — ALL 10 agents
- `pylance-mcp-server/*` — ALL 10 agents (fixed 2026-05-14: was missing from scout, settler, scanner)

## AI Config Audit Summary (2026-05-14)
- 27 tasks across 5 phases, ~30 files modified
- All `.venv/bin/python` → `python3` (39 occurrences)
- Removed broken skill references, phantom agent references
- Standardized PYTHONPATH handling
- Added `playwright/*` MCP tools to challenger, valuator, scanner
- Removed duplicate `sequentialthinking` from 9 agent tool arrays
- All verified via `scripts/_verify_ai_audit.py` (14 checks passing)

## Structured Script Output Protocol
15 scripts support `--verbose` + `AGENT_SUMMARY:{json}`:
`scan_events.py`, `html_deep_parser.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `build_shortlist.py`, `odds_evaluator.py`, `context_checks.py`, `upset_risk.py`, `fetch_odds_multi.py`, `validate_coupons.py`

Exit codes: 0=success, 1=partial/degraded, 2=critical failure.

## Key Design Lesson
When agents fail to follow instructions: make instructions SHORTER, add CONCRETE EXAMPLES, reduce DUPLICATION. Don't add more rules or bold text. Per-agent "YOUR VALUE" statements explain WHY the agent exists.
