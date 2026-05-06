# S3 ANALYST REVIEW — 2026-05-05 v6

**Analyst:** bet-statistician | **Date:** 2026-05-05 | **Bankroll:** 61.91 PLN
**Candidates reviewed:** 15 approved | **Data quality grade:** C+ (systemic issues)

---

## ⚠️ PORTFOLIO-LEVEL ALERTS

### 1. ONE-SIDED DATA ARTIFACT (CRITICAL)
7 of 15 picks have `team_b_avg = 0.0` — safety scores computed from only ONE team's stats. This inflates margins artificially. Every football Cards market uses only the home team's card average, ignoring the opponent. If Betclic lines are for the same team scope, this is fine; if they're match-total lines, the analysis is comparing apples to oranges.

### 2. DUPLICATE EVENT
Picks #4 (Total Goals U67) and #12 (Hannover Goals U31.5) are the SAME MATCH (Hannover-Burgdorf vs Flensburg-Handewitt). Only one can appear in a coupon. Pick #4 is stronger.

### 3. CARDS UNDER CLUSTER
6 of 7 football picks are team-specific Cards Under markets. This concentration suggests a systematic data artifact rather than genuine edge discovery. The pipeline found that single-team card averages are low, making Under lines appear safe.

### 4. RAZOR-THIN MARGINS
Multiple picks have margins < 2%: handball total (0.3%), steals (1.3%), hockey goals (1.4%), rebounds (0.2%). These are essentially coin flips.

### 5. DECLINING TRENDS (L5 < L10)
Picks #10 and #13 (NBA Rebounds Over) both show L5 averages BELOW the line, contradicting the Over direction. Three-way check correctly flags "CONFLICT → DOWNGRADE."

---

## PER-PICK ANALYTICAL REASONING

### Pick 1: Tecnico Universitario Cards U1.5 — MEDIUM confidence
**Safety:** 0.70 | **Gate:** 13/17 | **Margin:** 15.4% | **Hit:** 10/10 L10, 5/5 L5

Tecnico Universitario averages just 1.3 team yellow cards across L10 in Ecuador's Copa — a low-profile tournament where referees tend toward leniency and match intensity is lower than top-flight. The 15.4% margin above line is the strongest in the portfolio, and the 10/10 L10 hit rate is exceptional.

**Concern:** One-sided data (opponent card data = 0.0). If Betclic prices this as match-total cards, the analysis doesn't apply. Also, only 1 source (ESPN-football synthetic). The Ecuadorian league has minimal coverage — this "10/10 consistency" could reflect shallow data ingestion rather than genuine predictability.

**Verdict:** Trustworthy IF Betclic offers team-specific card lines at this level. Verify market scope before placing.

---

### Pick 2: Universitario de Vinto Cards U1.5 — LOW confidence
**Safety:** 0.70 | **Gate:** 13/17 | **Margin:** 15.4% | **Hit:** 10/10 L10, 5/5 L5

IDENTICAL metrics to Pick 1 (same avg 1.3, same margin 1.154, same safety 0.70). Bolivian Primera División. This statistical clone raises a red flag — two teams from two different countries with pixel-perfect identical profiles suggests the pipeline is generating synthetic template data rather than real match stats. If the underlying data is real, Bolivian domestic football is among the most card-light environments globally, supporting the Under.

**Concern:** Clone suspicion. The L10/L5 stability (1.30 → 1.32) is suspiciously smooth for real match data. Recommend verifying raw match-by-match card counts on Flashscore before trusting.

**Verdict:** DOWNGRADE candidate. Too suspicious when paired with Pick 1.

---

### Pick 3: Cruzeiro U17 Cards U2.0 — LOW confidence
**Safety:** 0.63 | **Gate:** 13/17 | **Margin:** 11.1% | **Hit:** L5 5/5

Youth matches (U17) are inherently volatile — referee standards vary dramatically, player discipline is inconsistent, and the sample of matches may include very different competition contexts (league vs cup). The 1.8 avg vs 2.0 line gives only 0.2 margin in absolute card terms — a single additional card breaks the bet.

**Concern:** Copa do Brasil U17 is knockout football — higher intensity than group stage. Youth red card / double-yellow scenarios are more common due to inexperience. Betclic likely doesn't even offer team-specific U17 card markets.

**Verdict:** SKIP unless Betclic has the market. Youth football cards are too volatile for 0.2-card margin.

---

### Pick 4: TSV Hannover-Burgdorf vs Flensburg Total Goals U67 — LOW confidence
**Safety:** 0.60 | **Gate:** 13/17 | **Margin:** 0.3% (66.8 vs 67.0)

German handball Bundesliga top-tier matchup. Combined L10 = 66.8 total goals (Hannover 31.4 + Flensburg 35.4). The margin is 0.2 goals — essentially zero for a sport where totals regularly swing 5-10 goals based on tempo and timeouts. Hit rate is only 3/5 L5 (60%).

**Edge mechanism:** Late-season Bundesliga matches between established teams *can* be more tactical with lower scoring. But Flensburg is an attack-first team averaging 35.4 per game. If they play at their average, Hannover needs to score ≤31.6 — which is right at their average.

**Concern:** This is a coin flip masquerading as an edge. The 0.003 margin is statistically meaningless. Handball lines on Betclic are typically at X.5 (e.g., 66.5 or 67.5), which would radically change the calculus.

**Verdict:** ONLY viable if Betclic line is 68.5 or higher. At 67.0, this is a REJECT.

---

### Pick 5: NY Yankees vs Texas Rangers — Rangers Runs O3.5 — MEDIUM confidence
**Safety:** 0.56 | **Gate:** 12/17 | **Margin:** 5.7% | **Hit:** 7/10 L10, 5/5 L5

Rangers averaging 3.7 runs L10, strong 5/5 L5 uptrend (L5 avg 3.74). Yankees games have been high-scoring (10.1 total runs L10, 17.0 hits). The 5.7% margin above 3.5 is workable for baseball.

**Edge mechanism:** The Rangers' recent form (5/5 over 3.5) suggests an uptick in batting productivity. Yankees at home in early May — warm weather in the Bronx supports higher run environments. However, this is critically dependent on the starting pitcher matchup, which we don't have.

**Concern:** Missing starting pitcher data is the biggest gap. If Yankees start an ace (Cole/Rodón), Rangers O3.5 becomes much harder. If it's a bullpen game or weaker starter, the edge strengthens. Also, 3 H2H meetings exist but no H2H-specific run data.

**Verdict:** BET-WORTHY if Yankees don't start an ace. Check lineups 1-2 hours before first pitch.

---

### Pick 6: Rosario Central Cards U2.5 — Copa Sudamericana — MEDIUM confidence
**Safety:** 0.56 | **Gate:** 12/17 | **Margin:** 8.7% | **Hit:** 8/10 L10, 5/5 L5

Rosario Central averages 2.3 team cards in recent matches — well under the 2.5 line with an 8.7% margin. The 8/10 L10 and 5/5 L5 consistency is strong. Copa Sudamericana group stage (not knockout) reduces the intensity factor somewhat.

**Edge mechanism:** Rosario Central may play a controlled, possession-heavy style (51% possession in Copa context) that generates fewer desperate fouls. Argentine teams in continental competition often focus on tactical discipline.

**Concern:** South American cup matches with international refs (CONMEBOL appointments) can be card-heavier than domestic matches. Playing against Paraguayan opposition (Libertad) who may be physical. One-sided data (Libertad card stats missing).

**Verdict:** Viable pick. The 8.7% margin provides reasonable cushion. Verify Betclic has team-specific card market.

---

### Pick 7: Independiente Petrolero Cards O2.0 — Copa Libertadores — MEDIUM-HIGH confidence ⭐
**Safety:** 0.56 | **Gate:** 12/17 | **Margin:** 10% | **Hit:** 5/5 L5

This is the one OVER cards pick and has the strongest analytical edge mechanism in the portfolio. Petrolero (Bolivia) playing in Copa Libertadores against Caracas FC — a classic underdog-in-continental-competition scenario.

**Edge mechanism:** Bolivian teams in Libertadores are typically outclassed technically, leading to more tactical fouls, time-wasting challenges, and frustrated lunges as the match progresses. Altitude (Sucre at ~2,800m) may not apply if playing away. Average 2.2 team cards with a clean 10% margin over 2.0 line suggests this is a structural pattern, not noise.

**Concern:** If Petrolero plays at home in altitude, Caracas may struggle physically and generate fewer Petrolero fouls (since Petrolero dominates). The edge depends on match context (home vs away).

**Verdict:** STRONGEST football pick. The structural rationale (underdog cards accumulation) is a proven pattern in continental competitions.

---

### Pick 8: River Plate Res. vs Racing Club Res. — Racing Cards U3.0 — LOW confidence
**Safety:** 0.56 | **Gate:** 12/17 | **Margin:** 9.1% | **Hit:** 8/10 L10, 5/5 L5

Racing Club Reserves average 2.75 yellow cards per match (total match cards = 4.9). Line 3.0 gives 9.1% margin on paper.

**Edge mechanism:** Argentine reserve matches are often lower intensity with younger players, and referees may be more lenient. 16 markets evaluated — the richest data set among football picks.

**Concern:** Racing's AWAY yellow cards average 2.8 (vs 2.1 home). This is an away match for Racing, so the relevant average is closer to 2.8, slashing the margin to just 7%. Also, River Plate Reserves have 2.75 cards and 5.5 total match cards — these are not disciplined teams. Reserve derbies between River and Racing can be feisty.

**Verdict:** BORDERLINE. The away-specific stat (2.8) erodes the margin. The derby context (Buenos Aires rivalry) adds card risk. Proceed with caution.

---

### Pick 9: Detroit Pistons vs Cleveland Cavaliers — Total Steals O16.5 — LOW confidence
**Safety:** 0.50 | **Gate:** 13/17 | **Margin:** 1.3% | **Hit:** 5/7 L10, 4/5 L5

Combined steals: Detroit 7.57 + Cleveland 9.14 = 16.71 L10. Line 16.5 = 0.21 steal margin. L5 improving to 17.6.

**Edge mechanism:** Cleveland is one of the NBA's best defensive teams (9.14 steals/game). Pistons' younger roster turns the ball over frequently, generating steal opportunities for Cleveland. The L5 uptick to 17.6 suggests increasing defensive intensity as playoffs approach.

**Concern:** Steals are the most volatile counting stat in basketball. A quiet defensive game (fewer turnovers, deliberate halfcourt sets) easily drops below 16.5. The 1.3% margin is essentially noise. Individual player availability (Garland, Mitchell, Mobley for CLE) heavily impacts steal totals.

**Verdict:** MARGINAL. The analytical logic (Cleveland's steal-generating defense vs Detroit's turnover-prone offense) is sound, but the margin is too thin for confident placement. Only bet at odds ≥ 1.90.

---

### Pick 10: NY Knicks vs Philadelphia 76ers — Total Rebounds O91.0 — VERY LOW confidence ⚠️
**Safety:** 0.50 | **Gate:** 12/17 | **Margin:** 0.2% | **Hit:** 5/7 L10, 3/5 L5

L10 avg = 91.14, L5 avg = 90.2. The L5 average is BELOW the 91.0 line and declining. Three-way check correctly returns "1/2 CONFLICT → DOWNGRADE."

**Edge mechanism:** None convincing. The Knicks' L5 rebounds dropped to 79.0 (from 80.43 L10), and the combined L5 = 90.2 is under the line. This is a bet against the recent trend.

**Concern:** Flagged conflicting three-way check. Risk tier = HR. The declining L5 suggests game pace or personnel changes are reducing rebound opportunities. Embiid's availability for 76ers is a massive variable.

**Verdict:** REJECT for coupon inclusion. Conflicting trend makes this a negative-edge bet.

---

### Pick 11: Sparta Rotterdam U19 vs Feyenoord U19 — SOT U5.5 — LOW confidence
**Safety:** 0.49 | **Gate:** 12/17 | **Margin:** 0.0% (avg = line) | **Hit:** L5 4/5

Sparta U19 averages exactly 5.5 shots on target L10 — right on the line. The L5 decline to 4.8 (↘) is the only argument for Under.

**Edge mechanism:** Declining form (fewer shot opportunities) could continue against a strong Feyenoord U19 defense. Youth teams can be inconsistent in shot quality.

**Concern:** Zero margin on L10. This is a Rotterdam derby — Feyenoord-Sparta matches are always intense regardless of age group, with likely more shots than average. One-sided data (only Sparta's shots). Risk tier = HR, upset risk = HIGH (0.65).

**Verdict:** REJECT. Zero-margin bets are not edges. Derby context likely increases shots.

---

### Pick 12: Hannover-Burgdorf Goals U31.5 — VERY LOW confidence ⚠️
**Safety:** 0.48 | **Gate:** 12/17 | **Margin:** 0.3% | **Only 1 market evaluated**

DUPLICATE EVENT with Pick #4. Hannover avg 31.4, line 31.5. Only 1 market in the analysis — the most limited evaluation in the portfolio.

**Verdict:** REJECT — duplicate event, 1-market analysis, zero margin. Use Pick #4 if this match is selected.

---

### Pick 13: Spurs vs Timberwolves — Total Rebounds O83.0 — VERY LOW confidence ⚠️
**Safety:** 0.47 | **Gate:** 12/17 | **Margin:** 0.2% | **Hit:** 4/6 L10, 3/5 L5

L10 avg = 83.17, L5 avg = 82.2. Same problem as Pick 10 — L5 trend declining BELOW the line. Three-way check: "1/2 CONFLICT → DOWNGRADE."

**Edge mechanism:** None. The trend is against the pick direction.

**Concern:** Timberwolves' L5 rebounds dropped to 84.8 → but combined L5 = 82.2. If both teams are trending down in rebounds, the Over at 83.0 is a losing bet.

**Verdict:** REJECT for coupon. Same issue as Pick 10 — declining trend contradicts OVER direction.

---

### Pick 14: Cristian Garin vs Jan Choinski — Total Sets O3.0 — VERY LOW confidence ⚠️
**Safety:** 0.42 | **Gate:** 12/17 | **Margin:** 7.3% | **Hit:** 3/5

L10 avg = 3.22 sets per match (i.e., 3-set matches more common). But Garin has only 1 match in the L10 data — making this "L10 average" essentially a 1-match sample.

**Edge mechanism:** O3.0 sets = match goes to 3 sets. Garin (former top-20, clay specialist, currently ranked ~100) vs Choinski (lower-ranked, inconsistent). IF Garin is in poor form, he drops sets. If fit, he wins in straights. The 3/5 hit rate on O3.0 is mediocre.

**Concern:** 1-match sample for Garin is statistically meaningless. No surface data. No H2H. No form context (injury comeback? clay season?). Safety 0.42 is very low.

**Verdict:** REJECT without additional live data. Cannot trust 1-match samples for tennis predictions.

---

### Pick 15: Vegas Golden Knights vs Anaheim Ducks — Total Goals O7.0 — VERY LOW confidence ⚠️
**Safety:** 0.38 | **Gate:** 13/17 | **Margin:** 1.4% | **Hit:** 5/10 L10, 3/5 L5

Combined L10 = 7.1 goals. Line = 7.0. Hit rate is 50% on L10 — literally a coin flip. Safety score 0.38 is the lowest in the portfolio.

**Edge mechanism:** VGK at home in T-Mobile Arena tends to play high-tempo. But Anaheim (rebuilding team) can play defensively against stronger opponents, lowering totals. Data shows Anaheim's games average 7.29 total goals, which is promising but not conclusive at 50% hit rate.

**Concern:** 50% L10 hit rate means zero edge. Safety 0.38 is below the minimum threshold. NHL playoff implications may change team approach entirely.

**Verdict:** REJECT. 50% hit rate = no edge. Lowest safety in portfolio.

---

## TOP 5 PICKS (Ranked by Analytical Edge Strength)

| Rank | Pick | Market | Why |
|------|------|--------|-----|
| 1 | #7 Independiente Petrolero | Cards O2.0 | Structural underdog-in-Libertadores edge, 10% margin, logical mechanism |
| 2 | #5 NY Yankees vs Texas Rangers | Rangers Runs O3.5 | 5.7% margin, strong L5 trend, high-scoring series environment |
| 3 | #6 Rosario Central | Cards U2.5 | 8.7% margin, 8/10 L10, good form data quality |
| 4 | #1 Tecnico Universitario | Cards U1.5 | Highest safety (0.70), 10/10 L10 (if data real), 15.4% margin |
| 5 | #9 Detroit vs Cleveland | Total Steals O16.5 | Sound defensive logic, improving L5, but thin margin |

---

## PICKS RECOMMENDED FOR REJECTION

| Pick | Market | Reason |
|------|--------|--------|
| #10 | Knicks/76ers Rebounds O91 | L5 declining BELOW line, three-way CONFLICT |
| #12 | Hannover Goals U31.5 | Duplicate event with #4, 1-market analysis |
| #13 | Spurs/Wolves Rebounds O83 | L5 declining BELOW line, three-way CONFLICT |
| #14 | Garin vs Choinski Sets O3 | 1-match sample for Garin, safety 0.42 |
| #15 | VGK vs Ducks Goals O7 | 50% hit rate = no edge, safety 0.38 |
| #11 | Sparta U19 SOT U5.5 | Zero margin (avg = line), derby inflator |

---

## ARSENAL vs ATLETICO MADRID (Champions League SF)

Currently in EXTENDED pool (gate 11/17, safety 0.49). The best computed market is Arsenal Corners U5.5, but:
- **L10 = 5.3** vs **L5 = 6.6** — sharply RISING trend (three-way CONFLICT)
- UCL semifinal at home = maximum intensity = MORE corners expected, not fewer
- This market is directionally wrong given the context

**Better approach for this match:** Look for Total Fouls Over, Total Cards Over, or BTTS markets. Champions League semifinals are physical, tactical affairs. Atletico Madrid in particular generates high card counts (Simeone's system). However, without Atletico-specific stat data in the pipeline (team_b_avg = 0.0), no market can be properly computed.

**Recommendation:** This match deserves manual analysis outside the pipeline. The user should check Betclic for Arsenal/Atletico card and foul lines, then apply the `hit_rate × odds > 1.0` stats-first formula manually.

---

## SUMMARY STATISTICS

| Metric | Value |
|--------|-------|
| Picks reviewed | 15 |
| Recommended BET | 5 (#1, #5, #6, #7, #9) |
| Recommended REJECT | 6 (#10, #11, #12, #13, #14, #15) |
| Borderline/conditional | 4 (#2, #3, #4, #8) |
| Average safety (top 5) | 0.564 |
| Average safety (rejects) | 0.44 |
| H2H blind | 15/15 (100%) |
| One-sided data | 7/15 (47%) |
| Duplicate events | 1 pair (#4 + #12) |
| Three-way conflicts | 3 picks (#10, #13, Arsenal extended) |
