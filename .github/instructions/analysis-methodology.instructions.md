---
applyTo: "betting/**/*"
---

# Analysis Methodology — Sequential Reasoning Protocol

This document captures the exact reasoning process used for daily pick composition. Follow these steps in order. Do not skip phases.

## Phase 1: Data Collection

1. Run orchestrator (`bash scripts/run_full_scan_and_prepare.sh`) to populate `betting/data/`.
2. Fetch Tier A market-best odds from BetExplorer for all sports in scope.
3. Fetch Tier A fixture data from Flashscore (schedules, results, H2H).
4. Fetch statistical data from specialist sources:
   - **Football corners/cards**: TotalCorner (match totals/handicaps), SoccerStats (league stats), Betaminic (team tables).
   - **Tennis**: TennisExplorer (H2H, surface form), TennisAbstract (Elo, serve/return profiles), UltimateTennisStatistics.
   - **Volleyball**: BetExplorer volleyball section (set/point totals, moneyline).
   - **Basketball**: Basketball-Reference (pace, ratings), DunksAndThrees.
   - **Hockey**: NaturalStatTrick (xGF, shot quality), MoneyPuck (predictions).
   - **Baseball**: BaseballSavant (Statcast data).
   - **Esports**: HLTV (CS2 stats), Liquipedia (tournament context), VLR.gg (Valorant), BO3.gg (CS2 predictions).
   - **Snooker**: CueTracker (H2H, frame averages), SnookerOrg (rankings/draws).
   - **Table Tennis**: ITTF rankings, tt-series.com (league predictions).
   - **Darts**: DartConnect (averages), DartsOrakel (predictions).
   - **Handball**: Handball-World, EHF stats.
   - **MMA/UFC**: UFCstats (fighter stats), Tapology (records, community picks).
5. **Tipster/community cross-check** (MANDATORY for every candidate):
   - Check at least 2 tipster/community sources per candidate: Zawod Typer, Trafiamy, Typersi, Protipster, Tipstrr, Blogabet, OLBG, FootySupertips, PicksWise, Windrawwin, BetIdeas, bettingexpert, GosuGamers (esports).
   - Record consensus direction, percentage, and notable tipster reasoning.
   - Tipster insights can reveal angles statistics miss (tactical changes, motivation, weather, late news).
6. Extract Betclic Statystyki odds from HTML snapshots for top-league matches (EPL, LaLiga, Bundesliga) — corners, cards, fouls, shots.
7. Check `betting/data/scan_errors.json` for source failures.
8. **Never declare "no sources available" for a sport without first searching specialist sites.** The internet is a goldmine of statistics, analysis, and prediction sites for every sport.

## Phase 2: Event Filtering

1. List all events in the betting-day window (06:00 today through 05:59 tomorrow, Europe/Warsaw).
2. For each event, note: sport, competition, kickoff, available odds.
3. **Cast the net WIDE**: scan ALL sports — football, tennis, basketball, hockey, volleyball, esports, snooker, table tennis, darts, handball, MMA. Do not limit to "major" events only.
4. **Football**: prioritize events where Betclic Statystyki tab is available (EPL, LaLiga, Bundesliga) for corner/card/foul markets. For other leagues, look for defensive profiles (SoccerStats BTTS%, O2.5%, team GF/GA) to back U2.5, BTTS, or DC markets.
5. **Tennis**: prioritize matches where match odds are close (both players between 1.50 and 2.50) — this indicates high 3-set probability, which favors over-games markets.
6. **Volleyball**: look for competitive matchups (ML odds 1.30-2.00 for favorite) where 4+ sets are likely — supports O3.5 sets and point totals.
7. **Esports**: check HLTV for CS2 tier-1/2 matches, Liquipedia for Dota 2/LoL events. Map handicap and map totals are strong markets.
8. **Snooker/Darts/Table Tennis**: check Betclic listings and cross-reference with CueTracker/DartsOrakel/tt-series.com for deep stats.
9. **Avoid popular high-profile events for pure result bets** — focus on statistical markets and deep analysis. Use 1X2/ML only with strong edge.
10. Discard events outside the betting-day window immediately.

## Phase 3: Statistical Market Selection

Prefer statistical markets over raw winners. The priority order by sport:

### Football
1. **Corners** (PRIMARY): Use three-source stack: TotalCorner (match corner total/handicap), SoccerStats (league corner rankings, team corner averages), Betclic Statystyki (verified corner odds from HTML snapshots). Match corners O8.5/O9.5/O10.5, 1H corners, team corners are all valid markets. Betclic Statystyki only available for EPL, LaLiga, Bundesliga.
2. **Cards**: Yellow card totals and team cards. Use SoccerStats card data + Betclic Statystyki when available.
3. **Fouls**: Match foul totals and team fouls. Use SoccerStats + Betclic Statystyki.
4. **Shots**: Match shot totals. Use Betclic Statystyki when available.
5. **BTTS**: use SoccerStats league BTTS% (accept when league > 55%) and team scoring/conceding profiles.
6. **Under 2.5**: use SoccerStats defensive profiles. Strong when: team GF+GA < 2.0 per match, league O2.5% < 50%, cup semifinal/final context.
7. **Team totals**: when one team dominates scoring.
8. **1X2/DC/DNB**: only when odds are in 1.30-3.50 range AND edge is clear (standings gap, form gap).
9. **Totals (Over/Under goals)**: LAST RESORT. Only use when no statistical markets available. Require strong form and H2H backing.

### Tennis — Over X Games (key market)
1. **Identify evenly matched pairings**: match odds between 1.50 and 2.50 for both players → high 3-set probability.
2. **Surface context**: clay (Madrid, Rome, Roland Garros) tends to produce more breaks and longer matches. Hard courts with big servers tend to hold serve → more games but potentially fewer breaks.
3. **Typical lines**: Over 20.5 games in best-of-3 = standard line. A 3-set match with 6-4, 4-6, 6-4 = 24 games (covers). A 2-set match with 6-3, 6-4 = 19 games (doesn't cover).
4. **3-set probability**: when odds are ~1.90/1.90, 3-set probability is typically 55-65%. When odds are 1.60/2.30, 3-set probability is ~45-50%. Higher 3-set probability = stronger over-games thesis.
5. **Player style**: aggressive baseliners on clay tend to produce longer rallies and more break opportunities. Big servers may hold easily → could mean decisive tiebreaks → 12-13 games per set.
6. **Never pick over games in massively one-sided matches** (e.g., 1.10/7.00) — these tend to finish in straight sets with bagels/breadsticks.

### Basketball, Hockey, Baseball
Follow standard totals and spreads analysis when US leagues are in session.

### Esports (CS2, Dota 2, LoL, Valorant)
1. **CS2**: Use HLTV rankings + recent form + map pool overlap + BO3.gg predictions. Map handicap and map O/U 2.5 are primary markets for BO3 matches.
2. **Dota 2 / LoL**: Use Liquipedia for bracket/roster context. Map handicap and kills totals when available.
3. **Valorant**: Use VLR.gg for map stats and player form.
4. **Key rule**: Only bet Tier 1 and Tier 2 events. Skip open qualifiers and unsigned team matches.

### Snooker
1. **Frame handicap**: Use CueTracker H2H and frame averages. Best-of-X format matters.
2. **Total frames**: Competitive matches (ranking difference < 20) favor over-frames.
3. **Century/50+ breaks**: High-break players (avg 40+) in long-format matches.
4. **Sources**: CueTracker for deep stats, SnookerOrg for draws, WorldSnooker for format.

### Table Tennis
1. **Set handicap / Total points**: Use ITTF rankings + tt-series.com form analysis.
2. **Key rule**: Stick to named tournaments (WTT, national leagues), avoid unverifiable exhibition matches.
3. **Sources**: Flashscore for results, ITTF for rankings.

### Darts
1. **Leg/set totals**: Use DartConnect player averages + DartsOrakel predictions.
2. **180s O/U**: High-averaging players (95+) produce more 180s.
3. **Sources**: PDC/WDF official data, DartConnect.

### Handball
1. **Totals**: Handball is high-scoring (50-60 total typical). Use league averages.
2. **Handicap**: Strong home-advantage sport.
3. **Sources**: Handball-World, EHF, Flashscore.

### MMA / UFC
1. **Moneyline**: Use UFCstats for statistical comparison (strikes/min, takedown accuracy, reach).
2. **Method of victory**: Analyze finish rate vs decision rate.
3. **Round totals O/U 1.5/2.5**: Heavy hitters → under, grapplers → could go distance.
4. **Sources**: UFCstats, Tapology, PicksWise.

### Volleyball
1. **Set totals (O/U 3.5 sets)**: Favor O3.5 in competitive matchups (favorite ML 1.30-2.00). Semifinal/final context supports competitiveness.
2. **Point totals (O/U 175.5 etc.)**: 4+ sets typically produce 190-200 total points. If O3.5 sets is likely, point over is strongly supported.
3. **Set handicap**: Use when clear quality gap but not dominant enough for 3-0.
4. **Moneyline**: Only in one-sided matchups with strong form evidence.
5. Sources: BetExplorer volleyball for odds comparison, Flashscore for results/H2H, Sofascore for form.

## Phase 4: Price Verification

1. Compare estimated Betclic odds to market-best from BetExplorer.
2. Calculate `price_gap_pct = 100 * ((bookmaker_odds / market_best_odds) - 1)`.
3. Low-risk picks: reject if gap < -3%.
4. Higher-risk picks: reject if gap < -5%.
5. **When Betclic match-level odds are inaccessible (HTTP 403)**, mark picks as CONDITIONAL and provide acceptance thresholds for user verification on app.

## Phase 5: Portfolio Construction — Non-Repeating Events

The key rule: **no event may appear in more than one selection (single OR coupon leg)**. This maximizes diversification and prevents catastrophic correlated losses.

### Allocation strategy:
1. **Singles (up to 3)**: assign highest-confidence picks as singles. Diversify across sports.
2. **Low-Risk Coupon (2-3 legs, max 2 PLN)**: combine remaining strong picks from different events. Each leg should be confidence 4-5. Max 2 same-sport legs.
3. **Higher-Risk Coupon (3-4 legs, max 1 PLN)**: combine additional picks. Each leg should be confidence 3+. Reduced stake. Max 2 same-sport legs.
4. **Check**: verify zero event overlap across all singles and coupons.
5. **Check**: total exposure within daily cap (4-7 PLN suggested, adjustable per config).

### Event distribution example:
- Single 1: Football match A
- Single 2: Tennis match D
- Single 3: Tennis match E
- LR Coupon: Football match B + Tennis match F
- HR Coupon: Football match C + Tennis match G + Tennis match H
→ 8 unique events, zero overlap, multi-sport

## Phase 6: Confidence Scoring

Score each pick 1-5 based on:
- 5: Multiple Tier A sources agree, strong statistical signal, good price gap
- 4: At least one Tier A + one Tier B agree, clear statistical direction, acceptable price
- 3: Directional signal present but some uncertainty or missing data
- 2: Weak signal, speculative
- 1: Pure gut or insufficient data (never use)

## Phase 7: Artifact Generation

Write all artifacts per the schema in `betting-artifacts.instructions.md`:
- Report: full analysis with all sections
- Coupon file: actionable plain-text format
- Picks ledger: one row per pick (singles AND coupon legs)
- Coupons ledger: one row per coupon
- Source log: all sources used
- Learning log: process changes only

Cross-check:
- Every pick_id in coupon file appears in picks ledger
- Every pick_id in a coupon's pick_ids appears in picks ledger
- No event duplicated across singles + coupons
- Total exposure matches sum of stakes

## Phase 8: Pre-Finalization Validation Protocol

After all picks and coupons are composed, run this full validation BEFORE presenting to the user. Do not skip any step. If any step fails, fix the issue or reject the pick before proceeding.

### V1: Artifact Consistency

Run these checks mechanically. Each must pass.

1. List every `pick_id` in the coupon file. Verify each exists in `picks-ledger.csv` with matching event, market, and selection.
2. List every `coupon_id` in the coupon file. Verify each exists in `coupons-ledger.csv` with matching pick_ids, stake, and combined odds.
3. Sum all stakes (singles + all coupon stakes). Verify the total matches `TOTAL PLANNED EXPOSURE PLN` in the coupon file.
4. Verify `UNUSED FROM CAP PLN` equals daily cap minus total exposure.
5. Verify no `pick_id` is duplicated in the picks ledger.
6. Verify no event name appears in more than one ticket (single or coupon). Build a table: event → ticket. Flag any event in 2+ tickets.
7. Verify the report's Exposure Summary numbers match the coupon file and ledger numbers exactly.

### V2: Per-Pick Source Validation

For each pick, answer these questions. If any answer is NO, the pick fails and must be rejected or downgraded.

1. **Tier A stats/fixture source present?** Name the source and the specific data point it provides (e.g., "Flashscore: fixture confirmed at 21:30 CEST", "Forebet: avg_goals 3.79").
2. **Tier A market/price source present?** Name the source and the specific odds it provides (e.g., "BetExplorer: 1X2 odds 1.26/6.66/9.69").
3. **Bookmaker odds stated?** If estimated, is it marked CONDITIONAL with an acceptance threshold?
4. **Market-best odds stated?** Is there a comparison price from a Tier A market source?
5. **Price gap calculated?** Is `price_gap_pct` within the allowed threshold for the pick's risk tier?
   - Low-risk: reject if gap < -3%
   - Higher-risk: reject if gap < -5%
6. **Confidence score (1-5) assigned with justification?** One sentence explaining why this score, not higher or lower.

### V3: Tennis Over-Games Specific Validation

For each tennis Over X games pick, check these conditions. All must pass.

1. **Match odds range check:** Are both players' match odds between 1.50 and 2.50? If one player is below 1.50, the match is too lopsided — 3-set probability drops below 40%. Reject.
2. **Odds gap ratio:** Calculate `max(odds_A, odds_B) / min(odds_A, odds_B)`. This is the "evenness ratio."
   - Ratio ≤ 1.15: STRONG (~55-65% 3-set probability). Best candidates.
   - Ratio 1.15–1.30: GOOD (~48-55% 3-set probability). Acceptable.
   - Ratio 1.30–1.50: BORDERLINE (~42-48% 3-set probability). Only use in coupon legs, never as singles. Reduce confidence to 3.
   - Ratio > 1.50: REJECT. Too lopsided for over-games market.
3. **Surface context:** Clay (Madrid, Rome, Roland Garros) produces more breaks and tends to extend matches. Hard court with big servers may produce fewer breaks. Note the surface and how it affects the thesis.
4. **Line check:** Is the line Over 20.5 games (standard best-of-3) or something else? Over 20.5 = a 3-set match with 6-4, 4-6, 6-4 (24 games) covers easily. A 2-set match with 6-4, 6-3 (19 games) does NOT cover.
5. **Player withdrawal/cancellation check:** Check Flashscore for any "Cancelled" or "Walkover" markers on the match. If the match is cancelled, remove the pick immediately.
6. **Player level assessment:** Are both players established tour-level (ATP/WTA main draw or strong qualifiers)? If one is a complete unknown with no tour results, downgrade confidence.

### V4: Football Validation

For each football pick, check these conditions.

1. **Market type hierarchy respected?** Corners/cards/fouls/shots picks are preferred over goals markets. If a goals market is used, confirm no statistical market was available for this match.
2. **Corner three-source stack?** For corner picks: TotalCorner match total + SoccerStats league corner ranking + Betclic Statystyki verified odds. If Statystyki unavailable (non-top-league), mark CONDITIONAL.
3. **BTTS league backing?** SoccerStats BTTS% > 55% for the league AND both teams score/concede regularly.
4. **U2.5 defensive profile?** SoccerStats league O2.5% < 55% AND team defensive profile (GF+GA < 2.0/match) confirms.
5. **O2.5 fallback justified?** Forebet avg_goals > 2.8 OR SoccerStats goals avg > 2.7 for the league, plus H2H and form support.
6. **Competition context:** League, cup, playoff? Cup semis/finals tend to be tactical (favor U2.5). League dead rubbers may be unpredictable.
7. **Missing data flags:** If no Tier A statistical source backs the market direction, do NOT proceed.

### V4b: Volleyball Validation

For each volleyball pick:

1. **Set totals O3.5:** ML odds for favorite between 1.30-2.00 (indicates competitive match). If favorite < 1.20, 3-0 sweep risk is too high.
2. **Point totals:** Only if O3.5 sets is likely (competitive matchup). 4+ sets typically = 190-200 total points.
3. **Competition context:** Semifinal/final = higher competitiveness. Regular season may have blowouts.
4. **Source backing:** BetExplorer for odds, Flashscore for form/H2H.

### V5: Coupon Structure Validation

For each coupon, verify against `config/betting_config.json`.

1. **Leg count within limits?**
   - Low-risk coupon: ≤ `max_low_risk_coupon_legs` (default 3)
   - Higher-risk coupon: ≤ `max_higher_risk_coupon_legs` (default 4)
   - Medium/extra coupons: use the lower of the two limits (3 legs max)
2. **Same-sport legs within limit?** Count tennis legs, football legs, etc. in the coupon. Must be ≤ `max_same_sport_legs_in_coupon` (default 2).
3. **Higher-risk coupon multi-sport?** If variant is "higher-risk", must have ≥ `min_sports_for_higher_risk_coupon` different sports (default 2).
4. **Correlation check:** No two legs from the SAME MATCH. No two legs that share a strong narrative link (e.g., "Team A wins" and "Team A Over 1.5 goals" are correlated). Flag and remove if found.
5. **Combined odds sanity check:** Multiply individual leg odds. Does the product roughly match the stated combined odds? If off by more than 10%, there's an error.
6. **Stake within limit?**
   - Low-risk coupon: ≤ `low_risk_coupon_max_stake_pln` (default 2.00)
   - Higher-risk coupon: ≤ `higher_risk_coupon_max_stake_pln` (default 1.00)

### V6: Portfolio Risk Check

1. **Total exposure ≤ daily cap?** Check against `suggested_daily_allocation_range_pln` upper bound.
2. **No single stake > `max_single_stake_pln`?** (default 2.00 PLN)
3. **Exposure as % of bankroll:** Calculate `total_exposure / working_bankroll * 100`. Should be < 25%. If > 25%, reduce stakes or drop weakest picks.
4. **Sport diversification:** Count events per sport. If all picks are from one sport, flag it. The config prefers multi-sport (`prefer_multi_sport: true`).
5. **Tournament concentration:** Count picks from the same tournament. If > 4 picks from one tournament, consider whether weather/scheduling risks create hidden correlation.

### V7: Weakness Flagging and Risk Assessment

List every known weakness. For each, state whether it is ACCEPTED (with reason) or requires ACTION.

1. **Tennis picks with odds gap ratio > 1.30:** List them. State which coupon they're in and what stake is at risk.
2. **Football picks with avg_goals < 3.0 for Over 2.5:** List them.
3. **CONDITIONAL picks (unverified Betclic odds):** List them. State the acceptance threshold the user must check.
4. **Weakest coupon leg:** For each coupon, identify the leg most likely to fail. State the risk scenario (e.g., "Kasatkina cruises in straight sets 6-2, 6-3 = 17 games, doesn't cover Over 20.5").
5. **Same-tournament concentration:** If multiple picks from one tournament, state the shared risk factors (weather, court conditions, schedule delays).

### V8: Final Sign-Off

Answer each question YES or NO. All must be YES to proceed.

1. All V1 artifact consistency checks pass?
2. All V2 source requirements met for every pick?
3. All V3 tennis validation checks pass (or borderline picks are flagged and in coupons only)?
4. All V4 football validation checks pass?
5. All V5 coupon structure rules satisfied?
6. All V6 portfolio risk limits respected?
7. V7 weaknesses documented and accepted or acted on?
8. Odds timestamp is current (within 2 hours of write time)?

If all YES: **PORTFOLIO APPROVED — present to user.**
If any NO: Fix the issue, then re-run the failed check. Do not present until all pass.

---

## Quick Reference: Validation Checklist (compact form for fast runs)

```
V1: ARTIFACTS
□ All pick_ids in coupon file exist in picks ledger
□ All coupon_ids in coupon file exist in coupons ledger  
□ Stake sum = total exposure
□ Unused = cap - total
□ No duplicate pick_ids
□ No event in 2+ tickets
□ Report exposure matches coupon file

V2: SOURCES (per pick)
□ Tier A stats source + specific data point
□ Tier A market source + specific odds
□ Bookmaker odds stated or CONDITIONAL
□ Price gap within threshold

V3: TENNIS OVER-GAMES (per tennis pick)
□ Both match odds 1.50–2.50
□ Odds gap ratio ≤ 1.50 (reject if higher)
□ Surface noted (clay/hard/grass)
□ Match not cancelled on Flashscore
□ Both players tour-level

V4: FOOTBALL (per football pick)
□ Market hierarchy respected (corners/cards/fouls > BTTS/U2.5 > O2.5)
□ Corner picks: three-source stack verified (TotalCorner + SoccerStats + Betclic Statystyki)
□ BTTS: SoccerStats BTTS% > 55%
□ U2.5: SoccerStats O2.5% < 55% + defensive profile
□ O2.5 (fallback): Forebet avg_goals > 2.8 or SoccerStats avg > 2.7

V4b: VOLLEYBALL (per volleyball pick)
□ Set totals: favorite ML between 1.30-2.00 (not too dominant)
□ Point totals: O3.5 sets likely first
□ Competition context (semifinal = competitive)

V5: COUPONS (per coupon)
□ Leg count within config limit
□ Same-sport legs ≤ max
□ HR coupon has min sports
□ No same-match correlation
□ Combined odds = product of legs (±10%)
□ Stake within coupon limit

V6: PORTFOLIO
□ Total ≤ daily cap
□ No single > max_single_stake
□ Exposure < 25% of bankroll
□ Multi-sport diversification

V7: WEAKNESSES
□ Borderline tennis picks listed
□ CONDITIONAL picks listed with thresholds
□ Weakest coupon legs identified
□ All weaknesses accepted or fixed

V8: SIGN-OFF
□ All V1–V7 pass → APPROVED
```
