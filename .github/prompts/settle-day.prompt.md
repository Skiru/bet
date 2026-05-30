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
- `screenshots_dir`: Optional path to directory with Betclic coupon screenshots

## Task

1. Run settlement for the previous day
2. Update PnL, CLV, bankroll
3. Run historical learning query (§0.2)
4. If screenshots provided: scan with `scan_coupon.py --batch {screenshots_dir} --save`, then run `learn_from_coupons.py --dir betting/coupons/ --date {prev_date} --save`
5. Present settlement summary + coupon scan learning (if applicable)

## Coupon Scan Learning
When screenshots are available, the pipeline:
- Uses local VLM (Qwen2.5-VL-3B-4bit via mlx-vlm) to extract events, markets, odds, status from Betclic app screenshots
- Matches scanned picks against pipeline predictions (bets + analysis_results DB tables)
- Produces learning signals: which high-confidence picks failed? Which low-confidence picks won?
- Outputs `{date}-coupon-learning.json` with safety score calibration data

This is equivalent to running only S0 from the full pipeline. Use `orchestrate-betting-day` for the full session.

<!-- BET:prompt:settle-day:v2 -->
