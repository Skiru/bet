---
applyTo: "betting/**/*"
---

# Analysis Methodology — Complete Daily Protocol

This is the DEFINITIVE, REPEATABLE methodology for daily betting analysis. Follow every step in order. Do not skip steps. Do not take shortcuts. This protocol produces professional-grade analysis every single day.

The goal: find MISPRICED ODDS, not predict winners. A 40% chance event at 3.00 odds (implied 33%) is a value bet even though it loses most of the time. Value betting is the only sustainable edge.

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

### 1.2 Master Event List
Build a COMPLETE list of every event happening in the betting-day window (06:00 today through 05:59 tomorrow, Europe/Warsaw). Use:
- **BetExplorer**: browse sport-by-sport (football, tennis, basketball, hockey, baseball, volleyball, esports, snooker, darts, table_tennis, handball, mma). Click "Tomorrow" or today's date tab.
- **Flashscore**: cross-reference for fixture times and any events BetExplorer misses. Check ALL 12 sports.
- **OddsPortal**: check for additional sports/events.

For each event, record:
- Sport, competition, event name, kickoff time (local)
- Available markets on Betclic (if known)
- Initial odds range (favorite/underdog)

### 1.3 Sport Coverage Checklist — MANDATORY (ALL 12 SPORTS)

**CRITICAL ENFORCEMENT RULE**: You MUST scan ALL 12 sports below. This is not optional. Every sport must be checked for events in the betting-day window. For each sport, record either: (a) candidate events found, or (b) "NO EVENTS TODAY" with the source you checked. Skipping a sport is a PROTOCOL VIOLATION.

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

**After scanning**: Count how many sports have events. Record the count. If fewer than 6 sports have events today, note this explicitly — it's unusual and should be verified.

**Source discovery for niche sports**: If BetExplorer/Flashscore don't cover a sport well:
- Esports: GosuGamers, Liquipedia, HLTV (stats only, NOT tips)
- Snooker: CueTracker, WorldSnooker.com
- Darts: DartsOrakel, PDC.tv
- Table Tennis: tt-liveresults.com
- Handball: eurohandball.com
- MMA: Sherdog, Tapology, UFC.com

**NEVER say "no sources available" for a sport without searching specialist sites first. The internet ALWAYS has data for every sport.**

### 1.4 Source Resilience Protocol
When ANY source returns 403, Cloudflare block, GDPR wall, or empty response:
1. Do NOT give up. Move to the next source in the Odds Source Map (source-registry.md).
2. If all mapped sources fail, search the internet for alternative sources. The internet ALWAYS has data.
3. Record every source failure in `source-log.csv`.
4. For every pick, you MUST have odds or data from at least 2 independent sources for cross-validation.
5. For US sports: SBR + ESPN Odds + ScoresAndOdds = three independent sources. Use all three.
6. For EU sports: BetExplorer + OddsPortal = two primary sources. Add The-Odds-API as fallback.
7. Different sources may show DIFFERENT lines for the same game (e.g., SBR: O6.0, ESPN: O6.5). This validates the multi-source approach — always note discrepancies.

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

### 2.3 Result: Shortlisted Events
Target: 15-40 events across multiple sports. If fewer than 15, widen the search. If more than 40, tighten criteria (remove events with weakest source coverage).

**Sport diversity requirement**: The shortlist MUST include events from at least 5 different sports. If fewer than 5 sports are represented, go back to Step 1 and scan the missing sports more aggressively. Football should NOT dominate the shortlist — aim for no more than 50% football events.

---

## STEP 3: STATS — Deep Statistical Analysis

For EACH shortlisted event, gather sport-specific statistical data. This is the CORE of the analysis — do NOT rush it.

### 3.1 Football Statistical Protocol
For every football candidate:

**A. League-Level Context (SoccerStats)**
- League average goals per match
- League O2.5%, BTTS%, corner averages
- League home/away splits
- Team rankings within league: goals for/against, corners for/against, cards

**B. Match-Level Data (BetExplorer + Flashscore)**
- BetExplorer match odds history and implied probability
- H2H history (last 5-10 meetings): goals, corners, cards patterns
- Recent form: last 5-6 matches for each team

**C. Corner Analysis (THREE-SOURCE STACK — mandatory for corner picks)**
1. **TotalCorner**: match-level corner total predictions, handicaps
2. **SoccerStats**: league corner rankings (team corner averages home/away)
3. **Betclic Statystyki** (top leagues only: EPL, LaLiga, Bundesliga): verified corner odds from HTML snapshots

If any of the three sources is missing, mark corner pick as LOWER CONFIDENCE.

**D. Defensive Profile Analysis (for U2.5/BTTS picks)**
- Team GF+GA per match: if <2.0 -> U2.5 candidate
- League O2.5%: if <50% -> U2.5 favorable league context
- Clean sheet percentages for both teams
- Competition context: cup semi/final -> typically tactical (U2.5 lean)

**E. xG Analysis (where available)**
- If Flashscore/Sofascore provide xG data, compare xG to actual goals
- xG > Goals -> team underperforming, likely to improve (regression UP)
- Goals > xG -> team overperforming, regression DOWN coming
- Use xG as truth, not recent results

### 3.2 Tennis Statistical Protocol
For every tennis candidate:

**A. Player Comparison**
- Current ranking and recent ranking trajectory
- Surface-specific win rate (clay/hard/grass)
- H2H record on current surface
- Recent form: last 5-10 matches, noting retirements and walkovers

**B. Match Dynamics (TennisAbstract)**
- Elo rating and surface Elo
- Serve hold % and return break %
- Average games per set
- Tiebreak frequency

**C. Over-Games Assessment**
- Match odds ratio: `max(odds) / min(odds)`. Must be <=1.50 for O-games picks.
  - <=1.15: STRONG (55-65% 3-set probability)
  - 1.16-1.30: GOOD (48-55%)
  - 1.31-1.50: BORDERLINE (42-48%) — coupon legs only
  - >1.50: REJECT
- Standard line O20.5 in best-of-3. A 3-set match with 6-4/4-6/6-4 = 24 games (covers). A 2-set 6-3/6-4 = 19 (does not cover).
- Surface effect: clay breaks are easier -> more break opportunities -> longer matches

### 3.3 Basketball Statistical Protocol
- Pace (possessions per game) for both teams
- Offensive/defensive rating
- Recent total points in last 5-10 games
- Injury report for key players
- Home/away splits for totals
- Playoff context: series dynamics, game number

### 3.4 Hockey Statistical Protocol
- Expected goals (xGF, xGA) from NaturalStatTrick/MoneyPuck
- Save percentage and goalie form
- Power play / penalty kill %
- Recent total goals in last 5-10 games
- Back-to-back schedule fatigue

### 3.5 Volleyball Statistical Protocol
For every volleyball candidate:

**A. Set Dynamics**
- Team set win percentages home/away
- Average sets per match (O/U 3.5 = frequent 3-2 finishes?)
- Tiebreak frequency (5th set frequency indicates competitive matchups)

**B. Point Totals**
- Average total points per match (typical range 150-190)
- Team scoring averages per set
- Home/away splits for points
- O/U lines from BetExplorer volleyball section

**C. Statistical Markets (priority order)**
1. Total sets O/U 3.5 — most valuable when teams are evenly matched (ML odds 1.50-2.50)
2. Total points O/U — less efficient market, good for mismatch exploitation
3. Set handicap -1.5 — when favorite is strong but ML is too short
4. Individual set score O/U 44.5 pts — very niche, very inefficient

**Sources**: Flashscore volleyball, BetExplorer volleyball, OddsPortal volleyball

### 3.6 Esports Statistical Protocol (CS2/LoL/Dota2/Valorant)
For every esports candidate:

**A. Map Analysis (CS2/Valorant)**
- Map pool overlap between teams
- Win rates per map for each team
- Average rounds per map (O/U 26.5 standard)
- Pistol round win rates (early-round advantage indicator)

**B. Match Format**
- BO1 vs BO3 vs BO5 — upsets more likely in BO1
- Map veto tendencies
- Home/away advantage (LAN vs online)

**C. Statistical Markets (priority order)**
1. Map totals O/U 2.5 (BO3) — main market. Evenly matched teams → O2.5 maps
2. Map handicap -1.5 — when favorite should dominate but ML too short
3. Total rounds O/U per map — niche, very inefficient
4. ML — only when odds ratio supports it AND form data is strong

**D. LoL/Dota2 Specific**
- Game duration averages (fast meta vs late-game scaling)
- Tower/dragon/baron objective stats
- Kill totals O/U

**Sources**: GosuGamers, HLTV stats (NOT tips), Liquipedia, BetExplorer esports

### 3.7 Snooker Statistical Protocol
For every snooker candidate:

**A. Frame Analysis**
- Tournament format (best-of-9, best-of-13, best-of-19, best-of-25, best-of-35)
- Average frames per match at this tournament stage
- Player break-building stats (century breaks per match)
- Safety play tendencies (safety-heavy players → more frames)

**B. Statistical Markets (priority order)**
1. Total frames O/U — most valuable. Close skill levels → more frames
2. Frame handicap — when favorite clear but ML too short
3. Century breaks O/U — very niche where available
4. ML — only with strong form + ranking disparity

**C. Key indicators for O frames**
- Both players ranked within 15 of each other → likely to go deep
- Player who plays long frames (avg frame time >20 min) → more frames
- World Championship sessions: early rounds best-of-19, later best-of-25/33

**Sources**: CueTracker (frame-level stats), Flashscore snooker, BetExplorer snooker, OddsPortal snooker

### 3.8 Darts Statistical Protocol
For every darts candidate:

**A. Leg/Set Analysis**
- Average 3-dart score (critical: >95 = elite, 90-95 = good, <90 = inconsistent)
- Checkout percentage (doubles hit rate)
- 180s per match average

**B. Statistical Markets (priority order)**
1. Total legs O/U — main market. Close matches → more legs
2. 180s O/U — correlates with scoring power, very niche market
3. Set totals O/U — in set-format events (World Championship)
4. ML — only when scoring averages diverge significantly

**Sources**: DartsOrakel, Flashscore darts, BetExplorer darts

### 3.9 Handball Statistical Protocol
For every handball candidate:

**A. Scoring Analysis**
- Average total goals per match (typically 48-60)
- Team scoring averages (offense + defense)
- Home/away scoring splits (home advantage is huge in handball)

**B. Statistical Markets (priority order)**
1. Total goals O/U — most valuable. High-scoring sport with predictable totals
2. Handicap — when team quality differs significantly
3. Half totals — first half O/U, more stable than full match
4. ML — predictable sport, underdogs rarely win

**Sources**: Flashscore handball, BetExplorer handball

### 3.10 Table Tennis Statistical Protocol
- Set handicap based on ranking difference
- Total points O/U based on player style (aggressive vs defensive)
- ML only with significant ranking gap
- **Sources**: Flashscore table tennis, BetExplorer table tennis

### 3.11 MMA/UFC Statistical Protocol
- Method of victory: KO/TKO, submission, decision — each has different value
- O/U rounds (1.5 for 3-rounders, 2.5 for 5-rounders)
- Fighter style matchup analysis (striker vs grappler)
- **Sources**: UFC stats, Sherdog, Tapology, BetExplorer MMA

### 3.12 Baseball (MLB) Statistical Protocol
- Starting pitcher ERA, WHIP, K/9
- Bullpen ERA and recent usage
- Total runs O/U (primary market)
- Run line (handicap +-1.5)
- First 5 innings line (removes bullpen variance)
- **Sources**: Baseball Reference, FanGraphs, ESPN, SBR, BetExplorer baseball

### 3.13 General Principle for ALL Sports
Follow sport-specific source references in source-registry.md. The universal approach:
- Get statistical data from specialist sources (sport-specific)
- Get form data from general sources (Flashscore, Sofascore)
- Get odds data from market sources (BetExplorer, OddsPortal)
- **ALWAYS prefer statistical/totals markets over ML/winner markets**
- The less liquid the market, the more likely it is mispriced — this is our edge

### 3.14 Sport-Specific Source URLs (Quick Reference)
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

---

## STEP 7: BEAR CASE — Devil's Advocate (mandatory, never skip)

For EACH candidate pick that passed Steps 3-6, explicitly argue AGAINST it:

### 7.1 Template
```
PICK: [selection]
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

## STEP 9: VALIDATE — Full V1-V8 Protocol

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
1. Game totals: odds ratio <=1.50?
2. Set totals: surface form checked?
3. No walkover risk (player injury)?

### V4b: Volleyball Validation
1. Set totals: favorite ML between 1.30-2.00?
2. Point totals: O3.5 sets likely?
3. Competition context?

### V4c: Basketball Validation
1. Total points: pace + OFF/DEF ratings checked?
2. Injury report reviewed (star players)?
3. Playoff context (series dynamics, rest days)?

### V4d: Hockey Validation
1. Total goals: goalie confirmed + save % checked?
2. PP/PK percentages noted?
3. Back-to-back schedule checked?

### V4e: Esports Validation
1. Map totals: form data from last 5 matches?
2. Match format (BO1/BO3/BO5) noted?
3. Map pool analysis done?

### V4f: Snooker Validation
1. Frame totals: match format (best-of-X) confirmed?
2. Frame averages per player checked?
3. Tournament stage context?

### V4g: Darts Validation
1. Leg totals: average scoring checked (3-dart avg)?
2. Checkout percentage compared?
3. Event format noted?

### V4h: Other Sports (handball, table tennis, MMA, baseball)
1. Appropriate statistical market selected (not defaulting to ML)?
2. Sport-specific data sources consulted?
3. Context verified (home/away, form, injuries)?

### V5: Coupon Structure
1. Minimum 2 legs per coupon?
2. Same-sport legs <= max?
3. HR coupon has min sports?
4. No same-match correlation?
5. Combined odds = product of legs (+-10%)?
6. Stake within coupon limit?
7. At least 5 coupons produced?

### V6: Portfolio Risk
1. No coupon stake > 3.00 PLN (LR) or 2.00 PLN (HR)?
2. Exposure < 25% of bankroll?
3. Exposure < 25% of bankroll?
4. Multi-sport diversification?
5. No tournament concentration (>4 picks same tournament)?

### V7: Weakness Flagging
1. List tennis picks with odds ratio > 1.30
2. List football picks without three-source stack
3. List CONDITIONAL picks with thresholds
4. Identify weakest coupon leg for each coupon
5. Note same-tournament risks

### V8: Final Sign-Off
All V1-V7 pass? -> PORTFOLIO APPROVED.
Any fail? -> Fix and re-check. Do not present until all pass.

---

## STEP 10: ARTIFACTS — Write and Commit

### 10.1 Write Order
1. Daily report: `betting/reports/YYYY-MM-DD.md`
2. Coupon file: `betting/coupons/YYYY-MM-DD.txt`
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
**Tennis**: total games O/U > set totals O/U > games handicap > set handicap > ML (1.50-2.50 only)
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
  [ ] Verify all 12 sports checked

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

STEP 7: Bear case for each pick
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

STEP 9: Validate V1-V8
  [ ] V1: artifacts consistent
  [ ] V2: per-pick sources valid
  [ ] V3: tennis checks pass
  [ ] V4: football checks pass
  [ ] V5: coupon structure valid
  [ ] V6: portfolio risk OK
  [ ] V7: weaknesses documented
  [ ] V8: all pass -> APPROVED

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
