# Manual Low Stake Pilot Runbook

## Purpose

This runbook proves the system can prepare exactly one bounded manual pilot coupon, require human/legal attestations, record a human bookmaker action after the fact, and settle the outcome without enabling automated execution.

## Scope

This is a manual low-stake pilot only. It never places a bet, never clicks Betclic, never stores bookmaker credentials, never calls bookmaker APIs, and never enables production execution.

## Fish Installation Commands

```fish
if not test -x .venv/bin/python3
    python3 -m venv .venv
end

.venv/bin/python3 -m pip install -U pip
.venv/bin/python3 -m pip install -e ".[dev]"; or .venv/bin/python3 -m pip install -e .
```

## Preconditions

Use `DRY_RUN` only.
Keep all pilot artifacts under `/private/tmp/...`.
Provide a paper ledger entry with bound S8 and S9 metadata.
Prepare at most one coupon for the betting day.
Keep `READY_FOR_PRODUCTION_EXECUTION=false`.

## Legal and Human Attestations

Before running `prepare`, confirm the bookmaker is a legal operator for the human user.
Before running `prepare`, confirm age and KYC requirements are already satisfied by the human user.
Before running `prepare`, confirm responsible gambling limits are already configured outside the code.
Before running `prepare` and `record-placement`, confirm the eventual placement action is a manual human click outside this software.

## Risk Limits

One-coupon limit: one manual pilot coupon per betting day.
Maximum stake rule: `stake_units` must be greater than `0` and no more than `--max-stake-units-per-coupon`.
Daily risk rule: open daily risk must be no more than `--max-daily-risk-units`.
Daily stop-loss rule: realized losses plus open risk must be no more than `--daily-stop-loss-units`.
Kill-switch behavior: if `kill_switch=true`, preparation, placement recording, and settlement fail closed.

## Prepare Command

```fish
set DAY (date +%F)
set RUN_ID "manual-pilot-"(date +%Y%m%d-%H%M%S)
set BASE_DIR "/private/tmp/bet-manual-low-stake-pilot"
set PILOT_DIR "$BASE_DIR/$DAY/$RUN_ID"
set LEDGER_PATH "$PILOT_DIR/manual_pilot_ledger.jsonl"
set REPORT_PATH "$PILOT_DIR/manual_low_stake_pilot_report.json"

mkdir -p "$PILOT_DIR"

.venv/bin/python3 scripts/pipeline_manual_low_stake_pilot.py prepare \
  --betting-day "$DAY" \
  --run-id "$RUN_ID" \
  --base-dir "$BASE_DIR" \
  --pilot-dir "$PILOT_DIR" \
  --ledger-path "$LEDGER_PATH" \
  --paper-ledger-path "/private/tmp/path/to/paper_coupons.jsonl" \
  --source-paper-coupon-id "paper-example-001" \
  --manual-bookmaker-name "licensed-operator-manual" \
  --stake-units 1 \
  --max-stake-units-per-coupon 1 \
  --max-daily-risk-units 1 \
  --daily-stop-loss-units 1 \
  --legal-operator-attested \
  --age-kyc-attested \
  --responsible-gambling-limits-attested \
  --manual-click-attested \
  --report-path "$REPORT_PATH"
```

## Manual Human Placement Instructions

Read the report and checklist before any real-world action.
Use the prepared coupon only as a human review aid.
If the human decides to place the tiny stake, the human must do it entirely outside this codebase.
Record the bookmaker ticket ID and UTC placement time manually.

## Record Placement Command

```fish
.venv/bin/python3 scripts/pipeline_manual_low_stake_pilot.py record-placement \
  --betting-day "$DAY" \
  --run-id "$RUN_ID" \
  --pilot-dir "$PILOT_DIR" \
  --ledger-path "$LEDGER_PATH" \
  --manual-pilot-coupon-id "<prepared-manual-pilot-coupon-id>" \
  --manual-bookmaker-name "licensed-operator-manual" \
  --manual-bookmaker-ticket-id "MANUAL-TEST-TICKET-001" \
  --manual-placed-at-utc "2026-06-27T10:00:00Z" \
  --manual-click-attested \
  --report-path "$REPORT_PATH"
```

## Settlement Command

```fish
.venv/bin/python3 scripts/pipeline_manual_low_stake_pilot.py settle \
  --betting-day "$DAY" \
  --run-id "$RUN_ID" \
  --pilot-dir "$PILOT_DIR" \
  --ledger-path "$LEDGER_PATH" \
  --manual-pilot-coupon-id "<prepared-manual-pilot-coupon-id>" \
  --result WIN \
  --report-path "$REPORT_PATH"
```

## Expected PASS Output

Console output should include `STATUS=PASS`, `REPORT_PATH=...`, `LEDGER_PATH=...`, and `MANUAL_PILOT_COUPON_ID=...` for prepare and subsequent record/settle calls.

## Ledger Schema

The ledger is append-only JSONL.
Each line is a JSON object with `schema_version`, `event_type`, `recorded_at_utc`, and `coupon`.
Expected event types are `manual_coupon_prepared`, `manual_coupon_placed`, and `manual_coupon_settled`.
Coupon status transitions are `PREPARED -> MANUALLY_PLACED -> SETTLED_WIN|SETTLED_LOSS|VOID`.

## Still Forbidden

Automated bookmaker placement remains forbidden.
Betclic API execution remains forbidden.
Browser automation for placement remains forbidden.
Production mode remains forbidden.
Production coupon writes remain forbidden.
Bypassing bound S8/S9 artifacts remains forbidden.

## Notes

There is no guaranteed profit. This pilot validates process, auditability, discipline, and risk control only.
The next phase after PASS is `PIPELINE_MANUAL_PILOT_OBSERVATION_A`.
