---
name: step5-odds-ev
description: "STEP 5: Odds comparison + EV calculation for each candidate. Outputs to betting/data/{date}_odds_ev.md"
agent: bet-analyst
argument-hint: "run_date=2026-04-25"
tools:
  - search
  - editFiles
  - runCommands
  - memory/*
  - sequentialthinking/*
---

## Inputs
- **run_date** = ${input:run_date:today}
- **deep_stats** = `betting/data/{run_date}_deep_stats.md`
- **tipster_dive** = `betting/data/{run_date}_tipster_dive.md`

## Task

For EACH candidate still alive after stats + tipster checks, calculate EV and assess odds value.

### Per-Candidate Protocol

1. **Get market-best odds** from BetExplorer/OddsPortal for the specific market
2. **Get Betclic reference odds** (estimated — user verifies on app)
3. **Estimate true probability**:
   - Best method: Pinnacle implied probability (remove vig: implied_prob / sum_of_both_sides)
   - Second: Statistical model estimate from hit rates (Step 3)
   - Third: Market consensus (average across 5+ books, remove vig)
4. **Calculate EV**: `EV = (true_probability × betclic_odds) - 1`
   - EV > 0 → POSITIVE expected value → candidate lives
   - EV ≤ 0 → REJECT unless other factors overwhelm
5. **Calculate price_gap_pct**: `100 × ((betclic_odds / market_best_odds) - 1)`
   - Low-risk: reject if < -3%
   - High-risk: reject if < -5%
6. **Check line movement**: Compare opening odds to current odds
   - Significant drift (>8%) → MANDATORY re-evaluation
   - Steam move toward our side → good signal
   - Reverse line movement (sharp money against us) → investigate
7. **Apply Kelly criterion**: `Kelly% = (true_prob × odds - 1) / (odds - 1)` → use 1/4 Kelly
   - If Kelly suggests 0 or negative → SKIP

### Output Format

Save to `betting/data/{run_date}_odds_ev.md`:

```markdown
# Odds & EV Analysis — {run_date}

## CANDIDATE: Arsenal vs Newcastle — Corners O9.5

| Metric | Value |
|--------|-------|
| Market best odds | 1.75 (Pinnacle) |
| Betclic est. odds | 1.70 |
| Pinnacle implied prob | 54.5% |
| True prob estimate | 58% |
| **EV** | **+1.6%** |
| Price gap % | -2.9% (OK for LR) |
| Line movement | Stable (opened 1.72) |
| 1/4 Kelly stake | 0.7% bankroll = 0.25 PLN |
| odds_checked_at | YYYY-MM-DD HH:MM |

### Verdict: APPROVED / BORDERLINE / REJECTED
### Reason: [1 sentence]

---
(repeat per candidate)
```

### Rejection Criteria (automatic)
- EV ≤ 0 → REJECT
- Price gap < -3% (LR) or < -5% (HR) → REJECT
- Odds drift > 8% from analysis time → MANDATORY re-eval
- Kelly ≤ 0 → REJECT
- No Pinnacle line available AND no statistical model estimate → REDUCE confidence -1
