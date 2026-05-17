# Pipeline Knowledge Base — Consolidated (May 4-14, 2026, updated 2026-05-17)

## 🆕 DB-FIRST MIGRATION + SQLITE LOCK FIX — 2026-05-17

**Plan:** `specifications/db-first-migration-plan.md` — 3 phases, 10 tasks.

### Phase 0 — SQLite Lock Fix (critical data loss prevention)
- **connection.py:** `busy_timeout` increased from 5s → 30s. Added `retry_on_lock()` utility with exponential backoff (0.5s → 1s → 2s, 3 retries).
- **data_enrichment_agent.py:** Added `_db_write_lock = threading.Lock()` to serialize all DB writes across worker threads. `_save_to_db()` and `_save_h2h_to_db()` wrapped with lock. `sqlite3.OperationalError` caught separately (CRITICAL log) — no longer silently swallowed by bare `except Exception`.
- **Root cause:** 4 worker threads each opened separate sqlite3 connections via `get_db()`, all writing to `team_form` table. With 5s busy_timeout, lock contention caused `OperationalError` that was silently caught = **data lost**.

### Phase 1 — DB-First Read Order
- **coupon_builder.py:** Flipped from JSON-first to DB-first gate results loading. `load_gate_results_from_db()` is primary, JSON is fallback.
- **context_checks.py:** DB-first S3 analysis loading via `load_analysis_results_from_db()`, JSON fallback.
- **upset_risk.py:** DB-first S3 analysis loading via `load_analysis_results_from_db()`, JSON fallback.
- **data_enrichment_agent.py:** DB-first fixture loading in `_detect_missing_from_shortlist()` via `load_fixtures_from_db()`.

### Phase 2 Bug Fix (found during live test)
- **batch_enrich Phase 2 retry filter:** Now only retries teams that failed due to thread-safety (greenlet/worker thread errors). Previously retried ALL failed teams including cached-404, which triggered `MAX_CONSECUTIVE_FAILURES=15` early termination before greenlet-skipped teams got a chance.
- **DB-first loading fix:** `_detect_missing_from_shortlist` no longer returns all teams when none are missing from cache (was `return missing if missing else teams_from_db` → now `return missing`).

### Tests Added
- `tests/test_db_connection.py` — 6 tests: `retry_on_lock` (success, retry, exhaustion, non-lock errors, backoff) + `busy_timeout=30000` verification.
- `tests/test_enrichment_thread_safety.py` — 4 tests: `_db_write_lock` exists, used in `_save_to_db` and `_save_h2h_to_db`, lock errors not silently swallowed.

### Live Test Results (2026-05-17)
- DB-first fixture loading: 3906 teams from 2089 fixtures ✅
- Single-team enrichment (Barcelona): saved to cache + DB ✅
- No DB LOCK errors with 4 workers ✅
- DB health: 207K team_form rows, 6750 unique teams ✅
- 36 tests pass (26 existing + 10 new) ✅

### Architecture Notes
- All pipeline scripts are **hybrid dual-write** (DB + JSON). No pure JSON-only scripts in core pipeline.
- DB layer: custom sqlite3 + dataclasses repos (`src/bet/db/`), NOT SQLAlchemy ORM (except discovery module).
- `--top` defaults to `None` (all candidates). The 200 limit was user/agent CLI behavior, not hardcoded.
- `db_data_loader.py` provides all DB-first loaders: `load_fixtures_from_db()`, `load_analysis_results_from_db()`, `load_gate_results_from_db()`, etc.
- Flashscore blocked by Cloudflare — fallback sources still provide data.

### Previous greenlet fix (same day, earlier commit)
- **data_enrichment_agent.py:** Guard `_fetch_stealth()` and `_try_flashscore()` with main-thread checks. Reset `_source_failures` before Phase 2 retry.

## 🆕 METHODOLOGY FIX — 2026-05-16

**Plan:** `specifications/pipeline-methodology-fixes.plan.md` — 5 phases, 16 tasks.

### Bugs Fixed
- **data_enrichment_agent.py:** Misleading "tennis player" log (line ~1137) → now shows actual sport. Dead code removed. batch_enrich Phase 2 gets early-break after 15 consecutive failures. Per-source circuit breaker (5 failures → skip source for rest of run).
- **deep_stats_report.py:** `--no-enrich` now emits prominent WARNING log.
- **run_scrapers.py:** Scraper failures now correctly set status="partial" instead of masking as "ok". AGENT_SUMMARY reports failure count.
- **repositories.py:** `save_team_form()` docstring documents concurrent write hazard.

### Documentation Fixed
- **All 10 bet-*.agent.md:** Consistency audit — R17 analysis-only rule, correct skills, correct instructions array. bet-db-analyst got missing analysis-methodology instruction.
- **bet-enricher.agent.md:** Raw SQL replaced with `StatsRepo.save_team_form()`. Concurrent write hazard documented.
- **bet-statistician.agent.md:** match_stats documented as sparsely populated with team_form fallback.
- **bet-orchestrator.agent.md:** Script→DB data flow matrix added (12 scripts with reads/writes/notes).

### Prompt Fixes
- **orchestrate-betting-day.prompt.md:** Anti-patterns #16-#18 added. §STEP COMPLETENESS GATE (S3→S7 dependency matrix). §DELEGATION COMPLIANCE GATE (running checklist per step). Delegation blocks simplified with §DELEGATION TEMPLATE references. Pipeline-errors log added to S0 context loading.

### Instruction Updates
- **analysis-methodology.instructions.md:** Zero Tolerance entries #22-#27 added (step skipping, tennis player log, batch_enrich early-break, --no-enrich flag, delegation enforcement, circuit breaker).

### Key Patterns
- **Circuit breaker:** `_source_failures` dict + `_source_is_down()` in data_enrichment_agent.py. Threshold=5, module-level, thread-safe with Lock.
- **Concurrent write hazard:** build_stats_cache, data_enrichment_agent, and deep_stats_report all write team_form. Must run sequentially.
- **Delegation enforcement:** §DELEGATION COMPLIANCE GATE in orchestration prompt — running checklist that tracks Script+Agent per step.

## 🆕 POST-REFACTOR ALIGNMENT — COMPLETED (2026-05-14 EVE)

**Plan:** `specifications/post-refactor-alignment.plan.md` — 7 phases, 20 tasks.

### What Was Fixed (all misalignments from discovery/scrapers/odds refactoring)

**Critical script fixes:**
- `inspect_pipeline.py`: `kickoff_utc` → `kickoff` (2 SQL sites), metric key `total_scan_events` → `total_discovery_events`
- `validate_phase.py`: recovery message `discover_fixtures.py` → `discover_events.py`
- `agent_protocol.py`: `kickoff_utc` → `kickoff` in tournament protection query

**Model A enforcement (3 agents aligned):**
- `bet-scanner`: Now CONDITIONAL — analysis-only when orchestrator-delegated, script-running when user-invoked directly
- `bet-settler`: Pure ANALYSIS-ONLY (R17 updated, script execution instructions removed)
- `bet-db-analyst`: Pure ANALYSIS-ONLY

**Documentation alignment (phantom scraper_to_team_form.py removed from 6 files):**
- Removed from: orchestrator agent, orchestration prompt (S2.4 step deleted), enricher agent, enricher prompt, pipeline-knowledge-base, orchestrator script table
- S2.4 remains in specs as BACKLOG (planned feature, not current pipeline)
- Scraper count updated 14→19 everywhere (matches actual `_SCRAPER_REGISTRY`)
- `scan_events.py` references replaced with `discover_events.py` in all instructions/skills
- `ask-betting.prompt.md` updated: memory refs, DB-first context surfaces

**Orchestrator fixes (2026-05-14 EVE):**
- Behavioral Mandate #1: Fixed critical contradiction — was "NEVER run analytical scripts yourself" (old model), now correctly says "YOU run ALL scripts, specialists ONLY analyze" (Model A)
- Script Execution Table: Expanded from 8→18 entries — added all S2-S8 analytical scripts with exact commands, PYTHONPATH, timeouts, modes
- Delegation Reference Table: Removed 2 deleted prompt refs (bet-scan-merge, bet-scan-all)
- Script count: 15 (corrected from 14)

**Cleanup:**
- Deleted: `_archive_integrate-discovery-module.prompt.md` (completed migration, 20+ stale refs)
- `source-registry.md`: Added Source Classification Quick Reference table (automated/manual/tipster/archived)

**Tests added:**
- `tests/test_inspect_pipeline.py`: regression tests for kickoff column, metric key consistency
- `tests/test_validate_phase.py`: regression tests for recovery script references
- 567 tests passing (1 pre-existing unrelated failure)

**README rewritten:** No fake CLI, correct modules, 5 sports, Model A, actual architecture

## 🆕 ODDS PIPELINE CLEANUP — COMPLETED (2026-05-14)

**Plan:** `specifications/odds-pipeline-cleanup.plan.md` — 6 phases, 20 tasks, 8 ADRs.

### What Changed
- **Evaluator** (`odds_evaluator.py`): Removed dead ESPN Source 3 + Phase 6 dropping odds. Now reads 3 sources: DB + the-odds-api snapshot + odds-api.io snapshot.
- **UnifiedAPIClient** (`unified.py`): Removed `ODDS_PRIORITY` dict + `get_odds()` method (both broken). `get_dropping_odds()` kept with degraded note.
- **Odds Source Registry** (`odds_sources/__init__.py`): Removed oddsportal/betexplorer from `SPORT_SOURCE_PRIORITY`. Now 3 sources max per sport.
- **fetch_odds_multi.py**: Removed oddsportal/betexplorer from `_SOURCE_MODULES`. 3 working sources.
- **fetch_odds_api_io.py**: Now has `--verbose` + AGENT_SUMMARY (R19 compliant). Volleyball primary source. DB persistence FIXED (2026-05-14 PM).
- **agent_protocol.py**: Added to `scripts_with_verbose`. ESPN description updated (stats only, no odds).

### DB Persistence Fix (2026-05-14 PM)
Two bugs in `_persist_io_odds_to_db()` caused **zero** odds-api.io records to reach the DB:
- Bug A: `event.get("sport")` returns a dict `{name, slug}`, not a string → `.lower()` crash → entire persistence silently failed
- Bug B: `event.get("kickoff")` doesn't exist in odds-api.io data → always fell back to midnight. Actual field is `"date"`
- Fix: use `_our_sport` (normalized string) and `date` field. Live-tested: **1048 records persisted** (Betclic PL + Bet365).

### Odds Pipeline Architecture (post-cleanup)
```
Sources:  the-odds-api (4 sports, 500 cr/mo) + odds-api.io (5 sports, 5000 req/hr) + api-football-odds (football)
Scripts:  fetch_odds_api.py | fetch_odds_api_io.py | fetch_odds_multi.py (orchestrates all 3)
DB:       odds_history table (all sources write here)
Eval:     odds_evaluator.py reads DB + 2 snapshot JSONs → injects EV into S3 candidates
```

### Key Decisions
- BetExplorer/OddsPortal: kept for fixture discovery, removed from odds pipeline
- ESPN: kept for stats/standings, removed from odds pipeline (API returns empty odds)
- odds-api.io: activated as primary volleyball odds source + secondary for all 5 sports
- Betclic HTML parse: unchanged (manual workflow, ADR-7)

## 🆕 SCRAPER MODULE — LIVE-TESTED (2026-05-14)

**Location:** `src/bet/scrapers/` — 19 scrapers across 5 sports, SQLAlchemy 2.0 ORM.
**CLI:** `scripts/run_scrapers.py --sport all --season 2425 --verbose`
**Tests:** 80/80 passing. DB: 98 league_profiles, 3,912 player_season_stats, 12,360 athletes.

### Scraper Status (live-verified)
| Sport | Source | Status | Data Volume |
|-------|--------|--------|-------------|
| Football | fbref | ✅ | 20 teams, 574 players |
| Football | flashscore | ✅ | 5/5 teams |
| Basketball | nba-api | ✅ | 21 teams, 569 players |
| Basketball | basketball-reference | ✅ | 19 teams, 736 players |
| Basketball | flashscore | ✅ | 3/3 teams |
| Tennis | sackmann | ✅ FIXED | 457 players |
| Tennis | sofascore-tennis | ⚠️ STUB | Fixtures only |
| Tennis | flashscore | ⚠️ PARTIAL | 1/3 teams |
| Hockey | nhl-api | ✅ FIXED | 15 teams, 261 players |
| Hockey | hockey-reference | ✅ FIXED | 27 teams, 1,251 players |
| Hockey | flashscore | ✅ | 3/3 teams |
| Volleyball | volleybox | ❌ 403 | Cloudflare blocked |
| Volleyball | sofascore-volleyball | ⚠️ STUB | Fixtures only |
| Volleyball | flashscore | ✅ | 3/3 teams |

### Critical Integration Gap
- **team_form bridge NOT built yet.** Scrapers write to `league_profiles` + `player_season_stats`. Pipeline reads `team_form`.
- Need: `scripts/scraper_to_team_form.py` adapter (see `specifications/scrapers-pipeline-integration.md`)
- **Football corners/fouls:** NOT available from scrapers. Old `data_enrichment_agent.py` remains only source.

### Bugs Fixed During Verification (2026-05-14)
1. Sackmann season `"2425"` → year `"2025"` (was `"2024"`)
2. NHL standings → date-based endpoint
3. NHL player stats → multi-category response parsing
4. NHL teamAbbrev string vs dict
5. Hockey-Ref → HTML comment extraction
6. Hockey-Ref → `player_stats` table ID
7. Volleybox → `"2024-2025"` season format

### New Pipeline Steps (not yet added to pipeline execution)
- S2.3: `run_scrapers.py` — 19 scrapers, ~2-3 min total
- S2.4 (BACKLOG): `scraper_to_team_form.py` — bridge adapter (TO BE BUILT, not part of current run)
- S2.5: `data_enrichment_agent.py` — now GAP-FILL FALLBACK only

## ✅ CRITICAL BUGS — ALL FIXED (2026-05-14)

| Bug | File(s) | Root Cause | Fix |
|-----|---------|------------|-----|
| **A** | `flashscore.py` | Deep enrichment in ThreadPoolExecutor → Playwright greenlet crash. Also `f.className` JS error (DOMTokenList not string). | Sequential main-thread enrichment (`--deep-workers 1`, `--deep-limit 50`). JS: `String(f.className \|\| '')`. |
| **B** | `data_enrichment_agent.py` | Thread guards skipped ALL Playwright clients in workers → 89% teams got nothing. | Phase 2 main-thread retry for failed/empty teams after thread pool pass. |
| **C** | `build_shortlist.py` | FIXTURE_ONLY scored 75 (same as STATS_ONLY for good leagues). | FIXTURE_ONLY tier score 5→0 + total score ×0.5 multiplier. |
| **D** | `deep_stats_report.py` | `--top 200` picked 144 dateless candidates first. | Sort by data_tier before applying `--top` (STATS_ONLY+ first, FIXTURE_ONLY last). |
| **E** | `odds_evaluator.py`, `utils.py` | Exact string match — "Montréal" ≠ "Montreal". | All odds sources + candidate lookup use `normalize_team_name()` (accents, hyphens, FC/SC). Fuzzy substring fallback. |

---

## ⛔ KNOWN ISSUES — ALL FIXED (2026-05-14, Phase 3)

| Issue | File(s) | Root Cause | Fix |
|-------|---------|------------|-----|
| **1+2** | `unified.py` | ESPN created new client per league + 400 flood for ~65 leagues | Reuse 1 ESPNClient per sport, cache 400/404 failures in-memory |
| **3** | `unified.py` | `get_fixture_stats()` on scheduled matches → guaranteed empty | Skip stats for `status="scheduled"`, pass status through chain |
| **4** | `flashscore.py` | "Advancing to next round" concatenated in team name from DOM | JS regex strip in `_JS_EXTRACT_FIXTURES` |
| **5** | `data_enrichment_agent.py` | Flashscore player pages 404 for all tennis players | Skip `_try_flashscore()` for `sport == "tennis"` |
| **6** | `flashscore.py` | `.h2h__row` selector stale | Added `[class*="h2h"]` wildcard fallback selectors |
| **7** | `gemini_news_enrichment.py` | 0 results logged without diagnostics | Added success/empty/error counters to batch_enrich_news |
| **8** | `data_enrichment_agent.py` | Lower-league teams 404 repeatedly every run | `known_missing_teams.json` cache with 7-day TTL |
| **9** | (legacy, removed) | `db_scan_results=0` on re-run misleading | Log "X skipped as duplicates", add `db_scan_attempted` metric |
| **10** | `fetch_api_stats.py` | Uses legacy `scripts/api_clients/`, times out on 1500+ fixtures, redundant with S2.3+S2.5 | **Removed from pipeline S1a (2026-05-15).** Script stays in repo. Superseded by `run_scrapers.py` (S2.3) + `data_enrichment_agent.py` (S2.5). `seed_espn_data.py` kept for unique ESPN data. |

---

## Data Funnel (2026-05-14 actual numbers)
```
1203 scanned → 0% with deep data from scan
506 shortlisted → 448 FIXTURE_ONLY (88%), 58 STATS_ONLY (12%)
200 fed to deep_stats → 144 no data, 56 with data → 98 analyzable
After S4-S7 gates → 3-4 viable core picks
```

---

## Enrichment Architecture

### Layer Priority
1. **DB team_form** (primary) — 200K+ entries, per-stat l10_avg/l5_avg/count
2. **JSON stats_cache** — `betting/data/stats_cache/{sport}/{slug}.json`, `_home`/`_away` suffixes
3. **ESPN** — 11.5K+ gamelogs, standings, ATS/OU records (basketball/hockey/baseball)
4. **Niche sport caches** — esports/darts/table_tennis player form
5. **Scan data ingestion** — `ingest_scan_stats.py` bridges scan → stats_cache + DB
6. **data_enrichment_agent.py** — Flashscore direct/search, Sofascore, scores24.live

### Key Limitations
- ESPN: no soccer player gamelogs, no handball/snooker/darts/table_tennis/esports/padel
- Betclic: always 403 — NEVER scrape
- 7 sports have ZERO API odds: snooker, darts, table_tennis, esports, mma, padel, speedway
- Football API odds: only ~92/4292 events covered (use stats-first mode R10)

### Enrichment Backlog
- Items moved to "KNOWN ISSUES" section above: tennis 404 (ISSUE 5), Gemini news (ISSUE 7), thread-guarded clients (fixed in BUG B Phase 2), lower-league 404 (ISSUE 8)
- Standalone Flashscore module details: see `memories/repo/flashscore-enricher-implementation.md`

---

## Safety Score Patterns (A-I)

| Pat | Rule | Cap |
|-----|------|-----|
| A | Directional conflict detection | — |
| B | Knockout/continental SF/Final | 0.65-0.70 |
| C | Sport volatility (baseball/hockey/basketball) | 0.55/0.60/0.70 |
| D | Concentration (>2 coupons, >25% budget) | flag |
| E | Data tier (youth 0.60, state 0.55, women 0.60, 2nd div 0.70) | varies |
| F | Line sensitivity P(hit) tables | ±0.5/±1/±1.5/±2 |
| G | Evidence requirements (safety ≥0.80 needs ≥10 L10 + H2H) | — |
| H | **One-sided data** | **hard cap 0.40** |
| I | **Small sample (<8 games in L10)** | **hard cap 0.50** |

---

## Data Quality Traps (proven killers)

1. **Synthetic data** — `db-synthetic` fabricates L10 from sparse data → cap at 0.50 safety
2. **Cache key mismatches** — `corners_home`/`corners_away` vs bare `corners` → check both
3. **Standard line collision** — basketball team [95-110] vs combined [195-225] → separate dicts
4. **Market-matched EV** — ML odds applied to corners prob = impossible EV → match market types
5. **JSON overwrite between steps** — S4 overwrote S3 full file → read JSON first, DB fallback
6. **DB status case** — "APPROVED" vs "approved" → use `UPPER(status)` always
7. **Compound penalty death spiral** — H2H×synthetic×one-sided = 0.245 → floor at 0.40
8. **UPSET_THRESHOLDS int vs float** — 55 (int) vs 0.55 (float) → keep consistent units
9. **L5 trend wrong slice** — L10 most-recent-first, `[:5]` = L5 (not `[-5:]`)
10. **Dedup ignores team order** — use `min(home,away)|max(home,away)|date` for dedup key

---

## Pipeline Architecture (current)

- ~48K LoC, 153 files, 21 agents, 62 scripts, 28 DB tables
- SQLite WAL at `betting/data/betting.db`, connection: `from bet.db.connection import get_db`
- Scripts = DATA TOOLS. Agents = ANALYSTS. `src/bet/` = shared packages (db, api_clients, stats, discovery)
- `src/bet/stats/market_ranking.py` = SINGLE SOURCE OF TRUTH for SPORT_MARKETS, STANDARD_MARKET_LINES, MARKET_PL
- 15 scripts emit `AGENT_SUMMARY:{json}` with `--verbose`. Exit: 0=OK, 1=partial, 2=critical
- Orchestrator runs ALL scripts (Model A). Specialists ONLY analyze output — they NEVER run scripts.
- Gate vocabulary: status=APPROVED/EXTENDED/REJECTED, advisory_tier=STRONG/MODERATE/WEAK/FLAGGED, risk_tier=LR/MS/HR/N
- Config: `max_legs_per_coupon: 4`, `min_safety_score: 0.4`, `max_picks_per_day: 80`

### Event Discovery Module — `src/bet/discovery/` (2026-05-14, FULLY INTEGRATED)

API-first event discovery using 3 structured sources. **Fast** (~30s). Live-tested: 1807 raw → 1734 merged events. Legacy `scan_events.py` and `beast_mode_pipeline.py` DELETED.

| Source | Coverage | Events (typical) |
|--------|----------|------------------|
| SofaScore Daily Schedule API | All 5 sports | ~1500 |
| API-Football | Football only | ~250 |
| The Odds API | Football (10 leagues) + auto-discovered tennis/hockey | ~17 (with structured odds) |

**Entry point:** `from bet.discovery import discover_events` or CLI `scripts/discover_events.py --date YYYY-MM-DD --verbose`

**Key files:**
- `coordinator.py` — orchestrates fetch→dedup→persist→JSON (ThreadPoolExecutor, 3 workers)
- `dedup.py` — exact match by `{sport}|{norm_home}|{norm_away}|{date}` + rapidfuzz fuzzy (threshold 85, ±2h window)
- `repository.py` — SQLAlchemy ORM for `fixture_sources` table (schema v8)
- `sources/sofascore.py`, `sources/odds_api.py`, `sources/api_football.py` — SourceAdapter Protocol implementations
- `models.py` — Pydantic v2 (DiscoveredEvent, MergedFixture, DiscoveryResult) + SA ORM (FixtureSourceModel)

**DB writes:** Same tables as old scan (`fixtures`, `teams`, `competitions`, `scan_results`) via raw SQL `text()` + `fixture_sources` via SA ORM. Backward-compatible JSON: `{date}_s1_events.json`.

**Persistence:** Savepoint-per-fixture (`session.begin_nested()`) — single FK/data error doesn't wipe batch.

**normalize_team_name:** Single source of truth at `src/bet/utils.py`. `scripts/utils.py` re-exports it.

**Integration handoff:** `betting/plans/discovery-integration-handoff.md` — 8 files to update (orchestrator prompt, agents, protocol). 32 tests (tests/discovery/).

**Deep integration guide:** `specifications/discovery-module-integration-guide.md` — 19-section reference covering architecture, source adapters, dedup engine, DB schema, JSON output format, CLI, data flow diagrams, integration points for ingest/shortlist/enrichment/scrapers/deep-stats, adding new sources/sports, testing strategy, performance, and troubleshooting.

**Status:** FULLY INTEGRATED. All orchestrator, agent, prompt, and script files updated. No legacy fallback paths.

### API Clients (2026-05-14)
- **unified.py** routes: Football(Flashscore→BetExplorer→Soccerway→ESPN), Tennis(Flashscore→Scores24→ESPN)
- **ESPN Site API** now uses **HTTPS** (was HTTP) — all endpoints confirmed working
- **ESPN `get_espn_league_for_competition()`** now uses **fuzzy substring matching** (was exact only). Matches "PKO BP Ekstraklasa"→pol.1, "La Liga EA Sports"→esp.1, etc. Longest-key-first to avoid ambiguity.
- **New clients:** BetExplorerClient(HTTP), OddsPortalClient(Playwright), TotalCornerClient(Playwright), Scores24Client(Playwright), SoccerwayClient(HTTP)
- **BetExplorer/Soccerway** `get_fixture_stats()` and `get_h2h()` are **stubs** (return `[]`, log debug). Only useful for fixture discovery + odds.
- **Sofascore Playwright fallback** now **reuses shared browser** (`_pw_browser` class-level cache) instead of launching/destroying per 403 request. Call `SofascoreClient.close_playwright()` for cleanup.
- **Disabled:** TheSportsDB, BallDontLie, API-Tennis
- **Sport adapters (2026-05-12):** Hockey=MoneyPuck PRIMARY, Tennis=TennisAbstract Elo, Basketball=Basketball-Reference enhanced

### Data Quality Guards (2026-05-14)
- **TeamRepo.find_or_create()** now **rejects garbage team names** before DB insert: ad text (`"#100 FREE $20"`), odds strings (`"- 1.03 11.00"`), promo text, separators. Raises `ValueError` — callers should catch.
- **Stat key `_home`/`_away` convention** is BY DESIGN: `build_stats_cache.py` saves venue-split keys (`corners_home`, `corners_away`), `enrichment.py` saves base keys (`corners`). Both consumers (`deep_stats_report.py`, `normalize_stats.py`) handle both conventions correctly.

---

## Execution Protocol (what works)

### Run-Then-Delegate Model (Model A — adopted 2026-05-14)
The orchestrator runs ALL scripts and delegates analysis-only to specialist subagents.
```
ORCHESTRATOR:
1. INSPECT: pylanceRunCodeSnippet → verify inputs (R18)
2. RUN: run_in_terminal(mode=async, --verbose, timeout)
3. THINK-WHILE-WAITING: sequentialthinking + pylanceRunCodeSnippet
4. MONITOR: get_terminal_output → watch for 404/403/timeouts → react immediately
5. EXTRACT: Parse AGENT_SUMMARY:{json} + key warnings
6. VALIDATE: pylanceRunCodeSnippet → verify outputs (R18)
7. DELEGATE: runSubagent(specialist) → pass AGENT_SUMMARY + log excerpts
8. RECEIVE: specialist returns analysis-only verdict (no script execution)
9. QUALITY GATE: 5-question check
10. DECIDE: PROCEED / FIX+RETRY / ESCALATE
```

**Why this replaced the old model (2026-05-14):**
- Subagents would launch scripts then sit idle at "Preparing" (R17 violation)
- Orchestrator was blind to 404/403 errors during subagent execution
- Despite extensive rules (R17, §ASYNC DELEGATION ENFORCEMENT, pre-filled async blocks, think_while_waiting field, Q6 quality gate), subagents still didn't comply
- Root cause: adding more rules doesn't help (instruction-design-lessons.md)
- Fix: remove script execution from subagents entirely — they ONLY analyze

### Structured Subagent Verdict Format (Model A — analysis-only)
Specialist agents receive script output and return verdicts in this format:

```
## Verdict: {script_name} (analysis-only)
```subagent_verdict
verdict: APPROVED | FLAGGED | REJECTED
quality_score: 1-10
script: {script_name}
exit_code: {from orchestrator context}
execution_model: analysis-only
```
### Metrics        — ≥3 rows, from provided script output
### Anomalies      — specific anomaly + root cause
### Analysis       — agent's ORIGINAL specialist reasoning
### Impact         — what downstream step should know
### Issues         — actionable blockers or `None`
### User Summary   — 2-3 plain-language sentences for user presentation
### Data For Orchestrator — required keys: next_step_ready, quality_flags, focus_points
```

**Section classification:**
- Facts-only: `subagent_verdict`, `Metrics`, `Anomalies`, `Issues`, `Data For Orchestrator`
- Reasoning: `Analysis`, `Impact`, `User Summary`

**Orchestrator duties:**
- Parse `subagent_verdict` → `Metrics` → `User Summary` → `Data For Orchestrator`
- Present user update: step header + User Summary + 2-4 key metrics + Next line
- Maintain quality ledger: step, agent, verdict, quality_score, key handoff fact
- 5-question quality gate before accepting any verdict (see §SUBAGENT OUTPUT VERIFICATION in orchestrate-betting-day.prompt.md)

---

## Betclic Constraints
- Hockey: **Penalty Minutes NOT available** — use total goals, puck line, period totals
- Always verify exotic statistical markets exist before including in core coupons
- Standard hockey markets: ML, total goals O/U, puck line (handicap), period O/U

---

## Tennis-Specific
- ESPN provides only 4 markets: Total Games O/U, Player A/B Games O/U, Total Sets O/U
- Individual sports: min_matches=3 (not 5)
- Lucky Loser entry = HARD REJECT (ZT#22)
- Over sets without H2H = HARD REJECT (ZT#3-EXT)
- Scan 45 days back for player matches

---

## Post-Mortem: 2026-05-13 Coupon (1W/3L, -2.0 PLN) — ALL FIXED

| Bug | Fix | Pattern |
|-----|-----|---------|
| Duplicate fixtures | Dedup by normalized team names (accent-stripped, FC/SC removed) | `duplicate_fixture_conflict` |
| One-sided data | Safety hard-capped at **0.40** (Pattern H) | `missing_opponent_data` |
| Opponent quality | ZT#23 flags stat markets vs top-5 opponents (standings query) | `opponent_quality_mismatch` |
| Small sample bias | Safety capped at **0.50** when L10 <8 games (Pattern I) | `small_sample_bias` |
| Odds vs safety gap | Gate #19: flag when gap >15 percentage points | `odds_vs_safety_disagreement` |

---

## Session Lessons (process)

1. **Rule overload causes blindness** — when everything is BOLD/URGENT, nothing stands out. Fix: shorter instructions + concrete examples + per-agent "YOUR VALUE" statements
2. **Duplicated instructions get skimmed** — single source of truth in agent-execution-protocol.instructions.md
3. **Examples teach better than rules** — each internal prompt needs filled-in good output example
4. **Pre-S3 data check** — if <50% have team_form data → enrich FIRST (not after S3 fails)
5. **S2 + S2.5 parallel** — independent, run simultaneously
6. **2-3 leg coupons preferred** — AKO5/7 = 0 wins historically
7. **UNDER picks 74% hit rate** — strongest direction historically
8. **Statistical markets 63% > outcomes 45%** — team_corners 87%, cards 75%, fouls 67%

---

## HTML Deep Parser (20 profiles, 2026-05-08)
- 12,166 enrichments from 538 snapshots across 20 domains
- Key: Flashscore(9482), TennisAbstract(1060), TennisExplorer(550), Forebet(251), Basketball-Reference(250)
- Sofascore = __NEXT_DATA__ JSON, Scores24 = React Query dehydrated, Betclic = JSON script blocks
- PRIMARY_SCAN_DOMAINS fail at <30% match, others WARN at <15%

---

## Modular Scrapers System (2026-05-14)

New module `src/bet/scrapers/` — 19 scrapers across 5 sports, SQLAlchemy 2.0 ORM, coexists with raw sqlite3.

| Sport | Sources | Data Written |
|-------|---------|-------------|
| Football | FBref, **ESPN**, Flashscore | league_profiles, player_season_stats, player_gamelogs |
| Basketball | NBA API, Basketball-Reference, **ESPN**, Flashscore | league_profiles, player_season_stats, player_gamelogs |
| Tennis | Sackmann CSVs, SofaScore API, **ESPN**, Flashscore | league_profiles, player_season_stats, player_gamelogs, fixtures |
| Hockey | NHL API, Hockey-Reference, **ESPN**, Flashscore | league_profiles, player_season_stats, fixtures |
| Volleyball | Volleybox, SofaScore API, **ESPN**, Flashscore | league_profiles, player_season_stats, fixtures |

**ESPN Scraper** (`src/bet/scrapers/espn.py`): wraps `ESPNClient` from `api_clients/espn.py`. 5 sport subclasses. Football: 29 stat keys (corners, fouls, yellow_cards, shots, possession, goals, crosses, clearances...). Free API, no key, no rate limits. Live-tested 2026-05-14.

**CLI:** `scripts/run_scrapers.py` — `--sport all`, `--sport hockey --source espn`, `--list`, `--fixtures YYYY-MM-DD`

**⚠️ GAP (partially resolved):** Scrapers do NOT yet write to `team_form` table. An adapter (`scraper_to_team_form.py`) is needed to bridge scraper data → L10/L5 → `team_form`. ESPN resolves the FOOTBALL corners/fouls gap that was previously only available via old enrichment.

**Status:** 103/103 scraper unit tests passing (all mocked). ESPN live-tested. NOT integrated into pipeline yet (need adapter).

**Full docs:** `specifications/scrapers-pipeline-integration.md`, `memories/repo/scrapers-module-migration-guide.md`
