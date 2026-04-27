---
name: orchestrate-betting-day
description: "Full daily cycle: 4-pass pipeline (Discovery → Fixes → Polish → Final) with settlement, scan, deep analysis, coupons."
agent: bet-orchestrator
argument-hint: "run_date=2026-04-27 session=full" or "run_date=2026-04-27 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

Run the full S0→S8 pipeline for a betting day. Executes 3 TEST passes to find and fix errors, then 1 FINAL pass to produce coupons.

## INPUTS

- **run_date** = {{run_date}}
  If empty, use the current calendar date.
- **session** = {{session}} (default: `full`)
  Controls which events to analyze:
  - `full` — entire betting day (06:00 → 05:59 next day). Default.
  - `day` — daytime events only (06:00 → 21:59).
  - `night` — night events only (22:00 → 05:59 next day).
  - `morning` — settle overnight results + scan early events (06:00 → 14:59).
- **rerun** = {{rerun}} (default: `false`)
  When `true`, forces complete fresh analysis even if artifacts exist. See §RERUN below.
- **version** = {{version}} (default: `v1`)
- **Bookmaker**: Betclic
- **Timezone**: Europe/Warsaw (CEST)
- Load all other parameters from `config/betting_config.json`.

---

## STEP -1: INSTRUCTION LOADING (ALWAYS FIRST — NEVER SKIP)

Load ALL files below. Do NOT proceed to any analysis until all are loaded and confirmed.

```
REQUIRED READS:
1. config/betting_config.json — bankroll, caps, sports list, betting_window_days
2. .github/instructions/analysis-methodology.instructions.md — STEPS 0-10, V1-V10
3. .github/instructions/betting-artifacts.instructions.md — output formats
4. .github/instructions/sport-analysis-protocols.instructions.md — sport stats, upset checklists, red flags
5. betting/sources/source-registry.md — source tiers + blocked list
6. /memories/ — all memory files (common-mistakes, workflow-rules, analysis-principles)
```

**PRE-FLIGHT CHECKLIST (print before proceeding):**
```
[ ] Bankroll: ___ PLN | Daily budget: ___-___ PLN
[ ] Session: {{session}} → window: HH:MM → HH:MM
[ ] Sports: 14 confirmed | betting_window_days: ___
[ ] Previous day settled: yes/no
[ ] Files loaded: 6/6 | Memory files loaded: yes/no
[ ] Blocked sources reviewed | Common mistakes reviewed (count: ___)
[ ] Market hit rates checked in picks-ledger | 48h repeat check ready
[ ] Rerun: {{rerun}} | Version: {{version}}
```

**MANDATORY: Use `sequentialthinking` for EVERY STEP (0-10). Per-candidate steps (3-7) = one call PER candidate.**

## SESSION PARITY RULE (NEVER VIOLATE)

**ALL sessions (full/day/night/morning) execute the EXACT SAME pipeline:**
- Same 4-pass protocol (Discovery → Targeted Fixes → Polish → Final)
- Same S0→S1→S2→S3→S4→S5→S6→S7→S3B→S8 step sequence
- Same 14-sport scan in S1 (ALL sports, even if most have 0 events in the window)
- Same deep analysis (S3-S7): H2H, tipsters, injuries, bear case, 17-point gate
- Coupon count = f(quality events, deep statistics), NOT f(bankroll). Produce as many as quality justifies.
- Same V1-V10 validation + §S8.FINAL Mechanical Verification

**The ONLY difference is the event time window filter in S2.** Nothing else changes.

If the time window yields fewer events → the shortlist is smaller → fewer picks → but each pick gets FULL analysis. If <3 picks survive → declare NO BET for that session. NEVER produce 1-2 shallow coupons as a compromise.

**This rule exists because of the v10 night session failure:** agent produced 2 "compact" coupons with 3 sports scanned, zero tipster checks, zero H2H, zero injuries. That is NEVER acceptable.

---

## PRE-FLIGHT (runs once before Pass 1)

Before any pass, ensure:
1. Run scan pipeline: `bash scripts/run_full_scan_and_prepare.sh` → check `betting/data/scan_summary.json`
2. Run The-Odds-API: `python3 scripts/fetch_odds_api.py` (if API key configured)
3. Config loaded: bankroll, daily cap, sports list, betting_window_days
4. Previous day's learning-log and error patterns reviewed
5. If `betting_window_days` > 1 → extend scan window to cover N days
6. If `rerun=true` → execute §RERUN versioning protocol (see above)

### §RERUN — VERSIONING PROTOCOL (when rerun=true)

When `rerun=true`, previous artifacts are PRESERVED, not replaced:

1. **Determine next version:** scan `betting/coupons/YYYY-MM-DD*.md` for highest existing version (e.g., v5 → next is v6). If no versioned file, start at v1.
2. **New IDs:** New picks get NEW pick_ids (next available PK-YYYYMMDD-## after highest existing). New coupons get versioned IDs (e.g., CP-YYYYMMDD-LR1v6).
3. **Ledger rows:** ADD new rows with `version=vN`. Old version rows stay untouched.
4. **Supersede old:** Set old version's `pending` picks/coupons to `status=superseded`.
5. **New files:** Create `betting/coupons/YYYY-MM-DD-vN.md` and `betting/reports/YYYY-MM-DD-vN.md`. Previous version files are kept.
6. **Settlement:** SKIP if previous day was already settled (check picks-ledger).
7. **Fresh analysis:** ALL steps S1-S8 run from scratch — do NOT reuse previous analysis.
8. **Learning-log:** Gets an entry noting the rerun and reason.
9. Re-run scan pipeline regardless of data freshness.

---

## STEP SEQUENCE

Each pass executes these steps IN ORDER. Each step:
1. Reads prior step's output file
2. Executes analysis
3. Writes its own output file to `betting/data/{date}_s{N}_{name}.md`
4. Runs self-verification checklist
5. Logs errors in `betting/data/{date}_pass{P}_errors.md`

| Step | Prompt | Agent | Input | Output | Gate |
|------|--------|-------|-------|--------|------|
| S0 | `s0-settlement` | bet-settler | picks-ledger, coupons-ledger, Flashscore | `{date}_s0_settlement.md` | All pending resolved, bankroll updated |
| S1 | `s1-scan` | bet-scanner | BetExplorer, Flashscore, scan_summary | `{date}_s1_master_events.md` + `{date}_s1_tipster_prefetch.md` | ≥50 events, ALL 14 sports scanned (≥6 with events), completeness ≥80%, **tipster HTML fetched** |
| S2 | `s2-shortlist` | bet-scanner | S1 output | `{date}_s2_shortlist.md` | 15-40 candidates, ≥8 sports in shortlist |
| S3 | `s3-deep-stats` | bet-statistician | S2 output | `{date}_s3_deep_stats.md` | Stats from ≥2 sources per candidate |
| S4 | `s4-tipsters` | bet-scout | S3 output + **§1.5 pre-fetched HTML** | `{date}_s4_tipsters.md` | ≥2 tipster sites per candidate, **§4.3 watchlist promotion done** |
| S5 | `s5-odds-ev` | bet-valuator | S3+S4 output | `{date}_s5_odds_ev.md` | EV > 0 for all approved |
| S6 | `s6-context-upset` | bet-challenger | S5 output | `{date}_s6_context.md` | Upset risk scored, context verified |
| S7 | `s7-bear-case-gate` | bet-challenger | S6 output | `{date}_s7_gate.md` | 17-point gate passed per pick |
| S3B | `s3b-time-sensitive` | bet-statistician | S7 output | `{date}_s3b_time_sensitive.md` | Lineups, weather, odds drift checked |
| S8 | `s8-portfolio-coupons` | bet-builder | S7+S3B output | Coupon file + ledgers | V1-V10 all pass |

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
- S4: Missing tipster sites, no arguments extracted → check specific URLs, use fallbacks. **If §1.5 pre-fetch was skipped → RUN IT NOW (Playwright fetch all 5 tipster sites) before re-doing S4.** Verify §4.3 watchlist promotion was done.
- S5: Missing odds source, no EV calculated → try alternative source
- S6: Missing injury check, upset risk not scored → verify on ESPN/Flashscore
- S7: Incomplete 17-point gate, Zero Tolerance pattern matched → fix or reject pick
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
7. **SESSION PARITY CHECK**: If session=night/morning, verify:
   - ALL 14 sports were scanned (not just US sports for night)
   - Every candidate got full S3-S7 (H2H, tipsters, injuries, bear case, 17-point gate)
   - ≥5 coupons built (or NO BET declared with justification)
   - V1-V10 ran fully (not a "compact" validation)
   - If ANY of these failed → treat as critical error, fix before Pass 4
8. Log any final issues in `{date}_pass3_errors.md`

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
10. **Run MECHANICAL VERIFICATION (§S8.FINAL) — MANDATORY before presenting to user**
11. Present REQUIRED RESPONSE to user

---

## §S8.FINAL — MECHANICAL VERIFICATION (MANDATORY — runs AFTER artifacts are written, BEFORE presenting)

This step catches bugs that V1-V10 misses. Use `sequentialthinking` for exact computation.

### A. COUPON ARITHMETIC RE-CALCULATION
For EVERY coupon, multiply each leg's odds step by step. Compare to the listed combined odds.
```
Example: CP-XX has legs 1.50, 1.55, 1.60
Step: 1.50 × 1.55 = 2.325; 2.325 × 1.60 = 3.720
Listed: 3.72 → MATCH ✅
Listed: 3.65 → MISMATCH ❌ → FIX to 3.72
```
Also verify: Return = Combined odds × Stake. Fix any rounding errors >0.02.

### B. PLACEMENT ORDER VERIFICATION
For EVERY coupon, identify which picks it contains, find each pick's kickoff time, and determine the earliest kickoff. The deadline = earliest kickoff minus ~30-60 min.
```
Example: CP-XX has PK-01 (18:45) + PK-05 (19:00) → earliest = 18:45 → deadline ~18:00
If listed deadline says "13:30" → WRONG ❌ → FIX to 18:00
```
Common bug: listing deadline based on a pick NOT in that coupon. Always trace pick IDs.

### C. PICK-COUPON CROSS-CHECK
1. List every pick and which coupons contain it. Verify the per-pick exposure table matches.
2. Confirm NO orphan picks (every pick in ≥1 coupon).
3. Confirm concentration: no pick in >60% of coupons.
4. Confirm sport count per coupon: max 2 same-sport legs.

### D. HOME/AWAY DIRECTION CHECK
For EVERY US sport pick (NHL, NBA, MLB, NFL): verify "@" = Away @ Home.
For EVERY BetExplorer-sourced pick: BetExplorer = "Home vs Away" format.
Cross-check that coupon file uses correct team ordering.

### E. EV CONSISTENCY CHECK
For every pick, verify the stated EV matches the formula: `EV = (true_prob × odds) - 1`.
If analysis says "EV +20%" but math shows +12.5% → fix the label.

### F. PRICE GAP FLAGGING
List any picks with `price_gap_pct` outside the allowed threshold (-3% LR, -5% HR).
If marginal (within -0.5% of threshold) and CONDITIONAL → acceptable but FLAG in conditional notes.

### G. TOTAL EXPOSURE VERIFICATION
Sum all coupon stakes. Compare to listed total. Verify total against 25% bankroll limit.
Budget variants must have correct stake sums.

### H. FIX PROTOCOL
If ANY check fails:
1. Fix the coupon file IN PLACE (edit, don't rewrite)
2. Fix the corresponding ledger entry if affected
3. Re-run the specific check that failed to confirm fix
4. Log what was wrong and what was fixed (include in REQUIRED RESPONSE §3)

---

## REQUIRED RESPONSE (end of Pass 4)

Present to user:

### 1. Settlement Summary
Previous day PnL, rolling 7-day, bankroll update

### 2. Session & Scan Summary
Session type, event window, events per sport, total scanned, scan completeness %

### 3. Error Resolution Summary
| Pass | Errors Found | Errors Fixed | Remaining |
|------|-------------|-------------|-----------|
| 1 | X | - | X |
| 2 | X | X | X |
| 3 | X | X | X |
| 4 | 0 | - | 0 |

### 4. Final Picks Table
| ID | Event | Market | Odds | EV | Conf | Sport | Stake |
|----|-------|--------|------|----|------|-------|-------|

### 5. Final Coupons (SHOW ALL)
For each coupon: legs, combined odds (arithmetic shown), stake, type

### 6. Watchlist
Picks that almost made it + promotion criteria (including §4.3 tipster-sourced picks)

### 7. Financial Summary
Total exposure, bankroll %, max single stake

### 8. V1-V10 + §S8.FINAL Status
ALL PASS or list any exceptions

### 9. Conditional Notes
ALL picks with Betclic acceptance thresholds + any source issues/outages

### 10. Risk Assessment
If top pick fails: what survives? Worst-case portfolio loss.

---

## ERROR ESCALATION

- **S0 gate FAIL**: Settlement incomplete → must resolve before proceeding (bankroll affects staking).
- **Step gate FAIL in Pass 1-2**: Expected. Log and fix.
- **Step gate FAIL in Pass 3**: Concerning. Must fix before Pass 4.
- **Step gate FAIL in Pass 4**: BLOCKER. Do NOT produce coupons. Fix first.
- **§S8.FINAL Mechanical Verification FAIL**: BLOCKER. Fix artifacts in place, re-run failed check. Do NOT present to user until all 7 checks (A-G) pass.
- **S3B gate FAIL**: Time-sensitive data missing → flag affected picks as CONDITIONAL with extra notes.
- **V1-V10 FAIL in Pass 4**: BLOCKER. Loop back to fix, re-validate.
- **<4 approved picks after all passes**: Declare NO BET day (do not produce coupons with <4 picks).
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
betting/coupons/{date}-v{version}.md (or {date}-night.md, {date}-morning.md for non-full sessions)
betting/reports/{date}.md (or {date}-v{version}.md for reruns)
betting/journal/picks-ledger.csv (append)
betting/journal/coupons-ledger.csv (append)
betting/journal/source-log.csv (append)
betting/journal/learning-log.csv (append)
```

**Session suffix:** night → `-night`, morning → `-morning`, day → `-day`, full → no suffix.
**Rerun suffix:** append `-v{N}` (e.g., `2026-04-27-v3.md`). Never overwrite previous versions.
