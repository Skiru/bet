---
applyTo: "betting/**/*"
---

# Analysis Methodology — Complete Daily Protocol

This is the DEFINITIVE, REPEATABLE methodology for daily betting analysis. Follow every step in order. Do not skip steps. Do not take shortcuts. This protocol produces professional-grade analysis every single day.

The goal: find MISPRICED ODDS, not predict winners. A 40% chance event at 3.00 odds (implied 33%) is a value bet even though it loses most of the time. Value betting is the only sustainable edge.

---

## AGGRESSIVE SCANNING MANDATE — READ FIRST, NEVER VIOLATE

This section overrides everything below. If you remember NOTHING else, remember this:

**You MUST scan WIDE, DEEP, MULTI-LEVEL, and AGGRESSIVELY. This is the #1 operational principle.**

1. **WIDE:** ALL 14 sports on EVERY run. Never skip a sport. Never say "no events" without checking ≥3 sources per sport. The internet ALWAYS has data.
2. **DEEP:** Click into EVERY tournament/league/division within each sport. Landing pages hide 80% of events. Count matches per tournament. Cross-validate counts between ≥2 sources. If counts disagree by >20%, you missed events.
3. **MULTI-LEVEL:** For every candidate: Tier A stats → Tier A markets → Tier B tipster arguments (READ the reasoning, not just the pick) → specialist niche sources → context sources. If ANY level is missing, go back and fill the gap.
4. **AGGRESSIVELY:** When a source fails (403, timeout, empty), IMMEDIATELY try the next. Never give up on a sport or event. If all mapped sources fail, SEARCH THE INTERNET — alternatives ALWAYS exist. Record failures but KEEP SEARCHING.
5. **COMPARE:** Never trust a single source. Every data point needs ≥2 independent confirmations.
6. **TIPSTER ARGUMENTS ARE MANDATORY:** For every candidate, check ≥2 argument-based tipster sites. Navigate to match pages. Read EACH tipster's FULL WRITTEN ARGUMENT. Extract their reasoning — stats cited, injuries mentioned, tactical context, model outputs. A tipster's headline pick is worthless; their REASONING is gold. Sites: ZawodTyper, Typersi, Meczyki, OLBG, PicksWise, BetIdeas, GosuGamers.

**Minimum output targets:**
- Scan completeness: ≥80% of events across all 14 sports
- Total unique events scanned: ≥50 on a normal day
- Shortlist: 15-40 candidates across ≥8 sports
- Final picks: from ≥5 different sports
- Final coupons: ≥5, diversified
- Every pick: ≥2 sources + ≥1 tipster argument checked

**Self-check before presenting:** "Did I scan ALL 14 sports? Did I click into sub-tournaments? Did I read tipster arguments? Did I try alternative sources when one failed?" If ANY answer is NO → go back.

### Source Fallback Chains (when primary source fails → try next)

| Sport | Primary | Secondary | Tertiary | Emergency |
|-------|---------|-----------|----------|-----------|
| Football | BetExplorer | Flashscore | OddsPortal | SoccerStats league pages |
| Tennis | BetExplorer tennis | Flashscore tennis | TennisExplorer | ATP/WTA official draws |
| Basketball | ESPN NBA | BetExplorer basketball | Flashscore | Basketball-Reference |
| Hockey | ESPN NHL | BetExplorer hockey | SBR | NaturalStatTrick |
| Baseball | ESPN MLB | SBR | BetExplorer baseball | BaseballSavant |
| Volleyball | BetExplorer volleyball | Flashscore volleyball | Sofascore | OddsPortal |
| Esports | GosuGamers | HLTV (stats only) | Liquipedia | BO3.gg |
| Snooker | Flashscore snooker | BetExplorer snooker | CueTracker | WorldSnooker/wst.tv |
| Darts | Flashscore darts | BetExplorer darts | DartsOrakel | PDC.tv |
| Table Tennis | Flashscore table tennis | BetExplorer table tennis | ITTF | tt-series.com |
| Handball | BetExplorer handball | Flashscore handball | EHF/eurohandball | Handball-World |
| MMA | Tapology | UFC.com | BetExplorer MMA | Sherdog |
| Padel | Sofascore padel | BetExplorer padel | PremierPadel.com | PadelFIP |
| Speedway | SpeedwayEkstraliga.pl | SportoweFakty żużel | Flashscore motorsport | BetExplorer speedway |

**If ALL sources in a chain fail:** Google "[sport] matches today" or "[sport] schedule April 24" and find a new source. Add it to source-log. The internet ALWAYS has data.

### Tipster Source Fallback Chains

| Sport | Primary tipster | Secondary | Tertiary | Emergency search |
|-------|----------------|-----------|----------|------------------|
| Football | ZawodTyper | Typersi | Meczyki | OLBG, BetIdeas |
| Tennis | ZawodTyper | Typersi | PicksWise | OLBG |
| Basketball/NHL/MLB | PicksWise | Covers | Sportsgambler | Google "[game] prediction" |
| Esports | GosuGamers | BO3.gg predictions | — | Google "[match] prediction" |
| Other sports | OLBG | Sportsgambler | ZawodTyper (if covered) | Google "[event] tips" |

**NEVER declare "no tipster data available" without exhausting all fallbacks + Google search.**

---

## STEP 0: SETTLE PREVIOUS DAY (mandatory, never skip)

### 0.1 Settlement Execution
1. Run `python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD` for the previous betting day.
2. For each pending pick: find result on Flashscore -> verify on Sofascore -> resolve market (win/loss/void/push).
3. Auto-settlement covers: match winner (1X2), totals (any line), BTTS, double chance. Manual settlement needed for: corners, cards, handicaps, MyCombi.
4. Update `picks-ledger.csv` status column (won/lost/void/push) and `result` column.
5. Update `coupons-ledger.csv` status column. A coupon wins only if ALL legs win.

### 0.2 Performance Tracking
1. Calculate previous-day PnL: `sum(returns) - sum(stakes)`.
2. Calculate rolling 7-day PnL.
3. Update per-market-type hit rates: `corners_hit_rate`, `btts_hit_rate`, `ml_hit_rate`, `tennis_games_hit_rate`, etc.
4. Update per-league ROI: which leagues produced profit, which produced loss.
5. **Post-mortem for each LOSS**: Was the analysis wrong (bad thesis) or did variance hit (correct thesis, unlucky result)? Record in learning log.

### 0.3 CLV Tracking (Closing Line Value)
1. For each settled pick, record the closing odds (odds just before kickoff) from OddsPortal/BetExplorer.
2. Calculate CLV: `(closing_implied_prob / placement_implied_prob) - 1`. Positive CLV = you got better odds than the market closing price = sharp.
3. Track rolling average CLV. If consistently negative, the betting approach needs fundamental revision.
4. Record in learning log weekly.

### 0.4 Bankroll Update
1. Update `working_bankroll_pln` in `config/betting_config.json`.
2. If bankroll dropped >20% from peak, reduce daily exposure range by 25%.
3. If bankroll grew >30% from start, consider increasing daily range by 10-15%.

---

## STEP 1: SCAN — Complete Event Discovery

### 1.1 Run Orchestrator
1. Execute `bash scripts/run_full_scan_and_prepare.sh`.
2. Check `betting/data/scan_errors.json` for failed sources. Record in source log.
3. Verify `scan_summary.json` and `picks_suggested.json` are populated.

### 1.2 Master Event List — Deep Scan Protocol

**PURPOSE**: Build a COMPLETE, VERIFIED list of every event in the betting-day window. The previous failure mode was SHALLOW scanning — glancing at a sport's page, picking one obvious match, and moving on. This protocol forces DEPTH.

Build the list using ALL THREE primary sources — not just one:
- **BetExplorer**: browse sport-by-sport (football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma, padel, speedway). Click "Tomorrow" or today's date tab.
- **Flashscore**: cross-reference for fixture times and any events BetExplorer misses. Check ALL 14 sports.
- **OddsPortal**: check for additional sports/events and odds not on BetExplorer.

**Deep Scan Rules (MANDATORY):**

1. **Enter every active tournament/league**: Do NOT just look at the sport landing page. Click into each active tournament/league to see the FULL fixture list. A single "Tennis" page may show 5 events — clicking into "ATP Madrid" reveals 16. Clicking into "WTA Madrid" reveals 16 more.
2. **Count matches per tournament**: Record the match count for every tournament. If a tournament has ≥4 matches today, ALL must be screened for value (odds check, form check). This is non-negotiable.
3. **Cross-validate between sources**: For every sport, compare event counts between BetExplorer and Flashscore. If BetExplorer shows 8 tennis matches but Flashscore shows 24, you missed tournaments. Go back and find them.
4. **Minimum 3 sources per sport**: Every sport must be checked on at least 2 of the 3 primary sources (BetExplorer, Flashscore, OddsPortal). For sports with specialist sites, use those as a 3rd source (GosuGamers for esports, CueTracker for snooker, etc.).
5. **Record event count per source**: Create a tally: "Tennis: BetExplorer=24, Flashscore=28, OddsPortal=22". Discrepancies > 20% → investigate which events are missing.
6. **No drive-by scanning**: Spending <2 minutes on a sport is NOT a scan. For each sport, you must open the fixture page, scroll through ALL events, identify tournaments/leagues, enter them, and count matches.

For each event, record:
- Sport, competition/tournament, event name, kickoff time (local)
- Available markets on Betclic (if known)
- Initial odds range (favorite/underdog)
- Source where found (for cross-validation)

### 1.3 Sport Coverage Checklist — MANDATORY (ALL 14 SPORTS)

**CRITICAL ENFORCEMENT RULE**: You MUST scan ALL 14 sports below. This is not optional. Every sport must be checked for events in the betting-day window. For each sport, record either: (a) candidate events found, or (b) "NO EVENTS TODAY" with the source you checked. Skipping a sport is a PROTOCOL VIOLATION.

Scan order (follow this exact sequence):
1. [ ] **Football**: top 5 leagues, cups, 2nd divisions, Scandinavian, Dutch, Portuguese, Turkish, Greek, MLS, Brazilian, Argentine, Asian leagues
2. [ ] **Tennis**: ATP, WTA, Challengers (skip ITF). Check BetExplorer tennis + Flashscore tennis.
3. [ ] **Basketball**: NBA, Euroleague, national leagues. Check ESPN + BetExplorer basketball.
4. [ ] **Hockey**: NHL, KHL, SHL, Liiga. Check ESPN NHL + BetExplorer hockey.
5. [ ] **Baseball**: MLB (if in season). Check ESPN MLB + SBR.
6. [ ] **Volleyball**: CEV Champions League, national leagues, international. Check BetExplorer volleyball + Flashscore.
7. [ ] **Esports**: CS2 (tier 1-2), Dota 2, LoL (LCK/LPL/LEC/LCS), Valorant. Check GosuGamers + BetExplorer esports + Liquipedia.
8. [ ] **Snooker**: World Championship, Tour events. Check Flashscore snooker + BetExplorer.
9. [ ] **Darts**: Premier League, PDC events, World Series. Check Flashscore darts + BetExplorer.
10. [ ] **Handball**: EHF Champions League, Bundesliga, national leagues. Check BetExplorer handball + Flashscore.
11. [ ] **Table Tennis**: WTT events, national leagues. Check Flashscore table tennis + BetExplorer.
12. [ ] **MMA/UFC**: any scheduled card. Check UFC.com + Tapology + BetExplorer MMA.
13. [ ] **Padel**: Premier Padel, FIP Tour events. Check Sofascore padel + BetExplorer padel + PremierPadel.com.
14. [ ] **Speedway/Żużel**: PGE Ekstraliga, 2. Ekstraliga, SGP. Check BetExplorer speedway + SportoweFakty.wp.pl/zuzel.

**After scanning**: Count how many sports have events. Record the count. If fewer than 6 sports have events today, note this explicitly — it's unusual and should be verified.

**Source discovery for niche sports**: If BetExplorer/Flashscore don't cover a sport well:
- Esports: GosuGamers, Liquipedia, HLTV (stats only, NOT tips)
- Snooker: CueTracker, WorldSnooker.com
- Darts: DartsOrakel, PDC.tv
- Table Tennis: tt-liveresults.com
- Handball: eurohandball.com
- MMA: Sherdog, Tapology, UFC.com
- Padel: PremierPadel.com, Sofascore padel, PadelFIP.com
- Speedway: SpeedwayEkstraliga.pl, SportoweFakty.wp.pl/zuzel

**NEVER say "no sources available" for a sport without searching specialist sites first. The internet ALWAYS has data for every sport.**

### 1.3a Tournament Awareness Protocol — MANDATORY

**CRITICAL RULE**: When a MAJOR TOURNAMENT is in progress (ATP/WTA Masters 1000, Grand Slam, World Championship, Champions League knockout, NBA/NHL playoffs, etc.), you MUST analyze the FULL daily slate of that tournament — not just 1-2 cherry-picked matches.

**What qualifies as a major tournament requiring full-slate analysis:**
- Tennis: ATP Masters 1000 (Madrid, Rome, Monte Carlo, Indian Wells, Miami, etc.), Grand Slams, WTA 1000
- Snooker: World Championship, UK Championship, Masters
- Football: Champions League/Europa League matchdays, World Cup, Euros
- Basketball: NBA Playoffs, Euroleague Final Four
- Hockey: NHL Playoffs, World Championship
- Baseball: MLB Playoffs, World Series
- Esports: Major tournaments (CS2 Majors, LoL Worlds, TI)
- Darts: World Championship, Premier League
- MMA: UFC numbered events

**Execution steps when a major tournament is active:**
1. **Count ALL matches** in the tournament scheduled for the betting day. Record the count.
2. **Extract odds for EVERY match** — not just the obvious ones. R1 of a Masters 1000 can have 16+ matches.
3. **Calculate odds ratio** for each match (for tennis O-games screening).
4. **Shortlist the best candidates** — typically 3-8 matches from a 16-match slate will have value.
5. **Apply deep analysis (Steps 3-8)** to each shortlisted match.
6. **Record which matches were checked and which were skipped** with reasons.

**Example**: ATP Madrid R1 has 16 matches on Apr 24. You MUST check all 16 for odds ratios/value, shortlist 3-8, and analyze them. Picking only 1 (Shelton) from 16 is a PROTOCOL VIOLATION.

**WTA runs parallel**: When ATP and WTA share a venue (Madrid, Rome, Indian Wells, etc.), BOTH draws must be scanned on the same day. 16 ATP + 16 WTA = 32 matches to screen.

This rule prevents the single biggest source of missed value: ignoring a tournament's depth because only the headline match was noticed.

### 1.3b Non-Major Tournament Depth Protocol

The §1.3a rule covers MAJOR tournaments. But value also hides in mid-tier tournaments. Apply this protocol to ANY tournament/league with ≥4 matches on the betting day:

**Mid-tier tournaments requiring full-match screening:**
- Tennis: ATP 500, ATP 250, WTA 500, WTA 250, strong Challengers
- Football: all league matchdays (not just top 5 — include Eredivisie, Ekstraklasa, Turkish Süper Lig, Brazilian Serie A, Argentine Primera, etc.)
- Basketball: Euroleague, EuroCup, national league full rounds
- Hockey: KHL, SHL, Liiga matchdays
- Volleyball: national league full rounds, CEV competition matchdays
- Esports: tier-2 events (BLAST, ESL, DreamHack), regional leagues (LCK, LPL, LEC, VCT)
- Snooker: Tour events, Championship League
- Darts: Players Championship, European Tour

**Execution:**
1. Count ALL matches in the tournament for the betting day.
2. Check odds for EVERY match (not just headliners).
3. For tennis: calculate odds ratio for every match → shortlist STRONG/GOOD ratios.
4. For team sports: identify totals/statistical markets for every match.
5. Shortlist the best 25-30% of matches for deep analysis (Steps 3-8).
6. Record which matches were checked and which were passed with a 1-line reason.

**The failure mode this prevents:** Scanning "tennis" and seeing 3 matches when there are actually 40 across ATP Madrid, WTA Madrid, ATP 250 Barcelona, and two Challenger events. Each tournament must be entered individually.

### 1.4 Source Resilience Protocol
When ANY source returns 403, Cloudflare block, GDPR wall, or empty response:
1. Do NOT give up. Move to the next source in the Odds Source Map (source-registry.md).
2. If all mapped sources fail, search the internet for alternative sources. The internet ALWAYS has data.
3. Record every source failure in `source-log.csv`.
4. For every pick, you MUST have odds or data from at least 2 independent sources for cross-validation.
5. For US sports: SBR + ESPN Odds + ScoresAndOdds = three independent sources. Use all three.
6. For EU sports: BetExplorer + OddsPortal = two primary sources. Add The-Odds-API as fallback.
7. Different sources may show DIFFERENT lines for the same game (e.g., SBR: O6.0, ESPN: O6.5). This validates the multi-source approach — always note discrepancies.

### 1.5 Scan Completeness Metrics — MANDATORY

Before proceeding to Step 2, compile and record these metrics. They are the QUALITY GATE for scanning depth.

**Per-Sport Event Count Table (record in report):**

| Sport | BetExplorer | Flashscore | OddsPortal | Specialist | Total Unique | Tournaments Entered |
|-------|-------------|------------|------------|------------|-------------|---------------------|
| Football | ? | ? | ? | — | ? | ? |
| Tennis | ? | ? | ? | — | ? | ? |
| Basketball | ? | ? | ? | ESPN | ? | ? |
| Hockey | ? | ? | ? | ESPN | ? | ? |
| Baseball | ? | ? | ? | ESPN/SBR | ? | ? |
| Volleyball | ? | ? | ? | — | ? | ? |
| Esports | ? | ? | ? | GosuGamers | ? | ? |
| Snooker | ? | ? | ? | CueTracker | ? | ? |
| Darts | ? | ? | ? | DartsOrakel | ? | ? |
| Table Tennis | ? | ? | ? | — | ? | ? |
| Handball | ? | ? | ? | — | ? | ? |
| MMA | ? | ? | ? | Tapology | ? | ? |
| Padel | ? | ? | ? | PremierPadel | ? | ? |
| Speedway | ? | ? | ? | SportoweFakty | ? | ? |
| **TOTAL** | | | | | **?** | **?** |

**Minimum thresholds:**
- Total unique events scanned must be ≥50 (on a normal day with all sports active). If <50, something was missed — go back.
- At least 6 sports must have events. If <6 on a non-holiday weekday, verify by checking a 3rd source.
- Every sport with >0 events must have events counted from ≥2 sources.
- Cross-source discrepancy >30% for any sport → investigate and reconcile before proceeding.

**Tournament depth audit:**
- List every tournament with ≥4 matches today.
- For each: confirm ALL matches have been logged with odds.
- If any tournament has matches NOT in the Master Event List → add them.

**Scan completeness score** = (events found from ≥2 sources) / (total unique events). Target: ≥80%.

If scan completeness score <80% or any sport was not checked → DO NOT proceed to Step 2. Go back and scan.

---

## STEP 2: FILTER — Event Shortlist

### 2.1 Automatic Removal
Remove events that:
- Are outside the betting-day window
- Have no Tier A source coverage at all
- Are too close to kickoff (<1 hour) at time of analysis
- Are exhibition/friendly matches (unless odds are available and analysis is possible)
- Are from unverifiable competitions (random e-sports, unranked fighters, etc.)

### 2.2 Market Opportunity Screening
For each remaining event, quickly assess:
- Does this event have a STATISTICAL MARKET available? (corners, cards, totals, set handicaps, etc.)
- Or only basic 1X2/ML? If only basic markets -> lower priority unless the edge is obvious.
- Are odds in our preferred range (1.30-3.50)? Events with all odds outside this range -> lower priority.

**UNIVERSAL RULE — ALL SPORTS: NEVER default to ML/1X2/match winner.** Statistical markets (totals, handicaps, cards, corners, fouls, frames, legs, maps, sets, games) are ALWAYS preferred across EVERY discipline. They have higher hit rates (~60-65%) and are less efficiently priced by bookmakers. ML/winner picks are the ABSOLUTE LAST RESORT — only when no statistical market exists on Betclic AND the statistical edge is overwhelming. This applies equally to football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, handball, table tennis, MMA, padel, and speedway.

### 2.3 Result: Shortlisted Events
Target: 15-40 events across multiple sports. If fewer than 15, widen the search. If more than 40, tighten criteria (remove events with weakest source coverage).

**Sport diversity requirement**: The shortlist MUST include events from at least 5 different sports. If fewer than 5 sports are represented, go back to Step 1 and scan the missing sports more aggressively. Football should NOT dominate the shortlist — aim for no more than 50% football events.

---

## STEP 3: STATS — Deep Statistical Analysis

For EACH shortlisted event, gather sport-specific statistical data. This is the CORE of the analysis — do NOT rush it.

### 3.1 Football Statistical Protocol — EXHAUSTIVE CHECKLIST
For every football candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. League-Level Context (SoccerStats / FootyStats)**
- League average goals per match
- League O2.5%, BTTS%, corner averages
- League home/away splits
- Team rankings within league: goals for/against, corners for/against, cards, fouls

**B. Match-Level Data (BetExplorer + Flashscore)**
- BetExplorer match odds history and implied probability
- H2H history (last 5-10 meetings): goals, corners, cards, fouls patterns. Include HOME/AWAY splits.
- Recent form: last 5-6 matches for each team

**C. FULL STATISTICAL PROFILE — EVERY TEAM (FootyStats / Flashscore / Sofascore)**
Collect ALL of these per-team stats. Split by Overall / Home / Away:

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **FOULS** | Fouls committed/match, Fouls drawn/match, Total match fouls avg | FootyStats |
| **CARDS** | Team cards/match, Opponent cards/match, Total match cards avg, O3.5/O4.5 cards hit rate | FootyStats |
| **CORNERS** | Team corners earned/match, Corners conceded/match, Total match corners avg, O9.5/O10.5 hit rate | TotalCorner + SoccerStats |
| **SHOTS** | Shots/match, Shots on target/match, Conversion rate %, O/U team shots hit rates | FootyStats |
| **FREE KICKS** | Team FK/match, Total FK/match, O19.5/O20.5 total FK hit rate | FootyStats |
| **GOALS** | Scored/match, Conceded/match, O2.5 %, BTTS %, Clean sheets % | FootyStats |
| **xG** | xG for/match, xG against/match, xG vs actual goals delta | Flashscore/Sofascore |
| **POSSESSION** | Possession %, Throw-ins/match | FootyStats |

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
After collecting all stats, RANK available markets by SAFETY and VALUE:
1. Calculate **hit rate** for each O/U line (e.g., Leipzig O16.5 shots hits 87% at home)
2. Calculate **combined hit rate** when both teams' data is merged (e.g., Leipzig home + Union away)
3. **Priority:** highest hit rate × best odds = best market. NOT the sexiest market.
4. **Football market hierarchy** (most inefficient → most efficient — 1X2 is LAST RESORT):
   - Fouls O/U → Cards O/U → Corners O/U → Shots O/U → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 (LAST RESORT)
5. Present TOP 3 markets per match with hit rates before choosing.

**E. Corner Analysis (THREE-SOURCE STACK — mandatory for corner picks)**
1. **TotalCorner**: match-level corner total predictions, handicaps
2. **SoccerStats**: league corner rankings (team corner averages home/away)
3. **Betclic Statystyki** (top leagues only: EPL, LaLiga, Bundesliga): verified corner odds from HTML snapshots

If any of the three sources is missing, mark corner pick as LOWER CONFIDENCE.

**F. Fouls & Cards Analysis (MANDATORY for ALL football picks)**
- **Fouls:** Team A fouls committed/match + Team B fouls committed/match = expected total fouls
- If both teams foul >11/match → O22.5 total fouls candidate
- If one team fouls >12/match and opponent draws >10 fouls → high-foul match
- **Cards:** Team cards avg + opponent cards avg = expected total cards
- Referee card tendency (if available): avg cards/match for this referee
- Union Berlin 2.3 cards/match + Leipzig 1.47 = ~3.77 → O3.5 cards candidate
- **Cross-reference:** high fouls + aggressive referee = cards value

**G. Defensive Profile Analysis (for U2.5/BTTS picks)**
- Team GF+GA per match: if <2.0 → U2.5 candidate
- League O2.5%: if <50% → U2.5 favorable league context
- Clean sheet percentages for both teams
- Competition context: cup semi/final → typically tactical (U2.5 lean)

**H. xG Analysis (where available)**
- If Flashscore/Sofascore provide xG data, compare xG to actual goals
- xG > Goals → team underperforming, likely to improve (regression UP)
- Goals > xG → team overperforming, regression DOWN coming
- Use xG as truth, not recent results

**I. Context Factors (MANDATORY)**
- Coach change: when? New coach bounce (first 5 matches) or settled?
- Injuries/suspensions: check ESPN, Flashscore, team social media
- Fixture congestion: <72h since last match?
- Motivation: relegation, title race, dead rubber, cup final?
- Weather: rain/wind impact on corners, shots, goals
- Referee: specific referee stats for cards/fouls if available

### 3.2 Tennis Statistical Protocol — EXHAUSTIVE CHECKLIST
For every tennis candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Player Comparison (Flashscore + ATP/WTA)**
- Current ranking and recent ranking trajectory (rising/falling)
- Surface-specific win rate (clay/hard/grass/indoor hard) — OVERALL + THIS SEASON
- H2H record on current surface (last 5-10 meetings)
- Recent form: last 5-10 matches, noting retirements and walkovers
- **Tournament round context (MANDATORY):** For R2+, check the player's result from the previous round in this same tournament — score, number of games, sets, physical condition, match duration. A 3h R1 match impacts R2 stamina. A dominant 6-1 6-2 R1 signals peak form.

**B. FULL STATISTICAL PROFILE — EVERY PLAYER (TennisAbstract + Flashscore + Sofascore)**
Collect ALL of these per-player stats:

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **ELO** | Overall Elo, Surface-specific Elo, Elo trajectory (rising/falling) | TennisAbstract |
| **SERVE** | 1st serve %, 1st serve points won %, 2nd serve points won %, Aces/match, Double faults/match, Service games held % | TennisAbstract + Flashscore |
| **RETURN** | Return points won %, Break points converted %, Return games won % | TennisAbstract + Flashscore |
| **GAMES** | Avg games per set, Avg total games per match, O/U 20.5/21.5/22.5 games hit rate | Flashscore match history |
| **SETS** | 3-set match %, Tiebreak frequency %, Sets won from behind % | Flashscore match history |
| **BREAK POINTS** | BP created/match, BP saved %, BP conversion rate | TennisAbstract |
| **PHYSICAL** | Avg match duration, 5-setter record (Slams), Retirements in last 20 matches | Flashscore + ATP/WTA |
| **SURFACE FORM** | Win % on this surface THIS YEAR, vs Top 20/50/100 on this surface | TennisAbstract |

**C. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
After collecting all stats, RANK available markets:
1. Calculate **odds ratio**: `max(odds) / min(odds)`
   - <=1.15: STRONG for O-games (55-65% 3-set probability)
   - 1.16-1.30: GOOD for O-games (48-55%)
   - 1.31-1.50: BORDERLINE — coupon leg only
   - >1.50: REJECT O-games
2. For ML bets: check serve/return stats gap. Both hold >80%? → likely tiebreaks → O-games better than ML.
3. Surface effect: clay breaks easier → longer matches. Hard court → serve-dominant → tiebreaks.
4. **Tennis market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Total games O/U → Set totals O/U → Game handicap → Set handicap → ML (1.50-2.50 range only, LAST RESORT)
   **ABSOLUTE RULE: NEVER default to ML in tennis. Statistical markets (games, sets) have dramatically higher hit rates. ML is only acceptable when odds ratio is STRONG (≤1.15) AND surface dominance AND H2H dominance all align. The Shelton v6 loss proved this: match went 3 sets, ML lost, O21.5 games would have won easily.**
5. Present TOP 2 markets per match with statistical backing before choosing.

**D. Over-Games Assessment (MANDATORY for O/U games picks)**
- Standard line O20.5 in best-of-3. A 3-set match 6-4/4-6/6-4 = 24 games (covers). A 2-set 6-3/6-4 = 19 (doesn't).
- Both players hold serve >75%? → tiebreaks likely → pushes total games UP.
- Both players break >25%? → shorter sets, but more likely 3 sets → could go either way.
- Clay: breaks are easier → more break opportunities → longer sets → more games on average.

**E. Context Factors (MANDATORY)**
- Injury/withdrawal risk: check ATP/WTA withdrawal list, recent retirements
- Fitness: back-to-back tournament weeks? Travel fatigue?
- Motivation: defending points? First-time at this level? Ranking implications?
- Weather: heat (affects stamina), wind (affects serve-dominant players more)
- Court speed: slow clay vs fast hard → completely different match dynamics

**Sources**: TennisAbstract (Elo, serve/return stats), Flashscore (form, H2H, live scores, match history), Sofascore (detailed match stats), ATP/WTA official sites (draws, Order of Play), BetExplorer/OddsPortal (odds)

### 3.3 Basketball Statistical Protocol — EXHAUSTIVE CHECKLIST
For every basketball candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Team Tempo & Efficiency (ESPN + Basketball-Reference + NBA.com)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **PACE** | Possessions/game (both teams), League rank in pace, Pace in last 10 games | ESPN/NBA.com |
| **OFFENSE** | Offensive rating (pts/100 poss), FG%, 3PT%, Free throw rate, Turnovers/game | Basketball-Reference |
| **DEFENSE** | Defensive rating, Opponent FG%, Opponent 3PT%, Steals/game, Blocks/game | Basketball-Reference |
| **TOTALS** | Team total pts/game, Opponent pts/game, Combined avg, O/U line hit rates (O/U 210.5, 215.5, 220.5, etc.) | ESPN + Flashscore |
| **REBOUNDS** | Off rebounds/game, Def rebounds/game, Total rebounds (2nd chance pts indicator) | Basketball-Reference |
| **ASSISTS** | Assists/game, Assist/TO ratio (ball movement indicator) | Basketball-Reference |
| **FREE THROWS** | FTA/game, FT%, Opponent FTA/game (foul-drawing teams = more FTs = higher totals) | Basketball-Reference |
| **HOME/AWAY** | Pts scored home vs away, Pts allowed home vs away, ATS record home/away | ESPN |

**B. Player Impact Analysis**
- Top scorer availability (injury report from ESPN/NBA.com — check DAY OF)
- Star player ON/OFF splits: what's the team's rating with vs without their star?
- Minutes load: back-to-back? 40+ minutes in previous game?
- Rest days advantage (3+ days rest vs B2B = huge factor in NBA)

**C. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: total points per game, margin, pace
- Last 10 games form: W-L, average total points, average margin
- Trends: O/U record in last 10, ATS record in last 10

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Fast pace teams (top 10 league) meeting → O-totals candidate. Both top 10 → STRONG.
2. Check combined pace: if both >100 possessions → high-scoring game likely.
3. Check defensive rating: if both bottom 10 defense → inflated totals.
4. **Basketball market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Team totals O/U → Quarter totals → Game totals O/U → Spreads → ML (LAST RESORT)
5. Playoff vs regular season: playoff games average 3-5 fewer points (slower pace, more defense).

**E. Context Factors (MANDATORY)**
- Playoff implications: seeding, elimination, rest starters?
- Back-to-back: B2B teams score 2-4 fewer pts on average
- Travel: coast-to-coast travel (EST→PST or reverse) = fatigue
- Altitude: Denver home games → visitors tire faster in 4th quarter
- Rivalry factor: intense rivals → lower totals (more physical play)

**Sources**: ESPN NBA (odds, injury reports, standings), Basketball-Reference (advanced stats), NBA.com (official stats, pace), SBR (odds comparison, US), Flashscore (form, H2H), BetExplorer (odds)

### 3.4 Hockey Statistical Protocol — EXHAUSTIVE CHECKLIST
For every hockey candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Team Statistics (NaturalStatTrick + MoneyPuck + ESPN)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **xG (EXPECTED GOALS)** | xGF/game, xGA/game, xG%, xG vs actual goals delta (regression indicator) | NaturalStatTrick/MoneyPuck |
| **GOALS** | GF/game, GA/game, Combined avg, O/U 5.5/6.5 hit rate, Empty net goals/game | ESPN + Flashscore |
| **SHOTS** | Shots/game, Shots against/game, Shot %, Shots on goal conversion | NaturalStatTrick |
| **POWER PLAY** | PP%, PP opportunities/game, PPG/game, League rank | ESPN/NHL.com |
| **PENALTY KILL** | PK%, Short-handed goals against/game, Penalties taken/game | ESPN/NHL.com |
| **PENALTIES** | PIM/game (penalty minutes), Minor penalties/game, Major penalties/game | ESPN |
| **FACEOFFS** | Faceoff win %, Offensive zone faceoff % (possession proxy) | NaturalStatTrick |
| **CORSI/FENWICK** | CF%, FF% (shot attempt differential — true possession metric) | NaturalStatTrick |
| **HOME/AWAY** | GF home vs away, GA home vs away, Home/away record, O/U record by venue | ESPN |

**B. Goalie Analysis (CRITICAL — most important single factor)**
- **Starting goalie CONFIRMED?** Check DailyFaceoff.com or team Twitter (~10am game day)
- Starting goalie: save %, GAA (goals against avg), last 5 starts (W-L, sv%, GAA)
- Goalie vs this opponent: career record, save % against them
- Backup risk: if starter rested/injured, backup's stats are often drastically worse
- Goalie workload: starts in last 7 days (fatigue factor)

**C. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: total goals per game, margin, OT frequency
- Last 10 games form: W-L, average total goals, goals for/against trends
- Division/conference rivals: tighter, lower-scoring games typical

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both teams xGF > 3.0? → O-totals candidate (strong both offenses)
2. Both goalies sv% < .910 in last 10? → O-totals candidate (weak goaltending)
3. One elite goalie (sv% > .920) vs weak offense (xGF < 2.5)? → U-totals candidate
4. **Hockey market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Period totals → Game totals O/U → Puck line (handicap ±1.5) → ML (LAST RESORT) → 3-way (regulation)
5. Playoff: tighter checking, better goaltending → 0.5-1.0 fewer goals than regular season avg.

**E. Context Factors (MANDATORY)**
- **Back-to-back (B2B):** Team on 2nd night of B2B → backup goalie likely, fatigue → +0.3 goals against avg
- **Travel:** 3-games-in-4-nights? Cross-timezone travel?
- **Playoff context:** elimination game → tighter defense. Series lead → complacency risk.
- **Trade deadline impact:** new players not yet integrated
- **Injury report:** check ESPN NHL injuries, DailyFaceoff
- **Schedule spot:** last game before All-Star break or bye week → motivation questions

**Sources**: NaturalStatTrick (xG, Corsi, shot metrics), MoneyPuck (expected goals model), ESPN NHL (odds, injuries, standings), DailyFaceoff.com (goalie confirmations), SBR (odds comparison), BetExplorer/OddsPortal (odds), Flashscore (form, H2H)

### 3.5 Volleyball Statistical Protocol — EXHAUSTIVE CHECKLIST
For every volleyball candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Team Statistics (Flashscore + Sofascore + League sites)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **SETS** | Sets won/lost, Avg sets/match, O/U 3.5 sets hit rate, 3-0/3-1/3-2 frequency | Flashscore |
| **POINTS** | Avg total points/match (typical 150-190), Avg points/set, O/U total points hit rate | Flashscore + Sofascore |
| **ATTACK** | Kill %, Attack errors/set, Efficiency % | League sites (CEV, PlusLiga) |
| **SERVE** | Aces/match, Service errors/match, Ace-to-error ratio | League sites |
| **BLOCK** | Blocks/match (key defensive stat, correlates with shorter sets) | League sites |
| **RECEPTION** | Reception %, Perfect reception % (determines attack quality) | League sites |
| **HOME/AWAY** | Points scored home vs away, Sets won home vs away, ML record | Flashscore |
| **TIEBREAKS** | 5th set frequency %, 5th set win rate, Tiebreak set avg points (typically 25-35) | Flashscore match history |

**B. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: sets score, total points, 5th set frequency
- Last 10 matches form: W-L, average sets/match, average total points
- League standing: top 4 teams vs bottom 4 → predictable. Middle-table → competitive.

**C. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both teams in top 6 with similar quality? → O3.5 sets candidate (competitive = more sets)
2. Big mismatch (table leader vs bottom)? → U3.5 sets / Set handicap -1.5 candidate
3. Both teams high attack efficiency? → O total points (more rallies, longer sets)
4. **Volleyball market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Individual set score O/U → Total points O/U → Set totals O/U 3.5 → Set handicap → ML (LAST RESORT)
5. ML only viable in 1.50-2.50 range. Below 1.40 = no value. Above 2.80 = too risky.

**D. Context Factors (MANDATORY)**
- Competition stage: regular season vs playoffs (playoff = tighter, more 5-setters)
- Roster changes: new setter = entire team attack changes
- Travel: international club competitions (Champions League) = travel fatigue
- Venue: some volleyball arenas have notable home advantage (loud crowds affect serve reception)
- Rotation: coach resting key players for upcoming playoff matches?

**Sources**: Flashscore volleyball (form, H2H, live scores), Sofascore (detailed match stats), BetExplorer volleyball (odds), OddsPortal volleyball (odds history), CEV (Champions League stats), PlusLiga.pl (Polish league stats)

### 3.6 Esports Statistical Protocol (CS2/LoL/Dota2/Valorant) — EXHAUSTIVE CHECKLIST
For every esports candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. CS2/Valorant — Team Statistics (HLTV stats + Liquipedia + VLR.gg)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **MAP POOL** | Maps played, Win rate per map, Map pool overlap between teams, Map veto history | HLTV/Liquipedia |
| **ROUNDS** | Avg rounds/map, O/U 26.5 hit rate, Overtime frequency % | HLTV stats |
| **PISTOL ROUNDS** | Pistol round win %, Pistol round conversion rate (win pistol → win half?) | HLTV stats |
| **K/D & RATING** | Team avg HLTV rating 2.0, Top fragger rating, Lowest player rating (weak link) | HLTV stats |
| **ECONOMY** | Eco round win %, Force buy success rate, Full buy round win % | HLTV stats |
| **CT/T SIDE** | CT-side win %, T-side win %, Side preference per map | HLTV stats |
| **CLUTCH** | 1vX clutch win %, Post-plant win % | HLTV stats |
| **FORM** | Last 3 months win %, Last 10 matches W-L, Recent LAN vs online results | HLTV + Liquipedia |

**B. LoL/Dota2 — Team Statistics (Liquipedia + GosuGamers + Oracle's Elixir/DotaBuff)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **GAME DURATION** | Avg game length (fast meta <28min → early aggression team wins) | Oracle's Elixir/DotaBuff |
| **OBJECTIVES** | First blood %, First tower %, Dragon/Baron control %, Roshan % | Oracle's Elixir/DotaBuff |
| **KILLS** | Avg kills/game, Kill differential, O/U kill total hit rates | GosuGamers |
| **GOLD** | Avg gold lead @15min, Gold diff/min, Comeback rate from deficit | Oracle's Elixir |
| **DRAFT** | Meta priority picks, Signature champions/heroes, Draft adaptation | Liquipedia |

**C. Match Format & Context**
- BO1 vs BO3 vs BO5 — upsets FAR more likely in BO1 (map variance is huge)
- LAN vs Online: LAN = more pressure, less internet advantage, crowd factor
- Tournament tier: Major/Minor/Regional → top teams try harder at Majors
- Group stage vs playoffs: different motivation levels
- Roster changes: new player (IGL, AWPer, support) in last 30 days = volatility

**D. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: map score, maps played, round differentials
- Recent form (last 10 matches): W-L, map win %, opponents faced (quality of opposition)
- Current tournament path: how did they get here? Easy bracket or hard matches?

**E. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Evenly matched teams in BO3? → O2.5 maps (competitive = more maps)
2. Clear favorite in BO3 with map pool edge? → Map HC -1.5
3. Close map pool overlap? → total rounds O/U on specific maps
4. **Esports market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Total rounds O/U per map → Map totals O/U 2.5 (BO3) → Map handicap -1.5 → Kill totals → ML (LAST RESORT)
5. BO1 markets are volatile — reduce confidence -1 for any BO1 pick.

**Sources**: HLTV (CS2 stats ONLY — tips are BLOCKED), Liquipedia (all esports wikis), GosuGamers (tips + stats), VLR.gg (Valorant), Oracle's Elixir (LoL), DotaBuff/OpenDota (Dota2), BetExplorer esports (odds)

### 3.7 Snooker Statistical Protocol — EXHAUSTIVE CHECKLIST
For every snooker candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Player Statistics (CueTracker + WorldSnooker + Flashscore)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **RANKING** | World ranking, Prize money ranking, Ranking trajectory (rising/falling) | WorldSnooker/WST |
| **FRAME WIN %** | Overall frame win %, Frame win % this season, Frame win % at this tournament/venue | CueTracker |
| **CENTURIES** | Century breaks/match, Total centuries this season, Highest break this season | CueTracker |
| **50+ BREAKS** | 50+ breaks/match, Break-building consistency (key for O frames) | CueTracker |
| **FRAME DURATION** | Avg frame time (>20min = safety-heavy = more tactical = more frames) | CueTracker |
| **SAFETY PLAY** | Safety shot %, Long pot success rate (tactical vs aggressive player) | CueTracker |
| **DECIDER FRAMES** | Decider frame record (clutch factor), % of matches going to final frame | CueTracker |
| **FORM** | Last 10 matches W-L, Current tournament results, Recent form trends | Flashscore |

**B. Tournament Context**
- Format: BO9 (ranking events early) / BO13 / BO19 (World Champ R1) / BO25 / BO35 (WC Final)
- Session structure: single session vs multi-session (fatigue factor in longer formats)
- Venue: Crucible (World Championship) has unique pressure — upsets more common in R1
- Defending champion/ranking points: motivation factor

**C. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: frame scores, decider frequency, century breaks
- Recent form (last 5-10 matches): frame win %, quality of opposition
- Current tournament path: easy draws or hard matches? Physical/mental state.

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both players ranked within 15 of each other? → O frames (competitive = more frames used)
2. Both players avg frame time >18min? → O frames (tactical match, slow-paced)
3. One player dominant (top 4) vs outside top 32? → Frame HC / U frames
4. **Snooker market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Century breaks O/U → Total frames O/U → Frame handicap → Correct score → ML (LAST RESORT)
5. World Championship: early rounds (BO19/BO25) produce MORE value than finals (heavily analyzed).

**E. Context Factors (MANDATORY)**
- Schedule: morning vs evening session (some players perform differently)
- Travel: did player just fly from China/Australia? Jet lag factor
- Off-table issues: check snooker media for any controversy, personal issues
- Referee: some referees call fouls more strictly (minor but noted)

**Sources**: CueTracker (frame stats, centuries, deciders — PRIMARY), WorldSnooker/WST.tv (rankings, draws, results), Flashscore snooker (form, H2H, live), BetExplorer snooker (odds), OddsPortal (odds history)

### 3.8 Darts Statistical Protocol — EXHAUSTIVE CHECKLIST
For every darts candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Player Statistics (DartsOrakel + PDC + Flashscore)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **AVERAGE** | 3-dart average (>95 elite, 90-95 good, <90 inconsistent), Avg this tournament, Avg last 10 matches | DartsOrakel/PDC |
| **CHECKOUT %** | Doubles hit rate %, Checkout % under pressure (deciding legs), Clutch checkout rate | DartsOrakel/PDC |
| **180s** | 180s per match, 180s per leg, 180s hit rate trends | DartsOrakel |
| **SCORING** | 100+ scores/match, 140+ scores/match, Ton-80 frequency, First 9-dart avg | DartsOrakel |
| **LEGS** | Avg legs/match, Deciding leg record, Legs won from behind %, Break of throw % | DartsOrakel |
| **SETS** | Sets/match (in set-format events), Set win % from behind | PDC |
| **FORM** | Last 10 matches W-L, Current tournament results, Recent TV event performance | Flashscore + PDC |
| **BULLSEYE** | Bull finish %, Bull checkout rate (for non-standard finishes) | DartsOrakel |

**B. Match Format & Context**
- Format: legs format (Premier League, World Series) vs sets format (World Championship)
- Best-of: BO11 legs, BO13, BO sets of legs — determines total legs possible
- Stage: group stage (less pressure) vs knockout (elimination pressure)
- TV event vs floor event: top players perform 3-5% better on TV (big-stage factor)
- Floor events (Players Championship): upsets more common, lower averages

**C. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: legs score, averages in those matches, 180s
- Recent form: last 10 matches W-L, average in last 10, checkout % trend
- Current tournament performance: is player in rhythm or struggling?

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both players avg >95? → More breaks of throw = more legs = O legs candidate
2. Both players checkout >40%? → Efficient leg closing → fewer legs → U legs candidate
3. One player avg >98, other <90? → Dominant win → U legs + ML combo
4. **Darts market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - 180s O/U → Total legs O/U → Set totals O/U → Correct score → ML (LAST RESORT)
5. In set-format: focus on total sets. In legs-format: focus on total legs.

**E. Context Factors (MANDATORY)**
- Venue: hometown crowd advantage (UK events favor UK players)
- Schedule: afternoon vs evening session, multiple matches in one day (fatigue)
- Ranking points: defending ranking → higher motivation
- Order of Merit implications: ProTour rankings, World Championship qualification

**Sources**: DartsOrakel (PRIMARY — averages, checkout, 180s, match history), PDC.tv (official stats, draws, results), Flashscore darts (form, live scores, H2H), BetExplorer darts (odds)

### 3.9 Handball Statistical Protocol — EXHAUSTIVE CHECKLIST
For every handball candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Team Statistics (Flashscore + EHF + League sites)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **GOALS** | Goals scored/match, Goals conceded/match, Combined avg, O/U 48.5/50.5/52.5/54.5 hit rates | Flashscore |
| **ATTACK** | Attack efficiency %, Fast breaks/match, 7-meter (penalty) goals/match, Turnovers/match | EHF/League stats |
| **DEFENSE** | Goals conceded/match, Blocks/match, Steals/match, Saves % (goalkeeper) | EHF/League stats |
| **GOALKEEPER** | Save %, 7-meter saves %, Saves/match, #1 vs #2 goalkeeper stats | EHF/League stats |
| **SUSPENSIONS** | 2-minute suspensions/match (CRITICAL: team plays 1 short → goals spike), Red cards/match | EHF/League stats |
| **HALF SPLITS** | 1st half goals avg, 2nd half goals avg (2nd halves typically higher-scoring by 1-2 goals) | Flashscore |
| **HOME/AWAY** | Goals scored home vs away, Goals conceded home vs away, Home advantage factor (HUGE in handball — 60-65% home win rate) | Flashscore |
| **PACE** | Attacks/match, Fast breaks/match (fast-break teams inflate totals) | League stats |

**B. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: total goals per game, margin, half-time scores
- Last 10 matches form: W-L, average total goals, scoring trends
- League standing context: top 4 vs bottom 4 = predictable. Mid-table = competitive.

**C. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both teams avg >28 goals scored/match? → O total goals candidate (combined >56)
2. Both teams poor defense (>29 conceded)? → O total goals STRONG candidate
3. Big mismatch + high-scoring favorite? → Handicap candidate
4. **Handball market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Half totals O/U → Game total goals O/U → Handicap → ML (LAST RESORT)
5. HOME ADVANTAGE is extreme: home team wins 60-65%. Factor this into ML and handicap.
6. 2nd half typically has 1-2 MORE goals than 1st half (fatigue + desperation scoring).

**D. Context Factors (MANDATORY)**
- Competition: Champions League (high intensity) vs domestic league (may rest players)
- Derby matches: more physical, more suspensions, sometimes lower-scoring
- Key player injuries: star pivot or goalkeeper absent = huge impact
- Fixture congestion: midweek European + weekend domestic = rotation risk
- Suspensions carried over: player accumulated suspensions → weakened lineup

**Sources**: Flashscore handball (form, H2H, live scores), EHF/eurohandball.com (Champions League stats), League-specific sites (PGNiG Superliga, Bundesliga handball, etc.), BetExplorer handball (odds), Sofascore (detailed match stats)

### 3.10 Table Tennis Statistical Protocol — EXHAUSTIVE CHECKLIST
For every table tennis candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Player Statistics (ITTF + Flashscore + tt-series)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **RANKING** | ITTF world ranking, Continental ranking, Ranking trajectory (rising/falling) | ITTF |
| **SETS** | Avg sets/match, Set win %, Deciding set frequency %, O/U 3.5/4.5 sets hit rate | Flashscore |
| **POINTS** | Avg points/set, Avg total points/match, Deuce frequency per set | Flashscore |
| **STYLE** | Playing style: attacking (pen/shake offensive) vs defensive (chopper/blocker) | ITTF player profiles |
| **SERVE** | Serve ace %, Service game dominance (first 3 balls) | Match video analysis/stats |
| **FORM** | Last 10 matches W-L, Current tournament results, Recent upset record | Flashscore |
| **SURFACE/BALL** | Equipment changes (new ball specifications affect different styles differently) | ITTF |

**B. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings: set scores, total points, deciding set frequency
- Recent form: last 10 matches W-L, quality of opponents beaten/lost to
- Tournament context: round (R32 = upsets common, QF+ = favorites dominate)

**C. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Close ranking (within 20 spots)? → O sets (competitive = more sets)
2. Big ranking gap (50+ spots)? → Set HC -1.5 or -2.5
3. Both aggressive players? → Higher total points per set → O total points
4. **Table tennis market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Total points O/U → Set totals O/U → Set handicap → ML (LAST RESORT)
5. Table tennis is HIGH-VARIANCE — rankings less predictive than in tennis. Reduce confidence by -0.5 for any TT pick.

**D. Context Factors (MANDATORY)**
- League vs tournament: WTT events vs national leagues have different dynamics
- Fatigue: multiple matches in one day (common in TT tournaments)
- Asian vs European style: different playstyles affect set lengths
- Home advantage: minimal in TT, but crowd can affect service rhythm

**Sources**: ITTF (rankings, player profiles), Flashscore table tennis (form, H2H, live scores, set scores), tt-series.com (WTT stats), BetExplorer table tennis (odds), Sofascore (match stats)

### 3.11 MMA/UFC Statistical Protocol — EXHAUSTIVE CHECKLIST
For every MMA candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Fighter Statistics (UFC.com/stats + Sherdog + Tapology)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **STRIKING** | Significant strikes landed/min, Strike accuracy %, Strikes absorbed/min, Strike defense % | UFC.com/stats |
| **GRAPPLING** | Takedowns attempted/15min, Takedown accuracy %, Takedown defense %, Submission attempts/15min | UFC.com/stats |
| **CLINCH** | Clinch strikes/fight, Clinch time %, Cage control time | UFC.com/stats |
| **GROUND** | Control time/fight, Ground strikes/min, Ground & pound effectiveness, Sweeps | UFC.com/stats |
| **CARDIO** | Pace change R1→R3 (does fighter fade?), Output in championship rounds (R4-R5) | Fight film analysis |
| **FINISH RATE** | KO/TKO %, Submission %, Decision % (for both wins AND losses) | Sherdog/Tapology |
| **RECORD** | Overall record, UFC record, Streak (current win/loss), Record vs ranked opponents | Sherdog |
| **FORM** | Last 5 fights: opponents, method, round, performance bonuses | Tapology |

**B. Matchup Analysis (CRITICAL in MMA)**
- **Striker vs Striker**: who has reach advantage? Who is more accurate? Chin durability?
- **Striker vs Grappler**: can the striker stuff takedowns (TDD%)? Does the grappler have a dangerous stand-up?
- **Grappler vs Grappler**: who controls top position? Submission threat comparison.
- **Southpaw vs Orthodox**: stance matchup creates different angles and openings
- **Size advantage**: weigh-in weight, walk-around weight, reach differential

**C. H2H and Recent Form (MANDATORY)**
- H2H: have they fought before? Result, method, controversial decisions?
- Recent form: last 5 fights — opponents quality, methods, KO/sub vulnerability trends
- Layoff: >12 months since last fight = ring rust risk (reduce confidence -0.5)

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both fighters finish rate >50%? → U rounds candidate (likely finish before the distance)
2. Both fighters decision rate >50%? → O rounds candidate (going to the scorecards)
3. High-level grappler vs mediocre TDD? → Method of victory: submission
4. **MMA market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Method of victory → O/U rounds → Round betting → ITD (inside the distance) → ML (LAST RESORT)
5. 3-round fights: O/U 1.5 rounds. 5-round fights: O/U 2.5 rounds.
6. Women's MMA: fewer finishes on average → O rounds default.

**E. Context Factors (MANDATORY)**
- Weight class: heavyweight (most KO variance) vs flyweight (more decisions)
- Fight card position: main event 5-rounders vs prelim 3-rounders
- Weight cut: did fighter miss weight? (affects cardio, chin, power)
- Camp/training: major camp change? New coach? Training partner issues?
- Motivation: title shot implications, rivalry, retirement fight
- Altitude: events at elevation (Mexico City, Denver) affect cardio

**Sources**: UFC.com/stats (official striking/grappling stats), Sherdog (records, fight history), Tapology (rankings, fight finder, MMA math), BetExplorer MMA (odds), ESPN MMA (odds, news), Flashscore (results)

### 3.12 Baseball (MLB) Statistical Protocol — EXHAUSTIVE CHECKLIST
For every baseball candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Starting Pitcher Analysis (BaseballSavant + Baseball-Reference)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **TRADITIONAL** | ERA, WHIP, W-L record, K/9, BB/9, IP/start avg | Baseball-Reference |
| **ADVANCED (Statcast)** | xERA (expected ERA), xFIP, SIERA, FIP (fielding-independent pitching) | BaseballSavant |
| **BATTED BALL** | Hard hit %, Barrel %, Ground ball %, Fly ball %, Line drive % | BaseballSavant |
| **PITCH MIX** | Pitch types %, Velocity trends (declining velocity = red flag), Spin rate | BaseballSavant |
| **SPLITS** | vs LHB/RHB splits (vulnerable to one side?), Home/away ERA, Day/night splits | Baseball-Reference |
| **RECENT** | Last 3-5 starts: IP, ER, K, BB (current form, NOT season average) | ESPN/Baseball-Reference |
| **VS OPPONENT** | Career stats vs this team's current lineup, Batter vs pitcher matchup data | BaseballSavant |

**B. Bullpen Analysis**
- Bullpen ERA (last 7/14/30 days — NOT season-long, bullpens fluctuate rapidly)
- Bullpen usage: how many innings pitched in last 3 days? Overworked = blowup risk
- Closer availability: is the closer available? Back-to-back save situations?
- High-leverage reliever stats: setup man and closer effectiveness

**C. Team Offense**
- Runs/game, OPS, wRC+ (weighted runs created)
- Team BABIP (luck indicator: high BABIP = regression DOWN, low = regression UP)
- K rate and BB rate (discipline at the plate)
- vs LHP and vs RHP splits (matchup with today's starter)
- Home/away splits, Day/night splits
- Lineup confirmation: any key bats out of lineup? Check ESPN/team social 2-3h before.

**D. H2H and Recent Form (MANDATORY)**
- Season series: W-L, runs scored in each game
- Last 10 games form: W-L, runs scored/allowed, O/U record
- Home/road record this season

**E. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Both starters xERA > 4.50? → O runs candidate (bad pitching = runs)
2. Elite starter (xERA < 3.00) vs weak lineup (wRC+ < 90)? → U runs candidate + F5 under
3. Bullpen overworked for both teams? → O runs (especially late-inning totals)
4. **Baseball market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - First 5 innings O/U → Team totals → Game totals O/U → Run line (±1.5) → ML (LAST RESORT)
5. F5 (first 5 innings) removes bullpen variance — MOST RELIABLE market.
6. Team totals are less efficient than game totals — good for pitcher mismatch.

**E. Context Factors (MANDATORY)**
- **Weather (CRITICAL):** Wind direction + speed at ballpark. Wind blowing out at Wrigley = +1.5 runs avg. Rain delay risk.
- **Park factor:** Coors Field (extreme hitter), Petco Park (extreme pitcher). Use park factor adjustment.
- **Day game after night game:** teams perform worse (fatigue, shorter prep)
- **Travel:** cross-country travel, series opener after long flight
- **Umpire:** home plate umpire's historical K-rate and run-scoring impact
- **Injury report:** check MLB injury report for key position players (C, SS, star bats)

**Sources**: BaseballSavant (Statcast — xERA, xFIP, barrel%, pitch mix — PRIMARY), Baseball-Reference (traditional stats, splits), ESPN MLB (odds, injury reports, lineups), SBR (odds comparison), ScoresAndOdds (US odds), BetExplorer baseball (odds). **Note: FanGraphs is BLOCKED — use BaseballSavant as primary.**

### 3.13 Padel Statistical Protocol — EXHAUSTIVE CHECKLIST
For every padel candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Pair Rankings and Form (PadelFIP + PremierPadel + Sofascore)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **RANKING** | FIP world ranking (both pairs), Ranking points gap, Ranking trajectory | PadelFIP |
| **FORM** | Last 3-5 tournament results (round reached, opponents beaten/lost to) | PremierPadel/Sofascore |
| **TOURNAMENT PATH** | Current tournament: previous round result, score, physical condition | PremierPadel |
| **SETS** | Avg sets/match, 3-set match %, O/U 2.5 sets hit rate | Sofascore |
| **GAMES** | Avg total games/match, Games per set avg, O/U game totals hit rate | Sofascore |
| **SERVE** | Service game hold %, Break point conversion rate | Match-level Sofascore |
| **PARTNERSHIP** | Partnership duration (>6 months = stable), Partner change history | PadelFIP/PremierPadel |

**B. Pair Comparison**
- Ranking points gap: >3000 pts = heavy favorite, 1000-3000 = moderate, <1000 = competitive
- Individual player ranking vs pair ranking (sometimes a weaker individual in a strong pair)
- Playing style: aggressive smash pair vs defensive lob pair → court surface matters

**C. H2H and Partnership History (MANDATORY)**
- H2H record between pairs (Sofascore padel → match detail → H2H tab)
- Partnership duration: established pairs (>6 months) are more stable than new partnerships
- Partner change history: recent partner change = volatility, regression risk
- Previous meeting scores and set counts

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Ranking gap <1000 pts? → O2.5 sets candidate (competitive = 3 sets likely)
2. Ranking gap >3000 and Major/P1? → Favorite ML (top pairs dominate higher tiers)
3. New partnership in first 2 tournaments? → Upset potential (underpriced)
4. **Padel market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Game totals O/U → Set totals O/U 2.5 → Set handicap -1.5 → ML (LAST RESORT, 1.40-2.20 range only)
5. ML only viable in 1.40-2.20 range. Below 1.35 = no value. Above 2.40 = too risky.
6. VALUE ZONE: pairs ranked 10-25 meeting = real uncertainty, ML 1.60-2.20.

**E. Context Factors (MANDATORY)**
- Tournament tier: Major/P1/P2/Bronze — higher tiers = more predictable (top pairs perform)
- Round: R32/R16 = more upsets, QF+ = favorites dominate
- Surface: indoor vs outdoor — wind affects lob-heavy padel significantly
- Fatigue: 3-set QF yesterday → SF today = fatigue factor, especially older pairs
- Travel: European vs South American leg → travel fatigue + altitude differences

**Sources**: PadelFIP.com (rankings — PRIMARY), PremierPadel.com (draws, match stats), Sofascore padel (H2H, form, livescores, set/game stats), BetExplorer/OddsPortal padel (odds). No major tipster sites cover padel — rely on ranking analysis and H2H.

### 3.14 Speedway / Żużel Statistical Protocol — EXHAUSTIVE CHECKLIST
For every speedway candidate, collect ALL of the following. Missing any category = INCOMPLETE analysis.

**A. Team & Rider Statistics (SpeedwayEkstraliga + SportoweFakty)**

| Stat Category | Metrics to Collect | Source |
|--------------|-------------------|--------|
| **ROSTER** | All 7 riders (5 seniors + 2 juniors) in announced lineup, Tactical reserve (R) | SpeedwayEkstraliga |
| **RIDER AVERAGES** | Rider avg at THIS track (filter by venue — MOST IMPORTANT STAT), Season avg, Home vs away avg | SpeedwayEkstraliga |
| **TEAM TOTAL** | Team match average (home + away separately), Points projection from rider track avgs | SpeedwayEkstraliga |
| **JUNIORS** | U24 rider averages (#6, #7, #14, #15 slots), Junior contribution to team total | SpeedwayEkstraliga |
| **RESERVE** | Tactical reserve usage patterns, Reserve rider average, Manager reserve strategy | SpeedwayEkstraliga |
| **HEAT LEADERS** | Top 2 riders avg (heat leaders carry 50-60% of team points) | SpeedwayEkstraliga |
| **HOME RECORD** | Home team home record this season + last 2 seasons, Avg margin at home | SpeedwayEkstraliga |
| **AWAY RECORD** | Away team away record, "Good travelers" vs "collapse away" pattern | SpeedwayEkstraliga |

**B. Home Advantage Deep Analysis (CRITICAL — home wins 70-75%)**
- HOME ADVANTAGE is EXTREME in speedway — the home team prepares the track to suit their riders
- Track preparation: hard track favors speed/technique riders, soft track favors gating/power riders
- Track dimensions: small tracks (e.g., Częstochowa) vs large tracks (e.g., Leszno) favor different riding styles
- Home team's home record this season and last 2 seasons
- Away team's away record — some teams are good travelers (e.g., Sparta Wrocław), others collapse away

**C. H2H and Recent Form (MANDATORY)**
- Last 5 H2H meetings at this venue: scores, margins, heat-by-heat patterns
- Season form: last 3-5 matches, scores, trends
- Rider vs rider: key individual matchups (heat leader vs heat leader)

**D. MARKET RANKING — DECIDE THE BEST BET (MANDATORY)**
1. Home rider averages sum > away by 10+? → Handicap candidate (home team to cover large spread)
2. Both teams with strong heat leaders but weak juniors? → Total points O/U candidate
3. Away team has "good traveler" record? → Away HC / Away ML upset potential
4. **Speedway market hierarchy** (most inefficient → most efficient — ML is LAST RESORT):
   - Total points O/U (e.g., O88.5) → Handicap (e.g., home -8.5) → Match winner (LAST RESORT)
5. Match winner usually too short for home team (1.20-1.40) — HC is the VALUE market.
6. Calculate team total from rider track averages: sum all 7 riders' venue-specific averages × heat appearances.

**E. Lineup Changes and Late News (TIME-SENSITIVE — check 2h before event)**
- **SportoweFakty.wp.pl/zuzel**: publishes confirmed lineups 2-3h before each match — CRITICAL source
- Injury updates: speedway injuries are frequent and impactful (one rider out = 6-10 points lost)
- Rider substitutions: tactical reserve (R) or guest rider changes — check official Ekstraliga communications
- Track conditions: weather (rain delays, wet track = more falls and unpredictable results)

**F. Expert Analysis Sources (Deep-Dive)**
- **SportoweFakty.wp.pl/zuzel**: PRIMARY source for Polish speedway analysis:
  - Match previews with expert predictions ("zapowiedź rundy")
  - Individual rider form analysis
  - Track condition reports
  - Post-match analysis and rider ratings
  - Lineup announcements with commentary
  **Navigation**: Main page → find today's match preview article → read expert analysis and check comments
- **Ekstraliga.pl**: official PGE Ekstraliga site:
  - Full season statistics (rider averages, team totals)
  - League table and standings context
  - Official lineup announcements
  - Historical results at each venue
- **Żużlowe fora** (Polish speedway forums): speedwayfans.pl, forum.gazeta.pl/zuzel — local knowledge

**G. Context Factors (MANDATORY)**
- Weather: rain = wet track = more falls, unpredictable, reduce confidence -1
- Track watering: heavy watering favors gaters, light watering favors technique riders
- Season stage: early season (riders finding form) vs late season (championship implications)
- Guest riders: foreign guest riders may not know the track — check their track history
- Relegation/promotion implications: bottom teams fight harder

**Sources**: SpeedwayEkstraliga.pl (stats, standings, lineups — PRIMARY), SportoweFakty.wp.pl/zuzel (expert analysis, match previews, rider form), BetExplorer/OddsPortal speedway (odds), Flashscore (results/settlement)

### 3.15 General Principle for ALL Sports — EXHAUSTIVE ANALYSIS MANDATE
**EVERY sport protocol above is MANDATORY, not optional.** Missing ANY stat category = INCOMPLETE analysis = pick CANNOT be finalized.

The universal approach for EVERY sport:
1. **Collect ALL stats** from the sport-specific table above. Not some. ALL.
2. **Split stats by home/away** where applicable. Aggregate stats hide crucial venue differences.
3. **Calculate hit rates** for O/U lines: how often does this team/player go O/U on this specific line?
4. **RANK markets by safety**: hit_rate × consistency × odds_value = best market. Choose the SAFEST bet, not the most interesting.
5. **Present TOP 2-3 markets** per match with statistical backing BEFORE choosing which to bet.
6. Get statistical data from specialist sources (sport-specific)
7. Get form data from general sources (Flashscore, Sofascore)
8. Get odds data from market sources (BetExplorer, OddsPortal)
9. **ALWAYS prefer statistical/totals markets over ML/winner markets**
10. The less liquid the market, the more likely it is mispriced — this is our edge
11. **H2H is MANDATORY for EVERY sport, EVERY candidate.** No exceptions.
12. **Context factors are MANDATORY for EVERY sport.** Injuries, weather, motivation, fixture schedule.

**FAILURE MODE TO AVOID:** Picking a market because it "feels right" or because you saw one stat. CORRECT MODE: collect ALL stats → calculate which market has the highest hit rate → verify with odds → THEN pick.

### 3.16 Sport-Specific Source URLs (Quick Reference)
When scanning events, use these URLs directly:
- **Football**: betexplorer.com/football/ | flashscore.com/football/
- **Tennis**: betexplorer.com/tennis/ | flashscore.com/tennis/
- **Basketball**: betexplorer.com/basketball/ | flashscore.com/basketball/ | espn.com/nba/
- **Hockey**: betexplorer.com/hockey/ | flashscore.com/hockey/ | espn.com/nhl/
- **Baseball**: betexplorer.com/baseball/ | flashscore.com/baseball/ | espn.com/mlb/
- **Volleyball**: betexplorer.com/volleyball/ | flashscore.com/volleyball/
- **Esports**: betexplorer.com/esports/ | gosugamers.net | liquipedia.net
- **Snooker**: betexplorer.com/snooker/ | flashscore.com/snooker/ | cuetracker.net
- **Darts**: betexplorer.com/darts/ | flashscore.com/darts/ | dartsorakel.com
- **Handball**: betexplorer.com/handball/ | flashscore.com/handball/
- **Table Tennis**: betexplorer.com/table-tennis/ | flashscore.com/table-tennis/
- **MMA**: betexplorer.com/mma/ | sherdog.com | tapology.com | ufc.com/events
- **Padel**: sofascore.com/padel | betexplorer.com/padel/ | premierpadel.com | padelfip.com/ranking-male/
- **Speedway**: speedwayekstraliga.pl | sportowefakty.wp.pl/zuzel | betexplorer.com/speedway/

---

## STEP 3B: TIME-SENSITIVE DATA COLLECTION (MANDATORY — run close to event time)

This step bridges Steps 3-4 and Step 8. It MUST be executed **within 2-3 hours of the earliest event kickoff**. Time-sensitive factors change the analysis and can invalidate picks approved earlier.

### 3B.1 Lineup and Injury Verification
For EVERY approved pick, verify the following close to kickoff:
- **Football**: Confirmed lineups (Flashscore shows lineups ~1h before kickoff). Check for surprise benchings, tactical changes, rotation.
- **Tennis**: Player not withdrawn? Check ATP/WTA official Order of Play. Retirement risk for players who went 3 sets in previous round.
- **Hockey**: Starting goalie confirmed? (DailyFaceoff.com or team social media). Goalie change = thesis invalidated for totals picks.
- **Basketball**: Injury report updates (ESPN, official NBA injury report). Star player ruled out = recalculate.
- **Baseball**: Starting pitcher confirmed? (ESPN, BaseballSavant). Pitcher change = void the pick.
- **Speedway**: Lineup confirmation from SportoweFakty or SpeedwayEkstraliga.pl (published 2-3h before). Rider changes drastically affect team strength.
- **Padel**: Pair withdrawal? Check PremierPadel.com draw page for walkovers.
- **All sports**: Check Flashscore/Sofascore for any postponement, cancellation, or venue change.

### 3B.2 Weather Check (Outdoor Sports)
- Football: Rain → fewer corners, more slippery = fewer cards. Wind → more long balls, more corners.
- Tennis: Extreme heat → fatigue favors fitter player. Wind → serve quality drops, more breaks.
- Speedway: Rain delay = track conditions change completely. Wet track = more falls, less predictable.
- Padel: Outdoor events — wind is a major factor (disrupts lobs, the key padel shot).
- Source: weather.com or local weather for event city.

### 3B.3 Late News Scan
- Check Flashscore match detail pages for "info" or "lineups" tabs
- Check team official social media (Twitter/X) for late team news
- Check SportoweFakty for żużel late lineup announcements
- **If any time-sensitive finding contradicts the pick thesis**: re-evaluate immediately. If the bear case strengthens → downgrade or void the pick.

### 3B.4 Odds Movement Check
- Compare current odds to the odds recorded at analysis time.
- Steam move (odds shortening rapidly on one side) → follow if consistent with thesis, flag if against
- Reverse line movement (RLM: line moving against the public side) → strong signal from sharp money
- If Betclic odds have moved >10% since analysis → recalculate EV. If EV now ≤0 → void the pick.

---

## STEP 4: TIPSTER DEEP-DIVE — Structured Community Cross-Check

This step is MANDATORY. Not a quick glance — a structured, deep extraction from each source. Tipster sites like Zawod Typer provide INDIVIDUAL TIPSTER ARGUMENTS with reasoning — these are invaluable for discovering angles, confirming/refuting statistical theses, and building confidence.

### 4.1 Source Rotation
For EACH candidate event, check at least 2 ARGUMENT-BASED tipster sources from this list:
- **Polish**: Zawod Typer (PRIORITY — see 4.1a), Typersi, Meczyki
- **International**: PicksWise, BetIdeas, OLBG, Sportsgambler
- **US sports**: PicksWise
- **Esports**: GosuGamers
- **ROI-tracked (bare picks, no arguments)**: Tipstrr

Note: The following sources are BLOCKED and must NOT be attempted:
Forebet, FootySupertips, Windrawwin, BettingExpert, Protipster, Oddspedia, SportyTrader, Predictz, Trafiamy, Blogabet, HLTV. See source-registry.md blocked list.

**When a tipster source is blocked:** Do NOT skip the tipster step. Search for alternative tipster sites. Use Google to find "[event name] prediction" or "[event name] tips" to discover new tipster pages. If you find a working tipster source not in the registry, use it and add it to the source log. NEVER declare tipster consensus impossible — if 7 sites are blocked, find the 8th and 9th.

### 4.1a Argument-Based Tipster Deep-Dive Protocol (MANDATORY)

Multiple tipster sites feature INDIVIDUAL TIPSTERS WHO POST DETAILED WRITTEN ARGUMENTS for each pick. These are the highest-value tipster sources because you get reasoning, not just a bare pick. This is NOT a quick headline check — you must navigate into match/event pages and read what each tipster wrote.

**Argument-based tipster sites (use at least 2 per candidate):**

| Site | URL | Sports | Language | How to navigate |
|------|-----|--------|----------|----------------|
| **Zawod Typer** | zawodtyper.pl | Football, tennis, basketball | PL | Daily page: `/typy-dnia-[DD]-[month]-[weekday]/`. Scroll deeply (lazy-loaded). Search: `/szukaj?q=[team]`. |
| **Typersi** | typersi.pl | Football, tennis, other | PL | Daily tips page. Navigate to specific match pages for individual tipster arguments. |
| **OLBG** | olbg.com/tips | Football, racing, all sports | EN | Navigate to sport → today's tips. Each tip has a written reason. Filter by sport/competition. |
| **PicksWise** | pickswise.com | NBA, NHL, MLB, NFL, soccer, tennis | EN | Navigate to sport → game preview pages. Expert analysis with detailed reasoning per game. |
| **BetIdeas** | betideas.com/tips | Football (BTTS, corners, goals) | EN | Navigate to specific tip category (corner-betting-tips, btts-tips). Model-backed reasoning. |
| **Meczyki** | meczyki.pl/typy-bukmacherskie | Football | PL | Navigate to daily tips. Click individual match for tipster arguments. Good for LaLiga/Bundesliga. |
| **Sportsgambler** | sportsgambler.com/predictions | Football, US sports | EN | Sport-specific prediction pages with match previews and reasoning. |

**Execution steps (same for ALL sites):**
1. Navigate to the site's daily tips / predictions page for the relevant sport.
2. Scroll deeply — many sites lazy-load content. Scroll at least 5-10 times to load all tips.
3. For EACH candidate event on the page:
   a. Identify all tipsters/analysts who posted picks for that event.
   b. Read EACH tipster's full argument — not just the pick, but WHY they picked it.
   c. Extract: tipster/analyst name, specific pick (market + selection), stated odds, written reasoning/argument.
   d. Count how many tipsters agree vs disagree on the direction.
4. If a candidate event is not on the main page, use the site's search function.
5. Check featured/highlighted sections for higher-confidence tips.

**What to extract from each tipster argument:**
- Statistical references ("Villarreal averages 6.2 corners away")
- Tactical/motivational context ("Oviedo needs points to avoid relegation")
- Injury/lineup info ("Without key striker X")
- Historical patterns ("Last 5 H2H had BTTS")
- Market-specific reasoning ("Referee averages 4.5 cards")
- Model outputs ("Our model gives 68% BTTS probability")

**Why this matters:** Argument-based tipster sites contain LOCAL KNOWLEDGE and EXPERT REASONING that pure statistics miss. Polish tipsters on Zawod Typer and Meczyki follow La Liga, Eredivisie, and Ekstraklasa deeply. PicksWise analysts write detailed NBA/NHL previews with pace, efficiency, and injury context. OLBG tipsters compete for accuracy rankings, so their arguments tend to be well-researched. A tipster saying "Villarreal rotates for Europa League" or "Lakers are 2-8 ATS on back-to-backs" is actionable context you won't find in raw stats.

### 4.2 Extraction Template
For each tipster source x event, extract:
```
Source: [name]
Tipster: [individual tipster name if available, e.g., "marekbet87"]
Event: [match]
Pick: [specific selection, e.g., "Over 9.5 corners"]
Reasoning: [key argument in 1-2 sentences — MUST include the tipster's actual reasoning, not just the pick]
Confidence: [tipster stated confidence if available]
Agreement with my stats thesis: [YES/NO/PARTIAL]
```

A pick without extracted reasoning is INCOMPLETE. If the source provides arguments, you MUST read and record them.

### 4.3 Consensus Analysis
After checking all sources for a candidate:
- **>=70% agreement with stats direction**: boost confidence +0.5 (round to nearest integer)
- **>=60% contradiction of stats direction**: RED FLAG. Investigate why. Check for info the stats miss (injuries, tactical shift, weather). If no explanation -> reduce confidence -1 or skip.
- **Mixed/split consensus (40-60%)**: neutral — rely on stats alone, no adjustment.
- **Strong tipster argument against your thesis**: even if only 1 tipster, if the argument is specific and fact-based (not just opinion), investigate before finalizing.

### 4.4 Angle Discovery
Tipster analysis often reveals:
- Tactical changes not reflected in stats (new formation, defensive approach)
- Managerial changes or caretaker effects
- Weather conditions (wind for corners, rain for under)
- Motivation context (relegation, qualification, nothing to play for)
- Squad rotation for upcoming bigger games
- Travel fatigue (midweek European games -> weekend league)
- Local knowledge (Polish league expertise, lower-division insights)
- Referee tendencies for statistical markets (cards, corners, fouls)

Record any such angle. If the angle contradicts your stats thesis, take it seriously — tipsters with arguments > tipsters with bare picks.

---

## STEP 5: ODDS — Price Analysis and Expected Value

### 5.1 Market-Best Price
For each candidate, get the market-best odds from BetExplorer or OddsPortal (whichever has better coverage for the market).

### 5.2 True Probability Estimation
Estimate the TRUE probability of the selection winning. Use this hierarchy:
1. **Pinnacle/sharp book implied probability** (if available): strip the margin. Formula: `1 / pinnacle_odds` then normalize by dividing by the sum of all outcomes.
2. **Statistical model**: from SoccerStats, Betaminic, or sport-specific models.
3. **Market consensus**: average of multiple bookmaker implied probabilities (from BetExplorer odds comparison).
4. **If none available**: use your best judgment from the statistical analysis, but mark as LOWER CONFIDENCE.

### 5.3 Expected Value Calculation
```
EV = (true_probability x betclic_odds) - 1
```
- EV > 0: VALUE BET — proceed
- EV <= 0: NO VALUE — skip unless the analysis strongly suggests the true probability is being underestimated by the market
- Record EV for every pick in the report

### 5.4 Price Gap Verification
```
price_gap_pct = 100 x ((betclic_odds / market_best_odds) - 1)
```
- Low-risk picks: reject if gap < -3%
- Higher-risk picks: reject if gap < -5%
- If gap is significantly POSITIVE (>+3%), double-check — the market might know something you do not.

### 5.5 Line Movement Check
Check OddsPortal line movement graph for each candidate:
- **Line moving TOWARD your selection** (odds dropping): public money agrees, but you may be buying at a worse price. Lock in NOW if you still have value.
- **Line moving AWAY from your selection** (odds rising): either the market is wrong (value opportunity) OR there is information you are missing (injury, weather). Investigate before proceeding.
- **Reverse Line Movement (RLM)**: public money on one side, but line moves the other way = sharp money on opposite side. Align with sharp money if possible.
- **Steam move**: sudden dramatic line movement = institutional/syndicate bet. Follow steam if it aligns with your thesis.

### 5.6 Kelly Criterion Staking (recommended, not mandatory)
Optimal stake fraction: `f = (b * p - q) / b`
where:
- b = decimal odds - 1
- p = estimated true probability
- q = 1 - p

Apply FRACTIONAL Kelly (1/4 Kelly) for bankroll safety:
```
stake = (bankroll * f) / 4
```
Cap at max coupon stake (3.00 PLN LR, 2.00 PLN HR). Floor at 0.50 PLN (minimum bet).

Example: true prob 55%, odds 1.80, bankroll 46 PLN:
- b = 0.80, f = (0.80 x 0.55 - 0.45) / 0.80 = -0.0125 -> NO BET (EV is negative!)
- true prob 60%, odds 1.80: f = (0.80 x 0.60 - 0.40) / 0.80 = 0.10 -> 1/4 Kelly = 0.025 x 46 = 1.15 PLN

If Kelly suggests 0 or negative stake -> SKIP. The odds do not have value.

---

## STEP 6: CONTEXT — Pre-Match Verification Checklist

Before APPROVING any pick, verify these contextual factors:

### 6.1 Universal Checklist
- [ ] **Fixture confirmed**: match is still scheduled (not postponed/cancelled) — check Flashscore
- [ ] **Kickoff within window**: match starts within the betting-day window
- [ ] **Key absences**: check team news for suspensions, injuries, rest (Flashscore lineups section)
- [ ] **Competition context**: league position, stakes (relegation/promotion/qualification/dead rubber)
- [ ] **Fixture congestion**: did the team play <72 hours ago? Is there a big game in <72 hours? (look-ahead trap)

### 6.2 Football-Specific
- [ ] **Referee** (for cards/fouls markets): check referee assignment. Some refs average 5+ cards, others 2-3. SoccerStats or Transfermarkt referee stats.
- [ ] **Weather** (for corners/goals): heavy rain -> fewer corners, more cautious play. Strong wind -> more corners, unpredictable crosses.
- [ ] **Tactical context**: is either team changing formation? New manager? Defensive stance expected?

### 6.3 Tennis-Specific
- [ ] **Withdrawal check**: search Flashscore for "walkover" or "cancelled" on the match page.
- [ ] **Physical condition**: did the player play a grueling 3-setter yesterday? Marathon match fatigue.
- [ ] **Surface form**: is the player adapting to a new surface (e.g., hard court -> clay)?

### 6.4 US Sports Specific (NBA/NHL/MLB)
- [ ] **Injury report**: official injury report (GTD, OUT, PROBABLE)
- [ ] **Playoff series context**: home/away split, Zig-Zag theory (team coming off road loss)
- [ ] **Rest days**: back-to-back games penalize totals (teams more tired -> lower scoring, or more sloppy -> higher scoring depending on sport)

### 6.5 UPSET RISK ASSESSMENT — MANDATORY FOR EVERY CANDIDATE (never skip)

**WHY THIS EXISTS:** On 2026-04-24, Shelton ML @1.61 lost to qualifier Prizmic — killing 2 coupons and ~25 PLN in unrealized returns. Post-mortem revealed the upset scored 8.5/10 on a systematic checklist. This step now catches future upsets BEFORE they enter coupons.

**WHEN TO RUN:** For EVERY candidate pick, BEFORE approving it. Score every candidate on the sport-specific checklist below. The score determines which markets are allowed.

**THE PARADOX RULE (CRITICAL INSIGHT):**
> High upset risk makes STATISTICAL OVER markets MORE profitable — a competitive match produces more total play (games, frames, sets, corners, goals).
> Low upset risk makes statistical OVERS DANGEROUS — blowouts produce fewer total play units.
>
> Shelton-Prizmic: 36 games (O22.5 wins by +13.5). Struff-Michelsen: 15 games (O22.5 misses by -7.5).
>
> **USE THIS:** When upset score is HIGH → prefer OVER totals (games, frames, rounds). When upset score is LOW → prefer UNDER, handicaps, or skip.

---

#### 6.5.1 TENNIS Upset Risk Checklist (score 0-12, threshold ≥4)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Surface mismatch** | 0-2 | Favorite's surface win% 10%+ lower than overall? Hard-court player on clay? Clay specialist on grass? Check TennisAbstract surface splits. |
| 2 | **Rising underdog** | 0-2 | Career-high ranking in last 4 weeks? Won Challenger/event recently? NextGen finalist? Breakthrough phase? |
| 3 | **Giant-killer history** | 0-1 | Any top-20 scalps in last 12 months? Competitive sets against top-10? |
| 4 | **Age/trajectory advantage** | 0-1 | Underdog ≤22yo in breakthrough phase? Favorite ≥30yo showing decline? |
| 5 | **Favorite's tournament history** | 0-1 | Best result at this tournament worse than QF? Never won on this surface at Masters/Slam level? |
| 6 | **Qualifier match fitness** | 0-0.5 | Underdog came through qualifying (2-3 extra wins = match-sharp and confident)? |
| 7 | **First H2H meeting** | 0-0.5 | No prior data = uncertainty premium. Unknown matchup dynamics. |
| 8 | **Serve dependency on slow surface** | 0-1 | Favorite's game built on big serve? Playing on clay/slow hard? Serve effectiveness drops 25-30% on clay. |
| 9 | **Altitude factor** | 0-0.5 | Madrid (660m) — thinner air, ball flies faster, partially neutralizes clay effect. Huge servers regain some power. |
| 10 | **Previous round fatigue** | 0-0.5 | Favorite played grueling 3-setter in previous round? Underdog had easy win or rest? |
| 11 | **Late-career complacency** | 0-0.5 | Favorite 28+yo in R1/R2, history of slow starts? Underdog has nothing to lose? |
| 12 | **Return game strength** | 0-0.5 | Underdog has high return points won % on this surface? Can neutralize serve advantage? |
| 13 | **Sharp money signal** | 0-0.5 | Line moving TOWARD underdog despite public on favorite? Smart money sees value. |
| 14 | **Draw section look-ahead** | 0-0.5 | Favorite has easy draw ahead — might look past R1/R2 opponent (trap game)? |

**Thresholds:**
- **≥4:** AVOID ML completely. Use game totals O/U (Paradox Rule: competitive match = more games).
- **≥6:** Extra caution even on totals. Only STRONG ratio (≤1.15) for O22.5+. Prefer O20.5/O21.5.
- **≥8:** SKIP entirely OR only with STRONG ratio on conservative line (O20.5). This is near-certain upset territory.

---

#### 6.5.2 FOOTBALL Upset Risk Checklist (score 0-14, threshold ≥4)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Fixture congestion** | 0-2 | Favorite played <72h ago (CL/EL midweek → weekend)? Key players rotated? |
| 2 | **Relegation desperation** | 0-1.5 | Underdog fighting relegation? Last 5 matches in relegation zone? Teams in desperation play harder. |
| 3 | **Cup/league priority split** | 0-1 | Favorite has cup semi/final or CL knockout in <5 days? Manager will rotate. |
| 4 | **Strong team playing away** | 0-1 | Favorite's away form significantly worse than home? Away win% <40%? |
| 5 | **New manager bounce** | 0-1.5 | Underdog changed manager in last 3 matches? New manager bounce = unpredictable results. |
| 6 | **H2H bogey team** | 0-1 | Underdog won 3+ of last 5 H2H at this venue? Historical dominance overrides league position. |
| 7 | **Key absences (≥2)** | 0-1.5 | Favorite missing 2+ first-choice starters? Check Flashscore/ESPN injury reports. |
| 8 | **Nothing to play for** | 0-1 | Favorite already qualified/safe/champion-elect? Low motivation = surprise losses. |
| 9 | **International break return** | 0-1 | First match after international break? Disrupted rhythm, travel, national team injuries. |
| 10 | **Derby/rivalry factor** | 0-1 | Local derby? These defy form — bottom team CAN beat top team in derbies. |
| 11 | **Altitude difference** | 0-0.5 | Match at altitude (La Paz, Quito, Mexico City)? Visitors suffer physically. |
| 12 | **Artificial turf** | 0-0.5 | Home team plays on synthetic pitch? Visitors unfamiliar = disrupted passing. |

**Thresholds:**
- **≥4:** Avoid ML/1X2 on favorite. Use corners, cards, fouls, BTTS, DC, DNB.
- **≥6:** Strong upset candidate. Statistical markets only. If corners: home team corner advantage may flip.
- **≥8:** Near-certain form disruption. Prefer UNDER markets or skip entirely.

---

#### 6.5.3 BASKETBALL Upset Risk Checklist (score 0-10, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **B2B 2nd night** | 0-2 | Favorite on 2nd night of back-to-back? -2 to -4 pts from average expected. |
| 2 | **Star player questionable** | 0-2 | Star (top-2 scorer) listed GTD/questionable? If ruled out → recalculate completely. |
| 3 | **Schedule fatigue** | 0-1 | 4-in-5 nights or 5-in-7? Extreme fatigue, especially for older rosters. |
| 4 | **Travel >1500km in 48h** | 0-1 | Cross-country flight (EST→PST)? Jet lag factor, especially for afternoon tip-offs. |
| 5 | **Playoff series shift** | 0-1 | G3/G4 after team led 2-0? Trailing team adjusts — Zig-Zag theory. |
| 6 | **Blowout reversal** | 0-1 | Favorite won by 20+ last game? Regression toward mean in next game. |
| 7 | **Altitude (Denver)** | 0-0.5 | Game in Denver? Visitors gas out in 4th quarter due to elevation. |
| 8 | **Overtime previous game** | 0-0.5 | Favorite went to OT in previous game? Key players with 40+ minutes. |
| 9 | **Coach revenge game** | 0-0.5 | Former coach vs old team? Extra motivation for underdog. |
| 10 | **Post-trade disruption** | 0-1 | Major trade in last 7 days? Chemistry disruption, new rotations. |

**Thresholds:**
- **≥3:** Avoid ML. Use team totals, game totals, quarter totals, spreads.
- **≥5:** Strong upset candidate. Statistical markets only. Reduce all exposure to this game.

---

#### 6.5.4 HOCKEY Upset Risk Checklist (score 0-10, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Goalie uncertain/backup** | 0-2 | Starter not confirmed on DailyFaceoff? Backup goalies have 5-8% worse save rate. |
| 2 | **B2B fatigue** | 0-2 | 2nd night of back-to-back? Backup goalie likely + skater fatigue. |
| 3 | **PP/PK regression** | 0-1 | Favorite on 30%+ PP over last 10 games? Will regress to ~20%. |
| 4 | **Road team in playoffs G3+** | 0-1 | Away team in a playoff series after losing at home? Desperate = dangerous. |
| 5 | **Elimination desperation** | 0-1 | Underdog facing elimination? Goalies stand on their heads in elimination games. |
| 6 | **3-in-4 nights** | 0-1 | Extreme schedule density → rest management, backup appearances. |
| 7 | **Empty net adjustment** | 0-0.5 | Trailing teams go empty net → inflates total goals in final minutes. |
| 8 | **Revenge game** | 0-0.5 | First meeting after a big trade or controversial hit? Extra motivation. |

**Thresholds:**
- **≥3:** Avoid ML. Use period totals, game totals, puck line.
- **≥5:** Strong upset candidate. Only totals markets. Confirm goalie before placing.

---

#### 6.5.5 BASEBALL Upset Risk Checklist (score 0-10, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **SP ERA >4.50 or rookie** | 0-2 | Favorite's starting pitcher struggling or debuting? Check BaseballSavant xERA. |
| 2 | **Bullpen fatigue** | 0-1.5 | Bullpen threw 6+ IP in last 2 days? Closer unavailable? |
| 3 | **Platoon advantage** | 0-1 | Lineup stacked with hitters who mash the SP's handedness? |
| 4 | **Day after night** | 0-1 | Day game after night game? Teams perform worse (shorter prep, fatigue). |
| 5 | **Key batter sitting** | 0-1 | Star hitter (top-2 OPS) out of lineup? Rest day? Check ESPN lineups. |
| 6 | **Umpire factor** | 0-1 | Home plate umpire with historically high run totals? Or low K-rate favoring hitters? |
| 7 | **Weather at ballpark** | 0-1 | Wind blowing out at Wrigley/Coors = +1.5 runs avg. Extreme cold = dead ball. |
| 8 | **Cross-country travel** | 0-0.5 | Series opener after coast-to-coast flight? Jet lag affects early innings. |

**Thresholds:**
- **≥3:** Avoid ML. Use F5 totals, team totals, game totals.
- **≥5:** Strong upset territory. Only F5 under or totals with confirmed pitching.

---

#### 6.5.6 VOLLEYBALL Upset Risk Checklist (score 0-7, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Playoff context** | 0-1.5 | Semifinal/final? Underdogs raise level in elimination matches. |
| 2 | **European travel** | 0-1 | Team played EHF/CEV midweek, now domestic? Rotation, fatigue. |
| 3 | **New setter** | 0-1.5 | Setter is the quarterback — new setter = entire attack disrupted. |
| 4 | **Home crowd** | 0-1 | Volleyball home advantage is significant (affects serve reception). |
| 5 | **Rest rotation** | 0-1 | Favorite resting key players for upcoming playoff round? |
| 6 | **5th set record** | 0-1 | Underdog has winning 5th set record (60%+)? Clutch factor. |

**Thresholds:**
- **≥3:** Avoid ML. Use set totals O/U, total points, set handicap.
- **≥5:** Strong upset candidate. Only point totals or set O/U markets.

---

#### 6.5.7 ESPORTS Upset Risk Checklist (score 0-10, threshold ≥2)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Roster change / stand-in** | 0-2 | Using a substitute player? This is the #1 esports upset factor. |
| 2 | **Map pool edge** | 0-1.5 | Underdog has 70%+ win rate on 2+ maps that favorite bans? Veto advantage. |
| 3 | **Online match** | 0-1 | Online has higher variance than LAN. "Online heroes" exist. |
| 4 | **New patch/meta** | 0-1.5 | Major game patch in last 2 weeks? Some teams adapt faster. Meta favoring underdogs. |
| 5 | **BO1 format** | 0-1.5 | Best-of-1 = map variance is HUGE. Single map upsets are common. |
| 6 | **LAN vs online gap** | 0-1 | Favorite dominates online but crumbles on LAN? Or vice versa? |
| 7 | **Coach ban/absence** | 0-0.5 | Coach banned from communicating during match? |
| 8 | **Regional style clash** | 0-0.5 | CIS aggressive vs EU tactical? Style clashes produce upsets. |

**Thresholds:**
- **≥2:** Avoid ML. Use map totals O/U, map handicap, round totals.
- **≥4:** Strong upset territory. Only map O/U or skip. BO1 + score ≥4 = DO NOT BET.

---

#### 6.5.8 SNOOKER Upset Risk Checklist (score 0-7, threshold ≥2)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Short format (BO7/BO9)** | 0-1.5 | Shorter formats have higher variance. BO7 is essentially a coin flip between top-32 players. |
| 2 | **Form discrepancy** | 0-1 | Favorite lost early in last 2 tournaments? Form slump? Underdog on a run? |
| 3 | **Safety-heavy underdog** | 0-1 | Defensive player who grinds out frames? Disrupts free-scoring favorites. |
| 4 | **World Championship R1 pressure** | 0-1 | Crucible Theatre R1 is unique — seeded players face extreme pressure from qualifiers. |
| 5 | **Multi-session structure** | 0-1 | BO19/BO25 allows comebacks. Sessions break momentum. |
| 6 | **Jet lag / travel** | 0-0.5 | Player arriving from Asian/Australian tour? |
| 7 | **Table conditions** | 0-0.5 | Morning vs evening session affects table speed and cloth behavior. |

**Thresholds:**
- **≥2:** Avoid ML. Use frame totals O/U, frame handicap, century O/U.
- **≥4:** Strong upset territory. Only frame O/U on conservative line.

---

#### 6.5.9 MMA/UFC Upset Risk Checklist (score 0-10, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Stylistic mismatch** | 0-2 | Wrestler vs striker without TDD? Grappler vs striker with TDD? Style determines outcome. |
| 2 | **Long layoff (>12mo)** | 0-1.5 | Ring rust is real. Fighters coming off long absence have higher upset rate. |
| 3 | **Weight class move** | 0-1 | Fighter moving UP in weight → may face bigger, stronger opponents. |
| 4 | **Short notice replacement** | 0-1 | Fighter taking fight on 2-3 weeks notice? Unprepared camp → chaos. |
| 5 | **Heavyweight division** | 0-1 | HW has highest KO variance. One punch changes everything. |
| 6 | **Bad weight cut** | 0-1 | Missed weight or looked drained at weigh-in? Affects chin and cardio. |
| 7 | **Southpaw vs Orthodox** | 0-0.5 | Stance mismatch creates openings. Unorthodox angles produce upsets. |
| 8 | **Altitude** | 0-0.5 | Event at elevation (Mexico City, Denver)? Affects cardio in later rounds. |
| 9 | **Camp/corner issues** | 0-0.5 | Major camp change? Trainer split? Affects preparation quality. |

**Thresholds:**
- **≥3:** Avoid ML. Use method of victory, O/U rounds, ITD.
- **≥5:** Strong upset territory. Only rounds O/U or skip.

---

#### 6.5.10 DARTS Upset Risk Checklist (score 0-7, threshold ≥2)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Floor event (not TV)** | 0-1.5 | Floor events (Players Championship) have MUCH higher upset rates. Top players avg 3-5% lower. |
| 2 | **Short format** | 0-1 | BO7 legs or BO3 sets = high variance. One bad visit can lose the match. |
| 3 | **Checkout slump** | 0-1 | Favorite's checkout% dropped below 35% in last 3 events? Missed doubles lose matches. |
| 4 | **Underdog 3-dart avg >95** | 0-1 | If underdog averages 95+, they can beat anyone on any given day. |
| 5 | **Multiple matches same day** | 0-1 | Playing 3+ matches in one day? Fatigue in later rounds. |
| 6 | **Home crowd (UK events)** | 0-0.5 | UK crowd can lift UK underdogs and unsettle overseas favorites. |

**Thresholds:**
- **≥2:** Avoid ML. Use total legs O/U, 180s O/U.
- **≥4:** Strong upset territory. Only 180s O/U or skip.

---

#### 6.5.11 HANDBALL Upset Risk Checklist (score 0-7, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **European midweek match** | 0-1.5 | EHF CL Wednesday → domestic Saturday? Rotation, travel fatigue. |
| 2 | **Home advantage** | 0-1.5 | Handball home wins 60-65%. If underdog is HOME → upset potential jumps. |
| 3 | **Goalkeeper form** | 0-1 | Underdog's #1 goalkeeper in form (save% >33%)? One hot keeper changes everything. |
| 4 | **Derby match** | 0-1 | Local rivalry = more physical, more suspensions, unpredictable. |
| 5 | **Key pivot/playmaker absence** | 0-1 | Favorite missing top scorer? Check EHF/league injury reports. |
| 6 | **7v6 play** | 0-0.5 | Teams using 7v6 aggressively = higher scoring but also turnovers = chaos. |

**Thresholds:**
- **≥3:** Avoid ML. Use half totals, game totals O/U, handicap.
- **≥5:** Only totals markets. Skip if not confident.

---

#### 6.5.12 TABLE TENNIS Upset Risk Checklist (score 0-6, threshold ≥2)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Ranking gap <20** | 0-1.5 | Close ranking = coin flip. TT rankings are less predictive than tennis. |
| 2 | **Multiple matches in one day** | 0-1 | Playing 3+ matches? Later matches have higher fatigue = higher variance. |
| 3 | **Style mismatch** | 0-1 | Defensive chopper vs aggressive attacker? Choppers frustrate and create upsets. |
| 4 | **Equipment change** | 0-0.5 | New rubber or blade = inconsistency period. Check ITTF equipment changes. |
| 5 | **Asian vs European style** | 0-0.5 | Different spin patterns, pacing. Unfamiliar style = more deuce sets. |
| 6 | **Tournament round** | 0-0.5 | R32 in TT has higher upset rate than QF+. Early rounds = less focused favorites. |

**Thresholds:**
- **≥2:** Avoid ML. Use total points O/U, set totals, set handicap.
- **≥3:** Only set totals or point totals. Skip if no stat source.

---

#### 6.5.13 PADEL Upset Risk Checklist (score 0-8, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **New partnership** | 0-2 | First 2-3 tournaments with new partner? Volatile results, poor chemistry. |
| 2 | **Ranking gap <1000 FIP pts** | 0-1.5 | Close ranking = real uncertainty. Both pairs competitive. |
| 3 | **Surface change** | 0-1 | Indoor fast court vs outdoor slow surface? Ball-wall interaction changes. |
| 4 | **R32/R16 stage** | 0-1 | Early rounds have higher upset rates in padel. QF+ favors top pairs. |
| 5 | **Altitude** | 0-0.5 | Padel at altitude = ball bounces differently off glass walls. |
| 6 | **Wind (outdoor)** | 0-1 | Strong wind disrupts lobs — the key padel shot. Favors aggressive smash pairs. |
| 7 | **Fatigue from previous round** | 0-0.5 | Favorite played 3 sets in QF yesterday? Older pairs (35+) recover slower. |

**Thresholds:**
- **≥3:** Avoid ML. Use game totals O/U, set totals O/U 2.5.
- **≥5:** Only game totals. Skip ML entirely.

---

#### 6.5.14 SPEEDWAY Upset Risk Checklist (score 0-8, threshold ≥3)

| # | Factor | Points | How to check |
|---|--------|--------|--------------|
| 1 | **Track preparation bias** | 0-2 | Home team ALWAYS prepares track for their riders. This is the #1 speedway factor. |
| 2 | **Rider injury / last-minute change** | 0-1.5 | Heat leader out? Check SportoweFakty 2h before. One rider = 6-10 pts lost. |
| 3 | **Weather / wet track** | 0-1 | Rain = wet track = more falls = chaos. Results become unpredictable. |
| 4 | **Junior rider weakness** | 0-1 | Team's U24 slots scoring 0-2 pts? That's 4-6 heats with minimal contribution. |
| 5 | **Away team "good traveler"** | 0-1 | Some teams have strong away records (e.g., Sparta Wrocław). Check last 3 away results. |
| 6 | **Equipment failure risk** | 0-0.5 | Rider known for bike problems? Engine failure = 3 pts lost per heat. |
| 7 | **Guest rider unfamiliarity** | 0-0.5 | Foreign guest rider who hasn't raced at this track before? Check venue-specific averages. |

**Thresholds:**
- **≥3:** Avoid match winner. Use total points O/U, handicap.
- **≥5:** Only handicap or total points with confirmed lineup.

---

#### 6.5.15 Upset Risk — Decision Matrix (APPLY TO EVERY PICK)

| Upset Score | ML Allowed? | Statistical Markets | Over Totals | Under/HC | Confidence Adjustment |
|-------------|-------------|---------------------|-------------|----------|-----------------------|
| 0-1 | Yes (if other criteria met) | Full range | Caution: blowout risk for overs | Preferred | No change |
| 2-3 | Caution (reduce confidence -1) | Preferred | Moderate | Good | -0.5 |
| 4-5 | **BANNED** | **ONLY option** | **PREMIUM** (Paradox Rule) | OK | -1 for ML |
| 6-7 | **BANNED** | Conservative lines only | Only STRONG ratio | Preferred | -1.5 |
| 8+ | **BANNED + consider SKIP** | Only if STRONG source | **AVOID** (too chaotic) | Skip | -2 |

**Record the upset score in the daily report for EVERY candidate.** Format: `UPSET: [score]/[max] — [top 3 factors]`

---

## STEP 7: BEAR CASE — Devil's Advocate (mandatory, never skip)

For EACH candidate pick that passed Steps 3-6, explicitly argue AGAINST it:

### 7.1 Template
```
PICK: [selection]
UPSET SCORE: [X/Y] — [top 3 risk factors from 6.5 checklist]
BULL CASE: [1-2 sentences why it should win]
BEAR CASE: [1-2 sentences why it could lose]
STREAK DEPENDENCY: [Is the thesis based on a continuing streak? Y/N. If Y, note regression risk]
REGRESSION RISK: [Is any team/player overperforming xG/expected stats? Y/N]
KEY FAILURE SCENARIO: [Most likely way this pick fails]
WOULD I BET AT 20% LOWER ODDS? [Y/N — if N, the edge is thin]
```

### 7.2 Decision Rules
- If the bear case is STRONGER than the bull case -> **REJECT**
- If the pick depends on a streak continuing (>5 games) -> **REDUCE CONFIDENCE by 1**
- If the key failure scenario has >40% probability -> **REJECT or move to WATCH LIST**
- If you would not bet at 20% lower odds -> the edge is thin. **COUPON LEG ONLY, not a single.**

---

## STEP 8: PORTFOLIO — Construct Final Tickets

### 8.1 Candidate Ranking
Rank all approved candidates by: EV (highest first), then confidence (highest first), then price_gap_pct (most favorable first).

### 8.2 Coupon-Only System (NO SINGLES)
All picks go into coupons. No singles are produced. Every coupon has at least 2 legs.

### 8.3 Coupon Construction — Minimum 5 Coupons
The target is MINIMUM 5 diverse coupons per day. If the board supports more, produce more. There is no upper limit on coupon count — 10, 15, or even 20 coupons are welcome if the analysis supports them. Search wider before accepting fewer than 5.

**Sport diversity in coupons**: At least 3 coupons must be MULTI-SPORT (legs from 2+ different sports). At least 1 coupon must include a non-football, non-tennis sport (e.g., hockey, volleyball, esports, darts, snooker, handball, table tennis, MMA, basketball, baseball). The final portfolio should showcase the FULL breadth of sports analyzed, not just football.

Coupon types to produce:
1. **Pewniaki system** (primary): identify 3-5 highest-confidence picks, build ALL non-repeating combinations:
   - All doubles (C(n,2) coupons)
   - All triples (C(n,3) coupons)
   - One quad if 4+ pewniaki
   This maximizes diversification: any 2 of 4 winning gives profit.
2. **Themed/higher-risk coupons**: combine medium-confidence picks across multiple sports.
3. **Long-shot coupons**: 4-6 legs with lower individual confidence but positive portfolio EV.
4. Each coupon must have a DIFFERENT composition. Diversity = different sport mixes, different leg counts, different risk levels.

### 8.4 Correlation Check
For EVERY pair of legs in a coupon:
- Same match? -> **FORBIDDEN** (remove one)
- Same league/day? -> **FLAG** (weather, referee, scheduling correlation). Accept only if different match contexts.
- Same narrative? (e.g., "Team A wins" and "Team B opponent of A loses") -> **REMOVE weaker leg**
- Same sport, same country? -> Keep but note shared risk.

### 8.5 Stake Suggestion (advisory, user decides)
- Suggest a stake for EVERY coupon based on risk level and Kelly guidance.
- Low-risk coupons (2-3 legs, each conf >=4): suggest 0.50-3.00 PLN
- Higher-risk coupons (3-4 legs, mixed conf): suggest 0.50-2.00 PLN
- Long-shot coupons (5+ legs): suggest 0.50-1.00 PLN
- **Total suggested exposure may EXCEED the daily budget.** This is intentional. The user decides which coupons to place. Do NOT reduce coupon count or stakes to fit the budget.
- Example: if you have 7 coupons totaling 12 PLN but the budget is 8 PLN — present all 7 with suggested stakes. The user chooses.

### 8.6 Watchlist
Always prepare 2-3 backup picks (Watch List). These are picks that:
- Barely missed the confidence threshold
- Have odds that might improve
- Could replace a coupon leg if Betclic odds are unacceptable

Specify promotion criteria: "Promote if Betclic odds >= X.XX for [selection]"

---

## STEP 9: VALIDATE — Full V1-V10 Protocol

Run EVERY validation check. If any fails, fix it before proceeding.

### V1: Artifact Consistency
1. Every `pick_id` in coupon file exists in `picks-ledger.csv` with matching event, market, selection.
2. Every `coupon_id` in coupon file exists in `coupons-ledger.csv` with matching pick_ids, stake, combined odds.
3. Sum of all stakes = `TOTAL PLANNED EXPOSURE PLN`.
4. `UNUSED FROM CAP PLN` = daily cap - total exposure.
5. No duplicate `pick_id` in picks ledger.
6. No event appears in 2+ tickets (unless explicitly justified with extra exposure note).
7. Report exposure numbers match coupon file numbers exactly.

### V2: Per-Pick Source Validation
For each pick:
1. Tier A stats source present with specific data point?
2. Tier A market/price source present with specific odds?
3. Bookmaker odds stated or marked CONDITIONAL with threshold?
4. Market-best odds stated?
5. Price gap within threshold?
6. EV calculated and positive?
7. Confidence score 1-5 with justification?

### V3: Tennis Over-Games Validation
For each tennis O-games pick:
1. Both match odds between 1.50-2.50?
2. Odds gap ratio <= 1.50?
3. Surface noted?
4. Match not cancelled?
5. Both players tour-level (ATP/WTA or strong Challenger)?

### V4: Football Validation
For each football pick:
1. Market hierarchy respected (corners/cards/fouls/shots > BTTS/U2.5 > O2.5)?
2. Corner picks: three-source stack verified?
3. BTTS: SoccerStats BTTS% > 55%?
4. U2.5: SoccerStats O2.5% < 55% + defensive profile?
5. Competition context noted?

### V4a: Tennis Validation
1. **Market hierarchy check**: Is the pick a statistical market (games O/U, sets O/U, handicap)? If ML → verify ALL of: STRONG ratio ≤1.15 + surface dominance + H2H dominance. If any missing → REJECT ML, use statistical market instead.
2. Game totals: odds ratio <=1.50?
3. Set totals: surface form checked?
4. No walkover risk (player injury)?

### V4b: Volleyball Validation
1. **ML check**: If ML pick → verify statistical markets (set totals, point totals, set HC) were unavailable or had no edge. ML only in 1.50-2.50 range.
2. Set totals: favorite ML between 1.30-2.00?
3. Point totals: O3.5 sets likely?
4. Competition context?

### V4c: Basketball Validation
1. **ML check**: If ML pick → verify totals/spreads/quarter markets were unavailable or had no edge.
2. Total points: pace + OFF/DEF ratings checked?
3. Injury report reviewed (star players)?
4. Playoff context (series dynamics, rest days)?

### V4d: Hockey Validation
1. **ML check**: If ML pick → verify totals/period totals/puck line were unavailable or had no edge.
2. Total goals: goalie confirmed + save % checked?
3. PP/PK percentages noted?
4. Back-to-back schedule checked?

### V4e: Esports Validation
1. **ML check**: If ML pick → verify map totals/round totals/map HC were unavailable or had no edge.
2. Map totals: form data from last 5 matches?
3. Match format (BO1/BO3/BO5) noted?
4. Map pool analysis done?

### V4f: Snooker Validation
1. **ML check**: If ML pick → verify frame totals/frame HC/century O/U were unavailable or had no edge.
2. Frame totals: match format (best-of-X) confirmed?
3. Frame averages per player checked?
4. Tournament stage context?

### V4g: Darts Validation
1. **ML check**: If ML pick → verify leg totals/180s/set totals were unavailable or had no edge.
2. Leg totals: average scoring checked (3-dart avg)?
3. Checkout percentage compared?
4. Event format noted?

### V4h: Other Sports (handball, table tennis, baseball, MMA)
1. **ML check**: If ML pick → verify sport-specific statistical markets were unavailable or had no edge. ML is LAST RESORT in ALL sports.
2. Appropriate statistical market selected (not defaulting to ML)?
3. Sport-specific data sources consulted?
4. Context verified (home/away, form, injuries)?

### V4i: Padel Validation
1. FIP ranking for both pairs checked?
2. Ranking gap correctly reflected in pick confidence?
3. Tournament tier (Major/P1/P2/Bronze) noted?
4. Indoor/outdoor + weather checked?
5. Partner change history verified (new partnership = extra caution)?

### V4j: Speedway Validation
1. Lineup confirmed from SpeedwayEkstraliga.pl or SportoweFakty?
2. Home/away rider track-specific averages checked?
3. Home advantage factor accounted for in handicap analysis?
4. Junior rider slots (#6, #7) assessed?
5. Weather/track condition verified (rain delay risk)?

### V4k: Upset Risk Assessment Validation (MANDATORY — NEVER SKIP)
1. **Upset score calculated for EVERY candidate?** Every pick must have a score from the sport-specific checklist (§6.5). No exceptions.
2. **Score recorded in report?** Format: `UPSET: [score]/[max] — [top 3 factors]`. Missing score = pick NOT validated.
3. **ML ban enforced?** If upset score ≥ threshold (tennis ≥4, football ≥4, basketball ≥3, hockey ≥3, baseball ≥3, volleyball ≥3, esports ≥2, snooker ≥2, darts ≥2, MMA ≥3, handball ≥3, table tennis ≥2, padel ≥3, speedway ≥3) → ML pick is FORBIDDEN. If ML exists with score above threshold → REJECT immediately.
4. **Paradox Rule applied?** If upset score is HIGH (≥4) → over-totals should be PREFERRED (more competitive match = more play). If upset score is LOW (0-1) → verify overs aren't blowout-risk.
5. **Bear case references upset score?** STEP 7 bear case template must include the upset score and top risk factors.
6. **Confidence adjusted?** Upset score ≥4 → ML confidence reduced by -1. Upset score ≥6 → all market confidence reduced by -0.5. Upset score ≥8 → consider skipping.
7. **Line/ratio matrix respected for tennis?** O22.5+ requires STRONG ratio (≤1.15). O21.5 requires GOOD (≤1.25). Combined with upset score for double-validation.

### V5: Coupon Structure
1. Minimum 2 legs per coupon?
2. Same-sport legs <= max (2 per sport per coupon)?
3. HR coupon has min sports?
4. No same-match correlation?
5. **Combined odds ARITHMETIC (MANDATORY — never skip):** For EVERY coupon, explicitly multiply each leg's odds and write the product. Compare to the stated combined odds. Tolerance: ±2%. If any coupon differs by >2%, FIX IT before proceeding. Do NOT claim "products match" without showing the multiplication.
6. Stake within coupon limit?
7. At least 5 coupons produced?

### V6: Portfolio Risk
1. No coupon stake > 3.00 PLN (LR) or 2.00 PLN (HR)?
2. Exposure < 25% of bankroll?
3. Multi-sport diversification?
4. No tournament concentration (>4 picks same tournament)?

### V7: Weakness Flagging
1. List tennis picks with odds ratio > 1.30
2. List football picks without three-source stack
3. List CONDITIONAL picks with thresholds
4. Identify weakest coupon leg for each coupon
5. Note same-tournament risks

### V7b: Date & Fixture Verification (MANDATORY)
Before finalizing ANY coupon, verify EVERY event in every coupon:
1. **Date check**: Confirm the event falls within the betting-day window (06:00 today to 05:59 tomorrow). Cross-check the date on Betclic/BetExplorer — do NOT trust source data or tipster sites for dates.
2. **Fixture existence**: Confirm the match is listed on Betclic or BetExplorer for today. If the event is not found on the bookmaker site for today, it does NOT exist today — void the pick immediately.
3. **Opponent name**: Confirm the exact team/player names match what Betclic shows. Cross-reference with picks-ledger.
4. **Competition name**: Confirm the league/tournament name is correct.
Failure on ANY of these → VOID the pick and remove from all coupons. Replace with a valid alternative or drop the coupon.

### V7c: Cross-Coupon Integrity Check (MANDATORY)
1. **No duplicate legs across coupons** (except pewniaki system where overlap is by design): outside of pewniaki, no pick should appear in more than 2 coupons.
2. **No identical coupons**: every coupon must differ by at least 1 leg.
3. **No correlated narrative across coupons**: if coupon A has "Leeds win" and coupon B has "Leeds O2.5", both depend on Leeds scoring — flag and replace one.
4. **Cross-match correlation**: if two legs in different coupons are from the same match, verify they are NOT on the same side of the market (e.g., O2.5 goals + BTTS Yes is correlated). Different-side legs (e.g., Team A corners + O2.5 goals) are acceptable but must be noted.
5. **Pick spread check**: count how many coupons each pick appears in. Outside pewniaki, no pick should appear in more than 2 coupons. Verify coupon diversity — each coupon should cover a different combination of events.

### V8: Source Completeness Audit
For EVERY active pick, verify:
1. At least 1 Tier A stats source with a SPECIFIC data point cited (not just "checked SoccerStats").
2. At least 1 Tier A market/price source with SPECIFIC odds cited.
3. At least 2 INDEPENDENT sources total (same site counted once).
4. At least 1 ARGUMENT-BASED tipster source checked per candidate — not bare picks, but a site where tipsters post written reasoning (ZawodTyper, Typersi, Meczyki, OLBG, PicksWise, BetIdeas, Sportsgambler, GosuGamers).

Sport-specific source requirements (fail = downgrade confidence -1 or flag):
- **Football corners**: TotalCorner + SoccerStats + Betclic Statystyki (3-source stack). Missing any → flag pick.
- **Tennis**: TennisAbstract Elo + surface form. Missing → flag pick.
- **MLB**: BaseballSavant (Statcast) or Baseball Reference pitcher ERA/WHIP. Missing → flag pick. Note: FanGraphs is BLOCKED.
- **Esports**: Liquipedia or GosuGamers roster/form data. Missing → flag pick.
- **Snooker**: CueTracker frame stats. Missing → flag pick.

For EVERY sport with active picks, verify:
1. At least 2 tipster/analysis sites were checked for events in that sport.
2. If football picks present → Meczyki + ZawodTyper + (Typersi or OLBG) checked.
3. If tennis picks present → OLBG or PicksWise checked + TennisAbstract.
4. If US sport picks present → PicksWise + SBR/ESPN checked.

Conflict resolution:
1. If any tipster argues AGAINST a pick with specific fact-based reasoning → the bear case (V7) MUST address that argument.
2. If tipster consensus is <50% for the pick direction → pick needs explicit justification or removal.
3. Record ALL conflicts found and their resolution in the daily report.

### V9: Coupon Composition Optimization
Verify coupons are optimally composed — not just valid, but the BEST possible combinations:

1. **Pick ranking**: Re-rank all active picks by `EV × confidence`. Are the highest-ranked picks in the most coupons (especially pewniaki)?
2. **Pewniaki integrity**: Are the top 3-5 picks genuinely the highest-confidence, highest-EV picks? No lower-ranked pick displaced a higher one?
3. **Sport diversity per coupon**: Every multi-sport coupon has legs from ≥2 sports? At least 3 coupons are multi-sport?
4. **Same-match check**: No two legs in the same coupon from the same match.
5. **Market concentration**: No coupon has ≥3 legs of the same market type (e.g., 3 corner picks, 3 ML picks). Max 2 same-type per coupon.
6. **Orphan pick check**: Every active pick appears in at least 1 coupon. Under NO SINGLES rule, picks without a coupon must be added to one or moved to watchlist.
7. **Timing coherence**: Night coupons contain only night games (≥00:00 CEST). Morning/afternoon plays are not mixed into night coupons.
8. **Weakest-leg swap test**: For each coupon, identify the weakest leg (lowest confidence or highest bear-case risk). Is there a BETTER pick in the pool that could replace it without creating correlation? If yes → swap.
9. **Combined odds sweet spot**: Pewniaki 2.00-8.00, multi-sport 3.00-10.00, higher-risk 8.00-20.00. Coupons outside these ranges should be reviewed.

### V10: Final Sign-Off
All V1-V9 pass? -> PORTFOLIO APPROVED.
Any fail? -> Fix and re-check. Do not present until all pass.

---

## STEP 10: ARTIFACTS — Write and Commit

### 10.1 Write Order
1. Daily report: `betting/reports/YYYY-MM-DD.md`
2. Coupon file: `betting/coupons/YYYY-MM-DD.md`
3. Portfolio (readable): `betting/coupons/YYYY-MM-DD-portfolio.md`
4. Picks ledger: `betting/journal/picks-ledger.csv`
5. Coupons ledger: `betting/journal/coupons-ledger.csv`
6. Source log: `betting/journal/source-log.csv`
7. Learning log: `betting/journal/learning-log.md`

### 10.2 Record for CLV
For each pick, record in a note or in the picks ledger:
- `odds_at_placement`: the odds when the user places the bet
- `odds_checked_at`: timestamp of last odds check

### 10.3 Present to User
Summarize in conversation:
- Number of coupons
- Total exposure
- Key conditional picks needing Betclic verification
- Watchlist picks available as replacements

---

## BATTLE-TESTED PRINCIPLES (always keep in mind)

### The 7 Laws of Sharp Betting
1. **Value > Prediction**: Do not predict winners. Find mispriced odds. A 40% probability event at 3.00 (implied 33%) is a value bet.
2. **CLV is King**: If you consistently beat the closing line, you are profitable long-term. Track it religiously.
3. **Correlation Kills Parlays**: Every shared factor between coupon legs destroys expected value. Same-game parlays are the bookmaker's best friend.
4. **Regression is Real**: Hot streaks end. xG tells the truth, goals lie. Teams overperforming xG by >0.5 per game will regress.
5. **Home Advantage is Overpriced**: Public overvalues home favorites. Away wins and draws are systematically underpriced in most leagues.
6. **Specialize AND Diversify**: Deep knowledge in 3-5 leagues + broad scanning across sports. Deep for edge, broad for opportunity.
7. **Never Force Action**: The best bet is sometimes no bet. A weak board is a sign to wait, not a signal to lower standards.

### The Bankroll Commandments
1. Never risk more than 5% of bankroll on a single bet (2.30 PLN on 46 PLN bankroll).
2. Never exceed 25% of bankroll in daily exposure (11.50 PLN on 46 PLN bankroll).
3. If bankroll drops 20% from peak -> reduce daily cap by 25%.
4. If bankroll grows 30% from start -> consider modest increase (10-15%).
5. Track ROI per market type and per league. Cut losing markets/leagues.
6. It is ALWAYS acceptable to have a NO BET day.

### The Cognitive Discipline Rules
1. **Confirmation bias check**: After finding evidence FOR a pick, spend equal time looking for evidence AGAINST.
2. **Recency bias check**: Do not overweight last game. Use 5-10 game samples minimum.
3. **Sunk cost check**: If a pick was good yesterday but data changed, drop it. Do not hold picks out of attachment.
4. **Gambler's fallacy check**: "This team is due for a win" is not a valid reason. Probability does not have memory.
5. **Anchor effect check**: Do not let the first odds you see anchor your probability estimate. Calculate independently.

### Market Hierarchy (why statistical markets > results markets)
The agent MUST independently identify which statistical markets offer the most value per sport. Do NOT wait for user direction — YOU are the analyst.

**Football**: corners > cards > fouls > shots on target > team totals > BTTS > U2.5 > O2.5 > DC/DNB > 1X2
**Tennis**: total games O/U > set totals O/U > game handicap > set handicap > ML (LAST RESORT — only when STRONG ratio + surface + H2H all align)
**Basketball**: total points O/U > spreads > quarter totals > team totals > ML
**Hockey**: total goals O/U > period totals > shots on goal > ML (with goalie confirmation)
**Volleyball**: total sets O/U > total points O/U > set handicap > individual set points > ML
**Esports**: map totals O/U > map handicap > round totals > ML
**Snooker**: total frames O/U > frame handicap > century breaks O/U > ML
**Darts**: total legs O/U > 180s O/U > set totals > ML
**Handball**: total goals O/U > handicap > half totals > ML
**Table tennis**: total points > set handicap > ML
**MMA**: method of victory > rounds O/U > ML
**Baseball**: total runs O/U > run line > F5 O/U > ML (with pitcher analysis)

The less popular the market, the more likely it is mispriced. This is our edge.
**Key principle**: statistical/totals markets are ALWAYS preferred over ML/winner markets. ML is a LAST RESORT, not a default.

---

## QUICK REFERENCE: Daily Workflow Checklist

```
STEP 0: Settle previous day
  [ ] Run settle script
  [ ] Calculate PnL + rolling 7-day PnL
  [ ] Update market-type hit rates
  [ ] Post-mortem losses
  [ ] Record CLV for settled picks
  [ ] Update bankroll in config

STEP 1: Scan all events
  [ ] Run orchestrator
  [ ] Check scan_errors.json
  [ ] Browse BetExplorer all sports
  [ ] Cross-ref Flashscore
  [ ] Build Master Event List
  [ ] Verify all 14 sports checked

STEP 2: Filter to shortlist
  [ ] Remove outside betting window
  [ ] Remove no Tier A coverage
  [ ] Remove too close to kickoff
  [ ] Assess statistical market availability
  [ ] Target 15-40 shortlisted events

STEP 3: Deep stats per candidate
  [ ] Football: league context + match data + corner stack + defensive profile + xG
  [ ] Tennis: ranking + surface form + H2H + Elo + odds ratio + games per set avg
  [ ] Basketball: pace + OFF/DEF ratings + injuries + home/away splits + quarter trends
  [ ] Hockey: xG + goalie save% + PP/PK + B2B fatigue + period totals history
  [ ] Volleyball: set win% + total points avg + tiebreak frequency + set handicap value
  [ ] Esports: map pool + win rates per map + round averages + form (last 5)
  [ ] Snooker: frame averages + century break rates + safety tendencies + format (best-of-X)
  [ ] Darts: 3-dart avg + checkout% + 180s avg + leg totals history
  [ ] Handball: total goals avg + home/away splits + half totals
  [ ] Table tennis: point totals + set handicap + ranking gap
  [ ] MMA: method of victory stats + rounds avg + style matchup
  [ ] Baseball: starting pitcher ERA/WHIP + bullpen + run totals + F5 line

STEP 4: Tipster deep-dive
  [ ] Check >=2 tipster sources per candidate
  [ ] Extract specific picks + reasoning
  [ ] Calculate consensus %
  [ ] Flag contradictions -> investigate
  [ ] Record discovered angles

STEP 5: Odds + EV analysis
  [ ] Get market-best from BetExplorer
  [ ] Estimate true probability
  [ ] Calculate EV (must be > 0)
  [ ] Calculate price_gap_pct
  [ ] Check line movement
  [ ] Apply Kelly for staking guidance

STEP 6: Context verification
  [ ] Fixture still confirmed
  [ ] Key absences checked
  [ ] Competition context (motivation)
  [ ] Fixture congestion
  [ ] Weather (if relevant)
  [ ] Referee (if cards/fouls market)

STEP 6.5: Upset Risk Assessment (MANDATORY)
  [ ] Score every candidate on sport-specific checklist (§6.5)
  [ ] Record score in report: UPSET: [X/Y] — [top 3 factors]
  [ ] If score ≥ threshold → BAN ML, use statistical markets only
  [ ] Apply Paradox Rule: high upset → prefer OVER totals, low upset → caution on overs
  [ ] Adjust confidence per decision matrix (§6.5.15)

STEP 7: Bear case for each pick
  [ ] UPSET SCORE included in bear case template
  [ ] Bull vs bear case documented
  [ ] Streak dependency checked
  [ ] Regression risk assessed
  [ ] Key failure scenario stated
  [ ] "20% lower odds" test

STEP 8: Portfolio construction
  [ ] Rank by EV -> confidence -> price gap
  [ ] Build coupon combos (pewniaki system + themed coupons)
  [ ] Minimum 5 coupons, minimum 2 legs each
  [ ] Correlation check all pairs
  [ ] Suggest stakes for all coupons (may exceed daily cap)
  [ ] Build watchlist with promotion criteria

STEP 9: Validate V1-V10
  [ ] V1: artifacts consistent
  [ ] V2: per-pick sources valid
  [ ] V3: tennis checks pass
  [ ] V4: football checks pass
  [ ] V5: coupon structure valid
  [ ] V6: portfolio risk OK
  [ ] V7: weaknesses documented
  [ ] V8: source completeness audit pass (all picks have ≥2 sources, sport-specific sources checked, tipster conflicts resolved)
  [ ] V9: coupon optimization pass (pick ranking, orphan check, market concentration, weakest-leg swap, timing coherence)
  [ ] V10: all pass -> APPROVED

STEP 10: Write artifacts
  [ ] Report, coupon file, portfolio
  [ ] Picks ledger, coupons ledger
  [ ] Source log, learning log
  [ ] Record odds_checked_at timestamps
  [ ] Present summary to user
```

---

## APPENDIX A: Sport-Specific Market Selection Priority

### Football
1. Corners (O/U match total, team corners, 1H corners)
2. Cards (yellow card totals, team cards)
3. Fouls (match fouls, team fouls)
4. Shots (shots on target, total shots)
5. Team totals (Team O1.5/O2.5 goals)
6. BTTS
7. Under 2.5 / Over 2.5 goals (fallback)
8. Double Chance / Draw No Bet
9. 1X2 (only with strong edge)

### Tennis
1. Match moneyline (when odds 1.50-2.50 range)
2. Over/Under total games
3. Set handicap
4. Set totals (O/U 2.5 sets)

### Basketball
1. Totals (match points O/U)
2. Spreads
3. Quarter/half totals
4. Moneyline (only with strong edge)

### Hockey
1. Totals (match goals O/U)
2. Moneyline (only with goalie + form context)
3. Period totals

### Volleyball
1. Set totals (O/U 3.5 sets)
2. Point totals
3. Set handicap
4. Moneyline

### Esports (CS2, Dota 2, LoL, Valorant)
1. Map handicap
2. Map totals (O/U 2.5 maps)
3. Moneyline
4. Round handicap (for individual maps)

### Snooker
1. Frame handicap
2. Total frames
3. Moneyline

### Darts
1. Leg/set totals
2. 180s O/U
3. Moneyline

### Handball
1. Totals (match goals)
2. Handicap
3. Moneyline

### Table Tennis
1. Set handicap
2. Total points
3. Moneyline

### MMA/UFC
1. Moneyline
2. Method of victory
3. Round totals O/U

### Baseball (MLB)
1. Totals (runs O/U)
2. Run line (spread)
3. Moneyline (only with pitching + form)

---

## APPENDIX B: Source Quick-Reference by Sport

| Sport | Tier A Stats | Tier A Market | Tier B Tipster | Tier C Specialist |
|-------|-------------|---------------|----------------|-------------------|
| Football | SoccerStats, Flashscore, Betaminic | BetExplorer, OddsPortal | BetIdeas, ZawodTyper, Meczyki, OLBG | TotalCorner, Betclic Statystyki |
| Tennis | TennisAbstract, Flashscore | BetExplorer, OddsPortal | PicksWise, OLBG | TennisExplorer |
| Basketball | TeamRankings, Covers | BetExplorer, SBR, ESPN Odds | PicksWise, Covers | Basketball-Reference |
| Hockey | Flashscore, Sofascore | BetExplorer, SBR, ESPN Odds | PicksWise, Covers | NaturalStatTrick, MoneyPuck |
| Volleyball | Flashscore | BetExplorer | OLBG | — |
| CS2 | GosuGamers | BetExplorer | GosuGamers | BO3.gg |
| Snooker | CueTracker | BetExplorer | — | SnookerOrg |
| Darts | PDC stats | BetExplorer | — | DartsOrakel |
| Handball | EHF stats | BetExplorer | — | Handball-World |
| MMA | UFCstats | BetExplorer | PicksWise, Tapology | — |
| Baseball | BaseballSavant | BetExplorer, Covers | PicksWise | — |
| Table Tennis | ITTF | BetExplorer | — | tt-series.com |

---

## APPENDIX C: Understanding Why This Works

### The Mathematical Edge
Bookmakers set odds to balance their book. They do NOT set odds at true probability. The gap between true probability and bookmaker-implied probability IS the edge. When we systematically identify mispriced odds using multiple data sources and only bet when EV > 0, mathematics guarantees long-term profit given sufficient volume.

### The Market Inefficiency Map
Not all markets are equally efficient:
- **Most efficient** (hardest to beat): 1X2 in top leagues, NBA ML, NFL sides -> avoid
- **Moderately efficient**: Goals O/U 2.5, BTTS, NBA totals -> occasional value
- **Least efficient** (easiest to beat): corners, cards, fouls, volleyball sets, esports maps, tennis games -> PRIMARY FOCUS

### The Compound Growth Formula
Starting bankroll: 46 PLN. Target: 1,000,000 PLN.
Required multiplication: ~21,739x.
At 5% weekly growth rate (very aggressive but achievable with consistent +EV):
- After 1 year (52 weeks): 46 x 1.05^52 = 46 x 12.64 = 581 PLN
- After 2 years: 7,347 PLN
- After 3 years: 92,900 PLN
- After 4 years: 1,174,503 PLN -> **target reached**

At 3% weekly (more realistic): ~6 years. At 10% weekly (unrealistic long-term): ~2 years.

The key: CONSISTENCY over months and years. Not one big win, but hundreds of small +EV bets compounding.

### Why the Pewniaki Coupon System Works
- Pewniaki coupon system (all combinations of top picks) provides exponential upside when 3/4 or 4/4 hit
- Risk distribution: diverse coupons across sports ensure not all eggs in one basket
- Any 2 of 4 pewniaki winning always produces positive day (with proper staking)
- User picks which coupons to place based on risk appetite and available budget
