---
applyTo: ""
---

# Sport-Specific Analysis Protocols — Reference Document

> **This file is loaded ON DEMAND, not auto-loaded.** It contains detailed per-sport statistical protocols, upset risk checklists, and instant red flag tables. The agent loads it when performing deep analysis (STEP 3+).
>
> **Sports:** Football, Volleyball, Basketball, Tennis, Hockey — all Tier 1. Scan ALL leagues/divisions deeply. Analysis depth is identical for all candidates.

---

## §3 SPORT-SPECIFIC STATISTICAL PROTOCOLS

### §3.1 Football

**Required stats (split Home/Away):**

| Category | Metrics | Source |
|----------|---------|--------|
| Goals | Scored/match, Conceded/match, O2.5%, BTTS%, Clean sheets% | SoccerStats, Sofascore |
| xG | xGF/match, xGA/match, xG vs actual delta (regression indicator) | Flashscore, Sofascore |
| Corners | Team earned/match, Conceded/match, Total match avg, O9.5/O10.5 hit rate | TotalCorner + SoccerStats |
| Cards | Team cards/match, Opponent cards/match, O3.5/O4.5 hit rate | SoccerStats, Betaminic |
| Fouls | Committed/match, Drawn/match, Total match avg | SoccerStats, Sofascore |
| Shots | Shots/match, SOT/match, Conversion%, O/U team shots hit rates | Sofascore, Flashscore |
| Possession | Possession%, Throw-ins/match | Sofascore |

> **Note:** FootyStats (footystats.org) is 403 blocked on main pages. Use SoccerStats + Betaminic + Sofascore as replacements. Individual FootyStats team pages sometimes work as last-resort fallback.

**Corner picks — THREE-SOURCE STACK (mandatory):**
1. TotalCorner: match-level corner total predictions + handicaps
2. SoccerStats: league corner rankings (team averages home/away)
3. Betclic Statystyki: verified corner odds (top leagues: EPL, LaLiga, Bundesliga only)

**Market decision process:**
1. Calculate hit rate for each O/U line from stats above
2. Calculate combined hit rate when both teams merged
3. Priority: highest hit rate × best odds = best market
4. Football hierarchy: Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 (LAST RESORT)
5. Present TOP 3 markets per match with hit rates before choosing
6. **WHY corners/fouls/shots > goals:** These markets accumulate throughout the match (5-8 corners per half regardless of score), are driven by team STYLE (pressing = corners, physical = fouls), and survive in-match chaos (red card barely affects total corners). Goals depend on finishing luck. EVERY match MUST have ≥1 corner/foul/shot market evaluated.

**§3.1M MANDATORY MULTI-MARKET CALCULATION (FOOTBALL):**
Before selecting ANY football market, calculate ALL of these for the specific match:
```
| Market           | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|------------------|-----------|-----------|---------|------|---------|---------|--------|
| Fouls O/U X.5    |           |           |         |      |         |         |        |
| Cards O/U X.5    |           |           |         |      |         |         |        |
| Corners O/U X.5  |           |           |         |      |         |         |        |
| Shots O/U X.5    |           |           |         |      |         |         |        |
| Team CK O/U X.5  |           |           |         |      |         |         |        |
| Goals O/U X.5    |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. If corners and fouls are both high → pick whichever has better H2H support. **NEVER default to corners without checking fouls/cards/shots first.**

**Context (MANDATORY):** Coach change (TransferMarkt), injuries/suspensions (ESPN, Flashscore), fixture congestion (<72h), motivation (relegation/title/dead rubber), weather (rain/wind→corners), referee stats (cards/fouls).

**§3.1E EXOTIC LEAGUE FOOTBALL (adjusted for thin data):**

When analyzing a football match from an exotic league (see §1.7 definition in analysis-methodology.instructions.md):

**Adjusted stat table (use when SoccerStats/TotalCorner don't cover the league):**

| Category | Metrics | Primary Source | Fallback Source |
|----------|---------|---------------|-----------------|
| Goals | Scored/match, Conceded/match, O2.5%, BTTS% | Flashscore match history (manual count from last 10) | Soccerway standings + results |
| Corners | Team earned/match, Total match avg | Flashscore per-match stats (if available) | Soccerway match reports (corner counts in match details) |
| Cards | Team cards/match | Flashscore per-match stats | Soccerway match reports |
| Fouls | Committed/match, Drawn/match | Sofascore match stats | Flashscore per-match stats |
| Shots | Shots/match, SOT/match | Sofascore match stats | Flashscore per-match stats |
| H2H | Last 3-5 meetings with stat breakdowns | Flashscore H2H tab | Soccerway H2H |

**CRITICAL:** When manually counting stats from Flashscore/Sofascore match pages, note this in §S3.10 Analysis Depth Proof as "Manual count from [N] match pages on [source]."

**Minimum stat thresholds to approve an exotic league pick:**

| Criterion | Threshold | Action if not met |
|-----------|-----------|-------------------|
| Match stats available (corners, shots, fouls) for ≥5 of last 10 home games | YES | Can proceed |
| Match stats available for 3-4 of last 10 games | PARTIAL | Proceed with EXOTIC-THIN flag |
| Match stats available for <3 of last 10 games | NO | SKIP — insufficient data |
| H2H meetings with stat breakdowns | ≥3 | Can proceed (flag if <5) |
| H2H meetings with stat breakdowns | 1-2 | Proceed only with EXOTIC-THIN flag + strong L10 convergence |
| H2H meetings with stat breakdowns | 0 | H2H-STAT-BLIND applies per §3.0c |

**Exotic league corner analysis (when TotalCorner has no data):**
1. Open Flashscore → league → click into each of the last 10 home matches for both teams
2. Record corner count per match from match stats tab
3. Calculate team average corners earned (home) and conceded (away)
4. If Flashscore has no match stats → try Sofascore match detail page
5. If neither has match stats → corner market is UNAVAILABLE for this pick. Move to next §3.0 ranked market.

**Kings League exception:** Do NOT use standard football stats for Kings League matches. Kings League uses modified rules (20-minute halves, special mechanics). Use ONLY Kings League-specific historical data from previous Kings League seasons. Standard §3.1 stat requirements do not apply. Treat as EXOTIC-THIN by default.

### §3.2 Tennis

**Required stats per player:**

| Category | Metrics | Source |
|----------|---------|--------|
| Elo | Overall, Surface-specific, trajectory | TennisAbstract |
| Serve | 1st serve%, 1st serve pts won%, 2nd serve pts won%, Aces/match, DFs/match, Hold% | TennisAbstract, Flashscore |
| Return | Return pts won%, BP converted%, Return games won% | TennisAbstract |
| Games | Avg games/set, Avg total games/match, O/U 20.5/21.5/22.5 hit rate | Flashscore match history |
| Sets | 3-set match%, Tiebreak frequency%, Sets won from behind% | Flashscore |
| Surface form | Win% on this surface THIS YEAR, vs Top 20/50/100 | TennisAbstract |
| Previous round | Score, games, duration, physical condition (MANDATORY for R2+) | Flashscore |

**Market decision:**
1. Calculate odds ratio: `max(odds) / min(odds)`
2. Grades (EXACT boundaries): ≤1.15=STRONG, 1.16-1.30=GOOD, 1.31-1.50=BORDERLINE, >1.50=REJECT
3. Tennis hierarchy: Game totals O/U → Set totals O/U → Game HC → Set HC → ML (LAST RESORT)
4. Both match odds must be 1.50-2.50 for O-games
5. Clay = more breaks = supports over. Hard = serve-dominant = tiebreaks.
6. **WHY games/sets > ML:** Games accumulate every set (driven by serve% and return%), making them style-predictable. ML depends on a few break points — high variance. A player losing a match still produces 18-25 games.

**§3.2M MANDATORY MULTI-MARKET CALCULATION (TENNIS):**
Before selecting ANY tennis market, calculate ALL of these:
```
| Market              | PlayerA avg | PlayerB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
|---------------------|-------------|-------------|---------|-------|---------|---------|--------|
| Total games O/U X.5 |             |             |         |       |         |         |        |
| Sets O/U 2.5        |             |             |         |       |         |         |        |
| Game HC -X.5        |             |             |         |       |         |         |        |
| Tiebreaks O/U 0.5   |             |             |         |       |         |         |        |
| Aces O/U X.5        |             |             |         |       |         |         |        |
```
Pick the market with HIGHEST safety score. **Surface-filter H2H is mandatory** (only same-surface meetings count).

**§3.2F PLAYER IDENTITY (MANDATORY):** Full first+last name, country, exact ranking. No slashes/abbreviations. Verify WC/Q/LL status.

**§3.2G WILDCARD BLOWOUT RULE:** WC/Q/LL vs seeded (top 30) in R1/R2:
- BINARY outcomes: 55-65% blowout (≤17 games), rest competitive
- P(≤16 games) = 40-50% for WC matches
- **O22.5+ = HARD REJECT**, O21.5 reject unless both within 20 ranking spots, O20.5 max with STRONG ratio
- Equal odds ≠ close match (uncertainty ≠ competitiveness)

### §3.3 Basketball

**Required stats:**

| Category | Metrics | Source |
|----------|---------|--------|
| Pace | Possessions/game, League rank, Last 10 pace | ESPN, NBA.com (NBA); BetExplorer, Flashscore (EU) |
| Offense | OFF rating, FG%, 3PT%, FT rate, TO/game | Basketball-Reference (NBA); Flashscore, Sofascore (EU) |
| Defense | DEF rating, Opp FG%, Opp 3PT%, Steals, Blocks | Basketball-Reference (NBA); Flashscore, Sofascore (EU) |
| Totals | Team pts/game, Opp pts/game, Combined avg, O/U hit rates | ESPN, Flashscore (NBA); BetExplorer standings, SportsGambler (EU) |
| Home/Away | Pts scored H/A, Pts allowed H/A, ATS record | ESPN (NBA); BetExplorer, Flashscore (EU) |

**Market decision:** Team totals → Quarter totals → Game totals O/U → Spreads → ML (LAST RESORT). Both top-10 pace → O-totals. Playoff = 3-5 fewer points avg.
**WHY points/totals > ML:** Points accumulate every possession (80-100 per team per game), driven by PACE (structural team trait). A team losing by 20 still scores 85+ points. ML depends on who has the better 4th quarter run — high variance.

**§3.3M MANDATORY MULTI-MARKET CALCULATION (BASKETBALL):**
Before selecting ANY basketball market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|-------|---------|---------|--------|
| Team pts O/U X.5     |           |           |         |       |         |         |        |
| Total pts O/U X.5    |           |           |         |       |         |         |        |
| Q1 total O/U X.5     |           |           |         |       |         |         |        |
| 1H total O/U X.5     |           |           |         |       |         |         |        |
| Spread X.5           |           |           |         |       |         |         |        |
```
Pick the market with HIGHEST safety score. **For EU leagues**: use BetExplorer PF/PA + Flashscore H2H scoring, NOT Basketball-Reference.

**Context:** Star player availability (DAY OF check), B2B (−3-5 pts), travel, altitude (Denver), playoff implications.

**EU leagues (BBL, ACB, BSL, VTB, ABA, etc.):** Use BetExplorer standings for PF/PA totals + H/A splits. Use Flashscore/Sofascore for H2H, form, and last 5/10 game scores. Use SportsGambler for written previews where available. Basketball-Reference and NBA.com are NBA-only — do NOT cite them for EU basketball.

### §3.4 Hockey

**Required stats:**

| Category | Metrics | Source |
|----------|---------|--------|
| xG | xGF/game, xGA/game, xG%, xG vs actual delta | NaturalStatTrick, MoneyPuck |
| Goals | GF/game, GA/game, Combined avg, O/U 5.5/6.5 hit rate | ESPN, Flashscore |
| PP/PK | PP%, PP opportunities/game, PK%, PIM/game | ESPN, NHL.com |
| Corsi/Fenwick | CF%, FF% (possession proxy) | NaturalStatTrick |
| Goalie | Save%, GAA, Last 5 starts, vs this opponent (CRITICAL) | DailyFaceoff, ESPN |

**Market decision:** Period totals → Game totals O/U → Puck line → ML (LAST RESORT). Both xGF>3.0 → O-totals. Both goalies sv%<.910 → O-totals. Playoff = 0.5-1.0 fewer goals.

**Context:** GOALIE CONFIRMED? (DailyFaceoff — #1 variable), B2B (+0.3 GA), playoff context, trade deadline.

**§3.4M MANDATORY MULTI-MARKET CALCULATION (HOCKEY):**
Before selecting ANY hockey market, calculate ALL of these:
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|------|---------|---------|--------|
| Period 1 total O/U   |           |           |         |      |         |         |        |
| Game total O/U X.5   |           |           |         |      |         |         |        |
| Shots O/U X.5        |           |           |         |      |         |         |        |
| PP goals O/U 0.5     |           |           |         |      |         |         |        |
| Puck line ±1.5       |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score. **For NHL**: use NaturalStatTrick xG + MoneyPuck. **For other leagues** (DEL, SHL, KHL, Liiga): use Flashscore + BetExplorer. GOALIE IDENTITY is critical — re-evaluate ALL markets if goalie changes after analysis.

### §3.5 Volleyball

**Required stats:** Sets won/lost, Avg sets/match, O/U 3.5 hit rate, Avg total pts/match, Attack efficiency%, Reception%, Tiebreak (5th set) frequency. Sources: Flashscore, Sofascore, CEV/PlusLiga.

**Market decision:** Set score O/U → Total pts O/U → Set totals O/U 3.5 → Set HC → ML (LAST RESORT, 1.50-2.50 range). Both top-6 = O3.5 sets. Big mismatch = U3.5/HC -1.5.
**WHY sets/points > ML:** Sets and points accumulate through rallies (driven by reception% and attack efficiency — structural). A losing team still wins 1-2 sets and scores 80+ points per set. ML depends on clutch 5th-set performance — high variance.

**§3.5M MANDATORY MULTI-MARKET CALCULATION (VOLLEYBALL):**
Before selecting ANY volleyball market, calculate ALL of these:
```
| Market              | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|---------------------|-----------|-----------|---------|------|---------|---------|--------|
| Total sets O/U 3.5  |           |           |         |      |         |         |        |
| Total pts O/U X.5   |           |           |         |      |         |         |        |
| Set HC -1.5/+1.5    |           |           |         |      |         |         |        |
| Pts/set O/U X.5     |           |           |         |      |         |         |        |
```
Pick the market with HIGHEST safety score.

### §3.6 Esports — ARCHIVED (removed from pipeline v4)

### §3.7 Snooker — ARCHIVED (removed from pipeline v4)

### §3.8 Darts — ARCHIVED (removed from pipeline v4)

### §3.9 Handball — ARCHIVED (removed from pipeline v4)

### §3.10 Table Tennis — ARCHIVED (removed from pipeline v4)

### §3.11 MMA/UFC — ARCHIVED (removed from pipeline v4)

### §3.12 Baseball (MLB) — ARCHIVED (removed from pipeline v4)

### §3.13 Padel — ARCHIVED (removed from pipeline v4)

### §3.14 Speedway — ARCHIVED (removed from pipeline v4)

---

## §6.5 UPSET RISK CHECKLISTS

Run for EVERY candidate BEFORE approving. Score on sport-specific checklist. If score ≥ threshold → ML BANNED.

**THE PARADOX RULE:** High upset risk → competitive match → MORE total play → prefer OVER totals. Low upset risk → blowout → OVERS FAIL → prefer UNDER/HC.

**Thresholds:** Tennis ≥4, Football ≥4, Basketball ≥3, Hockey ≥3, Volleyball ≥3.

### Tennis (0-12, threshold ≥4)
1. Surface mismatch (0-2): Favorite's surface win% 10%+ lower?
2. Rising underdog (0-2): Career-high ranking in last 4 weeks? Recent title?
3. Giant-killer history (0-1): Top-20 scalps in 12 months?
4. Age/trajectory (0-1): Underdog ≤22 breakthrough, favorite ≥30 declining?
5. Tournament history (0-1): Favorite best result worse than QF here?
6. Qualifier match fitness (0-0.5): Q through qualifying (match-sharp)?
7. First H2H (0-0.5): Unknown matchup dynamics.
8. Serve dependency on slow surface (0-1): Big server on clay?
9. Altitude (0-0.5): Madrid 660m — serve advantage partially restored.
10. Previous round fatigue (0-0.5): Grueling 3-setter yesterday?
11. Late-career complacency (0-0.5): Favorite 28+ in R1/R2?
12. Return game strength (0-0.5): Underdog high return pts won%?
13. Sharp money signal (0-0.5): Line toward underdog despite public?
14. Draw look-ahead (0-0.5): Favorite has easy draw → trap game?

### Football (0-14, threshold ≥4)
1. Fixture congestion (0-2): Played <72h ago, CL/EL midweek?
2. Relegation desperation (0-1.5): Underdog fighting drop?
3. Cup/league priority split (0-1): Cup semi/final in <5 days?
4. Away form gap (0-1): Favorite away win% <40%?
5. New manager bounce (0-1.5): Underdog changed manager in 3 matches?
6. H2H bogey (0-1): Underdog won 3+ of last 5 at venue?
7. Key absences ≥2 (0-1.5): Favorite missing 2+ starters?
8. Nothing to play for (0-1): Already safe/champion/qualified?
9. International break return (0-1): First match after break?
10. Derby (0-1): Local rivalry defies form.
11. Altitude (0-0.5): Match at altitude (La Paz, Quito)?
12. Artificial turf (0-0.5): Home synthetic pitch?

### Basketball (0-10, threshold ≥3)
1. B2B 2nd night (0-2): −2 to −4 pts expected.
2. Star questionable (0-2): Top-2 scorer GTD?
3. Schedule fatigue (0-1): 4-in-5 or 5-in-7?
4. Travel >1500km in 48h (0-1)
5. Playoff series shift (0-1): G3/G4 after 2-0 lead?
6. Blowout reversal (0-1): Won by 20+ last game → regression.
7. Altitude Denver (0-0.5)
8. OT previous game (0-0.5): 40+ min for key players.
9. Coach revenge (0-0.5)
10. Post-trade disruption (0-1): Major trade in 7 days?

### Hockey (0-10, threshold ≥3)
1. Goalie uncertain/backup (0-2): 5-8% worse save rate.
2. B2B fatigue (0-2): Backup goalie likely + skater fatigue.
3. PP/PK regression (0-1): 30%+ PP in last 10 → regresses to 20%.
4. Road playoff G3+ (0-1)
5. Elimination desperation (0-1): Goalies stand on their heads.
6. 3-in-4 nights (0-1)
7. Empty net adjustment (0-0.5)
8. Revenge game (0-0.5)

### Baseball — ARCHIVED (removed from pipeline v4)

### Volleyball (0-7, threshold ≥3)
1. Playoff context (0-1.5), 2. European travel (0-1), 3. New setter (0-1.5), 4. Home crowd (0-1), 5. Rest rotation (0-1), 6. 5th set record (0-1)

### Esports — ARCHIVED (removed from pipeline v4)

### Snooker — ARCHIVED (removed from pipeline v4)

### MMA — ARCHIVED (removed from pipeline v4)

### Darts — ARCHIVED (removed from pipeline v4)

### Handball — ARCHIVED (removed from pipeline v4)

### Table Tennis — ARCHIVED (removed from pipeline v4)

### Padel — ARCHIVED (removed from pipeline v4)

### Speedway — ARCHIVED (removed from pipeline v4)

### Decision Matrix (ALL SPORTS)

| Score | ML? | Statistical Markets | Over Totals | Under/HC | Confidence |
|-------|-----|---------------------|-------------|----------|------------|
| 0-1 | Yes (if criteria met) | Full range | Caution: blowout risk | Preferred | No change |
| 2-3 | Caution (−1) | Preferred | Moderate | Good | −0.5 |
| 4-5 | **BANNED** | **ONLY option** | **PREMIUM** (Paradox) | OK | −1 |
| 6-7 | **BANNED** | Conservative only | Only STRONG ratio | Preferred | −1.5 |
| 8+ | **BANNED + SKIP** | Only STRONG source | **AVOID** | Skip | −2 |

---

## §7.3 INSTANT RED FLAG CHECKS (30 seconds each, EVERY pick)

### Tennis
| T1 | WC/Q/LL status? → O22.5+ HARD REJECT |
| T2 | Previous round fatigue (3h+ / 3 sets)? → UNDER bias, −1 |
| T3 | First match on new surface? → −1 |
| T4 | Defending champion R1/R2? → −1 |
| T5 | Ambiguous names/slashes? → STOP, verify |
| T6 | Odds drift >8%? → Mandatory re-eval |

### Football
| F1 | Dead rubber? → SKIP ML, UNDER bias, −2 |
| F2 | Cup rotation (CL/EL in 5 days)? → −2, form invalid |
| F3 | Derby? → Form irrelevant, BTTS/U2.5 safer |
| F4 | International break return? → −1 |
| F5 | Promoted + synthetic pitch? → Adjust totals |
| F6 | Referee not checked (cards/fouls pick)? → STOP |

### Basketball
| B1 | B2B? → UNDER bias (−3-5 pts) |
| B2 | Star GTD/resting? → Check ≤1h before |
| B3 | Tank mode? → SKIP |
| B4 | Elimination game? → OVER bias |

### Hockey
| H1 | Backup goalie? → sv% drops 3-5%, OVER bias |
| H2 | B2B? → +0.5 GA |
| H3 | 0-3 in series? → 4% comeback rate |
| H4 | Goalie unconfirmed (totals pick)? → WAIT or SKIP |

### Volleyball
| VB1 | Playoff clinched? → Rotation, −1 |
| VB2 | 5th set to 15? → Verify line |
| VB3 | Home crowd >70%? → Factor into ML/spread |

### Esports — ARCHIVED (removed from pipeline v4)

### Snooker — ARCHIVED (removed from pipeline v4)

### Darts — ARCHIVED (removed from pipeline v4)

### Handball — ARCHIVED (removed from pipeline v4)

### Table Tennis — ARCHIVED (removed from pipeline v4)

### MMA — ARCHIVED (removed from pipeline v4)

### Padel — ARCHIVED (removed from pipeline v4)

### Speedway — ARCHIVED (removed from pipeline v4)
