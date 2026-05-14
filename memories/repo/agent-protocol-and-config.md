# Agent Protocol & Configuration — Current State

## Protocol Version: v8 (2026-05-14)

### 21 Rules in copilot-instructions.md (R1-R21)
- R1-R16: Core pipeline rules (unchanged)
- R17: LIVE SCRIPT MONITORING — ALL scripts async + think-while-waiting (no sync exceptions)
- R18: DATA FLOW VERIFICATION — read code before running
- R19: STRUCTURED SCRIPT OUTPUT — AGENT_SUMMARY:{json}
- R20: FISH SHELL — no inline Python, no bash syntax
- R21: PYLANCE-FIRST — pylanceRunCodeSnippet for ALL data inspection

### Agent Organization — copilot-collections pattern (v8, 2026-05-14)
Bet project now mirrors copilot-collections structure exactly:
```
.github/
  agents/           → bet-{role}.agent.md     (10 agents, bet- prefix like tsh-)
  instructions/     → *.instructions.md       (4 files, with applyTo patterns)
  internal-prompts/ → bet-{action}.prompt.md  (15 prompts, agent: frontmatter)
  prompts/          → *.prompt.md             (4 user-facing prompts)
  skills/           → bet-{gerund-subject}/   (8 skills, SKILL.md inside)
  memories/         → (domain extension, not in copilot-collections)
  plans/            → (domain extension, not in copilot-collections)
```

### Tool Declarations — Short Aliases (v8, 2026-05-14)
ALL bet-* agents use short tool aliases (same as tsh-* agents):
```yaml
tools: ["execute", "read", "edit", "search", "agent", "todo",
        "sequential-thinking/*", "pylance-mcp-server/*", "ms-python.python/*",
        "web/fetch", "browser/*", "playwright/*",
        "vscode/memory", "vscode/resolveMemoryFileUri", "vscode/askQuestions",
        "vscode/runCommand", "vscode/toolSearch"]
```
- 9 specialist agents: 17 entries each (was 38 verbose entries)
- bet-orchestrator: 27 entries (was 80+ verbose entries) — includes context7/*, web/github*, vscode/extensions etc.
- Short aliases expand to full tool sets: `execute` = runInTerminal + getTerminalOutput + sendToTerminal + killTerminal + createAndRunTask + runNotebookCell + runTests

### Rule Deduplication — Single Source of Truth (v8, 2026-05-14)
- ⛔ BANNED TERMINAL PATTERNS: REMOVED from all 10 agents (was copy-pasted in each)
- Now lives ONLY in `agent-execution-protocol.instructions.md` (referenced via `instructions:` frontmatter by all agents)
- Per instruction-design-lessons.md: "R17 block was copy-pasted in 11 files → replaced with 1 reference line in each"
- This was partially done in v3 but not completed — v8 finishes the cleanup

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

### Bugs Fixed 2026-05-14 (v7)
- bet-scout, bet-settler, bet-scanner were MISSING `pylance-mcp-server/*` → added
- bet-db-analyst was missing: vscode/askQuestions, vscode/runCommand, web/fetch, browser/*, playwright/*, agent/runSubagent → added
- 8 agents had DUPLICATE sequential-thinking/sequentialthinking → removed duplicates
- Rule count header said "20" but R21 was added → fixed to "21"

### Agent Cleanup 2026-05-14 (v8 — copilot-collections alignment)
- Tool declarations: 38→17 entries per specialist agent, 80→27 for orchestrator
- BANNED TERMINAL PATTERNS: removed from all 10 agents (single source of truth in instructions file)
- Pattern now identical to copilot-collections tsh-* agents

### Per-Agent THINK-WHILE-WAITING Work
| Agent | Long Script | What to do during wait |
|-------|-------------|----------------------|
| bet-scanner | discover_events (120s) or scan_events (600s) | Query DB for source health, check fixture counts |
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
`discover_events.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `build_shortlist.py`, `odds_evaluator.py`, `context_checks.py`, `upset_risk.py`, `fetch_odds_multi.py`, `validate_coupons.py`, `run_scrapers.py`

Exit codes: 0=success, 1=partial/degraded, 2=critical failure.

## Event Discovery Module (2026-05-14) — FULLY INTEGRATED

**Module:** `src/bet/discovery/` — API-first event discovery (no web scraping).
**CLI:** `PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose`
**Sources:** SofaScore (~1500 events) + API-Football (~250) + Odds API (~17 with odds). All 5 sports.
**Speed:** ~30s. `mode=sync, timeout=120000` is fine.
**Output:** DB tables (`fixtures`, `teams`, `competitions`, `scan_results`, `fixture_sources`) + JSON: `{date}_s1_events.json`.
**Tests:** 32 passing in `tests/discovery/`.
**Status:** FULLY INTEGRATED. All orchestrator, agent, prompt, and script files updated. Legacy `scan_events.py` and `beast_mode_pipeline.py` DELETED. No fallback paths.

## Key Design Lesson
When agents fail to follow instructions: make instructions SHORTER, add CONCRETE EXAMPLES, reduce DUPLICATION. Don't add more rules or bold text. Per-agent "YOUR VALUE" statements explain WHY the agent exists.
