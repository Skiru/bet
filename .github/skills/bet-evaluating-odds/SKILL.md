---
name: bet-evaluating-odds
description: "Odds evaluation methodology — EV calculation, Kelly 1/4 criterion, price gap analysis, drift detection (>8% mandatory re-eval), American odds conversion, line movement interpretation, and market performance tracking from picks-ledger. Use when comparing odds across bookmakers, calculating expected value, or determining stake sizes."
user-invokable: false
---

# Evaluating Betting Odds

Precise methodology for odds comparison, value detection, and stake calculation. Every approved pick must have EV > 0 — no exceptions.

## EV Calculation

```
EV = (true_probability × betclic_odds) - 1
```

- Must be > 0 for approval. EV ≤ 0 → REJECT.
- true_probability sources (in priority order):
  1. **Poisson/NegBin probability engine** (`scripts/probability_engine.py`) — for ALL count-based stat markets (corners, fouls, cards, shots, games, sets, points, frames, rounds, legs, 180s). Returns mathematically rigorous P(hit) with 90% confidence interval. PRIMARY source.
  2. Pinnacle implied probability (strip margin) — cross-validation for stat markets, PRIMARY for outcome markets (ML, DC, DNB)
  3. Average of sharp bookmakers (Pinnacle, Betfair, bet365)
  4. Statistical model estimate from deep analysis data
  5. Tipster consensus

## Price Gap Analysis

```
price_gap_pct = 100 × ((betclic_odds / market_best_odds) - 1)
```

| Risk Tier | Reject Threshold |
|-----------|-----------------|
| Low-risk | < −3% |
| Higher-risk | < −5% |

## Drift Detection

```
drift_pct = 100 × ((current_odds / analysis_odds) - 1)
```

| Drift | Action |
|-------|--------|
| ≤3% | Normal — no action |
| 3-8% | Note direction, check for news |
| **>8%** | **MANDATORY RE-EVALUATION** — check injuries, lineups, sharp money. No explanation → SKIP. |

- For OVER markets: drift > +8% = market thinks LESS likely → investigate
- For UNDER/ML: drift > +8% = market respects opponent more → investigate

## Kelly 1/4 Criterion

```
kelly_fraction = (true_prob × odds - 1) / (odds - 1)
suggested_stake = bankroll × kelly_fraction / 4
```

If Kelly ≤ 0 → NO BET (no edge exists).

## Staking Limits

| Coupon Type | Max Stake |
|-------------|-----------|
| Low-risk (LR) | 3.00 PLN |
| Higher-risk (HR) | 2.00 PLN |

Total suggested exposure may exceed daily budget — user decides which coupons to place.

## Probability Engine Integration

For count-based statistical markets, the probability engine provides the most accurate true probability:

```bash
# Read from S3 output (already computed):
# Look for P(hit), Fair Odds, λ columns in the ranking table

# Or compute directly:
python3 scripts/probability_engine.py --line 9.5 --direction OVER --values "11,8,13,9,10"

# Python:
from probability_engine import compute_probability, compute_ev, compute_kelly_quarter
result = compute_probability(line=9.5, direction="OVER", l10_values=[...], l5_values=[...], h2h_values=[...])
prob, fair_odds = result["probability"], result["fair_odds"]
ev = compute_ev(prob, betclic_odds)
stake = compute_kelly_quarter(prob, betclic_odds, bankroll)
```

**Cross-validation with Pinnacle:**
- If |Poisson_prob - Pinnacle_prob| < 5% → high confidence, use Poisson
- If |Poisson_prob - Pinnacle_prob| 5-10% → moderate confidence, average the two
- If |Poisson_prob - Pinnacle_prob| > 10% → investigate: check for news, injuries, sharp money
- CI width > 25% → low data confidence, weight Pinnacle higher

**Min Betclic Odds = 1 / P(hit)** — the fair odds. Betclic must offer ABOVE this for EV > 0.

## American Odds Conversion

For SBR, ESPN, ScoresAndOdds:
- Positive +X → decimal = `1 + X/100` (e.g., +150 = 2.50)
- Negative −X → decimal = `1 + 100/X` (e.g., −150 = 1.667)

## Line Movement Interpretation

| Pattern | Meaning | Action |
|---------|---------|--------|
| Steam move (sharp books move first, others follow) | Sharp money detected | Follow if aligned with thesis |
| Reverse line movement (RLM) | Public on one side, line moves opposite | Follow sharp money direction |
| Opening line = current | No significant action | Neutral signal |

## Market Performance Tracker

Before picking any market type, check historical hit rate in `picks-ledger.csv`:

| Hit Rate | Action |
|----------|--------|
| ≥50% on 10+ picks | Normal — proceed |
| 40-49% on 10+ picks | ⚠️ FLAG for user — show rate in report |
| <40% on 10+ picks | ⚠️ FLAG for user — show rate in report |
| <30% on 10+ picks | ⚠️ FLAG for user — show rate prominently in report |

**ADVISORY RULE:** All historical hit rate data is shown to the user for their decision-making. NEVER auto-reject, auto-downgrade confidence, or auto-exclude any market based on hit rates. Full analysis (S3-S7) is mandatory for every candidate regardless of historical performance.

## Multi-Source Odds Protocol

For EACH candidate, get odds from ≥2 sources:

| Sport Region | Source 1 | Source 2 | Source 3 |
|-------------|----------|----------|----------|
| EU sports | BetExplorer | OddsPortal | The-Odds-API |
| US sports (NHL/NBA/MLB) | SBR | ESPN Odds | ScoresAndOdds |

Cross-validate: if odds differ >5% between sources → investigate which is stale.

## The-Odds-API Integration

- Script: `python3 scripts/fetch_odds_api.py`
- Output: `betting/data/odds_api_snapshot.json` + `odds_api_summary.csv`
- Quota: 30 credits/full scan, 500/month free (~16 scans/month)
- Use in S1 (cross-validation) and S5 (market-best prices)

## Multi-Source Odds Aggregation (RECOMMENDED)

- Script: `python3 scripts/fetch_odds_multi.py --date YYYY-MM-DD`
- Output: `betting/data/odds_multi_sources.json` (provenance log with source attribution)
- Sources: The-Odds-API + API-Football + OddsPortal + BetExplorer + Betclic (5 sources)
- Uses `SPORT_SOURCE_PRIORITY` chains to select best odds per sport
- RECOMMENDED over single-source `fetch_odds_api.py` for comprehensive price comparison

## Connected Skills

- `bet-analyzing-statistics` — Safety scores and probability engine outputs used as true probability input for EV calculation
- `bet-navigating-sources` — Odds source chains (BetExplorer, OddsPortal, The-Odds-API) for multi-source comparison
- `bet-building-coupons` — Kelly 1/4 staking outputs feed directly into coupon stake sizing
