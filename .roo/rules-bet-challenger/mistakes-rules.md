# Betting Mistakes — Challenger Reference

## ⛔ HARD RULES (violation = reject from coupon)

1. **TENNIS_SETS_001:** O3.5 sets needs ALL: ranking ≤15 gap + competitive H2H + <60% straight-set + no surface mismatch + no injury return.
2. **TENNIS_GAMES_001:** Underdog games Over needs: gap <50 + hold >50% + odds ≤2.00.
3. **HANDBALL_001:** ML only at odds ≤1.43. Never in 2+ coupons.
4. **GOALS_001:** Combined L5 > line + 0.5. Below → flip to UNDER.
5. **UNDER_GOALS_001:** U2.5 forbidden: team needs win + L5 > 2.5 + odds ≥2.00.
6. **LOWER_LEAGUE_001:** No ML below 3rd tier. 2./3. Liga only at ≤1.40.
7. **SOT_001:** Combined L5 SOT > line + 1.5. Below → INSTANT REJECT.
8. **CORNERS_CONTEXT_001:** Dead rubber → subtract 2.5 from expected.
9. **BTTS_CONTEXT_001:** Relegation = NO BTTS.
10. **CORRELATION_001:** MAX 1 coupon per pick. NEVER repeat.
11. **SAFETY_FLOOR_001:** Below threshold → Extended Pool only.

## Close Game Rule (ZT#24)
P(draw) ≥ 25% + fouls/cards UNDER + avg within ±1.5 of line → DO NOT BET this market.

## Advisory Tier (assigned by gate_checker.py)
- STRONG (≤2 failed): full stake
- MODERATE (3-5 failed): standard stake
- WEAK (6-9 failed): reduced stake or watchlist
- FLAGGED (10+ failed): user must review carefully

## Key Failure Patterns
- Same pick in multiple coupons → catastrophic correlation
- Ignoring dead rubber context → corners/fouls undershoot
- Betting on tired/depleted squads without adjustment
- Tennis mismatch markets (O3.5 when one player dominates)
