---
name: s3-deep-stats
description: "STEP 3: Sport-specific deep statistical analysis per candidate"
agent: bet-analyst
---

# STEP 3 — DEEP STATISTICAL ANALYSIS

## INPUTS
- `betting/data/{date}_s2_shortlist.md` — shortlisted candidates
- Sport-specific protocols from analysis-methodology.instructions.md §3.1-3.14

## TASK
For EACH shortlisted candidate, gather sport-specific statistics. One candidate = one analysis block.

### PER-CANDIDATE PROTOCOL

#### FOOTBALL (§3.1) — FULL STAT COLLECTION:
1. **H2H** last 5-10 meetings (home/away splits, goals, corners, cards per meeting)
2. **League context** (SoccerStats): goals avg, O2.5%, BTTS%, corner avg, card avg, fouls avg
3. **Team form** last 6 matches (W/D/L, goals for/against, corners for/against)
4. **Full per-team stats** (FootyStats/Flashscore/Sofascore) — collect ALL:
   - FOULS: fouls committed/match, fouls drawn/match, total match fouls avg
   - CARDS: team cards/match, opponent cards/match, total match cards avg
   - CORNERS: corners earned/match, conceded/match, total avg (SoccerStats + TotalCorner)
   - SHOTS: shots/match, shots on target/match, conversion rate %
   - GOALS: scored/match, conceded/match, clean sheet %
   - xG: xG for/against (Flashscore/Sofascore) — xG > goals = regression UP, goals > xG = regression DOWN
5. **Market ranking — present TOP 3 markets with HIT RATES**:
   - For each candidate, calculate hit rate for ≥3 O/U lines
   - Example: "Leipzig O16.5 shots: hits 87% at home" + "Union away O14.5 shots: 73%"
   - Rank: highest (hit_rate × odds value) = best market
   - Hierarchy: fouls > cards > corners > shots > team totals > BTTS > U2.5 > O2.5 > DC > 1X2
6. **Corner picks**: 3-source stack = TotalCorner + SoccerStats + Betclic Statystyki (top leagues only)
7. **Injury/suspension check** (ESPN, Flashscore, team social media)
8. **Context**: dead rubber? cup rotation? derby? referee for cards/fouls?

#### TENNIS (§3.2) — STATISTICAL FIRST, ML LAST RESORT:
1. **Player identity**: FULL name, country, ranking, WC/Q/LL status — NO slashes, NO abbreviations
2. **Odds ratio**: max(odds)/min(odds) → grade STRONG(≤1.15)/GOOD(1.16-1.30)/BORDERLINE(1.31-1.50)/REJECT(>1.50)
3. **Surface-specific win rate** (clay for Madrid, hard for US, grass for Wimbledon) — THIS SEASON + overall
4. **H2H** on current surface (last 5-10 meetings, including set scores)
5. **Previous round result** in this tournament (score, duration, physical condition — 3h+ = fatigue risk)
6. **Serve/return stats** from TennisAbstract: 1st serve %, SPW, RPW, break points, hold %, Elo
7. **WC/Q/LL Blowout Rule**: O22.5+ HARD REJECT. O21.5 only within 20 ranking spots. O20.5 max with STRONG ratio.
8. **Over-games assessment**: both hold >75%? → tiebreaks → higher games. Both break >25%? → shorter sets but 3 sets likely.
9. **Market hierarchy**: game totals O/U > set totals O/U > game HC > set HC > ML (LAST RESORT — needs STRONG + surface + H2H ALL aligned)

#### BASKETBALL (§3.3):
1. Pace + offensive/defensive rating
2. Team totals avg, O/U line hit rates
3. Injury report (ESPN — check DAY OF)
4. B2B check, rest days
5. H2H last 5 meetings
6. Market: team totals > quarter totals > game totals > spreads > ML

#### HOCKEY (§3.4):
1. xG for/against
2. GOALIE CONFIRMATION (DailyFaceoff — CRITICAL)
3. PP/PK percentages
4. B2B check
5. H2H last 5
6. Market: period totals > game totals > puck line > ML

#### BASEBALL (§3.5):
1. Starting pitcher stats (ERA, WHIP, K/9, last 3 starts) — BaseballSavant
2. Bullpen status (innings pitched last 3 days)
3. Team batting vs RHP/LHP splits
4. Park factor
5. Wind/weather (outdoor stadiums)
6. Market: F5 totals > team totals > game totals > run line > ML

#### VOLLEYBALL/ESPORTS/SNOOKER/DARTS/HANDBALL/TABLE_TENNIS/MMA/PADEL/SPEEDWAY:
Follow sport-specific protocols in methodology §3.5-3.14. Minimum per candidate:

| Sport | Key stat requirement | Market hierarchy |
|-------|---------------------|-----------------|
| Volleyball | Sets avg, O/U 3.5 hit rate, attack eff | set score > points > sets > HC > ML |
| Esports | Map pool, rounds avg, BO format, roster | rounds > maps > map HC > ML |
| Snooker | Frame win %, centuries, decider record | centuries > frames > frame HC > ML |
| Darts | 3-dart avg, checkout %, 180s/match | 180s > legs > sets > ML |
| Handball | Goals scored/conceded, 2min suspensions, GK save % | half totals > game totals > HC > ML |
| Table Tennis | Set win %, ranking gap, set avg | points > sets > set HC > ML |
| MMA | Sig strikes/min, TD accuracy, finish rate | method > O/U rounds > ITD > ML |
| Padel | FIP ranking gap, partnership duration, surface | game totals > set totals > set HC > ML |
| Speedway | Rider TRACK averages (venue-specific!), junior assessment | total pts > HC > match winner |

**For EVERY sport**: identify the STATISTICAL MARKET first, not the winner. Present TOP 2 markets with data.

### OUTPUT FORMAT
Save to: `betting/data/{date}_s3_deep_stats.md`

For each candidate:
```
## [PICK_ID_PLACEHOLDER] — [Event Name] ([Sport], [Tournament])
- **Kickoff**: HH:MM CEST
- **Odds**: Team A X.XX / Draw X.XX / Team B X.XX (source: BE)
- **H2H**: [last 5 meetings summary]
- **Form**: Team A [WWDLW], Team B [LDWWL]
- **Key Stats**: [sport-specific data points]
- **Injuries**: [confirmed absences or "none found"]
- **Statistical Market Ranking**:
  1. [best market] — hit rate X%, data: [source]
  2. [2nd best] — hit rate X%, data: [source]
  3. [3rd option] — hit rate X%, data: [source]
- **Recommended Market**: [specific market + line + reasoning]
- **Sources Used**: [list all sources checked]
```

## SELF-VERIFICATION CHECKLIST

- [ ] **V-S3-01**: Every shortlisted candidate has an analysis block
- [ ] **V-S3-02**: Every candidate has H2H data (or explicit "no H2H found" with source checked)
- [ ] **V-S3-03**: Every candidate has injury check (or explicit "no injuries found" with source)
- [ ] **V-S3-04**: Every candidate has ≥2 stat sources listed
- [ ] **V-S3-05**: Statistical market ranked for every candidate (NOT defaulting to ML)
- [ ] **V-S3-06**: Tennis: odds ratio calculated + graded (STRONG/GOOD/BORDERLINE/REJECT)
- [ ] **V-S3-07**: Tennis: WC/Q/LL status checked for EVERY player
- [ ] **V-S3-08**: Hockey: goalie confirmation attempted
- [ ] **V-S3-09**: Baseball: starting pitcher identified
- [ ] **V-S3-10**: No candidate has ONLY a 1-sentence analysis (minimum 5 data points each)
- [ ] **V-S3-11**: Form data (last 5-6 matches) for every team/player
- [ ] **V-S3-12**: Football: SoccerStats league context checked

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S3 PASSED" → proceed to S4
- ANY fail → fix → re-verify
