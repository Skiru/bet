# Pipeline Errors Journal — 2026-05-26 (Settlement of 25.05.2026)

## Settlement Summary
- **Date:** 25.05.2026
- **Coupons:** 6 (1W / 5L)
- **Net PnL:** ±0.00 zł (breakeven — rescued by one 4.50 winner)
- **Staked:** 4.50 zł | Won: 4.50 zł

## Critical Lessons for Next Session

### 1. EXISTING RULE WAS VIOLATED (LOWER_LEAGUE_001)
- Wolfsburg "Przewaga dwoma bramkami lub wygrana" @ **2.00** — rule says max **1.43**!
- This is the most unforgivable error: the rule EXISTED and was IGNORED.
- **ENFORCEMENT:** Before building ANY coupon, run automated rule check against betting-mistakes-rules.

### 2. AKO(5) = GUARANTEED LOSS (now 0/17 lifetime!)
- The 5-pick tennis combo had 14% probability from the start
- With 2 ML picks at 1.24 and 1.81, the combo was doomed
- **RULE:** NEVER build AKO(5)+. Max 4 legs. Max 2 ML picks.

### 3. STAT MARKETS = THE ONLY WINNING FORMULA
- The ONLY winning coupon (Coupon 4, @4.50) was 100% stat markets (fouls + corners)
- Hit rates: team_corners 84%, cards 79%, shots 75%, fouls 67%
- vs: match_winner(football) 38%, win_by_2 43%, tennis ML 49%
- **ENFORCEMENT:** Minimum 70% stat markets in every coupon. Max 1 outcome/ML leg per coupon.

### 4. PLAYOFF CONTEXT IS MANDATORY
- Brescia/Trieste missed O165.5 by 0.5 points because playoff defense wasn't factored
- **ENFORCEMENT:** Any playoff game → apply -5 to -8 adjustment on totals

### 5. ICELAND/MINOR LEAGUE = NO GOALS OVER
- Icelandic football structurally averages 2.1 goals/game
- **ENFORCEMENT:** New ICELAND_GOALS_001 rule added

## Key Takeaways for Pipeline
1. Run automated rule-check BEFORE coupon construction
2. Ban AKO(5)+ — 0/17 lifetime = statistically dead
3. Enforce stat-market minimum (70% of legs)
4. Playoff detection → automatic line adjustment
5. Country/league scoring profiles as hard data (not guessed)
