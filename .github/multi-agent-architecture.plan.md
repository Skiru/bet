# Multi-Agent Betting Architecture — Implementation Plan

## Overview

Replace the monolithic `bet-analyst` agent with a system of 7 specialized agents + 1 orchestrator, backed by 7 reusable skills. Each agent gets the optimal model, tools, and domain knowledge for its step.

## Architecture Diagram

```
bet-orchestrator (Claude Opus 4.6)
│   Manages pipeline, delegates to specialized agents, handles errors
│
├─→ bet-settler (Claude Sonnet 4) ─ S0
│     Skills: bet-settling-results
│     Output: settlement.md, bankroll update, learning summary
│
├─→ bet-scanner (Claude Sonnet 4) ─ S1 + S2
│     Skills: bet-navigating-sources
│     Output: master_events.md, shortlist.md, tipster_prefetch.md
│
├─→ bet-statistician (Claude Opus 4.6) ─ S3 + S3B
│     Skills: bet-analyzing-statistics, bet-applying-sport-protocols
│     Output: deep_stats.md, time_sensitive.md
│
├─→ bet-scout (Claude Sonnet 4) ─ S4
│     Skills: bet-navigating-sources
│     Output: tipsters.md
│
├─→ bet-valuator (Claude Sonnet 4) ─ S5
│     Skills: bet-evaluating-odds
│     Output: odds_ev.md
│
├─→ bet-challenger (Claude Opus 4.6) ─ S6 + S7
│     Skills: bet-applying-sport-protocols, bet-analyzing-statistics
│     Output: context.md, gate.md
│
└─→ bet-builder (Claude Opus 4.6) ─ S8
      Skills: bet-building-coupons, bet-formatting-artifacts
      Output: coupons, report, ledgers, source-log

```

---

## Phase 1: Skills (Foundation Layer)

Skills must be created first — agents reference them.

### Task 1.1 — [CREATE] `bet-navigating-sources/SKILL.md`
**What:** Source registry knowledge — fallback chains, blocked lists, per-sport source order, Playwright tips, access notes.
**Used by:** bet-scanner, bet-scout, bet-valuator, bet-statistician, bet-challenger
**Content source:** Extract from `betting/sources/source-registry.md` + `analysis-methodology.instructions.md` §1
**Location:** `.github/skills/bet-navigating-sources/SKILL.md`

### Task 1.2 — [CREATE] `bet-analyzing-statistics/SKILL.md`
**What:** Statistical analysis methodology — §3.0 ranking protocol, §3.0b market tables, §3.0c H2H validation, three-way cross-check, safety score calculation, coach/roster stability check.
**Used by:** bet-statistician, bet-challenger
**Content source:** Extract from `analysis-methodology.instructions.md` §3.0, §3.0b, §3.0c
**Location:** `.github/skills/bet-analyzing-statistics/SKILL.md`

### Task 1.3 — [CREATE] `bet-applying-sport-protocols/SKILL.md`
**What:** Sport-specific stat tables (§3.1-3.14), mandatory multi-market calculation tables per sport, upset risk checklists, instant red flags, market hierarchies per sport.
**Used by:** bet-statistician, bet-challenger, bet-builder (for validation)
**Content source:** Extract from `sport-analysis-protocols.instructions.md`
**Location:** `.github/skills/bet-applying-sport-protocols/SKILL.md`
**Note:** This will be large — use `references/` folder for detailed per-sport protocols.

### Task 1.4 — [CREATE] `bet-evaluating-odds/SKILL.md`
**What:** EV calculation, Kelly 1/4 criterion, price gap analysis, drift detection, American odds conversion, line movement interpretation, market performance tracker.
**Used by:** bet-valuator
**Content source:** Extract from `analysis-methodology.instructions.md` §5
**Location:** `.github/skills/bet-evaluating-odds/SKILL.md`

### Task 1.5 — [CREATE] `bet-formatting-artifacts/SKILL.md`
**What:** Polish translations, coupon table format, ledger CSV headers/conventions, pick ID rules, coupon ID rules, versioning protocol, per-pick concentration limits, full team names.
**Used by:** bet-builder, bet-settler (ledger format)
**Content source:** Extract from `betting-artifacts.instructions.md`
**Location:** `.github/skills/bet-formatting-artifacts/SKILL.md`

### Task 1.6 — [CREATE] `bet-building-coupons/SKILL.md`
**What:** Portfolio construction rules, unique event per coupon, combo menu construction, correlation checks, coupon stress test (§8.2), coupon type labels (LR/MS/HR/N), V1-V10 validation suite, §S8.FINAL mechanical verification, staking rules.
**Used by:** bet-builder
**Content source:** Extract from `analysis-methodology.instructions.md` §8, V1-V10, §S8.FINAL
**Location:** `.github/skills/bet-building-coupons/SKILL.md`

### Task 1.7 — [CREATE] `bet-settling-results/SKILL.md`
**What:** Settlement procedures, PnL rules (win/loss/push/void/half), CLV tracking, bankroll management (20% drawdown rule), historical learning query (§0.2), post-mortem protocol, coupon settlement with void legs.
**Used by:** bet-settler
**Content source:** Extract from `analysis-methodology.instructions.md` §0, §0.2-0.5
**Location:** `.github/skills/bet-settling-results/SKILL.md`

---

## Phase 2: Agents

### Task 2.1 — [CREATE] `bet-orchestrator.agent.md`
**Role:** Pipeline manager. Delegates S0→S8 to specialized agents in order. Monitors progress, handles gate failures, manages 4-pass protocol, escalates errors.
**Model:** Claude Opus 4.6
**Tools:** subagent delegation (runSubagent), file reading, todo, askQuestions, sequential thinking
**Agents:** [bet-settler, bet-scanner, bet-statistician, bet-scout, bet-valuator, bet-challenger, bet-builder]
**Skills:** None directly — delegates to specialists
**Key behaviors:**
- Reads config and instructions before delegating
- Passes step outputs as context to next agent
- Enforces gate conditions between steps
- Manages 4-pass error correction (Discovery → Fixes → Polish → Final)
- Handles session types (full/day/night/morning) and rerun versioning

### Task 2.2 — [CREATE] `bet-settler.agent.md`
**Role:** The accountant. Settles previous day's picks/coupons, calculates PnL/CLV, updates bankroll, runs historical learning query.
**Model:** Claude Sonnet 4
**Tools:** terminal (Python scripts), file editing, web fetch, sequential thinking
**Skills:** bet-settling-results, bet-formatting-artifacts
**Persona:** Meticulous, precision-focused, data-driven. Never approximates — every number verified.

### Task 2.3 — [CREATE] `bet-scanner.agent.md`
**Role:** The scout. Exhaustive 14-sport event scan + shortlist filtering. Navigates sources, counts matches, cross-validates, runs tipster pre-fetch.
**Model:** Claude Sonnet 4
**Tools:** browser/Playwright, web fetch, terminal (scripts), file writing
**Skills:** bet-navigating-sources
**Persona:** Thorough, systematic, never declares "no events" without exhausting fallback chains.

### Task 2.4 — [CREATE] `bet-statistician.agent.md`
**Role:** The data scientist. Deep sport-specific statistical analysis, §3.0 market ranking, H2H validation, three-way cross-check, time-sensitive data collection.
**Model:** Claude Opus 4.6
**Tools:** web fetch, sequential thinking, file writing
**Skills:** bet-analyzing-statistics, bet-applying-sport-protocols, bet-navigating-sources
**Persona:** Methodical, evidence-driven. Never skips a stat table. Always presents TOP 3 markets with hit rates.

### Task 2.5 — [CREATE] `bet-scout.agent.md`
**Role:** The intelligence gatherer. Tipster deep-dive — argument extraction, consensus analysis, watchlist promotion (§4.3).
**Model:** Claude Sonnet 4
**Tools:** browser/Playwright, web fetch, file writing
**Skills:** bet-navigating-sources
**Persona:** Curious, reads every argument fully. Extracts reasoning, not just picks. Knows all tipster site navigation patterns.

### Task 2.6 — [CREATE] `bet-valuator.agent.md`
**Role:** The pricing expert. Multi-source odds comparison, EV calculation, Kelly staking, drift detection, price gap analysis.
**Model:** Claude Sonnet 4
**Tools:** web fetch, terminal (API scripts), file writing, sequential thinking
**Skills:** bet-evaluating-odds, bet-navigating-sources
**Persona:** Sharp, quantitative, never rounds in the wrong direction. Rejects any pick with EV ≤ 0, no exceptions.

### Task 2.7 — [CREATE] `bet-challenger.agent.md`
**Role:** The devil's advocate. Context verification, upset risk scoring, bear case construction, red flags, contrarian thinking, 17-point pick approval gate.
**Model:** Claude Opus 4.6
**Tools:** web fetch, sequential thinking, file writing
**Skills:** bet-applying-sport-protocols, bet-analyzing-statistics
**Persona:** Skeptical, adversarial, always finds the bear case. Every pick is guilty until proven innocent. Enforces the Zero Tolerance Shield.

### Task 2.8 — [CREATE] `bet-builder.agent.md`
**Role:** The portfolio constructor. Coupon building, combo menu, V1-V10 validation, §S8.FINAL mechanical verification, all artifact generation.
**Model:** Claude Opus 4.6
**Tools:** sequential thinking, file writing/editing
**Skills:** bet-building-coupons, bet-formatting-artifacts, bet-applying-sport-protocols
**Persona:** Precise, structured, obsessive about arithmetic. Shows every multiplication. Never skips V1-V10.

---

## Phase 3: Update Prompts

### Task 3.1 — [MODIFY] `s0-settlement.prompt.md`
Change `agent: bet-analyst` → `agent: bet-settler`

### Task 3.2 — [MODIFY] `s1-scan.prompt.md`
Change `agent: bet-analyst` → `agent: bet-scanner`

### Task 3.3 — [MODIFY] `s2-shortlist.prompt.md`
Change `agent: bet-analyst` → `agent: bet-scanner`

### Task 3.4 — [MODIFY] `s3-deep-stats.prompt.md`
Change `agent: bet-analyst` → `agent: bet-statistician`

### Task 3.5 — [MODIFY] `s3b-time-sensitive.prompt.md`
Change `agent: bet-analyst` → `agent: bet-statistician`

### Task 3.6 — [MODIFY] `s4-tipsters.prompt.md`
Change `agent: bet-analyst` → `agent: bet-scout`

### Task 3.7 — [MODIFY] `s5-odds-ev.prompt.md`
Change `agent: bet-analyst` → `agent: bet-valuator`

### Task 3.8 — [MODIFY] `s6-context-upset.prompt.md`
Change `agent: bet-analyst` → `agent: bet-challenger`

### Task 3.9 — [MODIFY] `s7-bear-case-gate.prompt.md`
Change `agent: bet-analyst` → `agent: bet-challenger`

### Task 3.10 — [MODIFY] `s8-portfolio-coupons.prompt.md`
Change `agent: bet-analyst` → `agent: bet-builder`

### Task 3.11 — [MODIFY] `orchestrate-betting-day.prompt.md`
Change `agent: bet-analyst` → `agent: bet-orchestrator`
Update step table to reference specialized agents.

### Task 3.12 — [MODIFY] `daily-betting-cycle.prompt.md`
Already deprecated — update to point to orchestrate-betting-day with bet-orchestrator.

---

## Phase 4: Cleanup

### Task 4.1 — [DELETE] `bet-analyst.agent.md`
Remove the monolithic agent. All its responsibilities are now distributed across 7 specialized agents.

---

## Agent-Skill Matrix

| Agent | bet-navigating-sources | bet-analyzing-statistics | bet-applying-sport-protocols | bet-evaluating-odds | bet-formatting-artifacts | bet-building-coupons | bet-settling-results |
|-------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| bet-settler | | | | | ✓ | | ✓ |
| bet-scanner | ✓ | | | | | | |
| bet-statistician | ✓ | ✓ | ✓ | | | | |
| bet-scout | ✓ | | | | | | |
| bet-valuator | ✓ | | | ✓ | | | |
| bet-challenger | | ✓ | ✓ | | | | |
| bet-builder | | | ✓ | | ✓ | ✓ | |

## Model Assignments

| Agent | Model | Rationale |
|-------|-------|-----------|
| bet-orchestrator | Claude Opus 4.6 | Complex orchestration, error handling |
| bet-settler | Claude Sonnet 4 | Reliable math, CSV, script execution |
| bet-scanner | Claude Sonnet 4 | Web browsing, data extraction |
| bet-statistician | Claude Opus 4.6 | Heavy multi-step statistical reasoning |
| bet-scout | Claude Sonnet 4 | Reading comprehension, argument extraction |
| bet-valuator | Claude Sonnet 4 | Math precision, odds comparison |
| bet-challenger | Claude Opus 4.6 | Critical/contrarian thinking, gate enforcement |
| bet-builder | Claude Opus 4.6 | Complex structured output, V1-V10 validation |
