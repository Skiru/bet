# AI Configuration Files Audit — Implementation Plan

**Created:** 2026-05-13
**Status:** PENDING
**Audit scope:** `.github/` — agents, prompts, internal-prompts, skills, instructions
**Total files to touch:** ~30 across 5 phases
**Approach:** Each phase is self-contained. Complete Phase 1 before Phase 2, etc.

---

## Phase 1: Critical Fixes (Broken References + Policy Contradictions)

> Fix things that cause actual failures or incorrect agent behavior.
> **Files touched: 12**

### Task 1.1: Remove `bet-reading-html` skill references [MODIFY × 2]

**Why:** `bet-reading-html` skill does not exist. Agents that reference it will fail skill loading or waste time searching.

- **File:** `.github/agents/bet-enricher.agent.md` (line ~85)
  - **Change:** Remove `bet-reading-html` from the Skills Usage Guidelines section. Replace the description with a direct reference to checking `{date}_deep_parse_report.json` for pre-extracted HTML data (which is what the non-existent skill was supposed to provide).
  - **Definition of Done:** No reference to `bet-reading-html` in the file. The enricher still knows to check deep parse reports before triggering web fetches.

- **File:** `.github/internal-prompts/bet-enrich.prompt.md` (line ~41)
  - **Change:** Remove `bet-reading-html` from the "Required Skills" section. Add a note under existing skills to check `{date}_deep_parse_report.json` before web fetching.
  - **Definition of Done:** No reference to `bet-reading-html` in the file.

### Task 1.2: Fix rule count in copilot-instructions.md [MODIFY × 1]

**Why:** Says "These 19 rules" but defines R1–R20. Misleading for agents counting rules.

- **File:** `.github/copilot-instructions.md` (line 62)
  - **Change:** Replace `These 19 rules` with `These 20 rules`.
  - **Definition of Done:** Rule count matches actual rules defined (R1–R20).

### Task 1.3: Fix non-existent per-sport scanner agent references [MODIFY × 1]

**Why:** The adapter overhaul table in the orchestrator references `bet-scanner-football`, `bet-scanner-tennis`, `bet-scanner-basketball`, `bet-scanner-volleyball`, `bet-scanner-hockey` — none of these exist. Only `bet-scanner.agent.md` exists.

- **File:** `.github/prompts/orchestrate-betting-day.prompt.md` (lines ~74–78, the ADAPTER OVERHAUL table)
  - **Change:** Replace sport-specific agent names in the "Agent Impact" column with the actual agent names: `bet-scanner` (for scan review), `bet-statistician` (for deep analysis), `bet-enricher` (for data gaps). Example: `| Hockey | MoneyPuck = PRIMARY... | bet-scanner, bet-statistician |`
  - **Definition of Done:** No references to `bet-scanner-football`, `bet-scanner-tennis`, `bet-scanner-basketball`, `bet-scanner-volleyball`, or `bet-scanner-hockey` anywhere in the file.

### Task 1.4: Fix R16 (live betting) violation — remove "<2h to kickoff" filter [MODIFY × 2]

**Why:** R16 says events in progress or about to start are VALID targets. Removing events <2h to kickoff violates this rule.

- **File:** `.github/internal-prompts/bet-shortlist.prompt.md` (line ~68)
  - **Change:** Remove `3. <2h to kickoff` and `4. Already started` from the removal criteria list. Add a note: "Events <2h to kickoff or in progress → flag as LIVE but do NOT remove (R16)." Renumber remaining criteria.
  - **Definition of Done:** No removal of events based on proximity to kickoff. LIVE flag added instead.

- **File:** `.github/instructions/analysis-methodology.instructions.md` (line ~414)
  - **Change:** Remove `<2h to kickoff, already started` from the "Remove:" line. Add: "Flag <2h to kickoff or in-progress as LIVE (R16) — do NOT remove."
  - **Definition of Done:** Consistent with R16.

### Task 1.5: Fix "<4 approved picks → NO BET" to align with extended pool philosophy [MODIFY × 4]

**Why:** The core + combo menu + extended pool philosophy means the user ALWAYS gets picks to choose from. "<4 picks → NO BET" contradicts this — the extended pool exists precisely for thin days. The user decides.

- **File:** `.github/skills/bet-building-coupons/SKILL.md` (line 16)
  - **Change:** Replace rule 4: `<4 approved picks → NO BET` with: `<4 approved picks → present as singles + extended pool with advisory. Flag thin day. User decides.`
  - **Definition of Done:** No automatic NO BET declaration based on pick count alone.

- **File:** `.github/agents/bet-builder.agent.md` (line ~79, ~128, ~155)
  - **Change:** Replace all `<4 approved picks = declare NO BET` references with: `<4 approved picks → flag thin day, present singles + extended pool. User decides.`
  - **Definition of Done:** Builder never auto-declares NO BET. User always gets options.

- **File:** `.github/internal-prompts/bet-portfolio.prompt.md` (line ~100)
  - **Change:** Replace `If <4 picks → NO BET day` with: `If <4 picks → flag thin day, present available picks as singles + extended pool. User decides.`
  - **Definition of Done:** Consistent with extended pool philosophy.

- **File:** `.github/instructions/analysis-methodology.instructions.md` (line ~927)
  - **Change:** Replace `<4 approved picks → NO BET` with: `<4 approved picks → thin day flag. Present as singles + extended pool.`
  - **Definition of Done:** Consistent across all files.

### Task 1.6: Clarify R3/R6 interaction on negative EV [MODIFY × 1]

**Why:** R3 says "NEVER auto-rejects events based on EV" but R6 says "negative EV" is a valid auto-rejection. These read as contradictory. The intent is clear (negative EV = math says no edge = valid rejection; positive EV events should never be rejected based on magnitude) but the wording needs alignment.

- **File:** `.github/copilot-instructions.md` (line ~68, R3)
  - **Change:** Add parenthetical to R3: "The pipeline NEVER auto-rejects events based on ~~EV,~~ safety scores, historical hit rates, or any other metric **(except negative EV per R6 — math says no edge)**."
  - **Definition of Done:** R3 and R6 no longer contradict. Negative EV rejection is explicitly allowed.

### Task 1.7: Fix Betclic in multi-source odds aggregation reference [MODIFY × 1]

**Why:** `bet-navigating-sources/SKILL.md` line 143 says `fetch_odds_multi.py` "Aggregates 5 sources: The-Odds-API + API-Football + OddsPortal + BetExplorer + Betclic". Betclic is 403 and cannot be scraped. If the script actually tries this, it fails silently.

- **File:** `.github/skills/bet-navigating-sources/SKILL.md` (line ~143)
  - **Change:** Remove `+ Betclic` from the aggregation list. Add note: "Betclic odds are NEVER scraped (403). User verifies on app (R12)."
  - **Definition of Done:** No suggestion that Betclic is part of automated odds aggregation.

**Phase 1 Checklist:**
- [ ] 1.1: Remove `bet-reading-html` from bet-enricher.agent.md and bet-enrich.prompt.md
- [ ] 1.2: Fix "19 rules" → "20 rules" in copilot-instructions.md
- [ ] 1.3: Fix per-sport scanner agent names in orchestrate-betting-day.prompt.md
- [ ] 1.4: Fix R16 violation in bet-shortlist.prompt.md and analysis-methodology.instructions.md
- [ ] 1.5: Fix "<4 picks → NO BET" in 4 files
- [ ] 1.6: Clarify R3/R6 interaction in copilot-instructions.md
- [ ] 1.7: Fix Betclic in bet-navigating-sources/SKILL.md

---

## Phase 2: Architecture Alignment (Stale References + Beast Mode Awareness)

> Update all files to reflect current pipeline architecture: Beast Mode scan, DB-first, unified API clients, stealth Playwright, 5 core sports.
> **Files touched: 7**

### Task 2.1: Fix stale API chain in bet-statistician.agent.md [MODIFY × 1]

**Why:** Line ~73 describes old API chain: "Use the 5-sport API client chain (api-football → football-data-org → understat → Playwright, etc.)". The current architecture uses: Beast Mode scan (Sofascore REST API) → DB-first (`team_form` table) → unified API clients (`src/bet/api_clients/`) → stealth Playwright fallback.

- **File:** `.github/agents/bet-statistician.agent.md` (line ~73)
  - **Change:** Replace the DB-first workflow paragraph. New text should describe:
    1. DB-first: check `team_form`, `match_stats`, `analysis_results` tables via `db_data_loader.py`
    2. Beast Mode scan data: `global_events_api.json` already has form/H2H/odds from Sofascore API
    3. Stats cache fallback: `stats_cache/{sport}/{team}.json`
    4. Unified API clients: `src/bet/api_clients/` (sofascore, flashscore, espn, basketball_reference, moneypuck, etc.)
    5. Stealth Playwright: when API endpoints return 403, stealth browser renders page
    6. Remove references to api-football, football-data-org, understat chains
  - **Definition of Done:** No references to old API chain. Architecture matches current codebase.

### Task 2.2: Fix stale references in bet-analyzing-statistics/SKILL.md [MODIFY × 1]

**Why:** §3.0 step 9 references "API-first data" with `analysis_pool_{date}.json` for "pre-computed rankings from API-Football/API-Basketball/API-Hockey stats". These API services are no longer the primary data source.

- **File:** `.github/skills/bet-analyzing-statistics/SKILL.md` (line ~75, step 9)
  - **Change:** Replace step 9 to reference:
    - DB-first: check `analysis_results` table for existing safety scores
    - Beast Mode data: `global_events_api.json` + `stats_cache/` from Sofascore REST API scan
    - Remove "API-Football/API-Basketball/API-Hockey" references
    - Note: `analysis_pool_{date}.json` still used as aggregated view but is built from DB + scan data, not external API subscriptions
  - **Definition of Done:** No references to old paid API services. Data flow matches current architecture.

### Task 2.3: Fix 14-sport model in bet-applying-sport-protocols/SKILL.md [MODIFY × 1]

**Why:** Description says "all 14 betting sports" and body has Tier 1 (4 sports) / Tier 2 (10 sports). Current architecture has 5 core Tier 1 sports (Football, Volleyball, Basketball, Tennis, Hockey) with no active Tier 2.

- **File:** `.github/skills/bet-applying-sport-protocols/SKILL.md`
  - **Change:**
    1. Update YAML description: "all 14 betting sports" → "all 5 core betting sports (football, volleyball, basketball, tennis, hockey) plus archived protocols for additional sports"
    2. Update Sport Tiers table: Make all 5 core sports Tier 1 (add Hockey to KEY tier). Mark remaining sports as ARCHIVED with note: "Protocols retained for reference. Not actively scanned."
    3. Keep the market hierarchies table intact (all 14 sports) as reference — just mark non-core sports as archived
  - **Definition of Done:** Tier table matches 5-sport reality. Description accurate. Archived sports clearly marked.

### Task 2.4: Fix 14-sport reference in bet-navigating-sources/SKILL.md [MODIFY × 1]

**Why:** Description says "14 supported sports". Current pipeline supports 5 core sports.

- **File:** `.github/skills/bet-navigating-sources/SKILL.md`
  - **Change:**
    1. Update YAML description: "14 supported sports" → "5 core sports (football, volleyball, basketball, tennis, hockey) plus source chains for additional sports"
    2. Body text already correctly says "all 5 core sports" — just fix the description
  - **Definition of Done:** Description matches body content and current architecture.

### Task 2.5: Clean archived pipeline-v4 sections in sport-analysis-protocols.instructions.md [MODIFY × 1]

**Why:** File has ~10 sections marked "ARCHIVED (removed from pipeline v4)" (Esports §3.6, Snooker §3.7, Darts §3.8, Handball §3.9, Table Tennis §3.10, MMA §3.11, Baseball §3.12, Padel §3.13, Speedway §3.14, plus archived upset risk sections). These waste context window tokens when loaded.

- **File:** `.github/instructions/sport-analysis-protocols.instructions.md`
  - **Change:**
    1. Replace each archived section with a single line: `### §3.X [Sport] — ARCHIVED → see references/sport-details.md`
    2. If a `references/sport-details.md` file exists in the skill, move full archived content there. If not, create it.
    3. Keep the 5 core sport sections (Football §3.1, Tennis §3.2, Basketball §3.3, Volleyball §3.4, Hockey §3.5) in full
    4. Collapse archived upset risk sections similarly
  - **Definition of Done:** Archived sections reduced to one-line pointers. Core sport protocols remain complete. File is significantly shorter (saves context tokens).

### Task 2.6: Add Beast Mode + stealth + html_cache awareness to agent layer [MODIFY × 2]

**Why:** No prompt or instruction mentions `daily_odds_warmup.py` (S0.1 stealth warm-up), `stealth_fetcher.py`, or the `html_cache/` directory. Agents don't know these exist.

- **File:** `.github/prompts/orchestrate-betting-day.prompt.md` (STEP S0 section, after settlement)
  - **Change:** Add optional S0.1 step for stealth cache warmup:
    ```
    ### STEP S0.1: Stealth Cache Warmup (optional — run if odds data stale)
    python3 scripts/daily_odds_warmup.py --date {date} --verbose 2>&1
    # Warms html_cache/ with odds pages via stealth Playwright
    # Downstream scripts (odds_evaluator, deep_stats_report) read from cache
    ```
  - **Definition of Done:** Orchestrator knows about stealth warmup step.

- **File:** `.github/instructions/agent-execution-protocol.instructions.md` (✅ ALWAYS DO INSTEAD table)
  - **Change:** Add row: `| Warm up odds cache | python3 scripts/daily_odds_warmup.py --date YYYY-MM-DD |`
  - **Definition of Done:** Protocol file documents the stealth warmup as an available tool.

**Phase 2 Checklist:**
- [ ] 2.1: Fix stale API chain in bet-statistician.agent.md
- [ ] 2.2: Fix stale API references in bet-analyzing-statistics/SKILL.md
- [ ] 2.3: Fix 14-sport model in bet-applying-sport-protocols/SKILL.md
- [ ] 2.4: Fix 14-sport description in bet-navigating-sources/SKILL.md
- [ ] 2.5: Clean archived sections in sport-analysis-protocols.instructions.md
- [ ] 2.6: Add Beast Mode + stealth awareness to orchestrator + protocol

---

## Phase 3: Tool & Execution Patterns (Python Tools, Async, MCP)

> Ensure all agents use proper Python tool setup, async patterns, and have appropriate MCP tools.
> **Files touched: 14**

### Task 3.1: Add Python tool usage note to internal prompts [MODIFY × ~10]

**Why:** All agents have `ms-python.python/*` tools in their `tools:` array, and the agent-execution-protocol.instructions.md §Python Environment Setup section describes the process. But internal prompts still hardcode `.venv/bin/python` and `PYTHONPATH=src python3` commands, bypassing the tool-based approach.

The protocol already tells agents to use `ms-python.python/configurePythonEnvironment` once per session then use the returned executable. The fix is to update hardcoded commands in internal prompts to use `python3` (the protocol handles env setup at boot).

- **Files (all in `.github/internal-prompts/`):**
  - `bet-scan.prompt.md` — lines 30, 42, 45, 48, 56, 57: change `.venv/bin/python` → `python3`
  - `bet-enrich.prompt.md` — any `.venv/bin/python` or bare `python3` with `PYTHONPATH=src` prefix
  - `bet-deep-stats.prompt.md` — check and standardize
  - `bet-odds-ev.prompt.md` — check and standardize
  - `bet-context-upset.prompt.md` — lines 70, 76: already use `PYTHONPATH=src python3`
  - `bet-gate.prompt.md` — line 66: already uses `PYTHONPATH=src python3`
  - `bet-validate.prompt.md` — line 63: already uses `PYTHONPATH=src python3`
  - `bet-portfolio.prompt.md` — check and standardize
  - `bet-tipsters.prompt.md` — check and standardize
  - `bet-shortlist.prompt.md` — check and standardize

  **Change for each file:** Replace all `.venv/bin/python scripts/` with `python3 scripts/` (the protocol's boot sequence handles `ms-python.python/configurePythonEnvironment`). Keep `PYTHONPATH=src` prefix where needed (for scripts that import from `src/bet/`). Add one-line note at top of each prompt's script section: `# Python env configured via ms-python.python tools at boot (see agent-execution-protocol.instructions.md)`

- **Also update:** `.github/prompts/orchestrate-betting-day.prompt.md` — multiple instances of `.venv/bin/python` in S0, S1, S1-ingest, S1a, S1b, S1c, S1d, S1e sections.

- **Definition of Done:** No `.venv/bin/python` anywhere in `.github/` files. All use `python3` and rely on the protocol boot sequence for env setup.

### Task 3.2: Fix anti-parallel instruction in orchestrator [MODIFY × 1]

**Why:** Per user memory (`parallel-agent-execution.md`), S2 (tipster xref) and S2.5 (enrichment) are INDEPENDENT and should run in parallel via separate `runSubagent` calls. The current orchestrator runs them sequentially (S2 first, then S2.5).

- **File:** `.github/prompts/orchestrate-betting-day.prompt.md` (S2 and S2.5 sections)
  - **Change:** Merge S2 and S2.5 into a single "STEP S2+S2.5: Tipster Intelligence + Data Enrichment (PARALLEL)" section. Instructions:
    ```
    # Launch BOTH in parallel — they are INDEPENDENT (no data dependency)
    1. runSubagent("bet-scout") — S2 tipster cross-reference
    2. runSubagent("bet-enricher") — S2.5 data enrichment
    # Both read from shortlist. Neither depends on the other.
    # Collect both verdicts, then merge insights before S3.
    ```
  - **Definition of Done:** Orchestrator explicitly instructs parallel execution of S2 and S2.5.

### Task 3.3: Add R17 enforcement instruction for subagent delegations [MODIFY × 1]

**Why:** Per user memory (`parallel-agent-execution.md` §R17 VIOLATION LOG), subagents run scripts SYNC instead of ASYNC. The orchestrator needs to include R17 guidance in delegation messages.

Note: The orchestrator currently says "Do not repeat these rules in delegation messages" (line ~146 of orchestrate-betting-day.prompt.md). This conflicts with the established rule that R17 MUST be enforced on subagents. The protocol file (loaded via agents' `instructions:` array) covers R17, but agents still violate it in practice.

- **File:** `.github/prompts/orchestrate-betting-day.prompt.md` (§TERMINAL EXECUTION RULES section, line ~146)
  - **Change:** Replace "Do not repeat these rules in delegation messages" with: "The protocol file covers terminal rules via agents' `instructions:` array. For scripts ≥300s, ADD to delegation: `Use mode=async, timeout={appropriate}. THINK-WHILE-WAITING: [specific analysis task]. Then get_terminal_output.` This is the ONE exception — R17 async patterns MUST be reinforced in delegation messages for long-running scripts."
  - **Definition of Done:** Orchestrator reinforces R17 for long scripts without duplicating the full protocol.

### Task 3.4: Add `pylance-mcp-server/*` to agents that modify Python code [MODIFY × 4]

**Why:** Only bet-enricher and bet-db-analyst have `pylance-mcp-server/*`. Other agents that run Python scripts and may need to diagnose import errors, check syntax, or understand module structure should also have these tools.

- **Files:** Add `pylance-mcp-server/*` to the `tools:` array of:
  - `.github/agents/bet-statistician.agent.md` — runs `deep_stats_report.py`, may need to diagnose import issues
  - `.github/agents/bet-builder.agent.md` — runs `coupon_builder.py`
  - `.github/agents/bet-challenger.agent.md` — runs `gate_checker.py`, `context_checks.py`, `upset_risk.py`
  - `.github/agents/bet-valuator.agent.md` — runs `odds_evaluator.py`
  - (bet-scanner, bet-scout, bet-settler already have sufficient tools or are less likely to debug Python)
  - **Definition of Done:** All agents that run analytical Python scripts have `pylance-mcp-server/*` in their tools array.

**Phase 3 Checklist:**
- [ ] 3.1: Standardize Python commands across ~10 internal prompts + orchestrator
- [ ] 3.2: Add parallel S2+S2.5 execution to orchestrator
- [ ] 3.3: Fix R17 enforcement instruction in orchestrator
- [ ] 3.4: Add pylance-mcp-server/* to 4 agent files

---

## Phase 4: Web Research Enhancement

> Improve web research capabilities and tool distribution.
> **Files touched: 5**

### Task 4.1: Assess web research agent need — DECISION REQUIRED

**Context:** Currently `web_research_agent.py` claims a Gemini → SerpAPI → Playwright fallback ladder, but SerpAPI client isn't fully implemented and "Playwright" fallback uses urllib in practice. No dedicated agent exists for web research — it's triggered by the orchestrator as L7 last resort. The orchestrator has `browser/*`, `playwright/*`, `web/fetch`, `context7/*` MCP tools available.

**Decision:** Do NOT create a dedicated web research agent. Instead:
1. Fix the existing script's documentation to match reality
2. Add `web/fetch` and `playwright/*` MCP tools to specialist agents that need live web data
3. The orchestrator already has the tools and can run `web_research_agent.py` or `gemini_web_research.py` directly

**Rationale:** Web research is a FALLBACK (L7), not a primary pipeline step. Creating a dedicated agent adds complexity for rare usage. Better to ensure existing agents can fetch web data when needed.

### Task 4.2: Add web research MCP tools to key specialist agents [MODIFY × 3]

**Why:** bet-scout (tipster sites), bet-enricher (data gap filling), and bet-challenger (live context verification) all need web access. bet-scout and bet-enricher already have `browser/*` and `playwright/*`. bet-challenger has `browser/*` but not `playwright/*`.

- **File:** `.github/agents/bet-challenger.agent.md`
  - **Change:** Add `playwright/*` to the `tools:` array (already has `browser/*` and `web/fetch`).
  - **Definition of Done:** bet-challenger can use Playwright MCP for live lineup/injury verification.

- **File:** `.github/agents/bet-valuator.agent.md`
  - **Change:** Add `playwright/*` to the `tools:` array. Valuator may need to check live odds pages.
  - **Definition of Done:** bet-valuator can use Playwright MCP for odds verification.

- **File:** `.github/agents/bet-scanner.agent.md`
  - **Change:** Add `playwright/*` to the `tools:` array (already has `browser/*` but not `playwright/*`). Scanner reviews scan output and may need to verify fixtures.
  - **Definition of Done:** bet-scanner has Playwright MCP available.

### Task 4.3: Remove irrelevant MCP tools from orchestrator [MODIFY × 1]

**Why:** The orchestrator has GCP tools (`gcp-gcloud/*`, `gcp-observability/*`, `gcp-storage/*`) that appear irrelevant to the betting pipeline. These consume context window tokens.

- **File:** `.github/agents/bet-orchestrator.agent.md`
  - **Change:** Remove all `gcp-gcloud/*`, `gcp-observability/*`, `gcp-storage/*` tool entries from the `tools:` array. These can be re-added if GCP integration is implemented.
  - **Definition of Done:** Orchestrator tool list contains only actively used tools. GCP tools removed.

### Task 4.4: Document web research fallback in orchestrator [MODIFY × 1]

**Why:** The orchestrator mentions `web_research_agent.py` and `gemini_web_research.py` but doesn't explain the current fallback reality (Gemini Search Grounding is primary, urllib is actual "Playwright" fallback, SerpAPI is placeholder).

- **File:** `.github/prompts/orchestrate-betting-day.prompt.md` (wherever `web_research_agent.py` is mentioned)
  - **Change:** Add a note clarifying the actual web research stack:
    ```
    Web research fallback chain (R15):
    L7a: gemini_web_research.py — Gemini Search Grounding (primary, most reliable)
    L7b: web_research_agent.py — urllib-based web fetch (fallback)
    L7c: MCP tools — browser/*, playwright/* for interactive page rendering
    Note: SerpAPI client exists but API key not configured. urllib is used, not Playwright headless.
    ```
  - **Definition of Done:** Documentation matches actual web research capabilities.

**Phase 4 Checklist:**
- [ ] 4.1: Decision documented (no dedicated web research agent)
- [ ] 4.2: Add playwright/* to challenger, valuator, scanner agents
- [ ] 4.3: Remove GCP tools from orchestrator
- [ ] 4.4: Document web research fallback chain in orchestrator

---

## Phase 5: Consistency Sweep (Minor Fixes, Dead Code, Token Savings)

> Clean up remaining inconsistencies and optimize token usage.
> **Files touched: 6**

### Task 5.1: Remove duplicate `sequentialthinking` entries from agent tool arrays [MODIFY × 8]

**Why:** Most agents list both `sequentialthinking/sequentialthinking` AND `sequential-thinking/sequentialthinking` — sometimes twice. This doesn't cause failures but wastes YAML space and is confusing.

- **Files:** All `.github/agents/bet-*.agent.md` files
  - **Change:** Keep only one entry: `sequential-thinking/sequentialthinking` (the canonical tool ID). Remove duplicate `sequentialthinking/sequentialthinking` entries.
  - **Definition of Done:** Each agent has exactly one sequential thinking tool entry.

### Task 5.2: Standardize PYTHONPATH handling in agent files [MODIFY × 6]

**Why:** Some agent files use `PYTHONPATH=src python3`, others use `PYTHONPATH=src:.`, and some use neither. The inconsistency causes confusion.

- **Files:** Agent files with `PYTHONPATH=src:.` references:
  - `bet-scout.agent.md` (line ~211)
  - `bet-statistician.agent.md` (line ~146, ~417)
  - `bet-settler.agent.md` (line ~186)
  - `bet-valuator.agent.md` (line ~219)
  - `bet-builder.agent.md` (line ~253)
  - `bet-challenger.agent.md` (line ~271)
  - `bet-enricher.agent.md` (line ~257)
  - **Change:** Standardize all `PYTHONPATH=src:.` → `PYTHONPATH=src` (the `:.` adds current directory which is already in Python path by default). These appear in "ModuleNotFoundError" recovery instructions.
  - **Definition of Done:** Consistent `PYTHONPATH=src` across all agents.

### Task 5.3: Fix stale Tier 1/Tier 2 reference in bet-shortlist.prompt.md [MODIFY × 1]

**Why:** Line ~98 says "Sections: Summary, Removal Log, Tier 1 (statistical markets), Tier 2 (ML/basic), Major Tournaments." This uses Tier 1/Tier 2 to mean market tiers, not sport tiers — but it's confusing since sport protocols also use Tier 1/Tier 2. Clarify.

- **File:** `.github/internal-prompts/bet-shortlist.prompt.md` (line ~98)
  - **Change:** Replace "Tier 1 (statistical markets), Tier 2 (ML/basic)" with "Statistical Markets (preferred), Outcome Markets (fallback)" to avoid confusion with sport tiers.
  - **Definition of Done:** No ambiguous Tier 1/Tier 2 references in shortlist prompt.

### Task 5.4: Clean bet-analyzing-statistics/SKILL.md bettable markets table [MODIFY × 1]

**Why:** §3.0b lists 14 sports in the bettable markets table. The non-core sports (Baseball through Speedway) should be marked as archived but retained for reference since the probability engine might still support them.

- **File:** `.github/skills/bet-analyzing-statistics/SKILL.md` (§3.0b table)
  - **Change:** Add "*(archived)*" suffix to non-core sport rows: Baseball, Snooker, Darts, Handball, Esports, Table Tennis, MMA, Padel, Speedway. Keep the data — just mark it clearly.
  - **Definition of Done:** Non-core sports marked as archived. Core 5 sports clearly primary.

### Task 5.5: Ensure bet-navigating-sources/SKILL.md source tables match reality [MODIFY × 1]

**Why:** Market Sources and Stats Sources tables list chains for 14 sports. Non-core sport chains should be marked as archived.

- **File:** `.github/skills/bet-navigating-sources/SKILL.md` (Market Sources table)
  - **Change:** Add "*(archived)*" suffix to non-core sport rows in both Market Sources and Stats Sources tables. Update any stale source references (NaturalStatTrick should note "BLOCKED 403, use MoneyPuck" per adapter overhaul).
  - **Definition of Done:** Source tables reflect current reality. MoneyPuck as primary hockey stats. Non-core sports marked.

### Task 5.6: Add `vscode/resolveMemoryFileUri` to agents missing it [MODIFY × ~6]

**Why:** bet-enricher and bet-db-analyst have `vscode/resolveMemoryFileUri` but other agents that read/write memory files don't. This is minor but agents that write to `/memories/session/` should have the tool.

- **Files:** Add `vscode/resolveMemoryFileUri` to agents that write session memory:
  - `bet-statistician.agent.md`
  - `bet-scanner.agent.md`
  - `bet-builder.agent.md`
  - `bet-challenger.agent.md`
  - `bet-valuator.agent.md`
  - `bet-scout.agent.md`
  - **Definition of Done:** All agents that reference `/memories/` have the memory URI resolution tool.

**Phase 5 Checklist:**
- [ ] 5.1: Remove duplicate sequentialthinking entries from all agents
- [ ] 5.2: Standardize PYTHONPATH across agent files
- [ ] 5.3: Fix Tier 1/Tier 2 market label confusion in shortlist prompt
- [ ] 5.4: Mark archived sports in bet-analyzing-statistics/SKILL.md
- [ ] 5.5: Update source tables in bet-navigating-sources/SKILL.md
- [ ] 5.6: Add memory URI tool to agents missing it

---

## Summary

| Phase | Tasks | Files | Priority |
|-------|-------|-------|----------|
| 1 — Critical Fixes | 7 | 12 | CRITICAL — do first |
| 2 — Architecture Alignment | 6 | 7 | HIGH — stale info causes wrong decisions |
| 3 — Tool & Execution Patterns | 4 | 14 | HIGH — improves execution reliability |
| 4 — Web Research Enhancement | 4 | 5 | MEDIUM — improves data coverage |
| 5 — Consistency Sweep | 6 | ~8 (some overlap) | LOW — polish and token savings |

**Total unique files touched:** ~30
**Estimated task count:** 27

### Verification After Each Phase

After completing each phase, run this verification:
1. `grep -r "bet-reading-html" .github/` — should return 0 (after Phase 1)
2. `grep -r "19 rules" .github/` — should return 0 (after Phase 1)
3. `grep -r "bet-scanner-football" .github/` — should return 0 (after Phase 1)
4. `grep -r "api-football.*football-data-org" .github/` — should return 0 (after Phase 2)
5. `grep -r "14 betting sports\|14 supported sports" .github/` — should return 0 (after Phase 2)
6. `grep -r ".venv/bin/python" .github/` — should return 0 (after Phase 3)
7. `grep -r "gcp-gcloud\|gcp-observability\|gcp-storage" .github/agents/` — should match only if re-added intentionally (after Phase 4)
