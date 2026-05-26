---
name: settle-day
description: "Quick settlement — settle previous day without running full pipeline"
agent: "bet-settler"
skills:
  - bet-orchestrating-workflows
---

# Quick Settlement

Settle the previous day's picks and coupons without running the full S0-S8 pipeline.

## Arguments
- `run_date`: The current date (default: today)

## Task

1. Run settlement for the previous day
2. Update PnL, CLV, bankroll
3. Run historical learning query (§0.2)
4. Present settlement summary

This is equivalent to running only S0 from the full pipeline. Use `orchestrate-betting-day` for the full session.

<!-- BET:prompt:settle-day:v1 -->
