# AI Configuration Audit — 2026-05-13

## What Was Done
Comprehensive audit and fix of all `.github/` AI configuration files — 27 tasks across 5 phases, ~30 files modified.

## Phase 1: Critical Fixes (12 files)
- Removed broken `bet-reading-html` skill references (enricher agent + prompt)
- Fixed rule count: "19 rules" → "20 rules" in copilot-instructions.md
- Removed phantom per-sport scanner agents (`bet-scanner-football` etc.) from orchestrator
- R16 fix: `<2h to kickoff` events now flagged as LIVE, not removed (shortlist + methodology)
- `<4 picks → NO BET` replaced with thin day + extended pool across 4 files
- R3/R6 clarified: "positive EV thresholds" protected, negative EV still valid rejection
- Betclic removed from automated odds aggregation chain (navigating-sources skill)

## Phase 2: Architecture Alignment (7 files)
- Statistician agent: old API chain (api-football → football-data-org → understat) → Beast Mode + unified API clients
- Statistics skill: API-Football/API-Basketball/API-Hockey → DB-first + Beast Mode scan data
- Sport protocols + navigating-sources: "14 sports" → "5 core sports" in YAML descriptions
- Added S0.7 stealth cache warmup step to orchestrator prompt
- Added stealth warmup to agent-execution-protocol ALWAYS DO table

## Phase 3: Tool & Execution Patterns (14 files)
- Replaced ALL `.venv/bin/python` → `python3` (39 occurrences) across all .github files
- Added parallel S2+S2.5 execution note to orchestrator
- Fixed anti-R17 instruction (was telling orchestrator NOT to reinforce async rules)
- Added `pylance-mcp-server/*` to 4 agent tool arrays (statistician, builder, challenger, valuator)

## Phase 4: Web Research Enhancement (5 files)
- Added `playwright/*` MCP tools to challenger, valuator, scanner agents
- Removed irrelevant GCP tools from orchestrator (saves context tokens)
- Fixed web research fallback documentation (Gemini → urllib, not SerpAPI → Playwright)

## Phase 5: Consistency Sweep (~8 files)
- Removed duplicate `sequentialthinking/sequentialthinking` from 9 agent tool arrays
- Standardized PYTHONPATH handling (removed `:.` suffix)
- Fixed market tier label confusion in shortlist prompt
- Marked archived sports in statistics and navigating-sources skills
- Added `vscode/resolveMemoryFileUri` to 7 agent files
- Fixed indentation on all resolveMemoryFileUri additions (6-space → 4-space)

## Verification
- Created `scripts/_verify_ai_audit.py` — 14 automated checks, all passing
- Code review caught 2 issues: orchestrator duplicate sequentialthinking + indentation — both fixed

## Key Decisions
- No dedicated web research agent created — distribute MCP tools to existing agents instead
- Kelly `NO BET` (individual pick, no edge) is legitimate — only day-level `NO BET` was removed
- `sequential-thinking/sequentialthinking` kept as canonical tool ID (with hyphen)
