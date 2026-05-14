---
name: bet-analyzing-statistics
description: "Statistical analysis methodology for betting — §3.0 market ranking protocol, safety score calculation, H2H market-specific validation (§3.0c), three-way cross-check (L10+H2H+L5), bettable market tables per sport, and coach/roster stability checks. Use when performing deep statistical analysis on betting candidates or ranking markets by safety score."
user-invokable: false
---

# Analyzing Betting Statistics

Core statistical methodology for evaluating betting candidates. Every pick must pass through the statistical market ranking protocol before selection.

## PREREQUISITE: Betclic History Data

Before analysis, verify `betting/data/betclic_bets_history.json` was read during §0.2 and `python3 scripts/analyze_betclic_learning.py` was run. Use analyzer's live output for current hit rates — never memorized numbers. Cross-reference §3.0 safety scores with Betclic history rates.

## Core Principle: Statistics > Outcomes

| Why statistical markets win | Example |
|---|---|
| **Accumulate** regardless of score | 5-8 corners/half even in 0-0 |
| **Style-driven** — persist in upsets | Pressing team → corners, physical → fouls |
| **Shock-resistant** | Red card destroys ML, barely moves fouls |
| **Mispriced** — less bookmaker liquidity | Peripheral markets = more edge |

**Every pick must be a statistical market unless none exists for that event.**

## §3.0 Statistical Market Ranking Protocol (MANDATORY — NEVER SKIP)

For EVERY candidate, BEFORE selecting a market:

1. **List ALL bettable statistical markets** for that sport (see table below)
2. **For EACH available market**, collect:
   - Team/player L10 average
   - H2H average for that SPECIFIC stat (last 5 meetings minimum)
   - Recent form L5 average
   - Bookmaker line
   - Hit rate (how often L10 + H2H covered that line)
3. **Calculate SAFETY SCORE** per market: `safety = min(hit_rate_L10, hit_rate_H2H)`
   - Higher = safer. Tiebreaker: avg margin vs line (Over: avg/line, Under: line/avg — bigger = more margin)
   - H2H-BLIND penalty: if no H2H data exists, safety = `hit_rate_L10 × 0.7` (30% penalty)
4. **Rank all markets** by safety score. Pick the TOP market — not default/favorite.
5. **CONFLICT CHECK**: H2H avg and L10 avg disagree by >20% → FLAG. L5 as tiebreaker. L5 also conflicts → DOWNGRADE or SKIP.
6. **PRESENT the ranking table** in analysis. Show WHY chosen market beat alternatives.
7. **THREE-WAY CHECK per market**: Every ranked market now carries its own three-way cross-check (L10 + H2H + L5 alignment). When the user selects a non-top market, the three-way data is immediately available.
8. **Deterministic calculation**: Always use `python3 scripts/compute_safety_scores.py stats_input.json` — never manually compute safety scores. The script handles the 0.7 H2H-blind penalty, margin calculation, ranking, and per-market three-way checks.
9. **DB-first data**: Check DB `analysis_results` table for pre-computed safety scores, then `stats_cache/{sport}/{team}.json` from scan, then `analysis_pool_{date}.json` as aggregated view. Events with `data_quality: FULL` already have safety scores computed from Flashscore + ESPN + unified API client data.

### Ranking Table Template

```
| Market           | TeamA avg | TeamB avg | H2H avg | Line | Hit L10 | Hit H2H | Safety |
|------------------|-----------|-----------|---------|------|---------|---------|--------|
| Fouls O/U X.5    |           |           |         |      |         |         |        |
| Cards O/U X.5    |           |           |         |      |         |         |        |
| Corners O/U X.5  |           |           |         |      |         |         |        |
| Shots O/U X.5    |           |           |         |      |         |         |        |
| ...              |           |           |         |      |         |         |        |
```

## §3.0b Bettable Statistical Markets by Sport

| Sport | Statistical Markets (ranked by typical reliability) |
|-------|-----------------------------------------------------|
| **Football** | Fouls O/U, Cards O/U, Corners team O/U, Corners total O/U, Shots O/U, SOT O/U, Throw-ins O/U, Goal kicks O/U, Offsides O/U, Team goals O/U, Total goals O/U, BTTS |
| **Tennis** | Total games O/U, Sets O/U, Game handicap, Set handicap, Tiebreaks O/U, Aces O/U, Double faults O/U |
| **Basketball** | Team points O/U, Quarter totals, Half totals, Total points O/U, Rebounds O/U, Assists O/U, 3-pointers O/U, Spread |
| **Volleyball** | Total sets O/U, Total points O/U, Set handicap, Points per set O/U |
| **Hockey** | Period totals O/U, Total goals O/U, Shots O/U, Power play goals O/U, Puck line |

## §3.0c H2H Market-Specific Validation (MANDATORY)

For EVERY selected market, you MUST have H2H data for THAT SPECIFIC STAT:

- Corners pick → H2H corner totals between these exact teams (last 3-5 meetings)
- Total games (tennis) → H2H game totals (last 3-5 meetings, surface-filtered)
- Total points (basketball) → H2H combined scoring (last 3-5 meetings)
- Period totals (hockey) → H2H period scoring (last 3-5 meetings)

**If H2H data for the SPECIFIC stat is unavailable:**
1. Mark pick as `H2H-STAT-BLIND`
2. Apply −0.5 confidence penalty
3. Pick CANNOT be in a LR coupon
4. Increase weight on L5 recent form as substitute

## Three-Way Cross-Check (MANDATORY for every pick)

```
L10 AVERAGE → [value] → hit rate vs line: [X/10]
H2H AVERAGE → [value] → hit rate vs line: [X/5]
L5 RECENT  → [value] → trend: [UP/DOWN/STABLE]
```

**ALL THREE must support the pick direction.**
- 2/3 conflict → DOWNGRADE
- 3/3 conflict → REJECT

## Coach/Roster Stability Check (MANDATORY)

For EVERY candidate:
1. **Coach change in last 5 matches?** Check TransferMarkt. New coach = first 5 games unreliable.
2. **Major transfers, loan returns, or squad changes in last 14 days?** Stats from previous games may not apply.
3. If either → flag and increase uncertainty margin.

## Market Hierarchy (5 Core Sports)

| Sport | Priority order (→ least preferred) |
|-------|-----------------------------------|
| Football | Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 |
| Tennis | Game totals O/U → Set totals → Game HC → Set HC → ML |
| Basketball | Team totals → Quarter totals → Game totals → Spreads → ML |
| Hockey | Period totals → Game totals → Puck line → ML |
| Volleyball | Set score O/U → Point totals → Set totals → Set HC → ML |

## §3.0-PROB Probability Engine (MANDATORY after safety scores)

After ranking markets by safety score, run the probability engine on each ranked market to get TRUE MATHEMATICAL PROBABILITY:

### Methodology

**Poisson Distribution** (default for count data):
- ALL sports count markets are Poisson-distributed: corners, fouls, cards, shots, games, sets, points, frames, rounds, legs, 180s, aces
- λ (expected count) = weighted average: **40% × L5_avg + 35% × L10_avg + 25% × H2H_avg**
- Recency weighting rationale: L5 captures current tactical setup and squad fitness, L10 provides stable baseline, H2H captures matchup-specific tendencies
- P(Over X.5) = 1 - CDF(X, λ) where CDF is cumulative Poisson distribution
- P(Under X.5) = CDF(X, λ)

**Negative Binomial** (auto-selected when overdispersed):
- When variance/mean > 1.5 across the sample → data is overdispersed (clustered events)
- Common for: goals, runs, power play goals — events that come in bursts
- Uses moment-matching to estimate r (failures) and p (success probability)
- P(Over X) = 1 - NegBin_CDF(X, r, p)

**Confidence Intervals** (90% bootstrap):
- 1000 resamples from L10+L5+H2H combined values
- For each resample: compute λ → compute P(hit)
- Report 5th and 95th percentile → 90% CI

### Output per market:
```
| Market | Safety | P(hit) | Fair Odds | Min EV>0 | λ | Model | CI 90% |
```

- **P(hit)**: True mathematical probability of the market hitting
- **Fair odds**: 1 / P(hit) — minimum odds needed for break-even
- **Min EV>0**: Fair odds + margin — minimum Betclic odds for positive EV
- **λ**: Expected count (weighted average)
- **Model**: POISSON or NEGBIN
- **CI 90%**: [lower%, upper%] confidence interval

### Usage
```bash
# Standalone calculation:
python3 scripts/probability_engine.py --line 9.5 --direction OVER --values "11,8,13,9,10,12,7,11,9,5"

# Integrated in pipeline (automatic):
python3 scripts/deep_stats_report.py --date YYYY-MM-DD
# → calls enrich_ranking_with_probabilities() after safety scores

# Python import:
from probability_engine import compute_probability, compute_ev
result = compute_probability(9.5, "OVER", l10, l5, h2h)
prob, fair_odds = result["probability"], result["fair_odds"]
ev = compute_ev(prob, betclic_odds)
```

### Decision Rules
- **P(hit) > 75% AND safety ≥ 0.70** → Strong candidate for LR coupon
- **P(hit) 60-75% AND safety ≥ 0.60** → Candidate for MS coupon
- **P(hit) < 50%** → Needs exceptionally high odds for positive EV (fair odds > 2.00)
- **CI width > 30%** → Low confidence — insufficient data, flag for user
- **NEGBIN model selected** → Data is overdispersed, expect higher variance

## Data Depth Requirements

| Dimension | Minimum | Below minimum |
|-----------|---------|---------------|
| L10 | ≥8 actual data points | Flag PARTIAL quality |
| H2H | ≥3 meetings with per-stat data | Apply H2H-BLIND penalty (×0.7) |
| L5 | ≥4 actual data points | Flag PARTIAL quality |

## DB Queries for Safety Scores

```sql
-- Load pre-computed safety scores
SELECT best_market_name, best_safety_score, ranking_json, three_way_check_json
FROM analysis_results WHERE fixture_id = ? AND betting_date = ?;

-- Load team form for safety calculation
SELECT stat_key, l10_values, l5_values, l10_avg, l5_avg, h2h_values, trend
FROM team_form WHERE team_id = ? AND sport_id = ?;

-- Save analysis result
-- Use: AnalysisResultRepo(conn).save(AnalysisResult(...))
```

## Connected Skills

| Skill | Load for |
|-------|----------|
| `bet-applying-sport-protocols` | Per-sport stat tables (§3.1-§3.5), upset risk thresholds, red flag checklists |
| `bet-navigating-sources` | Stats source fallback chains, specialist sources per sport |
| `bet-evaluating-odds` | EV formula, Kelly criterion — converts safety scores into stake recommendations |
| `bet-settling-results` | Historical hit rates feed back into safety score confidence |
