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
[ ] Sports: 5 (football, volleyball, basketball, tennis, hockey) | Previous day settled: yes/no
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
- Check that methodology rules (R1-R19) are respected in the agent's output
- Verify sport diversity, statistical market coverage, and gate compliance
- **VERIFY SUBAGENT OUTPUT QUALITY** (see §SUBAGENT OUTPUT VERIFICATION below)

**What you NEVER do:**
- Run `deep_stats_report.py`, `data_enrichment_agent.py`, `gate_checker.py`, `coupon_builder.py`, or any analytical script yourself
- Analyze statistical output yourself (that's bet-statistician's job)
- Build bear cases yourself (that's bet-challenger's job)
- Evaluate odds yourself (that's bet-valuator's job)
- **Accept subagent output that is just raw script paste without analysis**

**The ONLY scripts you may run directly:**
- `settle_on_finish.py` + `analyze_betclic_learning.py` (S0 — lightweight, pre-pipeline)
- `scan_events.py` (S1 — launches parallel scan, but bet-scanner reviews output)
- Simple validation one-liners: file existence, line counts, JSON key checks
- `validate_phase.py` (quick sanity gate between phases)
- `web_research_agent.py` — L7 fallback for missing H2H/injuries (R15)

---

## ⛔ TERMINAL EXECUTION RULES

All agents follow `agent-execution-protocol.instructions.md` (loaded via their `instructions:` array). That protocol covers: `--verbose` mandatory, `mode=sync` with timeouts, `AGENT_SUMMARY:{json}` parsing, live monitoring, and structured verdicts. **Do not repeat these rules in delegation messages** — the agents already have them.

---

## §STRUCTURED SCRIPT OUTPUT (R19)

10 analytical scripts emit `AGENT_SUMMARY:{json}`: `scan_events.py`, `html_deep_parser.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `build_shortlist.py`. Exit codes: 0=OK, 1=partial, 2=critical. Scripts with `--sport` filter: `scan_events.py`, `tipster_aggregator.py`.

---

## §SUBAGENT OUTPUT VERIFICATION (after every runSubagent)

**3-question quality gate — if ANY answer is NO, REJECT and re-delegate:**
1. Does the response cite ≥3 specific metrics extracted from script output? (not vague summaries)
2. Does it contain ORIGINAL ANALYSIS beyond what the script computed? (insights, anomalies, reasoning)
3. Is there a structured verdict with justification? (not just "APPROVED")

**Re-delegation instruction when rejecting:**
"Your output was rejected — you returned [raw script paste / verdict without reasoning / no original analysis]. Read agent-execution-protocol.instructions.md. Return: metrics table (≥3 rows), anomaly analysis, YOUR original reasoning, structured verdict with justification."

## ═══════════════════════════════════════════════
## DATA COLLECTION (Steps S0 → S2.5)
## ═══════════════════════════════════════════════

### STEP S0: Settlement + History

```bash
python3 scripts/settle_on_finish.py --betting-day {prev_date} --no-poll 2>&1
python3 scripts/evaluate_decisions.py --date {prev_date} 2>&1
python3 scripts/analyze_betclic_learning.py 2>&1
python3 scripts/data_rotation.py --execute --days 30 2>&1
python3 scripts/build_league_profiles.py 2>&1
```

**AFTER — Delegate to bet-settler** (read `.github/internal-prompts/bet-settle.prompt.md` first):

```
runSubagent("bet-settler"):
---
## Task: S0 Settlement Review for {prev_date}

[Paste content of .github/internal-prompts/bet-settle.prompt.md]

### Context
- Previous date: {prev_date}
- Scripts already ran: settle_on_finish, evaluate_decisions, analyze_betclic_learning
- Read: betting/data/betclic_learning_summary.json
- Use sequentialthinking to extract key patterns from Betclic history
- Load skill: bet-settling-results
- Key checks:
  - PnL summary: wins/losses/pushes, net PnL, bankroll impact
  - Rolling 7-day trend: improving or declining?
  - Market hit rates: which markets/sports performing best/worst? (R6: advisory only)
  - Coupon killers: which leg type causes most losses?
  - 20% drawdown protection: is bankroll approaching -20% from peak?
- Return: APPROVED/FLAGGED/REJECTED + pnl_summary + bankroll_update + learning_insights
---
```

---

### STEP S0.5: DB Quality Check (NEW — data foundation validation)

**Delegate to bet-db-analyst** (read `.github/internal-prompts/bet-db-quality.prompt.md` first):

```
runSubagent("bet-db-analyst"):
---
## Task: S0.5 DB Quality Check for {date}

[Paste content of .github/internal-prompts/bet-db-quality.prompt.md]

### Context
- Date: {date}
- Run full table census, date-specific analysis, source health check
- Load skill: bet-querying-database
- Key checks:
  - All 28 tables exist and are populated
  - team_form has data for all 5 sports
  - fixtures for today's date are loaded
  - source_health shows acceptable success rates
  - league_profiles populated for active competitions
- Return: APPROVED/FLAGGED/REJECTED + tables_populated + gaps[] + recommendations[]
---
```

**GATE:** If bet-db-analyst returns FLAGGED with critical gaps → run recommended enrichment scripts before S1.

---

### STEP S1: Event Scan (longest step — use async)

**You launch the scan, then delegate review to bet-scanner.**

```bash
# Run parallel-sport scan — takes 10-20 min
python3 scripts/scan_events.py --parallel-sport --date {date} --deep --max-deep-links 30 --workers 8 --verbose 2>&1
```

**WHILE RUNNING:** Use `mode=sync` with `timeout=600000`. When the script completes, read the full output immediately. If it times out, use `get_terminal_output` to check accumulated output and diagnose. While waiting, do productive work (read files, plan next steps with `sequentialthinking`). R17: LIVE MONITORING.

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
  - 5-sport coverage: football, volleyball, basketball, tennis, hockey
  - Which of the 5 sports had 0 events? (source failure → retry with fallback)
  - Data quality: How many events have deep data (H2H, form, injuries)?
  - Phantom fixture detection
  - Tournament protection (§SCAN.7) — major tournaments present?
  - Major domestic league protection (§SCAN.9) — Brasileirão, MLS, Liga MX, CSL, J-League, K-League, etc. present?
  - Minor league value (§SCAN.8)
  - Timeout/error triage
- Return: APPROVED/FLAGGED/REJECTED + per_sport_counts + issues[]
---
```

---

### STEP S1-ingest: Ingest Scan Stats

```bash
python3 scripts/ingest_scan_stats.py --verbose 2>&1
```

**AFTER:** Parse `AGENT_SUMMARY` from output → verify `verdict=OK`. If PARTIAL/FAILED → check which sports/sources had ingestion errors before proceeding.

---

### STEP S1-deep: HTML Deep Parsing

```bash
python3 scripts/html_deep_parser.py --date {date} --report --verbose 2>&1
```

**AFTER — Delegate to bet-scanner** for parsing quality review:

```
runSubagent("bet-scanner"):
---
## Task: S1-deep HTML Deep Parsing Review for {date}

### Context
- Date: {date}
- Script already ran. Review output quality.
- Check: betting/data/{date}_deep_parse_report.json
- Parse `AGENT_SUMMARY:` JSON from script output for verdict, metrics, issues
- Use sequentialthinking to evaluate parsing quality
- Key checks:
  - Per-domain verdicts: PASS/WARN/FAIL — any FAIL domains need CSS selector fixes
  - WARN domains: are out_of_range values real errors or outliers?
  - db_cross_reference match rates — low match = stale snapshots
  - field_coverage — expected fields being extracted per domain?
- Recovery: If profile returns 0 extractions → HTML structure changed, flag for update
- Return: APPROVED/FLAGGED/REJECTED + pass_domains + warn_domains + fail_domains + db_match_rate
---
```

---

### STEP S1a: Fixture Discovery + API Stats

```bash
python3 scripts/discover_fixtures.py --date {date} 2>&1
python3 scripts/fetch_api_stats.py --date {date} 2>&1
# Tennis enrichment handled by data_enrichment_agent.py in S2.5
python3 scripts/seed_espn_data.py --skip-players 2>&1
```

**Post-run check**: Verify fixtures discovered (>0 per active sport). If `fetch_api_stats.py` reports 0 API responses, proceed in stats-first mode (R10) — API stats are supplemental, not required.

---

### STEP S1b: Odds + Weather + Tipster Fetch

```bash
python3 scripts/fetch_odds_api.py 2>&1
python3 scripts/fetch_weather.py --date {date} 2>&1
python3 scripts/tipster_aggregator.py --date {date} --verbose 2>&1
```

**Note:** `tipster_aggregator.py` FETCHES raw tipster picks from all sites → produces `betting/data/{date}_tipster_consensus.json`. The ANALYSIS of tipster data (cross-reference vs shortlist) happens in S2 via `tipster_xref.py`.

---

### STEP S1c: Aggregate + Analysis Pool

```bash
# Aggregation and analysis pool handled by build_shortlist.py in S1e
```

---

### STEP S1d: Market Matrix

```bash
python3 scripts/generate_market_matrix.py --date {date} --stats-first 2>&1
```

---

### STEP S1e: Build Shortlist

```bash
python3 scripts/build_shortlist.py --date {date} --stats-first 2>&1
```

**AFTER shortlist built — Delegate to bet-scanner** (read `.github/internal-prompts/bet-shortlist.prompt.md` first):

```
runSubagent("bet-scanner"):
---
## Task: S1e Shortlist Review for {date}

[Paste content of .github/internal-prompts/bet-shortlist.prompt.md]

### Context
- Date: {date}
- Shortlist file: `betting/data/{date}_s2_shortlist.json`
- Use sequentialthinking to assess shortlist quality
- Key checks:
  - ≥20 candidates? If not → something failed upstream
  - All 5 sports represented? (informational — NOT a gate, just awareness)
  - Data quality: How many candidates have FULL/PARTIAL/MINIMAL data?
  - Lower-division leagues present? (minor league value — R8)
  - Major tournaments present? (§SCAN.7)
  - Major domestic leagues present? (§SCAN.9) — Brasileirão, MLS, Liga MX, CSL, etc.
  - Minor league value candidates present? (§SCAN.8)
  - Data quality distribution (FULL/PARTIAL/MINIMAL counts)
- Return: APPROVED/FLAGGED/REJECTED + candidate_count + data_quality_distribution
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
- Shortlist: `betting/data/{date}_s2_shortlist.json`
- Tipster data (from S1b): `betting/data/{date}_tipster_consensus.json`
- Script to run: `PYTHONPATH=src python3 scripts/tipster_xref.py --date {date} --verbose`
- Parse `AGENT_SUMMARY:` JSON from output for structured metrics (tips_loaded, matched, total)
- Use sequentialthinking to evaluate tipster consensus quality
- Load skill: bet-navigating-sources (Tier B tipster sites)
- Key checks:
  - Tipster quality: named expert > anonymous aggregate
  - Independence: ≥2 tipsters from different platforms agreeing = consensus
  - Angles pure stats missed: tactical changes, managerial quotes, team news
  - Watchlist picks with strong tipster backing → promote to shortlist
  - Picks where tipsters strongly disagree with stats → flag for S5
- Return: APPROVED/FLAGGED/REJECTED + tipster_count + event_coverage + consensus_picks[]
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
- Shortlist: `betting/data/{date}_s2_shortlist.json`
- Script to run: `PYTHONPATH=src python3 scripts/data_enrichment_agent.py --date {date} --verbose`
- Parse `AGENT_SUMMARY:` JSON from output for structured metrics (verdict, yield %, gaps)
- After script: run `python3 scripts/validate_phase.py --date {date} --phase data --format json`
- Use sequentialthinking for Enrichment Quality Assessment
- Load skill: bet-navigating-sources (source fallback chains)
- Key checks: enrichment yield %, per-sport data quality, gap recoverability
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
- Shortlist file: `betting/data/{date}_s2_shortlist.json`
- Script to run: `PYTHONPATH=src python3 scripts/deep_stats_report.py --date {date} --shortlist betting/data/{date}_s2_shortlist.json --top 200 --verbose`
- Parse `AGENT_SUMMARY:` JSON from output for per-candidate metrics, data quality scores, and issues
- After script: validate output quality with sequentialthinking (data depth, market coverage, three-way cross-check alignment)
- Use sequentialthinking for EVERY CANDIDATE (5-part Analytical Reasoning Layer)
- Load skills: bet-analyzing-statistics, bet-applying-sport-protocols, bet-navigating-sources
- Key checks:
  - R5: Statistical markets ranked FIRST (corners/fouls/shots before ML)
  - §3.0c: H2H validation for EXACT stat being bet
  - Three-way cross-check: L10 + H2H + L5 all support direction
  - Every football match: ≥1 stat market evaluated
  - Edge mechanisms articulated (not just numbers)
- Recovery actions:
  - If team_form empty for a candidate → call `enrich_team(team_name, sport)` before analysis
  - If H2H missing → call `enrich_h2h(team_a, team_b, sport)`
  - If league_profiles empty → run `build_league_profiles.py` first
  - If <3 data points in any dimension → flag but don't reject (R3)
- Return: APPROVED/FLAGGED/REJECTED + quality_score (1-10) + candidates_analyzed + avg_safety_score + specific_issues[]
---
```

**Your job after receiving verdict:**
1. Use `sequentialthinking`: Does the quality_score justify proceeding? Are issues fixable?
2. If FLAGGED: Send back to bet-statistician with specific fix instructions
3. If REJECTED: Escalate to user with explanation

> **S3B Trigger**: If earliest kickoff is ≤3h away, delegate `bet-time-sensitive.prompt.md` to bet-statistician BEFORE S4. This fetches live lineups, weather, late injuries, and odds drift. Re-evaluate affected picks' safety scores after S3B returns.

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
- S3 output: DB `analysis_results` table + `betting/data/{date}_s3_deep_stats.json`
- Script to run: `PYTHONPATH=src python3 -c "import sys; sys.path.insert(0, 'scripts'); from odds_evaluator import run_odds_eval; ok, msg = run_odds_eval('{date}', {}); print(msg)"`
- Also run: `python3 scripts/fetch_odds_api.py` for cross-validation
- Use sequentialthinking for EV assessment and drift detection
- Load skill: bet-evaluating-odds
- Key checks:
  - EV calculation per candidate: (true_prob × odds) - 1
  - R10: Events without API odds NOT excluded — show with suggested min odds
  - Drift detection: >8% change = mandatory re-evaluation
  - Kelly 1/4 sizing for each approved pick
- Recovery: If no odds available → flag for stats-first mode (R10), calculate minimum_acceptable_odds = 1/hit_rate
- Return: APPROVED/FLAGGED/REJECTED + candidates_with_ev + avg_ev + ev_positive_count + drift_flags[]
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
- S3 output: DB `analysis_results` table + `betting/data/{date}_s3_deep_stats.json`
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
- Recovery actions:
  - If weather data missing → run `python3 scripts/fetch_weather.py --date {date}` for outdoor venues
  - If injury data missing → scrape ESPN injury report via Playwright (R9 self-healing)
- Note: S5+S6 combined into one delegation (agent_protocol.py has separate configs s5_context + s6_upset_risk)
- Return: APPROVED/FLAGGED/REJECTED + weather_flags + injury_flags + high_risk_count + medium_risk_count + low_risk_count + compounding_risks[]
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
- S3 output: DB `analysis_results` table + `betting/data/{date}_s3_deep_stats.json`
- Script to run: `PYTHONPATH=src python3 scripts/gate_checker.py --date {date} --verbose`
- Parse `AGENT_SUMMARY:` JSON from output for tier distribution, gate scores, and issues
- Use sequentialthinking for gate quality assessment
- Key checks:
  - All 18 points evaluated per candidate (not abbreviated)
  - Bear cases cite SPECIFIC DATA (not generic "it could go wrong")
  - R4: Sport coverage is informational — NOT a gate. Quality over forced diversity.
  - R14: Data quality per candidate (FULL/PARTIAL/MINIMAL). Only FULL/PARTIAL in core coupons.
  - R3: NO auto-rejection — ALL candidates visible in output
  - Extended Pool: gate-failed EV>0 candidates documented
  - Tier distribution: >80% FLAGGED = gate calibration issue
  - Data quality validation mandatory (data_quality_validation=True in agent_protocol.py)
- Return: APPROVED/FLAGGED/REJECTED + approved_count + strong_count + moderate_count + weak_count + sport_diversity_check
---
```

**GATE:** If >50% candidates have MINIMAL data quality → enrichment failure. Spawn web_research_agent.py (R15) for data gaps. Re-delegate to bet-enricher.

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
  1. `PYTHONPATH=src python3 scripts/coupon_builder.py --date {date} --verbose`
  2. `python3 scripts/validate_phase.py --date {date} --phase build --format json`
- Parse `AGENT_SUMMARY:` JSON from coupon_builder output for spend/return metrics and issues
- Use sequentialthinking for 4-part Portfolio Intelligence Layer
- Load skill: bet-building-coupons
- Key checks:
  - Arithmetic: multiply each leg odds step-by-step → combined odds match (±0.02)
  - Unique events: zero shared events between core coupons
  - Data quality: Only FULL/PARTIAL picks in core coupons (R14). MINIMAL → Extended Pool.
  - No event duplication: Each event in at most 1 core coupon.
  - R5: ≥60% statistical markets
  - Exposure: total stakes ≤25% bankroll
  - V1-V10 + §S8.FINAL: ALL mechanical checks PASS
  - Conditional disclaimer present
  - R12: All picks marked CONDITIONAL
- Return: APPROVED/FLAGGED/REJECTED + coupon_count + total_legs + total_stake + discovery_count + arithmetic_verification + coupon_file_path
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
- No script needed — build summary from agent verdicts collected during S0-S9.
- Present: settlement PnL, scan coverage, data quality distribution, coupon details, Extended Pool.
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
| 11 | Accept subagent output without metrics | If subagent returns no specific numbers/counts → REJECT and re-delegate |
| 12 | Accept raw script paste from subagent | Subagent must return STRUCTURED VERDICT (metrics + reasoning + verdict), not terminal output |
| 13 | Fire-and-forget long scripts | Use `mode=sync` + timeout. After completion, READ FULL OUTPUT and extract metrics. If timed out, use `get_terminal_output` to diagnose (R17). |
| 14 | Skip data quality checks | Proceeding without checking data_quality_score. FULL/PARTIAL are core requirements. |
| 15 | Ignore live betting window | Excluding events ≤1h to kickoff. Betclic allows live betting (R16). |

---
## §THINK IN THE MIDDLE

> All agents follow `agent-execution-protocol.instructions.md` for the full RUN→EXTRACT→THINK→RETURN cycle.
> R18 data flow verification: READ producer/consumer code BEFORE running. Verify keys/tables/formats match.
> See the protocol for the complete GOOD vs BAD output examples and anti-pattern list.

---
## RULES ENFORCEMENT (R1-R19)

| Rule | What to check | When |
|------|--------------|------|
| R1 AGENT-DRIVEN | Script ran → agent analyzed → reasoned output | Every step |
| R2 DB-FIRST | Read from `betting/data/betting.db` via `get_db()`. JSON files = fallback only. Never raw `sqlite3.connect()`. | ALL |
| R3 NO AUTO-REJECTION | ALL candidates visible. No "rejected due to" | S7, S8 |
| R4 NO NARROWING | Sport diversity is informational, never a gate. Quality > forced diversity | S7 |
| R5 STATS > OUTCOMES | Every football match ≥1 stat market | S3, S8 |
| R6 BETCLIC ADVISORY | Hit rates shown, never auto-penalize | S0, S3 |
| R7 TOURNAMENT PROTECTION | Major tournaments present | S1e |
| R8 MINOR LEAGUE VALUE | No "obscure" penalties | S1e |
| R9 SELF-HEALING DATA | Missing data → auto-fallback L1→L6, then L7 web research (R15). See `SELF_HEALING_REGISTRY` in agent_protocol.py. | S1, S2.5, S3 |
| R10 STATS-FIRST | Events without odds NOT excluded | S4, S7 |
| R11 SEQUENTIAL THINKING | sequentialthinking per step + per candidate in S3 | ALL |
| R12 CONDITIONAL | Coupon carries conditional disclaimer | S8 |
| R13 MAJOR DOMESTIC LEAGUE | Brasileirão/MLS/Liga MX/CSL/J-League/K-League present when active | S1e |
| R14 DATA DEPTH | data_quality_score computed per candidate. FULL/PARTIAL only in core coupons | S3, S7, S8 |
| R15 WEB RESEARCH | Missing H2H/injuries → spawn web_research_agent.py. Max 5 SerpAPI + 10 Playwright | S2.5, S3 |
| R16 LIVE WINDOW | 06:00→05:59 next day. Events ≤1h to kickoff or in-play = LIVE, include in scan | S1, S1e |
| R17 LIVE SCRIPT MONITORING | ALWAYS --verbose. Read FULL output. Extract metrics. Report specific numbers. React to errors. If timeout: use get_terminal_output to diagnose. | ALL |
| R18 DATA FLOW VERIFICATION | Before running a script, READ its code to understand inputs/outputs. TRACE producer→consumer: do JSON keys, DB tables, field names match? Verify with actual data. READ CODE → THINK → CHECK → FIX. | ALL |
| R19 STRUCTURED OUTPUT | 9 analytical scripts support `--verbose` + `AGENT_SUMMARY:{json}` (see §STRUCTURED SCRIPT OUTPUT). Use `--verbose` on those scripts. Parse AGENT_SUMMARY for verdict/metrics/issues. Exit: 0=OK, 1=partial, 2=critical. | ALL |

---

## DELEGATION REFERENCE

| Step | Internal Prompt | Agent |
|------|----------------|-------|
| S0 Settlement | `bet-settle.prompt.md` | bet-settler |
| S0.5 DB Quality | `bet-db-quality.prompt.md` | bet-db-analyst |
| S1 Scan | `bet-scan.prompt.md` | bet-scanner |
| S1 Scan (sport-specific) | `bet-scan-football.prompt.md`, `bet-scan-basketball.prompt.md`, `bet-scan-tennis.prompt.md` | bet-scanner |
| S1 Scan (merge) | `bet-scan-merge.prompt.md` | bet-scanner |
| S1 Scan (all sports) | `bet-scan-all.prompt.md` | bet-scanner |
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

ALL sessions execute the SAME pipeline. Only the time window differs. Night/morning sessions get FULL analysis. If <3 picks survive after expansion → declare NO BET.

## KNOWN FAILURE PATTERNS

1. **PHANTOM GAMES**: ZT/tipster sites list tips for games that already played. Verify on Flashscore before shortlisting.
2. **BETCLIC LINE MISMATCH**: Do not assume BetExplorer lines = Betclic. When avg ≈ line → zero edge → DROP.
3. **MARKET UNAVAILABILITY**: Top market not on Betclic → need fallback. Check availability BEFORE deep analysis.
4. **INSUFFICIENT PICKS**: If <4 picks survive S7 → expand shortlist (§2.1). If <3 survive after expansion → NO BET.
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
# Use sequentialthinking to validate deep stats quality (no script needed)

# Coupon validation:
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json

# Individual tools:
python3 scripts/analyze_betclic_learning.py
python3 scripts/fetch_odds_api.py [--scores hockey]
python3 scripts/settle_on_finish.py --betting-day YYYY-MM-DD
```

## DB REFERENCE

SQLite at `betting/data/betting.db`. Connection: `from bet.db.connection import get_db`.
28 tables across 6 domains: Core (sports/teams/competitions/fixtures/athletes), Stats (team_form/match_stats/league_profiles/standings/power_index), Analysis (analysis_results/analysis_raw_data/gate_results/decision_snapshots/decision_outcomes), Betting (coupons/bets/odds_history), Pipeline (pipeline_runs/scan_results/scan_run_stats/source_health), ESPN (espn_predictions/player_gamelogs/player_splits/team_ats_records/team_ou_records/team_rosters).
