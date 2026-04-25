---
name: step3-deep-stats
description: "STEP 3: Deep statistical analysis per shortlisted candidate. One analysis per candidate. Outputs to betting/data/{date}_deep_stats.md"
agent: bet-analyst
argument-hint: "run_date=2026-04-25 candidates=Arsenal-Newcastle,Liverpool-Palace,Heerenveen-Sittard"
tools:
  - search
  - editFiles
  - runCommands
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **candidates** = ${input:candidates} (comma-separated list from step2 shortlist)
- **shortlist** = `betting/data/{run_date}_shortlist.md` (output from step2)

## Task

For EACH candidate, perform deep sport-specific statistical analysis. Use the sequentialthinking tool — one call per candidate.

### Per-Candidate Checklist (EVERY item MANDATORY)

#### ALL SPORTS:
- [ ] **H2H**: Fetch last 5-10 meetings from BetExplorer/Flashscore. Include home/away splits. Record scores.
- [ ] **Form**: Last 5-6 matches for each team/player. Record W/L and scores.
- [ ] **Injuries/Suspensions**: Check ESPN injury reports, Flashscore lineups, team social media. For tennis: ATP/WTA withdrawal list.
- [ ] **Deep stats**: Sport-specific protocol (see below).
- [ ] **Market ranking**: Identify TOP 3 markets by hit rate × odds. DO NOT default to ML.
- [ ] **Context**: Motivation, fixture congestion, weather (outdoor sports), referee (cards/fouls).

#### FOOTBALL-SPECIFIC:
- [ ] League averages: goals/match, O2.5%, BTTS%, corner avg from SoccerStats or BetExplorer league stats
- [ ] Team stats: GF, GA, corners for/against, cards for/against (home/away split)
- [ ] Corner 3-source stack: TotalCorner + SoccerStats + Betclic Statystyki (flag if any missing)
- [ ] xG data if available (Flashscore/Sofascore) — check for regression
- [ ] Defensive profile: clean sheets %, GF+GA per match (U2.5/BTTS indicator)

#### TENNIS-SPECIFIC:
- [ ] Odds ratio: max(odds)/min(odds). Grade: ≤1.15 STRONG, 1.16-1.30 GOOD, 1.31-1.50 BORDERLINE, >1.50 REJECT
- [ ] Surface form: clay/hard/grass win rate this season
- [ ] Player identity verified: full name, ranking, WC/Q/LL flag
- [ ] Previous round result in THIS tournament (fatigue check)
- [ ] WC/Q/LL blowout rule: O22.5 HARD REJECT, O21.5 REJECT unless within 20 ranking spots, O20.5 max with STRONG ratio

#### BASKETBALL-SPECIFIC:
- [ ] Pace: possessions/game for both teams
- [ ] OFF/DEF rating
- [ ] B2B check, rest days
- [ ] Home/away splits for totals

#### HOCKEY-SPECIFIC:
- [ ] Goalie confirmed? Check DailyFaceoff
- [ ] xG for/against
- [ ] PP/PK efficiency
- [ ] B2B fatigue check
- [ ] Series stats (if playoffs)

#### BASEBALL-SPECIFIC:
- [ ] Starting pitcher: ERA, WHIP, K/9, last 3 starts
- [ ] Bullpen ERA/WHIP (last 7 days)
- [ ] Team batting vs RHP/LHP splits
- [ ] Wind/weather for outdoor parks
- [ ] Verify Saturday starter (not assumed from weekday rotation)

### Source URLs to Fetch (per sport)
- Football: betexplorer.com match page (H2H tab), soccerstats.com/{league}, flashscore.com team page
- Tennis: betexplorer.com match page, tennisabstract.com/cgi-bin/player-classic.cgi?p={player}, flashscore.com player page
- Basketball: espn.com/nba/team/schedule/_/name/{team}, basketball-reference.com
- Hockey: espn.com/nhl/team/schedule, dailyfaceoff.com/starting-goalies, naturalstattrick.com
- Baseball: espn.com/mlb/game/_/gameId/{id}, baseballsavant.mlb.com/statcast_search

### Output Format

Save to `betting/data/{run_date}_deep_stats.md`:

```markdown
# Deep Stats — {run_date}

## CANDIDATE 1: Arsenal vs Newcastle (Football, EPL)
### H2H (last 5)
| Date | Home | Away | Score | Corners | Cards |
| ... |

### Form
| Team | L5 | GF | GA | Home/Away |
| Arsenal | WDLWW | 12 | 5 | Home |
| Newcastle | LLWDL | 6 | 9 | Away |

### Stats
- League avg goals: X, O2.5%: X%, BTTS%: X%
- Arsenal home: X corners/game, X cards/game
- Newcastle away: X corners/game, X cards/game
- Corner 3-source stack: TotalCorner [X], SoccerStats [X], Betclic [X]

### Injuries
- Arsenal: [player] OUT (reason), [player] DOUBTFUL
- Newcastle: [player] OUT

### Market Ranking
| # | Market | Hit Rate | Odds | EV est. |
| 1 | Corners O9.5 | 72% | 1.70 | +2% |
| 2 | O2.5 goals | 58% | 1.85 | +3% |
| 3 | BTTS Yes | 55% | 1.72 | +1% |

### Best Pick: [market] @ [odds]
### Flags: [any concerns]
```
