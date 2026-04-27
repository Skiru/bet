---
name: s3-deep-stats
description: "STEP 3: Sport-specific deep statistical analysis per candidate"
agent: bet-statistician
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
4. **Full per-team stats** (SoccerStats/Flashscore/Sofascore — FootyStats is 403 BLOCKED) — collect ALL:
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
   - Hierarchy: fouls > cards > corners > shots > team totals > BTTS > U2.5 > O2.5 > DC/DNB > 1X2
6. **Corner picks**: 3-source stack = TotalCorner + SoccerStats + Betclic Statystyki (top leagues only)
7. **Injury/suspension check** (ESPN, Flashscore, team social media)
8. **Context**: dead rubber? cup rotation? derby? referee for cards/fouls?
9. **§3.0 STATISTICAL MARKET RANKING (mandatory):** Run the full §3.0 protocol — list ALL bettable stat markets for this sport, calculate safety score for each (`min(hit_rate_L10, hit_rate_H2H)`), rank them, pick the TOP market. Present ranking table in analysis.
10. **COACH/ROSTER STABILITY CHECK (mandatory):** Did the coach change in last 5 matches (TransferMarkt)? Any major transfers, loan returns, or squad changes in last 14 days? New coach = volatile form. Major roster change = stats may not apply.

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

**CRITICAL: Every section below is MANDATORY. The orchestrator will structurally verify that ALL 9 sections exist for EVERY candidate. Missing sections = step sent back for fix. Do NOT abbreviate, skip, or merge sections.**

For each candidate, fill this EXACT template (all 9 numbered sections):
```
## [PICK_ID_PLACEHOLDER] — [Event Name] ([Sport], [Tournament])
- **Kickoff**: HH:MM CEST
- **Odds**: Team A X.XX / Draw X.XX / Team B X.XX (source: BE)

### 1. H2H (last 5-10 meetings)
| Date | Score | Stat1 [specific stat] | Stat2 | Surface/Venue |
|------|-------|----------------------|-------|---------------|
...
- **H2H summary**: [who dominated, key pattern, home/away split]
- **H2H for SPECIFIC STAT**: [the exact stat being evaluated — e.g., "H2H corner totals: 8, 11, 9, 12, 7 → avg 9.4"]
- **H2H-STAT STATUS**: ✅ Available (X meetings) / ❌ H2H-STAT-BLIND (−0.5 confidence, no LR coupon)

### 2. Form (last 6 matches)
- Team A: [WWDLWL] — scored X.X/match, conceded X.X/match
- Team B: [LDWWLW] — scored X.X/match, conceded X.X/match

### 3. §3.0 STATISTICAL MARKET RANKING TABLE (MANDATORY — ≥3 markets)
| Market           | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety | Margin |
|------------------|-----------|-----------|---------|-------|---------|---------|--------|--------|
| [market 1]       |           |           |         |       |   /10   |   /5    |        |        |
| [market 2]       |           |           |         |       |   /10   |   /5    |        |        |
| [market 3]       |           |           |         |       |   /10   |   /5    |        |        |
| [market 4+]      |           |           |         |       |   /10   |   /5    |        |        |

**Selected market**: [market with HIGHEST safety score] — Safety: X.X
**Why this beat alternatives**: [1 sentence — e.g., "Fouls had 80% safety vs corners 60% — both teams physical style"]

### 4. THREE-WAY CROSS-CHECK
- L10 AVERAGE → [value] → hit rate vs line: [X/10]
- H2H AVERAGE → [value] → hit rate vs line: [X/5]
- L5 RECENT  → [value] → trend: [UP/DOWN/STABLE]
- ALIGNMENT: ✅ ALL THREE support [OVER/UNDER] / ⚠️ 2/3 conflict → DOWNGRADE / ❌ 3/3 conflict → REJECT

### 5. Coach/Roster Stability Check
- **Coach change (last 5 matches)?**: [YES — details / NO] (source: TransferMarkt / Flashscore)
- **Major roster changes (last 14 days)?**: [YES — details / NO] (source: TransferMarkt)
- **Impact**: [none / form data unreliable / stats may not apply]

### 6. Injury/Suspension Check
- **Team A**: [name — injury type — status (OUT/DOUBTFUL)] or "None confirmed"
- **Team B**: [name — injury type — status] or "None confirmed"
- **Source**: [ESPN / Flashscore / team social media — name the actual source]
- **Impact on thesis**: [none / weakens thesis / strengthens thesis — explain]

### 7. TOP 3 Market Recommendations
1. **[BEST]**: [Market + Line] — Hit rate: X% (L10) / X% (H2H) — WHY: [1 sentence]
2. **[2ND]**: [Market + Line] — Hit rate: X% / X% — WHY: [1 sentence]
3. **[3RD]**: [Market + Line] — Hit rate: X% / X% — WHY: [1 sentence]

### 8. Recommended Market + Reasoning
- **Market**: [specific market + line, e.g., "O10.5 corners" or "O22.5 games"]
- **Reasoning**: [2-3 sentences with specific data — e.g., "Leipzig average 6.8 corners at home (L10), Union concede 5.2 away. H2H average 12.0 corners (5 meetings). Line 10.5 hit in 8/10 L10 + 4/5 H2H."]
- **Risk**: [1 sentence — what makes this fail]

### 9. Sources Used
| Source | Data Retrieved | Status |
|--------|---------------|--------|
| [source1] | [what data] | ✅ OK / ⚠️ Partial / ❌ Failed |
| [source2] | [what data] | |
| [source3+] | [what data] | |
```

**PER-SPORT MANDATORY CALCULATIONS (in addition to the template above):**
- **Football**: Must fill §3.1M multi-market table (Fouls, Cards, Corners, Shots, Team CK, Goals)
- **Tennis**: Must fill §3.2M multi-market table (Games, Sets, Game HC, Tiebreaks, Aces) + odds ratio grade
- **Basketball**: Must fill §3.3M multi-market table (Team pts, Total pts, Q1, 1H, Spread)
- **Volleyball**: Must fill §3.5M multi-market table (Sets, Points, Set HC, Pts/set)
- **Other sports**: Must fill the sport-specific §XM table from sport-analysis-protocols.instructions.md

## SELF-VERIFICATION CHECKLIST

**Count-based verification — the orchestrator will independently re-count these:**

- [ ] **V-S3-01**: Every shortlisted candidate has an analysis block with ALL 9 numbered sections
- [ ] **V-S3-02**: Every candidate has §3.0 RANKING TABLE with ≥3 markets (count rows)
- [ ] **V-S3-03**: Every candidate has H2H-STAT data for the SPECIFIC selected stat (or explicit H2H-STAT-BLIND flag)
- [ ] **V-S3-04**: Every candidate has THREE-WAY CROSS-CHECK with alignment verdict
- [ ] **V-S3-05**: Every candidate has COACH/ROSTER CHECK with source named
- [ ] **V-S3-06**: Every candidate has ≥2 stat sources in Sources table (count rows)
- [ ] **V-S3-07**: Every candidate has INJURY CHECK with source named (not just "none")
- [ ] **V-S3-08**: Every candidate has TOP 3 MARKETS listed with hit rates
- [ ] **V-S3-09**: Tennis: odds ratio calculated + graded (STRONG/GOOD/BORDERLINE/REJECT)
- [ ] **V-S3-10**: Tennis: WC/Q/LL status checked for EVERY player
- [ ] **V-S3-11**: Hockey: goalie confirmation attempted (DailyFaceoff)
- [ ] **V-S3-12**: Baseball: starting pitcher identified (BaseballSavant)
- [ ] **V-S3-13**: Football: §3.1M multi-market table filled (Fouls, Cards, Corners, Shots minimum)
- [ ] **V-S3-14**: No candidate has fewer than 5 data points in analysis
- [ ] **V-S3-15**: Form data (last 5-6 matches) for every team/player

**DEPTH METRIC**: Count candidates with ALL of {§3.0 table, H2H-stat, three-way check, coach check, top 3 markets, ≥2 sources, injury check} = DEPTH_%
**GATE**: DEPTH_% must be ≥95%. If <95% → list which candidates are missing which sections → FIX before proceeding.

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S3 PASSED" → proceed to S4
- ANY fail → fix → re-verify
