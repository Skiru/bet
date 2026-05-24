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

For count-based statistical markets, use the probability engine output from S3 (`bet-analyzing-statistics` §3.0-PROB):

```bash
# From S3 output: look for P(hit), Fair Odds, λ columns in ranking table
# Or compute directly:
python3 scripts/probability_engine.py --line 9.5 --direction OVER --values "11,8,13,9,10"
```

**Cross-validation with Pinnacle:**

| |Poisson − Pinnacle| | Confidence | Action |
|---|---|---|
| <5% | High | Use Poisson |
| 5-10% | Moderate | Average both |
| >10% | Low | Investigate news/injuries |

**Min Betclic Odds = 1 / P(hit)** — Betclic must offer ABOVE this for EV > 0.

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

Get odds from ≥2 sources per candidate. See `bet-navigating-sources` for full source chains.

| Sport Region | Source 1 | Source 2 | Source 3 |
|-------------|----------|----------|----------|
| EU sports | The-Odds-API (DB) | odds-api.io (DB + snapshot) | API-Football-Odds (football only) |
| US sports (NHL/NBA) | SBR | ESPN Odds | ScoresAndOdds |
| Volleyball | odds-api.io (primary) | — | — |
| Esports (CS2/Valorant) | bo3.gg via `fetch_esports_odds.py` (DB: bookmaker='bo3gg') | — | — |

Cross-validate: odds differ >5% between sources → investigate staleness.

## The-Odds-API & Multi-Source

→ See `bet-navigating-sources` for script commands (`fetch_odds_api.py`, `fetch_odds_multi.py`) and source fallback chains.

Quota: 30 credits/full scan, 500/month free (~16 scans/month). Key: `config/odds_api_key.txt`.

## DB Queries for Odds

```sql
-- Latest odds for a fixture
SELECT bookmaker, market, selection, odds, fetched_at
FROM odds_history WHERE fixture_id = ? ORDER BY fetched_at DESC;

-- CLV calculation (closing vs placement)
SELECT
  (SELECT odds FROM odds_history WHERE fixture_id = ? AND market = ? AND is_closing = 1) as closing,
  b.odds as placement
FROM bets b WHERE b.fixture_id = ? AND b.market = ?;
```

## Connected Skills

| Skill | Load for |
|-------|----------|
| `bet-analyzing-statistics` | Safety scores and P(hit) from probability engine → input to EV formula |
| `bet-navigating-sources` | Odds source chains, `fetch_odds_multi.py` script, American odds conversion |
| `bet-building-coupons` | Kelly 1/4 staking → coupon stake sizing |
