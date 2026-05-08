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

> **⛔ YOU DO NOT RUN SCRIPTS YOURSELF (except S0 settlement + trivial file checks).**
> **The specialist agents run scripts, think, analyze, and return verdicts.**
> **You are a COORDINATOR — you delegate, receive verdicts, and decide next steps.**

**Every step follows this pattern:**
```
1. DELEGATE: runSubagent(specialist_agent) — pass: date, internal prompt content, input files, issues
2. AGENT WORKS: Specialist runs script + sequentialthinking + loads skills + validates output
3. RECEIVE: Agent returns APPROVED/FLAGGED/REJECTED + quality_score + specific_issues[]
4. DECIDE: PROCEED (if APPROVED) / FIX+RETRY (if FLAGGED) / ESCALATE to user (if REJECTED)
```

**What YOU do between steps:**
- Use `sequentialthinking` to evaluate the agent's verdict — do you agree? Any red flags?
- Check that methodology rules (R1-R12) are respected in the agent's output
- Verify sport diversity, statistical market coverage, and gate compliance

**What you NEVER do:**
- Run `deep_stats_report.py`, `data_enrichment_agent.py`, `gate_checker.py`, `coupon_builder.py`, or any analytical script yourself
- Analyze statistical output yourself (that's bet-statistician's job)
- Build bear cases yourself (that's bet-challenger's job)
- Evaluate odds yourself (that's bet-valuator's job)

**The ONLY scripts you may run directly:**
- `settle_on_finish.py` + `analyze_betclic_learning.py` (S0 — lightweight, pre-pipeline)
- `scan_events.py` (S1 — launches parallel scan, but bet-scanner reviews output)
- Simple validation one-liners: file existence, line counts, JSON key checks
- `validate_phase.py` (quick sanity gate between phases)

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

**You launch the scan, then delegate review to bet-scanner.**

```bash
# Run parallel-sport scan — takes 10-20 min
python3 scripts/scan_events.py --parallel-sport --date {date} --deep --max-deep-links 30 --workers 8 2>&1 | tail -60
```

**WHILE RUNNING:** Check output periodically. Look for per-sport completion messages.

**AFTER scan completes — Delegate to bet-scanner** (read `.github/internal-prompts/bet-scan.prompt.md` first):

```
runSubagent("bet-scanner"):
---
## Task: S1 Scan Review for {date}

[Paste content of .github/internal-prompts/bet-scan.prompt.md]

### Context
- Date: {date}, Session: {session}
- Scan already completed. Review output quality.
- Check: betting/data/scan_summary.json
- Use sequentialthinking to evaluate coverage
- Load skill: bet-navigating-sources
- Key checks:
  - 14-sport coverage (how many events per sport?)
  - Which sports had 0 events? (source failure)
  - Phantom fixture detection
  - Tournament protection (§SCAN.7) — major tournaments present?
  - Minor league value (§SCAN.8)
  - Timeout/error triage
- Return: APPROVED/FLAGGED/REJECTED + per_sport_counts + issues[]
---
```

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

---

### STEP S1a: Fixture Discovery + API Stats

```bash
python3 scripts/discover_fixtures.py --date {date} 2>&1 | tail -30
python3 scripts/fetch_api_stats.py --date {date} 2>&1 | tail -30
python3 scripts/enrich_tennis_stats.py --date {date} --all-indexed 2>&1 | tail -20
python3 scripts/seed_espn_data.py --skip-players 2>&1 | tail -30
```

---

### STEP S1b: Odds + Weather + Tipsters

```bash
python3 scripts/fetch_odds_api.py 2>&1 | tail -30
python3 scripts/fetch_weather.py --date {date} 2>&1 | tail -20
python3 scripts/tipster_xref.py --date {date} 2>&1 | tail -30
```

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

---

### STEP S1e: Build Shortlist

```bash
python3 scripts/build_shortlist.py --date {date} --stats-first 2>&1 | tail -40
```

**AFTER shortlist built — Delegate to bet-scanner** (read `.github/internal-prompts/bet-shortlist.prompt.md` first):

```
runSubagent("bet-scanner"):
---
## Task: S1e Shortlist Review for {date}

[Paste content of .github/internal-prompts/bet-shortlist.prompt.md]

### Context
- Date: {date}
- Shortlist file: betting/data/{date_shortlist_file} (check both YYYY-MM-DD and YYYYMMDD formats)
- Use sequentialthinking to assess shortlist quality
- Key checks:
  - ≥20 candidates? If not → something failed upstream
  - ≥8 sports? If not → scan coverage issue
  - KEY sports (football, tennis, basketball, volleyball) ≥60% of candidates?
  - Major tournaments present? (§SCAN.7)
  - Minor league value candidates present? (§SCAN.8)
  - Sport diversity assessment
- Return: APPROVED/FLAGGED/REJECTED + candidate_count + sport_distribution
---
```

---

### STEP S2: Tipster Cross-Reference

**Delegate to bet-scout** — read `.github/internal-prompts/bet-tipsters.prompt.md` first, then:

```
runSubagent("bet-scout"):
---
## Task: S2 Tipster Cross-Reference for {date}

[Paste content of .github/internal-prompts/bet-tipsters.prompt.md]

### Context
- Date: {date}
- Shortlist: betting/data/{date_shortlist_file}
- Script to run: `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from tipster_xref import run_tipster_xref; ok, msg = run_tipster_xref('{date}', {}); print(msg)"`
- Use sequentialthinking to evaluate tipster consensus quality
- Load skill: bet-navigating-sources (Tier B tipster sites)
- Return: APPROVED/FLAGGED/REJECTED + tipster_consensus_summary
---
```

---

### STEP S2.5: Data Enrichment

**Delegate to bet-enricher** — read `.github/internal-prompts/bet-enrich.prompt.md` first, then:

```
runSubagent("bet-enricher"):
---
## Task: S2.5 Data Enrichment for {date}

[Paste content of .github/internal-prompts/bet-enrich.prompt.md]

### Context
- Date: {date}
- Shortlist: betting/data/{date_shortlist_file}
- Script to run: `PYTHONPATH=src python3 scripts/data_enrichment_agent.py --date {date}`
- After script: run `python3 scripts/validate_phase.py --date {date} --phase data --format json`
- Use sequentialthinking for Enrichment Quality Assessment
- Load skill: bet-navigating-sources (source fallback chains)
- Key metrics: enrichment yield %, per-sport data quality, gap recoverability
- Return: APPROVED/FLAGGED/REJECTED + yield_percentage + gaps[]
---
```

**GATE:** If bet-enricher returns REJECTED (yield <40%) → STOP, escalate to user.

---

## ═══════════════════════════════════════════════
## ANALYSIS (Steps S3 → S7) — FULLY DELEGATED TO SPECIALIST AGENTS
## ═══════════════════════════════════════════════

> **⛔ YOU DO NOT RUN ANY SCRIPTS IN THIS SECTION.**
> **Each step = one `runSubagent` call. The agent runs scripts, thinks, and returns a verdict.**
> **You evaluate the verdict with `sequentialthinking`, then decide: PROCEED / RETRY / ESCALATE.**

### STEP S3: Deep Statistical Analysis

**Delegate to bet-statistician** — read `.github/internal-prompts/bet-deep-stats.prompt.md` first, then:

```
runSubagent("bet-statistician"):
---
## Task: S3 Deep Statistical Analysis for {date}

[Paste content of .github/internal-prompts/bet-deep-stats.prompt.md]

### Context
- Date: {date}
- Shortlist file: betting/data/{date_shortlist_file}
- Script to run: `PYTHONPATH=src python3 scripts/deep_stats_report.py --date {date} --shortlist betting/data/{date_shortlist_file} --top 200`
- After script: run `python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json`
- Use sequentialthinking for EVERY CANDIDATE (5-part Analytical Reasoning Layer)
- Load skills: bet-analyzing-statistics, bet-applying-sport-protocols, bet-navigating-sources
- Key checks:
  - R5: Statistical markets ranked FIRST (corners/fouls/shots before ML)
  - §3.0c: H2H validation for EXACT stat being bet
  - Three-way cross-check: L10 + H2H + L5 all support direction
  - Every football match: ≥1 stat market evaluated
  - Edge mechanisms articulated (not just numbers)
- Return: APPROVED/FLAGGED/REJECTED + quality_score (1-10) + specific_issues[]
---
```

**Your job after receiving verdict:**
1. Use `sequentialthinking`: Does the quality_score justify proceeding? Are issues fixable?
2. If FLAGGED: Send back to bet-statistician with specific fix instructions
3. If REJECTED: Escalate to user with explanation

---

### STEP S4: Odds Evaluation

**Delegate to bet-valuator** — read `.github/internal-prompts/bet-odds-ev.prompt.md` first, then:

```
runSubagent("bet-valuator"):
---
## Task: S4 Odds Evaluation for {date}

[Paste content of .github/internal-prompts/bet-odds-ev.prompt.md]

### Context
- Date: {date}
- S3 output: betting/data/{date}_s3_deep_stats.md
- Script to run: `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from odds_evaluator import run_odds_eval; ok, msg = run_odds_eval('{date}', {}); print(msg)"`
- Also run: `python3 scripts/fetch_odds_api.py` for cross-validation
- Use sequentialthinking for EV assessment and drift detection
- Load skill: bet-evaluating-odds
- Key checks:
  - EV calculation per candidate: (true_prob × odds) - 1
  - R10: Events without API odds NOT excluded — show with suggested min odds
  - Drift detection: >8% change = mandatory re-evaluation
  - Kelly 1/4 sizing for each approved pick
- Return: APPROVED/FLAGGED/REJECTED + ev_summary + drift_flags[]
---
```

---

### STEP S5+S6: Context + Upset Risk (combined delegation)

**Delegate to bet-challenger** — read `.github/internal-prompts/bet-context-upset.prompt.md` first, then:

```
runSubagent("bet-challenger"):
---
## Task: S5+S6 Context Checks + Upset Risk for {date}

[Paste content of .github/internal-prompts/bet-context-upset.prompt.md]

### Context
- Date: {date}
- S3 output: betting/data/{date}_s3_deep_stats.md
- S4 output: (from bet-valuator's verdict above)
- Scripts to run:
  1. `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from context_checks import run_context_checks; ok, msg = run_context_checks('{date}', {}); print(msg)"`
  2. `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from upset_risk import run_upset_risk; ok, msg = run_upset_risk('{date}', {}); print(msg)"`
- Use sequentialthinking for 5-part Deep Adversarial Reasoning per candidate
- Load skill: bet-applying-sport-protocols (upset risk checklists)
- Key checks:
  - Context flags with REAL market impact (not generic "weather could matter")
  - Compounding risk factors identified
  - Sport-specific upset thresholds applied
  - Bayesian confidence update formula applied
- Return: APPROVED/FLAGGED/REJECTED + risk_summary + compounding_risks[]
---
```

---

### STEP S7: 18-Point Advisory Gate

**Delegate to bet-challenger** — read `.github/internal-prompts/bet-gate.prompt.md` first, then:

```
runSubagent("bet-challenger"):
---
## Task: S7 Gate Check for {date}

[Paste content of .github/internal-prompts/bet-gate.prompt.md]

### Context
- Date: {date}
- S3 output: betting/data/{date}_s3_deep_stats.md
- Script to run: `PYTHONPATH=src python3 scripts/gate_checker.py --date {date}`
- Use sequentialthinking for gate quality assessment
- Key checks:
  - All 18 points evaluated per candidate (not abbreviated)
  - Bear cases cite SPECIFIC DATA (not generic "it could go wrong")
  - R4: ≥5 sports in STRONG+MODERATE tiers
  - R3: NO auto-rejection — ALL candidates visible in output
  - Extended Pool: gate-failed EV>0 candidates documented
  - Tier distribution: >80% FLAGGED = gate calibration issue
- Return: APPROVED/FLAGGED/REJECTED + tier_distribution + sport_diversity_check
---
```

**GATE:** If <5 sports in approved → emergency expansion (R4). Delegate again with expanded scope.

---

## ═══════════════════════════════════════════════
## BUILD (Steps S8 → S10) — DELEGATED TO bet-builder
## ═══════════════════════════════════════════════

### STEP S8+S9: Build + Validate Coupons

**Delegate to bet-builder** — read `.github/internal-prompts/bet-portfolio.prompt.md` first, then:

```
runSubagent("bet-builder"):
---
## Task: S8+S9 Build and Validate Coupons for {date}

[Paste content of .github/internal-prompts/bet-portfolio.prompt.md]

### Context
- Date: {date}
- Gate output: betting/data/{date}_s7_gate_results.json (or from bet-challenger verdict)
- Config: config/betting_config.json
- Scripts to run:
  1. `PYTHONPATH=src python3 scripts/coupon_builder.py --date {date}`
  2. `python3 scripts/validate_phase.py --date {date} --phase build --format json`
- Use sequentialthinking for 4-part Portfolio Intelligence Layer
- Load skill: bet-building-coupons
- Key checks:
  - Arithmetic: multiply each leg odds step-by-step → combined odds match (±0.02)
  - Unique events: zero shared events between core coupons
  - Sport diversity: ≥5 sports across portfolio
  - R5: ≥60% statistical markets
  - Exposure: total stakes ≤25% bankroll
  - V1-V10 + §S8.FINAL: ALL mechanical checks PASS
  - Conditional disclaimer present
  - R12: All picks marked CONDITIONAL
- Return: APPROVED/FLAGGED/REJECTED + arithmetic_verification + coupon_file_path
---
```

---

### STEP S10: Final Summary

```
runSubagent("bet-builder"):
---
## Task: S10 Generate Final Summary for {date}

### Context
- Date: {date}
- Script to run: `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from pipeline_summary import run_summary; ok, msg = run_summary('{date}', {}); print(msg)"`
- Return: summary text for user presentation
---
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
| 3 | Run script → show output → done | Script = calculator. Agent = analyst. DELEGATE. |
| 4 | Skip `sequentialthinking` between steps | No methodology enforcement without thinking |
| 5 | Skip `runSubagent` delegation | Specialist agents catch what you miss |
| 6 | Proceed despite validation failure | Garbage in → garbage out |
| 7 | Present raw script output to user | User gets ANALYZED output, not log dumps |
| 8 | Run S3-S7 as one batch | Each analytical step needs separate agent review |
| 9 | Run analytical scripts yourself | `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `data_enrichment_agent.py` = ALWAYS delegated |
| 10 | Say "Analyzing" after running a script | YOU don't analyze — you DELEGATE to the specialist agent who analyzes |

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
