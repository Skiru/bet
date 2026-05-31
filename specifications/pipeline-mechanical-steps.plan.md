# Pipeline Mechanical Steps — Implementation Plan

## Problem Summary

The Qwen3.6-35B-A3B orchestrator model (3B active params) cannot infer dependencies between pipeline steps listed in separate prompt sections. On 2026-05-31 it skipped `tipster_aggregator.py` (S1b) before running `tipster_xref.py` (S2), resulting in 0 tipster data propagating through S3→S8.

**Root causes:**
1. Execution spine uses implied dependencies — no explicit PRECONDITION per step
2. Scripts silently succeed with 0 data instead of failing with actionable errors
3. No verification commands between steps
4. Model skipped `runSubagent` delegations entirely

---

## Technical Context

### Current State of Files

| File | Lines | Relevant Section |
|------|-------|-----------------|
| `.github/prompts/orchestrate-betting-day.prompt.md` | ~550 | EXECUTION SPINE (lines 62–380): narrative format, bash blocks, delegation notes |
| `scripts/agent_protocol.py` | ~1400 | `PIPELINE_STEPS` (line 1227): flat dict with script+description only. `DATA_FLOW_CONTRACTS` (line 608): has `depends_on`, `requires`, `produces` — already contains precondition data |
| `scripts/tipster_xref.py` | ~250 | No precondition check. Silently returns `"No tipster data in DB — skipping"` as success |
| `scripts/deep_stats_report.py` | ~500+ | Reads `pipeline_candidates` DB table. No guard if 0 rows |
| `scripts/gate_checker.py` | ~400+ | Reads `analysis_results`. No guard if 0 rows |
| `scripts/coupon_builder.py` | ~500+ | Reads `gate_results`. No guard if 0 rows |
| `scripts/agent_output.py` | Standard `AgentOutput` class with `.error()`, `.summary()`, `sys.exit(2)` pattern |
| `AGENTS.md` | Line 48: "S2 is NEVER OPTIONAL" — mentions single script, not the two-script sequence |

### Existing Infrastructure to Leverage

- `AgentOutput` class already supports `stop_on_error`, exit code 2, structured JSON events
- `DATA_FLOW_CONTRACTS` already defines `depends_on` and `requires` per step — can be referenced from step cards
- `REACTION_PATTERNS["exit_code_2"]` already instructs agents to STOP on code 2
- DB-first architecture: all inter-step data flows through DB tables with repository classes

---

## CRITICAL DISCOVERY: Conflicting Execution Sources

The pipeline runs via **Kilo Code** (not Copilot). Kilo Code reads `.roo/rules-bet-orchestrator/execution-spine.md` which has **DIFFERENT step numbering** than `.github/prompts/orchestrate-betting-day.prompt.md`:

| Canonical (.github) | .roo file | Script | CONFLICT? |
|---|---|---|---|
| S1b (step 8) | S1.5 | tipster_aggregator.py | ⚠️ Different slot |
| S1e (step 9) | S2 | build_shortlist.py | ⚠️ Different slot |
| S2 (step 10) | (missing?) | tipster_xref.py | ⚠️ NOT IN .roo! |

**ROOT CAUSE CONFIRMED:** The `.roo` execution spine puts `tipster_aggregator.py` at "S1.5" but `tipster_xref.py` ISN'T listed separately. The Kilo model read the `.roo` spine, ran `build_shortlist.py` (called "S2" there), then jumped to enrichment/deep-stats — completely missing `tipster_xref.py`.

**Fix:** The `.roo/rules-bet-orchestrator/execution-spine.md` MUST be the canonical mechanical runbook. It's what the Kilo orchestrator actually reads.

---

## Implementation Order

**Phase 0: Sync .roo execution spine** (ROOT CAUSE FIX — most critical)
**Phase 1: Script Precondition Guards** (lowest risk, immediate value)
**Phase 2: agent_protocol.py PIPELINE_STEPS Enhancement** (programmatic reference)
**Phase 3: .github Prompt Spine Sync** (keep .github in sync with .roo canonical)
**Phase 4: AGENTS.md Update** (documentation alignment)

---

## Phase 0: Sync .roo Execution Spine (ROOT CAUSE FIX)

### Task 0.1 [MODIFY] `.roo/rules-bet-orchestrator/execution-spine.md` — Complete rewrite

**What:** Replace the current 54-line file with a mechanical step-by-step runbook that matches the canonical `.github/prompts/orchestrate-betting-day.prompt.md` execution order. This file is what Kilo Code actually reads when running the orchestrator.

**Current problems:**
1. Step numbers conflict with .github prompt (S1.5 vs S1b, S2 = build_shortlist vs S2 = tipster_xref)
2. `tipster_xref.py` is NOT listed as a separate step
3. Many steps have wrong or missing script commands (S4, S5-S6 just say "(tipster deep-dive + odds evaluation)")
4. No PRECONDITION/VERIFY/PRODUCES per step
5. Missing steps: S1a (ESPN), S1b (fetch_odds/weather/tipster_agg), S2.6-S2.9 (sport enrichment), S7.5/S7.6, validate_phase gates

**Target format:** Same mechanical card format as Phase 3 prompt rewrite, but compact (table format works since .roo files are often shorter):
```markdown
| # | Step | Precondition | Script | Verify | Delegate |
```

**Definition of Done:**
- [ ] All steps from S0 through S10 present in correct canonical order
- [ ] Step numbers match .github prompt exactly (S0, S0.5, S1, S1-ingest, S1a, S1b, S1e, S2, S2.3, S2.5, S2.6-S2.9, gates, S3-S10)
- [ ] tipster_aggregator.py clearly in S1b with notation "PRODUCES tipster_picks DB rows needed by S2"
- [ ] tipster_xref.py clearly in S2 with notation "REQUIRES tipster_picks from S1b"
- [ ] Every step has correct PYTHONPATH=src .venv/bin/python3 prefix
- [ ] Every delegation target matches the routing matrix
- [ ] No steps reference non-existent scripts or wrong filenames

**Complexity:** Medium (full rewrite of 54-line file to ~80 lines)

---

### Task 0.2 [MODIFY] `.roo/rules-bet-orchestrator/routing.md` — Fix step references

**What:** Update step number references in routing table to match the canonical order.

**Changes needed:**
- "S1.5 output needs argument quality assessment" → "S2 output (tipster_xref) needs argument quality assessment"
- "S2.3-S2.9 output" references stay correct
- Verify all other step references match canonical numbering

**Definition of Done:**
- [ ] All step references in routing.md match canonical execution order
- [ ] bet-scout trigger correctly says S2 (after tipster_xref completes)
- [ ] No references to S1.5, S1.8, S1.9 (old non-canonical numbers)

**Complexity:** Low (update ~5 lines in table)

---

## Phase 1: Script Precondition Guards

### Task 1.1 [MODIFY] `scripts/tipster_xref.py` — Add precondition check

**What:** At the top of `run_tipster_xref()`, before any processing, check that tipster data exists for the date.

**Implementation:**
```python
# After argument parsing, before main logic:
from agent_output import AgentOutput

out = AgentOutput("s2_tipster_xref", verbose=args.verbose)

# Precondition 1: tipster_picks has rows for this date
from bet.db.connection import get_db
with get_db() as conn:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM tipster_picks WHERE betting_date = ?", (date,)
    )
    tip_count = cursor.fetchone()[0]

if tip_count == 0:
    out.error(
        "PRECONDITION_FAILED: tipster_picks has 0 rows for {date}. "
        "Run tipster_aggregator.py --date {date} --use-gemini --verbose FIRST.",
        recoverable=False,
    )
    out.summary(
        verdict="PRECONDITION_FAILED",
        metrics={"tipster_picks_count": 0, "date": date},
        issues=[{"level": "critical", "message": "tipster_aggregator.py must run before tipster_xref.py"}],
    )
    sys.exit(2)
```

**Definition of Done:**
- [ ] Script exits with code 2 and clear message when DB has 0 tipster_picks for date
- [ ] Message names the exact recovery action: "Run tipster_aggregator.py --date {date} --use-gemini --verbose FIRST"
- [ ] Uses AgentOutput format so orchestrator can parse the failure
- [ ] Existing behavior unchanged when precondition passes (>0 tips in DB)

**Complexity:** Low (15-20 lines added at function entry)

---

### Task 1.2 [MODIFY] `scripts/deep_stats_report.py` — Add precondition check

**What:** Before the analysis loop, verify `pipeline_candidates` has rows for the date.

**Implementation:**
```python
# After arg parsing, before candidate loading:
from bet.db.connection import get_db

with get_db() as conn:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM pipeline_candidates WHERE betting_date = ?", (date,)
    )
    candidate_count = cursor.fetchone()[0]

if candidate_count == 0:
    out.error(
        "PRECONDITION_FAILED: pipeline_candidates has 0 rows for {date}. "
        "Run build_shortlist.py --date {date} --stats-first --verbose FIRST.",
        recoverable=False,
    )
    out.summary(
        verdict="PRECONDITION_FAILED",
        metrics={"pipeline_candidates_count": 0, "date": date},
        issues=[{"level": "critical", "message": "build_shortlist.py must complete before deep_stats_report.py"}],
    )
    sys.exit(2)
```

**Definition of Done:**
- [ ] Script exits code 2 when pipeline_candidates has 0 rows for date
- [ ] Message names recovery: "Run build_shortlist.py --date {date} --stats-first --verbose FIRST"
- [ ] AgentOutput format with PRECONDITION_FAILED verdict
- [ ] Existing behavior unchanged when candidates exist

**Complexity:** Low (15-20 lines added)

---

### Task 1.3 [MODIFY] `scripts/gate_checker.py` — Add precondition check

**What:** Before gate evaluation, verify `analysis_results` has rows for the date.

**Implementation:**
```python
from bet.db.connection import get_db

with get_db() as conn:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM analysis_results WHERE betting_date = ?", (date,)
    )
    analysis_count = cursor.fetchone()[0]

if analysis_count == 0:
    out.error(
        "PRECONDITION_FAILED: analysis_results has 0 rows for {date}. "
        "Run deep_stats_report.py --date {date} --verbose FIRST.",
        recoverable=False,
    )
    out.summary(
        verdict="PRECONDITION_FAILED",
        metrics={"analysis_results_count": 0, "date": date},
        issues=[{"level": "critical", "message": "deep_stats_report.py must complete before gate_checker.py"}],
    )
    sys.exit(2)
```

**Definition of Done:**
- [ ] Exits code 2 when analysis_results has 0 rows
- [ ] Message names recovery: "Run deep_stats_report.py"
- [ ] AgentOutput format
- [ ] Existing behavior preserved when data exists

**Complexity:** Low (15-20 lines)

---

### Task 1.4 [MODIFY] `scripts/coupon_builder.py` — Add precondition check

**What:** Before coupon construction, verify `gate_results` has rows for the date.

**Implementation:**
```python
from bet.db.connection import get_db

with get_db() as conn:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM gate_results WHERE betting_date = ?", (date,)
    )
    gate_count = cursor.fetchone()[0]

if gate_count == 0:
    out.error(
        "PRECONDITION_FAILED: gate_results has 0 rows for {date}. "
        "Run gate_checker.py --date {date} --verbose FIRST.",
        recoverable=False,
    )
    out.summary(
        verdict="PRECONDITION_FAILED",
        metrics={"gate_results_count": 0, "date": date},
        issues=[{"level": "critical", "message": "gate_checker.py must complete before coupon_builder.py"}],
    )
    sys.exit(2)
```

**Definition of Done:**
- [ ] Exits code 2 when gate_results has 0 rows
- [ ] Message names recovery action
- [ ] AgentOutput format
- [ ] Existing behavior preserved

**Complexity:** Low (15-20 lines)

---

## Phase 2: agent_protocol.py Enhancement

### Task 2.1 [MODIFY] `scripts/agent_protocol.py` — Add `preconditions` to PIPELINE_STEPS

**What:** Enhance `PIPELINE_STEPS` dict to include a `preconditions` field per step. This is the programmatic reference the prompt can point to without duplicating data.

**Target structure:**
```python
PIPELINE_STEPS = {
    "S0": {
        "script": "settle_on_finish.py + evaluate_decisions.py + analyze_betclic_learning.py",
        "description": "Settlement, decision review, and Betclic learning",
        "preconditions": [],
        "verify": None,
        "produces": ["settlement artifacts", "betclic_learning"],
    },
    "S1b": {
        "script": "fetch_odds_api.py + fetch_odds_api_io.py + fetch_esports_odds.py + fetch_weather.py + tipster_aggregator.py",
        "description": "Odds + Weather + Tipster aggregation (ALL 5 scripts mandatory)",
        "preconditions": ["S1 completed"],
        "verify": "python3 -c \"from bet.db.connection import get_db; db=get_db(); print(db.execute('SELECT COUNT(*) FROM tipster_picks WHERE betting_date=\\'{date}\\'').fetchone()[0])\"",
        "produces": ["odds_history", "tipster_picks", "tipster_consensus"],
    },
    "S2": {
        "script": "tipster_xref.py",
        "description": "Cross-reference shortlist with tipster consensus",
        "preconditions": [
            "S1b completed (tipster_aggregator.py ran)",
            "DB: tipster_picks has >0 rows for {date}",
            "DB: pipeline_candidates has >0 rows for {date}",
        ],
        "verify": "python3 -c \"from bet.db.connection import get_db; db=get_db(); t=db.execute('SELECT COUNT(*) FROM tipster_picks WHERE betting_date=\\'{date}\\'').fetchone()[0]; p=db.execute('SELECT COUNT(*) FROM pipeline_candidates WHERE betting_date=\\'{date}\\'').fetchone()[0]; print(f'tips={t} candidates={p}'); assert t>0 and p>0\"",
        "produces": ["pipeline_candidates (tipster_support enrichment)"],
    },
    # ... (all steps)
}
```

**Scope:** Add `preconditions`, `verify`, and `produces` to ALL entries in the existing PIPELINE_STEPS dict. Do NOT add new steps — only enhance existing entries.

**Definition of Done:**
- [ ] Every entry in PIPELINE_STEPS has `preconditions` (list of strings), `verify` (str or None), `produces` (list of strings)
- [ ] `preconditions` for S2 explicitly lists "S1b completed (tipster_aggregator.py ran)"
- [ ] `preconditions` for S3 explicitly lists "pipeline_candidates has >0 rows"
- [ ] `preconditions` for S7 explicitly lists "analysis_results has >0 rows"
- [ ] `preconditions` for S8 explicitly lists "gate_results has >0 rows"
- [ ] Verify commands are executable Python one-liners that assert success
- [ ] No changes to DATA_FLOW_CONTRACTS (it stays as the detailed contract spec)

**Complexity:** Medium (each of ~15 steps needs 3 new fields; ~80 lines added)

---

## Phase 3: .github Prompt Execution Spine Rewrite

### Task 3.1 [MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md` — Rewrite EXECUTION SPINE

> **Note:** The .roo file (Phase 0) is what Kilo Code reads. This .github prompt is what Copilot reads AND serves as the human-readable reference. Both must be in sync.

**What:** Replace lines 62–380 (the narrative EXECUTION SPINE) with mechanical step cards. Keep:
- Lines 1–61 (frontmatter, GOOD SESSION example, FAILURE MODES, INPUTS) — UNCHANGED
- Lines 380–550 (DELEGATION PROTOCOL, RULES, TECHNICAL REFERENCE) — UNCHANGED
- Only the EXECUTION SPINE section is rewritten

**Format per step card (8-12 lines each):**
```markdown
### STEP {N}: {step_id} — {title}
PRECONDITION: {one-line check or "none"}
SCRIPT: `{exact command}`
VERIFY: `{one-liner that asserts success}`
PRODUCES: {what downstream steps consume}
DELEGATE: → runSubagent("{agent}") — load {prompt file}
IF FAILED: {specific recovery, not generic}
NEXT: {step_id}
```

**Design decisions:**
- One card per numbered step from the "GOOD SESSION" list (23 steps → 23 cards)
- Cards reference `PIPELINE_STEPS["{id}"].preconditions` from agent_protocol.py instead of repeating full precondition lists — keeps prompt SHORT
- Include 2 example cards at the top so model learns pattern
- Parallel steps (S2 + S2.3) noted inline: "PARALLEL with STEP 11"
- Gates get their own cards (4 gates)
- Total target: ~300 lines for spine (vs current ~320) — slightly shorter

**Key changes vs current format:**
1. Add PRECONDITION line to every step (currently missing)
2. Add VERIFY line to every step (currently missing)
3. Add IF FAILED with specific recovery (currently "generic")
4. Remove long explanatory paragraphs between steps
5. Keep delegation map table as-is (it's in a separate section)

**Definition of Done:**
- [ ] Every step from PRE-FLIGHT through S10 has a mechanical step card
- [ ] Every card has: PRECONDITION, SCRIPT, VERIFY, PRODUCES, DELEGATE (or "none"), IF FAILED, NEXT
- [ ] S2 card explicitly states "S1b completed (tipster_aggregator.py ran)" as precondition
- [ ] 2 example cards appear before the first real card
- [ ] Total EXECUTION SPINE section ≤320 lines
- [ ] No duplication with DELEGATION PROTOCOL section (delegation map table stays there)
- [ ] PRE-FLIGHT, DELEGATION PROTOCOL, RULES, TECHNICAL REFERENCE sections unchanged
- [ ] Parallel steps clearly marked

**Complexity:** High (full section rewrite, must preserve all 23 steps accurately)

---

## Phase 4: Documentation Alignment

### Task 4.1 [MODIFY] `AGENTS.md` — Update S2 section

**What:** Expand the "S2 is NEVER OPTIONAL" section to explicitly name the two-script sequence and the dependency.

**Target:**
```markdown
## S2 is NEVER OPTIONAL

**TWO-SCRIPT SEQUENCE (order matters):**
1. `tipster_aggregator.py --date {date} --use-gemini --verbose` → writes tipster_picks + tipster_consensus to DB
2. `tipster_xref.py --date {date} --verbose` → reads tipster_picks from DB, enriches pipeline_candidates

Script 2 WILL EXIT CODE 2 if script 1 hasn't run (0 tipster_picks for date).

Source fusion (tipsters + stats + web) is the CORE VALUE.
If S2 returns 0 tips → brave-search tipster sites → if still 0 → **ASK USER** before continuing.
Without tipster data → coupons are worthless pure math.
```

**Definition of Done:**
- [ ] Two-script sequence explicitly named with order
- [ ] Mentions exit code 2 behavior (from Phase 1)
- [ ] Existing content preserved (brave-search fallback, ASK USER rule)

**Complexity:** Low (5-8 lines replaced/expanded)

---

## Dependency Graph

```
Phase 1 (Tasks 1.1-1.4)     — independent, can be done in any order
        ↓
Phase 2 (Task 2.1)          — references Phase 1 behavior (exit code 2)
        ↓
Phase 3 (Task 3.1)          — references Phase 2 structure (PIPELINE_STEPS.preconditions)
        ↓
Phase 4 (Task 4.1)          — references Phase 1 behavior
```

Phase 1 tasks are fully independent of each other. Phase 4 is independent of Phase 3.

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Scripts exit 2 on valid empty state (off-season sport) | Guard checks specific date, not "ever". Off-season = legitimately 0 rows |
| Prompt becomes too long with 23 cards | Target 10 lines/card × 23 = 230 lines. Current spine is 320. We're actually shorter |
| agent_protocol.py grows too large | PIPELINE_STEPS stays compact — 3 extra fields per entry, not full paragraphs |
| Breaking change if tables don't exist | Use `try/except` around DB check with informative message about migration |
| Model ignores step cards anyway | Step cards + exit code 2 = defense in depth. Model can ignore prompt but can't ignore script failure |

---

## Testing Strategy

- **Phase 1:** Run each script with `--date 2026-05-31` against an empty DB (no prior steps) → must exit code 2 with clear message. Run against DB with data → must proceed normally.
- **Phase 2:** `python3 -c "from scripts.agent_protocol import PIPELINE_STEPS; assert 'preconditions' in PIPELINE_STEPS['S2']"`
- **Phase 3:** Manual review — count lines, verify no section was accidentally deleted, verify delegation map table intact
- **Phase 4:** Visual inspection of AGENTS.md diff

---

## Estimated Total Scope

| Phase | Tasks | Lines Changed | Complexity |
|-------|-------|---------------|-----------|
| 1 | 4 scripts | ~80 lines added (20 per script) | Low |
| 2 | 1 file | ~80 lines added to PIPELINE_STEPS | Medium |
| 3 | 1 file | ~320 lines replaced | High |
| 4 | 1 file | ~10 lines modified | Low |
| **Total** | **7 tasks** | **~490 lines** | **Medium-High** |
