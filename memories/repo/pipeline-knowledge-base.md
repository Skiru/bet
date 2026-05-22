# Pipeline Knowledge Base — Consolidated (May 4-22, 2026, updated 2026-05-22)

## 🆕 FLASHSCORE STAT KEY SEPARATION — 2026-05-22

### Problem
FlashScore HTML regex fallback (`_extract_match_scores`) sums home+away scores, producing GAME TOTALS. These were stored under team-specific keys (`goals`, `points`) which then polluted per-team L10 analysis in `normalize_stats.py` → `compute_safety_scores.py`. A team averaging 1.2 goals would show 2.8 because game totals were stored.

### Fix (3 files)
| File | Change |
|------|--------|
| `scripts/flashscore_enricher.py` | Feed parser: `stats["goals"] = our_scores` (per-team); `stats["game_total_goals"] = total_scores` (combined). HTML fallback: stores under `game_total_*` only. |
| `src/bet/scrapers/flashscore.py` | `_primary_score_key()` returns `game_total_goals`/`game_total_points` (not `goals`/`points`) |
| `src/bet/stats/value_ranges.py` | Added validation ranges for `game_total_goals` (0-15/0-20) and `game_total_points` (100-350) |

### Data Flow After Fix
- **Feed parser** (`_parse_embedded_feed`): produces BOTH `goals` (team-specific, from `our_scores`) AND `game_total_goals` (combined `total_scores`)
- **HTML fallback** (`_extract_match_scores`): produces ONLY `game_total_*` (cannot distinguish teams)
- **normalize_stats.py** → uses `goals`/`points` stat keys (per-team) for market analysis — CORRECT
- **If only HTML fallback ran**: no `goals` key available → normalize_stats finds nothing → correct (game totals shouldn't masquerade as per-team)

### Basketball range fix
- `points` range narrowed from (50, 180) → (50, 160) — reflects realistic per-team scoring

## 🆕 SESSION HARDENING (22 May 2026 PM)

### Today's Committed Changes (6 commits)
1. **Fixture status filter** — PST/CANC/ABD/AWD/WO/SUSP detection in gate_checker, coupon_builder, validate_coupons (3 layers)
2. **Tipster shortlist boost** — DB tipster consensus (≥2 tipsters or HIGH) gives +25/+40 score in shortlist
3. **Tennis walkover filter** — `compute_safety_scores.py` rejects values below 12 total games or 6 player games
4. **Tipster spam filter** — `tipster_aggregator.py` validates picks against actual fixtures
5. **Tipster pool in coupon** — Advisory section showing high-consensus picks not in pipeline
6. **Betclic validator fixes** — False demotion prevention + junk event filter

### Code Review Fix Applied
- `validate_coupons.py` `check_fixture_status`: Changed first-token matching to longest-word matching (≥3 chars) to avoid false positives from common prefixes ("fc", "sc", "as")

### Tests: 800 passed, 0 failures

## 🆕 BOVADA PUBLIC FEED INTEGRATION (PLANNED) — 2026-05-22

### Discovery
Evaluated multiple free data sources. Rejected SportsDataverse (broken xgboost, wraps ESPN) and WagerWise (empty 0-record DB). Discovered Bovada public JSON API — richest free source found.

### Bovada Public API
- **URL:** `https://www.bovada.lv/services/sports/event/v2/events/A/description/{sport}/{league}`
- **Auth:** NONE — completely free, no API key, no rate limit documented
- **Format:** JSON with American + Decimal + Fractional odds
- **Live tested 2026-05-22:** All endpoints return 200 from EU IP (no geo-block)

### Confirmed Working Endpoints
| Endpoint | Events | Markets/event | Key Data |
|----------|--------|--------------|----------|
| /basketball/nba | 2 | 268-510 | Player Points/Rebounds/Assists/3PM/Blocks/Steals O/U, PRA combos, quarter/half |
| /basketball/wnba | 3 | 326 | Same as NBA |
| /hockey/nhl | 2 | 194 | Goalscorers (anytime/first/last), Player SOG O/U, period markets |
| /tennis/atp | 6 | 178 | Game spread, set betting, per-player game totals |
| /tennis/wta | 6 | 157 | Same as ATP |
| /baseball/mlb | 15 | 1221 | Pitcher props, player HR/hits/RBI/runs/bases |
| /volleyball | 21 | 119 | ML + totals only (no player props) |
| /soccer | 42MB mega | ALL leagues | Goal spread, 3-way ML, totals — needs streaming parser |
| /football/nfl | 20 | 90 | Spread, total, ML |
| /table-tennis | 86 | 658 | ML + totals, live events |
| /esports | 84 | 953 | ML + totals + maps |

### Dead Endpoints (404/empty)
Individual soccer league paths (/soccer/epl, /soccer/bundesliga etc.) return 404 — all soccer combined in one mega-endpoint.

### Integration Architecture (Plan: `betting/plans/bovada-integration.plan.md`)
- **DB-FIRST:** All data writes to SQLite — NO JSON file primary storage (R2)
- **Main odds** → existing `odds_history` table with `bookmaker="bovada"` → auto-integrated with `odds_evaluator.py` Source 0
- **Player props** → NEW `player_prop_lines` table (fixture_id, athlete_name, market_type, line, over/under odds)
- **Fixture matching:** NEVER creates phantom fixtures — only writes for events already discovered by `discover_events.py`
- **Pipeline position:** After S1 (discover_events.py), before S3/S4 (deep_stats/odds_evaluator)
- **Soccer handling:** `ijson` streaming parser for 42MB endpoint with competition filter

### Implementation Status: PENDING
Files to create:
- `src/bet/api_clients/bovada.py` — client (no BaseAPIClient inheritance, uses RateLimiter)
- `scripts/fetch_bovada_odds.py` — fetcher script (writes to DB via OddsRepo + PlayerPropRepo)
- `src/bet/db/models.py` — add PlayerPropLine dataclass
- `src/bet/db/repositories.py` — add PlayerPropRepo class
- `src/bet/db/schema.sql` — add player_prop_lines table + indexes

Files already updated (agent awareness):
- `.github/copilot-instructions.md` — §2b + Source Rules + PENDING marker
- `.github/agents/bet-orchestrator.agent.md` — script list + DB matrix + delegation map
- `.github/agents/bet-valuator.agent.md` — sources + DB access + script output
- `.github/agents/bet-scanner.agent.md` — source architecture + Phase 2 + DB tables
- `.github/agents/bet-enricher.agent.md` — DB access (player_prop_lines)
- `.github/agents/bet-statistician.agent.md` — DB access (L10 vs line comparison)
- `betting/sources/source-registry.md` — full Bovada entry + classification table

### Key Design Decisions
| Decision | Choice | Rationale |
|----------|--------|-----------|
| API key | None needed | Public endpoint |
| Rate limiting | 1 req/30s, 500/day cap | Conservative — no documented limits |
| Odds format | Convert American→Decimal on ingest | Pipeline uses decimal everywhere |
| Soccer endpoint | ijson streaming + competition filter | 42MB would OOM without streaming |
| Inheritance | Standalone class (not BaseAPIClient) | No API key, simpler interface |
| Retry | 3 attempts, exponential backoff | Match existing pattern |

### Rejected Sources (this session)
- **SportsDataverse:** Broken xgboost dependency, just wraps ESPN API → uninstalled
- **WagerWise:** Returns empty database (0 records for any query) → rejected

## 🆕 ESPN CLIENT EXPANSION — 2026-05-22

### Summary
Full audit of ESPN client against Public-ESPN-API documentation (github.com/pseudo-r/Public-ESPN-API). Added 7 missing high-value endpoints, expanded soccer league coverage from 36→70+ leagues, fixed provider ID mapping.

### New Endpoints Added
| Module | Method | What It Does | Sports |
|--------|--------|-------------|--------|
| `espn.py` | `get_coaches(year)` | League coaching staff list | NBA, NHL (soccer=500) |
| `espn.py` | `get_coach_record(id, type)` | Coach W/L/T record (type: 0=total, 1=home, 2=away) | NBA, NHL |
| `espn.py` | `get_play_by_play(event_id)` | Goals/cards/corners/subs with timestamps | All sports |
| `espn.py` | `get_cdn_game_package(game_id)` | Full boxscore+plays+odds in one call | Unreliable (returns HTML) |
| `espn_stats.py` | `get_realtime_news(sport, league, team)` | Real-time injury/transfer news | All sports |
| `espn_odds.py` | `get_futures(sport, league, year)` | Season futures betting markets | NBA, NHL |
| `espn_odds.py` | Provider IDs updated | Both format 1 (1001-1004) and format 2 (37-68) | All |

### Soccer League Expansion (+34 leagues)
Added: `eng.fa`, `esp.copa_del_rey`, `ger.dfb_pokal`, `ita.coppa_italia`, `fra.coupe_de_france`, `ned.cup`, `por.taca.portugal`, `uefa.champions_qual`, `uefa.europa_qual`, `uefa.europa.conf_qual`, `fifa.worldq.concacaf`, `fifa.worldq.caf`, `uefa.nations`, `conmebol.recopa`, `concacaf.nations.league`, `concacaf.leagues.cup`, `caf.nations`, `caf.champions`, `arg.copa`, `bra.copa_do_brazil`, `bra.2`, `chi.1`

### Known Limitations (verified live)
- Soccer coaches endpoint returns HTTP 500 (ESPN limitation)
- CDN game package (`cdn.espn.com/core/`) returns HTML, not JSON — endpoint locked down
- Player gamelogs only work for NBA, NHL (not soccer)
- Tennis injuries returns 500

### Live Test Results (2026-05-22)
- ✅ Coaches NBA: 25 coaches, records work (Quin Snyder: 292-237-0, 55.2%)
- ✅ Play-by-play EPL: 161 plays for eng.1 match
- ✅ Futures NBA: 15 season markets
- ✅ News: basketball + soccer news working (headlines key)
- ✅ All 41 existing ESPN tests pass (no regression)

## 🆕 SHORTLIST + COUPON SCORING OVERHAUL — 2026-05-22

### Root Cause (21.05 Post-Mortem)
Pipeline produced 110+ garbage events from Iraqi, Vietnamese, Georgian, Paraguayan leagues with 0.00-0.52 safety scores. Coupons were boilerplate with no reasoning. Orchestrator didn't call specialist subagents.

### Changes Made
| File | Change |
|------|--------|
| `scripts/build_shortlist.py` | League quality scoring: unbettable markers (return 0), bettable league boost (×7 weight), unknown league penalty (×0.3/×0.5), quality floor (score < 10 removed), MAJOR_COMPETITIONS fallback |
| `scripts/coupon_builder.py` | Structured per-coupon output with `_build_rich_description()` per leg (L10/L5/H2H reasoning), matrix capped to top 30, fixed KeyError on `c['id']`, fixed falsy hit_rate=0.0 |
| `.github/prompts/orchestrate-betting-day.prompt.md` | "TOP 3 FAILURES" header from post-mortem + enrichment `--limit 60` |

### Code Review Fixes (v2)
| Bug | Issue | Fix |
|-----|-------|-----|
| BUG-1 | `c['id']` KeyError in `_coupon_section()` | Use `.get('id', f'COUPON-{i}')` |
| LE-1 | "women" in obscure_markers blocked WSL | Narrowed to "women u17/u19/u20/reserve/amateur" |
| LE-2 | COMP_TIER_KEYWORDS missing Veikkausliiga, Cyprus, etc. | Added 15 leagues to tier 6 |
| LE-3 | `hit_rate_l10=0.0` silently dropped (falsy) | Changed to `is not None` check |
| LE-4 | MIN_SCORE_THRESHOLD=20 was R3 violation | Lowered to 10 (only catches absolute junk) |
| FP-1 | `comp_score≤3` penalty too aggressive | Split into ≤2 (×0.3) and ≤4 (×0.5), added MAJOR_COMPETITIONS fallback returning 6 |

### Scoring Math (for reference)
- Recognized major league FIXTURE_ONLY: ~42 pts (comp 8×7=56, ×0.4 fixture) → PASSES
- Unknown league FIXTURE_ONLY: ~3 pts (comp 2×7=14+5=19, ×0.3 unknown, ×0.4 fixture) → FILTERED
- French Open tennis: ~127 pts (comp 10×7+stats+major+tournament) → TOP PRIORITY
- Unbettable country: 0 pts → FILTERED at _score_competition level

### Verification
- 744 events → 312 garbage (regex) + 276 sub-threshold (score<10) = **95 candidates** (was 110+ garbage before)
- Distribution: 32 football, 32 basketball, 24 tennis, 7 hockey
- Top candidates: French Open qualifying, major European football

### Final Outcome
- Tokenized `d.flashscore.com/x/feed/d_st_{event_id}` feed is retired from runtime.
- Branch B is the final settlement policy. Branch A is superseded and removed from `scripts/settle_on_finish.py`.
- Football stat-market settlement now reads canonical DB `match_stats` through `_fetch_settlement_db_match_stats()` and `settle_stat_market()`, not Flashscore HTML.
- When required football stat coverage is missing, picks stay unresolved and are tagged `manual_verification_required`.
- Shared helper `scripts/_helpers/flashscore_match_page_stats.py` remains in use for shared Flashscore HTML/search/results-page enrichment flows, not for the main settlement path.

### Validation Anchors
- Live validation passed on real ledger pick `PK-20260507-02` (`Crystal Palace vs Shakhtar Donetsk`) with `db_match_stats_settlement` provenance.
- Focused cleanup validation passed: `PYTHONPATH=src .venv/bin/pytest -q tests/test_flashscore_token_policy.py tests/test_flashscore_match_page_stats.py tests/test_db_repositories.py` → 47 tests passing.

### Implementation Notes
- Settlement code no longer carries Branch A Flashscore wrapper delegates, request-budget globals, or settlement-only HTML helper state.
- Flashscore HTML regression coverage now lives with the owning shared helper tests in `tests/test_flashscore_match_page_stats.py`.

## 🆕 PIPELINE REMEDIATION COMPLETE + DEEP REVIEW — 2026-05-19

### What
Completed ALL 32 tasks from `specifications/pipeline-remediation.plan.md` (5 phases). Then deep review found and fixed 8 regressions. **Final state: 681 tests pass, 0 failures.**

### Plan Phases Completed
| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 — Stats Module Extraction | 1.1-1.5 | `src/bet/stats/` package: fetcher.py, fallback_chains.py, value_ranges.py |
| 2 — API Client Consolidation | 2.1-2.5 | Moved 8 clients from `scripts/api_clients/` → `src/bet/api_clients/`, shim __init__.py |
| 3 — Settlement Enhancements | 3.1, 3.3 | Stat-market settlement groundwork via `settle_stat_market()`; later finalized as Branch B DB-backed settlement |
| 4 — Build & Test Infra | 4.1-4.6 | conftest.py, pyproject.toml paths, test fixtures, CI config |
| 5 — Dead Code Removal | 5.1-5.3 | unified.py kept (still imported), scripts/api_clients/ now shim-only |

### Deep Review: 8 Bugs Found & Fixed
| # | Issue | Root Cause | Fix |
|---|-------|-----------|-----|
| 1 | `data_quality` default "MINIMAL" in coupon_builder | Picks without field sent to Extended Pool | Default → "FULL" (gate-approved = adequate) |
| 2 | Module-level `out` undefined in coupon_builder | _FallbackOutput class missing | Added `_FallbackOutput` + `global out` in main() |
| 3 | `_filter_past_events` removed test picks | Hardcoded "2026-05-01" was past date | Dynamic `datetime.now() + timedelta(days=1)` |
| 4 | `_record_source_health` ImportError in gemini_client | Function missing from base_client.py | Added function to src/bet/api_clients/base_client.py |
| 5 | Dual class definitions (isinstance mismatch) | scripts/ and src/ both define APIRateLimitError | Fixed test imports to use bet.api_clients.base_client |
| 6 | ESPN registry conflict | espn_adapter.ESPN_FACTORIES overwrote _espn_factory | Changed to `if _k not in CLIENT_REGISTRY` (no overwrite) |
| 7 | Thread safety tests reference `_save_to_db` | Function renamed to `_save_flashscore_to_db` | Updated test assertions |
| 8 | TransactionRepo test date 12 days old | Hardcoded "2026-05-07" outside 7-day window | Dynamic `datetime.now() - 2 days` |

### Key Architecture Decisions

**API Client Registry (src/bet/api_clients/__init__.py):**
- 16 clients load successfully at runtime (api-football×4, flashscore, oddsportal, totalcorner, scores24, soccerway, betexplorer, espn×5, gemini)
- 6 newly-moved clients (football_data_org, understat, nba_api, serpapi, google_sports, odds_api_io) fail import due to `from normalize_stats import ...` — gracefully caught by try/except
- `normalize_stats.py` lives in `scripts/` — these clients need PYTHONPATH to include scripts/ to load (pre-existing, not a regression)
- ESPN registration order: `_espn_factory` (ESPNClient) registers first, `espn_adapter` (ESPNMultiLeagueClient) only fills gaps (espn-tennis was added to _espn_factory)

**scripts/api_clients/ shim:**
- `__init__.py` rewrites sys.path and re-exports from `bet.api_clients`
- Individual .py files still exist with their own class defs (legacy, for scripts importing them directly)
- `isinstance()` checks work correctly ONLY when importing from `bet.api_clients.*` (canonical path)

**Settlement: DB-backed stat settlement (settle_on_finish.py):**
- Branch B uses `_fetch_settlement_db_match_stats()` + `settle_stat_market()` for football stat markets.
- Manual fallback is explicit when canonical DB `match_stats` coverage is missing.
- Shared Flashscore match-page helper remains available for enrichment/shared HTML use, not as the settlement main path.
- Only for football picks that remain unsettled after score-based settlement

### Test Infrastructure State
- **681 tests pass** (up from 602 at start of remediation plan)
- conftest.py: PYTHONPATH=src auto-configured, tmp_db fixture, mock_api_keys
- pyproject.toml: `testpaths = ["tests"]`, `pythonpath = ["src", "scripts"]`
- All date-dependent tests use dynamic dates (no more hardcoded past dates)

### Known Gaps (tracked, not blocking)
1. `normalize_stats.py` in scripts/ — 10 api_client modules import from it; needs move to src/bet/stats/
2. `unified.py` kept alive — still imported by 2 test files
3. ESPN dual-client architecture — ESPNClient (simple) vs ESPNMultiLeagueClient (adapter) coexist

## 🆕 ORCHESTRATOR FILES DEEP REVIEW & FIX — 2026-05-19

### What
Deep review of `orchestrate-betting-day.prompt.md` and `bet-orchestrator.agent.md` found 13 issues (inconsistencies, Model B remnants, missing scripts, wrong counts). All fixed.

### Files Changed
| File | Edits | Key Changes |
|------|-------|-------------|
| `.github/prompts/orchestrate-betting-day.prompt.md` | 7 | S2 Model A rewrite, S7.5/S7.6/S9 steps added, R19 fixed, Pre-filled table updated, parallel note fixed |
| `.github/agents/bet-orchestrator.agent.md` | 8 | Execution Loop unified to Model A, PYTHONPATH standardized, 4 scripts added, Data Flow Matrix updated, anti-pattern #5 fixed |
| `.github/copilot-instructions.md` | 1 | R19: "15 scripts" → "6 scripts" with explicit list |
| `.github/instructions/agent-execution-protocol.instructions.md` | 1 | Diagram: "6-question" → "5-question" gate |

### Issues Found & Fixed
1. **S2 followed Model B** — told subagent to run `tipster_xref.py`. Rewritten: orchestrator runs script, passes output to bet-scout for analysis-only.
2. **Agent.md Execution Loop** had stale Model B text ("subagent runs script + analyzes"). Unified to Model A.
3. **validate_betclic_markets.py missing** from pipeline. Added as S7.5 pre-coupon gate.
4. **validate_coupons.py never called** explicitly. Added to S9.
5. **check_48h_repeats.py not called**. Added as S7.6 loss-repeat detector.
6. **R19 AGENT_SUMMARY claimed 15 scripts** — only 6 actually emit it. Corrected everywhere (prompt, agent, copilot-instructions).
7. **Quality gate "5 vs 6"** inconsistency between files. Standardized to "5-question" everywhere.
8. **S2.3 (scrapers) missing** from compliance gate + delegation reference. Added.
9. **build_shortlist.py --verbose/--force** — neither flag exists. Removed from commands.
10. **Parallel execution note** said "launch subagents in parallel" (Model B). Fixed to "run scripts then delegate analyses".
11. **PYTHONPATH inconsistencies** — mix of `python3`, `.venv/bin/python3`. All standardized to `PYTHONPATH=src .venv/bin/python3`.
12. **4 scripts missing from agent.md** — validate_betclic_markets, check_48h_repeats, validate_coupons, generate_coupon_pdf. Added to command table + data flow matrix.
13. **Anti-pattern #5** still said "RUN + THINK + VALIDATE" (Model B). Fixed to analysis-only language.

### AGENT_SUMMARY Reality (verified via grep)
**DO emit:** discover_events, run_scrapers, odds_evaluator, context_checks, upset_risk, validate_coupons (6 total)
**DO NOT emit (despite previous claims):** tipster_aggregator, tipster_xref, data_enrichment_agent, deep_stats_report, gate_checker, coupon_builder, build_shortlist, fetch_odds_multi, ingest_scan_stats

### Current Pipeline Steps (complete list)
```
S0   — settle_on_finish.py + evaluate_decisions.py + analyze_betclic_learning.py + data_rotation.py
S1   — discover_events.py (scan)
S1e  — build_shortlist.py (shortlist)
S2   — tipster_xref.py (tipster cross-reference)
S2.3 — run_scrapers.py (Flashscore/Soccerway)
S2.5 — data_enrichment_agent.py (API enrichment)
S3   — deep_stats_report.py (statistical analysis)
S4   — odds_evaluator.py (EV/Kelly)
S5   — context_checks.py (injuries/weather/form)
S6   — upset_risk.py (upset probability)
S7   — gate_checker.py (approval gate)
S7.5 — validate_betclic_markets.py (market existence check)
S7.6 — check_48h_repeats.py (48h loss repeat detector)
S8   — coupon_builder.py (portfolio construction)
S9   — validate_coupons.py (V1-V10 validation)
S10  — generate_coupon_pdf.py (PDF output)
```

## 🆕 METHODOLOGY ALIGNMENT WITH REMEDIATION — 2026-05-19

### What
Aligned all methodology/instruction docs with the pipeline remediation changes (13 files, commit `6de74ee`).

### Key Updates
1. **Settlement categories changed** — corners/cards/shots/fouls upgraded from "Manual" to DB-backed semi-auto settlement via `settle_stat_market()` + `_fetch_settlement_db_match_stats()`. Only HC, MyCombi, and unresolved stat markets without DB coverage remain manual. Updated in 5 files: copilot-instructions, analysis-methodology, bet-settler agent, bet-settling-results SKILL, bet-settle prompt.

2. **API client canonical path** — `src/bet/api_clients/` is canonical (35+ clients). `scripts/api_clients/` = shim that re-exports. Updated references in bet-enricher agent, bet-navigating-sources SKILL, orchestrate-betting-day prompt.

3. **Stats module documented** — `src/bet/stats/` package (value_ranges.py, fallback_chains.py, fetcher.py) added to project-structure. FALLBACK_CHAINS source updated in bet-enricher agent.

4. **DB table count: 30 → 41** — Schema v10 has 31 tables in schema.sql + 10 from migration 005 (ESPN). Updated in 7 files: bet-querying-database SKILL, bet-orchestrator agent, bet-db-analyst agent, orchestrate-betting-day prompt (2 places), ask-betting prompt, project-structure memory.

### Current Settlement Categories
- **Auto:** winner/1X2, totals (any line), BTTS, double chance — from score/result sources
- **Semi-auto:** football corners, cards, shots, fouls — via `settle_stat_market()` reading canonical DB `match_stats`
- **Manual:** HC, MyCombi, unresolved stat markets without DB coverage

## 🆕 BETCLIC MARKET SCRAPER — FULL IMPLEMENTATION — 2026-05-18/19

### What
Complete production system for detecting which betting markets actually exist on Betclic, so the pipeline stops recommending unavailable markets (corners/cards/shots for minor leagues, hockey, etc.).

### Files Created/Modified
| File | Action | Purpose |
|------|--------|---------|
| `src/bet/scrapers/betclic.py` | REWRITTEN (~600 lines) | BetclicSession + BetclicMarketChecker + parse_event_page() |
| `scripts/validate_betclic_markets.py` | REWRITTEN | Pre-coupon validation gate (scan + validate picks) |
| `src/bet/db/migrations/010_betclic_markets.sql` | CREATED | Schema for betclic_markets + betclic_competition_profiles |
| `src/bet/db/schema.py` | MODIFIED | SCHEMA_VERSION=10, migration handler |
| `src/bet/db/schema.sql` | MODIFIED | Added betclic tables at end |
| `scripts/coupon_builder.py` | MODIFIED | Loads validation JSON, renders "⚠️ WALIDACJA RYNKÓW BETCLIC" section |

### Key Architectural Decisions
1. **curl_cffi (NOT Playwright)** — Chrome impersonation via `impersonate='chrome110'`, session-based, retry logic
2. **Angular SSR extraction** — Market data in `<script>` tag (~500K chars), regex `"marketId":"X","marketName":"Y"` pairs
3. **Direct sqlite3 connection** — `BetclicMarketChecker` uses direct `sqlite3.connect()` + `_configure_connection()` (not `get_db()` context manager) for long-lived connections
4. **Competition registry** — 38 competitions across 5 sports with Betclic URL paths
5. **Time-dependent markets** — Statystyki tab only ≤48h before kickoff. Validation MUST run on betting day.

### Pipeline Integration Flow
```
validate_betclic_markets.py --date X --validate-coupon coupon.md
  → scans Betclic sport/competition pages
  → checks each event for Statystyki tab + market count
  → validates coupon picks against findings
  → outputs: betting/data/betclic_market_validation_{date}.json
  → persists to DB: betclic_markets + betclic_competition_profiles

coupon_builder.py --date X
  → loads betclic_market_validation_{date}.json (if exists)
  → sets coupons_data["betclic_market_validation"]
  → write_coupon_markdown() renders unavailable/unknown/available tables
```

### Market Detection Rules (NEVER_HAS_STATISTICS)
- **Hockey**: NEVER has statistical markets on Betclic (any competition)
- **DFB Pokal**: NEVER has them (even match day)
- **Minor leagues**: Rarely have them (< 200 open markets = no stats)
- **PL/EL/CL within 48h**: ALWAYS have full statistical markets (300-600 total)

### E2E Results (2026-05-18)
- 43 events scanned across 5 sports in ~54s
- 17 coupon picks correctly flagged UNAVAILABLE
- DB: 26 events stored, 14 competition profiles, Premier League avg_mkt=254
- Probe scripts cleaned up (3 deleted)

### DB Tables Added (v10)
- `betclic_markets` (19 cols): sport, competition, event, tabs JSON, market_count, has_statistics_tab, detected_markets JSON, checked_at
- `betclic_competition_profiles` (15 cols): sport, competition, typically_has_statistics, avg_open_markets, observations_count
- 5 indexes for efficient lookups

## 🆕 PRE-FLIGHT VERIFICATION + DATA FLOW FIX — 2026-05-18 (afternoon)

### Critical Fix: tipster_support Data Flow Gap (S2→S3→S7→S8)
**Problem:** `deep_stats_report.py` (`_analyze_one()`) did NOT pass `tipster_support` from the shortlist candidate dict into its output. Result: S3 JSON had 0/927 candidates with `tipster_support` despite S2 shortlist having 30/927 with the field populated. Gate checker (S7) and coupon builder (S8) read empty `{}` for all.

**Fix (commit 8aea661):**
- Line ~1553: `result["tipster_support"] = candidate.get("tipster_support", {})` injected after `_analyze_one()` returns
- Line ~1707: JSON output builder includes `tipster_support` in `json_entry` if present

### Dead Tipster Sites Removed from Methodology Docs
Removed 4 sites from `.github/instructions/analysis-methodology.instructions.md` and `.github/prompts/audit-scraping-pipeline.prompt.md`:
- **OLBG** — aggressive Cloudflare 403
- **Tipstrr** — JS-only empty shell
- **Tips180** — domain expired
- **Meczyki** — never existed (hallucinated reference)

### Pipeline Readiness State (verified 2026-05-18 16:00 CET)
| Component | Status | Detail |
|-----------|--------|--------|
| Scripts (13) | ✅ All import | Zero import errors |
| Database | ✅ 41 tables | 1406 fixtures, 883 team_form, 273 tipster_picks |
| Config | ✅ Complete | bankroll=57.235 PLN, daily 5-15 PLN, max stake 2 PLN |
| API Keys | ✅ 7/9 | odds-api, odds-api-io, serpapi, api-football/basketball/hockey, football-data-org |
| Odds API credits | ✅ 500 remaining | 44 used from S1 scan |
| Betclic history | ✅ 9435 lines | Ready for S0 |
| Dependencies | ✅ | playwright, curl_cffi, rapidfuzz |
| Tests | ✅ 602 pass | 5 pre-existing failures (unrelated) |
| Git | ✅ Clean | 2 commits pushed (ec41749 code review, 8aea661 verification) |

### Non-blocking Notes
- `thesportsdb` key = placeholder (3 chars) — not used by core pipeline
- `gemini` key = empty — optional AI summarization only
- `odds_api_key.txt` has placeholder text but `api_keys.json` has working key (adapter reads JSON first)

### Sports Distribution for 2026-05-18
- Tennis: 1031 fixtures
- Football: 215 fixtures
- Basketball: 134 fixtures
- Volleyball: 15 fixtures
- Hockey: 11 fixtures

## 🆕 CODE REVIEW FIXES (10 issues) — 2026-05-18

### Critical Fixes (4)
1. **C1 — Stale `ratio` variable** (`tipster_playwright.py:974`): In ZawodTyper XHR dedup branch, `ratio` read from PREVIOUS loop iteration → wrong accuracy. Fix: local `_ratio = float(ratio_raw)`.
2. **C2 — Hardcoded `2026` year** (`tipster_aggregator.py:1217,1363`): Sportsgambler regex `prediction[^"]*2026` → breaks Jan 2027. Fix: `str(datetime.now().year)` dynamic.
3. **C3 — `rapidfuzz` hard import** (`tipster_xref.py:10`): No try/except → crash if not installed. Fix: `_RAPIDFUZZ_AVAILABLE` guard.
4. **C4 — `IndexError` on whitespace** (`fetch_espn_odds.py:351`): `"  ".split()[0]` crashes. Fix: pre-split + check `home_parts` truthy.

### High Fixes (3)
5. **H1 — AGENT_SUMMARY lost on crash** (`daily_odds_warmup.py`): If Playwright throws, summary never emitted. Fix: crash handler in `__main__` emits FAILED summary + `sys.exit(2)`.
6. **H2 — Missing EOF newline** (`daily_odds_warmup.py`): Added trailing newline + `sys` import.
7. **H4 — Bare `except` in DB fallback** (`coupon_builder.py:351`): Swallowed DB errors silently. Fix: `logging.warning()` with exc details.

### Medium/Low Fixes (3)
8. **M1 — Duplicate `"claim now"`** in `_GARBAGE_REASONING_PHRASES` set + **M5 — redundant `import json as _json`** in fetch_espn_odds. Removed.
9. **M8 — Detail page errors swallowed** (`tipster_aggregator.py:2088`): Added `_log()` with URL + error.
10. **L2 — Agreement ignores direction** (`coupon_builder.py:307`): `OVER≠UNDER` now correctly detected — added `direction_match` check.

### Accepted/Deferred
- **H3 — `_auth_failed` no reset:** OddsAPI circuit breaker has no reset mechanism. Low risk (adapter recreated each pipeline run). Deferred.
- **M3 — `SPORT_VALUE_RANGES` in flashscore_enricher `__all__`:** Cosmetic, deferred.
- **M4 — O(n²) dedup in ZawodTyper XHR:** Performance acceptable at current scale (~200 bets). Deferred.
- **M7 — Fuzzy matching O(n×m):** 200K comparisons but ~200ms total. Deferred.
- **L3 — Garbage/signal words duplicated:** Between tipster_aggregator + tipster_playwright. Deferred (shared module refactor).

## 🆕 AUDIT FIXES + TIPSTER-TO-COUPON FEATURE — 2026-05-18

### Phase 1: Code Fixes (8 audit findings)
| Fix | File | Change |
|-----|------|--------|
| AGENT_SUMMARY | `fetch_odds_api.py` | Added structured output for R19 |
| Auto-install removed | `flashscore_enricher.py` | Removed subprocess curl_cffi install |
| Unified SPORT_VALUE_RANGES | `src/bet/stats/value_ranges.py` (NEW) | Single source of truth, 50 keys across 5 sports |
| Scanner tools | `bet-scanner.agent.md` | Removed `playwright/*` |
| Stale API refs | `bet-statistician.agent.md` | Removed basketball_reference, moneypuck |
| Discovery PARTIAL verdict | `src/bet/discovery/coordinator.py` | Added 0-persisted detection |
| OddsAPI circuit breaker | `src/bet/discovery/sources/odds_api.py` | `_auth_failed` stops 401 loops |
| ESPN odds DB query | `fetch_espn_odds.py` | Fixed JOIN via teams table + fuzzy LIKE fallback |

### Phase 2: Documentation (3 tasks)
- `bet-enricher.agent.md`: Concrete fallback chains per sport (replaced abstract L1-L6)
- `bet-querying-database/SKILL.md` + `bet-deep-stats.prompt.md`: H2H retrieval docs
- `bet-navigating-sources/SKILL.md`: Google Sports / SerpAPI section

### Phase 3: Tipster-to-Coupon Feature (3 tasks)
- `gate_checker.py`: `tipster_support` dict passed through (backward compatible)
- `coupon_builder.py`: `_build_tipster_insight()` + `_get_tipster_data_fallback()` + `_tipster_pick_to_dict()`
- Output format: `🎯 TIPSTER INSIGHT:` with per-tipster bullets + `✓ ZGODNOŚĆ` / `↔ NASZ WYBÓR` comparison
- Direction-aware agreement (OVER≠UNDER), fuzzy DB fallback via rapidfuzz

### Tests: 637 passed, 6 pre-existing failures (unchanged)

## 🆕 TIPSTER AGGREGATOR: DEAD SITES REMOVED + BUG FIXES — 2026-05-18

### Sites Removed (3)
- **Tips180** (`tips180.com`) — domain expired, DNS failure
- **OLBG** (`olbg.com`) — aggressive Cloudflare, 403 on all pages including /tips/
- **Tipstrr** (`tipstrr.com`) — returns empty HTML shell (JS-only, no useful content via Playwright)

### Current 7 Sites (TIPSTER_SITES)
| Site | Fetch | Detail Pages | Avg Reasoning Length |
|------|-------|--------------|---------------------|
| ZawodTyper | Playwright (JS) | ❌ (inline) | 651 chars |
| Feedinco | HTTP + detail | /predictions/YYYY-MM-DD/Team-vs-Team-prediction | 457 chars |
| PicksWise | HTTP + detail | /news/ articles (__NEXT_DATA__ extraction) | 220 chars |
| Sportsgambler | HTTP + detail | /predictions/league/team-a-vs-team-b | 105 chars |
| BettingClosed | HTTP + detail | /prediction/{id}/{slug} (1x2, BTTS, O/U, correct score) | 60 chars |
| BetIdeas | HTTP + detail | /league/team-a-vs-team-b-{id} | 49 chars |
| Typersi | Playwright (JS) | ❌ (inline) | 0 chars (picks only) |

### Bugs Fixed
1. **BettingClosed IndexError:** `pred_match.group(2)` crashed when fallback regex (1 group) was used. Fix: check `pred_match.lastindex >= 2` before accessing group(2).
2. **Dead `playwright_only` code:** Tips180 was the only site using `playwright_only=True` flag. After removal, the conditional was dead code. Removed entirely.
3. **Formatting artifacts:** Extra blank lines from site removal cleaned up.

### Architecture: Post-Playwright Detail Page Enrichment
After Playwright returns basic picks (event + market + pick), 5 parsers follow detail page URLs via HTTP to extract reasoning:
```
Playwright → list[dict] with detail_url field
→ HTTP GET detail_url (within SITE_FETCH_TIMEOUT - 3s)
→ Parser extracts reasoning text → TipsterPick.to_dict() → extends result["picks"]
```
**Key:** `detail_url` lives only in Playwright dicts (used during enrichment), not persisted to final output.

### Playwright Client Changes (`tipster_playwright.py`)
- `_convert_raw_to_picks()` preserves `detail_url` field from raw JS extraction
- `_JS_EXTRACT_BETIDEAS` uses raw string (r-prefix) for regex — prevents escape issues in `page.evaluate()`
- BetIdeas JS finds `a[href*="-vs-"]` links and returns `{detail_url, ...}` per pick

### Temp Files Cleaned Up (6 deleted)
`_check_pw_detail.py`, `_test_zt_bets.py`, `_test_zt_intercept.py`, `_analyze_zt_comments.py`, `_analyze_tipster_html.py`, `_analyze_sg_detail.py`

### Test Results
637 passed, 6 failed (all pre-existing, unrelated to these changes)

## 🆕 ENRICHMENT AGENT: COMPLETE REWRITE + TENNIS FIX — 2026-05-18

### Problem
`data_enrichment_agent.py` was 1715 lines of broken monolithic code:
- Own inline ESPN scraping via urllib (duplicating proper `api_clients/` infrastructure)
- Regex parsing of JS-rendered HTML (broken for every site)
- Dead `UnifiedAPIClient` integration (never returned data)
- The WORKING API client infrastructure (`scripts/api_clients/` + `scripts/fetch_api_stats.py`) existed but sat UNUSED

### Solution: Complete Rewrite (1715 → ~800 lines)
**Architecture:** Thin orchestrator delegating to established API client fallback chains.
- Imports `fetch_team_stats()`, `fetch_h2h_stats()`, `_store_in_cache()` from `fetch_api_stats.py`
- Uses `get_client()` + `RateLimiter` from `scripts/api_clients/`
- Flashscore via `curl_cffi` as last-resort fallback only
- Concurrent batch enrichment via `ThreadPoolExecutor(max_workers=4)`

### Key Design Patterns
1. **Circuit Breaker** — per-source with half-open window (60s). 5 consecutive failures → DOWN. Auto-retries after 60s.
2. **Known-Missing Cache** — `known_missing_teams.json` with 7-day TTL. Thread-safe (dedicated lock).
3. **FALLBACK_CHAINS** per sport: ESPN → sport-specific API → Google Sports → SerpAPI → Flashscore (curl_cffi)
4. **Range Validation** — `SPORT_VALUE_RANGES` dict validates stat values before DB write (prevents garbage)

### Tennis Fix: ESPN Search API for Player Resolution
**Problem:** `_resolve_athlete_id()` in `src/bet/api_clients/espn.py` only scanned TODAY's scoreboard. If player not playing today → ID resolution fails → 100% enrichment failure for tennis.
**Fix:** Added ESPN Web Search API as primary resolution method:
```
GET https://site.web.api.espn.com/apis/common/v3/search?query=Carlos+Alcaraz&type=player&sport=tennis&limit=10
```
Returns player ID regardless of whether they're playing today. Scoreboard scanning kept as fallback.

### Tennis Data Available from ESPN (FREE)
- ✅ sets_won, total_sets, games_won, total_games, ranking (from linescores)
- ❌ aces, double_faults, first_serve_pct, break_points_won (requires premium API)
- For our betting markets (total games, total sets) the available data is sufficient.

### Scoreboard Scan Improvement
Changed from step-3 (0, 3, 6, 9...) to daily-recent + step-3-historical:
```python
days = list(range(0, 7)) + list(range(9, 46, 3))  # days 0-6 daily, then 9-45 step-3
```
Prevents missing matches from yesterday/day-before.

### Dead Code Cleaned (7 files deleted)
- `scripts/sofascore_enricher.py` — zero callers
- `scripts/generate_coupon_pdf_detailed.py` — hardcoded date, zero callers
- `scripts/test_google_direct.py`, `test_google_playwright.py`, `test_google_sports_live.py`, `test_serpapi_comprehensive.py`, `test_serpapi_vs_query.py` — dev throwaways

### Still Existing Legacy (tracked, not blocking)
- `src/bet/api_clients/unified.py` — dead export, zero runtime callers
- Dual `api_clients/` directories (`src/bet/api_clients/` vs `scripts/api_clients/`) — structural duplicate, needs consolidation plan
- `fetch_api_stats.py` — marked "LEGACY" in agent_protocol but still imported as library by `data_enrichment_agent.py`

### Live Test Results (2026-05-18)
| Sport | Test Team | Result | Keys | Time |
|-------|-----------|--------|------|------|
| Football | Manchester City | enriched | 29 | 1.1s |
| Basketball | (from earlier) | enriched | 18 | 1.4s |
| Hockey | (from earlier) | enriched | 15 | 1.5s |
| Tennis | Carlos Alcaraz | partial | 5 (sets/games/ranking) | 15s |
| Tennis | Jannik Sinner | partial | 5 | 5s |
| Tennis | Novak Djokovic | partial | 5 | 6s |

## 🆕 ENRICHMENT: PLAYWRIGHT FULLY REMOVED, CURL_CFFI ONLY — 2026-05-18

### Problem (original)
`enrich_h2h()` used fake URL pattern `flashscore.com/h2h/{team_a}/{team_b}/` which does NOT exist on Flashscore → 100% 404s. Each 404 triggered Playwright fallback via `fetch()` → saturated rate limiter (10/10) → blocked ALL other Playwright enrichment.

Additionally, `web_research_agent.py` had flashscore.com URLs with guessed slugs (no entity ID) for injuries/form/coach — all guaranteed failures wasting the daily counter.

### Fix Applied (2 phases)
**Phase 1:** Flashscore-specific (early 2026-05-18)
1. `_PLAYWRIGHT_BLOCKED_DOMAINS` added — flashscore.com domains blocked from Playwright fallback
2. `enrich_h2h()` rewritten with curl_cffi entity resolution
3. `web_research_agent.py` purged of flashscore URLs

**Phase 2:** Complete Playwright removal from enrichment (2026-05-18)
4. **`_fetch_stealth()` rewritten** — 70-line Playwright+stealth+greenlet code replaced with 30-line `curl_cffi.requests.get(impersonate="chrome110")` with 2-attempt retry
5. **`fetch()` fallback** — now uses curl_cffi stealth instead of Playwright browser for 403/429
6. **Thread safety** — curl_cffi is thread-safe (no greenlet conflicts), enables full parallel enrichment
7. **Eliminated** — `playwright.sync_api`, `playwright_stealth` imports, all thread/asyncio guards

### Rule: Enrichment Access (PERMANENT)
- **Flashscore:** ONLY `curl_cffi` with `impersonate="chrome110"` — via `flashscore_enricher.py`
- **All domains in enrichment:** `_fetch_stealth()` uses `curl_cffi` (NOT Playwright)
- **NEVER** Playwright for ANY enrichment fetch (data_enrichment_agent.py is Playwright-free)
- **Playwright still used by:** `daily_odds_warmup.py`, `tipster_aggregator.py`, `SoccerwayClient`, `OddsPortalClient` (separate subsystems)
- **Correct Flashscore URL:** `https://www.flashscore.com/{entity_type}/{slug}/{entity_id}/results/`
- **Search API:** `https://s.flashscore.com/search/?q={team}&l=1&sid={sport_id}&pid=1&f=1;1` (header: `x-fsign: SW9D1eZo`)
- **DOES NOT EXIST:** `/h2h/`, `/team/{guessed-slug}/` (without entity_id)

## 🆕 GOOGLE SPORTS H2H CLIENT (SerpAPI) — 2026-05-18

### What
New dedicated H2H enrichment source: `scripts/api_clients/google_sports_client.py`. Uses SerpAPI to query Google Knowledge Panels via "Team A vs Team B" — returns structured H2H data for ALL 5 sports.

### Data Extracted Per Sport
- **Football/Hockey/Basketball:** H2H match scores, tournament, venue, red cards, dates, KGMIDs
- **Tennis:** Set scores per set, player rankings, tournament stage, winner
- **Live matches:** Goal scorers with player name, jersey #, minute + stoppage time

### DB Integration (3 tables written)
| Table | Data | Key |
|-------|------|-----|
| `fixtures` | Each H2H match (scores, teams, comp) | `(sport_id, home_team_id, away_team_id, kickoff)` |
| `team_form` | `goals_scored` (team sports) / `sets_won` (tennis) with `h2h_opponent_id` set | `(team_id, stat_key, h2h_opponent_id)` |
| `match_stats` | Red cards per team per fixture | `(fixture_id, team_id, stat_key)` |

### Pipeline Integration
- **Fallback chain position:** L3.5 — after sport-specific APIs, before web research
- **FALLBACK_CHAINS** in `fetch_api_stats.py`: added "google-sports" to all 5 sports
- **Registry:** `CLIENT_REGISTRY["google-sports"] = GoogleSportsClient` in `api_clients/__init__.py`
- **agent_protocol.py:** Added to `SELF_HEALING_REGISTRY` + fallback layers list

### Key Design Decisions
1. **Overwrite protection:** Won't overwrite existing H2H data if existing has ≥ same count of meetings (prevents 2-meeting google data from replacing 5-10 meeting Flashscore data)
2. **Team-identity tracking:** Goals tracked BY TEAM across meetings, not by home/away slot (critical for correctness when teams swap home/away)
3. **Budget:** 15 queries per pipeline run, 250/month SerpAPI free tier, 48h file cache
4. **Source-registry.md:** Full entry added under "Tier A Core Stats — API Sources"

### How Pipeline Reads This Data
`normalize_stats.py` → `build_safety_input_from_db()` queries:
```sql
SELECT * FROM team_form WHERE team_id = ? AND sport_id = ? AND h2h_opponent_id = ?
```
Then reads `h2h_values` JSON array for three-way cross-check (L10 + H2H + L5) in safety score computation.

## 🆕 DATA FLOW AUDIT + GARBAGE CLEANUP — 2026-05-18

### Full Pipeline Data Flow (verified):
```
S1 discover_events.py → DB: fixtures, fixture_sources, scan_results, teams, competitions, sports
S2 data_enrichment_agent.py → DB: team_form (L10/L5/H2H), injuries + JSON stats_cache
S2.5 build_shortlist.py → JSON: {date}_s2_shortlist.json (reads DB fixtures + odds)
S3 deep_stats_report.py → DB: analysis_results, analysis_raw_data (reads team_form, H2H, injuries, standings, tipsters)
S7 gate_checker.py → DB: gate_results (reads analysis_results, fixtures, 48h ledger)
S8 coupon_builder.py → DB: coupons + bets, MD: coupon file (reads gate_results APPROVED)
```

### Data Quality Issues Found & Fixed:
**CRITICAL — Garbage values in team_form (source: enrichment-agent):**
- football/corners max=989 (should be 0-20): 38 garbage rows
- football/fouls max=989 (should be 0-35): 38 garbage rows
- football/goals max=211 (should be 0-12): 146 garbage rows
- football/possession max=989 (should be 0-80): 10 garbage rows
- football/red_cards max=989 (should be 0-4): 50 garbage rows
- tennis/total_games with values <10: ~100+ rows (sets, not games)
- volleyball/aces with values 160-210: ~20 rows (season totals, not per-match)
- **Total:** 281 rows for deletion, 241 rows for update

**Root cause:** Non-Flashscore enrichment paths (UnifiedAPIClient, ESPN) bypassed `_validate_stat_values()` range check. Season totals saved as per-match values.

**Fixes applied:**
1. `data_enrichment_agent.py` line 787: Added `SPORT_VALUE_RANGES` validation in `_save_to_db()` BEFORE any DB write
2. `scripts/clean_garbage_team_form.py`: Cleanup script (--dry-run, --verbose, AGENT_SUMMARY)

### Current Data Volumes (2026-05-18):
- team_form: 207,876 rows (434 updated today), 47,234 H2H records
- fixtures: scan today = football:1786, basketball:518, tennis:389, volleyball:50, hockey:34
- analysis_results: 360, gate_results: 197 APPROVED / 3 REJECTED
- tipster_consensus: football:583, basketball:99, hockey:94, tennis:88
- 14 sports in DB (5 core tier-1 + 9 tier-2)

### Agent Analysis Capabilities (DB access):
- Agents access DB via `from bet.db.connection import get_db` + repository classes
- Key repos: SportRepo, TeamRepo, StatsRepo, FixtureRepo, OddsRepo, PipelineRepo, TipsterRepo
- team_form: L10/L5 match-by-match values + H2H stat-specific + trends
- analysis_results: ranking_json (per-market safety scores), three_way_check_json
- decision_outcomes: historical results for learning (sport×market patterns)
- Agents combine quantitative (safety scores, hit rates) with qualitative (tipster reasoning, injuries) — this is their UNIQUE VALUE vs scripts

### Report: `betting/reports/pipeline-data-flow-audit.md`

## 🆕 AGENT/PROMPT ALIGNMENT AUDIT — 2026-05-17

Cross-cutting audit of 17 `.github/` files + 1 source fix + 1 memory fix to align all agents, prompts, instructions, and skills with 4 recent code changes.

### Changes Applied (19 files total)
| Category | Files Changed | What |
|----------|--------------|------|
| `--top 200` removal | bet-orchestrator.agent.md, orchestrate-betting-day.prompt.md, bet-deep-stats.prompt.md | Removed hardcoded `--top 200`; defaults to all candidates |
| `scrapers%` heuristic | bet-enricher.agent.md, bet-enrich.prompt.md | Replaced wrong `source LIKE 'scrapers%'` with correct `scraper_runs`+`player_season_stats`/`league_profiles` checks |
| 28→30 tables / 6→7 domains | copilot-instructions.md, bet-orchestrator.agent.md, bet-db-analyst.agent.md, orchestrate-betting-day.prompt.md, ask-betting.prompt.md, bet-db-quality.prompt.md, bet-querying-database/SKILL.md, project-structure.md | Added Tipster domain (`tipster_picks`, `tipster_consensus`) |
| sqlite3.connect examples | agent-execution-protocol.instructions.md, bet-enrich.prompt.md, bet-db-quality.prompt.md | All code examples now use `get_db()` pattern |
| Tipster DB-first | bet-scout.agent.md, orchestrate-betting-day.prompt.md, bet-tipsters.prompt.md, analysis-methodology.instructions.md, bet-navigating-sources/SKILL.md | Playwright sequential (10 sites), TipsterRepo, `--use-gemini` |
| DB lock docs | bet-enricher.agent.md | Full SQLite Lock-Fix Architecture section (busy_timeout, retry_on_lock, _db_write_lock) |
| Odds/portfolio | bet-odds-ev.prompt.md, bet-portfolio.prompt.md | DB-first context, removed stale `--input` flag |
| Code fix | repositories.py | `r[14]` → `r["tipster_sources"]` (named dict access, M1 completion) |

### Verification
- Final grep: zero remaining stale references (`--top 200`, `28 tables`, `6 domains`, `12 sites`)
- All `sqlite3.connect` mentions are in "NEVER do this" warnings only
- Tests: 676 passed, 5 pre-existing failures (unrelated)

## 🆕 TIPSTER PLAYWRIGHT REWRITE + DB-FIRST — 2026-05-17

**Plan:** `specifications/tipster-playwright-db-migration.plan.md` — 5 phases.

### Tipster Fetching: requests.get() → Playwright DOM Scraping
- **tipster_aggregator.py:** Replaced plain `requests.get()` (returned garbage HTML from JS-rendered sites) with `TipsterPlaywrightClient` (extends `PlaywrightBaseClient`). Sites now rendered with headless Chromium + stealth mode.
- **TipsterPlaywrightClient:** `src/bet/api_clients/tipster_playwright.py` — site-specific JavaScript DOM extraction via `page.evaluate()`. Extractors for: ZawodTyper (structural IDs), PicksWise (__NEXT_DATA__), Sportsgambler (prediction links), Generic (semantic selectors). Deep reasoning extraction finds `.analysis`, `.reasoning`, `.expert-analysis` sections.
- **Sequential fetching:** Playwright is NOT thread-safe — when Playwright is active, sites are fetched sequentially (not ThreadPoolExecutor). HTTP fallback still uses parallel fetching.
- **HTTP fallback preserved:** If Playwright unavailable, falls back to `requests.get()` + regex parsers (existing behavior).

### Tipster DB Schema (v8 → v9)
- **schema.sql:** Added `tipster_picks` and `tipster_consensus` tables with proper indexes (date, teams, sport, source). Previously created dynamically via `_ensure_tipster_tables()`.
- **models.py:** Added `TipsterPick` and `TipsterConsensus` dataclasses.
- **repositories.py:** Added `TipsterRepo` with `save_picks`, `save_consensus`, `get_picks_by_date`, `get_consensus_by_date`, `get_picks_for_event`. All parameterized queries.
- **schema.py:** Bumped to v9 with migration for new indexes on existing tables.

### Pipeline DB-First Updates
- **tipster_aggregator.py:** Uses `TipsterRepo.save_picks()` + `TipsterRepo.save_consensus()` instead of raw SQL. Removed `_ensure_tipster_tables()`. Gemini picks now merged into `all_picks` (was dead variable — C1 fix). Sites already fetched by Gemini are skipped in Playwright pass.
- **tipster_xref.py:** Uses `TipsterRepo.get_picks_by_date()` instead of raw SQL. Exception logging added (was bare `except: pass`).
- **db_data_loader.py:** Added `load_tipster_picks_from_db(date)` and `load_tipster_consensus_from_db(date)`. Exception logging via `logging.debug()` (was bare `except: pass`).
- **agent_protocol.py:** Added `tipster_picks` and `tipster_consensus` to `DB_SCHEMA_REFERENCE`, updated `TipsterRepo` in repositories list, added tipster query patterns.
- **bet-scout.agent.md:** Updated with DB access patterns via TipsterRepo.

### Code Review Fixes Applied (same commit)
- **C1 (CRITICAL):** `gemini_picks` was dead variable — Gemini results were collected but never merged into `all_picks`. Fixed: `all_picks = list(gemini_picks)` + skip already-fetched sites.
- **M1 (MAJOR):** `TipsterRepo` used fragile positional `r[0]..r[18]` index access. Fixed: named `r["column_name"]` dict access (matches all other repos).
- **M2 (MAJOR):** `save_picks`/`save_consensus` used non-atomic DELETE + loop INSERT. Fixed: `with self.conn:` + `executemany` for rollback-safe bulk operations.
- **M3 (MAJOR):** `tipster_playwright.py` had entire class duplicated (1310→656 lines after fix).
- **M5/N3:** Bare `except: pass` in `tipster_xref.py` and `db_data_loader.py` now log the exception.
- **N1:** `stats_cited` non-list values now always serialized as `json.dumps([])` instead of raw string (was lost on read).
- **All SQL:** Parameterized queries verified. No string interpolation. JS extraction snippets are hardcoded constants (no injection risk).

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
