---
name: step2-shortlist
description: "STEP 2: Filter Master Event List to 15-40 shortlisted candidates. Outputs shortlist to betting/data/{date}_shortlist.md"
agent: bet-analyst
argument-hint: "run_date=2026-04-25"
tools:
  - search
  - editFiles
  - memory/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **master_events** = `betting/data/{run_date}_master_events.md` (output from step1)

## Task

Filter the Master Event List down to a shortlist of 15-40 candidates for deep analysis.

### Filtering Rules

1. **REMOVE** events outside betting-day window (06:00 today → 05:59 tomorrow CEST)
2. **REMOVE** events with no Tier A source coverage
3. **REMOVE** events too close to kickoff (<1h at analysis time)
4. **REMOVE** exhibition/friendly matches without odds
5. **REMOVE** ITF tennis (unreliable — only ATP/WTA main draw or strong Challengers)

### Screening Criteria (keep events that have ANY of these)

- Statistical market available (corners, cards, totals, sets, frames, maps, handicaps)
- Odds in preferred range (1.30–3.50 for at least one market)
- Both teams/players roughly competitive (odds ratio ≤ 2.0 for tennis O-games)
- Strong statistical trend (e.g., 100% O2.5 streak, elite pitcher matchup)
- Tournament with ≥4 matches today (full slate screening)

### Market Priority (screen for these FIRST — ML is LAST RESORT)
- Football: corners > cards > fouls > shots > team totals > BTTS > U2.5 > O2.5 > DC > 1X2
- Tennis: game totals > set totals > game HC > set HC > ML
- Basketball: team totals > quarter totals > game totals > spreads > ML
- Hockey: period totals > game totals > puck line > ML
- Baseball: F5 totals > team totals > game totals > run line > ML
- All others: totals > handicaps > props > ML

### Sport Diversity Check
- Shortlist MUST include ≥ 5 different sports
- Football ≤ 50% of shortlist
- If < 5 sports, go back to Step 1 and scan missing sports deeper

### Output Format

Save to `betting/data/{run_date}_shortlist.md`:

```markdown
# Shortlist — {run_date}
## Summary: X candidates from Y sports

| # | Sport | Competition | Event | Time | Best Market Idea | Odds Range | Priority |
|---|-------|-------------|-------|------|-----------------|------------|----------|
| 1 | Football | EPL | Arsenal vs Newcastle | 18:30 | Corners O9.5 | ~1.70 | HIGH |
| ... |

## Removed Events (with reasons)
| Event | Reason |
|-------|--------|
| ... | ... |

## Sport Coverage
| Sport | Events in MEL | Shortlisted | Passed | Reason |
|-------|--------------|-------------|--------|--------|
```
