---
agent: "bet-scanner"
description: "S1e: Build ranked shortlist of 50-100 candidates with sport diversity"
---

# S1e — SHORTLIST FILTERING

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

### 2b. Enrichment Data Check

For each shortlisted event, verify data completeness:
- **L10 stats**: Check `betting/data/stats_cache/{sport}/{team}.json` exists for both teams
- **H2H data**: Check `h2h` key in stats cache files
- **Odds**: Check event appears in `odds_multi_sources.json` or acknowledge STATS-FIRST mode
- **Weather** (outdoor only): Check `weather_{date}.json` has entry

Flag events with <50% enrichment data as "DATA-SPARSE" — they still proceed but S3 analysis will rely more on web-scraped stats.

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

## Self-Verification (V-S1e-01 to V-S1e-11)

Key gates: 50-100 events, ≥8 sports, football ≤50%, no ITF tennis.

## Pass/Fail Gate

ALL 11 checks pass → "S1e PASSED" → orchestrator proceeds to S2.

<!-- BET:internal-prompt:bet-shortlist:v2 -->
