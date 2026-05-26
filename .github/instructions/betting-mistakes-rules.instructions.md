---
description: "Hard reject rules derived from settled losses. MANDATORY during S3/S5/S7/S8. These rules apply at COUPON CONSTRUCTION stage — candidates still appear in the matrix (R3 compliance) but are FLAGGED/REJECTED when building final coupons."
---

# Betting Mistakes & Hard Rules (MANDATORY READ)

> **When to read:** Every agent during S3 (deep stats), S5 (odds evaluation), S7 (gate), and S8 (coupon building).
> **R3 Compliance:** These rules do NOT auto-reject from the pipeline matrix. Candidates ALWAYS appear in the matrix and Extended Pool. These rules apply when BUILDING COUPONS — the coupon_builder and bet-builder agent must enforce them. In the gate, they produce FLAGS (not auto-rejections) so the user can see WHY a pick is risky.
> **Source:** Settled results from `betting/journal/learning-log.md` and `betting/journal/{date}-pipeline-errors.md`.
> **Last updated:** 2026-05-26 after 25.05 session (breakeven: 1W/5L, +0.00 PLN). New rules: TENNIS_ML_AGE, TENNIS_GAMES_002, BASKETBALL_PLAYOFF, ICELAND_001, CORNERS_CONTRADICTION_001.

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

## 📋 Quick Decision Matrix for Agents

See **Updated Quick Decision Matrix** below (includes all original + new rules from 2026-05-26).

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

---

## ⛔ NEW RULES — Added 2026-05-26 (from 25.05.2026 settlement)

### TENNIS_ML_AGE_001 — Aging Players in Grand Slam 5-Set Matches

**NEVER** bet ML on players aged **≥35** in Grand Slam (5-set) matches when:
1. Opponent is **<30 years old** (fitness advantage in 5th set)
2. Opponent is playing **at home** (crowd energy in deciding set)
3. Odds are **>1.60** (implied <63% — bookmaker already prices in the risk)
4. Player has shown **physical decline** in recent matches (retirements, 5-setters lost)

**Specific ban: Monfils ML in Grand Slams** — at 39, he CANNOT sustain 5-set intensity.

Evidence: 2026-05-25 Monfils @1.81 vs Hugo Gaston (French, home crowd at RG). Won first 2 sets 6-2, 6-3 then COLLAPSED: 3-6, 2-6, 0-6 in last 3 sets. Classic aging pattern — dominates early, fades physically.

---

### TENNIS_ML_COMBO_001 — Tennis Match Winners in Large AKO (≥4 legs)

Tennis match winner picks in combos with **≥4 legs** require:
1. **Max 2 ML picks** per combo (each adds 15-20% failure probability)
2. Each ML pick must have odds **≤1.30** (implied ≥77%)
3. If ANY ML pick has odds >1.50 → that pick CANNOT be in a ≥4-leg combo
4. **WTA is more volatile than ATP** — apply extra caution for WTA ML in combos

**Math:** Two "80% picks" = 64% combined probability. Three = 51%. Four = 41%. You're BELOW coinflip with 4 "safe" favorites!

Evidence: 2026-05-25 AKO(5) with Fernandez @1.24 + Monfils @1.81 — both lost. The combo had combined implied prob of only 7.15⁻¹ = 14%. You need ALL 5 to hit.

---

### TENNIS_GAMES_002 — Over Total Games vs Dominant Favorites

Over total games **REJECT** when:
1. One player is ranked **≥30 spots higher** than opponent
2. Favorite's recent sets have been **dominant** (avg <4 games conceded per set in L5)
3. Ranking gap **≥50 spots** → REJECT on ANY surface (including clay). Gap 30-49 on hard/grass → REJECT. Gap 30-49 on clay → CAUTION (clay adds ~2 games but cannot save a mismatch)
4. Odds **>1.50** for Over = bookmaker sees dominant favorite scenario as likely

**Key insight:** When a top player wins 3-1 in sets, total games are often LOW because 3 of 4 sets are one-sided (e.g., 6-3, 6-3, 2-6, 6-3 = only 35 games). Clay provides partial protection but NOT for massive ranking gaps.

Evidence: 2026-05-25 Munar vs Hurkacz O36.5 @1.55. Hurkacz won 6-3, 6-3, 2-6, 6-3 = 35 games. Three dominant sets at 9 games each. Munar could only compete in one set.

---

### BASKETBALL_PLAYOFF_001 — Playoff Over/Under Points Adjustment

For **playoff** basketball games (any league):
1. Apply **-5 to -8 points** to regular season combined averages (defense intensifies)
2. If line is within **3 points** of adjusted average → **SKIP** (edge too thin)
3. Series game number matters: Game 1-2 = -5, Game 3+ = -8 (teams learn each other's plays)
4. **NEVER** bet Over in playoff with regular-season data without adjustment

Evidence: 2026-05-25 Brescia vs Trieste O165.5 @1.84 (Italian basketball playoff). Result: 165 total — MISSED BY 0.5 POINTS. Playoff defense made the difference. No adjustment was applied.

---

### ICELAND_GOALS_001 — Icelandic Football Over Goals

**NEVER** bet Over 2.5 goals in Icelandic football (Úrvalsdeild, 1. deild, cups) unless:
1. Combined L5 goals for BOTH teams exceeds **3.5** (not just 2.5!)
2. Match is NOT a cup game (K. = Keppni = Cup → extra conservative)
3. Both teams are from the **same division** (cross-division = unpredictable)
4. Odds are **≤1.40** (bookmaker must strongly agree)

**Structural fact:** Icelandic football averages ~2.1 goals/game. Weather (cold, wind), short season, and defensive tactics make Over 2.5 a LOSING proposition by default.

Evidence: 2026-05-25 Throttur Reykjavik K. vs Stjarnan K. O2.5 @1.54. Result: 0-1 (1 goal total). Icelandic cup match between teams from different tiers. Only 1 goal scored.

---

### CORNERS_CONTRADICTION_001 — Contradictory Picks in Same Match

**HARD RULE:** You cannot bet UNDER team corners for **BOTH teams** in the same match across different coupons:
1. If Team A dominates → Team B chases → Team B gets MORE corners
2. If the match is close → BOTH teams get corners
3. The ONLY scenario where both teams get few corners is a dead, boring 0-0 with no attacks

**Before placing any team corner UNDER:** Check if the OTHER team from same match already has a pick. If yes:
- Same direction (both UNDER) → REJECT the second one
- Opposite direction (one UNDER, one OVER) → OK (they complement each other)

Evidence: 2026-05-25 Ham-Kam U4.5 corners WON ✅ but Lillestrøm U4.5 corners LOST ❌ in the SAME match. Ham-Kam won 2-0, dominating → Lillestrøm was chasing and taking corners.

---

### PRZEWAGA_AWAY_001 — "Win by 2+ OR Win" Market for Away Teams

"Przewaga dwoma bramkami lub wygrana" (Double Chance Win variant) for **away teams**:
1. Odds MUST be **≤1.43** (existing LOWER_LEAGUE_001 rule was IGNORED)
2. **NEVER** in relegation playoffs/decisive matches (home team fights desperately)
3. **NEVER** when home team has scored in **>80% of home L5 games** (will at least get 1 goal)
4. This market requires winning OR winning by 2+ — a draw = LOSS. It's riskier than ML!

**Key:** This market is effectively just ML (moneyline) — "win by 2+ OR win" = "win." A draw = LOSS. Odds @2.00 for an away team in a relegation playoff = pure coin flip with ZERO edge. If you wouldn't bet standard ML at those odds, don't bet this.

Evidence: 2026-05-25 Wolfsburg "Przewaga 2+" @2.00 AWAY at Paderborn (Bundesliga relegation playoff). Paderborn won 2-1. Rule LOWER_LEAGUE_001 explicitly says max odds 1.43 for this market. THE RULE WAS VIOLATED.

---

## 📋 Updated Quick Decision Matrix

| Situation | Action |
|-----------|--------|
| Tennis ML player ≥35 in Grand Slam | REJECT |
| Tennis ML in combo ≥4 legs with odds >1.50 | REJECT |
| Tennis Over games, ranking gap >30 spots | REJECT |
| Basketball playoff Over, line within 3 of adjusted avg | REJECT |
| Icelandic football Over 2.5 | REJECT (unless combined L5 > 3.5) |
| Both teams UNDER corners in same match | REJECT second pick |
| Przewaga/win by 2+ away, odds >1.43 | REJECT |
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
