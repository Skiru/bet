---
name: daily-betting-cycle
description: Settle the previous betting day, update all artifacts, analyze today's slate, build optimal coupons.
agent: bet-analyst
argument-hint: "run_date=YYYY-MM-DD coupon_count=5"
tools:
  - search
  - editFiles
  - runCommands
  - terminalLastCommand
  - changes
  - memory/*
  - sequentialthinking/*
---

Use these inputs:
- run_date = ${input:run_date:YYYY-MM-DD}
- coupon_count = ${input:coupon_count:5}
- bookmaker = Betclic
- local_timezone = Europe/Warsaw
- Load all other parameters (sports, stakes, caps, thresholds) from config/betting_config.json.

Follow [repo instructions](../copilot-instructions.md), [artifact rules](../instructions/betting-artifacts.instructions.md), [model-ready rules](../instructions/model-ready-betting.instructions.md), and [source registry](../../betting/sources/source-registry.md).

**MANDATORY: Use the `sequentialthinking` tool for every phase (A–I). Do not reason only in text — call the tool explicitly at each phase transition. This prevents shortcuts, counting errors, and skipped checks.**

---

## PHASE A: SETUP

A1. Resolve the current betting day from run_date (06:00 run_date → 05:59 next day, Europe/Warsaw).
A2. Ensure all artifact paths exist and bootstrap missing ones with exact headers from artifact rules:
    - betting/reports/ betting/coupons/ betting/journal/ betting/sources/
    - betting/journal/learning-log.md picks-ledger.csv coupons-ledger.csv source-log.csv
A3. If betting/sources/source-registry.md is missing, stop and ask the user.

## PHASE B: ORCHESTRATOR

B1. Check if `betting/data/scan_summary.json` and `betting/data/picks_suggested.json` exist and were generated today.
B2. If missing or stale, run the orchestrator automatically:
    ```
    cd /Users/mkoziol/projects/bet && bash scripts/run_full_scan_and_prepare.sh
    ```
    This installs dependencies, runs Playwright smoke test, fetches all source pages, and produces structured outputs. It takes 2–5 minutes.
B3. If the orchestrator fails (non-zero exit), show the error and ask the user to fix the environment before retrying.
B4. After orchestrator data is confirmed, check `betting/data/scan_errors.json` for source failures and note them.

## PHASE C: SETTLEMENT

C1. Determine the previous betting day.
C2. List every pending pick and coupon from the previous betting day.
C3. For each pending pick:
    - Try `python3 scripts/settle_on_finish.py --betting-day <prev_date>` first.
    - For picks the script cannot auto-resolve (corners, cards, handicaps, MyCombi), check Flashscore + Sofascore manually.
    - Use at least two verification sources. If only one is available, say so in notes.
    - Update picks-ledger.csv status and pnl_pln.
C4. For each pending coupon, derive status from its legs (all legs win → coupon win, any leg loss → coupon loss).
C5. Update coupons-ledger.csv status and pnl_pln.
C6. Compute previous-day PnL and rolling 7-day PnL.

## PHASE D: LEARNING & SOURCES

D1. Append a section to learning-log.md following the template (max 3 rule changes).
D2. Update source-log.csv for today — one row per source, noting availability and usage.

## PHASE E: ANALYSIS

E1. Scan the betting-day slate across all sports in config. Use orchestrator outputs (scan_summary.json, picks_suggested.json) as the primary event list.
E2. Build a candidate board of all events inside the betting window.
E3. For each candidate, evaluate:
    - Tier A stats source evidence — for football corners: TotalCorner match total + SoccerStats league ranking + Betclic Statystyki odds. For BTTS/U2.5: SoccerStats defensive profiles. For volleyball: BetExplorer set/point totals.
    - Tier A market source evidence (specific odds from BetExplorer)
    - Evidence against / risk factors
    - Bookmaker odds vs market-best → compute price_gap_pct
    - Community sentiment check: scan Zawod Typer, bettingexpert, or Oddspedia Community for the event. Note consensus direction and percentage if available. If ≥60% diverge from Tier A direction, flag as red flag and investigate.
    - Hard rejection checks (missing Tier A, source conflict, bad price gap, correlated with existing picks)
    - Confidence score 1–5 with one-sentence justification (adjust ±1 based on community consensus alignment/divergence per source-registry rules)
    - Verdict: approved, rejected, or watch
E4. For football: prefer statistical markets (corners, cards, fouls) over goals markets. Use three-source corner stack. Use SoccerStats defensive profiles for BTTS/U2.5. Goals markets are last resort.
E5. For tennis: calculate odds_gap_ratio, assign STRONG/GOOD/BORDERLINE/REJECT grade per exact boundaries in model-ready instructions.
E6. For volleyball: check favorite ML (1.30-2.00 for competitive), semifinal/final context, point total feasibility.

## PHASE F: PORTFOLIO CONSTRUCTION

F1. From approved candidates, select up to 3 singles (highest confidence picks).
F2. Compose up to **coupon_count** total tickets (singles + coupons combined = coupon_count tickets).
    - If coupon_count = 5 and you have 1 single, build 4 coupons.
    - If coupon_count = 5 and you have 0 singles, build 5 coupons.
    - If the board is weak, produce fewer tickets. Never force action.
F3. Coupon composition rules:
    - First coupon: LOW-RISK COUPON (max 3 legs, confidence 4+, can be single sport)
    - Remaining coupons: HIGHER-RISK COUPON if multi-sport (≥2), or LOW-RISK COUPON if single-sport (e.g., tennis-only)
    - Tennis-only coupons MUST be LOW-RISK (cannot meet higher-risk min 2 sports)
    - Max 2 same-sport legs per coupon
    - Zero event overlap across all tickets
    - Drop BORDERLINE tennis picks (ratio 1.31–1.50) from portfolio rather than forcing them
F4. Assign stakes per config limits. Leave unused bankroll if board is weak.
F5. Total exposure must not exceed daily cap from config.

## PHASE G: ODDS RECHECK

G1. Run the Betclic odds verification script to automatically check live odds for all pending picks:
    ```
    cd /Users/mkoziol/projects/bet && .venv/bin/python3 scripts/verify_betclic_odds.py --betting-day <run_date>
    ```
    This script reads pending picks from picks-ledger.csv, searches Betclic for each match,
    navigates to match pages, and extracts target market odds (Over/Under, Total Games, etc.).
    Results are saved to `betting/data/betclic_verified_odds.json`.
G2. Review the verification output:
    - PASS: odds meet or exceed the acceptance threshold → keep the pick.
    - FAIL: odds below threshold → reject the pick or reduce stake.
    - CHECK: odds could not be extracted automatically → user must verify manually on the Betclic app.
G3. For any pick where verified odds differ significantly from estimated odds, update bookmaker_odds in picks-ledger.csv and recalculate price_gap_pct.
G4. If a pick fails the threshold check, remove it from the portfolio and adjust coupon composition.
G5. Record odds_checked_at_local timestamp.

## PHASE H: ARTIFACT GENERATION

H1. Write or update betting/reports/YYYY-MM-DD.md (all 10 required sections).
H2. Write or update betting/coupons/YYYY-MM-DD.txt (exact template from model-ready instructions).
H3. Update betting/journal/picks-ledger.csv — reuse existing IDs, do not duplicate.
H4. Update betting/journal/coupons-ledger.csv — reuse existing IDs, do not duplicate.
H5. Update betting/journal/source-log.csv.
H6. Update betting/journal/learning-log.md.
H7. If no bets, write NO BET TODAY in report and coupon file, still update logs.

## PHASE I: VALIDATION

I1. Run the full V1–V8 checklist from model-ready-betting.instructions.md.
I2. Fix any failures before presenting results.
I3. Cross-check: every pick_id in coupon file → picks-ledger, every coupon_id → coupons-ledger.
I4. Verify total exposure = sum of stakes, unused = cap - total.

---

## REQUIRED CHAT RESPONSE

After all file updates, respond with:
1. **Settlement:** X picks settled (Y win, Z loss), N coupons settled
2. **Previous day PnL:** ±X.XX PLN (rolling 7d: ±X.XX PLN)
3. **Today's portfolio:** N singles + M coupons = coupon_count tickets
4. **Planned exposure:** X.XX PLN / Y.YY cap (Z.ZZ unused)
5. **Source issues:** list any outages or stale data
6. Brief summary table of all tickets with pick_ids, odds, and stakes