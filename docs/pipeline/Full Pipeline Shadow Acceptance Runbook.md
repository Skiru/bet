# Full Pipeline Shadow Acceptance Runbook

## Purpose

Run a non-production shadow acceptance proving that the current S0-S10 pipeline safety architecture is auditable and fail-closed.

## Scope

This acceptance exercises the S0/S1/S2/S3/S4/S5/S6/S7/S8/S9 path in shadow-safe mode, keeps S8 draft-only, keeps S9 human-gated, and proves S10 only unblocks with a strict run-bound S9 approval tied to the exact S8 draft SHA256.

## Fish Install Commands

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
- Keep `READY_FOR_PRODUCTION_EXECUTION=false`.
- Use a `/private/tmp/...` base directory.
- Do not enable live provider calls, Betclic execution, or production writes.

## Exact Command

```fish
set DAY (date +%F)
set RUN_ID "full-shadow-"(date +%Y%m%d-%H%M%S)
set BASE_DIR "/private/tmp/bet-full-shadow-acceptance"
set REPORT_PATH "/private/tmp/bet-full-shadow-acceptance/"$DAY"/"$RUN_ID"/full_shadow_acceptance_report.json"

.venv/bin/python3 scripts/pipeline_full_shadow_acceptance.py \
  --betting-day "$DAY" \
  --run-id "$RUN_ID" \
  --base-dir "$BASE_DIR" \
  --runtime-mode DRY_RUN \
  --report-path "$REPORT_PATH"
```

## Expected PASS Output

- `STATUS=PASS`
- `PIPELINE_TERMINAL_STATUS=S9_BLOCK_WAITING_FOR_HUMAN_GATE`
- JSON report written at the requested report path
- `ready_for_production_execution=false`
- `protected_repo_write_verdict=PASS`

## Valid Terminal Outcomes

- `S9_BLOCK_WAITING_FOR_HUMAN_GATE`
- `S7_NO_ACTION_TERMINAL`

If `S7_NO_ACTION_TERMINAL` occurs, treat the run as technically safe but not a completed coupon-path acceptance.

## What Is Still Not Allowed

- Production mode
- Real bet execution
- Betclic execution
- Production coupon writes
- Writes under `betting/data`, `betting/coupons`, `betting/journal`, or `reports`

## Qualification After PASS

PASS qualifies the system for the next phase `PIPELINE_PAPER_TRADING_READINESS_A`.

## Safety Statement

This acceptance does not guarantee profit. It proves technical safety and auditability only.
