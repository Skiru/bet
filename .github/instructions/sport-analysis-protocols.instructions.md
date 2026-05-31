---
applyTo: ""
---

# Sport-Specific Analysis Protocols

> Loaded ON DEMAND for STEP 3+ analysis. Contains per-sport stat tables, market rankings, upset risk checklists, and red flags.

---

## §3.1 Football

| Required Stat | Source |
|---------------|--------|
| Goals: scored/conceded, O2.5%, BTTS%, xG | SoccerStats, Flashscore |
| Corners: earned/conceded, total avg, O9.5/O10.5 hit rate | TotalCorner, SoccerStats |
| Cards: team/opponent per match, O3.5/O4.5 hit rate | SoccerStats, Betaminic |
| Fouls: committed/drawn, total avg | SoccerStats, Flashscore |
| Shots: shots/SOT per match, O/U hit rates | Flashscore |

**Hierarchy:** Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2

**§3.1M Multi-Market Table (MANDATORY):**
`| Market | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |`
Rows: Fouls O/U, Cards O/U, Corners O/U, Shots O/U, Team CK O/U, Goals O/U. Min 4 rows.

**Red flags:** ① Relegation match ② Manager sacked <7 days ③ 3+ key injuries ④ Cup rotation (CL/EL <5d) ⑤ Dead rubber
**ZT#24:** P(draw)≥25% + fouls/cards UNDER + avg ±1.5 of line → SKIP market.

---

## §3.2 Tennis

| Required Stat | Source |
|---------------|--------|
| Elo: overall + surface-specific | TennisAbstract |
| Serve: 1st%, pts won, aces, DFs, hold% | TennisAbstract, Flashscore |
| Return: pts won%, BP converted% | TennisAbstract |
| Games: avg/set, total/match, O/U hit rates | Flashscore match history |
| Sets: 3-set%, tiebreak freq | Flashscore |
| Surface form: win% this surface this year | TennisAbstract |

**Hierarchy:** Games O/U → Sets O/U → Game HC → Set HC → ML (last resort)
**Odds ratio grades:** ≤1.15=STRONG, 1.16-1.30=GOOD, 1.31-1.50=BORDERLINE, >1.50=REJECT
**WC/Q/LL rule:** vs seeded top 30 → O22.5+ HARD REJECT. Binary blowout risk.

**§3.2M Multi-Market Table:** Total games O/U, Sets O/U 2.5, Game HC, Tiebreaks O/U, Aces O/U. Surface-filter H2H mandatory.

**Red flags:** ① WC/Q/LL status ② Previous round fatigue (3h+) ③ New surface ④ Ambiguous names

---

## §3.3 Basketball

| Required Stat | Source |
|---------------|--------|
| Pace: possessions/game, rank | ESPN (NBA); Flashscore (EU) |
| Offense: OFF rating, FG%, 3PT%, TO/game | Basketball-Ref (NBA); Flashscore (EU) |
| Defense: DEF rating, opp FG%, blocks | Basketball-Ref (NBA); Flashscore (EU) |
| Totals: team pts, opp pts, combined avg, O/U hit rates | ESPN, Flashscore |
| Home/Away: pts H/A, ATS record | ESPN (NBA); BetExplorer (EU) |

**Hierarchy:** Team totals → Quarter totals → Game total O/U → Spreads → ML (last resort)
**Key:** Both top-10 pace → O-totals. Playoff = 3-5 fewer pts. B2B = −3-5 pts.

**§3.3M Multi-Market Table:** Team pts O/U, Total pts O/U, Q1 total O/U, 1H total O/U, Spread.

**Red flags:** ① B2B 2nd night ② Star GTD/resting ③ Tank mode ④ Elimination game (OVER bias)

---

## §3.4 Hockey

| Required Stat | Source |
|---------------|--------|
| Shots: team/against, combined avg | api-hockey (canonical), ESPN |
| Hits: per game H/A, combined | api-hockey |
| Blocks: per game, combined | api-hockey |
| PIM: per game, combined | api-hockey |
| PP/PK: PP goals, PP%, PK% | api-hockey, ESPN |
| Goals: GF/GA, combined, O/U 5.5/6.5 | ESPN, api-hockey |
| Goalie: save%, GAA, last 5 starts | DailyFaceoff, ESPN |

**Hierarchy:** Shots O/U → Hits O/U → Blocks O/U → PIM O/U → PP Goals → Game total → Puck line → ML
**Key:** GOALIE IDENTITY is #1 variable. Re-evaluate ALL if goalie changes. B2B = +0.3 GA.

**§3.4M Multi-Market Table:** Total Shots O/U 60.5, Hits O/U 45.5, Blocks O/U 28.5, PIM O/U 10.5, PP Goals O/U 1.5, Goals O/U 5.5.

**Red flags:** ① Backup goalie (sv% −3-5%) ② B2B ③ 0-3 in series (4% comeback) ④ Goalie unconfirmed

---

## §3.5 Volleyball

| Required Stat | Source |
|---------------|--------|
| Sets: won/lost, avg/match, O/U 3.5 hit rate | Flashscore, CEV/PlusLiga |
| Points: avg total/match, attack eff% | Flashscore |
| 5th set: frequency, record | Flashscore |
| Reception: team reception% | CEV stats |

**Hierarchy:** Sets O/U → Total pts O/U → Set HC → ML (last resort, 1.50-2.50)
**Key:** Top-6 both → O3.5 sets. Big mismatch → U3.5 / HC −1.5.

**§3.5M Multi-Market Table:** Total sets O/U 3.5, Total pts O/U, Set HC ±1.5, Pts/set O/U.

**Red flags:** ① Playoff clinched (rotation) ② 5th set to 15 (verify line) ③ Home crowd >70%

---

## §3.6 Esports (CS2, Valorant, Dota 2)

| Required Stat | Source |
|---------------|--------|
| Map Win Rate: overall + per-map WR% | bo3.gg, VLR.gg, HLTV |
| H2H: last 5 meetings, map scores | bo3.gg (detail page) |
| Map Pool: per-map WR, bans/picks history | bo3.gg |
| Lineups: confirmed 5-player, stand-ins | bo3.gg, VLR.gg, Liquipedia |
| Form: L5/L10 results, streak | VLR.gg, bo3.gg |
| Ranking: team ranking | VLR.gg (Val), HLTV (CS2) |

**Hierarchy:** ML → Map HC ±1.5 → Total Maps O/U 2.5
**Key:** No home/away. Bo1 = high variance (skip ML or use HC). Roster change = −2.

**§3.6M Multi-Market Table:** ML, Map HC ±1.5, Total Maps O/U 2.5.

**Red flags:** ① Stand-in/sub ② Bo1 format ③ Roster change <2 weeks ④ Major patch <1 week

---

## §6.5 Upset Risk — Thresholds & Paradox Rule

**Paradox:** High upset → competitive → MORE stats → prefer OVER. Low upset → blowout → UNDER/HC preferred.

| Sport | Threshold | Max score |
|-------|-----------|-----------|
| Tennis | ≥4 | 12 |
| Football | ≥4 | 14 |
| Basketball | ≥3 | 10 |
| Hockey | ≥3 | 10 |
| Volleyball | ≥3 | 7 |

**Decision matrix:**
| Score | ML | Statistical | Over | Under/HC |
|-------|----|------------|------|----------|
| 0-1 | OK | Full range | Caution (blowout) | Preferred |
| 2-3 | Caution (−1) | Preferred | Moderate | Good |
| 4-5 | **BANNED** | ONLY option | **PREMIUM** | OK |
| 6+ | **BANNED+SKIP** | Conservative | AVOID | Preferred |

---

## §7.3 Instant Red Flags (30s each, EVERY pick)

**Tennis:** T1: WC/Q/LL→O22.5+ REJECT | T2: Fatigue 3h+→UNDER −1 | T3: New surface→−1 | T4: Defending champ R1/R2→−1 | T5: Name ambiguity→STOP | T6: Drift >8%→re-eval

**Football:** F1: Dead rubber→SKIP ML −2 | F2: Cup rotation→−2 | F3: Derby→BTTS/U2.5 | F4: Int'l break→−1 | F5: Synthetic pitch→adjust | F6: Referee unchecked→STOP | F7: ZT#24 close game→FLAG

**Basketball:** B1: B2B→UNDER −3-5pts | B2: Star GTD→check ≤1h | B3: Tank→SKIP | B4: Elimination→OVER

**Hockey:** H1: Backup goalie→OVER | H2: B2B→+0.5 GA | H3: 0-3 series→4% | H4: Goalie unconfirmed→WAIT

**Volleyball:** VB1: Clinched→rotation −1 | VB2: 5th set line→verify | VB3: Home crowd >70%→factor

**Esports:** E1: Stand-in→−2 | E2: Bo1→skip ML | E3: Roster <2w→−1 | E4: Online vs LAN | E5: Patch <1w→−1 | E6: Map overlap ≥3→OVER maps
