---
applyTo: "betting/**/*"
---

# Analysis Methodology — Sequential Reasoning Protocol

This document captures the exact reasoning process used for daily pick composition. Follow these steps in order. Do not skip phases.

## Phase 1: Data Collection

1. Run orchestrator (`bash scripts/run_full_scan_and_prepare.sh`) to populate `betting/data/`.
2. Fetch Tier A market-best odds from BetExplorer for all sports in scope (football today page, tennis tournament pages).
3. Fetch Tier A fixture data from Flashscore (schedules, results, H2H).
4. Fetch Tier B model predictions from Forebet (avg_goals for football, match predictions).
5. Extract Betclic adapter odds where available (1X2 from league pages).
6. Check `betting/data/scan_errors.json` for source failures.

## Phase 2: Event Filtering

1. List all events in the betting-day window (06:00 today through 05:59 tomorrow, Europe/Warsaw).
2. For each event, note: sport, competition, kickoff, available odds.
3. **Football**: prioritize events where Forebet avg_goals > 2.5 (for totals) or where competitive odds suggest balanced match.
4. **Tennis**: prioritize matches where match odds are close (both players between 1.50 and 2.50) — this indicates high 3-set probability, which favors over-games markets.
5. Discard events outside the betting-day window immediately.

## Phase 3: Statistical Market Selection

Prefer statistical markets over raw winners. The priority order by sport:

### Football
1. **Totals (Over/Under)**: use Forebet avg_goals as primary signal. Accept Over 2.5 when avg_goals > 3.0 with confirming trends (previous H2H, team scoring rates, defensive records).
2. **BTTS**: use team scoring/conceding rates. Both teams must score in >55% of recent matches.
3. **Team totals**: when one team dominates scoring.
4. **Corners**: only when tempo profile confirmed by multiple sources.
5. **1X2/DC/DNB**: only when price is in 1.30–3.50 range AND edge is clear.

### Tennis — Over X Games (key market)
1. **Identify evenly matched pairings**: match odds between 1.50 and 2.50 for both players → high 3-set probability.
2. **Surface context**: clay (Madrid, Rome, Roland Garros) tends to produce more breaks and longer matches. Hard courts with big servers tend to hold serve → more games but potentially fewer breaks.
3. **Typical lines**: Over 20.5 games in best-of-3 = standard line. A 3-set match with 6-4, 4-6, 6-4 = 24 games (covers). A 2-set match with 6-3, 6-4 = 19 games (doesn't cover).
4. **3-set probability**: when odds are ~1.90/1.90, 3-set probability is typically 55-65%. When odds are 1.60/2.30, 3-set probability is ~45-50%. Higher 3-set probability = stronger over-games thesis.
5. **Player style**: aggressive baseliners on clay tend to produce longer rallies and more break opportunities. Big servers may hold easily → could mean decisive tiebreaks → 12-13 games per set.
6. **Never pick over games in massively one-sided matches** (e.g., 1.10/7.00) — these tend to finish in straight sets with bagels/breadsticks.

### Basketball, Hockey, Baseball
Follow standard totals and spreads analysis when US leagues are in session.

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

### V4: Football Totals Specific Validation

For each football Over/Under totals pick, check these conditions.

1. **Forebet avg_goals:** Is it above the line threshold? For Over 2.5, avg_goals should be > 2.8 (ideally > 3.0). For Over 3.5, avg_goals should be > 3.5.
2. **H2H recent meetings:** Do the last 3-5 head-to-head meetings support the totals direction? Count how many went Over/Under the line.
3. **Team form (last 5):** Are both teams in scoring form? For Over 2.5, check team scoring and conceding rates per game.
4. **Competition context:** League match, cup match, playoff? Cup matches (especially semis/finals) can be more tactical. Adjust confidence accordingly.
5. **Missing data flags:** If Forebet prediction is unavailable, do NOT proceed with a football totals pick without an alternative statistical source. The pick needs quantitative backing.

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

V4: FOOTBALL TOTALS (per football pick)
□ Forebet avg_goals above line threshold
□ H2H supports direction
□ Team form supports direction

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
