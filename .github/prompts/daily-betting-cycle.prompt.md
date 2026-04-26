---
name: daily-betting-cycle
description: "Full daily cycle: settle previous day, scan events, deep analysis (EV/CLV/Kelly), build unique-event diversified coupons."
agent: bet-analyst
argument-hint: "run_date=2026-04-25 session=night" or "run_date=2026-04-25 session=full rerun=true"
tools:
  - search
  - editFiles
  - runCommands
  - terminalLastCommand
  - changes
  - memory/*
  - sequentialthinking/*
---

## Inputs

- **run_date** = ${input:run_date:today}
  If "today" or empty, use the current calendar date.
- **session** = ${input:session:full}
  Controls which events to analyze:
  - `full` — entire betting day (06:00 → 05:59 next day). Default.
  - `day` — daytime events only (06:00 → 21:59).
  - `night` — night events only (22:00 → 05:59 next day). SAME full process as `full` session — all 14 sports scanned, all steps 0-10, min 5 coupons. Only the event time window differs.
  - `morning` — settle overnight results + scan early events (06:00 → 14:59).
- **rerun** = ${input:rerun:false}
  When `true`, forces a complete fresh analysis for run_date, even if artifacts already exist:
  - Settlement (STEP 1) is SKIPPED if previous day was already settled.
  - Orchestrator is re-run to get fresh data (forced, even if scan_summary.json exists).
  - **Versioning (CRITICAL):** Previous picks and coupons are PRESERVED, not replaced. New analysis creates a new version:
    - Determine next version: scan `betting/coupons/YYYY-MM-DD*.md` for highest existing version (e.g., v5 → next is v6). If no versioned file, start at v1.
    - New picks get NEW pick_ids (next available PK-YYYYMMDD-## after the highest existing one for that day).
    - New coupons get versioned coupon_ids (e.g., CP-YYYYMMDD-PD1v6).
    - picks-ledger.csv: ADD new rows with `version=vN`. Old version rows stay untouched.
    - coupons-ledger.csv: ADD new rows with `version=vN`. Old version rows stay untouched.
    - Coupon file: create `betting/coupons/YYYY-MM-DD-vN.md`. Previous version files are kept.
    - Report file: create `betting/reports/YYYY-MM-DD-vN.md`. Previous version files are kept.
    - The user sees ALL versions in the ledger and compares them to decide which to place.
    - Set old version's pending picks/coupons to `status=superseded` (new status value).
  - ALL analysis steps (3-8) run from scratch — do NOT reuse previous analysis or picks.
  - Learning-log gets an entry noting the rerun and reason (methodology change, new sources, etc.).
- **bookmaker** = Betclic
- **local_timezone** = Europe/Warsaw
- Load all other parameters from `config/betting_config.json` (bankroll, stakes, caps, thresholds, sports).

## References

Follow [methodology STEPS 0-10](../instructions/analysis-methodology.instructions.md) — the SINGLE SOURCE OF TRUTH for all analysis steps.
Also: [artifact rules](../instructions/betting-artifacts.instructions.md), [sport protocols](../instructions/sport-analysis-protocols.instructions.md) (load for STEP 3+), [source registry](../../betting/sources/source-registry.md).

**MANDATORY: Use `sequentialthinking` for EVERY STEP (0-10). Per-candidate steps (3-7) = one call PER candidate.**

---

## STEP -1: INSTRUCTION LOADING (ALWAYS FIRST — NEVER SKIP)

Load ALL files below. Do NOT proceed until all are loaded.

```
REQUIRED READS:
1. config/betting_config.json — bankroll, caps, sports list, betting_window_days
2. .github/instructions/analysis-methodology.instructions.md — STEPS 0-10, V1-V10
3. .github/instructions/betting-artifacts.instructions.md — output formats
4. .github/instructions/sport-analysis-protocols.instructions.md — sport stats, upset checklists, red flags
5. betting/sources/source-registry.md — source tiers + blocked list
6. /memories/common-mistakes.md — lessons learned
7. /memories/betting-workflow-rules.md — workflow rules
8. /memories/analysis-principles.md — permanent principles
```

**PRE-FLIGHT CHECKLIST (print before proceeding):**
```
[ ] Bankroll: ___ PLN | Daily budget: ___-___ PLN
[ ] Session: {{session}} → window: HH:MM → HH:MM
[ ] Sports: 14 confirmed | betting_window_days: ___
[ ] Previous day settled: yes/no
[ ] Files loaded: 8/8 | Memory: 3/3
[ ] Blocked sources reviewed | Common mistakes reviewed (count: ___)
[ ] Market hit rates checked in picks-ledger | 48h repeat check ready
```

---

## SETUP + ORCHESTRATOR

1. Resolve event window from **session**:
   - `full`: 06:00 run_date → 05:59 next day
   - `day`: 06:00 → 21:59 run_date
   - `night`: 22:00 run_date → 05:59 next day
   - `morning`: 06:00 → 14:59 run_date
2. Check `betting_window_days` in config — if >1, extend scan window to cover N days.
3. Ensure artifact dirs exist. Run orchestrator if scan data stale:
   ```
   cd /Users/mkoziol/projects/bet && bash scripts/run_full_scan_and_prepare.sh
   ```
4. Run `python3 scripts/fetch_odds_api.py` for cross-validation odds.
5. Check `betting/data/scan_errors.json` for source failures.

**If rerun=true:**
- Re-run orchestrator regardless of data freshness.
- Determine next version: scan `betting/coupons/YYYY-MM-DD*.md` for highest vN → next is v(N+1).
- New picks get NEW pick_ids (next available after highest existing for that day).
- Mark old `pending` picks/coupons as `status=superseded`. Add new rows — never overwrite.
- ALL steps run from scratch. Learning-log gets rerun entry.

---

## EXECUTE STEPS 0-10

Follow [analysis-methodology.instructions.md](../instructions/analysis-methodology.instructions.md) STEPS 0-10 exactly. Key reminders:

- **STEP 0 (Settle):** Skip if rerun=true and already settled, or night session with day already settled.
- **STEPS 1-2 (Scan + Filter):** Pass `session` window to filter events. All 14 sports, deep scan, completeness gate.
- **STEPS 3-7 (Analysis per candidate):** Load sport-protocols. One `sequentialthinking` call PER candidate.
- **STEP 3B (Time-sensitive):** Run 2-3h before earliest kickoff. Lineups, injuries, weather, odds drift.
- **STEP 8 (Portfolio):** Unique event per coupon. Coupon count = f(quality), NOT f(money).
- **STEP 9 (V1-V10):** Full validation including V10e completeness matrix.
- **STEP 10 (Artifacts):** Write coupon file, ledgers, report, source-log. All picks CONDITIONAL (Betclic 403).

### Additional rules (not in methodology):
- **MARKET PERFORMANCE TRACKER:** Before picking any market, check hit rate in picks-ledger. If <40% on 10+ picks → AUTO-DOWNGRADE confidence -1. If <30% → WATCHLIST ONLY.
- **MLB CAUTION ZONE:** MLB totals hit rate 33% (3W/6L). Until >50%, all MLB totals get -1 confidence. MLB overs ≥8.5 → HARD REJECT.

### Artifact naming:
- Report: `betting/reports/YYYY-MM-DD.md` (or `-night.md`, `-morning.md`)
- Coupon: `betting/coupons/YYYY-MM-DD.md` (or `-night.md`, `-vN.md` for reruns)
- Ledgers: `betting/journal/picks-ledger.csv`, `coupons-ledger.csv`, `source-log.csv`, `learning-log.md`

---

## REQUIRED RESPONSE

After all artifacts are written, respond with:

1. **Settlement:** X picks settled (Y win, Z loss), N coupons settled
2. **Previous day PnL:** ±X.XX PLN (rolling 7d: ±X.XX PLN, bankroll: XX.XX PLN)
3. **Session:** {{session}} — event window HH:MM → HH:MM
4. **Board:** N events scanned (X sports, Y events, Z% completeness) → M shortlisted → K approved (L rejected, W watchlist)
5. **Portfolio:** M coupons (unique-event: each pick in exactly 1 coupon)
6. **Exposure:** X.XX PLN / Y.YY cap (Z.ZZ unused, W.WW% of bankroll)
7. **Source issues:** any outages or stale data
8. Summary table: all picks with pick_ids, market, odds, stake, EV, confidence
9. **Watch List:** backup picks with promotion criteria
10. **Conditional picks:** ALL picks with acceptance thresholds for Betclic
11. **Validation summary:** V8 source audit + V9 coupon optimization results