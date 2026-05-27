# Sport-Specific Analysis Protocols (Condensed)

> Load ON DEMAND for deep S3+ analysis. All 5 core sports + 3 esports are Tier 1.

## Market Hierarchies (STAT MARKETS FIRST)

| Sport | Hierarchy (left = best) |
|-------|------------------------|
| Football | Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 |
| Tennis | Game totals O/U → Set totals O/U → Game HC → Set HC → ML |
| Basketball | Team pts O/U → Quarter totals → Game totals → Spreads → ML |
| Hockey | Shots O/U → Hits O/U → Blocks O/U → PIM O/U → PP Goals → Game totals → Puck line → ML |
| Volleyball | Set score O/U → Total pts O/U → Set totals O/U 3.5 → Set HC → ML |
| Esports | ML → Map HC → Total Maps → Round HC |

> **Betclic placement note:** Hierarchy above is for ANALYSIS ranking (determining best statistical edge). For Betclic placement, use available markets (Goals O/U, BTTS, Handicap, 1X2, Player props, Red Card Y/N) with the same statistical rigor. Fouls/Corners/Cards/Team Shots totals are NOT available on Betclic.

---

## Mandatory Multi-Market Calculation

Before selecting ANY market, fill the sport-specific table with ALL available markets, then pick HIGHEST safety score. Never default to one market without checking alternatives.

### Football §3.1M
```
| Market           | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
| Fouls O/U X.5   |           |           |         |      |         |         |        |
| Cards O/U X.5   |           |           |         |      |         |         |        |
| Corners O/U X.5 |           |           |         |      |         |         |        |
| Shots O/U X.5   |           |           |         |      |         |         |        |
| Goals O/U X.5   |           |           |         |      |         |         |        |
```
**Close Game Rule (ZT#24):** P(draw)≥25% + foul/card UNDER + avg within ±1.5 of line → DO NOT BET. Pick alternative market.

### Tennis §3.2M
```
| Market              | PlayerA avg | PlayerB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
| Total games O/U X.5 |             |             |         |       |         |         |        |
| Sets O/U 2.5        |             |             |         |       |         |         |        |
| Game HC -X.5        |             |             |         |       |         |         |        |
```
**Surface-filter H2H mandatory** (only same-surface meetings). WC/Q/LL vs top 30: O22.5+ = HARD REJECT.

### Basketball §3.3M
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
| Team pts O/U X.5     |           |           |         |       |         |         |        |
| Total pts O/U X.5    |           |           |         |       |         |         |        |
| Q1 total O/U X.5     |           |           |         |       |         |         |        |
| Spread X.5           |           |           |         |       |         |         |        |
```
**EU leagues:** Use BetExplorer PF/PA + Flashscore H2H (NOT Basketball-Reference). Lines are league-specific (NBA ~220, NBB ~160, Women ~150).

### Hockey §3.4M
```
| Market               | TeamA avg | TeamB avg | H2H avg | Line  | Hit L10 | Hit H2H | Safety |
| Total Shots O/U      |           |           |         | 60.5  |         |         |        |
| Total Hits O/U       |           |           |         | 45.5  |         |         |        |
| Total Blocks O/U     |           |           |         | 28.5  |         |         |        |
| Total Goals O/U      |           |           |         | 5.5   |         |         |        |
```
**GOALIE CONFIRMED?** Re-evaluate ALL markets if goalie changes. Canonical source: api-hockey. MoneyPuck = advisory only.

### Volleyball §3.5M
```
| Market              | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
| Total sets O/U 3.5  |           |           |         |      |         |         |        |
| Total pts O/U X.5   |           |           |         |      |         |         |        |
| Set HC -1.5/+1.5    |           |           |         |      |         |         |        |
```

### Esports §3.6M
```
| Market              | Home L10  | Away L10  | H2H (5m) | Line | Hit% | Safety |
| ML (Match Winner)   |           |           |           |      |      |        |
| Map HC ±1.5         |           |           |           |      |      |        |
| Total Maps O/U 2.5  |           |           |           |      |      |        |
```
**Roster changes = critical.** One stand-in drops WR 20%+. Bo1 = high variance (prefer HC or skip).

---

## Upset Risk Scoring

Run for EVERY candidate BEFORE approving. If score ≥ threshold → ML BANNED.

**THE PARADOX RULE:** High upset risk → competitive → MORE total play → prefer OVER totals.

| Sport | Threshold | Checklist Range |
|-------|-----------|-----------------|
| Tennis | ≥4 | 0-12 |
| Football | ≥4 | 0-14 |
| Basketball | ≥3 | 0-10 |
| Hockey | ≥3 | 0-10 |
| Volleyball | ≥3 | 0-7 |

### Key Upset Factors (abbreviated)
- **Tennis:** Surface mismatch, rising underdog, giant-killer history, WC/Q match fitness
- **Football:** Fixture congestion <72h, relegation desperation, cup priority, derby, new manager bounce
- **Basketball:** B2B 2nd night (-2 to -4 pts), star GTD, schedule fatigue, Denver altitude
- **Hockey:** Goalie uncertain (+5-8% GAA), B2B, PP/PK regression, elimination desperation
- **Volleyball:** Playoff context, European travel, new setter

---

## Instant Red Flags §7.3

| Sport | Flag | Action |
|-------|------|--------|
| Tennis | WC/Q/LL status | O22.5+ HARD REJECT |
| Tennis | Previous round fatigue 3h+ | UNDER bias, −1 |
| Tennis | First match on new surface | −1 |
| Football | Dead rubber | SKIP ML, UNDER bias, −2 |
| Football | Cup rotation (CL/EL in 5 days) | −2, form invalid |
| Football | Derby | Form irrelevant, BTTS/U2.5 safer |
| Football | Close Game + foul/card UNDER | FLAG ZT#24, −1.0 safety |
| Basketball | Star ruled out post-line | Re-evaluate ALL markets |
| Hockey | Backup goalie confirmed | +0.5 goals expected |

---

## Context Requirements (MANDATORY per sport)

| Sport | Must Check |
|-------|-----------|
| Football | Coach change, injuries (2+), fixture congestion, motivation, weather, referee stats |
| Tennis | Previous round score/duration, surface form THIS YEAR, ranking trajectory |
| Basketball | Star availability DAY OF, B2B status, travel distance, playoff implications |
| Hockey | GOALIE CONFIRMED (DailyFaceoff), B2B, playoff context |
| Volleyball | Setter availability, European schedule, playoff/cup context |
| Esports | Roster (stand-ins?), patch recency, map pool overlap |

---

## Source Priorities

| Sport | Primary | Fallback |
|-------|---------|----------|
| Football | Flashscore + SoccerStats + TotalCorner | Soccerway, ESPN |
| Tennis | TennisAbstract + Flashscore | Sackmann CSV |
| Basketball (NBA) | Basketball-Reference + ESPN | Flashscore |
| Basketball (EU) | BetExplorer + Flashscore | SportsGambler |
| Hockey | api-hockey (canonical) + MoneyPuck (advisory) | ESPN |
| Volleyball | Flashscore + CEV/PlusLiga | — |
| Esports | bo3.gg + VLR.gg (Valorant) + HLTV (CS2) | Liquipedia |

---

## Betclic Market Availability (CRITICAL)

**Confirmed available:** Goals O/U, BTTS, Handicap, 1X2, Double Chance, Player props, Red Card Y/N
**NOT available (despite Statystyki tab):** Corners O/U, Fouls O/U, Team Shots O/U, Cards Total O/U

**Rule:** When stat markets unavailable on Betclic, evaluate Goals O/U, BTTS, Handicap with same statistical rigor. Use STATS-FIRST mode (probability portfolio) for picks where Betclic odds need manual verification.
