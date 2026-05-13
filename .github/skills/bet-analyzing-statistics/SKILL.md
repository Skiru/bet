---
name: bet-analyzing-statistics
description: "Statistical analysis methodology for betting — §3.0 market ranking protocol, safety score calculation, H2H market-specific validation (§3.0c), three-way cross-check (L10+H2H+L5), bettable market tables per sport, and coach/roster stability checks. Use when performing deep statistical analysis on betting candidates or ranking markets by safety score."
user-invokable: false
---

# Analyzing Betting Statistics

Core statistical methodology for evaluating betting candidates. Every pick must pass through the statistical market ranking protocol before selection.

## PREREQUISITE: Betclic History Data (MANDATORY)

Before ANY statistical analysis, verify that `betting/data/betclic_bets_history.json` was read during §0.2 and `python3 scripts/analyze_betclic_learning.py` was run. Always use the analyzer's live output for current hit rates — never rely on memorized numbers. The analyzer output provides per-market and per-sport hit rates that inform market selection and safety score calculations. Cross-reference §3.0 safety scores with Betclic history rates for the same market type.

## ULTIMATE RULE: BET STATISTICS, NOT OUTCOMES

Statistical markets (corners, fouls, shots, games, sets, points, frames, rounds) are **fundamentally more predictable** than outcome markets (ML, winner, goals):

1. **Accumulation**: Pile up throughout the match (5-8 corners per half regardless of score)
2. **Style-driven**: Pressing team → corners. Physical team → fouls. Structural traits that persist in upsets.
3. **Shock-resistant**: Red card or freak goal destroys ML but barely moves total corners/fouls/shots
4. **Mispriced**: Bookmakers focus liquidity on ML/goals. Peripheral markets get less attention = more edge.

**Every pick must be a statistical market unless no statistical market exists for that event.**

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
9. **DB-first data**: Check DB `analysis_results` table for pre-computed safety scores, then `stats_cache/{sport}/{team}.json` from Beast Mode scan, then `analysis_pool_{date}.json` as aggregated view. Events with `data_quality: FULL` already have safety scores computed from Sofascore REST API + ESPN + unified API client data.

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
| **Baseball *(archived)*** | F5 innings total O/U, Team totals, Total runs O/U, Hits O/U, Strikeouts O/U, Run line |
| **Snooker *(archived)*** | Frame totals O/U, Century breaks O/U, 50+ breaks O/U, Frame handicap |
| **Darts *(archived)*** | 180s O/U, Total legs O/U, Set totals, Checkout % props |
| **Handball *(archived)*** | Half totals O/U, Total goals O/U, Team goals O/U, Suspensions O/U |
| **Esports (CS2) *(archived)*** | Round totals O/U, Map totals O/U, Kill totals, Map handicap |
| **Table Tennis *(archived)*** | Set totals O/U, Total points O/U, Set handicap |
| **MMA *(archived)*** | Total rounds O/U, Method of victory, ITD Y/N |
| **Padel *(archived)*** | Game totals O/U, Set totals O/U, Set handicap |
| **Speedway *(archived)*** | Total points O/U, Team handicap |

## §3.0c H2H Market-Specific Validation (MANDATORY)

For EVERY selected market, you MUST have H2H data for THAT SPECIFIC STAT:

- Corners pick → H2H corner totals between these exact teams (last 3-5 meetings)
- Total games (tennis) → H2H game totals (last 3-5 meetings, surface-filtered)
- Total points (basketball) → H2H combined scoring (last 3-5 meetings)
- Frame totals (snooker) → H2H frame counts (last 3-5 meetings)

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

## Market Hierarchy (ALL SPORTS — ML IS LAST RESORT)

| Sport | Priority order (→ least preferred) |
|-------|-----------------------------------|
| Football | Fouls → Cards → Corners → Shots → Team totals → BTTS → U2.5 → O2.5 → DC/DNB → 1X2 |
| Tennis | Game totals O/U → Set totals → Game HC → Set HC → ML |
| Basketball | Team totals → Quarter totals → Game totals → Spreads → ML |
| Hockey | Period totals → Game totals → Puck line → ML |
| Baseball | F5 totals → Team totals → Game totals → Run line → ML |
| Volleyball | Set score O/U → Point totals → Set totals → Set HC → ML |
| Esports | Round totals → Map totals → Map HC → Kill totals → ML |
| Snooker | Century O/U → Frame totals → Frame HC → ML |
| Darts | 180s O/U → Leg totals → Set totals → ML |
| Handball | Half totals → Game totals → HC → ML |
| Table Tennis | Point totals → Set totals → Set HC → ML |
| MMA | Method → O/U rounds → ITD → ML |
| Padel | Game totals → Set totals → Set HC → ML |
| Speedway | Total pts → HC → Match winner |

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

## Connected Skills

- `bet-applying-sport-protocols` — Sport-specific stat tables, mandatory multi-market calculation templates, bettable market lists per sport
- `bet-navigating-sources` — Stats source chains and specialist sources for statistical data collection
- `bet-evaluating-odds` — Probability engine integration for converting safety scores into EV calculations
- `bet-settling-results` — Historical hit rates from settlement feed back into §3.0 market ranking confidence

## Structured Adapters for Automated Data Extraction

- `scripts/adapters/soccerway_adapter.py` — normalized football fixtures/standings
- `scripts/adapters/tennisexplorer_adapter.py` — normalized tennis results/rankings
- `scripts/adapters/soccerstats_adapter.py` — normalized football statistics

These adapters parse sport-specific web pages into structured JSON data, reducing reliance on manual web-fetch for common stats.

## Data Depth Requirements (v4 Pipeline)

Before computing safety scores, verify data completeness:
- L10: ≥8 actual match data points (not interpolated)
- H2H: ≥3 meetings with per-stat data
- L5: ≥4 actual match data points
- If any dimension has <minimum → flag as PARTIAL quality

## Reasoning Before Ranking

THINK IN THE MIDDLE — when data arrives:
1. Is the data source reliable? (API > deep parse > regex)
2. Are the stat values in expected ranges for this sport/league?
3. Do recent matches suggest a trend change that averages might hide?
4. Is H2H relevant? (same teams, similar context, or very different?)
