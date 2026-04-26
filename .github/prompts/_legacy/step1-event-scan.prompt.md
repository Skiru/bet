---
name: step1-event-scan
description: "STEP 1: Exhaustive event scan across ALL 14 sports. Outputs Master Event List to betting/data/{date}_master_events.md"
agent: bet-analyst
argument-hint: "run_date=2026-04-25"
tools:
  - search
  - editFiles
  - runCommands
  - memory/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **local_timezone** = Europe/Warsaw
- Betting day window: 06:00 run_date → 05:59 next day CEST

## Task

Build a COMPLETE Master Event List for the betting day. This is SCAN ONLY — no analysis, no picks, no coupons.

### Instructions

1. **For EACH of the 14 sports below**, fetch the BetExplorer page AND at least one secondary source.
2. **Click into EVERY tournament/league** — do NOT just scan the landing page.
3. **Count matches per tournament**. If a tournament has ≥4 matches, flag it for full screening.
4. **Record odds** (1X2 or ML) for every event.
5. **Cross-validate** event counts between sources. Note discrepancies.

### Sport Scan Order (follow exactly)

| # | Sport | Primary URL | Secondary URL | Specialist |
|---|-------|-------------|---------------|------------|
| 1 | Football | betexplorer.com/soccer/ | flashscore.com/football/ | — |
| 2 | Tennis | betexplorer.com/tennis/ | flashscore.com/tennis/ | atptour.com, wtatennis.com |
| 3 | Basketball | betexplorer.com/basketball/ | espn.com/nba/schedule | — |
| 4 | Hockey | betexplorer.com/hockey/ | espn.com/nhl/schedule | — |
| 5 | Baseball | betexplorer.com/baseball/ | espn.com/mlb/schedule | — |
| 6 | Volleyball | betexplorer.com/volleyball/ | flashscore.com/volleyball/ | — |
| 7 | Esports | betexplorer.com/esports/ | hltv.org/matches | gosugamers.net |
| 8 | Snooker | betexplorer.com/snooker/ | flashscore.com/snooker/ | — |
| 9 | Darts | betexplorer.com/darts/ | flashscore.com/darts/ | — |
| 10 | Handball | betexplorer.com/handball/ | flashscore.com/handball/ | — |
| 11 | Table Tennis | betexplorer.com/table-tennis/ | flashscore.com/table-tennis/ | — |
| 12 | MMA | betexplorer.com/mma/ | tapology.com/fightcenter | ufc.com |
| 13 | Padel | betexplorer.com/padel/ | sofascore.com/padel | premierpadel.com |
| 14 | Speedway | betexplorer.com/speedway/ | speedwayekstraliga.pl | sportowefakty.wp.pl/zuzel |

### Output Format

Save to `betting/data/{run_date}_master_events.md`:

```markdown
# Master Event List — {run_date}
## Scan Completeness

| Sport | Source 1 (BE) | Source 2 | Specialist | Total Unique | Tournaments ≥4 matches |
|-------|---------------|----------|------------|-------------|----------------------|
| Football | X | X | — | X | list... |
| ... | | | | | |
| TOTAL | | | | X | |

## Events by Sport

### 1. Football
#### EPL — Round X (6 matches)
| Time | Match | 1 | X | 2 | Books |
| ... |

#### La Liga — Round X (4 matches)
...

### 2. Tennis
#### ATP Madrid R32 (16 matches)
| Time | Match | P1 odds | P2 odds | Ratio |
...
```

### Quality Gates (MUST pass before done)
- [ ] All 14 sports checked (record "NO EVENTS" with source if empty)
- [ ] Total unique events ≥ 50
- [ ] ≥ 6 sports have events
- [ ] Every tournament with ≥4 matches listed with ALL matches
- [ ] Cross-source discrepancy < 30% per sport
- [ ] Odds recorded for every event
