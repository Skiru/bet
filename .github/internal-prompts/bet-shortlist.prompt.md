---
agent: "bet-scanner"
description: "S2: Build ranked shortlist of 50-100 candidates with sport diversity"
---

# S2 — SHORTLIST FILTERING

## Required Skills

Load these skills before starting:
- `bet-navigating-sources` — source tiers, Betclic market availability checks

## Context (provided by orchestrator)

- **Inputs**: `{date}_s1_master_events.md`, `market_matrix_{date}.json`, `analysis_pool_{date}.json`
- **Session**: event window filter from session type
- **Script**: `python3 scripts/build_shortlist.py --date {date} --stats-first`

## Workflow

### 1. Run Automated Shortlist

```bash
python3 scripts/build_shortlist.py --date {date} --stats-first
```
Produces `{date}_s2_shortlist.md` + `{date}_s2_shortlist.json`.

### 2. Review and Refine

Apply removal criteria in order:
1. Outside window, 2. No Tier A source, 3. <2h to kickoff, 4. Already started, 5. Exhibition, 6. ITF tennis, 7. Unverifiable

### 3. Early Betclic Market Check

For niche sports (volleyball, table tennis, padel, speedway): verify Betclic market existence BEFORE deep analysis.

### 4. Screening Criteria

Assess: statistical market available? Odds in range (1.30-3.50)? Major tournament? Tier A data quality?

### 5. Sport Diversity Gate

- ≥8 sports in shortlist (≥5 in final picks)
- Football ≤50% of shortlist
- If <8 sports → go back to S1, scan missing sports deeper

## Output

Save to: `betting/data/{date}_s2_shortlist.md`

Sections: Summary, Removal Log, Tier 1 (statistical markets), Tier 2 (ML/basic), Major Tournaments.

## Self-Verification (V-S2-01 to V-S2-11)

Key gates: 50-100 events, ≥8 sports, football ≤50%, no ITF tennis.

## Pass/Fail Gate

ALL 11 checks pass → "S2 PASSED" → orchestrator proceeds to S3.

<!-- BET:internal-prompt:bet-shortlist:v1 -->
