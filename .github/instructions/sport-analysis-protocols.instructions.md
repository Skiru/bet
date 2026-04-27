---
applyTo: ""
---

# Sport-Specific Analysis Protocols — Reference Document

> **This file is loaded ON DEMAND, not auto-loaded.** It contains detailed per-sport statistical protocols, upset risk checklists, and instant red flag tables. The agent loads it when performing deep analysis (STEP 3+).
>
> **Sport Tiers:** KEY (Tier 1) = Football, Volleyball, Basketball, Tennis — scan ALL leagues/divisions deeply. SUPPORT (Tier 2) = all others — scan main leagues/tournaments. Analysis depth is identical for all candidates regardless of tier.

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

**Context (MANDATORY):** Coach change (TransferMarkt), injuries/suspensions (ESPN, Flashscore), fixture congestion (<72h), motivation (relegation/title/dead rubber), weather (rain/wind→corners), referee stats (cards/fouls).

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
| Pace | Possessions/game, League rank, Last 10 pace | ESPN, NBA.com |
| Offense | OFF rating, FG%, 3PT%, FT rate, TO/game | Basketball-Reference |
| Defense | DEF rating, Opp FG%, Opp 3PT%, Steals, Blocks | Basketball-Reference |
| Totals | Team pts/game, Opp pts/game, Combined avg, O/U hit rates | ESPN, Flashscore |
| Home/Away | Pts scored H/A, Pts allowed H/A, ATS record | ESPN |

**Market decision:** Team totals → Quarter totals → Game totals O/U → Spreads → ML (LAST RESORT). Both top-10 pace → O-totals. Playoff = 3-5 fewer points avg.

**Context:** Star player availability (DAY OF check), B2B (−3-5 pts), travel, altitude (Denver), playoff implications.

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

### §3.5 Volleyball

**Required stats:** Sets won/lost, Avg sets/match, O/U 3.5 hit rate, Avg total pts/match, Attack efficiency%, Reception%, Tiebreak (5th set) frequency. Sources: Flashscore, Sofascore, CEV/PlusLiga.

**Market decision:** Set score O/U → Total pts O/U → Set totals O/U 3.5 → Set HC → ML (LAST RESORT, 1.50-2.50 range). Both top-6 = O3.5 sets. Big mismatch = U3.5/HC -1.5.

### §3.6 Esports (CS2/LoL/Dota2/Valorant)

**Required stats:** Map pool overlap + win rates, Avg rounds/map, Pistol round win%, K/D rating, CT/T splits (CS2), Game duration + objectives (LoL/Dota2). Sources: HLTV stats (NOT tips), Liquipedia, GosuGamers, VLR.gg.

**Market decision:** Round totals O/U → Map totals O/U 2.5 (BO3) → Map HC -1.5 → Kill totals → ML (LAST RESORT). BO1 = massive upset risk, reduce confidence -1.

**Context:** Stand-in player? New patch <2 weeks? Online vs LAN? BO1 format?

### §3.7 Snooker

**Required stats:** Frame win%, Century breaks/match, 50+ breaks/match, Frame duration, Decider frame record, Form (last 10). Sources: CueTracker (PRIMARY), WorldSnooker, Flashscore.

**Market decision:** Century O/U → Frame totals O/U → Frame HC → Correct score → ML (LAST RESORT). Both within 15 spots → O frames. Both >18min/frame → O frames (tactical).

### §3.8 Darts

**Required stats:** 3-dart average (>95 elite), Checkout%, 180s/match, Leg totals, Break of throw%. Sources: DartsOrakel (PRIMARY), PDC.tv, Flashscore.

**Market decision:** 180s O/U → Leg totals O/U → Set totals → Correct score → ML (LAST RESORT). Both avg >95 → more breaks → O legs. Floor events = higher upset rate.

### §3.9 Handball

**Required stats:** Goals scored/match, Conceded/match, Combined avg, Goalkeeper save%, Suspensions/match, Half splits (2nd half +1-2 goals), Home/Away (60-65% home win). Sources: Flashscore, EHF/eurohandball.

**Market decision:** Half totals O/U → Game total goals O/U → HC → ML (LAST RESORT). Both >28 scored → O totals. HOME ADVANTAGE is extreme.

### §3.10 Table Tennis

**Required stats:** Ranking, Avg sets/match, Set win%, Points/set, Style (attacking/defensive), Form. Sources: ITTF, Flashscore, tt-series.com.

**Market decision:** Total pts O/U → Set totals O/U → Set HC → ML (LAST RESORT). Close ranking (<20 spots) → O sets. HIGH-VARIANCE — reduce confidence -0.5.

### §3.11 MMA/UFC

**Required stats:** Sig strikes/min, Strike accuracy%, TD accuracy%, TD defense%, Finish rate (KO/Sub/Dec split), Record vs ranked. Sources: UFC.com/stats, Sherdog, Tapology.

**Market decision:** Method of victory → O/U rounds → Round betting → ITD → ML (LAST RESORT). Both finish >50% → U rounds. Both decision >50% → O rounds. HW = highest KO variance.

**Context:** Weight cut issues, layoff >12mo, camp change, reach advantage.

### §3.12 Baseball (MLB)

**Required stats:** SP: ERA, WHIP, xERA, K/9, BB/9, Hard hit%, Barrel%, vs LHB/RHB splits, last 3-5 starts. Bullpen: ERA last 7/14/30 days, innings last 3 days, closer availability. Offense: R/game, OPS, wRC+, BABIP, K rate, vs LHP/RHP. Sources: BaseballSavant (PRIMARY — FanGraphs BLOCKED), Baseball-Reference, ESPN.

**Market decision:** F5 totals O/U → Team totals → Game totals O/U → Run line → ML (LAST RESORT). F5 removes bullpen variance = most reliable. Both SP xERA >4.50 → O runs.

**Context:** WEATHER CRITICAL (wind at Wrigley/Coors = +1.5 runs), park factor, day-after-night, umpire K-rate.

### §3.13 Padel

**Required stats:** FIP world ranking (both pairs), Ranking gap, Partnership duration (>6mo = stable), Avg sets/match, 3-set%, O/U game totals. Sources: PadelFIP (PRIMARY), PremierPadel, Sofascore padel.

**Market decision:** Game totals O/U → Set totals O/U 2.5 → Set HC → ML (LAST RESORT, ranking gap >3000 only). Gap <1000 → O2.5 sets. New partnership = volatility.

**Context:** Tournament tier (Major/P1/P2/Bronze), indoor vs outdoor (wind disrupts lobs), fatigue from 3-set previous match.

### §3.14 Speedway

**Required stats:** Rider avg at THIS TRACK (most important), Season avg, Team match avg (home/away), Junior (U24) slot contribution, Heat leader performance. Sources: SpeedwayEkstraliga (PRIMARY), SportoweFakty.

**Market decision:** Total pts O/U → HC → Match winner (LAST RESORT, usually too short at 1.20-1.40). HOME ADVANTAGE = 70-75%. Calculate team total from rider track-specific averages.

**Context:** LINEUP CONFIRMATION (SportoweFakty, 2-3h before — rider out = 6-10 pts lost), weather (rain = chaos), track preparation bias, junior rider rule.

---

## §6.5 UPSET RISK CHECKLISTS

Run for EVERY candidate BEFORE approving. Score on sport-specific checklist. If score ≥ threshold → ML BANNED.

**THE PARADOX RULE:** High upset risk → competitive match → MORE total play → prefer OVER totals. Low upset risk → blowout → OVERS FAIL → prefer UNDER/HC.

**Thresholds:** Tennis ≥4, Football ≥4, Basketball ≥3, Hockey ≥3, Baseball ≥3, Volleyball ≥3, Esports ≥2, Snooker ≥2, Darts ≥2, MMA ≥3, Handball ≥3, Table Tennis ≥2, Padel ≥3, Speedway ≥3.

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

### Baseball (0-10, threshold ≥3)
1. SP ERA>4.50 or rookie (0-2)
2. Bullpen fatigue (0-1.5): 6+ IP in 2 days?
3. Platoon advantage (0-1)
4. Day after night (0-1)
5. Key batter sitting (0-1)
6. Umpire factor (0-1)
7. Weather at ballpark (0-1): Wind blowing out = +1.5 runs.
8. Cross-country travel (0-0.5)

### Volleyball (0-7, threshold ≥3)
1. Playoff context (0-1.5), 2. European travel (0-1), 3. New setter (0-1.5), 4. Home crowd (0-1), 5. Rest rotation (0-1), 6. 5th set record (0-1)

### Esports (0-10, threshold ≥2)
1. Stand-in (0-2), 2. Map pool edge (0-1.5), 3. Online match (0-1), 4. New patch <2wks (0-1.5), 5. BO1 format (0-1.5), 6. LAN/online gap (0-1), 7. Coach ban (0-0.5), 8. Regional style (0-0.5)

### Snooker (0-7, threshold ≥2)
1. Short format BO7/BO9 (0-1.5), 2. Form discrepancy (0-1), 3. Safety-heavy underdog (0-1), 4. WC R1 pressure (0-1), 5. Multi-session (0-1), 6. Jet lag (0-0.5), 7. Table conditions (0-0.5)

### MMA (0-10, threshold ≥3)
1. Stylistic mismatch (0-2), 2. Long layoff >12mo (0-1.5), 3. Weight class move (0-1), 4. Short notice (0-1), 5. Heavyweight (0-1), 6. Bad weight cut (0-1), 7. Southpaw/Orthodox (0-0.5), 8. Altitude (0-0.5), 9. Camp issues (0-0.5)

### Darts (0-7, threshold ≥2)
1. Floor event (0-1.5), 2. Short format (0-1), 3. Checkout slump (0-1), 4. Underdog avg >95 (0-1), 5. Multiple matches (0-1), 6. Home crowd (0-0.5)

### Handball (0-7, threshold ≥3)
1. European midweek (0-1.5), 2. Home advantage (0-1.5), 3. Goalkeeper form (0-1), 4. Derby (0-1), 5. Key pivot absent (0-1), 6. 7v6 play (0-0.5)

### Table Tennis (0-6, threshold ≥2)
1. Ranking gap <20 (0-1.5), 2. Multiple matches/day (0-1), 3. Style mismatch (0-1), 4. Equipment change (0-0.5), 5. Asian vs European (0-0.5), 6. Tournament round (0-0.5)

### Padel (0-8, threshold ≥3)
1. New partnership (0-2), 2. Ranking gap <1000 (0-1.5), 3. Surface change (0-1), 4. R32/R16 (0-1), 5. Altitude (0-0.5), 6. Wind outdoor (0-1), 7. Fatigue (0-0.5)

### Speedway (0-8, threshold ≥3)
1. Track preparation bias (0-2), 2. Rider injury/change (0-1.5), 3. Weather/wet track (0-1), 4. Junior rider weakness (0-1), 5. Away "good traveler" (0-1), 6. Equipment failure (0-0.5), 7. Guest rider unfamiliarity (0-0.5)

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

### Baseball
| BB1 | Bullpen game/opener? → +1.5 runs, OVER |
| BB2 | MLB debut pitcher? → OVER, −1 |
| BB3 | Wind blowing out (Wrigley/Coors)? → +2 runs, OVER |
| BB4 | Day after night? → −1 |

### Volleyball
| VB1 | Playoff clinched? → Rotation, −1 |
| VB2 | 5th set to 15? → Verify line |
| VB3 | Home crowd >70%? → Factor into ML/spread |

### Esports
| E1 | Stand-in? → Underdog value rises |
| E2 | New patch <2wks? → +30-40% upset rate, SKIP ML |
| E3 | Online vs LAN mismatch? → 20%+ gap |
| E4 | BO1? → Massive upset rate |

### Snooker
| S1 | Long-format fatigue (10+ frames)? → UNDER frames |
| S2 | Morning session? → Check player patterns |
| S3 | Century frequency mismatch? → Affects frame totals |

### Darts
| D1 | Sets vs legs format? → Different dynamics |
| D2 | Premier League vs ranking event? → Different motivation |
| D3 | Both top-10 in 180s? → OVER 180s |

### Handball
| HB1 | CL/EHF midweek? → Rotation, −1 |
| HB2 | 7m specialist absent? → Affects total goals |

### Table Tennis
| TT1 | Division gap in cup? → Blowout, UNDER |
| TT2 | BO5 vs BO7? → Verify line format |
| TT3 | Withdrawal history? → Avoid |

### MMA
| MMA1 | Late opponent change (<2wks)? → −1 |
| MMA2 | Failed weight cut? → Grappler advantage |
| MMA3 | Layoff >1 year? → Ring rust, −1 |
| MMA4 | Reach advantage >6"? → Decisions more likely |

### Padel
| PD1 | New pair (<3 events)? → OVER sets, ML volatile |
| PD2 | Outdoor + wind? → More breaks, totals UP |
| PD3 | FIP gap <500? → SKIP ML |

### Speedway
| SP1 | Rain/wet? → UNDER everything, −1 |
| SP2 | Rider track record checked? → Individual > overall |
| SP3 | Junior rider in key heat? → Lower team score |
