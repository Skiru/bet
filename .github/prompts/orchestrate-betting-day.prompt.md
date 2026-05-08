---
name: orchestrate-betting-day
description: "Agent-driven daily cycle: YOU are the orchestrator. Scripts are tools. NEVER run pipeline_orchestrator.py."
agent: bet-orchestrator
argument-hint: "run_date=2026-05-08 session=full" or "run_date=2026-05-08 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

## ⛔ ABSOLUTE BAN: `pipeline_orchestrator.py`

**NEVER run `python3 scripts/pipeline_orchestrator.py` — not with `--phase`, not with `--step`, not with any flags.**

That script is a DUMB automation wrapper. It runs for 1-2 hours, produces zero agent analysis, enforces zero methodology, and defeats the entire purpose of this system.

**YOU are the orchestrator.** You call individual scripts ONE AT A TIME. You THINK between every call. You DELEGATE to specialist agents. You FIX issues in real-time. You ENFORCE the methodology.

---

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

## THE EXECUTION PROTOCOL

**Every step follows the same atomic pattern:**
```
1. RUN: One script, one purpose, ≤10 min
2. CHECK: Read output, verify sanity (file exists, not empty, reasonable numbers)
3. THINK: sequentialthinking — analyze what was produced, catch issues
4. DELEGATE: runSubagent to specialist agent for quality review
5. DECIDE: PROCEED / FIX+RETRY / ESCALATE to user
```

**If a script takes >10 minutes:** Run in async mode. Check output every 60 seconds. Monitor for errors.

**Between EVERY step:** You MUST use `sequentialthinking`. No exceptions. This is where methodology enforcement happens.

---

## ═══════════════════════════════════════════════
## DATA COLLECTION (Steps S0 → S2.5)
## ═══════════════════════════════════════════════

### STEP S0: Settlement + History

```bash
python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll 2>&1 | tail -30
python3 scripts/evaluate_decisions.py --date {prev_date} 2>&1 | tail -30
python3 scripts/analyze_betclic_learning.py 2>&1 | tail -50
python3 scripts/data_rotation.py --execute --days 30 2>&1 | tail -10
```

**AFTER:** Read `betting/data/betclic_learning_summary.json`. Use `sequentialthinking` to extract key patterns. Delegate to **bet-settler** if PnL issues.

---

### STEP S1: Event Scan (longest step — use async)

```bash
# Run parallel-sport scan — takes 10-20 min
python3 scripts/scan_events.py --parallel-sport --date {date} --deep --max-deep-links 30 --workers 8 2>&1 | tail -60
```

**WHILE RUNNING:** Check output periodically. Look for per-sport completion messages.

**AFTER:** Use `sequentialthinking`:
- How many events per sport?
- Which sports had 0 events? (source failure)
- Any timeout errors?

```bash
# Quick validation
python3 -c "
import json
from pathlib import Path
summary = json.loads(Path('betting/data/scan_summary.json').read_text())
print(f'Total events: {summary.get(\"total_events\", 0)}')
for sport, data in summary.get('per_sport', {}).items():
    print(f'  {sport}: {data.get(\"events\", 0)} events, {data.get(\"sources_ok\", 0)} sources OK')
"
```

**Delegate to bet-scanner** (read `.github/internal-prompts/bet-scan.prompt.md` first):
- 14-sport coverage check
- Phantom fixture detection
- Tournament protection (§SCAN.7)
- Minor league value (§SCAN.8)

---

### STEP S1-ingest: Ingest Scan Stats

```bash
python3 scripts/ingest_scan_stats.py 2>&1 | tail -20
```

---

### STEP S1-deep: HTML Deep Parsing

```bash
python3 scripts/html_deep_parser.py --date {date} --report 2>&1 | tail -40
```

**AFTER:** `sequentialthinking` — Were key stats extracted? Any broken CSS selectors?

---

### STEP S1a: Fixture Discovery + API Stats

```bash
python3 scripts/discover_fixtures.py --date {date} 2>&1 | tail -30
python3 scripts/fetch_api_stats.py --date {date} 2>&1 | tail -30
python3 scripts/enrich_tennis_stats.py --date {date} --all-indexed 2>&1 | tail -20
python3 scripts/seed_espn_data.py --skip-players 2>&1 | tail -30
```

**AFTER:** `sequentialthinking` — How many fixtures discovered? Coverage gaps?

---

### STEP S1b: Odds + Weather + Tipsters

```bash
python3 scripts/fetch_odds_api.py 2>&1 | tail -30
python3 scripts/fetch_weather.py --date {date} 2>&1 | tail -20
python3 scripts/tipster_xref.py --date {date} 2>&1 | tail -30
```

**AFTER:** `sequentialthinking` — Odds coverage? Weather impacts? Tipster consensus?

---

### STEP S1c: Aggregate + Analysis Pool

```bash
python3 scripts/aggregate_and_select.py --date {date} 2>&1 | tail -30
python3 scripts/deep_analysis_pool.py --date {date} 2>&1 | tail -30
```

---

### STEP S1d: Market Matrix

```bash
python3 scripts/generate_market_matrix.py --date {date} --stats-first 2>&1 | tail -30
```

**AFTER:** Verify matrix file exists and has entries.

---

### STEP S1e: Build Shortlist

```bash
python3 scripts/build_shortlist.py --date {date} --stats-first 2>&1 | tail -40
```

**AFTER — CRITICAL CHECKPOINT:**
```bash
python3 -c "
import json
from pathlib import Path
from collections import Counter
# Try both date formats
for fmt in ['{date}', '{date_compact}']:
    p = Path(f'betting/data/{{fmt}}_s2_shortlist.json')
    if p.exists():
        data = json.loads(p.read_text())
        candidates = data.get('candidates', [])
        sports = Counter(c.get('sport','?') for c in candidates)
        print(f'Shortlist: {{len(candidates)}} candidates across {{len(sports)}} sports')
        for s, n in sports.most_common():
            print(f'  {{s}}: {{n}}')
        break
"
```

Use `sequentialthinking`:
- ≥20 candidates? If not → something failed upstream
- ≥8 sports? If not → scan coverage issue
- KEY sports (football, tennis, basketball, volleyball) ≥60% of candidates?
- Major tournaments present?

**Delegate to bet-scanner** (read `.github/internal-prompts/bet-shortlist.prompt.md`):
- Sport diversity assessment
- Tournament protection verification
- Minor league value check

---

### STEP S2: Tipster Cross-Reference

```bash
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0, 'scripts')
from tipster_xref import run_tipster_xref
ok, msg = run_tipster_xref('{date}', {{}})
print(msg)
" 2>&1 | tail -30
```

**Delegate to bet-scout** (read `.github/internal-prompts/bet-tipsters.prompt.md`)

---

### STEP S2.5: Data Enrichment

```bash
PYTHONPATH=src python3 scripts/data_enrichment_agent.py --date {date} 2>&1 | tail -50
```

**AFTER — ENRICHMENT QUALITY CHECK:**
```bash
python3 scripts/validate_phase.py --date {date} --phase data --format json 2>&1 | tail -40
```

Use `sequentialthinking`:
- Enrichment yield — what % of candidates have sufficient stats for S3?
- Which sports/leagues still have gaps?
- Is downstream analysis possible?

**Delegate to bet-enricher** (read `.github/internal-prompts/bet-enrich.prompt.md`):
- Data quality per sport
- Gap recoverability
- Source health assessment

**GATE:** If enrichment <40% AND bet-enricher returns REJECTED → STOP, escalate to user.

---

## ═══════════════════════════════════════════════
## ANALYSIS (Steps S3 → S7) — AGENT-INTENSIVE
## ═══════════════════════════════════════════════

> **⚠️ THIS IS WHERE AGENT VALUE IS HIGHEST.**
> Each step here requires DEEP ANALYTICAL THINKING. The scripts produce numbers.
> YOU and the specialist agents produce INSIGHTS, EDGE MECHANISMS, and BEAR CASES.

### STEP S3: Deep Statistical Analysis

```bash
PYTHONPATH=src python3 scripts/deep_stats_report.py --date {date} --shortlist betting/data/{date_shortlist_file} --top 200 2>&1 | tail -60
```

**⚠️ This takes 5-15 min. Run in async mode if needed. Monitor progress.**

**AFTER — MANDATORY QUALITY AUDIT:**

1. Read the output: `betting/data/{date}_s3_deep_stats.md` (first 200 lines to assess)
2. Use `sequentialthinking` — CRITICAL analysis:
   - Does EVERY candidate have analytical reasoning (not just numbers)?
   - Are statistical markets prioritized (R5)?
   - Three-way alignment present (L10+H2H+L5)?
   - Any football candidate missing corners/fouls/shots market?
   - Safety scores reasonable (not all 0.0 or all 1.0)?
   - Edge mechanisms articulated?

3. Run validation:
```bash
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json 2>&1 | tail -30
```

4. **Delegate to bet-statistician** (read `.github/internal-prompts/bet-deep-stats.prompt.md`):
```
Review S3 output for {date}:
- Read: betting/data/{date}_s3_deep_stats.md
- Verify: ANALYTICAL REASONING per candidate (not just tables)
- Check: R5 compliance (stat markets FIRST)
- Check: Three-way cross-check (L10+H2H+L5)
- Check: H2H market-specific validation (§3.0c)
- Validate: Run validate_s3_output.py
- Return: APPROVED/FLAGGED/REJECTED + quality score 1-10 + specific issues
```

5. **If FLAGGED:** Fix issues (re-run specific candidates, fetch missing data)
6. **If REJECTED:** Escalate to user

---

### STEP S4: Odds Evaluation

```bash
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0, 'scripts')
from odds_evaluator import run_odds_eval
ok, msg = run_odds_eval('{date}', {{}})
print(msg)
" 2>&1 | tail -30
```

**AFTER:** `sequentialthinking` — EV distribution, pricing anomalies, drift flags.

**Delegate to bet-valuator** (read `.github/internal-prompts/bet-odds-ev.prompt.md`)

---

### STEP S5: Contextual Checks

```bash
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0, 'scripts')
from context_checks import run_context_checks
ok, msg = run_context_checks('{date}', {{}})
print(msg)
" 2>&1 | tail -30
```

---

### STEP S6: Upset Risk Scoring

```bash
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0, 'scripts')
from upset_risk import run_upset_risk
ok, msg = run_upset_risk('{date}', {{}})
print(msg)
" 2>&1 | tail -30
```

**AFTER S5+S6:** `sequentialthinking` — which candidates have compounding risk factors?

**Delegate to bet-challenger** (read `.github/internal-prompts/bet-context-upset.prompt.md`):
- Context flags with REAL market impact
- Upset risk with sport-specific reasoning
- Compounding factor identification

---

### STEP S7: 18-Point Advisory Gate

```bash
PYTHONPATH=src python3 scripts/gate_checker.py --date {date} 2>&1 | tail -50
```

**AFTER — CRITICAL GATE REVIEW:**

Use `sequentialthinking`:
- Tier distribution: >80% FLAGGED = gate calibration issue
- ≥5 sports in STRONG+MODERATE tiers? (R4)
- Any auto-rejection language? (R3 violation)
- Extended Pool populated?

**Delegate to bet-challenger** (read `.github/internal-prompts/bet-gate.prompt.md`):
```
Review S7 gate for {date}:
- All 18 points evaluated per candidate (not abbreviated)?
- Bear cases cite SPECIFIC DATA (not generic "it could go wrong")?
- R4: ≥5 sports in approved picks?
- R3: NO auto-rejection — ALL candidates visible in output?
- Extended Pool: gate-failed EV>0 candidates documented?
- Return: APPROVED/FLAGGED/REJECTED + gate quality assessment
```

**GATE:** If <5 sports in approved → emergency expansion (R4). Analyze ALL remaining shortlist candidates.

---

## ═══════════════════════════════════════════════
## BUILD (Steps S8 → S10)
## ═══════════════════════════════════════════════

### STEP S8: Build Coupons

```bash
PYTHONPATH=src python3 scripts/coupon_builder.py --date {date} 2>&1 | tail -40
```

**AFTER:** `sequentialthinking` — Portfolio strategy, correlation, exposure.

---

### STEP S9: Validate Coupons

```bash
python3 scripts/validate_phase.py --date {date} --phase build --format json 2>&1 | tail -30
```

**Delegate to bet-builder** (read `.github/internal-prompts/bet-portfolio.prompt.md`):
```
Review coupons for {date}:
- Arithmetic: multiply each leg odds step-by-step → combined odds match (±0.02)?
- Unique events: zero shared events between core coupons?
- Sport diversity: ≥5 sports across portfolio?
- R5: ≥60% statistical markets?
- Exposure: total stakes ≤25% bankroll?
- V1-V10 + §S8.FINAL: ALL checks PASS?
- Conditional disclaimer present?
Return: APPROVED/FLAGGED/REJECTED with arithmetic verification
```

---

### STEP S10: Final Summary

```bash
PYTHONPATH=src python3 -c "
import sys; sys.path.insert(0, 'scripts')
from pipeline_summary import run_summary
ok, msg = run_summary('{date}', {{}})
print(msg)
" 2>&1 | tail -30
```

---

## ═══════════════════════════════════════════════
## PRESENT RESULTS TO USER
## ═══════════════════════════════════════════════

Only after ALL steps pass validation + agent review:

Present to user:
1. **Settlement Summary** — Previous day PnL, rolling 7-day, bankroll
2. **Scan Summary** — Session type, event window, events per sport, completeness %
3. **FULL STATISTICAL MATRIX** — ALL S3-analyzed candidates with ALL stat markets. Columns: Event | Market | Direction | Line | L10 hit% | H2H hit% | Safety | P(hit) | Min kurs | 3-Way | Data Quality
4. **Final Coupons** — legs, combined odds (arithmetic shown), stake, type
5. **Extended Pool** — EV>0 picks that did not fully pass gate
6. **Watchlist** — picks awaiting triggers

---

## ⛔ ANTI-PATTERNS (HARD FAILURES)

| # | Anti-Pattern | Why it kills the pipeline |
|---|---|---|
| 1 | Run `pipeline_orchestrator.py` | Dumb script, no agent analysis, runs 1-2h blind |
| 2 | Run `--phase data/analysis/build` | Bundles steps, removes agent control points |
| 3 | Run script → show output → done | Script = calculator. You = analyst. THINK. |
| 4 | Skip `sequentialthinking` between steps | No methodology enforcement without thinking |
| 5 | Skip `runSubagent` delegation | Specialist agents catch what you miss |
| 6 | Proceed despite validation failure | Garbage in → garbage out |
| 7 | Present raw script output to user | User gets ANALYZED output, not log dumps |
| 8 | Run S3-S7 as one batch | Each analytical step needs separate agent review |
| 9 | Run any script >15 min synchronously | Use async mode + periodic monitoring |

---

## RULES ENFORCEMENT (R1-R12)

| Rule | What to check | When |
|------|--------------|------|
| R1 AGENT-DRIVEN | Script ran → agent analyzed → reasoned output | Every step |
| R3 NO AUTO-REJECTION | ALL candidates visible. No "rejected due to" | S7, S8 |
| R4 NO NARROWING | ≥5 sports in approved picks | S7 gate |
| R5 STATS > OUTCOMES | Every football match ≥1 stat market | S3, S8 |
| R6 BETCLIC ADVISORY | Hit rates shown, never auto-penalize | S0, S3 |
| R7 TOURNAMENT PROTECTION | Major tournaments present | S1e |
| R8 MINOR LEAGUE VALUE | No "obscure" penalties | S1e |
| R10 STATS-FIRST | Events without odds NOT excluded | S4, S7 |
| R11 SEQUENTIAL THINKING | sequentialthinking per step + per candidate in S3 | ALL |
| R12 CONDITIONAL | Coupon carries conditional disclaimer | S8 |

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

All internal prompts are in `.github/internal-prompts/`. **Read them BEFORE delegating.**

---

## RERUN PROTOCOL (when rerun=true)

1. Scan `betting/coupons/{date}*.md` for highest version → next version
2. New picks get NEW IDs. Old pending → `superseded`
3. Ledger: ADD new rows, keep old
4. Create `betting/coupons/{date}-v{N}.md`
5. ALL steps run from scratch

## SESSION PARITY

ALL sessions execute the SAME pipeline. Only the time window differs. Night/morning sessions get FULL analysis. If <3 picks survive → declare NO BET.

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

## VALIDATION COMMANDS (use BETWEEN steps)

```bash
# Phase-level validation:
python3 scripts/validate_phase.py --date {date} --phase data|analysis|build --format json

# S3 output validation:
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json

# Coupon validation:
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
