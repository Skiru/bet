# Betting Mistakes & Hard Rules

> Apply at COUPON CONSTRUCTION (S8) and GATE (S7). Candidates stay in matrix — rules REJECT from coupons.

## ⛔ Instant Reject Conditions

| Rule | Condition | Action |
|------|-----------|--------|
| SAFETY_FLOOR_001 | safety_score < 0.15 | INSTANT REJECT |
| SAFETY_FLOOR_001 | safety_score < 0.30, core coupon | REJECT (extend only) |
| CORRELATION_001 | Same pick in 2+ coupons | REJECT from 2nd coupon |
| KICKOFF_GUARD_001 | kickoff < NOW | INSTANT REJECT |

## Tennis Rules

**TENNIS_SETS_001 — O3.5 Sets:** ALL must be true: ≤15 ranking gap, competitive H2H, BOTH <60% straight-set wins L5, no surface mismatch, no injury return. ANY fails → REJECT.

**TENNIS_GAMES_001 — Underdog Games Over:** Ranking gap <50, service hold >50% L5, odds ≤2.00. Otherwise REJECT.

## Team Sport Rules

**HANDBALL_001:** ML needs implied prob ≥70% (odds ≤1.43) for AKO. NEVER same handball pick in 2+ coupons. Prefer totals/handicaps.

**GOALS_001 — Over X Goals:** Combined L5 goals MUST be > line + 0.5 buffer. If combined L5 < line → FLIP to UNDER or SKIP.

**UNDER_GOALS_001:** FORBIDDEN when: must-win context, combined L5 > 2.5, odds ≥2.00. MAX 1 coupon per U2.5 pick.

**LOWER_LEAGUE_001:** No ML below 3rd tier as AKO leg. 2./3. Liga ML only at odds ≤1.40. Prefer STAT MARKETS.

**SOT_001 — Shots on Target:** Combined L5 SOT must be > line + 1.5 buffer. If L5 < line → INSTANT REJECT. Dead rubber → subtract 1.5.

**CORNERS_CONTEXT_001:** Dead rubber → subtract 2.5 from expected corners. If post-penalty < line → REJECT.

**BTTS_CONTEXT_001:** Relegation matches → default NO BTTS. Never BTTS live when 0-0 at 30'+ in defensive match.

## Meta Rules

**DIRECTION_CONTEXT_001:** margin ≤ 0.5 + must-win context → VERIFY direction manually. If L5 contradicts direction → REJECT/FLIP.

**SYNTHETIC_RESCUE_001:** L5 ≥ 4/5 (80%+) hit rate → NEVER auto-demote. Rescue from EXTENDED if consistency is high.

## Quick Decision Matrix

| Situation | Action |
|-----------|--------|
| safety < 0.15 | INSTANT REJECT |
| safety < 0.30 in core | REJECT (extend) |
| Tennis O3.5, gap >15 | REJECT |
| Handball ML >1.43 | REJECT from AKO |
| Over goals, L5 < line | REJECT or flip |
| U2.5 + must-win | REJECT |
| Lower league ML >1.40 | REJECT |
| SOT Over, L5 < line | INSTANT REJECT |
| Same pick in 2 coupons | REJECT from 2nd |
| Dead rubber + stat market | -2.5 penalty |
| BTTS in relegation | REJECT |
| L5 ≥ 4/5 in EXTENDED | RESCUE to coupon |
| kickoff < NOW | INSTANT REJECT |
