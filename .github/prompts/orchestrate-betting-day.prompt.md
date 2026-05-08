---
name: orchestrate-betting-day
description: "Full daily cycle: 3-phase pipeline with agent-driven analysis at every step."
agent: bet-orchestrator
argument-hint: "run_date=2026-04-27 session=full" or "run_date=2026-04-27 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

**YOU ARE AN ANALYST, NOT A SCRIPT RUNNER.**

Scripts produce raw data. Your job is to THINK about that data, DELEGATE to specialist agents, and REACT to what you find. If you ever catch yourself just running a script and moving on — STOP. That is the anti-pattern this prompt exists to prevent.

## INPUTS

- **run_date** = {{run_date}} (default: today)
- **session** = {{session}} (default: `full`). Options: `full` (06:00→05:59), `day` (06:00→21:59), `night` (22:00→05:59), `morning` (06:00→14:59)
- **rerun** = {{rerun}} (default: `false`)
- **version** = {{version}} (default: `v1`)
- Timezone: Europe/Warsaw (CEST). Bookmaker: Betclic.

---

## STEP 0: LOAD CONTEXT (do this ONCE before anything else)

Read these files. Do NOT proceed until all are loaded:
1. `config/betting_config.json`
2. `.github/instructions/analysis-methodology.instructions.md`
3. `.github/instructions/betting-artifacts.instructions.md`
4. `betting/sources/source-registry.md`
5. `/memories/repo/pipeline-lessons-learned.md`

Print the pre-flight checklist:
```
[ ] Bankroll: ___ PLN | Daily budget: ___-___ PLN
[ ] Session: {session} → window: HH:MM → HH:MM
[ ] Sports: 14 | Previous day settled: yes/no
[ ] Memory loaded: yes/no (mistakes count: ___)
```

---

## THE EXECUTION LOOP

**Follow this EXACTLY. Each phase has: RUN → STOP → ANALYZE → DELEGATE → DECIDE.**

### ═══════════════════════════════════════════════
### PHASE 1: DATA COLLECTION (S0→S2.5)
### ═══════════════════════════════════════════════

**RUN:**
```bash
python3 scripts/pipeline_orchestrator.py --date {date} --phase data --session {session} [--version {version}] 2>&1 | tail -200
```

**▸ MANDATORY STOP. Do NOT type another command. Instead, do ALL of the following:**

**1. ANALYZE the terminal output using `sequentialthinking`:**
- How many events found? Across how many sports?
- Which steps succeeded, which failed/timed out?
- Any scan errors or source failures?
- Read `/memories/repo/pipeline-lessons-learned.md` — does this match a known failure pattern?

**2. RUN validation:**
```bash
python3 scripts/validate_phase.py --date {date} --phase data --format json
```

**3. ANALYZE validation results using `sequentialthinking`:**
- For each FAIL: WHY did it fail? Root cause, not symptom.
- For each WARN: Is this acceptable today?
- Do the numbers make sense together? (200 fixtures + 0 team_form = enrichment didn't run)
- What is the downstream impact on S3 analysis?

**4. DELEGATE to specialist agents for deep review (use `runSubagent`):**

Delegate to **bet-scanner** — read `.github/internal-prompts/bet-scan.prompt.md` first, then ask:
```
Review Phase 1 data output for {date}:
1. Are ALL 14 sports represented in scan? Which sources succeeded/failed?
2. Any phantom fixtures or timezone conversion errors?
3. Are active major tournaments present (§SCAN.7)?
4. Is shortlist quality reasonable? Minor league value applied (§SCAN.8)?
Return: APPROVED/FLAGGED/REJECTED with specific issues.
```

Delegate to **bet-enricher** — read `.github/internal-prompts/bet-enrich.prompt.md` first, then ask:
```
Review Phase 1 enrichment output for {date}:
1. What % of candidates have sufficient stats for S3?
2. Which sports/leagues have no data? Are gaps recoverable?
3. Which sources are degraded today?
Return: APPROVED/FLAGGED/REJECTED with data quality assessment per sport.
```

**5. DECIDE:**
- Both APPROVED → proceed to Phase 2
- Any FLAGGED → fix issues, re-validate (max 2 retries)
- Any REJECTED → STOP, ask user via `askQuestions` what to do
- Write status to `/memories/session/`

### ═══════════════════════════════════════════════
### PHASE 2: ANALYSIS (S3→S7)
### ═══════════════════════════════════════════════

**RUN:**
```bash
python3 scripts/pipeline_orchestrator.py --date {date} --phase analysis [--resume] 2>&1 | tail -200
```

**▸ MANDATORY STOP. Do NOT type another command. Instead:**

**1. ANALYZE using `sequentialthinking`:**
- Did candidate count drop significantly between shortlist and S3? WHY?
- Are gate tier distributions reasonable? (>80% FLAGGED = gate calibration issue)
- Did S3 produce genuine analytical reasoning or just repeat numbers?
- Any contradictions between S4 (odds) and S3 (stats)?

**2. RUN validation:**
```bash
python3 scripts/validate_phase.py --date {date} --phase analysis --format json
```

**3. DELEGATE specialist reviews (use `runSubagent`):**

Delegate to **bet-statistician** — read `.github/internal-prompts/bet-deep-stats.prompt.md` first:
```
Review S3 analysis output for {date}:
1. Does EVERY candidate have ANALYTICAL REASONING with edge mechanism?
2. R5: every football candidate has ≥1 stat market (corners/fouls/shots)?
3. Three-way alignment: L10+H2H+L5 cross-check for every market?
4. Run validate_s3_output.py — are ALL candidates PASS?
Return: APPROVED/FLAGGED/REJECTED, quality score 1-10, specific issues.
```

Delegate to **bet-challenger** — read `.github/internal-prompts/bet-gate.prompt.md` first:
```
Review S7 gate output for {date}:
1. All 18 points evaluated per candidate (not abbreviated)?
2. Bear cases cite specific data (not "it could go wrong")?
3. R4: ≥5 sports in approved picks?
4. Extended Pool: gate-failed EV>0 candidates documented?
Return: APPROVED/FLAGGED/REJECTED, gate quality assessment.
```

**4. DECIDE:** Same rules as Phase 1.

### ═══════════════════════════════════════════════
### PHASE 3: BUILD (S8→S10)
### ═══════════════════════════════════════════════

**RUN:**
```bash
python3 scripts/pipeline_orchestrator.py --date {date} --phase build [--resume] 2>&1 | tail -200
```

**▸ MANDATORY STOP. Do NOT type another command. Instead:**

**1. ANALYZE using `sequentialthinking`:**
- Does the portfolio make strategic sense?
- Are coupon groupings intelligent? (correlation avoidance, sport diversity)
- Is exposure distribution reasonable?
- Do Polish descriptions accurately describe markets?

**2. RUN validation:**
```bash
python3 scripts/validate_phase.py --date {date} --phase build --format json
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json
```

**3. DELEGATE to bet-builder** — read `.github/internal-prompts/bet-portfolio.prompt.md` first:
```
Review build output for {date}:
1. Coupon arithmetic: multiply each leg step-by-step — combined odds match (±0.02)?
2. Unique events: zero shared events between core coupons?
3. Sport diversity: ≥5 sports across portfolio?
4. R5: ≥60% statistical markets in legs?
5. Exposure: total stakes ≤25% bankroll?
6. V1-V10 + §S8.FINAL: ALL checks PASS?
7. Conditional disclaimer present?
Return: APPROVED/FLAGGED/REJECTED with arithmetic verification.
```

**4. DECIDE:** Same rules as Phase 1.

### ═══════════════════════════════════════════════
### PHASE 4: PRESENT RESULTS
### ═══════════════════════════════════════════════

Only after ALL 3 phases pass validation + agent review:

Present to user:
1. **Settlement Summary** — Previous day PnL, rolling 7-day, bankroll
2. **Scan Summary** — Session type, event window, events per sport, completeness %
3. **FULL STATISTICAL MATRIX** — ALL S3-analyzed candidates with ALL stat markets. User selects from this. Columns: Event | Market | Direction | Line | L10 hit% | H2H hit% | Safety | P(hit) | Min kurs | 3-Way | Data Quality
4. **Final Coupons** — legs, combined odds (arithmetic shown), stake, type
5. **Extended Pool** — EV>0 picks that did not fully pass gate
6. **Watchlist** — picks awaiting triggers

---

## ANTI-PATTERNS (you MUST avoid these)

1. **❌ Run script → show output → done.** Scripts are calculators. You are the analyst. ALWAYS think about the output.
2. **❌ Skip sequential thinking.** Every phase MUST have a `sequentialthinking` call analyzing results.
3. **❌ Skip agent delegation.** Every phase MUST delegate to specialist agents via `runSubagent`.
4. **❌ Proceed despite failures.** If validation fails or agent returns REJECTED, STOP and fix.
5. **❌ Run full pipeline in one command.** ALWAYS 3 separate phases with analysis between each.
6. **❌ Present raw script output to user.** ALL output passes through agent review first.
7. **❌ Forget to read internal prompts.** Before each `runSubagent` call, READ the internal-prompt file to include as context.

---

## RULES ENFORCEMENT (R1-R12)

These rules apply to EVERY step. Violation = pipeline failure.

| Rule | What to check |
|------|--------------|
| R1 AGENT-DRIVEN | Script ran → agent analyzed → reasoned output produced |
| R3 NO AUTO-REJECTION | ALL candidates in matrix. No "rejected due to" language |
| R4 NO NARROWING | ≥5 sports in approved picks |
| R5 STATS > OUTCOMES | Every football match has ≥1 stat market |
| R6 BETCLIC ADVISORY | Hit rates shown, never auto-penalize |
| R7 TOURNAMENT PROTECTION | Major tournaments present |
| R8 MINOR LEAGUE VALUE | No "obscure" penalties |
| R10 STATS-FIRST | Events without odds NOT excluded |
| R11 SEQUENTIAL THINKING | `sequentialthinking` used per phase + per candidate |
| R12 CONDITIONAL | Coupon carries conditional disclaimer |

---

## DELEGATION REFERENCE

| Step | Internal Prompt | Agent |
|------|----------------|-------|
| S0 Settlement | `bet-settle.prompt.md` | bet-settler |
| S1 Scan | `bet-scan.prompt.md` | bet-scanner |
| S1e Shortlist | `bet-shortlist.prompt.md` | bet-scanner |
| S2 Tipsters | `bet-tipsters.prompt.md` | bet-scout |
| S2.5 Enrichment | `bet-enrich.prompt.md` | bet-enricher |
| S3 Deep Stats | `bet-deep-stats.prompt.md` | bet-statistician |
| S3B Time-Sensitive | `bet-time-sensitive.prompt.md` | bet-statistician |
| S4 Odds/EV | `bet-odds-ev.prompt.md` | bet-valuator |
| S5 Context | `bet-context-upset.prompt.md` | bet-challenger |
| S6 Upset Risk | `bet-context-upset.prompt.md` | bet-challenger |
| S7 Gate | `bet-gate.prompt.md` | bet-challenger |
| S8 Portfolio | `bet-portfolio.prompt.md` | bet-builder |
| S9 Validation | `bet-validate.prompt.md` | bet-builder |

All internal prompts are in `.github/internal-prompts/`. Read them before delegating.

---

## RERUN PROTOCOL (when rerun=true)

1. Scan `betting/coupons/{date}*.md` for highest version → next version
2. New picks get NEW IDs. Old pending → `superseded`
3. Ledger: ADD new rows, keep old
4. Create `betting/coupons/{date}-v{N}.md`
5. ALL steps run from scratch

## SESSION PARITY

ALL sessions execute the SAME pipeline. Only the time window differs. Night/morning sessions get FULL analysis (H2H, tipsters, injuries, bear cases). If <3 picks survive → declare NO BET.

## KNOWN FAILURE PATTERNS

1. **PHANTOM GAMES**: ZT/tipster sites list tips for games that already played. Verify on Flashscore before shortlisting.
2. **BETCLIC LINE MISMATCH**: Do not assume BetExplorer lines = Betclic. When avg ≈ line → zero edge → DROP.
3. **MARKET UNAVAILABILITY**: Top market not on Betclic → need fallback. Check availability BEFORE deep analysis.
4. **INSUFFICIENT PICKS**: If pick drops in S7 → expand shortlist (§2.1), do not accept <4 picks.
5. **MISSING TIPSTER PICKS**: Always scan ZT for statistical-market tips with reasoning.

## §S8.FINAL — MECHANICAL VERIFICATION

After coupons are built, verify:
- **A. ARITHMETIC**: Multiply each leg odds step-by-step. Must match listed combined odds (±0.02).
- **B. PLACEMENT ORDER**: Deadline = earliest kickoff minus 30-60 min.
- **C. CROSS-CHECK**: No orphan picks, no pick in >60% coupons, max 2 same-sport per coupon.
- **D. HOME/AWAY**: US sports: "@" = Away @ Home. BetExplorer: "Home vs Away".
- **E. EV CHECK**: EV = (true_prob × odds) - 1. Labels must match math.
- **F. PRICE GAP**: Flag picks outside threshold (-3% LR, -5% HR).
- **G. EXPOSURE**: Total stakes ≤ 25% bankroll.
- **H. FIX**: Fix in place, re-verify.
- **I. MATRIX COMPLETENESS**: ALL analyzed events in matrix. No auto-rejection language.

## PIPELINE COMMANDS

```bash
# Phase execution (ALWAYS use phases, never run full):
python3 scripts/pipeline_orchestrator.py --date YYYY-MM-DD --phase data|analysis|build
python3 scripts/pipeline_orchestrator.py --date YYYY-MM-DD --resume
python3 scripts/pipeline_orchestrator.py --date YYYY-MM-DD --skip-scan

# Validation:
python3 scripts/validate_phase.py --date YYYY-MM-DD --phase data|analysis|build --format json
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json

# Individual tools:
python3 scripts/analyze_betclic_learning.py
python3 scripts/fetch_odds_api.py [--scores baseball,hockey]
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
python3 scripts/check_48h_repeats.py
```

## DB REFERENCE

SQLite at `betting/data/betting.db`. Connection: `from bet.db.connection import get_db`.
28 tables across 6 domains: Core (sports/teams/competitions/fixtures/athletes), Stats (team_form/match_stats/league_profiles/standings/power_index), Analysis (analysis_results/gate_results/decision_snapshots), Betting (coupons/bets/odds_history), Pipeline (pipeline_runs/scan_results/source_health), ESPN (espn_predictions/player_gamelogs/team_ats_records/team_ou_records).
