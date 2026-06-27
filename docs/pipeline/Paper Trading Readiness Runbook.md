# Paper Trading Readiness Runbook

## Purpose

Run a non-production paper-trading readiness proof showing the pipeline can track picks, stake, expected payout, outcome, and PnL without placing any real bet.

## Scope

This gate keeps S8 draft-only, keeps S9 human-gated, writes the paper ledger outside the repository by default, and proves duplicate blocking, budget limits, settlement math, and protected-write boundaries.

## Fish Installation Commands

```fish
if not test -x .venv/bin/python3
    python3 -m venv .venv
end

.venv/bin/python3 -m pip install -U pip
.venv/bin/python3 -m pip install -e ".[dev]"; or .venv/bin/python3 -m pip install -e .
```

## Preconditions

- Work from the repository root.
- Use Fish shell.
- Keep `runtime_mode=DRY_RUN`.
- Keep `allow_real_bet_execution=false`.
- Keep `allow_betclic_execution=false`.
- Keep all outputs under `/private/tmp/...`.
- Do not write under `betting/data`, `betting/coupons`, `betting/journal`, or `reports`.

## Exact CLI Command

```fish
set DAY (date +%F)
set RUN_ID "paper-ready-"(date +%Y%m%d-%H%M%S)
set BASE_DIR "/private/tmp/bet-paper-trading-readiness"
set LEDGER_DIR "$BASE_DIR/$DAY/$RUN_ID/ledger"
set REPORT_PATH "$BASE_DIR/$DAY/$RUN_ID/paper_trading_readiness_report.json"

mkdir -p "$LEDGER_DIR"

.venv/bin/python3 scripts/pipeline_paper_trading_readiness.py \
  --betting-day "$DAY" \
  --run-id "$RUN_ID" \
  --base-dir "$BASE_DIR" \
  --ledger-dir "$LEDGER_DIR" \
  --runtime-mode DRY_RUN \
  --bankroll-units 100 \
  --max-stake-units-per-coupon 1 \
  --max-daily-risk-units 3 \
  --report-path "$REPORT_PATH"
```

## Expected PASS Output

- `STATUS=PASS`
- `PAPER_COUPON_COUNT=3`
- JSON report written to the requested report path
- JSONL ledger written under the requested ledger directory
- `ready_for_manual_low_stake_pilot=true`
- `ready_for_production_execution=false`

## Ledger Schema

The ledger is append-only JSONL at `paper_coupons.jsonl`.

Each line contains:

- `schema_version`
- `event_type` as `coupon_opened` or `coupon_settled`
- `recorded_at_utc`
- `coupon`

Each `coupon` records:

- `paper_coupon_id`
- `betting_day`
- `run_id`
- `source_s8_coupon_draft_path`
- `source_s8_coupon_draft_sha256`
- `source_s9_artifact_path`
- `source_s9_artifact_sha256`
- `selection_id`
- `event_id`
- `market`
- `pick`
- `odds_decimal`
- `stake_units`
- `expected_payout_units`
- `created_at_utc`
- `status`
- `pnl_units`

## Budget Rules

- `stake_units` must be greater than `0`.
- `odds_decimal` must be greater than `1`.
- `expected_payout_units = stake_units * odds_decimal`.
- Each paper coupon must stay within `max_stake_units_per_coupon`.
- Total open daily risk must stay within `max_daily_risk_units`.
- Bankroll limits fail closed.

## Kill-Switch Behavior

If the kill-switch is active, paper coupon creation blocks immediately and the ledger remains unchanged.

## Manual Low-Stake Pilot Criteria

Require all of the following:

- `ready_for_manual_low_stake_pilot=true`
- `ready_for_production_execution=false`
- `no_real_bet_execution_verdict=PASS`
- `no_betclic_execution_verdict=PASS`
- `protected_repo_write_verdict=PASS`
- `budget_guard_verdict=PASS`
- `ledger_schema_verdict=PASS`
- `settlement_verdict=PASS`
- duplicate submission blocked idempotently

## What Is Still Not Allowed

- Production mode
- Real bet execution
- Betclic execution
- Automated bookmaker placement
- Production coupon writes
- Repo-local protected writes

## Safety Statement

There is no guaranteed profit. Paper trading validates tracking, auditability, and risk controls only.

## Next Phase After PASS

`PIPELINE_MANUAL_LOW_STAKE_PILOT_A`
