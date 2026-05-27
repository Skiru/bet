# Coupon Risk Lessons

## Hard Rules (from settled losses)
1. TENNIS_SETS_001: O3.5 sets needs ranking ≤15 gap + competitive H2H + <60% straight-set wins.
2. TENNIS_GAMES_001: Underdog O games needs ranking gap <50 + hold rate >50% + odds ≤2.00.
3. HANDBALL_001: ML only at implied ≥70%. Never same handball pick in 2+ coupons.
4. GOALS_001: Combined L5 goals MUST > line + 0.5 buffer. Below → flip to UNDER.
5. UNDER_GOALS_001: U2.5 forbidden when team needs to win + combined L5 > 2.5 + odds ≥2.00.
6. LOWER_LEAGUE_001: Never ML below 3rd tier in AKO. Prefer stat markets.
7. SOT_001: Combined L5 SOT must > line + 1.5 buffer. Below → INSTANT REJECT.
8. CORNERS_CONTEXT_001: Dead rubber → subtract 2.5 from expected corners.
9. BTTS_CONTEXT_001: Relegation = default NO BTTS.
10. CORRELATION_001: MAX 1 coupon per unique pick. NEVER repeat across coupons.
11. SAFETY_FLOOR_001: Minimum safety score threshold applies.

## Catastrophic Day: 2026-05-24 (-9.06 PLN)
- 4 unique losing picks repeated across coupons → 9 coupon losses.
- Root cause: same bet in multiple coupons = correlated disaster.
