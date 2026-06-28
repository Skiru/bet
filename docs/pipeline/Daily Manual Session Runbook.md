# Daily Manual Session Runbook

## Overview
The Daily Manual Session Control layer enforces extreme safety, budget control, and completeness verification on real bets performing manual placement. It sits before any manual pilot or bookmaker interaction to ensure no malformed, incomplete, or production-violating picks are ever placed.

## Safety Checkpoints
1. **Attestation & Compliance:** The operator must attest to legal operator status, Age KYC, and responsible gambling limits.
2. **Automated-Placement Disabling:** Automated placement, browser automation, and Betclic API calls must remain completely disabled.
3. **Market Completeness:** No O/U market can be reviewed without a precise numeric line (e.g., Over/Under 2.5). Any bare `UNDER`/`OVER` or missing player/identity fields will trigger a hard `NO_BET` rejection.
4. **Budget Guard & Stop Loss:** Open daily risk and total realized losses are strictly monitored and cannot exceed their respective configured thresholds.

## Operational CLI Commands

### 1. Review S8 Draft Candidate Picks
Run the draft review subcommand to validate candidates against all completeness and safety constraints:
```fish
./scripts/pipeline_daily_manual_session.py review-draft \
  --betting-day 2026-06-28 \
  --session-id run_20260628_manual_a \
  --base-dir /tmp/pipeline_runs \
  --session-dir /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a \
  --session-ledger-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_ledger.jsonl \
  --s8-coupon-draft-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/data/2026-06-28_s8_coupon_drafts.json \
  --s8-coupon-draft-sha256 3799c201191894241e9c6fcbfeebba0b6d58d78a11011086a7356abe58ea0945 \
  --s9-artifact-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/data/2026-06-28_s9_human_gate.json \
  --s9-artifact-sha256 a83d1cde4094... \
  --operator-name Betclic \
  --report-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_report.json \
  --legal-operator-attested \
  --age-kyc-attested \
  --responsible-gambling-limits-attested
```

### 2. Prepare First Bettable Coupon
After a successful review, prepare the first approved candidate to register it for manual placement:
```fish
./scripts/pipeline_daily_manual_session.py prepare-first-bettable \
  --betting-day 2026-06-28 \
  --session-id run_20260628_manual_a \
  --base-dir /tmp/pipeline_runs \
  --session-dir /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a \
  --session-ledger-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_ledger.jsonl \
  --report-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_report.json \
  --legal-operator-attested \
  --age-kyc-attested \
  --responsible-gambling-limits-attested
```

### 3. Close the Session
Once placing and settling is complete, close the session ledger to generate a terminal session audit:
```fish
./scripts/pipeline_daily_manual_session.py close-session \
  --session-ledger-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_ledger.jsonl \
  --report-path /tmp/pipeline_runs/2026-06-28/run_20260628_manual_a/daily_session_report.json
```
