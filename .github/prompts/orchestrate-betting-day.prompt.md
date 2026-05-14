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
- **rescan** = {{rescan}} (default: `false`). Set `true` after infrastructure changes (new API clients, new data sources, pipeline overhauls). Wipes stale scan/analysis data for the date and re-runs the full pipeline with new sources.
- **version** = {{version}} (default: `v1`)
- Timezone: Europe/Warsaw (CEST). Bookmaker: Betclic.

---

## STEP -1: DETECT PROGRESS & ASK WHERE TO CONTINUE

Before starting any work, check what already exists for `run_date`:

1. **Quick state check:** `python3 scripts/inspect_pipeline.py --step all --date {run_date} --verbose`
   This replaces manual `ls` + inline Python queries. Shows per-step metrics.
2. Check coupons: `ls betting/coupons/{run_date}*`
3. Check reports: `ls betting/reports/{run_date}*`
4. Check DB tables (via bet-db-analyst or quick query): fixtures, scan_results, shortlist_candidates for that date

**Then ASK the user:**
```
Pipeline progress for {run_date}:
✅ S0 Settlement — [done/not done]
✅ S1 Scan — [X events found / not done]
✅ S2 Enrichment — [Y teams enriched / not done]
❌ S3 Deep Stats — [not started / partial]
❌ S4-S10 — not started

Where should I start? [S3 / full rerun / specific step]
```

**NEVER assume** — always ask. Even if rerun=true, confirm which steps to redo.

---

## STEP 0: LOAD CONTEXT (do this ONCE before anything else)

Read these files. Do NOT proceed until all are loaded:
1. `config/betting_config.json`
2. `config/gemini_config.json` — **Gemini feature flags, model selection, daily budget**
3. `.github/instructions/analysis-methodology.instructions.md`
4. `.github/instructions/betting-artifacts.instructions.md`
5. `betting/sources/source-registry.md`
6. `/memories/repo/pipeline-lessons-learned.md`
7. `/memories/repo/api-clients-overhaul-plan.md` — **API client architecture + patterns**
8. Latest session memory from `/memories/repo/session-*.md` (pick most recent date)

### ⚠️ ADAPTER OVERHAUL (2026-05-12) — ENFORCE IN ALL STEPS

68 files changed, 7193 lines added — all 5 sport adapter chains overhauled. Key changes every agent MUST enforce:

| Sport | Key Change | Agent Impact |
|-------|-----------|--------------|
| Hockey | **MoneyPuck = PRIMARY** advanced stats (xG%, Corsi%, Fenwick%). NaturalStatTrick BLOCKED (403). DailyFaceoff for goalie confirmations. | bet-scanner, bet-statistician, bet-enricher |
| Tennis | TennisAbstract Elo integrated (data_quality_score +1). ATP Tour adapter added. Paired-row parser overhauled. | bet-scanner, bet-statistician, bet-enricher |
| Basketball | Basketball-Reference adapter enhanced. BallDontLie DISABLED. | bet-scanner, bet-statistician, bet-enricher |
| Volleyball | Flashscore volleyball adapter enhanced. Deep stats enrichment improved. | bet-scanner, bet-statistician, bet-enricher |
| Football | Soccerway, SoccerStats, WhoScored, Covers, Forebet adapters all enhanced. | bet-scanner, bet-statistician, bet-enricher |

**Disabled clients (removed from CLIENT_REGISTRY):** TheSportsDB, BallDontLie, API-Tennis.
**New adapters:** atptour, dailyfaceoff, hockey_reference, moneypuck, naturalstattrick (blocked but registered).
**Protocol:** v6 — 6-step cycle (INSPECT/RUN/THINK/ANALYZE/VALIDATE/VERDICT), pylanceRunCodeSnippet for data inspection, heredocs banned, async mandatory for scripts >120s.

### ⚡ API CLIENT OVERHAUL (2026-05-13) — NEW DATA SOURCES

5 new API clients deployed + `PlaywrightBaseClient` extraction + `unified.py` resilient routing:

| Client | Type | Sports | Data Provided |
|--------|------|--------|---------------|
| `BetExplorerClient` | HTTP (BeautifulSoup) | All 5 | Fixtures, odds comparison, results |
| `OddsPortalClient` | Playwright SPA | All 5 | Multi-bookmaker odds, dropping odds, price gaps |
| `TotalCornerClient` | Playwright | Football only | Corner predictions, handicaps, dangerous attacks |
| `Scores24Client` | Playwright | All 5 | H2H, form, odds, **structured betting trends with hit rates** |
| `SoccerwayClient` | HTTP (BeautifulSoup) | Football only | 200+ countries, 1000+ leagues, exotic fixture discovery |

**unified.py routing (SOURCE_PRIORITY):**
- Football: Flashscore → BetExplorer → Soccerway → ESPN
- Tennis: Flashscore → Scores24 → ESPN
- Basketball/Hockey/Volleyball: Flashscore → BetExplorer → Scores24 → ESPN
- Odds: OddsPortal → BetExplorer (all sports)
- Stats: TotalCorner → Flashscore (football corners)

**Key:** `discover_events.py` discovers fixtures from 3 API sources (SofaScore, Odds API, API-Football) in ~30s. Deep data (form, H2H, injuries) is handled by enrichment (S2), not scan.

Print the pre-flight checklist:
```
[ ] Bankroll: ___ PLN | Daily budget: ___-___ PLN
[ ] Session: {session} → window: HH:MM → HH:MM
[ ] Sports: 5 (football, volleyball, basketball, tennis, hockey) | Previous day settled: yes/no
[ ] Memory loaded: yes/no (mistakes count: ___)
[ ] Gemini: enabled/disabled | Model: ___ | Daily budget: ___/___  requests
```

### ⚡ GEMINI FEATURE FLAGS (read from `config/gemini_config.json`)

Gemini features are ADDITIVE — they enhance the pipeline behind feature flags. The existing pipeline works unchanged without them.

| Flag | Script | Effect |
|------|--------|--------|
| `--use-gemini` | `tipster_aggregator.py` | Gemini reads tipster pages natively (replaces BS4 HTML parsing). Falls back per-site if Gemini fails. |
| `--news` | `data_enrichment_agent.py` | Gemini Search Grounding fetches injuries, coaching changes, morale data → saves to `team_news` DB table → consumed by `context_checks.py` (S5). |
| `--gemini` | `deep_stats_report.py` | Gemini "second opinion" per candidate: independent market recommendations, upset risk, `agreement_score` tracking Python↔Gemini alignment. |
| `use_gemini=True` | `web_research_agent.py` | L7a Gemini Search Grounding as primary web research. Falls back to urllib-based web fetch (L7b). MCP tools `browser/*`, `playwright/*` available as L7c for interactive page rendering. Note: SerpAPI client exists but requires API key configuration. |

**Decision:** Include ALL Gemini flags by default when `config/gemini_config.json` exists and API key is configured. Skip Gemini gracefully when not configured (all modules have try/except ImportError guards).

---

## THE EXECUTION PROTOCOL

> **⛔ YOU RUN ALL SCRIPTS. Specialist agents ONLY ANALYZE the output.**
> **This is the "Run-Then-Delegate" model (Model A in agent-execution-protocol.instructions.md).**
> **You launch scripts, monitor for errors, extract AGENT_SUMMARY, then delegate analysis.**

**Every analytical step (S2-S8) follows this pattern:**
```
1. INSPECT: pylanceRunCodeSnippet → verify inputs exist and format matches (R18)
2. RUN: run_in_terminal(mode=async, --verbose) → you control the terminal
3. THINK-WHILE-WAITING: sequentialthinking + pylanceRunCodeSnippet (review upstream data, plan next step)
4. MONITOR: get_terminal_output → watch for errors (404s, 403s, timeouts) → react immediately
5. EXTRACT: Parse AGENT_SUMMARY:{json} + key metrics + warnings/errors from output
6. VALIDATE: pylanceRunCodeSnippet → verify output files/DB writes (R18)
7. DELEGATE ANALYSIS: runSubagent(specialist_agent) — pass extracted output for specialist analysis
8. RECEIVE VERDICT: Agent returns structured verdict with specialist reasoning
9. QUALITY GATE: 6-question check on verdict quality
10. DECIDE: PROCEED / FIX+RETRY / ESCALATE to user
```

**Why YOU run scripts (not subagents):**
- You see 404/403 errors IMMEDIATELY and can react (kill, retry, investigate)
- You THINK-WHILE-WAITING at the orchestrator level (more reliable than subagent compliance)
- Subagents get COMPLETED output → focus entirely on specialist analysis (their core value)
- Eliminates R17 violations where subagents launch scripts and sit idle at "Preparing"

**What specialist agents receive:**
```
runSubagent(agent_name):
  script_output: {AGENT_SUMMARY JSON}
  raw_log_excerpt: {relevant warnings/errors, max 50 lines}
  input_context: {upstream step verdicts, quality flags, focus points}
  → Agent returns: analysis-only verdict (no script execution)
```

**What you NEVER do:**
- Let subagents run analytical scripts (they ANALYZE output, not execute scripts)
- Run `pipeline_orchestrator.py` (BANNED)
- Present raw script output to user without specialist agent review
- Ignore errors in script output (404s, timeouts, 0-yield sources)

---

## ⛔ TERMINAL EXECUTION RULES

All agents follow `agent-execution-protocol.instructions.md` v6 (loaded via their `instructions:` array). That protocol covers: 6-step cycle (INSPECT→RUN→THINK→ANALYZE→VALIDATE→VERDICT), `pylanceRunCodeSnippet` for data inspection, `--verbose` mandatory, `mode=async` + THINK-WHILE-WAITING (≥120s), `AGENT_SUMMARY:{json}` parsing, structured verdicts, REACTION_PATTERNS, input contract pre-checks. The protocol file covers terminal rules via agents' `instructions:` array.

**V5 pipeline inspector:** Use `python3 scripts/inspect_pipeline.py --step {step} --date {date}` instead of complex inline Python for state checks. Supports: s0/s1/s1e/s2/s3/s7/s8/all.

---

## §RUN-THEN-DELEGATE PROTOCOL

> **YOU run scripts. Subagents ONLY analyze.** This eliminates R17 violations where subagents sit idle.

### Orchestrator Script Execution Template (use for EVERY analytical step)

```
# 1. INSPECT inputs (pylanceRunCodeSnippet)
pylanceRunCodeSnippet: verify {input_file} exists, format matches script expectations

# 2. RUN script (you, the orchestrator, run this)
run_in_terminal:
  command: "PYTHONPATH=src .venv/bin/python3 scripts/{script}.py --date {date} --verbose 2>&1"
  mode: async
  timeout: {timeout_ms}

# 3. THINK-WHILE-WAITING (sequentialthinking + pylanceRunCodeSnippet)
sequentialthinking: {what to analyze while script runs}
pylanceRunCodeSnippet: {data checks, DB queries, upstream review}

# 4. MONITOR (get_terminal_output — watch for errors)
get_terminal_output(terminal_id) → check for:
  - 404/403 errors (source failures)
  - Timeout signals
  - 0 results / empty output
  - AGENT_SUMMARY:{json} line
→ If critical errors: kill terminal, diagnose, retry or escalate

# 5. EXTRACT metrics from AGENT_SUMMARY + verbose output
# 6. VALIDATE outputs (pylanceRunCodeSnippet — verify files/DB writes)

# 7. DELEGATE ANALYSIS to specialist
runSubagent(specialist_agent):
  ## Task: Analyze {step_name} output for {date}
  ### Script Output (AGENT_SUMMARY)
  {paste AGENT_SUMMARY JSON here}
  ### Key Warnings/Errors from Log
  {paste relevant warnings, max 50 lines}
  ### Upstream Context
  {paste upstream verdicts, quality flags, focus points}
  ### Your Job
  Analyze this output with your specialist knowledge.
  DO NOT run any scripts. Return analysis-only verdict.
  ### Expected Response
  Return agent-execution-protocol.instructions.md Model A verdict format.
```

### Pre-filled Run-Then-Delegate Blocks Per Step

| Step | Script | Timeout | THINK-WHILE-WAITING | Specialist Agent |
|------|--------|---------|---------------------|------------------|
| S2 tipsters | `tipster_xref.py` | 300000 | Read shortlist, identify tipster coverage gaps | bet-scout |
| S2.3 scrapers | `run_scrapers.py` | 300000 | Check shortlist sports, plan scraper selection | bet-enricher |
| S2.4 adapter | `scraper_to_team_form.py` | 120000 | Review scraper_runs results, assess data yield | bet-enricher |
| S2.5 enrich | `data_enrichment_agent.py` | 600000 | Check team_form coverage from scrapers, identify gaps | bet-enricher |
| S3 deep stats | `deep_stats_report.py` | 600000 | Read enrichment output, pre-load sport protocols | bet-statistician |
| S4 odds | `odds_evaluator.py` | 300000 | Read S3 deep stats, identify strongest stat edges | bet-valuator |
| S5 context | `context_checks.py` | 300000 | Review deep stats, draft bear cases for borderline | bet-challenger |
| S6 upset | `upset_risk.py` | 300000 | Review context output, prepare gate criteria | bet-challenger |
| S7 gate | `gate_checker.py` | 300000 | Review S3+S4+S5 verdicts, assess portfolio diversity | bet-challenger |
| S8 coupons | `coupon_builder.py` | 300000 | Review gate results, check bankroll config | bet-builder |

---

## §STRUCTURED SCRIPT OUTPUT (R19)

15 analytical scripts emit `AGENT_SUMMARY:{json}`: `discover_events.py`, `ingest_scan_stats.py`, `tipster_aggregator.py`, `tipster_xref.py`, `run_scrapers.py`, `scraper_to_team_form.py`, `data_enrichment_agent.py`, `deep_stats_report.py`, `gate_checker.py`, `coupon_builder.py`, `build_shortlist.py`, `odds_evaluator.py`, `context_checks.py`, `upset_risk.py`, `fetch_odds_multi.py`, `validate_coupons.py`. Exit codes: 0=OK, 1=partial, 2=critical. Scripts with `--sport` filter: `discover_events.py`, `tipster_aggregator.py`, `run_scrapers.py`.

---

## §DELEGATION TEMPLATE (analysis-only — subagents do NOT run scripts)

For every specialist delegation, the orchestrator has ALREADY run the script. Pass the output and append this response contract:

```
### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste AGENT_SUMMARY JSON}
Exit code: {0|1|2}
Key warnings/errors: {paste relevant log lines, max 50}

### Upstream Context
Previous verdicts: {list}
Quality flags: {list}
Focus points: {list}

### ⛔ Analysis-Only Mode
You do NOT run any scripts. Analyze the provided output with specialist knowledge.
Use pylanceRunCodeSnippet/read_file for deeper data inspection if needed.
Use sequentialthinking for per-candidate reasoning where required.

### Expected Response Format
Return Model A analysis-only verdict (agent-execution-protocol.instructions.md):
- `subagent_verdict` block with `verdict`, `quality_score`, `script`, `exit_code`, `execution_model: analysis-only`
- `### Metrics` with ≥3 rows from the provided script output
- `### Anomalies` with specific anomaly + root cause
- `### Analysis` with YOUR original specialist reasoning
- `### Impact`
- `### Issues`
- `### User Summary` with 2-3 plain-language sentences for the user
- `### Data For Orchestrator` with required keys: `next_step_ready`, `quality_flags`, `focus_points`

Facts-only sections: `subagent_verdict`, `Metrics`, `Anomalies`, `Issues`, `Data For Orchestrator`
Reasoning sections: `Analysis`, `Impact`, `User Summary`
Do NOT return free-form prose and do NOT rename the headers.
```

---

## §SUBAGENT OUTPUT VERIFICATION (after every runSubagent)

**5-question quality gate — if ANY answer is NO, REJECT and re-delegate:**
1. Does the response contain a `subagent_verdict` block with `verdict`, `quality_score`, `script`, `exit_code`, and `execution_model: analysis-only`?
2. Does `### Metrics` contain ≥3 specific metrics extracted from the provided script output?
3. Are `### Analysis` and `### User Summary` both present, with `User Summary` clearly plainer and different from `Analysis`?
4. Do `### Data For Orchestrator` and `### Impact` provide actionable next-step facts?
5. Does `### Issues` list specific blockers, or explicitly say `None`?

**Re-delegation instruction when rejecting:**
"Your output was rejected — the structured verdict is incomplete or shallow. You received script output for analysis — re-read it carefully. Return the full Model A verdict format."

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

### STEP S0.7: Stealth Cache Warmup (optional — run if odds data stale)

```bash
python3 scripts/daily_odds_warmup.py --date {date} --verbose
```

Stealth Playwright warm-up: dumps odds pages from protected bookmakers to `betting/data/html_cache/`. Downstream scripts (`odds_evaluator`, `deep_stats_report`) read from local cache instead of live-scraping. Only needed if `html_cache/` is empty or stale for the target date. Skip if today's cache files already exist.

---

### STEP S1: Event Discovery (fast — use sync)

**You launch discovery, then delegate review to bet-scanner.**

```bash
# API-first discovery via 3 sources (SofaScore, Odds API, API-Football) — ~30s
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose 2>&1
```

**EXECUTION:** Use `mode=sync` with `timeout=120000`. Discovery completes in ~30s. Parse `AGENT_SUMMARY:{json}` from output.

**AFTER scan completes — Delegate to bet-scanner** (read `.github/internal-prompts/bet-scan.prompt.md` first):

```
runSubagent("bet-scanner"):
---
## Task: S1 Scan Review for {date}

[Paste content of .github/internal-prompts/bet-scan.prompt.md]

### Context
- Date: {date}, Session: {session}
- Scan already completed. Review output quality.
- Check: betting/data/{date}_s1_events.json (discovery output)
- Use sequentialthinking to evaluate coverage
- Load skill: bet-navigating-sources
- Key checks:
  - 5-sport coverage: football, volleyball, basketball, tennis, hockey
  - Which of the 5 sports had 0 events? (source failure → retry with fallback)
  - Source cross-references: How many events confirmed by ≥2 sources?
  - Phantom fixture detection
  - Tournament protection (§SCAN.7) — major tournaments present?
  - Major domestic league protection (§SCAN.9) — Brasileirão, MLS, Liga MX, CSL, J-League, K-League, etc. present?
  - Minor league value (§SCAN.8)
  - Dedup quality: merges reasonable (expect 3-5%)?
- Return: APPROVED/FLAGGED/REJECTED + per_sport_counts + issues[]
---
```

---

### STEP S1-ingest: Ingest Scan Stats

```bash
python3 scripts/ingest_scan_stats.py --date {date} --verbose 2>&1
```

**AFTER:** Parse `AGENT_SUMMARY` from output → verify `verdict=OK`. If PARTIAL/FAILED → check which sports had ingestion errors before proceeding. This step transforms discovery data from `{date}_s1_events.json` into `stats_cache/` + DB `team_form`.

---

### STEP S1a: API Stats + ESPN Enrichment

```bash
python3 scripts/fetch_api_stats.py --date {date} 2>&1
python3 scripts/seed_espn_data.py --skip-players 2>&1
```

**Post-run check**: If `fetch_api_stats.py` reports 0 API responses, proceed in stats-first mode (R10) — API stats are supplemental to discovery scan data.

---

### STEP S1b: Odds + Weather + Tipster Fetch

```bash
python3 scripts/fetch_odds_api.py 2>&1
python3 scripts/fetch_weather.py --date {date} 2>&1
python3 scripts/tipster_aggregator.py --date {date} --verbose 2>&1
```

**Gemini feature flag:** Add `--use-gemini` to `tipster_aggregator.py` to use Gemini URL reading instead of BS4 HTML parsing. Gemini reads tipster pages natively, extracting structured picks without fragile CSS selectors. Falls back to BS4 if Gemini fails per site.

```bash
# WITH Gemini (recommended — better extraction, no CSS selector maintenance):
python3 scripts/tipster_aggregator.py --date {date} --use-gemini --verbose 2>&1
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
- **§ASYNC:** Include the Mandatory Async Block from §ASYNC DELEGATION ENFORCEMENT (S2 tipsters row, timeout=300000)
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

> ⚡ **PARALLEL EXECUTION:** S2 (tipster xref) and S2.3 (scrapers) are INDEPENDENT — they both read from the shortlist but neither depends on the other's output. Launch BOTH via separate `runSubagent` calls simultaneously. Collect both verdicts, then proceed to S2.4 → S2.5 sequentially. This halves wall-clock time.

### STEP S2.3: Run Scrapers (NEW — scraper data collection)

**Orchestrator runs scrapers for today's sports, then delegates analysis to bet-enricher.**

**Step 1: RUN script (you, the orchestrator):**
```bash
PYTHONPATH=src .venv/bin/python scripts/run_scrapers.py --sport all --season 2425 --verbose 2>&1
```
Mode: `async`, timeout: `300000` (scrapers take ~2-3 min total, FBref is slowest at ~66s)

**Step 2: THINK-WHILE-WAITING:**
- Review shortlist composition by sport
- Check which scrapers are relevant for today's fixtures

**Step 3: MONITOR + EXTRACT:**
- Watch for 403 errors (Volleybox known to 403)
- Extract `AGENT_SUMMARY:{json}` with per-scraper results
- Note: 10/14 scrapers typically succeed; Volleybox + SofaScore stubs expected to have issues

**Step 4: Note output for S2.4 (DO NOT delegate yet — wait for S2.4 to also complete).**

---

### STEP S2.4: Scraper-to-Team-Form Adapter (NEW — bridge scraper data to pipeline)

**Orchestrator runs adapter, then delegates combined S2.3+S2.4 analysis to bet-enricher.**

**Step 1: RUN script (you, the orchestrator):**
```bash
PYTHONPATH=src .venv/bin/python scripts/scraper_to_team_form.py --date {date} --verbose 2>&1
```
Mode: `sync`, timeout: `120000` (DB-only processing, no HTTP, ~30s)

**Step 2: EXTRACT + VALIDATE:**
- Parse `AGENT_SUMMARY:{json}` — teams_processed, team_form_rows_written, gaps
- Check `team_form` table for rows with `source LIKE 'scrapers%'`

**Step 3: Delegate combined S2.3+S2.4 analysis to bet-enricher:**
```
runSubagent("bet-enricher"):
---
## Task: Analyze S2.3 Scrapers + S2.4 Adapter output for {date}

### Script Outputs (already executed by orchestrator)
S2.3 AGENT_SUMMARY (run_scrapers.py): {paste extracted JSON}
S2.4 AGENT_SUMMARY (scraper_to_team_form.py): {paste extracted JSON}
Exit codes: S2.3={0|1|2}, S2.4={0|1|2}
Key warnings: {paste source failures, 403s, gaps}

### Upstream Context
- Shortlist: {count} candidates across {sports}
- Scraper results: {X} scrapers succeeded, {Y} failed
- team_form rows from scrapers: {count}

### ⛔ Analysis-Only Mode
DO NOT run any scripts. Analyze scraper + adapter output.
Key assessment: which sports/teams are covered by scrapers? Which gaps remain for S2.5?
Return: Model A verdict + explicit gap list for S2.5 enrichment
---
```

---

### STEP S2.5: Data Enrichment (now GAP-FILL FALLBACK — only fills what scrapers missed)

**Orchestrator runs enrichment script, then delegates analysis to bet-enricher.**

**Step 1: INSPECT inputs (pylanceRunCodeSnippet):**
Verify shortlist exists: `betting/data/{date}_s2_shortlist.json`
Check team_form baseline count in DB.

**Step 2: RUN script (you, the orchestrator):**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/data_enrichment_agent.py --date {date} --news --verbose 2>&1
```
Mode: `async`, timeout: `600000`

**Step 3: THINK-WHILE-WAITING:**
- Check which teams already have form data in DB
- Review source health from previous runs
- Plan S3 approach based on shortlist composition

**Step 4: MONITOR + EXTRACT:**
- Watch for 404/403 errors from Flashscore/ESPN (react immediately if critical)
- Extract `AGENT_SUMMARY:{json}` line
- Note key warnings (source failures, low yield)

**Step 5: VALIDATE outputs (pylanceRunCodeSnippet):**
Run `python3 scripts/validate_phase.py --date {date} --phase data --format json`

**Step 6: Delegate analysis to bet-enricher:**
```
runSubagent("bet-enricher"):
---
## Task: Analyze S2.5 Enrichment output for {date}

[Paste content of .github/internal-prompts/bet-enrich.prompt.md]

### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste extracted JSON}
Exit code: {0|1|2}
Key warnings: {paste source failures, 404s, low yield sources}

### Upstream Context
- Shortlist: {count} candidates across {sports}
- team_form baseline: {count} rows before enrichment

### ⛔ Analysis-Only Mode
DO NOT run data_enrichment_agent.py. Analyze the provided output.
Use pylanceRunCodeSnippet to inspect enrichment results in DB if needed.
Key assessment: enrichment yield %, per-sport data quality, gap recoverability.
Load skills: bet-navigating-sources, bet-analyzing-statistics
Return: Model A analysis-only verdict
---
```

**GATE:** If bet-enricher returns REJECTED (yield <40%) → STOP, escalate to user.

---

### ⛔ DATA PHASE GATE (MANDATORY before S3)

Run validation BEFORE entering the analysis phase. This is your checkpoint — do NOT skip it.

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase data --format json 2>&1
```

**Assertion checklist (verify ALL before proceeding):**
- [ ] Exit code 0 (all gates pass) or 2 (warnings only, non-blocking)
- [ ] D3: scan_results > 0 for today
- [ ] D6: candidates available (shortlist or analysis_results > 0)
- [ ] D8: candidate count ≥ 20
- [ ] D13: market_matrix_{date}.json exists

**If exit code 1 (gate failure):** Read the JSON output, identify WHICH gate failed, run the recovery command shown in output. Re-run validation after fix. Do NOT proceed to S3 with gate failures.

---

## ═══════════════════════════════════════════════
## ANALYSIS (Steps S3 → S7) — ORCHESTRATOR RUNS SCRIPTS, AGENTS ANALYZE
## ═══════════════════════════════════════════════

> **⛔ YOU run every script in this section. Then delegate output to specialist agent for analysis.**
> **Each step = RUN script → EXTRACT output → runSubagent(analysis-only) → receive verdict.**
> **You evaluate the verdict with `sequentialthinking`, then decide: PROCEED / RETRY / ESCALATE.**

### STEP S3: Deep Statistical Analysis

**Orchestrator runs deep_stats_report.py, then delegates analysis to bet-statistician.**

**Step 1: INSPECT inputs (pylanceRunCodeSnippet):** Verify enrichment output, team_form per sport.

**Step 2: RUN script:**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/deep_stats_report.py --date {date} --shortlist betting/data/{date}_s2_shortlist.json --top 200 --gemini --verbose 2>&1
```
Mode: `async`, timeout: `600000`

**Step 3: THINK-WHILE-WAITING:** Read enrichment output, pre-load sport protocol requirements, assess data quality per candidate.

**Step 4: MONITOR + EXTRACT:** Parse `AGENT_SUMMARY:{json}`. Note data quality scores, candidate counts.

**Step 5: VALIDATE outputs (pylanceRunCodeSnippet):** Verify output files exist with expected structure.

**Step 6: Delegate analysis to bet-statistician:**
```
runSubagent("bet-statistician"):
---
## Task: Analyze S3 Deep Stats output for {date}

[Paste content of .github/internal-prompts/bet-deep-stats.prompt.md]

### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste extracted JSON}
Exit code: {0|1|2}
Key warnings: {paste data quality issues, missing H2H, etc.}

### Upstream Context
- Enrichment verdict: {from S2.5}
- Quality flags: {from S2.5 — e.g., hockey=PARTIAL}
- Candidates: {count} total

### ⛔ Analysis-Only Mode
DO NOT run deep_stats_report.py. Analyze the provided output with specialist knowledge.
Use pylanceRunCodeSnippet to read deep stats JSON for per-candidate details.
Use sequentialthinking for EVERY CANDIDATE (5-part Analytical Reasoning Layer).
Load skills: bet-analyzing-statistics, bet-applying-sport-protocols
Key checks: R5 (stat markets FIRST), three-way cross-check, edge mechanisms
Return: Model A analysis-only verdict
---
```

> **S3B Trigger**: If earliest kickoff is ≤3h away, delegate `bet-time-sensitive.prompt.md` to bet-statistician BEFORE S4.

---

### STEP S4: Odds Evaluation

**Orchestrator runs odds_evaluator.py, then delegates analysis to bet-valuator.**

**Step 1: INSPECT + RUN:**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/odds_evaluator.py --date {date} --verbose 2>&1
```
Mode: `async`, timeout: `300000`. Also run `python3 scripts/fetch_odds_api.py` for cross-validation.

**Step 2: THINK-WHILE-WAITING:** Read S3 deep stats, identify strongest stat edges.

**Step 3: EXTRACT + VALIDATE + Delegate:**
```
runSubagent("bet-valuator"):
---
## Task: Analyze S4 Odds output for {date}

[Paste content of .github/internal-prompts/bet-odds-ev.prompt.md]

### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste extracted JSON}
Exit code: {0|1|2}
Key warnings: {paste drift flags, missing odds sources}

### Upstream Context
- S3 verdict: {from bet-statistician}
- Quality flags: {from S3}

### ⛔ Analysis-Only Mode
DO NOT run odds_evaluator.py. Analyze provided EV data with specialist knowledge.
Use pylanceRunCodeSnippet to read odds data for deeper inspection.
Key checks: EV per candidate, drift >8%, R10 stats-first for no-odds events, Kelly 1/4
Load skill: bet-evaluating-odds
Return: Model A analysis-only verdict
---
```

---

### STEP S5+S6: Context + Upset Risk (combined)

**Orchestrator runs both scripts, then delegates combined analysis to bet-challenger.**

**Step 1: RUN context_checks.py:**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/context_checks.py --date {date} --verbose 2>&1
```
Mode: `async`, timeout: `300000`

**Step 2: THINK-WHILE-WAITING:** Review deep stats, draft bear cases for borderline candidates.

**Step 3: RUN upset_risk.py (after context_checks completes):**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/upset_risk.py --date {date} --verbose 2>&1
```
Mode: `async`, timeout: `300000`

**Step 4: EXTRACT both AGENT_SUMMARYs + Delegate:**
```
runSubagent("bet-challenger"):
---
## Task: Analyze S5+S6 Context + Upset Risk output for {date}

[Paste content of .github/internal-prompts/bet-context-upset.prompt.md]

### Script Output (already executed by orchestrator)
context_checks AGENT_SUMMARY: {paste JSON}
upset_risk AGENT_SUMMARY: {paste JSON}
Exit codes: context={0|1|2}, upset={0|1|2}
Key warnings: {paste weather flags, injury reports, risk distributions}

### Upstream Context
- S3 verdict: {from bet-statistician}
- S4 verdict: {from bet-valuator}

### ⛔ Analysis-Only Mode
DO NOT run context_checks.py or upset_risk.py. Analyze provided output.
Use pylanceRunCodeSnippet to inspect context/upset data files for per-candidate details.
Use sequentialthinking for 5-part Deep Adversarial Reasoning per candidate.
Load skills: bet-applying-sport-protocols, bet-analyzing-statistics
Return: Model A analysis-only verdict
---
```

---

### STEP S7: 18-Point Advisory Gate

**Orchestrator runs gate_checker.py, then delegates analysis to bet-challenger.**

**Step 1: INSPECT + RUN:**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/gate_checker.py --date {date} --verbose 2>&1
```
Mode: `async`, timeout: `300000`

**Step 2: THINK-WHILE-WAITING:** Review S3+S4+S5 verdicts, assess portfolio diversity.

**Step 3: EXTRACT + VALIDATE + Delegate:**
```
runSubagent("bet-challenger"):
---
## Task: Analyze S7 Gate output for {date}

[Paste content of .github/internal-prompts/bet-gate.prompt.md]

### Script Output (already executed by orchestrator)
AGENT_SUMMARY: {paste JSON}
Exit code: {0|1|2}
Key warnings: {paste tier distribution, gate failures, data quality issues}

### Upstream Context
- S3 verdict: {from bet-statistician}
- S4 verdict: {from bet-valuator}
- S5+S6 verdict: {from bet-challenger context/upset}

### ⛔ Analysis-Only Mode
DO NOT run gate_checker.py. Analyze provided gate output with adversarial specialist knowledge.
Use pylanceRunCodeSnippet to read gate results for per-candidate details.
Use sequentialthinking per candidate for bear cases.
Key checks: R3 (all candidates visible), R14 (data quality), R4 (no forced diversity)
Load skills: bet-applying-sport-protocols, bet-analyzing-statistics
Return: Model A analysis-only verdict
---
```

**GATE:** If >50% candidates have MINIMAL data quality → enrichment failure. Spawn web_research_agent.py (R15).

---

### ⛔ ANALYSIS PHASE GATE (MANDATORY before S8)

Run validation BEFORE entering the build phase. This is your checkpoint — do NOT skip it.

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase analysis --format json 2>&1
```

**Assertion checklist (verify ALL before proceeding):**
- [ ] Exit code 0 or 2
- [ ] A1: S3 deep stats output exists (analysis_results in DB or JSON)
- [ ] A2: gate_results exist (S7 ran)
- [ ] A3: ≥1 candidate with APPROVED or EXTENDED status
- [ ] A5: STRONG+MODERATE ≥ 3 candidates (enough for coupons)

**If exit code 1 (gate failure):** Read the JSON output, identify WHICH gate failed. If A5 fails (too few approved picks), trigger emergency expansion: re-run `build_shortlist.py --date {date} --stats-first --force` then re-delegate S3→S7 with expanded pool. Do NOT build coupons from insufficient picks.

---

## ═══════════════════════════════════════════════
## BUILD (Steps S8 → S10) — DELEGATED TO bet-builder
## ═══════════════════════════════════════════════

### STEP S8+S9: Build + Validate Coupons

**Orchestrator runs coupon_builder.py, then delegates analysis to bet-builder.**

**Step 1: INSPECT + RUN:**
```bash
PYTHONPATH=src .venv/bin/python3 scripts/coupon_builder.py --date {date} --verbose 2>&1
```
Mode: `async`, timeout: `300000`

**Step 2: THINK-WHILE-WAITING:** Review gate results, check bankroll config, prepare portfolio strategy.

**Step 3: EXTRACT + VALIDATE:**
Parse `AGENT_SUMMARY:{json}`. Run: `python3 scripts/validate_phase.py --date {date} --phase build --format json`

**Step 4: Delegate analysis to bet-builder:**
```
runSubagent("bet-builder"):
---
## Task: Analyze S8+S9 Coupon Build output for {date}

[Paste content of .github/internal-prompts/bet-portfolio.prompt.md]

### Script Output (already executed by orchestrator)
coupon_builder AGENT_SUMMARY: {paste JSON}
validate_phase output: {paste validation results}
Exit code: {0|1|2}
Key warnings: {paste arithmetic issues, exposure warnings}

### Upstream Context
- S7 gate verdict: {from bet-challenger}
- Config: bankroll={X}, daily_cap={Y}
- Approved candidates: {count STRONG + MODERATE}

### ⛔ Analysis-Only Mode
DO NOT run coupon_builder.py or validate_coupons.py. Analyze provided output.
Use pylanceRunCodeSnippet to read coupon files for per-coupon validation.
Use sequentialthinking for 4-part Portfolio Intelligence Layer.
Key checks: arithmetic, unique events, R5 (≥60% stat markets), R14, R12 conditional
Load skills: bet-building-coupons, bet-formatting-artifacts
Return: Model A analysis-only verdict
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

### ⛔ BUILD PHASE GATE (MANDATORY before presenting to user)

Run validation BEFORE presenting results.

```bash
PYTHONPATH=src python3 scripts/validate_phase.py --date {date} --phase build --format json 2>&1
```

**Assertion checklist (verify ALL before presenting):**
- [ ] Exit code 0 or 2
- [ ] B1: Coupon files exist in `betting/coupons/`
- [ ] B2: Each coupon has ≥2 legs
- [ ] B3: Total stake ≤ 25% bankroll
- [ ] B4: No duplicate events across core coupons
- [ ] B5: Arithmetic verified (combined odds match leg multiplication ±0.02)

**If exit code 1:** Fix coupons before presenting. Re-delegate to bet-builder with specific issues.

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
| 13 | Fire-and-forget long scripts | Use `mode=async` + THINK-WHILE-WAITING. Launch async, actively analyze previous step data while waiting. Call `get_terminal_output` when complete → EXTRACT → THINK → RETURN (R17). |
| 14 | Skip data quality checks | Proceeding without checking data_quality_score. FULL/PARTIAL are core requirements. |
| 15 | Ignore live betting window | Excluding events ≤1h to kickoff. Betclic allows live betting (R16). |

---
## §THINK IN THE MIDDLE

> All agents follow `agent-execution-protocol.instructions.md` v6 for the 6-step INSPECT→RUN→THINK→ANALYZE→VALIDATE→VERDICT cycle.
> V6 adds: `pylanceRunCodeSnippet` for INSPECT (before) and VALIDATE (after) every script. Tool Selection Matrix. Anti-patterns expanded to 20.
> R18 data flow verification: `DATA_FLOW_CONTRACTS` in `agent_protocol.py` + `validate_input_contract()` for programmatic enforcement.
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
| R9 SELF-HEALING DATA | Missing data → auto-fallback L1→L6, then L7a Gemini Search Grounding (primary), L7b SerpAPI, L7c Playwright. See `SELF_HEALING_REGISTRY` in agent_protocol.py. | S1, S2.5, S3 |
| R10 STATS-FIRST | Events without odds NOT excluded | S4, S7 |
| R11 SEQUENTIAL THINKING | sequentialthinking per step + per candidate in S3 | ALL |
| R12 CONDITIONAL | Coupon carries conditional disclaimer | S8 |
| R13 MAJOR DOMESTIC LEAGUE | Brasileirão/MLS/Liga MX/CSL/J-League/K-League present when active | S1e |
| R14 DATA DEPTH | data_quality_score computed per candidate. FULL/PARTIAL only in core coupons | S3, S7, S8 |
| R15 WEB RESEARCH | Missing H2H/injuries → spawn web_research_agent.py. Max 5 SerpAPI + 10 Playwright | S2.5, S3 |
| R16 LIVE WINDOW | 06:00→05:59 next day. Events ≤1h to kickoff or in-play = LIVE, include in scan | S1, S1e |
| R17 LIVE SCRIPT MONITORING | ALWAYS --verbose. Read FULL output. Extract metrics. Report specific numbers. React to errors. If timeout: use get_terminal_output to diagnose. | ALL |
| R18 DATA FLOW VERIFICATION | Before running a script, READ its code to understand inputs/outputs. TRACE producer→consumer: do JSON keys, DB tables, field names match? Verify with actual data. READ CODE → THINK → CHECK → FIX. | ALL |
| R19 STRUCTURED OUTPUT | 15 analytical scripts support `--verbose` + `AGENT_SUMMARY:{json}` (see §STRUCTURED SCRIPT OUTPUT). Use `--verbose` on those scripts. Parse AGENT_SUMMARY for verdict/metrics/issues. Exit: 0=OK, 1=partial, 2=critical. | ALL |

---

## DELEGATION REFERENCE

| Step | Internal Prompt | Agent |
|------|----------------|-------|
| S0 Settlement | `bet-settle.prompt.md` | bet-settler |
| S0.5 DB Quality | `bet-db-quality.prompt.md` | bet-db-analyst |
| S1 Scan | `bet-scan.prompt.md` | bet-scanner |
| S1 Scan (sport-specific) | Use `bet-scan.prompt.md` with `--sport {sport}` filter | bet-scanner |
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

## RESCAN PROTOCOL (when rescan=true)

Use after **infrastructure changes** — new API clients deployed, data sources added/removed, client overhauls. This wipes stale data that was collected with OLD infrastructure and re-runs the full pipeline with the NEW sources.

### When to use
- New API clients added (e.g., BetExplorer, OddsPortal, TotalCorner, Scores24, Soccerway)
- Existing client fixed (e.g., stealth alignment, new selectors)
- unified.py routing changed (new fallback chains)
- Source registry updated

### Execution

```bash
# 1. Wipe stale scan results for the date
sqlite3 betting/data/betting.db "DELETE FROM scan_results WHERE date(created_at) >= '{date}' AND date(created_at) < date('{date}', '+1 day');"
sqlite3 betting/data/betting.db "DELETE FROM scan_run_stats WHERE date(started_at) >= '{date}';"

# 2. Wipe stale analysis results (computed from old data)
sqlite3 betting/data/betting.db "DELETE FROM analysis_results WHERE betting_date='{date}';"
sqlite3 betting/data/betting.db "DELETE FROM gate_results WHERE betting_date='{date}';"

# 3. Backup old coupons (will be rebuilt from scratch)
mv betting/coupons/{date}.md betting/coupons/{date}.md.pre-rescan 2>/dev/null; true
mv betting/coupons/{date}.json betting/coupons/{date}.json.pre-rescan 2>/dev/null; true

# 4. Clear stale shortlist/matrix artifacts
rm -f betting/data/{date}_s2_shortlist.json betting/data/market_matrix_{date}.json 2>/dev/null; true
rm -f betting/data/{date}_s3_deep_stats.json betting/data/{date}_s7_gate_results.json 2>/dev/null; true
```

Then run the FULL pipeline from S0.5 (skip S0 settlement — that's for the previous day):
- S0.5 → S0.7 → S1 → S1-ingest → S1a → S1b → S1c → S1d → S1e → S2 ∥ S2.5 → S3 → S4 → S5+S6 → S7 → S8+S9 → S10

**Key difference from rerun:** Rescan wipes stale data FIRST. Rerun just increments version and builds on existing data.

## SESSION PARITY

ALL sessions execute the SAME pipeline. Only the time window differs. Night/morning sessions get FULL analysis. If <3 picks survive after expansion → flag THIN DAY, present as singles + extended pool.

## KNOWN FAILURE PATTERNS

1. **PHANTOM GAMES**: ZT/tipster sites list tips for games that already played. Verify on Flashscore before shortlisting.
2. **BETCLIC LINE MISMATCH**: Do not assume BetExplorer lines = Betclic. When avg ≈ line → zero edge → DROP.
3. **MARKET UNAVAILABILITY**: Top market not on Betclic → need fallback. Check availability BEFORE deep analysis.
4. **INSUFFICIENT PICKS**: If <4 picks survive S7 → expand shortlist (§2.1). If <3 survive after expansion → flag THIN DAY, present as singles + extended pool. User decides.
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


## STEP S11: KNOWLEDGE TRANSFER & MEMORY UPDATE (CRITICAL)

At the end of the session, or immediately if a critical pipeline break was fixed, you **MUST** save this knowledge to memory using the `memory` tool. This prevents the "amnesia" loop where the same bugs reappear tomorrow.

1. Unresolved Exceptions / Future Work: Use `memory` to write into `/memories/session/{date}-notes.md`.
2. Permanent Pipeline Fixes / Instructions: Use `memory` tool to create or update files in `/memories/repo/` (e.g., `/memories/repo/pipeline-lessons-learned.md`).
3. **DO NOT SKIP THIS**. If you found a bug (e.g., a 403 Forbidden, an API attribute missing, a wrong loop, etc.), make sure it is documented!
