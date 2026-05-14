# Session 2026-05-13 (evening): Agent Protocol v6 + Code Bug Fixes

## What Was Done

### 1. Agent Execution Protocol v5→v6
Core problem: agents ran scripts SYNCHRONOUSLY, blocked for 5-10 min, produced zero original analysis.

**Fix — 6-Step Cycle:**
- Step 0 INSPECT: use `pylanceRunCodeSnippet` to verify input data BEFORE running script
- Step 1 RUN: always `mode=async` for scripts >120s
- Step 2 THINK: `sequentialthinking` while script runs
- Step 3 ANALYZE: parse `AGENT_SUMMARY`, extract metrics
- Step 4 VALIDATE: use `pylanceRunCodeSnippet` to verify output data
- Step 5 VERDICT: cite specific numbers, original insight

**Tool Selection Matrix added:**
- `pylanceRunCodeSnippet` = PRIMARY for data inspection (DB queries, JSON reads, file checks)
- `run_in_terminal mode=sync` = scripts <120s
- `run_in_terminal mode=async` = scripts >120s (THINK-WHILE-WAITING)

### 2. Files Modified (10 agent/prompt files)
- `agent-execution-protocol.instructions.md` — v6: 6-step cycle, tool matrix, anti-patterns 17→20
- `orchestrate-betting-day.prompt.md` — INSPECT column in async blocks, 4-question quality gate
- `bet-orchestrator.agent.md` — updated rules table for R17/R18 with pylanceRunCodeSnippet
- 7 internal prompts — each got Step 0 INSPECT + async enforcement:
  - `bet-enrich.prompt.md`: check shortlist + team_form baseline
  - `bet-deep-stats.prompt.md`: check team_form + shortlist
  - `bet-tipsters.prompt.md`: check tipster consensus format + shortlist
  - `bet-gate.prompt.md`: check S3 + odds files
  - `bet-odds-ev.prompt.md`: check S3 data + odds
  - `bet-context-upset.prompt.md`: check weather + standings + team_news
  - `bet-portfolio.prompt.md`: check gate results + bankroll config

### 3. Code Bug Fixes (2 scripts)

**Bug 1 CRITICAL — Scores24 URL (data_enrichment_agent.py):**
- `removeprefix("s24-")` on href external_ids produced double-path URLs
- Fix: if `external_id.startswith('/')` → use directly; if `s24-` prefix → skip (not a valid URL)

**Bug 2 MEDIUM — Playwright browser leak (fetch_odds_multi.py):**
- OddsPortalSource and other Playwright sources never had `close()` called
- Fix: added cleanup loop after scan — `hasattr(source, 'close')` → `source.close()`

**Bug 3 MINOR — isinstance(row, dict) checks (data_enrichment_agent.py):**
- sqlite3.Row is NOT a dict but supports dict-like access
- Cleaned up 3 occurrences to use `row["external_id"]` directly

## Key Insight
When agents fail to follow instructions: make instructions SHORTER, add CONCRETE EXAMPLES, reduce DUPLICATION. Don't add more rules or bold text.
