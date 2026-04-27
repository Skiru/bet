# Sport-Specific Detailed Protocols

Reference file for `bet-applying-sport-protocols` skill. Load when performing deep analysis (S3+) for specific sports.

---

## §3.1 Football

**Required stats (split Home/Away):**

| Category | Metrics | Source |
|----------|---------|--------|
| Goals | Scored/match, Conceded/match, O2.5%, BTTS%, Clean sheets% | SoccerStats, Sofascore |
| xG | xGF/match, xGA/match, xG vs actual delta | Flashscore, Sofascore |
| Corners | Team earned/match, Conceded/match, Total match avg, O9.5/O10.5 hit rate | TotalCorner + SoccerStats |
| Cards | Team cards/match, Opponent cards/match, O3.5/O4.5 hit rate | SoccerStats, Betaminic |
| Fouls | Committed/match, Drawn/match, Total match avg | SoccerStats, Sofascore |
| Shots | Shots/match, SOT/match, Conversion%, O/U team shots hit rates | Sofascore, Flashscore |
| Possession | Possession%, Throw-ins/match | Sofascore |

**Corner picks — THREE-SOURCE STACK:**
1. TotalCorner: match-level corner total predictions + handicaps
2. SoccerStats: league corner rankings (team averages home/away)
3. Betclic Statystyki: verified corner odds (top leagues: EPL, LaLiga, Bundesliga only)

**§3.1M MANDATORY MULTI-MARKET CALCULATION:**
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

**Context (MANDATORY):** Coach change (TransferMarkt), injuries/suspensions (ESPN, Flashscore), fixture congestion (<72h), motivation, weather (rain/wind→corners), referee stats (cards/fouls).

**Upset risk factors** (threshold ≥4, max 8):
Derby/rivalry, Cup rotation (CL/EL <5d), Dead rubber, International break return, Key player suspended/injured, Synthetic/unusual pitch, Manager recently fired/appointed, Travel fatigue.

---

## §3.2 Tennis

**Required stats per player:**

| Category | Metrics | Source |
|----------|---------|--------|
| Elo | Overall, Surface-specific, trajectory | TennisAbstract |
| Serve | 1st serve%, 1st serve pts won%, 2nd serve pts won%, Aces/match, DFs/match, Hold% | TennisAbstract, Flashscore |
| Return | Return pts won%, BP converted%, Return games won% | TennisAbstract |
| Games | Avg games/set, Avg total games/match, O/U 20.5/21.5/22.5 hit rate | Flashscore match history |
| Sets | 3-set match%, Tiebreak frequency%, Sets won from behind% | Flashscore |
| Surface form | Win% on this surface THIS YEAR, vs Top 20/50/100 | TennisAbstract |
| Previous round | Score, games, duration, physical condition | Flashscore |

**Odds ratio grading:**
≤1.15=STRONG, 1.16-1.30=GOOD, 1.31-1.50=BORDERLINE, >1.50=REJECT

**§3.2F PLAYER IDENTITY:** Full first+last name, country, exact ranking. No slashes/abbreviations. Verify WC/Q/LL status.

**§3.2G WILDCARD BLOWOUT RULE:**
- WC/Q/LL vs seeded (top 30) in R1/R2: P(≤16 games) = 40-50%
- O22.5+ = HARD REJECT, O21.5 reject unless within 20 ranking spots, O20.5 max with STRONG ratio

**§3.2M MANDATORY MULTI-MARKET CALCULATION:**
```
| Market              | PlayerA avg | PlayerB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
|---------------------|-------------|-------------|---------|-------|---------|---------|--------|
| Total games O/U X.5 |             |             |         |       |         |         |        |
| Sets O/U 2.5        |             |             |         |       |         |         |        |
| Game HC -X.5        |             |             |         |       |         |         |        |
| Tiebreaks O/U 0.5   |             |             |         |       |         |         |        |
| Aces O/U X.5        |             |             |         |       |         |         |        |
```
Surface-filter H2H is mandatory (only same-surface meetings count).

**Upset risk factors** (threshold ≥4, max 12):
Surface mismatch (0-2), Rising underdog (0-2), Giant-killer history (0-1), Age/trajectory (0-1), Favorite tournament history (0-1), Qualifier match fitness (0-0.5), First H2H (0-0.5), Serve dependency on slow surface (0-1), Altitude (0-0.5), Previous round fatigue (0-0.5), Late-career complacency (0-0.5), Return game strength (0-0.5), Sharp money (0-0.5), Draw section look-ahead (0-0.5).

---

## §3.3 Basketball

**Required stats:**

| Category | Metrics | Source |
|----------|---------|--------|
| Pace | Possessions/game, League rank, Last 10 pace | ESPN/NBA.com (NBA); BetExplorer/Flashscore (EU) |
| Offense | OFF rating, FG%, 3PT%, FT rate, TO/game | Basketball-Reference (NBA); Flashscore/Sofascore (EU) |
| Defense | DEF rating, Opp FG%, Opp 3PT%, Steals, Blocks | Same |
| Totals | Team pts/game, Opp pts/game, Combined avg, O/U hit rates | ESPN/Flashscore (NBA); BetExplorer (EU) |
| Home/Away | Pts scored H/A, Pts allowed H/A, ATS record | Same |

Both top-10 pace → O-totals. Playoff = 3-5 fewer points avg.

**EU leagues:** Use BetExplorer PF/PA + Flashscore H2H. Basketball-Reference is NBA-only.

**§3.3M MANDATORY MULTI-MARKET CALCULATION:**
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
|----------------------|-----------|-----------|---------|-------|---------|---------|--------|
| Team pts O/U X.5     |           |           |         |       |         |         |        |
| Total pts O/U X.5    |           |           |         |       |         |         |        |
| Q1 total O/U X.5     |           |           |         |       |         |         |        |
| 1H total O/U X.5     |           |           |         |       |         |         |        |
| Spread X.5           |           |           |         |       |         |         |        |
```

**Context:** Star player availability (DAY OF), B2B (−3-5 pts), travel, altitude (Denver), playoff implications.

**Upset risk factors** (threshold ≥3, max 6):
B2B, Load management, Tank mode, Elimination game, Travel fatigue, Schedule loss.

---

## §3.4 Hockey

**Required stats:**

| Category | Metrics | Source |
|----------|---------|--------|
| xG | xGF/game, xGA/game, xG%, xG vs actual delta | NaturalStatTrick, MoneyPuck |
| Goals | GF/game, GA/game, Combined avg, O/U 5.5/6.5 hit rate | ESPN, Flashscore |
| PP/PK | PP%, PP opportunities/game, PK%, PIM/game | ESPN, NHL.com |
| Corsi/Fenwick | CF%, FF% | NaturalStatTrick |
| Goalie | Save%, GAA, Last 5 starts, vs this opponent | DailyFaceoff, ESPN |

**GOALIE CONFIRMATION (DailyFaceoff) = #1 variable.** Both xGF>3.0 → O-totals. Both sv%<.910 → O-totals. Playoff = 0.5-1.0 fewer goals.

**Upset risk factors** (threshold ≥3, max 6):
Backup goalie, B2B, Down 0-3 in series, Goalie unconfirmed, Travel, Playoff desperation.

---

## §3.5 Volleyball

**Required stats:** Sets won/lost, Avg sets/match, O/U 3.5 hit rate, Avg total pts/match, Attack efficiency%, Reception%, Tiebreak (5th set) frequency. Sources: Flashscore, Sofascore, CEV/PlusLiga.

Both top-6 = O3.5 sets. Big mismatch = U3.5/HC -1.5.

**§3.5M MANDATORY MULTI-MARKET CALCULATION:**
```
| Market              | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|---------------------|-----------|-----------|---------|------|---------|---------|--------|
| Total sets O/U 3.5  |           |           |         |      |         |         |        |
| Total pts O/U X.5   |           |           |         |      |         |         |        |
| Set HC -1.5/+1.5    |           |           |         |      |         |         |        |
| Pts/set O/U X.5     |           |           |         |      |         |         |        |
```

**Upset risk factors** (threshold ≥3, max 6):
Playoff clinched, 5th set to 15, Home crowd >70%, Cup vs league priority, Rotation, Travel.

---

## §3.6 Esports (CS2/LoL/Dota2/Valorant)

**Required stats:** Map pool overlap + win rates, Avg rounds/map, Pistol round win%, K/D rating, CT/T splits (CS2), Game duration + objectives (LoL/Dota2). Sources: HLTV stats (NOT tips), Liquipedia, GosuGamers, VLR.gg.

BO1 = massive upset risk (reduce confidence −1).

**Upset risk factors** (threshold ≥2, max 5):
Stand-in player, New patch <2 weeks, Online vs LAN, BO1 format, Map pool disadvantage.

---

## §3.7 Snooker

**Required stats:** Frame win%, Century breaks/match, 50+ breaks/match, Frame duration, Decider frame record, Form (last 10). Sources: CueTracker, WorldSnooker, Flashscore.

Both within 15 spots → O frames. Both >18min/frame → O frames (tactical).

**Upset risk factors** (threshold ≥2, max 5):
Long-format fatigue, Morning session, Century frequency mismatch, Venue unfamiliarity, Schedule congestion.

---

## §3.8 Darts

**Required stats:** 3-dart average (>95 elite), Checkout%, 180s/match, Leg totals, Break of throw%. Sources: DartsOrakel, PDC.tv, Flashscore.

Both avg >95 → more breaks → O legs. Floor events = higher upset rate.

**Upset risk factors** (threshold ≥2, max 5):
Sets vs legs format confusion, Premier League vs ranking event, 180s power matchup, Floor event, Long travel.

---

## §3.9 Handball

**Required stats:** Goals scored/match, Conceded/match, Combined avg, Goalkeeper save%, Suspensions/match, Half splits (2nd half +1-2 goals), Home/Away (60-65% home win). Sources: Flashscore, EHF.

HOME ADVANTAGE is extreme.

**Upset risk factors** (threshold ≥3, max 6):
European week rotation, 7m specialist absent, Home crowd factor, Key defender suspended, Travel, Season stage.

---

## §3.10 Table Tennis

**Required stats:** Ranking, Avg sets/match, Set win%, Points/set, Style (attacking/defensive), Form. Sources: ITTF, Flashscore, tt-series.com.

Close ranking (<20 spots) → O sets. HIGH-VARIANCE — reduce confidence −0.5.

**Upset risk factors** (threshold ≥2, max 5):
Division gap in cup, BO5 vs BO7, Withdrawal history, Style mismatch, Ranking manipulation.

---

## §3.11 MMA

**Required stats:** Fighter records, Finish rate, Method breakdown (KO/SUB/DEC), Takedown defense%, Significant strikes/min, Reach advantage, Recent layoff. Sources: UFCstats, Tapology, Sherdog.

**Upset risk factors** (threshold ≥3, max 6):
Late opponent change, Failed weight cut, Layoff >1 year, Reach advantage, Chin deterioration, Style nightmare matchup.

---

## §3.12 Padel

**Required stats:** FIP ranking, Partnership duration, Indoor/outdoor surface, Recent form, H2H. Sources: Sofascore, PremierPadel, PadelFIP.

**Upset risk factors** (threshold ≥3, max 6):
New pair <3 events, Indoor vs outdoor switch, FIP gap <500, Travel, Altitude, Surface change.

---

## §3.13 Speedway

**Required stats:** Rider TRACK-SPECIFIC averages (not season avg), Team total, Lineup (7 riders confirmed), Home/away. Sources: SpeedwayEkstraliga, SportoweFakty.

**Upset risk factors** (threshold ≥3, max 6):
Rain/wet track, Rider track record poor, Junior rider rule, Equipment issues, Injury return, Away disadvantage.
