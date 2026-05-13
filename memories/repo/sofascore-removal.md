# Sofascore Removal from Active Pipeline

## Date: 2026-05-13

## Status: COMPLETE — Sofascore removed from all active pipeline code, config, docs, agents, prompts, skills, instructions

## Root Cause
- Sofascore API completely blocked by Cloudflare WAF (HTTP 403 on ALL endpoints)
- 4 bypass approaches tested and ALL failed:
  1. Same-domain API (`api.sofascore.com`) → 403
  2. Playwright DOM scraping → only 16 featured matches vs 225 from Flashscore
  3. Cookie transfer from Playwright → 403 (TLS fingerprint check)
  4. cloudscraper → 403
- Conclusion: Sofascore is DEAD as a data source

## What Was Changed

### Code (scripts + src)
- `src/bet/api_clients/unified.py` — FULL REWRITE: removed SofascoreClient import/instance/routing. Now Flashscore→ESPN only
- `src/bet/api_clients/__init__.py` — removed SofascoreClient import and CLIENT_REGISTRY entry
- `scripts/scan_events.py` — 5 edits: comments, default source "flashscore"
- `scripts/data_enrichment_agent.py` — ~320 lines of dead Sofascore code removed (helpers, parsers, fallback chains)
- `scripts/agent_protocol.py` — SELF_HEALING_REGISTRY updated (5 edits)
- `scripts/ingest_scan_stats.py` — 4 edits: docstring, source, fake_url, comments
- `scripts/deep_stats_report.py` — 2 edits: injury verification messages
- `scripts/gemini_web_research.py` — 2 edits: removed from research prompts

### Config
- `config/scan_urls.json` — 9 Sofascore URLs removed from sport sections, shared_sources, and extras
- `betting/sources/source-registry.md` — MAJOR REWRITE: Flashscore promoted to PRIMARY, Sofascore sections ARCHIVED

### Documentation (.github)
- `copilot-instructions.md` — R9 updated
- `instructions/analysis-methodology.instructions.md` — 5 edits
- `instructions/agent-execution-protocol.instructions.md` — 2 edits (UnifiedAPIClient, Playwright Fallback)
- `instructions/sport-analysis-protocols.instructions.md` — 8 edits (all sport stat tables)
- `skills/bet-navigating-sources/SKILL.md` — 5 edits
- `skills/bet-settling-results/SKILL.md` — 2 edits
- `skills/bet-analyzing-statistics/SKILL.md` — 1 edit
- `skills/bet-applying-sport-protocols/references/sport-details.md` — 4 edits

### Agents
- `agents/bet-scanner.agent.md` — description + architecture section rewritten
- `agents/bet-statistician.agent.md` — 4 edits (DB-first workflow, sources, fallback, live data)
- `agents/bet-enricher.agent.md` — 10 edits (description, DB-first, self-healing, source table, parsing section removed)
- `agents/bet-settler.agent.md` — 4 edits (auto-resolve, sources, health check, fallback)
- `agents/bet-orchestrator.agent.md` — 1 edit (routing table)

### Internal Prompts
- `internal-prompts/bet-scan.prompt.md` — 3 edits
- `internal-prompts/bet-enrich.prompt.md` — 3 edits
- `internal-prompts/bet-scan-all.prompt.md` — 2 edits
- `internal-prompts/bet-scan-merge.prompt.md` — 2 edits
- `internal-prompts/bet-settle.prompt.md` — 1 edit
- `internal-prompts/bet-deep-stats.prompt.md` — 1 edit

### User Prompts
- `prompts/scan-day.prompt.md` — 4 edits
- `prompts/ask-betting.prompt.md` — 1 edit
- `prompts/orchestrate-betting-day.prompt.md` — 1 edit

### Memory
- `memories/repo/workflow.md` — updated Tier A stats sources (removed Sofascore)

## What Was KEPT (insurance)
- `src/bet/api_clients/sofascore.py` — client code preserved as dormant insurance
  - Has `_is_sofascore_id()` guards and circuit breaker from previous session
  - NOT imported by any active code
  - Can be re-activated if Sofascore WAF changes

## What Was NOT Changed (intentional)
- `scripts/ingest_scan_stats.py` line 59 `_SOURCE_PATTERNS` has `("sofascore.com", ...)` — parser for historical scan data
- `.github/plans/ai-files-audit.plan.md` — historical documentation, not active pipeline

## New Architecture
- **Primary scan source**: Flashscore (via `FlashscoreClient`)
- **Fallback**: ESPN (via `ESPNClient`)
- **Enrichment chain**: Flashscore → scores24 → ESPN
- **Settlement**: Flashscore → ESPN → Google
