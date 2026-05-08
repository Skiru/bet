# Pipeline Audit — Full Codebase Deep Research

**Date:** 2026-05-08  
**Scope:** Every script, agent, database table, adapter, scanner, and data flow in the betting pipeline  
**Method:** Line-by-line code reading of 60+ files across `scripts/`, `src/bet/`, `.github/agents/`, `tests/`

---

## 1. Pipeline Flow Map

### 1.1 Orchestrator: `scripts/pipeline_orchestrator.py` (~2,500 lines)

The main orchestrator defines 15 pipeline steps executed sequentially:

| Step ID | Name | Type | Timeout | Critical | Agent Required |
|---------|------|------|---------|----------|----------------|
| `s0_settle` | S0: Settle + Learn | SHELL (2 commands) | 180s | YES | — |
| `s1_scan` | S1: Playwright Scan | PYTHON (`scan_events`) | 1200s | YES | `bet-scanner` |
| `s1_ingest` | S1-ingest: Ingest Scan Stats | SHELL | 180s | NO | — |
| `s1a_discover` | S1a: Discover Fixtures + API Stats + Tennis | SHELL (3 commands) | 600s | NO | — |
| `s1b_parallel` | S1b: Odds + Weather + Tipsters | PYTHON (`parallel_enrichment`) | 600s | NO | — |
| `s1c_aggregate` | S1c: Aggregate + Deep Analysis Pool | SHELL (2 commands) | 300s | NO | — |
| `s1d_matrix` | S1d: Market Matrix | SHELL | 120s | NO | — |
| `s1e_shortlist` | S1e: Build Ranked Shortlist | SHELL | 120s | NO | `bet-scanner` |
| `s2_tipster` | S2: Tipster Cross-Reference | PYTHON (`tipster_xref`) | 60s | NO | `bet-scout` |
| `s3_deep_stats` | S3: Deep Statistical Analysis | PYTHON (`deep_stats`) | 600s | implicit | `bet-statistician` |
| `s4_odds_eval` | S4: Odds Evaluation | PYTHON (`odds_eval`) | 120s | NO | `bet-valuator` |
| `s5_context` | S5: Contextual Checks | PYTHON (`context_checks`) | 60s | NO | `bet-challenger` |
| `s6_upset_risk` | S6: Upset Risk Scoring | PYTHON (`upset_risk`) | 120s | NO | `bet-challenger` |
| `s7_gate` | S7: 17-Point Gate Check | PYTHON (`gate_check`) | 300s | implicit | `bet-challenger` |
| `s8_coupons` | S8: Build Coupons | PYTHON (`build_coupons`) | 120s | implicit | `bet-builder` |
| `s9_validate` | S9: Validate Coupons | PYTHON (`validate`) | 60s | NO | — |
| `s10_summary` | S10: Final Summary | PYTHON (`summary`) | 30s | NO | — |

**Step execution strategy:**
- Steps with `"commands"` run shell subprocesses via `run_command()`
- Steps with `"python_step"` dispatch to `run_python_step()` which calls internal functions
- Mixed: some steps have both (only commands are used if present)

**Phases:**
- `data`: S0 through S2 (scan, discover, enrich, shortlist)
- `analysis`: S3 through S7 (stats, odds, context, upset risk, gate)
- `build`: S8 through S10 (coupons, validation, summary)

### 1.2 State Management

- **Dual-write**: DB (`pipeline_runs` table via `PipelineRepo`) + JSON file (`betting/data/pipeline_state/pipeline_{date}.json`)
- **Resume**: Loads state from DB first, JSON fallback. Skips steps with `status=completed`
- **Atomic writes**: JSON state uses `tempfile.mkstemp()` + `os.replace()` for crash safety

### 1.3 Actual Code Paths

```
S0: subprocess → settle_on_finish.py, analyze_betclic_learning.py
S1: _run_parallel_scan() → ThreadPoolExecutor → 11 sport scanners → merge_results
    Fallback: subprocess → scan_events.py (legacy monolithic scan)
S1-ingest: subprocess → ingest_scan_stats.py
S1a: subprocess → discover_fixtures.py, fetch_api_stats.py, enrich_tennis_stats.py
S1b: ThreadPoolExecutor → 5 parallel tasks (odds, odds-io, weather, tipsters, ESPN)
S1c: subprocess → aggregate_and_select.py, deep_analysis_pool.py
S1d: subprocess → generate_market_matrix.py
S1e: subprocess → build_shortlist.py
S2: _run_tipster_xref() (inline in orchestrator)
S3: generate_deep_stats() (imported from deep_stats_report.py)
S4: _run_odds_eval() → _inject_ev_from_odds() (inline, 250+ lines of odds merging)
S5: _run_context_checks() (inline, reads weather + ESPN injuries)
S6: _run_upset_risk() (inline, sport-specific heuristics)
S7: run_gate() (imported from gate_checker.py)
S8: build_coupons() (imported from coupon_builder.py)
S9: validate_file() (imported from validate_coupons.py)
S10: _run_s10() (inline, summary formatting)
```

---

## 2. Script Inventory

### 2.1 Core Pipeline Scripts (ACTIVE — called by orchestrator)

| Script | Purpose | Called By | Inputs | Outputs |
|--------|---------|-----------|--------|---------|
| `pipeline_orchestrator.py` | Main orchestrator | CLI | config, date | state JSON, all artifacts |
| `settle_on_finish.py` | Settlement engine | S0 shell | ledger, DB | updated ledger, bankroll |
| `analyze_betclic_learning.py` | Betclic history analysis | S0 shell | `betclic_bets_history.json` | `betclic_learning_summary.json` |
| `scan_events.py` | Legacy monolithic scanner | S1 fallback | `scan_urls.json` | `scan_summary.json` |
| `ingest_scan_stats.py` | Ingest scan data to cache | S1-ingest | `scan_summary.json` | stats_cache updates |
| `discover_fixtures.py` | API fixture discovery | S1a | API clients | fixtures JSON + DB |
| `fetch_api_stats.py` | Multi-API stats fetch | S1a | fixtures | stats_cache + DB |
| `enrich_tennis_stats.py` | Tennis-specific enrichment | S1a | tennis fixtures | tennis stats cache |
| `fetch_odds_api.py` | The-Odds-API fetch | S1b | API key | `odds_api_snapshot.json` |
| `fetch_odds_api_io.py` | Odds-API.io fetch | S1b | API key | `odds_api_io_snapshot.json` |
| `fetch_weather.py` | Weather data | S1b | locations | `weather_{date}.json` |
| `tipster_aggregator.py` | Tipster site scraping | S1b | tipster URLs | `tipster_aggregation_{date}.json` |
| `aggregate_and_select.py` | Aggregate scan results | S1c | `scan_summary.json` | `picks_suggested.json` |
| `deep_analysis_pool.py` | Build analysis candidate pool | S1c | fixtures + stats | `analysis_pool_{date}.json` |
| `generate_market_matrix.py` | Market matrix generation | S1d | all data sources | `market_matrix_{date}.json/.md` |
| `build_shortlist.py` | Ranked shortlist builder | S1e | market matrix | `{date}_s2_shortlist.json` |
| `deep_stats_report.py` | S3 deep statistical analysis | S3 python | shortlist + cache | `{date}_s3_deep_stats.json/.md` |
| `gate_checker.py` | 17-point gate check | S7 python | S3 analyses | `{date}_s7_gate_results.json/.md` |
| `coupon_builder.py` | Coupon construction | S8 python | gate results | `{date}.json/.md` in coupons/ |
| `validate_coupons.py` | Coupon validator | S9 python | coupon markdown | validation report |
| `validate_s3_output.py` | S3 structural validator | S3 post-check | S3 markdown | validation report |
| `compute_safety_scores.py` | Safety score calculator | S3 (imported) | stats data | ranked markets |
| `normalize_stats.py` | Stats normalization framework | S3 (imported) | raw API data | normalized stats |
| `probability_engine.py` | Poisson probability engine | S3 enrichment | stats data | probabilities |

### 2.2 Support Scripts (ACTIVE — utility/setup)

| Script | Purpose | Usage |
|--------|---------|-------|
| `init_database.py` | DB initialization | Setup |
| `migrate_data.py` | JSON/CSV → SQLite migration | One-time |
| `db_data_loader.py` | DB↔JSON bridge | Imported by many scripts |
| `build_stats_cache.py` | Stats cache CRUD | Imported by ingest, fetch_api_stats |
| `check_48h_repeats.py` | 48h repeat loss checker | Imported by gate_checker |
| `source_health.py` | Source availability tracker | Called after scan |
| `scan_health_report.py` | Post-scan health dashboard | Called by scanner agent |
| `query_team.py` | DB team query CLI | Ad-hoc |
| `build_league_profiles.py` | League statistical profiles | Setup/periodic |
| `utils.py` | Shared utilities | Imported everywhere |
| `fetch_with_playwright.py` | Playwright browser fetch | Imported by scanners/adapters |

### 2.3 Likely DEAD CODE — Scripts Never Called by Pipeline

| Script | Evidence | Notes |
|--------|----------|-------|
| `build_s1s2_shortlist.py` | **HARDCODED DATE** (`DATE = '2026-05-07'`), hardcoded absolute paths | One-time throwaway script for May 7. Not called by orchestrator. |
| `espn_deep_analysis.py` | Hardcoded `BASE` URL, no CLI integration, no date param | One-time deep ESPN analysis, not integrated |
| `seed_deep_stats.py` | Imports niche clients (SofascoreDarts, SnookerOrg, OpenDota, ITTF) | One-time seeder, not in pipeline |
| `seed_espn_data.py` | One-time ESPN data seeder | Setup script, not in pipeline |
| `betclic_login.py` | Playwright Betclic login helper | Used only by `fetch_betclic_bets.py` |
| `fetch_betclic_bets.py` | Playwright Betclic scraper | Manual run only |
| `parse_betclic_bets.py` | HTML → JSON parser for Betclic bets | Manual run only |
| `verify_betclic_odds.py` | Playwright Betclic odds checker | Manual run only |
| `smoke_playwright.py` | Playwright smoke test | Manual testing |
| `historical_learning.py` | CSV-based historical learning | Superseded by `analyze_betclic_learning.py` |
| `run_full_scan_and_prepare.sh` | Legacy bash orchestrator | Superseded by `pipeline_orchestrator.py` |
| `run_session.sh` | Legacy session runner | Superseded by `pipeline_orchestrator.py` |
| `evaluate_decisions.py` | Post-settlement decision evaluation | Not called by pipeline (should be in S0) |
| `fetch_espn_odds.py` | ESPN odds fetcher | Partially superseded by ESPN adapter in S1b |
| `fetch_espn_standings.py` | ESPN standings fetcher | Not called by pipeline |
| `fetch_odds_multi.py` | Multi-source odds aggregator | Not called by pipeline (superseded by S1b parallel) |

### 2.4 Scanner Scripts (ACTIVE)

| Scanner | Sports Covered | Base Class |
|---------|---------------|------------|
| `football_scanner.py` | football | `BaseSportScanner` |
| `tennis_scanner.py` | tennis | `BaseSportScanner` |
| `basketball_scanner.py` | basketball | `BaseSportScanner` |
| `volleyball_scanner.py` | volleyball | `BaseSportScanner` |
| `hockey_scanner.py` | hockey | `BaseSportScanner` |
| `esports_scanner.py` | esports | `BaseSportScanner` |
| `handball_scanner.py` | handball | `BaseSportScanner` |
| `combat_scanner.py` | mma | `BaseSportScanner` |
| `racket_scanner.py` | table_tennis, padel | `BaseSportScanner` |
| `niche_scanner.py` | snooker, darts, speedway | `BaseSportScanner` |
| `baseball_scanner.py` | baseball | `BaseSportScanner` |
| `base_scanner.py` | — (ABC) | — |
| `config_loader.py` | URL config loader | Utility |
| `domain_semaphore.py` | Domain rate limiting | Utility |
| `merge_results.py` | Per-sport → unified merge | Utility |

### 2.5 Adapter Scripts (ACTIVE)

18 adapters in `scripts/adapters/`:
`basketball_reference`, `betclic`, `betexplorer`, `covers`, `flashscore`, `forebet`, `hltv`, `hockey_reference`, `oddsportal`, `raw` (generic), `scores24`, `soccerstats`, `soccerway`, `sofascore`, `tennisabstract`, `tennisexplorer`, `totalcorner`, `whoscored`

### 2.6 API Client Scripts

23 clients in `scripts/api_clients/`:
Sport-specific: `api_football`, `api_basketball`, `api_hockey`, `api_tennis`, `api_volleyball`, `api_handball`, `api_baseball`, `api_football_odds`
Service-specific: `espn_adapter` (multi-league), `football_data_org`, `understat_client`, `balldontlie`, `nba_api_client`, `thesportsdb`, `sofascore_darts`, `snooker_org`, `opendota`, `ittf_client`, `serpapi_client`, `odds_api_io`
Infrastructure: `base_client`, `rate_limiter`

### 2.7 Odds Sources

6 sources in `scripts/odds_sources/`:
`the_odds_api`, `odds_api_io_source`, `api_football_odds`, `betexplorer_scraper`, `oddsportal_scraper`, `betclic_scraper`

---

## 3. Database Analysis

### 3.1 Schema (v5) — 20 tables

| Table | Purpose | Row Scale | Used By |
|-------|---------|-----------|---------|
| `sports` | 14 sports with stat_keys | 14 | Everywhere |
| `competitions` | Leagues/tournaments | ~1000s | fixture discovery |
| `teams` | Team/player entities with aliases | ~10,000s | fixture matching |
| `fixtures` | Match records | ~10,000s/day | Core entity |
| `match_stats` | Per-fixture per-team stat values | ~100,000s | S3 analysis |
| `team_form` | Denormalized L10/L5/H2H cache | ~50,000s | S3 analysis |
| `odds_history` | Multi-bookmaker odds | ~97,000+ | S4 odds eval |
| `coupons` | Coupon records | ~100s | S8, settlement |
| `bets` | Individual bet legs | ~300s | S8, settlement |
| `pipeline_runs` | Pipeline step tracking | ~15/day | State management |
| `source_health` | Source availability tracking | ~50 | Scan monitoring |
| `analysis_results` | S3 output (markets, safety scores) | ~1000s/day | S7 gate |
| `gate_results` | S7 gate output (approved/rejected) | ~100s/day | S8 coupons |
| `league_profiles` | League-level stat profiles | ~1000s | Probability engine |
| `analysis_raw_data` | Raw stats snapshots for learning | ~1000s/day | Decision learning |
| `decision_snapshots` | Per-bet decision context | ~100s | Decision learning |
| `decision_outcomes` | Post-settlement comparisons | ~100s | Decision learning |
| `scan_results` | Per-event scanner output | ~10,000s/day | Scanner system |
| `scan_run_stats` | Per-sport scan metadata | ~11/day | Health monitoring |
| `schema_meta` | Schema version tracking | 1 | Migrations |

**ESPN tables (v5 migration — `005_espn_deep_tables.sql`):**
Additional tables exist for ESPN deep data: `standings`, `team_rosters`, `athletes`, `player_gamelogs`, `player_splits`, `team_ats_records`, `team_ou_records`, `espn_predictions`, `power_index`, `transactions`. These are populated by `seed_espn_data.py`.

### 3.2 Schema Observations

1. **Well-designed core**: fixtures/teams/sports/competitions are properly normalized with FKs
2. **Dual-storage pattern**: Every pipeline step writes to both DB + JSON files. This adds complexity but provides resilience
3. **Missing migration 004**: Migrations jump from 003 to 005 — no `004_*.sql` exists
4. **`team_form` NULL handling**: Uses expression-based unique index `COALESCE(h2h_opponent_id, 0)` with DELETE+INSERT upsert — correct but complex
5. **`scan_results.raw_data`**: Stored as TEXT (JSON string), not using SQLite JSON functions
6. **No TTL/cleanup**: No mechanism to clean old fixtures, stats, or scan results — DB grows indefinitely

### 3.3 Repository Layer

Comprehensive repo classes in `src/bet/db/repositories.py`:
`SportRepo`, `TeamRepo`, `CompetitionRepo`, `FixtureRepo`, `StatsRepo`, `OddsRepo`, `CouponRepo`, `PipelineRepo`, `SourceHealthRepo`, `LeagueProfileRepo`, `AnalysisResultRepo`, `GateResultRepo`, `ScanResultRepo`, `AnalysisRawDataRepo`, `DecisionSnapshotRepo`, `DecisionOutcomeRepo`, `StandingRepo`, `TeamRosterRepo`, `AthleteRepo`, `PlayerGamelogRepo`, `PlayerSplitRepo`, `TeamATSRepo`, `TeamOURepo`, `ESPNPredictionRepo`, `PowerIndexRepo`, `TransactionRepo`

**All use parameterized queries** — no SQL injection risk.

---

## 4. Agent Inventory

### 4.1 All 19 Agents

| Agent | Model | User-Invokable | Pipeline Role | Orchestrator References |
|-------|-------|----------------|---------------|------------------------|
| `bet-orchestrator` | Claude Opus 4.6 | YES (entry point) | Pipeline coordinator | Delegates to all others |
| `bet-scanner` | Claude Opus 4.6 | YES | S1/S1e: Scan verification | `s1_scan`, `s1e_shortlist` |
| `bet-scanner-football` | Claude Opus 4.6 | YES | Football scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-tennis` | Claude Opus 4.6 | YES | Tennis scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-basketball` | Claude Opus 4.6 | YES | Basketball scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-volleyball` | Claude Opus 4.6 | YES | Volleyball scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-hockey` | Claude Opus 4.6 | YES | Hockey scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-esports` | Claude Opus 4.6 | YES | Esports scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-handball` | Claude Opus 4.6 | YES | Handball scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-combat` | Claude Opus 4.6 | YES | MMA scan sub-agent | Dispatched by bet-scanner |
| `bet-scanner-racket` | Claude Opus 4.6 | YES | Table tennis/padel sub-agent | Dispatched by bet-scanner |
| `bet-scanner-niche` | Claude Opus 4.6 | YES | Snooker/darts/speedway sub-agent | Dispatched by bet-scanner |
| `bet-scanner-baseball` | Claude Opus 4.6 | YES | Baseball scan sub-agent | Dispatched by bet-scanner |
| `bet-statistician` | Claude Opus 4.6 | NO | S3: Deep stats analysis | `s3_deep_stats` |
| `bet-scout` | Claude Sonnet 4.6 | NO | S2: Tipster intelligence | `s2_tipster` |
| `bet-valuator` | Claude Sonnet 4.6 | NO | S4: Odds evaluation | `s4_odds_eval` |
| `bet-challenger` | Claude Opus 4.6 | NO | S5/S6/S7: Context, upset risk, gate | `s5_context`, `s6_upset_risk`, `s7_gate` |
| `bet-builder` | Claude Opus 4.6 | NO | S8: Coupon construction | `s8_coupons` |
| `bet-settler` | Claude Sonnet 4.6 | NO | S0: Settlement | `s0_settle` |

### 4.2 Agent Integration Status

**Agents are NOT programmatically invoked by `pipeline_orchestrator.py`.** The `agent_review_required` fields are purely informational banners printed to stdout — they instruct the human/orchestrator-agent to dispatch subagents via `runSubagent`, but the script itself does not and cannot call agents.

The actual integration model is:
1. `pipeline_orchestrator.py` runs data collection + computation
2. Prints "AGENT-REVIEW-REQUIRED" banners with agent name + task description
3. The `bet-orchestrator` agent (Copilot chat) is expected to read these banners and use `runSubagent` to dispatch specialist agents
4. This means **pipeline script output is raw data**, not final analysis

### 4.3 Agent Overlap Analysis

- **`bet-challenger`** handles 3 steps (S5, S6, S7) — context, upset risk, AND gate. Could be split.
- **11 sport scanner agents** each delegate to the same `BaseSportScanner` Python infrastructure. Their agent files add sport-specific Copilot context but the actual scanning code is identical in pattern.
- **`bet-scout`** (S2 tipster) vs the tipster logic in `tipster_aggregator.py` — the script does automated scraping, the agent adds qualitative reasoning. Complementary but could be cleaner.

---

## 5. Data Flow

### 5.1 Data Flow Diagram

```
SOURCES                    PIPELINE                    OUTPUTS
─────────────────────────────────────────────────────────────────
Betclic history   ──→ S0 (settle + learn)       ──→ betclic_learning_summary.json
                                                     bankroll update

232+ URLs         ──→ S1 (Playwright scan)      ──→ scan_summary.json
                      11 parallel scanners           scan_results (DB)
                      18 adapters

API clients       ──→ S1a (discover + enrich)   ──→ fixtures_{date}.json
(13 clients)          discover_fixtures.py           fixtures (DB)
                      fetch_api_stats.py             team_form (DB)
                      enrich_tennis_stats.py         stats_cache/ (JSON)

Odds API × 2      ──→ S1b (parallel enrichment) ──→ odds_api_snapshot.json
ESPN (free)            fetch_odds_api.py              odds_api_io_snapshot.json
Weather API            fetch_weather.py               weather_{date}.json
Tipster sites          tipster_aggregator.py           tipster_aggregation_{date}.json
                       ESPN DraftKings adapter         espn_enrichment_{date}.json

All data          ──→ S1c (aggregate)           ──→ picks_suggested.json
                      aggregate_and_select.py         analysis_pool_{date}.json
                      deep_analysis_pool.py

Aggregated data   ──→ S1d (market matrix)       ──→ market_matrix_{date}.json/.md
                      generate_market_matrix.py       decision_matrix_{date}.md

Matrix data       ──→ S1e (shortlist)           ──→ {date}_s2_shortlist.json
                      build_shortlist.py

Tipster data      ──→ S2 (tipster xref)         ──→ enriched shortlist
                      (inline in orchestrator)

Shortlist         ──→ S3 (deep stats)           ──→ {date}_s3_deep_stats.json/.md
stats_cache            deep_stats_report.py           analysis_results (DB)
team_form (DB)         compute_safety_scores.py
                       probability_engine.py

S3 output         ──→ S4 (odds eval)            ──→ enriched S3 with EV
odds_history (DB)      (inline in orchestrator)
odds snapshots

S3 + weather      ──→ S5 (context checks)       ──→ enriched S3 with flags
ESPN injuries          (inline in orchestrator)

S3 enriched       ──→ S6 (upset risk)           ──→ enriched S3 with risk scores
                      (inline in orchestrator)

S3 enriched       ──→ S7 (gate check)           ──→ {date}_s7_gate_results.json/.md
                      gate_checker.py                 gate_results (DB)

Gate results      ──→ S8 (coupons)              ──→ {date}.json/.md in coupons/
                      coupon_builder.py               coupons + bets (DB)

Coupon files      ──→ S9 (validate)             ──→ validation report
                      validate_coupons.py

All artifacts     ──→ S10 (summary)             ──→ stdout summary
```

### 5.2 Data Format Inconsistencies

1. **Shortlist date format**: `build_shortlist.py` writes `{YYYYMMDD}_s2_shortlist.json` (no dashes). Orchestrator tries both formats with fallback.
2. **S3 JSON structure**: `analyses` array with nested `ranking_result.ranking` — deeply nested, fragile
3. **Odds injection**: S4 writes back to the same S3 JSON file, mutating it in-place
4. **Context/upset enrichment**: S5 and S6 also mutate the S3 JSON file in-place
5. **Candidate format inconsistency**: Different scripts use `home_team`/`away_team` vs `home`/`away` for the same concept

---

## 6. Inconsistencies Found

### CRITICAL

1. **TWO ORCHESTRATORS**: `scripts/pipeline_orchestrator.py` (2,500 lines, 15 steps, ACTIVE) vs `src/bet/pipeline/orchestrator.py` (200 lines, 5 steps, UNUSED). The package orchestrator uses a completely different step model (discover→enrich→analyze→build→settle) with async/await but is never called. The scripts-based orchestrator is the actual runner.

2. **TWO COUPON BUILDERS**: `scripts/coupon_builder.py` (~500 lines, uses config JSON directly, writes markdown+JSON, Polish translations inline) vs `src/bet/coupon/builder.py` (~100 lines, uses `BettingConfig` dataclass, returns `(Coupon, [Bet])` tuples). Only the scripts version is used by the pipeline.

3. **TWO SAFETY SCORE IMPLEMENTATIONS**: `scripts/compute_safety_scores.py` (used by pipeline — comprehensive, 500+ lines) vs `src/bet/stats/safety_scores.py` (DB-model-based, returns `MarketCandidate` objects). Only the scripts version runs.

4. **TWO MARKET RANKING DEFINITIONS**: `scripts/normalize_stats.py::SPORT_MARKETS` and `src/bet/stats/market_ranking.py::SPORT_MARKETS`. Both define the same markets but separately maintained — risk of drift.

5. **DUPLICATE POLISH TRANSLATIONS**: `scripts/coupon_builder.py::MARKET_PL` and `src/bet/coupon/translations.py::MARKET_PL` — same dict in two places.

6. **DUPLICATE REPOSITORY CODE**: `src/bet/db/repositories.py` is ~1,200 lines with 26 repo classes. The identical `SportRepo`, `TeamRepo`, `CompetitionRepo`, `FixtureRepo`, `StatsRepo` code appears in both the orchestrator's DB reads and the package's orchestrator.

7. **S4 INLINE MONSTER**: `_inject_ev_from_odds()` is ~250 lines of inline code in `pipeline_orchestrator.py` that merges odds from 4 sources (DB, the-odds-api, odds-api.io, ESPN). This should be its own module.

### HIGH

8. **`agent_review_required` is decorative**: The orchestrator prints banners about agent review but never actually invokes agents. The integration is documentation-level only — relies on the LLM orchestrator reading stdout.

9. **Unreferenced `evaluate_decisions.py`**: This post-settlement analysis script populates `decision_outcomes` table but is never called by the pipeline. It should run as part of S0 after settlement.

10. **`build_s1s2_shortlist.py` has HARDCODED dates and paths**: Contains `DATE = '2026-05-07'` and `/Users/mkoziol/projects/bet` — throwaway script committed to repo.

11. **`espn_deep_analysis.py` is not parameterized**: Hardcodes team IDs and sport leagues — a one-off debug script, not reusable.

12. **STEP ID MISMATCH**: Steps are named `s0_settle` through `s10_summary` but actual methodology documentation references S0-S10 as different semantic steps. The orchestrator prepends `s` to match Python naming conventions, creating confusion with documentation that says "STEP 3" meaning `s3_deep_stats`.

13. **`historical_learning.py` is superseded**: Reads from CSV picks-ledger, while `analyze_betclic_learning.py` reads from JSON/DB. Both serve similar purposes but `historical_learning.py` is never called by the pipeline.

### MEDIUM

14. **Mixed import patterns**: Every script does `try: from scripts.X import Y except ImportError: from X import Y` — this dual-import pattern is repeated ~40 times across the codebase. Should use a consistent `sys.path` strategy.

15. **`scan_events.py` legacy scan still maintained**: 200+ lines of monolithic scanning code that's only used as fallback when parallel scanners fail to import. Adds maintenance burden.

16. **THREE weather fallback formats**: `_run_context_checks()` handles weather data as dict, list of dicts, and list of venue dicts — evidence of format changes without cleanup.

17. **No cleanup for stale data files**: `betting/data/` accumulates per-date files indefinitely (`{date}_s3_deep_stats.json`, `market_matrix_{date}.json`, etc.). No rotation.

18. **Config value inconsistency**: `config.py::BettingConfig` uses `daily_exposure_range` while `betting_config.json` has both `daily_exposure_range` AND `suggested_daily_allocation_range_pln`. The config loader handles both names but it's confusing.

19. **`fetch_odds_multi.py` never called**: A multi-source odds aggregator that was built but never integrated into the pipeline. The S1b parallel enrichment does its own odds fetching.

20. **`fetch_espn_odds.py` partially redundant**: The ESPN odds CLI fetcher overlaps with the inline ESPN adapter in S1b's `run_espn_enrichment()` function.

---

## 7. Dead Code & Unused Files

### 7.1 Definitely Dead (can be removed)

| File | Reason |
|------|--------|
| `scripts/build_s1s2_shortlist.py` | Hardcoded date/paths, one-time throwaway |
| `scripts/espn_deep_analysis.py` | Hardcoded teams/leagues, not parameterized |
| `scripts/run_full_scan_and_prepare.sh` | Fully superseded by `pipeline_orchestrator.py` |
| `scripts/run_session.sh` | Fully superseded by `pipeline_orchestrator.py` |
| `scripts/historical_learning.py` | Superseded by `analyze_betclic_learning.py` + DB |
| `src/bet/pipeline/orchestrator.py` | Never used — `scripts/pipeline_orchestrator.py` is the real one |
| `src/bet/pipeline/progress.py` | Only used by the unused package orchestrator |

### 7.2 Questionable (may still have ad-hoc use)

| File | Notes |
|------|-------|
| `scripts/smoke_playwright.py` | Diagnostic tool — keep if useful for debugging |
| `scripts/verify_betclic_odds.py` | Manual odds verification — keep for user |
| `scripts/fetch_betclic_bets.py` | Manual bet scraping — keep for user |
| `scripts/parse_betclic_bets.py` | Manual bet parsing — keep for user |
| `scripts/seed_deep_stats.py` | One-time seeder — keep for new environment setup |
| `scripts/seed_espn_data.py` | One-time ESPN seeder — keep for new environment setup |
| `scripts/fetch_odds_multi.py` | Could replace fragmented odds fetching — potential simplification |
| `scripts/fetch_espn_odds.py` | Standalone ESPN odds — overlaps with S1b inline |
| `scripts/fetch_espn_standings.py` | Standalone standings — only used by seed_espn_data |

### 7.3 Unused Package Code

| File | Notes |
|------|-------|
| `src/bet/coupon/builder.py` | Clean implementation but never called |
| `src/bet/coupon/shopping_list.py` | Clean implementation but never called |
| `src/bet/coupon/translations.py` | Duplicated in scripts/coupon_builder.py |
| `src/bet/stats/safety_scores.py` | DB-model implementation but never called |
| `src/bet/scanner/discovery.py` | Used only by unused package orchestrator |
| `src/bet/scanner/odds_fetcher.py` | Used only by unused package orchestrator |
| `src/bet/scanner/playwright_pool.py` | Used only by unused package orchestrator |
| `src/bet/settlement/settler.py` | DB-based settler but never called |
| `src/bet/settlement/learning.py` | DB-based learning but never called |
| `src/bet/config.py` | Config loader — only used by package code |
| `src/bet/cli.py` | CLI entry point — never used |
| `src/bet/__main__.py` | Package runner — never used |
| `src/bet/adapters/betexplorer.py` | Package adapter — overlaps scripts/adapters/ |
| `src/bet/adapters/flashscore.py` | Package adapter — overlaps scripts/adapters/ |
| `src/bet/adapters/scores24.py` | Package adapter — overlaps scripts/adapters/ |
| `src/bet/utils/odds.py` | Package odds utilities |
| `src/bet/utils/team_names.py` | Package team name normalization |

---

## 8. Duplication Analysis

### 8.1 Severe Duplications (same logic in 2+ places)

| Logic | Location 1 | Location 2 | Notes |
|-------|-----------|-----------|-------|
| **Orchestrator** | `scripts/pipeline_orchestrator.py` (2,500 lines) | `src/bet/pipeline/orchestrator.py` (200 lines) | Completely different architectures |
| **Coupon builder** | `scripts/coupon_builder.py` (~500 lines) | `src/bet/coupon/builder.py` (~100 lines) | Different APIs, same purpose |
| **Safety scores** | `scripts/compute_safety_scores.py` | `src/bet/stats/safety_scores.py` | Identical algorithm, different data models |
| **Market definitions** | `scripts/normalize_stats.py::SPORT_MARKETS` | `src/bet/stats/market_ranking.py::SPORT_MARKETS` | Can drift |
| **Polish translations** | `scripts/coupon_builder.py::MARKET_PL` | `src/bet/coupon/translations.py::MARKET_PL` | Exact duplicate |
| **Standard market lines** | `scripts/generate_market_matrix.py::STANDARD_MARKET_LINES` | `src/bet/stats/market_ranking.py::STANDARD_MARKET_LINES` | Can drift |
| **Sport stat keys** | `scripts/normalize_stats.py::SPORT_STAT_KEYS` | `src/bet/stats/market_ranking.py::SPORT_STAT_KEYS` | Can drift |
| **Team name normalization** | `scripts/utils.py::normalize_team_name` | `src/bet/utils/team_names.py::normalize_team_name` | Both used |
| **Rate limiter** | `scripts/api_clients/rate_limiter.py` | `src/bet/api_clients/rate_limiter.py` | Both used |
| **API clients** | `scripts/api_clients/api_football.py` etc. | `src/bet/api_clients/api_football.py` etc. | Overlapping |
| **Odds conversion** | `pipeline_orchestrator.py::_convert_espn_odds_to_decimal` | `src/bet/utils/odds.py` (likely) | American→decimal |
| **Fixtures discovery** | `scripts/discover_fixtures.py` | `src/bet/scanner/discovery.py` | Both do API fixture discovery |

### 8.2 Pattern Duplications (same pattern repeated)

- **Dual-import try/except**: ~40 instances of `try: from scripts.X except: from X`
- **DB connection boilerplate**: Every script has `try: from bet.db.connection import get_db; _HAS_DB = True except: _HAS_DB = False`
- **Date format conversion**: `date.replace("-", "")` appears in ~10 scripts for shortlist filename
- **Odds lookup normalization**: `home.strip().lower()` + `away.strip().lower()` → key pattern appears in 5+ scripts

---

## 9. Architecture Gaps

### 9.1 Structural Issues

1. **`scripts/` vs `src/bet/` duality**: The project has TWO codebases solving the same problems. `scripts/` is the active one (grown organically), `src/bet/` is a cleaner rewrite (never activated). This creates:
   - Maintenance burden (changes need to be made in two places)
   - Confusion about which code actually runs
   - Import path complexity

2. **No single source of truth for market definitions**: `SPORT_MARKETS`, `SPORT_STAT_KEYS`, `STANDARD_MARKET_LINES` exist in multiple files. Changes in one don't propagate.

3. **`pipeline_orchestrator.py` is a God Object**: 2,500 lines with inline implementations of S2, S4, S5, S6, and S10. These should be separate modules.

4. **Missing step in pipeline**: `evaluate_decisions.py` should be S0.5 (after settlement, before new day analysis) but isn't called.

5. **No retry mechanism**: If a step fails (e.g., API timeout), the only recovery is `--resume`, which skips the step entirely. No automatic retry with backoff.

6. **No data validation between steps**: S3 output is consumed by S4-S7 without schema validation. Malformed data can propagate silently.

7. **JSON file proliferation**: Each pipeline run generates 15+ files in `betting/data/` with date-stamped names. No rotation or cleanup.

### 9.2 Missing Integrations

1. **`evaluate_decisions.py`** → Should be called after `settle_on_finish.py` in S0
2. **`build_league_profiles.py`** → Should run periodically (weekly?) to update priors for probability engine
3. **`fetch_espn_standings.py`** → Contains useful team form data not currently used in pipeline
4. **`scan_health_report.py`** → Generated but not acted upon — should trigger re-scans for failed sports

### 9.3 Testing Gaps

Tests directory contains 30+ test files covering:
- ✅ DB operations (`test_db.py`, `test_db_repositories.py`, `test_db_integration_fixes.py`)
- ✅ Safety scores (`test_safety_scores.py`, `test_compute_safety_scores.py`)
- ✅ Coupon builder (`test_coupon_builder.py`)
- ✅ Gate checker (`test_data_gate.py`)
- ✅ Pipeline modules (`test_pipeline.py`, `test_pipeline_modules.py`, `test_pipeline_integration.py`)
- ✅ API clients (`test_espn_client.py`, `test_deep_stats_clients.py`, `test_fetch_api_stats.py`)
- ✅ Adapters (`test_betexplorer_adapter.py`, `test_flashscore_volleyball.py`)
- ✅ Enrichment (`test_enrichment.py`, `test_enrichment_budget.py`)
- ❌ **No tests for**: `pipeline_orchestrator.py` (main orchestrator), `tipster_aggregator.py`, `build_shortlist.py`, `deep_analysis_pool.py`, `generate_market_matrix.py`, `aggregate_and_select.py`, `ingest_scan_stats.py`, individual sport scanners
- ❌ **No integration tests**: End-to-end pipeline run with mock data

---

## 10. Key Findings — Top 20 Critical Issues

### Architecture (must fix for maintainability)

1. **🔴 TWO PARALLEL CODEBASES**: `scripts/` (active, organic growth) vs `src/bet/` (clean rewrite, unused). Decide on ONE and eliminate the other. The `src/bet/` package code (coupon builder, safety scores, discovery, settlement, config, CLI) is never executed by the actual pipeline.

2. **🔴 GOD OBJECT ORCHESTRATOR**: `pipeline_orchestrator.py` at 2,500 lines contains inline implementations of 5+ steps. Extract S2 (tipster xref), S4 (odds eval — 250 lines), S5 (context), S6 (upset risk), and S10 (summary) into separate modules.

3. **🔴 MARKET DEFINITION DRIFT RISK**: `SPORT_MARKETS`, `SPORT_STAT_KEYS`, `STANDARD_MARKET_LINES`, and `MARKET_PL` exist in 2-3 files each. Must have ONE canonical source.

### Dead Code (cleanup for clarity)

4. **🟡 7 DEFINITELY DEAD FILES**: `build_s1s2_shortlist.py`, `espn_deep_analysis.py`, `run_full_scan_and_prepare.sh`, `run_session.sh`, `historical_learning.py`, `src/bet/pipeline/orchestrator.py`, `src/bet/pipeline/progress.py`. Remove to reduce confusion.

5. **🟡 13 UNUSED PACKAGE FILES**: Entire `src/bet/coupon/`, `src/bet/scanner/`, `src/bet/settlement/`, `src/bet/config.py`, `src/bet/cli.py` are never called. Either activate or remove.

### Data Flow (correctness risks)

6. **🔴 S3 FILE MUTATION**: Steps S4, S5, S6 all mutate the same `{date}_s3_deep_stats.json` file in-place. Race conditions are impossible (sequential execution) but the pattern is fragile — any step crash leaves partial data.

7. **🟡 DATE FORMAT INCONSISTENCY**: Shortlist uses `YYYYMMDD` while everything else uses `YYYY-MM-DD`. The orchestrator has fallback code for both formats — sign of a known but unfixed issue.

8. **🟡 FIELD NAME INCONSISTENCY**: Some scripts use `home_team`/`away_team`, others use `home`/`away`. Causes frequent `.get("home_team") or .get("home")` patterns.

### Pipeline Completeness

9. **🟡 MISSING DECISION EVALUATION**: `evaluate_decisions.py` exists but isn't called. Post-settlement analysis (`decision_outcomes` table) is never populated during pipeline runs.

10. **🟡 AGENT INTEGRATION IS FICTION**: `agent_review_required` in the orchestrator is just stdout banners. No programmatic agent dispatch. The LLM orchestrator must manually read and act on these.

### Operational

11. **🟡 NO DATA ROTATION**: Per-date files accumulate forever. After months, `betting/data/` will contain thousands of files.

12. **🟡 NO RETRY MECHANISM**: Step failures are terminal (critical) or silently skipped (non-critical). No automatic retry with backoff for transient API failures.

13. **🟡 DB GROWS INDEFINITELY**: No cleanup of old fixtures, match_stats, scan_results, odds_history. After months of daily runs, the DB could reach several GB.

### Code Quality

14. **🟡 40+ DUAL-IMPORT TRY/EXCEPT BLOCKS**: Every script has `try: from scripts.X except: from X` blocks. Should use a single import strategy.

15. **🟡 INLINE ODDS MERGING (250 lines)**: `_inject_ev_from_odds()` in the orchestrator handles 4 different data sources with format-specific parsing. Should be a separate module with unit tests.

16. **🟡 LEGACY MONOLITHIC SCANNER**: `scan_events.py` (200+ lines) is maintained as fallback but only used if parallel scanners fail to import.

### Configuration

17. **🟡 CONFIG KEY NAMING**: `betting_config.json` uses inconsistent names (`bankroll_pln` vs `working_bankroll_pln`, `daily_exposure_range` vs `suggested_daily_allocation_range_pln`). The config loader handles aliases but it adds confusion.

18. **🟡 HARDCODED VALUES**: `MAX_LEGS = 3`, `MAX_SAME_SPORT = 2`, various thresholds are hardcoded in scripts rather than in config.

### Testing

19. **🟡 NO ORCHESTRATOR TESTS**: The most critical file (`pipeline_orchestrator.py`) has zero test coverage.

20. **🟡 NO E2E PIPELINE TEST**: No test runs the full pipeline with mock data to verify end-to-end flow.

---

## Appendix A: File Count Summary

| Directory | Files | Lines (est.) |
|-----------|-------|-------------|
| `scripts/` (root) | 52 | ~15,000 |
| `scripts/scanners/` | 16 | ~3,000 |
| `scripts/adapters/` | 18 | ~5,000 |
| `scripts/api_clients/` | 24 | ~6,000 |
| `scripts/odds_sources/` | 7 | ~1,500 |
| `src/bet/` | 30 | ~5,000 |
| `.github/agents/` | 19 | ~3,000 |
| `tests/` | 31 | ~4,000 |
| **Total** | **~197** | **~42,500** |

## Appendix B: Import Dependency Graph (simplified)

```
pipeline_orchestrator.py
├── deep_stats_report.py ← normalize_stats.py ← compute_safety_scores.py
│                        ← generate_market_matrix.py (STANDARD_MARKET_LINES)
├── gate_checker.py ← check_48h_repeats.py
├── coupon_builder.py
├── validate_coupons.py
├── scanners/ ← base_scanner.py ← adapters/ ← fetch_with_playwright.py
│             ← merge_results.py ← bet.db.repositories
├── db_data_loader.py ← bet.db.connection ← bet.db.repositories
├── utils.py
├── probability_engine.py
└── tipster_aggregator.py ← fetch_with_playwright.py
```

## Appendix C: Recommended Refactoring Priorities

**Phase 1 — Cleanup (low risk, high clarity gain):**
1. Delete 7 dead files
2. Consolidate market definitions into ONE canonical source
3. Consolidate Polish translations into ONE file
4. Fix date format to always use `YYYY-MM-DD`
5. Standardize field names to `home_team`/`away_team` everywhere

**Phase 2 — Extraction (medium risk, architecture improvement):**
1. Extract S4 odds evaluation into `scripts/odds_evaluator.py`
2. Extract S5/S6 into `scripts/context_checks.py` and `scripts/upset_risk.py`
3. Extract S2 tipster xref into `scripts/tipster_xref.py`
4. Add `evaluate_decisions.py` call to S0

**Phase 3 — Unification (high impact, needs careful migration):**
1. Decide on `scripts/` vs `src/bet/` — recommend keeping `scripts/` as active and removing unused `src/bet/` package code OR gradually migrating scripts into the package
2. Add orchestrator unit tests
3. Add data rotation / cleanup mechanism
4. Add retry mechanism for transient failures
