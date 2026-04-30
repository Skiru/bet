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
  1. Pinnacle implied probability (strip margin) — most sharp
  2. Average of sharp bookmakers (Pinnacle, Betfair, bet365)
  3. Statistical model estimate from deep analysis data
  4. Tipster consensus

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

- `bet-navigating-sources` — provides the source chains for odds retrieval
- `bet-analyzing-statistics` — provides the statistical analysis that feeds into EV calculation
- `bet-building-coupons` — uses EV ranking to prioritize picks in coupon construction
