# Rich Coupon Package Runbook & Reference Guide

## Overview
The **Rich Coupon Package System** is the final product layer for generating deeply verified, human-readable and machine-readable manual coupon files and analysis reports. 

This system operates under a strict safety contract:
1. **NO Automated Login**: The system never logs into bookmakers.
2. **NO API Placement**: No Betclic or Superbet APIs are ever called.
3. **NO Browser Automation**: Playwright, Selenium, or other tools are strictly forbidden from placing bets.
4. **NO Invented Combined Odds**: Combined odds must never be guessed; the human operator must verify and log them.

---

## Dataclasses & Models

### `CouponLeg`
Represents an individual selection/leg within a manual package:
* `leg_id`: Unique identifier of the leg.
* `event_id`: Fixture/Event identifier.
* `event`: Match description (e.g. `Donald, M. W. vs Potenza, Luca`).
* `market` & `market_type`: Market details (e.g. `Luca Potenza Player Aces O/U`).
* `pick` & `line`: Precise selection side and threshold.
* `odds_decimal`: Captured odds of the selection.
* `supporting_stats` & `counter_stats`: Adheres to point-in-time and adversarial balance. Can contain metric form statistics with source and timestamp, or mark as `UNKNOWN`.

### `BetBuilderPackage`
Represents the combined coupon structure:
* `package_id` & `package_type`: Type is categorized as `SINGLE`, `BET_BUILDER`, `MULTI_BET_BUILDER`, or `NO_BET_PACKAGE`.
* `combined_odds_decimal`: Hardcoded to `null` to prevent halluncinating odds.
* `operator_screen_checklist`: Sequentially guides the human user.
* `ready_for_human_manual_placement`: True if all validators pass.
* `ready_for_automated_bet_placement` & `ready_for_production_execution`: ALWAYS `false`.

---

## Operational Execution (CLI)

To build a rich package from a daily session ledger, execute the CLI utility:

```fish
# Run under fish environment
env PYTHONPATH=src:scripts .venv/bin/python3 scripts/pipeline_rich_coupon_package.py build-from-session \
  --betting-day 2026-06-28 \
  --session-id run_20260628_manual_a \
  --session-ledger-path /private/tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_ledger.jsonl \
  --output-dir /private/tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/artifacts \
  --operator-name Betclic \
  --report-path /private/tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/report.json
```

### Outputs
* **JSON File**: `{output_dir}/{betting_day}_rich_coupon_package.json`
* **Markdown File**: `{output_dir}/{betting_day}_rich_coupon_package.md`
* **Report File**: `{report_path}` (RichCouponPackageReport)

Stdout prints:
* `STATUS=READY_FOR_HUMAN_REVIEW` if a package is safely buildable.
* `STATUS=NO_BET_PACKAGE` if any validation blocks.
