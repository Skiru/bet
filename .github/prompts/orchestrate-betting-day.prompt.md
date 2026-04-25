---
name: orchestrate-betting-day
description: "Run S1-S8 pipeline: 3 test passes + 1 final coupon pass"
agent: bet-analyst
---

# BETTING DAY ORCHESTRATOR

Run the full S1→S8 pipeline for a betting day. Executes 3 TEST passes to find and fix errors, then 1 FINAL pass to produce coupons.

## CONFIG
- **Date**: {{run_date}}
- **Timezone**: Europe/Warsaw (CEST)
- **Betting window**: 06:00 {{run_date}} → 05:59 {{run_date}}+1
- **Config**: `config/betting_config.json`

---

## PRE-FLIGHT

Before any pass, ensure:
1. Orchestrator ran: `bash scripts/run_full_scan_and_prepare.sh` → check `betting/data/scan_summary.json`
2. The-Odds-API ran: `python3 scripts/fetch_odds_api.py` (if API key configured)
3. Config read: bankroll, daily cap, sports list
4. Previous day's learning-log.csv and error patterns reviewed

---

## STEP SEQUENCE

Each pass executes these steps IN ORDER. Each step:
1. Reads prior step's output file
2. Executes analysis
3. Writes its own output file to `betting/data/{date}_s{N}_{name}.md`
4. Runs self-verification checklist
5. Logs errors in `betting/data/{date}_pass{P}_errors.md`

| Step | Prompt | Input | Output | Gate |
|------|--------|-------|--------|------|
| S0 | `s0-settlement` | picks-ledger, coupons-ledger, Flashscore | `{date}_s0_settlement.md` | All pending resolved, bankroll updated |
| S1 | `s1-scan` | BetExplorer, Flashscore, scan_summary | `{date}_s1_master_events.md` | ≥50 events, 14 sports |
| S2 | `s2-shortlist` | S1 output | `{date}_s2_shortlist.md` | 15-40 candidates, ≥5 sports |
| S3 | `s3-deep-stats` | S2 output | `{date}_s3_deep_stats.md` | Stats from ≥2 sources per candidate |
| S4 | `s4-tipsters` | S3 output | `{date}_s4_tipsters.md` | ≥2 tipster sites per candidate |
| S5 | `s5-odds-ev` | S3+S4 output | `{date}_s5_odds_ev.md` | EV > 0 for all approved |
| S6 | `s6-context-upset` | S5 output | `{date}_s6_context.md` | Upset risk scored, context verified |
| S7 | `s7-bear-case-gate` | S6 output | `{date}_s7_gate.md` | 13-point gate passed per pick |
| S3B | `s3b-time-sensitive` | S7 output | `{date}_s3b_time_sensitive.md` | Lineups, weather, odds drift checked |
| S8 | `s8-portfolio-coupons` | S7+S3B output | Coupon file + ledgers | V1-V10 all pass |

**NOTE:** S3B runs AFTER S7 (bear case) but BEFORE S8 (coupons) so that lineup/weather findings can still void picks before coupon construction. S3B should run within 2-3h of earliest event kickoff. If analysis is done well before kickoff, S3B can be a separate later run — the orchestrator supports both modes.

---

## PASS PROTOCOL

### PASS 1 — DISCOVERY (find all errors)

Execute S0→S1→S2→S3→S4→S5→S6→S7→S3B→S8 fully. At each step:
- Run the step's self-verification checklist
- Log EVERY failure to: `betting/data/{date}_pass1_errors.md`
- Format: `| Step | Check | Status | Error Description | Fix Required |`
- Do NOT stop at first error — complete ALL steps, log ALL errors
- At end: count total errors, categorize by step

**Pass 1 output**: `{date}_pass1_errors.md` with full error inventory

### PASS 2 — TARGETED FIXES

Read `{date}_pass1_errors.md`. For each error:
1. Identify root cause
2. Re-execute ONLY the affected step (not all steps)
3. Verify the fix with that step's checklist
4. If fix introduces new errors → log in `{date}_pass2_errors.md`
5. Re-run downstream steps affected by the fix

**Focus areas** (common Pass 1 failures):
- S0: Pending picks not resolved, bankroll not updated → check Flashscore results
- S1: Missing sports, low event count → re-scan specific sports deeper
- S2: Too few candidates or missing sports → relax filters slightly
- S3: Missing H2H, missing stats, no TOP 3 markets → fetch specific data
- S4: Missing tipster sites, no arguments extracted → check specific URLs, use fallbacks
- S5: Missing odds source, no EV calculated → try alternative source
- S6: Missing injury check, upset risk not scored → verify on ESPN/Flashscore
- S7: Incomplete 13-point gate, Zero Tolerance pattern matched → fix or reject pick
- S3B: Lineups not checked, odds drift not calculated → re-run close to kickoff
- S8: Arithmetic error, orphan picks, missing sections → fix and re-validate

**Pass 2 output**: `{date}_pass2_errors.md` (should be shorter than Pass 1)

### PASS 3 — POLISH & EDGE CASES

Read `{date}_pass2_errors.md`. Fix remaining issues. Then:
1. Full V1-V10 validation on current state
2. Cross-check ALL pick IDs across ALL files
3. Verify combined odds arithmetic for every coupon
4. Check concentration (no pick in >60% coupons)
5. Verify sport diversity (≥5 sports in final picks)
6. Run Zero Tolerance Shield against known failure patterns
7. Log any final issues in `{date}_pass3_errors.md`

**Pass 3 output**: `{date}_pass3_errors.md` (should be 0-2 minor issues)

### PASS 4 — FINAL (COUPON PRODUCTION)

**This is the ONLY pass that writes final artifacts.** Passes 1-3 are working drafts.

1. Read Pass 3 error log — must have 0 critical errors
2. If critical errors remain → fix them first, do NOT produce coupons with known errors
3. Generate final coupon file: `betting/coupons/{date}-v{version}.md`
4. Update `betting/journal/picks-ledger.csv` (supersede old version)
5. Update `betting/journal/coupons-ledger.csv` (supersede old version)
6. Update `betting/journal/source-log.csv`
7. Update `betting/journal/learning-log.csv`
8. Write daily report: `betting/reports/{date}.md`
9. Run FINAL V1-V10 validation on produced artifacts
10. Present REQUIRED RESPONSE to user

---

## REQUIRED RESPONSE (end of Pass 4)

Present to user:

### 1. Settlement Summary
Previous day PnL, rolling 7-day, bankroll update

### 2. Scan Summary
Events per sport, total scanned, scan completeness %

### 3. Error Resolution Summary
| Pass | Errors Found | Errors Fixed | Remaining |
|------|-------------|-------------|-----------|
| 1 | X | - | X |
| 2 | X | X | X |
| 3 | X | X | X |
| 4 | 0 | - | 0 |

### 4. Final Picks Table
| ID | Event | Market | Odds | EV | Conf | Sport |
|----|-------|--------|------|----|------|-------|

### 5. Final Coupons (SHOW ALL)
For each coupon: legs, combined odds (arithmetic shown), stake, type

### 6. Watchlist
Picks that almost made it + promotion criteria

### 7. Financial Summary
Total exposure, bankroll %, max single stake

### 8. V1-V10 Status
ALL PASS or list any exceptions

### 9. Conditional Notes
Picks that need Betclic odds verification, acceptance thresholds

### 10. Risk Assessment
If top pick fails: what survives? Worst-case portfolio loss.

---

## ERROR ESCALATION

- **S0 gate FAIL**: Settlement incomplete → must resolve before proceeding (bankroll affects staking).
- **Step gate FAIL in Pass 1-2**: Expected. Log and fix.
- **Step gate FAIL in Pass 3**: Concerning. Must fix before Pass 4.
- **Step gate FAIL in Pass 4**: BLOCKER. Do NOT produce coupons. Fix first.
- **S3B gate FAIL**: Time-sensitive data missing → flag affected picks as CONDITIONAL with extra notes.
- **V1-V10 FAIL in Pass 4**: BLOCKER. Loop back to fix, re-validate.
- **<5 approved picks after all passes**: Consider NO BET day or promote watchlist.
- **<5 sports in final picks**: Go back to S1, scan missing sports deeper.

---

## FILE NAMING CONVENTION

Working files (Passes 1-3):
```
betting/data/{date}_s0_settlement.md
betting/data/{date}_s1_master_events.md
betting/data/{date}_s2_shortlist.md
betting/data/{date}_s3_deep_stats.md
betting/data/{date}_s4_tipsters.md
betting/data/{date}_s5_odds_ev.md
betting/data/{date}_s6_context.md
betting/data/{date}_s7_gate.md
betting/data/{date}_s3b_time_sensitive.md
betting/data/{date}_pass1_errors.md
betting/data/{date}_pass2_errors.md
betting/data/{date}_pass3_errors.md
```

**NOTE:** Each pass OVERWRITES the same S-output files (they reflect the CURRENT best state). Error logs are per-pass and NOT overwritten — all 3 error logs are kept for audit trail.

Final artifacts (Pass 4 only):
```
betting/coupons/{date}-v{version}.md
betting/reports/{date}.md
betting/journal/picks-ledger.csv (append)
betting/journal/coupons-ledger.csv (append)
betting/journal/source-log.csv (append)
betting/journal/learning-log.csv (append)
```
