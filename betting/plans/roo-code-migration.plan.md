# Migration Plan: GitHub Copilot → Roo Code + Continue.dev + LM Studio

**Created:** 2026-05-27  
**Deadline:** 2026-06-01  
**Status:** DRAFT  
**Hardware:** MacBook Pro M4 Pro, 48GB RAM, macOS  

---

## Table of Contents

1. [Technical Context](#1-technical-context)
2. [Architecture Mapping](#2-architecture-mapping)
3. [Condensation Strategy](#3-condensation-strategy)
4. [Phase 1: Foundation](#phase-1-foundation)
5. [Phase 2: Core Modes](#phase-2-core-modes)
6. [Phase 3: Remaining Modes](#phase-3-remaining-modes)
7. [Phase 4: Continue.dev Setup](#phase-4-continuedev-setup)
8. [Phase 5: Testing & Validation](#phase-5-testing--validation)
9. [Phase 6: Cleanup](#phase-6-cleanup)
10. [Risk Register](#10-risk-register)

---

## 1. Technical Context

### 1.1 Roo Code `.roomodes` JSON Schema

File location: `PROJECT_ROOT/.roomodes`

```json
{
  "customModes": [
    {
      "slug": "string (kebab-case, unique identifier)",
      "name": "string (display name in mode picker)",
      "roleDefinition": "string (system prompt — WHO the agent is, max ~80 lines for Gemma)",
      "whenToUse": "string (routing hint for orchestrator — WHEN to delegate here)",
      "customInstructions": "string (always-on rules for this mode — merged instructions+skills)",
      "groups": ["read", "edit", "browser", "command", "mcp"]
    }
  ]
}
```

**Tool groups available (5 total):**
- `read` — file reading, directory listing, search
- `edit` — file creation, modification, deletion
- `browser` — web browsing, page interaction
- `command` — terminal command execution
- `mcp` — all MCP server tools (sqlite, brave-search, sequential-thinking)

**Notes:**
- No per-tool granularity; you grant entire groups.
- All modes get `read` implicitly. Specify only additional groups.
- `roleDefinition` + `customInstructions` together form the full system prompt for a mode.

### 1.2 `.clinerules` Format

File location: `PROJECT_ROOT/.clinerules`

Plain markdown file. Always-on rules injected into EVERY mode's context. Equivalent to `copilot-instructions.md`. Should be concise — everything here costs context in every interaction.

### 1.3 `.roo/` Directory Structure

```
PROJECT_ROOT/.roo/
  mcp.json              — MCP server config (identical format to .vscode/mcp.json)
  rules/                — Per-mode rule files: {mode-slug}.md
  rules-orchestrator/   — Rules only for orchestrator mode
  rules-bet-statistician/ — Rules only for bet-statistician mode (etc.)
  memory-bank/          — Persistent memory files (markdown)
```

**Per-mode rules:** Files in `.roo/rules-{slug}/` are loaded ONLY when that mode is active. This is the overflow mechanism when `customInstructions` is too long. Roo loads all `.md` files in the matching directory.

**Global rules:** Files in `.roo/rules/` are loaded for ALL modes (equivalent to .clinerules extensions). Use sparingly — costs context everywhere.

### 1.4 Boomerang Orchestration Mechanics

**Built-in Orchestrator mode:**
- Spawns sub-tasks using `new_task` tool
- Each sub-task runs in a specified mode (slug)
- Sub-task receives: task description + any context payload
- Sub-task completes → returns result text to orchestrator
- Orchestrator processes result → decides next step

**`new_task` tool signature:**
```
new_task(mode: string, message: string)
```

**`whenToUse` field:** The orchestrator reads this to decide which mode handles a sub-task. Write it as a clear conditional: "When the pipeline needs deep statistical analysis of S3/S3B output."

**`attempt_completion` tool:** Each mode calls this when done, returning its verdict to the orchestrator.

**Key difference from Copilot `runSubagent`:**
- No structured handoff payload format — just a text message
- The orchestrator must include all needed context in the message
- Sub-task has NO access to orchestrator's conversation history
- Mode switching is explicit — no automatic routing

### 1.5 Continue.dev Configuration

File location: `~/.continue/config.json` (global) or `PROJECT_ROOT/.continuerc.json` (project-level)

```json
{
  "models": [
    {
      "title": "Gemma 4 31B (Local)",
      "provider": "openai",
      "model": "gemma-4-31b",
      "apiBase": "http://localhost:1234/v1",
      "apiKey": "lm-studio"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen 2.5 Coder 7B",
    "provider": "openai",
    "model": "qwen2.5-coder-7b-instruct",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "lm-studio"
  },
  "tabAutocompleteOptions": {
    "debounceDelay": 500,
    "maxPromptTokens": 2048
  }
}
```

**Notes:**
- Continue.dev handles ONLY autocomplete (tab completion while typing).
- Roo Code handles ALL agentic work (chat, tool use, orchestration).
- Both connect to LM Studio via OpenAI-compatible API on `localhost:1234`.
- LM Studio must have BOTH models loaded (Gemma 31B + Qwen 7B). With 48GB RAM this is tight — may need to swap models or use Qwen 3B instead.

### 1.6 LM Studio Configuration

**Models to load:**
- `gemma-4-31b-it-Q4_K_M.gguf` — main agentic model (Roo Code chat + orchestration)
- `qwen2.5-coder-7b-instruct-Q4_K_M.gguf` — autocomplete model (Continue.dev tab)

**Server settings:**
- Port: 1234 (default)
- Context length: 32768 tokens for Gemma, 8192 for Qwen
- GPU offload: full (M4 Pro unified memory)
- Concurrent requests: enable (both extensions hit same server)

**RAM budget (48GB total):**
- Gemma 31B Q4_K_M: ~20GB VRAM
- Qwen 7B Q4_K_M: ~5GB VRAM
- macOS + apps: ~8GB
- Remaining: ~15GB for context/KV cache

---

## 2. Architecture Mapping

### 2.1 Copilot → Roo Code Mapping Table

| Copilot Concept | Roo Code Equivalent | Location |
|-----------------|---------------------|----------|
| `copilot-instructions.md` | `.clinerules` | project root |
| 10 × `agent.md` | 10 modes in `.roomodes` | project root |
| `instructions/*.md` (always-on per-agent) | Per-mode `customInstructions` + `.roo/rules-{slug}/` overflow | inline + `.roo/rules-{slug}/` |
| `skills/bet-*/SKILL.md` (progressive load) | Condensed into `customInstructions` or `.roo/rules-{slug}/` | inline or `.roo/` |
| `prompts/*.prompt.md` (entry points) | User types mode name + request. `whenToUse` guides routing. | `.roomodes` |
| `internal-prompts/*.prompt.md` (handoffs) | Part of orchestrator's `customInstructions` as routing table | `.roomodes` |
| `runSubagent` | `new_task(mode, message)` | built-in |
| `.vscode/mcp.json` | `.roo/mcp.json` | `.roo/` |
| Repo memory (`/memories/repo/`) | `.roo/memory-bank/` | `.roo/` |
| Session memory (`/memories/session/`) | Conversation context (ephemeral) | N/A |
| User memory (persistent notes) | Roo Code global custom instructions (settings) | VS Code settings |

### 2.2 Tool Group Assignments Per Mode

| Mode (slug) | Tool Groups | Rationale |
|-------------|-------------|-----------|
| `bet-orchestrator` | `read`, `edit`, `command`, `mcp`, `browser` | Full access — runs scripts, delegates |
| `bet-scanner` | `read`, `edit`, `command`, `mcp`, `browser` | Runs scan scripts, browses sources |
| `bet-settler` | `read`, `edit`, `command`, `mcp`, `browser` | Runs settlement, browses for results |
| `bet-statistician` | `read`, `command`, `mcp`, `browser` | Runs stats scripts, queries DB, searches web |
| `bet-scout` | `read`, `command`, `mcp`, `browser` | Browses tipster sites, searches web |
| `bet-enricher` | `read`, `edit`, `command`, `mcp`, `browser` | Runs enrichment scripts, edits data |
| `bet-valuator` | `read`, `command`, `mcp` | Queries DB, evaluates odds |
| `bet-challenger` | `read`, `command`, `mcp`, `browser` | Searches web for context, queries DB |
| `bet-builder` | `read`, `edit`, `command`, `mcp` | Builds coupon files, queries DB |
| `bet-db-analyst` | `read`, `command`, `mcp` | Queries DB, inspects files |

---

## 3. Condensation Strategy

### 3.1 The Problem

Gemma 31B has 32K context. Each mode's system prompt (`roleDefinition` + `customInstructions`) competes with conversation history and tool outputs for space. Target: **50-80 lines** per mode's inline content. Overflow goes to `.roo/rules-{slug}/` files.

### 3.2 What to KEEP Inline (customInstructions)

- Role identity (2-3 sentences)
- Hard rules (5-8 bullet points max)
- Critical methodology reminders (key rules that prevent past mistakes)
- Output contract / verdict template (condensed)
- Routing hints (when to hand back to orchestrator)

### 3.3 What Goes to `.roo/rules-{slug}/` Overflow Files

- Full sport-specific stat tables (too large for inline)
- Detailed market hierarchies and calculation tables
- Complete source navigation details (URLs, fallback chains)
- Extended mistake rules (beyond the top 5 critical ones)
- DB schema reference

### 3.4 What to CUT Entirely

- Progressive disclosure wrappers ("Use When", "What This Skill Owns") — Roo has no skill loading
- Resource map pointers to sub-files — flatten into one document
- Duplicate rule references that are already in `.clinerules`
- Verbose anti-pattern lists (keep top 5 only)
- Meta-instructions about when to load what

### 3.5 Per-Mode Condensation Plan

| Mode | Sources to Merge | Target Lines (inline) | Overflow Files |
|------|------------------|----------------------|----------------|
| `bet-orchestrator` | agent.md + execution-spine + routing-matrix + handoff-contracts | 80 | `routing.md`, `execution-spine.md` |
| `bet-scanner` | agent.md + bet-navigating-sources (condensed) | 50 | `source-navigation.md` |
| `bet-settler` | agent.md + bet-settling-results + bet-formatting-artifacts | 60 | none |
| `bet-statistician` | agent.md + bet-analyzing-statistics + sport-protocols (condensed) | 70 | `sport-protocols.md`, `market-tables.md` |
| `bet-scout` | agent.md + bet-navigating-sources (tipster subset) | 45 | none |
| `bet-enricher` | agent.md + bet-navigating-sources + bet-analyzing-statistics (data quality subset) | 55 | `source-navigation.md` |
| `bet-valuator` | agent.md + bet-evaluating-odds | 50 | none |
| `bet-challenger` | agent.md + bet-applying-sport-protocols + bet-analyzing-statistics + mistakes-rules | 70 | `sport-protocols.md`, `mistakes-rules.md` |
| `bet-builder` | agent.md + bet-building-coupons + bet-formatting-artifacts + mistakes-rules | 70 | `artifacts-format.md`, `mistakes-rules.md` |
| `bet-db-analyst` | agent.md + bet-querying-database | 45 | none |

### 3.6 Shared Overflow Strategy

Some `.roo/rules-{slug}/` content is identical across modes (e.g., sport-protocols used by statistician + challenger). **Duplicate the file** into each mode's directory — Roo has no symlink mechanism. Keep a canonical source in `.roo/rules/` for maintenance, and copy to per-mode dirs.

---

## Phase 1: Foundation

**Goal:** Set up the base configuration that all modes depend on.  
**Duration:** ~1 hour  
**Dependencies:** None  

### Task 1.1 — Create `.clinerules`

- **Type:** [CREATE]
- **File:** `/Users/mkoziol/projects/bet/.clinerules`
- **Content guidance:** Condense `copilot-instructions.md` to ~40 lines. Keep:
  - Ownership model (1 sentence per row, not full table)
  - Active model: Gemma 4 31B via LM Studio
  - Repo-wide constraints (bookmaker, timezone, coverage, coupon model, DB-first, no auto-rejection)
  - The ONE RULE from execution protocol (if response = script output piped to file → FAILED)
  - Fish shell terminal rule (no bash syntax)
  - Memory boundary (`.roo/memory-bank/` is primary)
  - Cut: canonical owners table, required loads section, session expectations (those become per-mode)
- **Definition of done:** File exists, <45 lines, covers all repo-wide rules.

### Task 1.2 — Create `.roo/mcp.json`

- **Type:** [CREATE]
- **File:** `/Users/mkoziol/projects/bet/.roo/mcp.json`
- **Content:** Direct copy of `.vscode/mcp.json` with one change: replace `${workspaceFolder}` with absolute path `/Users/mkoziol/projects/bet` in the sqlite args (Roo may not resolve VS Code variables).
- **Content:**
```json
{
  "mcpServers": {
    "sequentialthinking": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    },
    "sqlite": {
      "command": "uvx",
      "args": ["mcp-server-sqlite", "--db-path", "/Users/mkoziol/projects/bet/betting/data/betting.db"]
    },
    "brave-search": {
      "command": "npx",
      "args": ["-y", "brave-search-mcp"],
      "env": {
        "BRAVE_API_KEY": "<from config/api_keys.json>"
      }
    }
  }
}
```
- **Definition of done:** File exists, all 3 MCP servers configured, paths are absolute.

### Task 1.3 — Create `.roo/memory-bank/` with seed files

- **Type:** [CREATE]
- **Files:**
  - `/Users/mkoziol/projects/bet/.roo/memory-bank/project-structure.md` — copy from `memories/repo/project-structure.md` (if <30 lines) or condense
  - `/Users/mkoziol/projects/bet/.roo/memory-bank/pipeline-knowledge-base.md` — copy from `memories/repo/pipeline-knowledge-base.md`
  - `/Users/mkoziol/projects/bet/.roo/memory-bank/coupon-risk-lessons.md` — copy from `memories/repo/coupon-risk-lessons.md`
  - `/Users/mkoziol/projects/bet/.roo/memory-bank/betting-preferences.md` — copy from `.github/memories/betting-preferences.md`
- **Definition of done:** Memory bank directory exists with 4 seed files containing essential context.

### Task 1.4 — Create `.roomodes` skeleton

- **Type:** [CREATE]
- **File:** `/Users/mkoziol/projects/bet/.roomodes`
- **Content:** Empty `customModes` array — placeholder for Phase 2+3.
```json
{
  "customModes": []
}
```
- **Definition of done:** Valid JSON file exists, parseable by Roo Code.

### Task 1.5 — Create shared overflow rule files

- **Type:** [CREATE]
- **Files (source material for per-mode copies in Phase 2/3):**
  - `/Users/mkoziol/projects/bet/.roo/rules/analysis-methodology-compact.md` — Condense `analysis-methodology.instructions.md` to 60 lines: keep ULTIMATE RULE, data architecture key tables, sport tiers, hallucination prevention rules. Cut: full DB function listings, verbose market examples.
  - `/Users/mkoziol/projects/bet/.roo/rules/sport-protocols-compact.md` — Condense `sport-analysis-protocols.instructions.md` to 80 lines: keep per-sport stat table headers + market hierarchies + mandatory multi-market calculation tables. Cut: verbose examples, context items (these are general knowledge).
  - `/Users/mkoziol/projects/bet/.roo/rules/mistakes-rules-compact.md` — Keep full `betting-mistakes-rules.instructions.md` (it's already short: ~60 lines of critical rules).
  - `/Users/mkoziol/projects/bet/.roo/rules/artifacts-format-compact.md` — Condense `betting-artifacts.instructions.md` to 50 lines: keep coupon structure skeleton, general rules, path conventions. Cut: verbose per-section column specs (builder mode will have these in its own overflow).
- **Definition of done:** 4 compact reference files exist in `.roo/rules/`, each under 80 lines.

---

## Phase 2: Core Modes (Orchestrator + 3 Critical Specialists)

**Goal:** Get the orchestration loop working with the most-used modes.  
**Duration:** ~2 hours  
**Dependencies:** Phase 1 complete  

### Task 2.1 — Create `bet-orchestrator` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-orchestrator`
- **name:** `Bet Orchestrator`
- **roleDefinition** (target: 20 lines):
  ```
  You coordinate the bet pipeline. You are the manager, not the analyst.
  
  Responsibilities:
  - Run individual scripts one at a time in approved phase order
  - Monitor outputs, extract key metrics, react to errors or drift
  - Delegate interpretation to specialist modes via new_task after EVERY script
  - Keep user-facing synthesis coherent across settlement, scan, analysis, coupons
  - NEVER run pipeline_orchestrator.py — you ARE the orchestrator
  
  Operating Rules:
  - Pattern: RUN SCRIPT → new_task(specialist) → receive verdict → PROCEED
  - If you ever do "run script → proceed" without delegation — YOU HAVE FAILED
  - Present synthesized decisions, not raw script output
  - Use sequential-thinking MCP tool for planning between steps
  - Fish shell only: no bash syntax, no inline python, use set -x for env vars
  ```
- **whenToUse:** `When the user wants to run the full betting day pipeline, settle results, or coordinate multi-step betting workflows.`
- **customInstructions** (target: 60 lines): Merge execution-spine (condensed to routing table), verdict template, top 3 failure modes, delegation targets table.
- **groups:** `["read", "edit", "command", "mcp", "browser"]`
- **Overflow files:**
  - `.roo/rules-bet-orchestrator/execution-spine.md` — Full S0-S10 step list with script commands and delegation targets
  - `.roo/rules-bet-orchestrator/routing.md` — Condensed routing-matrix (mode slug → when to use → expected output)
- **Definition of done:** Orchestrator mode added to `.roomodes`. Overflow files created. Can be selected in Roo Code mode picker.

### Task 2.2 — Create `bet-statistician` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-statistician`
- **name:** `Bet Statistician`
- **roleDefinition** (target: 15 lines):
  ```
  Deep statistical analyst for S3 and S3B. You analyze finished deep_stats_report.py output.
  
  Your analytical value: You find PATTERNS in numbers that scripts cannot — structural
  edges from style matchups, competition-context adjustments, and three-way alignment
  (L10 + H2H + L5) that produce safety scores with GENUINE predictive power.
  
  Responsibilities:
  - Validate market ranking, safety scores, H2H relevance, three-way alignment
  - Explain edge mechanisms and competition-context adjustments  
  - Flag data gaps, stale inputs, contradictions → send back to enrichment
  - Return structured verdict with metrics, analysis, next-step readiness for S4
  
  Hard Rules:
  - Evaluate statistical markets BEFORE outcome markets
  - Flag thin data; do NOT auto-reject candidates
  - Never invent numbers — missing data = FLAGGED, not DEFAULT
  ```
- **whenToUse:** `When the pipeline needs deep statistical analysis of S3/S3B output — market ranking validation, safety score review, H2H checks, and three-way cross-validation.`
- **customInstructions** (target: 50 lines): Condensed from bet-analyzing-statistics + verdict template + key methodology reminders (safety score formula, ranking protocol essence).
- **groups:** `["read", "command", "mcp", "browser"]`
- **Overflow files:**
  - `.roo/rules-bet-statistician/sport-protocols.md` — Copy of `sport-protocols-compact.md`
  - `.roo/rules-bet-statistician/market-tables.md` — Multi-market calculation table templates per sport
- **Definition of done:** Mode in `.roomodes`, overflow files created, can be targeted by `new_task`.

### Task 2.3 — Create `bet-challenger` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-challenger`
- **name:** `Bet Challenger`
- **roleDefinition** (target: 15 lines):
  ```
  Final analytical judge for S5, S6, and S7. You synthesize stats, context, odds, and
  competition type into one decisive verdict per candidate.
  
  Your analytical value: You build specific BEAR CASES — identifying the mechanism that
  breaks the edge. Not "risky" but "WHY risky: team X's L5 fouls drop 30% in dead rubbers."
  
  Responsibilities:
  - Synthesize stats + context + odds + competition type → decisive verdict
  - Build specific bear cases with mechanism identification
  - Assign advisory strength WITHOUT auto-rejecting from matrix
  - Return structured verdict for S8 or reason to pause
  
  Hard Rules:
  - Missing critical evidence = flagged/extended-pool, NOT auto-rejected
  - Every candidate stays in matrix with clear advisory language
  - Never invent missing numbers; use web search to fill gaps
  ```
- **whenToUse:** `When the pipeline needs final analytical judgment on candidates — S5 context checks, S6 upset risk assessment, or S7 gate review.`
- **customInstructions** (target: 50 lines): Condensed from bet-applying-sport-protocols (upset risk checklist) + bet-analyzing-statistics (key thresholds) + betting-mistakes-rules (top 4 hard rules).
- **groups:** `["read", "command", "mcp", "browser"]`
- **Overflow files:**
  - `.roo/rules-bet-challenger/sport-protocols.md` — Copy of `sport-protocols-compact.md`
  - `.roo/rules-bet-challenger/mistakes-rules.md` — Copy of `mistakes-rules-compact.md`
- **Definition of done:** Mode in `.roomodes`, overflow files created.

### Task 2.4 — Create `bet-builder` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-builder`
- **name:** `Bet Builder`
- **roleDefinition** (target: 15 lines):
  ```
  Portfolio strategist for S8. You convert approved picks into a coherent portfolio
  and final betting artifacts (coupon file + daily report).
  
  Your analytical value: You spot CORRELATION between legs, exposure concentration,
  and presentation issues that pure math misses — the "two handball picks in two coupons"
  trap, the "avg ≠ hit rate" confusion.
  
  Responsibilities:
  - Structure core portfolio, combination menu, extended pool
  - Enforce unique-event-per-coupon, hard reject rules at construction stage
  - Run hallucination check: trace every cited stat back to actual source
  - Return structured coupons with per-pick reasoning (WHY + data + mechanism + bear case)
  
  Hard Rules:
  - Picks are CONDITIONAL until user verifies on Betclic
  - Preserve full matrix — use advisory language, not silent exclusions
  - VALIDATE every stat cited: L10 avg crossing line ≠ hit rate (count individual games)
  ```
- **whenToUse:** `When approved picks are ready for coupon construction — S8 portfolio building, combination menu creation, and final artifact formatting.`
- **customInstructions** (target: 60 lines): Condensed from bet-building-coupons + bet-formatting-artifacts (coupon structure template) + top validation rules (team identity, hallucination, avg vs raw, line vs reality).
- **groups:** `["read", "edit", "command", "mcp"]`
- **Overflow files:**
  - `.roo/rules-bet-builder/artifacts-format.md` — Full coupon structure (sections, column specs, Polish naming)
  - `.roo/rules-bet-builder/mistakes-rules.md` — Copy of `mistakes-rules-compact.md`
- **Definition of done:** Mode in `.roomodes`, overflow files created.

---

## Phase 3: Remaining Modes (6 Specialists)

**Goal:** Complete the mode roster.  
**Duration:** ~2 hours  
**Dependencies:** Phase 2 complete (for testing orchestrator routing)  

### Task 3.1 — Create `bet-scanner` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-scanner`
- **name:** `Bet Scanner`
- **roleDefinition** (15 lines): Discovery & shortlist specialist. Evaluates scan coverage, fixture validity, shortlist readiness. Protects tournament/league breadth.
- **whenToUse:** `When the pipeline needs scan output analysis — S1 discovery, S1e shortlist building, or coverage quality assessment.`
- **customInstructions** (45 lines): Condensed source navigation (tier system, sport scan depth requirements), coverage quality metrics, shortlist composition rules.
- **groups:** `["read", "edit", "command", "mcp", "browser"]`
- **Overflow:** `.roo/rules-bet-scanner/source-navigation.md` (URLs, fallback chains, blocked sources)
- **Definition of done:** Mode in `.roomodes`, overflow file created.

### Task 3.2 — Create `bet-settler` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-settler`
- **name:** `Bet Settler`
- **roleDefinition** (15 lines): Settlement accountant. Analyzes settled picks, bankroll impact, learning signals.
- **whenToUse:** `When the pipeline needs settlement analysis — S0 PnL calculation, bankroll impact, and learning extraction from finished results.`
- **customInstructions** (50 lines): PnL rules (win/loss/push/void/half), CLV tracking, 20% drawdown protection, learning query patterns, formatting rules for settlement reports.
- **groups:** `["read", "edit", "command", "mcp", "browser"]`
- **Overflow:** None needed (bet-settling-results + formatting fits in 50 lines condensed).
- **Definition of done:** Mode in `.roomodes`.

### Task 3.3 — Create `bet-scout` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-scout`
- **name:** `Bet Scout`
- **roleDefinition** (12 lines): Tipster intelligence analyst. Evaluates consensus, argument quality, contrarian signals from S2 output.
- **whenToUse:** `When the pipeline needs tipster analysis — S2 tipster cross-reference evaluation, argument quality assessment, or contrarian signal identification.`
- **customInstructions** (40 lines): Tipster tier system (A/B/C), independence checking, statistical-market reasoning preference, contrarian signal extraction.
- **groups:** `["read", "command", "mcp", "browser"]`
- **Overflow:** None.
- **Definition of done:** Mode in `.roomodes`.

### Task 3.4 — Create `bet-enricher` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-enricher`
- **name:** `Bet Enricher`
- **roleDefinition** (12 lines): Data quality guardian. Validates S2.3-S2.9 readiness and enrichment gaps before S3.
- **whenToUse:** `When the pipeline needs enrichment quality assessment — S2.3 scraper output, S2.5 data enrichment, S2.6-S2.9 sport-specific enrichment validation.`
- **customInstructions** (45 lines): Data quality scoring (FULL/PARTIAL/MINIMAL thresholds), per-sport readiness criteria, fallback policy summary, R14 data quality rule.
- **groups:** `["read", "edit", "command", "mcp", "browser"]`
- **Overflow:** `.roo/rules-bet-enricher/source-navigation.md`
- **Definition of done:** Mode in `.roomodes`.

### Task 3.5 — Create `bet-valuator` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-valuator`
- **name:** `Bet Valuator`
- **roleDefinition** (12 lines): Pricing analyst. Evaluates odds, EV, drift, and market quality from S4 output.
- **whenToUse:** `When the pipeline needs odds evaluation — S4 fair-odds vs offered-odds analysis, EV calculation, drift detection, or line movement interpretation.`
- **customInstructions** (45 lines): EV formula, Kelly 1/4 criterion, price gap analysis, drift threshold (>8% = mandatory re-eval), American odds conversion, conditional pricing rule.
- **groups:** `["read", "command", "mcp"]`
- **Overflow:** None.
- **Definition of done:** Mode in `.roomodes`.

### Task 3.6 — Create `bet-db-analyst` mode

- **Type:** [MODIFY] `.roomodes`
- **slug:** `bet-db-analyst`
- **name:** `Bet DB Analyst`
- **roleDefinition** (12 lines): Database specialist. Audits readiness, validates critical tables, triages DB-backed pipeline gaps.
- **whenToUse:** `When the pipeline needs database quality assessment — S0.5 pre-flight check, table coverage audit, freshness validation, or downstream readiness triage.`
- **customInstructions** (40 lines): Key table schemas (compact), repository pattern usage, critical DB queries for pipeline readiness, row count / freshness thresholds.
- **groups:** `["read", "command", "mcp"]`
- **Overflow:** None.
- **Definition of done:** Mode in `.roomodes`.

---

## Phase 4: Continue.dev Setup

**Goal:** Configure local autocomplete independent of Roo Code.  
**Duration:** 15 minutes  
**Dependencies:** LM Studio running with Qwen model loaded  

### Task 4.1 — Install Continue.dev extension

- **Type:** [CREATE]
- **Action:** Install `continue.continue` extension from VS Code marketplace.
- **Definition of done:** Extension visible in sidebar.

### Task 4.2 — Create project-level Continue config

- **Type:** [CREATE]
- **File:** `/Users/mkoziol/projects/bet/.continuerc.json`
- **Content:**
```json
{
  "tabAutocompleteModel": {
    "title": "Qwen 2.5 Coder 7B (Local)",
    "provider": "openai",
    "model": "qwen2.5-coder-7b-instruct",
    "apiBase": "http://localhost:1234/v1",
    "apiKey": "lm-studio"
  },
  "tabAutocompleteOptions": {
    "debounceDelay": 400,
    "maxPromptTokens": 2048,
    "multilineCompletions": "always"
  }
}
```
- **Definition of done:** Autocomplete triggers when typing Python/TypeScript in the project. Suggestions come from local Qwen model.

### Task 4.3 — Configure LM Studio for dual-model serving

- **Type:** [MODIFY]
- **Action:** In LM Studio settings:
  1. Load Gemma 4 31B as primary model (for Roo Code)
  2. Load Qwen 2.5 Coder 7B as secondary model (for Continue.dev)
  3. Enable "Serve multiple models" in server settings
  4. Set context length: Gemma=32768, Qwen=8192
  5. Start server on port 1234
- **Definition of done:** Both models respond to API requests. Test: `curl http://localhost:1234/v1/models` shows both.

### Task 4.4 — Configure Roo Code to use LM Studio

- **Type:** [MODIFY]
- **Action:** In Roo Code extension settings:
  1. Set API provider to "OpenAI Compatible"
  2. Set base URL to `http://localhost:1234/v1`
  3. Set model to `gemma-4-31b` (must match LM Studio model name)
  4. Set API key to `lm-studio` (any non-empty string)
- **Definition of done:** Roo Code chat responds using Gemma model.

---

## Phase 5: Testing & Validation

**Goal:** Verify the migrated infrastructure works end-to-end.  
**Duration:** ~2 hours  
**Dependencies:** Phases 1-4 complete  

### Task 5.1 — Validate MCP server connectivity

- **Type:** Test
- **Actions:**
  1. In Roo Code, switch to any mode
  2. Ask it to use `sequentialthinking` tool → should work
  3. Ask it to query `sqlite` → `SELECT count(*) FROM fixtures` → should return a number
  4. Ask it to use `brave_web_search` → should return results
- **Definition of done:** All 3 MCP servers respond correctly from within Roo Code.

### Task 5.2 — Validate orchestrator routing

- **Type:** Test
- **Actions:**
  1. Switch to `bet-orchestrator` mode
  2. Ask: "What mode would you delegate S3 analysis to?"
  3. Expected: mentions `bet-statistician`
  4. Ask: "Run a new_task to bet-statistician with message: Analyze this test output..."
  5. Expected: task spawns in statistician mode, returns verdict, orchestrator continues
- **Definition of done:** Boomerang delegation works. Orchestrator can spawn and receive results from specialist modes.

### Task 5.3 — Validate specialist mode depth

- **Type:** Test
- **Actions:**
  1. Switch to `bet-statistician` mode
  2. Ask: "What are your hard rules?"
  3. Expected: mentions statistical markets first, no auto-rejection, flag thin data
  4. Ask: "What's the football market hierarchy?"
  5. Expected: Fouls → Cards → Corners → Shots → ... (from sport protocols in overflow)
- **Definition of done:** Mode has access to both inline customInstructions AND overflow rule files.

### Task 5.4 — Validate Continue.dev autocomplete

- **Type:** Test
- **Actions:**
  1. Open any `.py` file in the project
  2. Start typing `def calculate_`
  3. Expected: autocomplete suggestion appears from Qwen model
  4. Tab to accept
- **Definition of done:** Autocomplete works independently of Roo Code chat.

### Task 5.5 — End-to-end pipeline simulation

- **Type:** Test
- **Actions:**
  1. Switch to orchestrator mode
  2. Say: "Run S0 settlement for yesterday"
  3. Expected behavior:
     - Orchestrator runs `settle_on_finish.py`
     - Orchestrator spawns `new_task` to `bet-settler` mode
     - Settler analyzes output, returns structured verdict
     - Orchestrator presents settlement summary to user
  4. Verify: verdict contains metrics, analysis, next-step readiness (not just "completed successfully")
- **Definition of done:** Single-step delegation produces quality analytical output with structured verdict.

### Task 5.6 — Context budget validation

- **Type:** Test
- **Actions:**
  1. In orchestrator mode, run 3-4 delegation cycles
  2. Monitor: does the model start losing context / repeating / forgetting rules?
  3. If yes → identify which mode's prompt is too long → condense further
- **Definition of done:** Model maintains coherent behavior through 4+ delegation cycles without degradation.

---

## Phase 6: Cleanup

**Goal:** Remove Copilot-specific artifacts that are now superseded.  
**Duration:** 30 minutes  
**Dependencies:** Phase 5 validates everything works  

> ⚠️ **DO NOT execute this phase until Phase 5 is fully green.** Keep Copilot artifacts as backup until confident.

### Task 6.1 — Archive `.github/` betting artifacts

- **Type:** [MODIFY]
- **Action:** Move (don't delete) Copilot-specific files to an archive:
  ```
  mkdir -p .github/_archived-copilot/
  mv .github/agents/ .github/_archived-copilot/agents/
  mv .github/internal-prompts/ .github/_archived-copilot/internal-prompts/
  mv .github/prompts/ .github/_archived-copilot/prompts/
  mv .github/skills/ .github/_archived-copilot/skills/
  mv .github/instructions/ .github/_archived-copilot/instructions/
  mv .github/memories/ .github/_archived-copilot/memories/
  mv .github/copilot-instructions.md .github/_archived-copilot/
  ```
- **Definition of done:** Old artifacts archived, not deleted. `.github/` only contains non-Copilot files.

### Task 6.2 — Update `.gitignore`

- **Type:** [MODIFY]
- **File:** `/Users/mkoziol/projects/bet/.gitignore`
- **Action:** Add `.roo/memory-bank/` to gitignore if memory should stay local. Keep `.roomodes` and `.clinerules` tracked.
- **Definition of done:** Git tracks the right files.

### Task 6.3 — Remove Copilot extension dependency

- **Type:** [MODIFY]
- **Action:** In VS Code settings, disable or uninstall GitHub Copilot extension. Keep Continue.dev + Roo Code.
- **Definition of done:** No Copilot extension active. Roo + Continue handle all AI functionality.

### Task 6.4 — Adapt or remove `tests/test_copilot_customizations.py`

- **Type:** [MODIFY] or [DELETE]
- **File:** `/Users/mkoziol/projects/bet/tests/test_copilot_customizations.py`
- **Issue found:** This test suite validates `.github/agents/`, `.github/prompts/`, `.github/skills/` structure — all Copilot-specific. Tests check model literals (`GPT-5.4`), frontmatter fields, instruction references, skill directories, handoff targets. After migration, these paths no longer exist.
- **Options:**
  1. **Replace** with `tests/test_roo_customizations.py` that validates `.roomodes` JSON schema, `.clinerules` exists, `.roo/mcp.json` is valid, overflow rule files are referenced correctly.
  2. **Delete** if no automated validation is needed for Roo Code config.
- **Recommended:** Option 1 — write a new test that validates `.roomodes` JSON structure (all modes have required fields, tool groups are valid, whenToUse is non-empty).
- **Definition of done:** Old test removed/replaced, `pytest` passes cleanly.

### Task 6.5 — Update `scripts/agent_protocol.py` docstrings

- **Type:** [MODIFY]
- **File:** `/Users/mkoziol/projects/bet/scripts/agent_protocol.py`
- **Issue found:** Docstring says "Agents (via Copilot) read the input" and "written by agent (manually or via Copilot)". This is now "Agents (via Roo Code)".
- **Action:** Replace references to "Copilot" with "Roo Code" in comments/docstrings. Keep `STEP_AGENT_CONFIG` and `AGENT_SKILLS_MAP` — they're still valid (mode names match agent names).
- **Definition of done:** No "Copilot" string in active Python code comments.

### Task 6.6 — Update dashboard components

- **Type:** [MODIFY]
- **Files:**
  - `dashboard/src/components/gemini-status.tsx` — Rename to `lmstudio-status.tsx`. Remove stale "Feature flags: --use-gemini, --news, --gemini" text. Keep the LM Studio config display.
  - `dashboard/src/components/run-pipeline-button.tsx` — Change alert text from "use the Copilot agent" to "use Roo Code orchestrator mode".
  - `dashboard/src/app/page.tsx` — Update import from `GeminiStatus` to `LMStudioStatus`.
- **Definition of done:** Dashboard builds, no "Copilot" or "Gemini" text in UI.

### Task 6.7 — Update `/memories/repo/` files

- **Type:** [MODIFY]
- **Files:**
  - `memories/repo/agent-protocol-and-config.md` — Update references from "copilot-collections pattern" to "Roo Code modes pattern". Remove `GPT-5.4` references.
  - `memories/repo/pipeline-knowledge-base.md` — Change "copilot-instructions.md" references to ".clinerules" where they describe active config (keep historical entries as-is since they're change logs).
- **Definition of done:** Memory files reflect current architecture.

### Task 6.8 — Update README.md

- **Type:** [MODIFY]
- **File:** `/Users/mkoziol/projects/bet/README.md`
- **Issue found:** Contains "Przejść do panelu Copilot w VS Code" instruction.
- **Action:** Replace Copilot panel instructions with Roo Code mode instructions. Update architecture description to mention Roo Code + Continue.dev + LM Studio.
- **Definition of done:** README accurately describes current AI tooling setup.

### Task 6.9 — Clean config files

- **Type:** [MODIFY]
- **Files:**
  - `config/api_keys.example.json` — Remove `"gemini"` key (no longer needed). Keep `"brave_search"`.
  - `config/api_keys.json` — Remove `"gemini"` entry.
- **Definition of done:** No Gemini API key references in config.

### Task 6.10 — Update `.github/memories/repo/` files

- **Type:** [MODIFY]
- **Files:**
  - `.github/memories/repo/project-structure.md` — Line 13: `"All active bet agent models must be \`GPT-5.4\`"` → update to reflect Roo Code + Gemma 4 31B architecture (or DELETE this file since `.roo/memory-bank/project-structure.md` supersedes it).
  - `.github/memories/repo/workflow.md` — Line 4: `"Copilot is the orchestrator"` → update or DELETE (superseded by `.roo/memory-bank/`).
- **Definition of done:** No stale model or tool references in any memory file.

---

## 10. Risk Register

### Risk 0 (NEWLY IDENTIFIED): Stale Infrastructure Residue

**Description:** Multiple files outside `.github/` still reference "Copilot", "GPT-5.4", "Gemini", or assume Copilot-specific behavior. These were missed in the initial scope.

**Affected files (exhaustive audit):**
| File | Issue | Fix |
|------|-------|-----|
| `tests/test_copilot_customizations.py` | Validates `.github/agents/` structure | Replace with `.roomodes` validator |
| `scripts/agent_protocol.py` (lines 5, 11) | Docstring says "via Copilot" | Update comment |
| `dashboard/src/components/gemini-status.tsx` | Component named "GeminiStatus", stale feature flags text | Rename + update text |
| `dashboard/src/components/run-pipeline-button.tsx` | Alert says "use the Copilot agent" | Update text |
| `README.md` (line 76) | "Przejść do panelu Copilot w VS Code" | Rewrite section |
| `memories/repo/agent-protocol-and-config.md` | "copilot-collections pattern" references | Update |
| `memories/repo/pipeline-knowledge-base.md` | Historical "copilot-instructions.md" refs | Keep historical, update active |
| `.github/memories/repo/project-structure.md` (line 13) | "GPT-5.4" model literal | Update or delete |
| `.github/memories/repo/workflow.md` (line 4) | "Copilot is the orchestrator" | Update or delete |
| `config/api_keys.example.json` (line 9) | "gemini" key | Remove |
| `config/api_keys.json` (line 11) | Live Gemini API key | Remove |
| `bet.code-workspace` | Multi-root workspace includes copilot-collections | Keep if user still uses copilot-collections for reference |

**Resolution:** All covered in Phase 6, Tasks 6.4-6.10.

---

### Risk 1: Gemma 31B Can't Follow Complex Protocols

**Probability:** Medium-High  
**Impact:** Modes produce script-runner output instead of analytical verdicts  

**Mitigations:**
1. Keep inline prompts SHORT (50-80 lines). Gemma follows short prompts better than long ones.
2. Use the verdict template as a STRUCTURAL ENFORCER — the model fills slots.
3. Add concrete BAD vs GOOD examples in each mode (models learn from examples better than rules).
4. If Gemma fails on complex modes → split into even simpler sub-modes (e.g., `bet-stats-football`, `bet-stats-tennis`).

**Fallback:**
- Switch to Qwen 32B or Llama 3.3 70B (Q3 quant) if Gemma proves inadequate for agentic work.
- Consider cloud API fallback (DeepSeek, Groq free tier) for the orchestrator mode only.

### Risk 2: Context Exhaustion in Long Sessions

**Probability:** High  
**Impact:** Model forgets rules mid-pipeline, produces hallucinated stats  

**Mitigations:**
1. Boomerang inherently helps — each sub-task gets a FRESH context window.
2. Keep orchestrator messages concise — pass only essential context in `new_task`.
3. Use `.roo/memory-bank/` to persist key decisions across mode switches.
4. Split full-day pipeline into 2-3 sessions (settlement → scan+enrich → analysis+coupons).

**Fallback:**
- Reduce Gemma context to 16K and rely more heavily on Boomerang sub-tasks (each gets fresh 16K).
- Use `attempt_completion` liberally to flush context between major phases.

### Risk 3: Boomerang Delegation Loses Information

**Probability:** Medium  
**Impact:** Specialist mode doesn't have enough context to produce quality analysis  

**Mitigations:**
1. Orchestrator must pack essential context into the `new_task` message (key metrics, file paths, specific questions).
2. Specialist modes can read files and query DB — they're not limited to what's in the message.
3. Keep a "stage context pack" pattern: orchestrator writes a brief markdown file, specialist reads it.

**Fallback:**
- If delegation quality is poor → have orchestrator do more inline analysis, use modes only for DB queries and web searches.

### Risk 4: Dual Model RAM Pressure

**Probability:** Medium  
**Impact:** LM Studio runs out of memory, models get swapped, latency spikes  

**Mitigations:**
1. Monitor Activity Monitor during sessions — watch memory pressure.
2. Qwen 7B is small (5GB) — shouldn't cause issues alongside Gemma 31B (20GB).
3. Close all other heavy apps during pipeline sessions.

**Fallback:**
- Drop Qwen 7B and use Gemma 31B for both chat and autocomplete (slower autocomplete but saves 5GB).
- Use Qwen 2.5 Coder 3B (2.5GB) instead of 7B.
- Disable Continue.dev autocomplete during heavy pipeline sessions.

### Risk 5: Missing Copilot-Specific Features

**Probability:** Low-Medium  
**Impact:** Some workflows don't have equivalents  

**Missing features and workarounds:**
| Copilot Feature | Roo Code Status | Workaround |
|-----------------|-----------------|------------|
| `applyTo` file patterns | Not supported | Put in per-mode rules. Mode selection replaces auto-activation. |
| Structured handoff payloads | Not native | Include structured data in `new_task` message text |
| User memory (persistent cross-workspace) | Not built-in | Use Roo Code global custom instructions in settings |
| `pylanceRunCodeSnippet` | Not available via MCP | Use `command` group to run Python scripts instead |
| Real-time file watching | Not supported | Manual re-read after modifications |

### Risk 6: LM Studio Instability

**Probability:** Low  
**Impact:** Pipeline interruption mid-session  

**Mitigations:**
1. Save LM Studio model loading config — quick restart if crash.
2. Write pipeline checkpoints to `.roo/memory-bank/session-state.md` after each major step.
3. All data is in DB — pipeline can resume from any step.

**Fallback:**
- Keep `config/lmstudio_config.json` updated with working settings.
- If LM Studio is unstable → switch to `llama.cpp` server directly (same OpenAI-compatible API).

---

## Appendix A: Orchestrator Routing Table (for `customInstructions`)

This table goes into the orchestrator's `customInstructions` field:

```
## Routing Table
| Step | Script | Delegate To | Expected Output |
|------|--------|-------------|-----------------|
| S0   | settle_on_finish.py | bet-settler | PnL verdict + learning signals |
| S0.5 | (DB audit) | bet-db-analyst | Table readiness + blockers |
| S1   | discover_events.py | bet-scanner | Coverage verdict + shortlist quality |
| S1e  | build_shortlist.py | bet-scanner | Shortlist composition verdict |
| S2   | tipster_xref.py | bet-scout | Consensus + contrarian signals |
| S2.3-S2.9 | run_scrapers + enrichment | bet-enricher | Data quality verdict per sport |
| S3   | deep_stats_report.py | bet-statistician | Market ranking + safety scores |
| S4   | odds_evaluator.py | bet-valuator | EV analysis + drift flags |
| S5+S6 | context_checks + upset_risk | bet-challenger | Bear cases + upset risk |
| S7   | gate_checker.py | bet-challenger | Gate verdict + approved list |
| S8   | coupon_builder.py | bet-builder | Portfolio + coupons + artifacts |
```

## Appendix B: Quick Reference — File Tree After Migration

```
/Users/mkoziol/projects/bet/
├── .clinerules                          ← Global rules (all modes)
├── .roomodes                            ← Mode definitions (10 modes)
├── .continuerc.json                     ← Continue.dev autocomplete config
├── .roo/
│   ├── mcp.json                         ← MCP servers (sqlite, brave, seq-thinking)
│   ├── memory-bank/                     ← Persistent memory
│   │   ├── project-structure.md
│   │   ├── pipeline-knowledge-base.md
│   │   ├── coupon-risk-lessons.md
│   │   └── betting-preferences.md
│   ├── rules/                           ← Shared reference files (maintenance copies)
│   │   ├── analysis-methodology-compact.md
│   │   ├── sport-protocols-compact.md
│   │   ├── mistakes-rules-compact.md
│   │   └── artifacts-format-compact.md
│   ├── rules-bet-orchestrator/
│   │   ├── execution-spine.md
│   │   └── routing.md
│   ├── rules-bet-statistician/
│   │   ├── sport-protocols.md
│   │   └── market-tables.md
│   ├── rules-bet-challenger/
│   │   ├── sport-protocols.md
│   │   └── mistakes-rules.md
│   ├── rules-bet-builder/
│   │   ├── artifacts-format.md
│   │   └── mistakes-rules.md
│   ├── rules-bet-scanner/
│   │   └── source-navigation.md
│   └── rules-bet-enricher/
│       └── source-navigation.md
├── .github/_archived-copilot/           ← Phase 6 archive
│   ├── agents/
│   ├── prompts/
│   ├── internal-prompts/
│   ├── skills/
│   ├── instructions/
│   └── copilot-instructions.md
└── (existing project files unchanged)
```

## Appendix C: Execution Checklist (Copy-Paste for Sessions)

```markdown
## Migration Progress Tracker

### Phase 1: Foundation
- [ ] 1.1 Create .clinerules
- [ ] 1.2 Create .roo/mcp.json
- [ ] 1.3 Create .roo/memory-bank/ (4 seed files)
- [ ] 1.4 Create .roomodes skeleton
- [ ] 1.5 Create shared overflow rule files (4 files in .roo/rules/)

### Phase 2: Core Modes
- [ ] 2.1 bet-orchestrator mode + overflow files
- [ ] 2.2 bet-statistician mode + overflow files
- [ ] 2.3 bet-challenger mode + overflow files
- [ ] 2.4 bet-builder mode + overflow files

### Phase 3: Remaining Modes
- [ ] 3.1 bet-scanner mode + overflow
- [ ] 3.2 bet-settler mode
- [ ] 3.3 bet-scout mode
- [ ] 3.4 bet-enricher mode + overflow
- [ ] 3.5 bet-valuator mode
- [ ] 3.6 bet-db-analyst mode

### Phase 4: Continue.dev
- [ ] 4.1 Install Continue.dev extension
- [ ] 4.2 Create .continuerc.json
- [ ] 4.3 Configure LM Studio dual-model
- [ ] 4.4 Configure Roo Code → LM Studio

### Phase 5: Testing
- [ ] 5.1 MCP server connectivity
- [ ] 5.2 Orchestrator routing (new_task works)
- [ ] 5.3 Specialist mode depth (rules accessible)
- [ ] 5.4 Continue.dev autocomplete
- [ ] 5.5 End-to-end pipeline simulation (1 step)
- [ ] 5.6 Context budget validation (4+ cycles)

### Phase 6: Cleanup & Residual Fixes
- [ ] 6.1 Archive .github/ Copilot artifacts
- [ ] 6.2 Update .gitignore
- [ ] 6.3 Remove Copilot extension
- [ ] 6.4 Fix test_copilot_customizations.py (adapt or delete)
- [ ] 6.5 Update agent_protocol.py docstrings (Copilot → Roo Code references)
- [ ] 6.6 Update dashboard components (gemini-status → lmstudio-status, run-pipeline-button text)
- [ ] 6.7 Update /memories/repo/ files (remove stale Copilot/GPT-5.4 references)
- [ ] 6.8 Update README.md (remove Copilot panel instructions)
- [ ] 6.9 Clean config/api_keys.example.json (remove gemini key, add brave_search)
- [ ] 6.10 Update .github/memories/repo/ (project-structure.md model reference, workflow.md)
```
