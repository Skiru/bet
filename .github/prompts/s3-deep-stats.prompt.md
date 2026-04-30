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

### PRE-CHECK: API ANALYSIS POOL
Before web-fetching stats for any candidate, check if the analysis pool already has data:
1. Read `betting/data/analysis_pool_{date}.json`
2. For each shortlisted candidate, search the pool by team names
3. If found with `data_quality: FULL` or `PARTIAL`:
   - Use the pre-computed `all_markets` table as the §3.0 ranking starting point
   - Use `best_market.safety_score`, `l10_avg`, `h2h_avg`, `l5_avg` as pre-validated data
   - Still verify with web sources and supplement missing stats (injuries, context, coach stability)
   - Run `compute_safety_scores.py` to validate/extend the ranking with additional markets
4. If NOT in pool or `data_quality: THIN`:
   - Full web-fetch required per sport protocol below
5. For football/basketball/hockey: additional API stats available via `python3 scripts/fetch_api_stats.py --date YYYY-MM-DD --sports football,basketball,hockey`

### PER-CANDIDATE PROTOCOL

#### Per-Sport Protocols
Follow the sport-specific protocol from `bet-applying-sport-protocols` skill:
- **Football §3.1**: corners, fouls, cards, shots hierarchy + SoccerStats/Flashscore/Sofascore sources. 3-source corner stack. xG regression. Referee for cards/fouls markets.
- **Tennis §3.2**: games/sets O/U priority. Odds ratio grading. Surface-specific H2H. WC/Q/LL blowout rule. TennisAbstract serve/return stats.
- **Basketball §3.3**: team totals > quarter totals > game totals. Pace/ratings. B2B check. ESPN injury DAY-OF.
- **Hockey §3.4**: period totals priority. Goalie confirmation (DailyFaceoff CRITICAL). xG, PP/PK.
- **Baseball §3.5**: starting pitcher (BaseballSavant). Bullpen load. Park factor. Wind/weather.
- **Volleyball §3.6**, **Esports §3.7**, **Snooker §3.8**, **Darts §3.9**
- **Table Tennis §3.10**, **Handball §3.11**, **MMA §3.12**, **Padel §3.13**, **Speedway §3.14**

Each protocol defines: required stat tables, mandatory multi-market calculation (§XM), bettable market lists, data sources, and market hierarchy.

**Universal requirements for EVERY sport:**
- §3.0 STATISTICAL MARKET RANKING: list ALL bettable stat markets, calculate safety score (`min(hit_rate_L10, hit_rate_H2H)`), rank, pick TOP market
- COACH/ROSTER STABILITY CHECK: coach change in last 5 matches (TransferMarkt)? Major roster changes in last 14 days?
- Identify the STATISTICAL MARKET first, not the winner. Present TOP 2 markets with data.

### OUTPUT FORMAT
Save to: `betting/data/{date}_s3_deep_stats.md`

**CRITICAL: Every section below is MANDATORY. The orchestrator will structurally verify that ALL 10 sections exist for EVERY candidate. Missing sections = step sent back for fix. Do NOT abbreviate, skip, or merge sections.**

For each candidate, fill this EXACT template (all 10 numbered sections):
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

### 10. §S3.10 — ANALYSIS DEPTH PROOF
| Metric | Value |
|--------|-------|
| Sources queried | [count] |
| Data points collected | [count] |
| Markets evaluated | [count] |
| Time spent (est.) | [minutes] |
| Confidence in data completeness | [HIGH/MEDIUM/LOW] |
```

**PER-SPORT MANDATORY CALCULATIONS (in addition to the template above):**
- **Football**: Must fill §3.1M multi-market table (Fouls, Cards, Corners, Shots, Team CK, Goals)
- **Tennis**: Must fill §3.2M multi-market table (Games, Sets, Game HC, Tiebreaks, Aces) + odds ratio grade
- **Basketball**: Must fill §3.3M multi-market table (Team pts, Total pts, Q1, 1H, Spread)
- **Volleyball**: Must fill §3.5M multi-market table (Sets, Points, Set HC, Pts/set)
- **Other sports**: Must fill the sport-specific §XM table from sport-analysis-protocols.instructions.md

## SELF-VERIFICATION CHECKLIST

**Count-based verification — the orchestrator will independently re-count these:**

- [ ] **V-S3-01**: Every shortlisted candidate has an analysis block with ALL 10 numbered sections
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

**DEPTH METRIC**: Count candidates with ALL of {§3.0 table, H2H-stat, three-way check, coach check, top 3 markets, ≥2 sources, injury check, depth proof} = DEPTH_%
**GATE**: DEPTH_% must be ≥95%. If <95% → list which candidates are missing which sections → FIX before proceeding.

### ERROR LOG
```
| Check | Status | Error | Fix |
|-------|--------|-------|-----|
```

### PASS/FAIL GATE
- ALL checks pass → "S3 PASSED" → proceed to S4
- ANY fail → fix → re-verify
