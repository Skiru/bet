# Coupon Risk Lessons

## Core Rules (from catastrophic losses)

1. **CORRELATION_001**: MAX 1 coupon per unique pick. Repeating picks across coupons = multiplied losses.
2. **DATA-BACKED STAT MARKETS WIN**: L5 > line + buffer → historically profitable.
3. **OPINION/GUT/CONTEXT-IGNORED PICKS LOSE**: Without statistical backing, picks are gambling.

## 2026-05-24 Catastrophe (-9.06 PLN, 1W/11L)

### What WON (all stat-backed):
- Tottenham fouls O12.5 (L5=13.6 vs 12.5 line)
- Man Utd SOT O3.5 (L5=4.6 vs 3.5 line)
- Arsenal SOT O3.5 (L5=4.6 vs 3.5 line)
- Man City corners O8.5 (L5=9.4 vs 8.5 line)
- Burnley/Wolves U2.5 (combined L5=1.2 vs 2.5 line)
- ALL had L5 > line + clear buffer. ALL stat markets.

### What LOST (pattern):
- Tennis O3.5 sets with ranking gap >15 (TENNIS_SETS_001 violation)
- Over goals when combined L5 < line (GOALS_001 violation)
- Lower league ML at odds >1.40 (LOWER_LEAGUE_001 violation)
- Same pick in 4+ coupons = 9 losses from 4 bad picks (CORRELATION_001)

## 2026-05-26 v1 Total Failure (rebuilt to v2)

### Gate Bugs Discovered:
1. Gate approved safety=0.0 picks → added SAFETY_FLOOR_001
2. Gate used absolute hit_num≥7 instead of hit_rate≥0.70 → fixed denominator
3. No context override for direction (must-win + UNDER = wrong) → DIRECTION_CONTEXT_001
4. Started events in matryca → must check kickoff > NOW
5. L5 5/5 (100%) demoted for synthetic data → SYNTHETIC_RESCUE_001

### Orchestrator Rules (ALWAYS apply after S8):
- Check kickoff > NOW before presenting any pick
- REJECT safety < 0.15 regardless of gate
- VALIDATE direction when margin ≤ 0.5
- RESCUE L5 ≥ 4/5 from EXTENDED
- Matryca is INFORMATIONAL only — not "bettable"

## Meta-Insight

- If challenger returns 0 BET and odds ≈ safety-implied fair odds → NO BET or micro-stakes only
- Combo menus must NOT turn watchlist/conditional legs into real portfolio
- Cards + cards combos with same H2H-blind defect = structurally weak
