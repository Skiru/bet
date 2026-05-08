---
name: orchestrate-betting-day
description: "Full daily cycle: 4-pass pipeline (Discovery → Fixes → Polish → Final) with settlement, scan, deep analysis, coupons."
agent: bet-orchestrator
argument-hint: "run_date=2026-04-27 session=full" or "run_date=2026-04-27 session=night rerun=true"
---

# BETTING DAY ORCHESTRATOR

Run the full S0→S10 pipeline for a betting day. Executes 3 TEST passes to find and fix errors, then 1 FINAL pass to produce coupons.

## DELEGATION ARCHITECTURE

This prompt defines WHAT to do. Agent delegation uses internal-prompts that define HOW:

| Pipeline Step | Internal Prompt | Agent |
|---------------|----------------|-------|
| S0 Settlement | `.github/internal-prompts/bet-settle.prompt.md` | bet-settler |
| S1+S1a-S1e Scan+Enrich+Shortlist | `.github/internal-prompts/bet-scan.prompt.md` | bet-scanner |
| S1e Shortlist (refinement) | `.github/internal-prompts/bet-shortlist.prompt.md` | bet-scanner |
| S2 Tipsters | `.github/internal-prompts/bet-tipsters.prompt.md` | bet-scout |
| S2.5 Data Enrichment | `.github/internal-prompts/bet-enrich.prompt.md` | bet-enricher |
| S3 Deep Stats | `.github/internal-prompts/bet-deep-stats.prompt.md` | bet-statistician |
| S3B Time-Sensitive | `.github/internal-prompts/bet-time-sensitive.prompt.md` | bet-statistician |
| S4 Odds/EV | `.github/internal-prompts/bet-odds-ev.prompt.md` | bet-valuator |
| S5 Context | `.github/internal-prompts/bet-context-upset.prompt.md` | bet-challenger |
| S6 Upset Risk | `.github/internal-prompts/bet-context-upset.prompt.md` | bet-challenger |
| S7 Gate | `.github/internal-prompts/bet-gate.prompt.md` | bet-challenger |
| S8 Portfolio | `.github/internal-prompts/bet-portfolio.prompt.md` | bet-builder |
| S9 Validation | `.github/internal-prompts/bet-validate.prompt.md` | bet-builder |
| S10 Summary | _(automated)_ | _(script)_ |

When delegating via `runSubagent`, read the internal-prompt file and pass its content as the task prompt.

## NON-NEGOTIABLE RULES (R1-R12) — ENFORCED AT EVERY STEP

These rules are defined in `copilot-instructions.md` and apply to EVERY agent, EVERY session, EVERY step. The orchestrator MUST verify compliance at each checkpoint.

| Rule | Enforcement Point | What Orchestrator Checks |
|------|------------------|-------------------------|
| **R1 AGENT-DRIVEN** | Every step | Script ran → agent analyzed → reasoned output produced |
| **R2 DB-FIRST** | S1-S8 | All data reads use `get_db()`, not raw JSON |
| **R3 NO AUTO-REJECTION** | S7, S8 output | ALL candidates in matrix. No "rejected due to" language. Extended Pool has gate-failed picks. |
| **R4 NO AGGRESSIVE NARROWING** | S7→S8 gate | ≥5 sports in approved picks. If <5 → emergency expansion before S8. |
| **R5 STATS > OUTCOMES** | S3, S8 | Every football match has ≥1 corners/fouls/shots market. Statistical markets dominate portfolio. |
| **R6 BETCLIC ADVISORY** | S0, S3, S7 | Hit rates shown prominently. Zero auto-penalties based on history. |
| **R7 TOURNAMENT PROTECTION** | S1, S1e | All major tournament matches present. +15 boost applied. |
| **R8 MINOR LEAGUE VALUE** | S1e, S3 | No "obscure league" penalties. +6 value boost for non-top-5. |
| **R9 SELF-HEALING** | S2.5, S3 | Missing data → enrichment sub-agent triggered. Yield ≥60%. |
| **R10 STATS-FIRST** | S4, S7, S8 | Events without odds NOT excluded. Shown with min acceptable odds. |
| **R11 SEQUENTIAL THINKING** | S0-S10 | `sequentialthinking` used per step AND per candidate (S3-S7). |
| **R12 CONDITIONAL** | S8 output | Coupon file carries conditional disclaimer. Betclic verification noted. |

**VIOLATION OF ANY RULE = PIPELINE FAILURE.** The orchestrator re-runs the affected step until compliance is achieved.

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

## SESSION PARITY RULE (NEVER VIOLATE)

**ALL sessions (full/day/night/morning) execute the EXACT SAME pipeline:**
- Same 4-pass protocol (Discovery → Targeted Fixes → Polish → Final)
- Same S0 → S1 → S1a(discover) → S1b(PARALLEL: odds+weather+tipsters) → S1c(aggregate) → S1d → S1e → S2(tipster xref) → S2.5(enrichment) → S3 → S4(odds eval) → S5(context) → S6(upset risk) → S7(gate) → S3B(time-sensitive) → S8(coupons) → S9(validate) → S10(summary) automated step sequence
- Same 14-sport scan in S1 (ALL sports, even if most have 0 events in the window)
- Same deep analysis (S3-S7): H2H, tipsters, injuries, bear case, 18-point gate
- Coupon count = f(quality events, deep statistics), NOT f(bankroll). Produce as many as quality justifies.
- Same V1-V10 validation + §S8.FINAL Mechanical Verification

**The ONLY difference is the event time window filter in S2.** Nothing else changes.

If the time window yields fewer events → the shortlist is smaller → fewer picks → but each pick gets FULL analysis. If <3 picks survive → declare NO BET for that session. NEVER produce 1-2 shallow coupons as a compromise.

**This rule exists because of the v10 night session failure:** agent produced 2 "compact" coupons with 3 sports scanned, zero tipster checks, zero H2H, zero injuries. That is NEVER acceptable.

## KNOWN FAILURE PATTERNS (from production incidents — CHECK EACH RUN)

1. **PHANTOM OVERNIGHT GAMES (v5, 2026-04-29):** ZT/tipster sites list tips for NBA/NHL games at 01:00-04:00 CEST. These games often ALREADY PLAYED the previous night. Check: if tip was posted >12h ago AND game time < current time → verify on Flashscore. Look for post-game comments on ZT page ("W plecy", scores). NEVER shortlist an event without verifying it hasn't already been played.

2. **BETCLIC LINE MISMATCH (v3, 2026-04-29):** Analysis assumed Betclic line 20.5 (frames) but actual was 22.5. When avg = line → zero edge → MUST DROP. Always verify the ACTUAL Betclic line before committing to a pick. Don't assume the line from BetExplorer/OddsPortal applies to Betclic.

3. **BETCLIC MARKET UNAVAILABILITY (v4, 2026-04-29):** Top-ranked market (fouls O22.5, safety 0.80) not available on Betclic for Finnish football. Forced last-minute fallback to weaker market (goals O2.5, safety 0.60). Check Betclic sport section for market availability BEFORE deep §3.0 analysis.

4. **INSUFFICIENT PICKS WITHOUT EXPANSION (v4, 2026-04-29):** v4 had only 3 picks after dropping Higgins. Should have triggered shortlist expansion (§2.1) rather than producing coupons with <4 picks. If a pick drops during S7 → immediately check for replacement candidates from ZT/tipster pool.

5. **MISSING TIPSTER CANDIDATES (v3, 2026-04-29):** ZT had 57 tips including strong statistical market picks (Tromsø CK from 63% tipster, Sporting CK from 70% tipster, Fils-Lehecka games from 75% tipster) that were NOT shortlisted. Always scan ZT for statistical-market tips with reasoning and promote them to shortlist per §1.5.

---

## PRE-FLIGHT (runs once before Pass 1)

### OPTION A: Pipeline Orchestrator (RECOMMENDED — two-phase approach)

**Phase 1: Data Collection (automated script)**
```bash
python3 scripts/pipeline_orchestrator.py --date YYYY-MM-DD [--session full|day|night|morning] [--resume]
```

This runs the ENTIRE data pipeline S0→S10 automatically, producing raw data artifacts. It executes:
- **S0**: Betclic history analysis (`analyze_betclic_learning.py`)
- **S1**: Full 14-sport scan (`scan_events.py --parallel-sport`) — **per-sport parallel scanning** (11 groups, independent timeouts: football 15min, others 2-5min)
- **S1a**: API fixture discovery + stats enrichment (`discover_fixtures.py` + `fetch_api_stats.py`, timeout: 10 min)
- **S1b**: Odds + weather + tipsters in PARALLEL (ThreadPoolExecutor, 5 workers, timeout: 10 min)
- **S1c**: Aggregate scan + analysis pool (`aggregate_and_select.py` + `deep_analysis_pool.py`, timeout: 2 min)
- **S1d**: Market matrix generation (`generate_market_matrix.py --stats-first`, timeout: 2 min)
- **S1e**: Ranked shortlist (`build_shortlist.py --stats-first`, all candidates — no cap, timeout: 2 min)
- **S2**: Tipster cross-reference (timeout: 1 min)
- **S2.5**: Data enrichment — self-healing fetch of missing team stats from Flashscore/Sofascore/ESPN for shortlisted candidates (timeout: 15 min)
- **S3**: Deep stats analysis — **8-worker parallel candidate analysis**, Poisson/NegBin probability enrichment, error-resilient (timeout: 10 min)
- **S4**: Odds evaluation — cross-validate odds, compute EV, detect drift >8% (timeout: 2 min)
- **S5**: Context checks — weather impact, venue, referee, roster changes (timeout: 1 min)
- **S6**: Upset risk scoring — sport-specific checklists (timeout: 2 min)
- **S7**: 18-point advisory gate — **stats-first EV fix** (passes candidates without odds with advisory tier), sport-specific H2H penalties (timeout: 5 min)
- **S8**: Coupon construction — Kelly 1/4 staking with true probability, rich per-leg Polish analysis (timeout: 2 min)
- **S9**: V1-V10 validation (expanded odds regex matches `@1.85` and `(1.85)`)
- **S10**: Final summary

State tracking with `--resume` support. Use `--status` to check progress. Use `--skip-scan` to re-run analysis only.

**Per-step timeouts** — each step has its own timeout (scan: 15 min, S3: 10 min, gate: 5 min, etc.) instead of a single 40-minute global timeout. A slow scan won't block the entire pipeline.

**SQLite DB** — all pipeline outputs are dual-written to `betting/data/betting.db` (28-table schema organized by domain: **Core** — sports, teams, competitions, fixtures, athletes; **Stats** — team_form, match_stats, league_profiles, standings, power_index; **Analysis** — analysis_results, analysis_raw_data, gate_results, decision_snapshots, decision_outcomes; **Betting** — coupons, bets, odds_history; **Pipeline** — pipeline_runs, scan_results, scan_run_stats, source_health; **ESPN** — espn_predictions, player_gamelogs, player_splits, team_ats_records, team_ou_records, team_rosters) alongside flat files. Team aliases stored as JSON in `teams` table. Always use `from bet.db.connection import get_db` context manager — never raw `sqlite3.connect()`.

**Config keys used:** `bankroll_pln` (fallback: `working_bankroll_pln`), `daily_exposure_range` (fallback: `suggested_daily_allocation_range_pln`), `db_path`.

### OPTION B: Manual step-by-step (fallback)

Before any pass, ensure:
1. Run Betclic history analysis: `python3 scripts/analyze_betclic_learning.py` → reads `betting/data/betclic_bets_history.json` (MANDATORY — ground truth of all placed bets)
2. Run parallel scan: `python3 scripts/scan_events.py --parallel-sport --urls-file config/scan_urls.json --deep --date YYYY-MM-DD` → runs per-sport scanners with independent timeouts, stores results in DB `scan_results` + `scan_run_stats` tables
3. Run enrichment + aggregation steps individually:
   - **API fixtures**: `python3 scripts/discover_fixtures.py --date YYYY-MM-DD` — queries API-Football (1000+ leagues), API-Basketball (50+ leagues), API-Hockey, API-Tennis, API-Volleyball, API-Handball, API-Baseball, TheSportsDB
   - **API stats**: `python3 scripts/fetch_api_stats.py --date YYYY-MM-DD` — L10 form + H2H for all discovered teams with fallback chains across 7 sport APIs
   - **Analysis pool**: `python3 scripts/deep_analysis_pool.py --date YYYY-MM-DD` → outputs `betting/data/analysis_pool_{date}.json` + `.md`
   - **Aggregate**: `python3 scripts/aggregate_and_select.py --date YYYY-MM-DD`
   - Check DB: `scan_results`, `fixtures`, `team_form` tables populated
4. Log source health: `python3 scripts/source_health.py --log` → check for degraded sources. **Note:** Source health is also auto-tracked in DB `source_health` table by every API client call (success/failure recorded via `SourceHealthRepo`)
4. Run odds cross-validation (choose one):
   - **Single-source**: `python3 scripts/fetch_odds_api.py` — The-Odds-API only (30 credits/scan)
   - **Multi-source (RECOMMENDED)**: `python3 scripts/fetch_odds_multi.py` — aggregates 5 sources (The-Odds-API + API-Football + OddsPortal + BetExplorer + Betclic) per sport priority chain. Produces backward-compatible `odds_api_snapshot.json` + `odds_api_summary.csv` + `odds_multi_sources.json` provenance log.
5. **Generate market matrix**: `python3 scripts/generate_market_matrix.py --date YYYY-MM-DD --stats-first`
   - Combines ALL data sources (fixtures, odds, scan, stats cache, analysis pool)
   - Produces `betting/data/market_matrix_{date}.json` + `.md` (full event universe with ALL odds/safety data)
   - Produces `betting/data/decision_matrix_{date}.md` (compact bettable opportunities sorted by safety score)
6. **Build ranked shortlist**: `python3 scripts/build_shortlist.py --date YYYY-MM-DD --stats-first`
   - Reads market matrix and scores all events by data quality, competition importance, odds, tipster coverage
   - Enforces sport diversity (≥8 sports, per-sport caps)
   - Produces `betting/data/{date}_s2_shortlist.md` + `.json` (ALL candidates ranked — no hardcoded cap)
   - Use `--top N` only if you want to explicitly limit (default: process all)
   - This is the PRIMARY input for S2 → S3 deep analysis
6. **Fetch weather for outdoor venues**: `python3 scripts/fetch_weather.py --date YYYY-MM-DD`
   - Open-Meteo API (free, unlimited, no API key) → produces `betting/data/weather_{date}.json`
   - Flags: RAIN_HEAVY, WIND_STRONG, EXTREME_HEAT, FREEZING for football/baseball/speedway/MMA/padel
7. Config loaded: bankroll, daily cap, sports list, betting_window_days
8. Previous day's learning-log and error patterns reviewed
9. If `betting_window_days` > 1 → extend scan window to cover N days
10. If `rerun=true` → execute §RERUN versioning protocol (see above)
11. Check 48h repeat losses: `python3 scripts/check_48h_repeats.py` → flag for S7 gate
12. **Review analysis pool + market matrix**: Read `betting/data/analysis_pool_{date}.md` and `betting/data/market_matrix_{date}.md` — events with `data_tier: FULL` have API-sourced stats + multi-source odds. Pass to bet-scanner (S1/S2) and bet-statistician (S3) as pre-computed starting data.

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

## AGENT DELEGATION RULE (MANDATORY — NEVER BYPASS)

**For steps S2, S2.5, S3, S4, S5, S6, S7, S8 — ALWAYS delegate to the specialist agent** (bet-scout, bet-enricher, bet-statistician, bet-valuator, bet-challenger, bet-builder). Scripts generate raw data; agents analyze and decide.

**THE ORCHESTRATOR MUST SPAWN DEDICATED AGENTS. SCRIPTS ARE DATA TOOLS, NOT THE ANALYSIS.**

| Step | Script (DATA TOOL — runs first) | Agent (THINKER — runs second, MANDATORY) | What Agent MUST Deliver (NOT optional) |
|------|-------------------------------|----------------------------------------|---------------------------------------|
| S2 | tipster consensus from `tipster_xref` | **bet-scout** via `runSubagent` (use `bet-tipsters.prompt.md`) | Per-candidate: FULL tipster argument extraction, argument quality assessment, independence verification, angle discovery, watchlist promotions |
| S2.5 | `data_enrichment_agent.py` → enriched stats | **bet-enricher** via `runSubagent` (use `bet-enrich.prompt.md`) | Enrichment yield, gap analysis, source reliability, persistent failure flags |
| S3 | `deep_stats_report.py` → raw safety scores, market rankings, probabilities | **bet-statistician** via `runSubagent` (use `bet-deep-stats.prompt.md`) | Per-candidate: edge mechanism ("WHY does this trend exist?"), pattern insights, anomaly flags, cross-source verification, ANALYTICAL REASONING section |
| S4 | `_run_odds_eval()` → EV injection from odds API | **bet-valuator** via `runSubagent` (use `bet-odds-ev.prompt.md`) | Per-candidate: multi-source cross-validation, mispricing reasoning, edge durability assessment, relative value vs alternative markets |
| S5 | `_run_context_checks()` → context flags | **bet-challenger** via `runSubagent` (use `bet-context-upset.prompt.md`) | Per-candidate: REAL impact assessment (not just listing flags), motivation modeling, context-stat interactions |
| S6 | `_run_upset_risk()` → upset scores | **bet-challenger** via `runSubagent` (use `bet-context-upset.prompt.md`) | Per-candidate: upset risk with sport-specific reasoning, compounding factor analysis, Paradox Rule |
| S7 | `gate_checker.py` → 18-point mechanical gate | **bet-challenger** via `runSubagent` (use `bet-gate.prompt.md`) | Per-candidate: qualitative bear cases with SPECIFIC scenarios, assumption audits, historical analogies, second-order effects, Bayesian confidence update |
| S8 | `coupon_builder.py` → portfolio math, Kelly staking | **bet-builder** via `runSubagent` (use `bet-portfolio.prompt.md`) | Strategic portfolio review, hidden correlation detection, stake adjustments by conviction, Polish descriptions with reasoning, V1-V10 + §S8.FINAL, placement strategy |

> **Note:** Step IDs in `pipeline_orchestrator.py` match the delegation table above: s2_tipster, s2_5_enrich, s3_deep_stats, s4_odds_eval, s5_context, s6_upset_risk, s7_gate, s8_coupons.

### AGENT DELEGATION CHECKPOINTS (BLOCKING — the pipeline STOPS here until agent completes)

After `pipeline_orchestrator.py` finishes (or after each script step), the orchestrator MUST:

```
CHECKPOINT 1: After s2_tipster completes
  → Spawn bet-scout agent with:
    - Input: {date}_tipster_consensus.json, pre-fetched HTML from betting/data/zawodtyper.pl/ etc.
    - Task: "Read FULL tipster arguments. Assess quality. Check independence. Discover angles.
             Promote statistical-market tips to watchlist."
    - Gate: Each candidate has argument quality + independence + contrarian signal

CHECKPOINT 2: After s2_5_enrich completes
  → Spawn bet-enricher agent with:
    - Input: enrichment results, {date}_s2_shortlist.json, source_health table
    - Task: "Review enrichment yield. Identify persistent gaps. Assess data quality.
             Flag sports/leagues with no data for S3."
    - Gate: Enrichment yield ≥60%, gap analysis complete

CHECKPOINT 3: After s3_deep_stats completes
  → Spawn bet-statistician agent with:
    - Input: {date}_s3_deep_stats.json, {date}_s2_shortlist.json, analysis_pool_{date}.json
    - Task: "Analyze ALL candidates. For each: interpret safety scores, find edge mechanisms,
             fetch missing stats from ESPN/Flashscore, write ANALYTICAL REASONING section.
             Do NOT just summarize the script output — ADD VALUE."
    - Gate: Each candidate has analytical reasoning (edge + pattern + anomaly + narrative)
  → WAIT for agent response before proceeding

CHECKPOINT 4: After s4_odds_eval completes
  → Spawn bet-valuator agent with:
    - Input: odds_api_snapshot.json, S3 agent output, bet-scout agent output
    - Task: "Cross-validate pricing. Reason about mispricing. Calculate relative value.
             Assess edge durability. Flag drift >8%."
    - Gate: Each candidate has line reasoning + mispricing vector + edge durability

CHECKPOINT 5: After s5_context + s6_upset_risk complete
  → Spawn bet-challenger agent with:
    - Input: weather_{date}.json, ALL prior agent outputs (statistician + scout + valuator)
    - Task: "Assess REAL market impact of each context flag. Model motivation effects.
             Score upset risk with sport-specific reasoning. Identify compounding factors."
    - Gate: Each candidate has motivation analysis + context-stat interaction

CHECKPOINT 6: After s7_gate completes
  → Spawn bet-challenger agent with:
    - Input: {date}_s7_gate_results.json, ALL prior agent outputs
    - Task: "Build specific bear cases with named scenarios. Audit assumptions.
             Find historical analogies. Model second-order effects. Bayesian-update confidence."
    - Gate: Each approved candidate has scenario model + assumption audit + historical analogy

CHECKPOINT 7: After s8_coupons completes
  → Spawn bet-builder agent with:
    - Input: {date}.json (coupons), ALL prior agent outputs, config
    - Task: "Review portfolio strategically. Check hidden correlations. Adjust stakes.
             Write Polish descriptions. Run V1-V10 + §S8.FINAL. Produce placement guide."
    - Gate: Complete portfolio with reasoning, arithmetic verified, §S8.FINAL all pass
```

**VIOLATION OF THESE CHECKPOINTS = PIPELINE FAILURE.** The orchestrator MUST NOT present any output to the user that hasn't passed through the appropriate specialist agent.

**The flow for each step:**
1. Run the script to produce raw data
2. Delegate to the specialist agent via `runSubagent` with the script output as context
3. The agent READS the data, THINKS about it, CROSS-REFERENCES with other sources, and produces REASONED output
4. The orchestrator validates the agent's output against structural requirements before proceeding

**NEVER treat script output as final analysis.** Scripts are calculators — agents are analysts.

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
| S0 | `bet-settle` | bet-settler | picks-ledger, coupons-ledger, Flashscore, **DB coupons/bets tables** | `{date}_s0_settlement.md` | All pending resolved, bankroll updated, **DB synced via `_sync_settlement_to_db()`** |
| S1 | `bet-scan` | bet-scanner | BetExplorer, Flashscore, scan_summary, **analysis_pool_{date}.json**, **market_matrix_{date}.json** | `{date}_s1_master_events.md` + `{date}_s1_tipster_prefetch.md` | ≥50 events, ALL 14 sports scanned (≥6 with events), completeness ≥80%, **tipster HTML fetched** |
| S1a | _(auto)_ | _(script)_ | API-Football/Basketball/Hockey/Tennis/Volleyball/Handball/Baseball, TheSportsDB | `analysis_pool_{date}.json` | API fixture discovery + L10 form + H2H stats enrichment (timeout: 5 min) |
| S1b | _(auto)_ | _(script)_ | **PARALLEL**: `fetch_odds_api.py` + `fetch_weather.py` + `tipster_aggregator.py` | `odds_api_snapshot.json`, `weather_{date}.json`, `{date}_tipster_consensus.json` | Odds + weather + tipster consensus (timeout: 10 min). **Odds persisted to DB `odds_history` table** via `OddsRepo.upsert()` |
| S1c | _(auto)_ | _(script)_ | `aggregate_and_select.py` + `deep_analysis_pool.py` | `analysis_pool_{date}.json/md` | Aggregate scan results + pre-computed safety scores + market rankings (timeout: 2 min) |
| S1d | _(auto)_ | _(script)_ | `generate_market_matrix.py --date {date} --stats-first` | `market_matrix_{date}.json/md`, `decision_matrix_{date}.md` | Full event universe with all odds + safety data (timeout: 2 min) |
| S1e | _(auto)_ | _(script)_ | `build_shortlist.py --date {date} --stats-first` | `{date}_s2_shortlist.md/json` | All candidates ranked, ≥8 sports (timeout: 2 min) |
| S2 | _(auto)_ | _(script)_ | tipster consensus + shortlist | tipster cross-reference data | Cross-reference picks with tipster consensus (timeout: 1 min) |
| S2.5 | `bet-enrich` | bet-enricher | shortlist, stats cache, DB `team_form` | `{date}_s2_5_enrichment.md` | **Self-healing enrichment from Flashscore/Sofascore/ESPN. Yield ≥60%. (timeout: 15 min)** |
| S3 | **AUTOMATED** (`deep_stats_report.py`, 8-worker parallel) + `bet-deep-stats` supplement | bet-statistician | S2 shortlist, **analysis_pool** (pre-computed safety), stats cache, **DB `team_form` table (tried first)** | `{date}_s3_deep_stats.md/json` | **DB-first stats lookup → JSON cache fallback. Script runs §3.0 market ranking + Poisson/NegBin probability. Sport-specific H2H penalties (0.70-0.90). Agent supplements for candidates without API data. ANALYTICAL GATE: ANALYTICAL REASONING section per candidate. (timeout: 10 min)** |
| S4 | _(auto)_ | _(script)_ | S3 output + odds snapshots + analysis_pool EV | `{date}_s4_odds_eval.json` | **Cross-validate odds, compute EV, detect drift >8%. (timeout: 2 min)** |
| S5 | _(auto)_ | _(script)_ | S3 output + weather + venue data | `{date}_s5_context.json` | **Weather impact, venue, referee, roster changes. (timeout: 1 min)** |
| S6 | _(auto)_ | _(script)_ | S3 output + upset risk checklists | `{date}_s6_upset_risk.json` | **Score upset risk per candidate using sport-specific checklists. (timeout: 2 min)** |
| S7 | **AUTOMATED** (`gate_checker.py`) + `bet-gate` supplement | bet-challenger | S4+S5+S6 output | `{date}_s7_gate.md/json` | **Script runs 18-point advisory gate with tiers (STRONG/MODERATE/WEAK/FLAGGED), stats-first EV pass (no odds → advisory, not rejection), red flags, risk tiers. Agent builds qualitative bear cases for borderline picks. ANALYTICAL GATE: DEEP ADVERSARIAL REASONING per candidate. (timeout: 5 min)** |
| S3B | `bet-time-sensitive` | bet-statistician | S7 output + `weather_{date}.json` | `{date}_s3b_time_sensitive.md` | Lineups, weather (from `fetch_weather.py`), odds drift formula per pick |
| S8 | **AUTOMATED** (`coupon_builder.py`) + `bet-portfolio` review | bet-builder | S7+S3B output | Coupon file + ledgers + **DB coupons/bets tables** | **Script builds core portfolio + combo menu + extended pool with Kelly 1/4 stakes + rich per-leg Polish analysis. Coupons persisted to DB with `fixture_id` resolved via `FixtureRepo.get_by_teams_and_date()`. Agent reviews and runs V1-V10 + §S8.FINAL. (timeout: 2 min)** |

**PARALLEL EXECUTION:** S4 (odds eval), S5 (context), and S6 (upset risk) all receive S3 output as input. None depends on the others. They run in parallel within the pipeline orchestrator. S7 waits for ALL three to complete before running the 18-point gate.

**PER-STEP TIMEOUTS:** Each step has its own timeout (shown above). A single slow source in S1 (30 min max) won't block S3 (10 min max). If any step times out, the pipeline logs the failure and continues with available data rather than aborting after 40 minutes.

---

## STRUCTURAL OUTPUT VERIFICATION (MANDATORY — NEVER SKIP)

**After EACH step completes, the orchestrator validates output quality. Script-based validation replaces manual counting.**

### After S3 — AUTOMATED VALIDATION of `{date}_s3_deep_stats.md`:

**Run the validation script — this replaces manual section counting:**

```bash
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json
```

The script checks ALL 7 structural requirements per candidate:
1. Section markers §S3.1-§S3.10 (all 10 present)
2. Ranking table row count (≥3, ≥4 for football)
3. Banned word scan (all tables)
4. Safety score numeric validation (0.00-1.00)
5. Three-way check numeric validation
6. Source table row count (≥2)
7. Injury source presence

**GATE:** ALL candidates must have status `PASS`. If ANY candidate has `FAIL`:
- Read the JSON errors array for specific violations
- Return ONLY failing candidates to bet-statistician with exact error list
- Do NOT proceed to S4 with any FAIL candidates

### After S2 — Read `{date}_tipster_consensus.json` and verify:
```
1. [ ] TIPSTER COVERAGE SUMMARY TABLE present (§S4-COVERAGE format — see below).
2. [ ] For each candidate: ≥2 site names listed, ≥1 tipster argument text extracted.
3. [ ] CONSENSUS % calculated per candidate.
4. [ ] OPPOSING ARGUMENTS recorded (or explicit "none found").
5. [ ] §4.3 WATCHLIST PROMOTION section present.
6. [ ] §1.5 pre-fetched HTML referenced (not fresh web-fetch only).

METRIC: candidates_with_2+_tipster_args / total_candidates × 100 = TIPSTER_%
GATE: TIPSTER_% ≥ 80%. If <80% → list candidates with <2 args → return to bet-scout with fallback chain instructions.
```

#### §S2-COVERAGE — Required Summary Table
The S2 tipster output file must contain the Tipster Coverage Summary table as defined in the `bet-tipsters` internal-prompt. The orchestrator verifies:
- Table exists at the top of the file (before per-candidate sections)
- A TOTAL row is present with aggregate metrics (avg sites/candidate, avg with args, % full)
- Status column uses: ✅ OK (≥2 sites with args) / ⚠️ 1-source / ❌ TIPSTER-BLIND (0 args) / 🔄 RETRY
- Candidate count in TOTAL row matches total candidates from S3

### After S7 — Read `{date}_s7_gate.md` and verify:
```
For EACH approved pick (✅):
1. [ ] 18-POINT GATE TABLE — all 18 rows present with PASS/FAIL per row (NOT abbreviated to "15-18: PASS").
2. [ ] BEAR CASE references specific data, stats, or a named scenario (NOT "it could go wrong").
3. [ ] RED FLAG TABLE — sport-specific flags listed and resolved.
4. [ ] CONTRARIAN — all 4 questions answered with substance.
5. [ ] ZERO TOLERANCE — explicitly scanned against all 14 patterns.

GATE: 100% of approved picks must have all 5 structural elements. ANY missing → return to bet-challenger.
```

---

## PASS PROTOCOL

### ADAPTIVE PASS PROTOCOL

After Pass 1, run automated validation:
```bash
python3 scripts/validate_s3_output.py betting/data/{date}_s3_deep_stats.md --format json
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json
```

**Decision tree:**
- **ZERO critical errors** (all candidates PASS, all coupons PASS, V10e complete) → **SKIP to Pass 4** (Final)
- **ONLY non-critical errors** (warnings, minor formatting) → **Pass 2 (Targeted Fixes) → Pass 4**
- **Critical errors** (FAIL candidates, arithmetic errors, missing sections) → **Pass 2 → Pass 3 → Pass 4**

This eliminates 2 unnecessary passes when the pipeline produces clean output on the first run.

### PASS 1 — DISCOVERY (find all errors)

Execute S0 → S1 → S1a → S1b(parallel) → S1c → S1d → S1e → S2 → S2.5 → S3 → S4+S5+S6(parallel) → S7 → S8 → S9 → S10 fully. At each step:
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
- S2: Missing tipster sites, no arguments extracted → check specific URLs, use fallbacks. **If §1.5 pre-fetch was skipped → RUN IT NOW (Playwright fetch all 5 tipster sites) before re-doing S2.** Verify §4.3 watchlist promotion was done.
- S4: Missing odds source, no EV calculated → try alternative source
- S5: Missing injury check, context flags incomplete → verify on ESPN/Flashscore
- S6: Upset risk not scored → run sport-specific checklists
- S7: Incomplete 18-point gate, Zero Tolerance pattern matched → fix or reject pick
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
   - Every candidate got full S3-S7 (H2H, tipsters, injuries, bear case, 18-point gate)
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

This step catches bugs that V1-V10 misses. Run automated validation first, then manual checks.

### AUTOMATED VALIDATION (run first)
```bash
python3 scripts/validate_coupons.py betting/coupons/{date}*.md --format json
```
This script checks coupon arithmetic (±2% tolerance), unique events in core portfolio, and Polish descriptions. Fix any FAIL results before proceeding to manual checks below.

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

### I. STATISTICAL MATRIX COMPLETENESS (NO AUTO-REJECTION ENFORCEMENT)
This check enforces the CORE RULE: Pipeline NEVER auto-rejects events. ALL analyzed events MUST appear in the coupon file. User decides what to bet.
1. Count events with deep analysis in S3 output → N_analyzed
2. Subtract phantoms + already_played + out_of_window → N_valid
3. Count unique events in coupon's STATISTICAL MATRIX → N_matrix
4. **GATE: N_matrix ≥ N_valid.** Missing events = BLOCKER.
5. Count total market rows in matrix (across all events) → R_markets
6. **GATE: R_markets ≥ 3 × N_football + 2 × N_other** (football events must show ≥3 stat markets, others ≥2).
7. Verify EVERY market row shows: P(hit), Min odds (= 1/P), Safety score, L10 hit rate, H2H hit rate, 3-way alignment
8. Verify NO auto-rejection message appears ("rejected due to", "excluded based on", "filtered to", "only X picks survived")
9. **FORBIDDEN patterns:** Any language implying the pipeline pre-selected picks for the user. The matrix shows EVERYTHING. User picks.
10. Non-analyzed shortlist events must appear in a separate section with available markets noted (user may request deep analysis for any of them)

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

### 4. FULL STATISTICAL MATRIX (PRIMARY OUTPUT — MANDATORY)
The coupon file's main section. Show ALL S3-analyzed candidates with ALL evaluated statistical markets.
Format: One row per market per event, organized by sport.
Columns: Event | Market | Direction | Combined avg | Line | L10 hit% | H2H hit% | Safety | P(hit) | Min kurs (1/P) | 3-Way | Data Quality
**The user selects from this matrix. The pipeline does NOT pre-select, pre-filter, or pre-reject.**
Also include: per-event backing data (L10 form, H2H summary, injuries, referee), non-analyzed shortlist summary, excluded/phantom list.

### 5. Final Coupons (SHOW ALL)
For each coupon: legs, combined odds (arithmetic shown), stake, type

### 5b. Extended Pool (ROZSZERZONY WYBÓR)
EV > 0 picks that didn't fully pass the 18-point gate. For each: event, market, odds, EV, gate score, bull case, bear case, missing data, when to bet, suggested combos with approved picks. See §EXTENDED-POOL in betting-artifacts.instructions.md.

### 6. Watchlist
Picks awaiting a trigger (e.g., lineup confirm) without calculated EV. For EV > 0 picks, use Extended Pool (§5b) instead.

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
- **§S8.FINAL Mechanical Verification FAIL**: BLOCKER. Fix artifacts in place, re-run failed check. Do NOT present to user until all 9 checks (A-I) pass.
- **S3B gate FAIL**: Time-sensitive data missing → flag affected picks as CONDITIONAL with extra notes.
- **V1-V10 FAIL in Pass 4**: BLOCKER. Loop back to fix, re-validate.
- **<4 approved picks after all passes**: Declare NO BET day (do not produce coupons with <4 picks).
- **<5 sports in final picks**: Go back to S1, scan missing sports deeper.

---

## ADVISORY TIER SYSTEM

The S7 gate assigns advisory tiers based on gate score (not binary approved/rejected):
- **STRONG** (≤2 checks failed): High confidence — full stake
- **MODERATE** (3-5 failed): Good but gaps — standard stake
- **WEAK** (6-9 failed): Marginal — reduced stake or watchlist
- **FLAGGED** (10+ failed): Significant concerns — user must review carefully

Tiers are ADVISORY ONLY — user decides. ALL candidates shown in matrix regardless of tier.

---

## FILE NAMING CONVENTION

Working files (Passes 1-3):
```
betting/data/{date}_s0_settlement.md
betting/data/{date}_s1_master_events.md
betting/data/{date}_s2_shortlist.md
betting/data/{date}_s2_tipsters.md
betting/data/{date}_s2_5_enrichment.md
betting/data/{date}_s3_deep_stats.md
betting/data/{date}_s4_odds_eval.md
betting/data/{date}_s5_context.md
betting/data/{date}_s6_upset_risk.md
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
