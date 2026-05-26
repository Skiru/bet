---
description: "Hard reject rules derived from settled losses. MANDATORY during S3/S5/S7/S8. These rules apply at COUPON CONSTRUCTION stage — candidates still appear in the matrix (R3 compliance) but are FLAGGED/REJECTED when building final coupons."
---

# Betting Mistakes & Hard Rules (MANDATORY READ)

> **When to read:** Every agent during S3 (deep stats), S5 (odds evaluation), S7 (gate), and S8 (coupon building).
> **R3 Compliance:** These rules do NOT auto-reject from the pipeline matrix. Candidates ALWAYS appear in the matrix and Extended Pool. These rules apply when BUILDING COUPONS — the coupon_builder and bet-builder agent must enforce them. In the gate, they produce FLAGS (not auto-rejections) so the user can see WHY a pick is risky.
> **Source:** Settled results from `betting/journal/learning-log.md` and `betting/journal/{date}-pipeline-errors.md`.
> **Last updated:** 2026-05-24 after -9.06 PLN catastrophic day.

---

## ⛔ HARD RULES — Violation = Automatic REJECT from coupon

### TENNIS_SETS_001 — Over 3.5 Sets Qualification

Over 3.5 sets ONLY when ALL conditions met:
1. Players within **15 ranking spots** of each other
2. H2H record is competitive (no 3-0 or worse dominance by either)
3. BOTH players have **<60% straight-set wins** in last 5 matches
4. Surface does NOT heavily favor one player (check clay/hard/grass specialist status)
5. Neither player is returning from long injury/ban (reduced fitness = faster losses)

**If ANY condition fails → REJECT O3.5 sets. No exceptions.**

Evidence: 2026-05-24 lost 3 coupons on Etcheverry vs Borges (Borges won 6-3, 6-4, 6-2) and Kecmanovic vs Marozsan (won in 3 sets). Both were clear mismatches.

---

### TENNIS_GAMES_001 — Player Game Totals (Underdog Over)

Betting on underdog's total games OVER requires:
1. Ranking gap **<50 spots**
2. Underdog's service hold rate in L5 matches **>50%**
3. Odds must be ≤2.00 (higher odds = bookmaker EXPECTS the underdog to get crushed)

Evidence: 2026-05-24 Fiona Ferro O6.5 games @2.45 vs Andreeva (rank gap ~135). Ferro got 6 games (3+3). Bookmaker odds of 2.45 were screaming "this probably won't happen."

---

### HANDBALL_001 — Handball Match Winner in AKO

1. Required implied probability **≥70%** (odds ≤1.43) for AKO leg
2. **NEVER** place same handball pick in 2+ coupons
3. Prefer totals/handicaps over match winner for handball
4. Check playoff/season implications for BOTH teams

Evidence: 2026-05-24 Wisła Płock ML @1.70 vs Industria Kielce (lost 25-30). Placed in 2 separate coupons = 2 losses from one mistake.

---

### GOALS_001 — Over X Goals Statistical Gate

1. Combined L5 goals of both teams MUST be **> line + 0.5** minimum buffer
2. If combined L5 < line → **FLIP to UNDER** or SKIP entirely
3. Playoffs/cup finals → apply **UNDER bias** unless data overwhelmingly contradicts

Evidence: 2026-05-24 Parma vs Sassuolo O2.5 @1.88. Parma home goals L5=1.0, Sassuolo goals L5=1.2. Combined=2.2 which is BELOW 2.5 line. Result: 1-0. The data SAID under.

---

### UNDER_GOALS_001 — Under 2.5 Goals Restrictions

Under 2.5 is **FORBIDDEN** when:
1. End-of-season match where one team **NEEDS to win** (title/CL/relegation)
2. Combined L5 goals > 2.5 (stats don't support under)
3. Odds **≥2.00** (coin flip implies NO EDGE — bookmaker sees it as 50/50)
4. **NEVER** place same U2.5 pick in more than 1 coupon

Evidence: 2026-05-24 Crystal Palace vs Arsenal U2.5 @1.92-1.94 placed in 3 SEPARATE coupons. Arsenal needed to win for title race. Result: 1-2 (3 goals). All 3 coupons lost.

---

### LOWER_LEAGUE_001 — Lower League Match Winners

1. **NEVER** use match winner/handicap below **3rd tier** as AKO leg (no data = pure gamble)
2. 2. Liga and 3. Liga ML: only at odds **≤1.40** (implied ≥71%)
3. "Przewaga 2+ lub wygrana" needs odds **≤1.43** (this market loses on draws!)
4. For lower leagues: prefer **STAT MARKETS** (corners, fouls) where data exists

Evidence: 2026-05-24 Pcimianka Pcim ML @2.17 (7th tier!), Ruch Chorzów away @1.75 (lost 2-3), Śląsk Wrocław -2/win @1.54 (0-0 draw).

---

### SOT_001 — Shots on Target Over Lines

1. Combined L5 SOT MUST be **> line + 1.5 buffer**
2. If combined L5 **< line** → **INSTANT REJECT** (no exceptions!)
3. End-of-season dead rubber context → subtract **1.5** from expected SOT (reduced intensity)
4. Verify both teams have **consistent** SOT (check std deviation — if one team swings 1-9, unreliable)

Evidence: 2026-05-24 Brighton vs Man Utd O9.5 SOT. Combined L5 = 7.4. Line = 9.5. Gap = 2.1 BELOW line. Should have been INSTANT REJECT.

---

### CORNERS_CONTEXT_001 — Dead Rubber Corner Penalty

Even when stats support Over corners:
1. Check if match is a **dead rubber** (both teams with nothing to play for)
2. Apply dead rubber penalty: **subtract 2.5** from expected combined corners
3. If post-penalty value < line → **REJECT**

Evidence: 2026-05-24 Napoli (already champions) vs Udinese O9.5 corners. Stats said 11.8 combined, BUT dead rubber penalty → 9.3 < 9.5 → should have been rejected.

---

### BTTS_CONTEXT_001 — Both Teams to Score Restrictions

1. Relegation matches → **default NO BTTS** (defensive tactical approach dominates)
2. **NEVER** bet BTTS live when score is 0-0 at 30'+ in a defensive/tight match
3. BTTS needs attacking context: title race, derby, historically open encounters

Evidence: 2026-05-24 Catanzaro vs Monza BTTS @1.83 (live 31', 0-0). Serie B relegation playoff. Result: 0-0.

---

### CORRELATION_001 — Pick Repetition Limit (MOST CRITICAL!)

1. **MAX 1 coupon per unique pick** — NEVER repeat same bet across multiple coupons
2. If a pick fails, it kills EVERY coupon it's in → catastrophic correlation
3. 2026-05-24 proof: 4 unique losing picks were repeated across coupons → caused 9 coupon losses
4. Diversify: each coupon should have DIFFERENT events, not the same events recombined

Evidence: Crystal Palace vs Arsenal U2.5 in 3 coupons, Wisła Płock in 2, Etcheverry O3.5 in 2, Odra/Polonia U2.5 in 2 → 4 losing picks × 2.25 avg coupons = 9 losses instead of 4.

---

### SAFETY_FLOOR_001 — Minimum Safety Score

1. safety_score < 0.15 → **INSTANT REJECT** from any coupon
2. safety_score < 0.30 → **NEVER in core coupon**; extended pool ONLY
3. Gate APPROVED status does NOT override this (gate uses 19 criteria, safety is just 1)

Evidence: 2026-05-26 Bologna/Trento Points U73.5 safety=0.0, gate_score 11/19 → APPROVED. Zero statistical edge. Should never have been on coupon.

---

### DIRECTION_CONTEXT_001 — Direction Override for Must-Win

When margin ≤ 0.5 (avg ≈ line) AND match has relegation/promotion/must-win context:
1. **VERIFY direction manually** — pure statistical direction may be wrong
2. If team MUST attack (trailing in playoff series, relegation playoff) → shots/goals OVER bias
3. If l5_avg CONTRADICTS the chosen direction → **REJECT or FLIP**
4. avg = line (exactly) is NOT an edge — it's a coin flip

Evidence: 2026-05-26 Fürth Shots U13.5. Avg=13.5=line (zero margin). L5_avg=13.8 > line (contradicts UNDER). Team lost 0-1 first leg, playing at home, MUST attack. UNDER is wrong direction.

---

### SYNTHETIC_RESCUE_001 — Do Not Penalize High-Consistency Picks

When a pick has L5 ≥ 4/5 (80%+) hit rate:
1. **NEVER auto-demote** regardless of data source (synthetic/real)
2. L5 consistency > data completeness in predictive value
3. If gate says EXTENDED but L5 ≥ 4/5: **RESCUE to coupon consideration**
4. Compare hit_rate as PERCENTAGE, not absolute numerator (6/8=75% > 7/10=70%)

Evidence: 2026-05-26 Waltert vs Siniakova, L5 5/5 (100%!) demoted to EXTENDED because hit_num=6 < 7 threshold (designed for /10 denominator). Best pick of the day missed.

---

### KICKOFF_GUARD_001 — Time Validation at Presentation

1. **EVERY pick presented to user MUST have kickoff > NOW**
2. Orchestrator checks `kickoff > current_time` AFTER gate, AFTER coupon build, BEFORE presentation
3. Matryca/matrix is informational only — NEVER present started events as bettable
4. If >30 min until kickoff: OK. If <30 min: FLAG as TIME-CRITICAL.

Evidence: 2026-05-26 coupon v1 matrix led with 4 tennis picks (13:00 UTC) already LIVE when user saw the coupon (13:38 UTC). Misleading presentation.

---

## 📋 Quick Decision Matrix for Agents

| Situation | Action |
|-----------|--------|
| safety_score < 0.15 | INSTANT REJECT |
| safety_score < 0.30, in core coupon | REJECT (extend only) |
| Tennis O3.5 sets, ranking gap >15 | REJECT |
| Handball ML odds >1.43 | REJECT from AKO |
| Over goals, combined L5 < line | REJECT (or flip to UNDER) |
| Under 2.5, PL last day, team needs win | REJECT |
| Lower league ML, odds >1.40 | REJECT |
| SOT Over, combined L5 < line | INSTANT REJECT |
| Same pick already in another coupon | REJECT from 2nd coupon |
| Dead rubber + stat market | Apply -2.5 penalty, re-evaluate |
| BTTS in relegation playoff | REJECT |
| Any bet below 3rd tier league | REJECT unless stat market with data |
| margin ≤ 0.5 + must-win context | VERIFY direction manually |
| l5_avg contradicts direction | FLAG CONFLICTED, likely REJECT |
| L5 ≥ 4/5 in EXTENDED pool | RESCUE — consider for coupon |
| kickoff < NOW | INSTANT REJECT from presentation |

---

## ✅ What WORKS (positive signals from same day)

| Market Type | Data Signal | Hit Rate |
|-------------|------------|----------|
| Team corners OVER | Combined L5 > line + 1.0 | 87% |
| Team fouls OVER | L5 avg > line, rising trend | 77%+ |
| SOT OVER (reasonable line) | Combined L5 > line + 1.5 | 70%+ |
| Under 2.5 goals (low-scoring teams) | Combined L5 < 1.8 | 74% |
| Team corners (specific) | L5 > line + 1.0 | 87% |

**Pattern: DATA-BACKED stat markets win. Opinion/gut/context-ignored picks lose.**
