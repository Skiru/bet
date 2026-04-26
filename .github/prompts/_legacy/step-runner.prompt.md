---
name: step-runner
description: "Master orchestrator: run all steps 1-8 sequentially for a betting day. Each step reads the previous step's output."
agent: bet-analyst
argument-hint: "run_date=2026-04-25 start_step=1"
tools:
  - search
  - editFiles
  - runCommands
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **start_step** = ${input:start_step:1} (resume from this step if previous steps already completed)

## Sequential Step Execution

Execute each step by invoking the corresponding prompt. Each step's output feeds the next.

### Step Chain:

```
STEP 1: Event Scan → betting/data/{date}_master_events.md
    ↓
STEP 2: Shortlist → betting/data/{date}_shortlist.md
    ↓
STEP 3: Deep Stats → betting/data/{date}_deep_stats.md  (one analysis per candidate)
    ↓
STEP 4: Tipster Dive → betting/data/{date}_tipster_dive.md  (≥2 sites per candidate)
    ↓
STEP 5: Odds + EV → betting/data/{date}_odds_ev.md  (EV calculation per candidate)
    ↓
STEP 6: Context → (merged into deep_stats — injuries, weather, lineups)
    ↓
STEP 7: Bear Case → betting/data/{date}_bear_case.md  (approval gate per candidate)
    ↓
STEP 8-10: Portfolio → betting/coupons/{date}-v{N}.md + ledger updates
```

### Rules:
1. DO NOT skip steps. DO NOT merge steps.
2. Each step produces a file. Read the previous step's file before starting the next.
3. If a step reveals that a previous step's data is wrong or incomplete, GO BACK and fix it.
4. Use sequentialthinking for EVERY step (at least one call per step, one call per candidate for steps 3-7).
5. Do not produce any coupon until Step 8. Steps 1-7 are RESEARCH ONLY.

### Data Flow Integrity:
- Step 2 reads Step 1 output → only shortlists events that exist in Master Event List
- Step 3 reads Step 2 output → only analyzes shortlisted candidates
- Step 4 reads Step 2 output → checks tipsters for shortlisted candidates
- Step 5 reads Steps 3+4 → calculates EV using stats and tipster data
- Step 7 reads Steps 3+4+5 → builds bear case using all prior evidence
- Step 8 reads Step 7 → only builds coupons from APPROVED picks

### Error Recovery:
- If Step 1 finds <50 events → widen search, check more sources
- If Step 2 produces <15 candidates → lower thresholds or scan more sports
- If Step 3 finds critical error (wrong date, wrong opponent) → fix and re-shortlist
- If Step 4 finds 0 tipsters for a candidate → flag, reduce confidence -1
- If Step 5 shows EV ≤ 0 → REJECT candidate, do not proceed to Step 7
- If Step 7 rejects >70% of candidates → go back to Step 2 and widen shortlist
- If Step 8 produces <5 coupons → relax criteria or promote watchlist picks
