# Deep Reasoning Enforcement — Implementation Plan

## Problem Statement

Qwen3.6-35B-A3B (3B active params) spams tool calls without reasoning first, causing:
- Slow responses (each tool call = full inference cycle at 15-25 tok/s)
- Malformed JSON (coherence loss after 3+ rapid calls)
- Shallow analysis (data dump instead of insight)

## Already Fixed (DO NOT TOUCH)

- `.kilo/prompts/bet-orchestrator.md` — think-first enforced
- `.kilocode/rules/anti-drift-protocol.md` — THINK-BEFORE-ACT, CITE-OR-DELETE, RE-GROUND rules
- `.github/instructions/agent-execution-protocol.instructions.md` — full execution protocol

---

## Phase 1: Infrastructure — Load Execution Protocol in All Subagents

**Rationale:** The anti-drift rules (think-first, max 3 tools/turn, cite-or-delete, re-ground at 2000 tokens) already exist in `agent-execution-protocol.instructions.md`. None of the 9 subagents load it. Adding it to their `instructions:` array gives ALL agents these rules with ZERO prompt duplication.

### Task 1.1 — [MODIFY] `kilo.jsonc`: Add protocol to bet-statistician

**File:** `/Users/mkoziol/projects/bet/kilo.jsonc`

```
oldString:
    "bet-statistician": {
      "description": "Deep statistical analyst — S3/S3B specialist for market ranking, safety scores, H2H validation, three-way alignment. Use when the pipeline needs deep statistical analysis of S3/S3B output.",
      "model": "openai-compatible/qwen3.6-35b-a3b",
      "mode": "subagent",
      "steps": 40,
      "temperature": 0.6,
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],

newString:
    "bet-statistician": {
      "description": "Deep statistical analyst — S3/S3B specialist for market ranking, safety scores, H2H validation, three-way alignment. Use when the pipeline needs deep statistical analysis of S3/S3B output.",
      "model": "openai-compatible/qwen3.6-35b-a3b",
      "mode": "subagent",
      "steps": 40,
      "temperature": 0.6,
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
```

### Task 1.2 — [MODIFY] `kilo.jsonc`: Add protocol to bet-challenger

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-challenger.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-challenger.md}",
```

### Task 1.3 — [MODIFY] `kilo.jsonc`: Add protocol to bet-builder

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md",
        ".github/instructions/betting-artifacts.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-builder.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md",
        ".github/instructions/betting-artifacts.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-builder.md}",
```

### Task 1.4 — [MODIFY] `kilo.jsonc`: Add protocol to bet-scanner

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-scanner.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-scanner.md}",
```

### Task 1.5 — [MODIFY] `kilo.jsonc`: Add protocol to bet-settler

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-settler.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-settler.md}",
```

### Task 1.6 — [MODIFY] `kilo.jsonc`: Add protocol to bet-scout

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-scout.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-scout.md}",
```

### Task 1.7 — [MODIFY] `kilo.jsonc`: Add protocol to bet-enricher

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-enricher.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/sport-analysis-protocols.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-enricher.md}",
```

### Task 1.8 — [MODIFY] `kilo.jsonc`: Add protocol to bet-valuator

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-valuator.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md",
        ".github/instructions/betting-mistakes-rules.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-valuator.md}",
```

### Task 1.9 — [MODIFY] `kilo.jsonc`: Add protocol to bet-db-analyst

```
oldString:
      "instructions": [
        ".github/instructions/analysis-methodology.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-db-analyst.md}",

newString:
      "instructions": [
        ".github/instructions/agent-execution-protocol.instructions.md",
        ".github/instructions/analysis-methodology.instructions.md"
      ],
      "prompt": "{file:.kilo/prompts/bet-db-analyst.md}",
```

**Definition of Done (Phase 1):** All 9 subagents have `agent-execution-protocol.instructions.md` as FIRST entry in their `instructions:` array. Verified by grep: `grep -c "agent-execution-protocol" kilo.jsonc` = 10 (1 global + 1 orchestrator + 9 subagents... wait, global also counts → 11 matches).

---

## Phase 2: Per-Agent Think-First Section

**Rationale:** The protocol gives them the rules, but each agent needs a SHORT role-specific reminder at the top of their prompt that says "think first about YOUR specific concern." This is 3-5 lines, not a duplicate of the protocol.

### Task 2.1 — [MODIFY] `bet-scout.md`: Remove thinking cap, add think-first

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-scout.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

**THINKING: ≤200 tokens. Identify what to analyze → do it. No session planning.**

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "What tipster arguments exist? Which are data-backed vs opinion? What 1-2 queries confirm independence?"
- Plan max 3 tool calls. Execute. Narrate. Done.
```

### Task 2.2 — [MODIFY] `bet-enricher.md`: Remove thinking cap, add think-first

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-enricher.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

**THINKING: ≤200 tokens. Identify what to check → do it. No session planning.**

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "Which sports need coverage check? What's my shortlist size? Which 1-2 queries tell me BLOCKER vs ADVISORY?"
- Plan max 3 tool calls. Execute. Narrate. Done.
```

### Task 2.3 — [MODIFY] `bet-scanner.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-scanner.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "How many fixtures per sport? Any missing leagues from protected list? Phantoms? What 1-2 queries confirm coverage?"
- Plan max 3 tool calls. Execute. Narrate. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.4 — [MODIFY] `bet-statistician.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-statistician.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "Which candidates need ranking? What's the three-way alignment question? Which 2-3 queries verify L10+H2H+L5?"
- Plan max 3 tool calls per candidate group. Cite every number. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.5 — [MODIFY] `bet-valuator.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-valuator.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "Which picks have EV data? Any drift >8%? What 1-2 queries confirm fair-odds vs offered?"
- Plan max 3 tool calls. Explain mispricing mechanism. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.6 — [MODIFY] `bet-challenger.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-challenger.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "What's the specific failure mechanism for each candidate? Dead rubber? Motivation? What 1-2 web searches confirm context?"
- Plan max 3 tool calls. Build bear case with MECHANISM. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.7 — [MODIFY] `bet-builder.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-builder.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "How many approved picks? Any correlation between legs? Which stats need hit-rate verification (avg ≠ hit rate)?"
- Plan max 3 tool calls for validation. Trace every number to source. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.8 — [MODIFY] `bet-settler.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-settler.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "Which coupons need settling? What's expected PnL? Which 1-2 queries give me results + bankroll?"
- Plan max 3 tool calls. Extract learning signal. Done.

## YOUR ANALYTICAL VALUE
```

### Task 2.9 — [MODIFY] `bet-db-analyst.md`: Add think-first after tool block

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-db-analyst.md`

```
oldString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## YOUR ANALYTICAL VALUE

newString:
> ⛔ ONLY these tools exist: `sqlite_read_query`, `sqlite_write_query`, `sqlite_list_tables`, `sqlite_describe_table`, `brave-search_brave_web_search`, `brave-search_brave_news_search`, `sequentialthinking_sequentialthinking`, `read`, `write`, `edit`, `bash`, `glob`, `grep`. NO other tool names work. `read_file`=WRONG, `brave_web_search`=WRONG, `list_files`=WRONG, `websearch`=WRONG.

## ⚡ THINK-FIRST (before ANY tool call)

Call `sequentialthinking_sequentialthinking` FIRST with:
- thought: "What tables does today's pipeline need? Which are BLOCKER if stale? What 2 queries show coverage + freshness?"
- Plan max 3 tool calls. Classify BLOCKER vs ADVISORY. Done.

## YOUR ANALYTICAL VALUE
```

**Definition of Done (Phase 2):**
- [ ] All 9 subagent prompts have `## ⚡ THINK-FIRST` section between tool block and `## YOUR ANALYTICAL VALUE`
- [ ] bet-scout and bet-enricher no longer have `**THINKING: ≤200 tokens**` cap
- [ ] Each think-first section includes a role-specific `sequentialthinking` thought template
- [ ] Each section enforces "max 3 tool calls" pattern
- [ ] Verified by grep: `grep -l "THINK-FIRST" .kilo/prompts/bet-*.md` = 9 files

---

## Phase 3: Source Fusion Mandate for Analysis Agents

**Rationale:** Only bet-builder has formalized "DB + tipster + web" triple-source. Agents that analyze data (statistician, challenger, valuator, scout) can currently produce verdicts from a single source. Adding a 2-line rule prevents single-source shallow analysis.

### Task 3.1 — [MODIFY] `bet-statistician.md`: Add source fusion rule

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-statistician.md`

```
oldString:
## Hard Rules

1. Statistical markets BEFORE outcome markets
2. HIT RATE > average (8/10 > avg crossing line)
3. Never invent numbers — missing = FLAGGED, not DEFAULT
4. League-specific lines (NBA≠NBB≠Women's≠Euroleague)
5. Apply HARD REJECT rules from betting-mistakes-rules
6. Fabrication: all-same L10, zero variance, source="db-synthetic" → cap safety at 0.50

newString:
## Hard Rules

1. Statistical markets BEFORE outcome markets
2. HIT RATE > average (8/10 > avg crossing line)
3. Never invent numbers — missing = FLAGGED, not DEFAULT
4. League-specific lines (NBA≠NBB≠Women's≠Euroleague)
5. Apply HARD REJECT rules from betting-mistakes-rules
6. Fabrication: all-same L10, zero variance, source="db-synthetic" → cap safety at 0.50
7. **SOURCE FUSION**: DB stats alone = incomplete. Cross-check with tipster reasoning (S2 output) + web context. Cite ≥2 independent sources per STRONG verdict.
```

### Task 3.2 — [MODIFY] `bet-challenger.md`: Add source fusion rule

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-challenger.md`

```
oldString:
## Hard Rules

1. safety < 0.15 → INSTANT REJECT. < 0.30 → extended only.
2. Direction conflict (margin ≤0.5 + L5 contradicts) → REJECT/FLIP
3. Hit rate = PERCENTAGE (6/8=75% > 7/10=70%)
4. Missing evidence = FLAGGED, not auto-rejected
5. Every candidate stays in matrix with advisory language
6. Dead rubber + stat market → apply −2.5 penalty

newString:
## Hard Rules

1. safety < 0.15 → INSTANT REJECT. < 0.30 → extended only.
2. Direction conflict (margin ≤0.5 + L5 contradicts) → REJECT/FLIP
3. Hit rate = PERCENTAGE (6/8=75% > 7/10=70%)
4. Missing evidence = FLAGGED, not auto-rejected
5. Every candidate stays in matrix with advisory language
6. Dead rubber + stat market → apply −2.5 penalty
7. **SOURCE FUSION**: Bear cases need MECHANISM from ≥2 sources (DB stat + web context or tipster dissent). "Risky" without evidence = DRIFT.
```

### Task 3.3 — [MODIFY] `bet-valuator.md`: Add source fusion rule

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-valuator.md`

```
oldString:
## Hard Rules

1. Odds conditional until user verifies on Betclic
2. Statistical markets priced BEFORE outcome markets
3. Drift > 8% = MANDATORY re-evaluation
4. EV = (hit_rate × odds) - 1. Only EV > 0 valid.
5. League-specific lines (NBA≠NBB≠Women's≠Euroleague)
6. Betclic PL missing market ≠ rejection (mark EXTENDED)

newString:
## Hard Rules

1. Odds conditional until user verifies on Betclic
2. Statistical markets priced BEFORE outcome markets
3. Drift > 8% = MANDATORY re-evaluation
4. EV = (hit_rate × odds) - 1. Only EV > 0 valid.
5. League-specific lines (NBA≠NBB≠Women's≠Euroleague)
6. Betclic PL missing market ≠ rejection (mark EXTENDED)
7. **SOURCE FUSION**: Drift explanation needs web/news confirmation. "Line moved" without WHY = insufficient. Check injuries, lineup news, sharp money signals.
```

### Task 3.4 — [MODIFY] `bet-scout.md`: Add source fusion rule

**File:** `/Users/mkoziol/projects/bet/.kilo/prompts/bet-scout.md`

```
oldString:
## Hard Rules

1. Tipster hit rates = advisory only — NEVER auto-reject
2. Prefer statistical-market reasoning over winner-only chatter
3. Include esports tipster picks (CS2, Dota2, Valorant)
4. Preserve tipster's ARGUMENT — it's the core value
5. Verify output format: `"tips"` key (NOT `"all_picks"`)

newString:
## Hard Rules

1. Tipster hit rates = advisory only — NEVER auto-reject
2. Prefer statistical-market reasoning over winner-only chatter
3. Include esports tipster picks (CS2, Dota2, Valorant)
4. Preserve tipster's ARGUMENT — it's the core value
5. Verify output format: `"tips"` key (NOT `"all_picks"`)
6. **SOURCE FUSION**: Validate tipster claims against DB/web. "L5 fouls rising" → verify with `sqlite_read_query`. "Injury" → verify with `brave_news_search`. Unverified claims marked [UNCONFIRMED].
```

**Definition of Done (Phase 3):**
- [ ] bet-statistician, bet-challenger, bet-valuator, bet-scout each have rule 6/7 with `**SOURCE FUSION**`
- [ ] Each rule specifies WHAT sources to cross-reference for that agent's role
- [ ] Verified by grep: `grep -l "SOURCE FUSION" .kilo/prompts/bet-*.md` = 5 files (4 above + builder already has it in narrative)

---

## Execution Order

1. **Phase 1 first** — gives all agents the protocol rules immediately (HIGHEST IMPACT, lowest risk)
2. **Phase 2 second** — adds per-agent think-first reminders (reinforces Phase 1)
3. **Phase 3 last** — source fusion rules (analytical quality improvement)

## Verification Script

After all changes, run:
```fish
# Phase 1: protocol loaded by all agents
grep -c "agent-execution-protocol" kilo.jsonc
# Expected: 11 (1 global + 1 orchestrator + 9 subagents)

# Phase 2: think-first in all prompts
grep -l "THINK-FIRST" .kilo/prompts/bet-*.md | wc -l
# Expected: 9

# Phase 2: no more thinking caps
grep -r "THINKING: ≤200" .kilo/prompts/
# Expected: 0 results

# Phase 3: source fusion in analysis agents
grep -l "SOURCE FUSION" .kilo/prompts/bet-*.md | wc -l
# Expected: 4
```

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Protocol adds context tokens | It's ~80 lines, well within 131K budget. Subagents have 20-50 steps max anyway. |
| Think-first adds latency | 1 sequentialthinking call (2-5s) vs 5+ blind sqlite calls (15-25s each). Net FASTER. |
| Source fusion blocks on missing data | Rules say "cite ≥2 sources" not "require all 3". Fallback chain preserved. |
| Conflicting rules between protocol + prompt | Protocol = HOW (mechanics). Prompt = WHAT (domain). No overlap by design. |
