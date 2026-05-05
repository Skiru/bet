# Data Quality Improvements for Betting Pipeline — Implementation Plan

## Task Details

| Field            | Value                                                                        |
| ---------------- | ---------------------------------------------------------------------------- |
| Jira ID          | N/A                                                                          |
| Title            | Data Quality Improvements for Betting Pipeline                               |
| Description      | Address all data quality gaps identified in the field-level audit across 14 sports — missing stats, unconnected enrichment sources, and empty cache directories |
| Priority         | P0–P3 (phased)                                                               |
| Related Research | [data-quality-audit.research.md](data-quality-audit.research.md)             |

## Proposed Solution

The pipeline has robust infrastructure (18 adapters, 16 API clients, dual-write cache, Poisson probability engine) but suffers from **wiring gaps** — data is collected but never persisted, or enrichment steps exist but are never invoked. The solution prioritizes fixing existing wiring over building new infrastructure.

**Key architectural decisions:**

1. **ESPN-first for injuries** — ESPN already has `get_injuries()` implemented in `src/bet/api_clients/espn.py` but it's never called in the pipeline. Wire it up (FREE, unlimited) rather than burning API-Sports quota.
2. **Web scraping for tennis detailed stats** — ESPN tennis only returns sets/games. TennisExplorer match detail pages contain aces, double faults, first serve %, break points. Playwright is already configured for tennisexplorer.com. Scrape rather than use API-Tennis (100/day shared quota).
3. **Adapter data bridge** — Forebet probabilities, TotalCorner corner counts, Scores24 H2H/trends are already extracted into `scan_summary.json` but lost downstream. A new lightweight integrator script reads these and merges into stats cache.
4. **Elo persistence bridge** — TennisAbstract Elo data is parsed by the adapter into `structured_latest.json` (518 players with per-surface Elo). `probability_engine.py` already has `load_tennis_elo()` and `elo_adjusted_lambda()` functions. Just need a conversion step and a call site in `compute_safety_scores.py`.
5. **Budget-aware volleyball/handball fix** — These sports have working API clients (`api_volleyball.py`, `api_handball.py`) but the shared 100/day quota is consumed by football/basketball before volleyball gets a turn. Reserve minimum quota per Tier 1 sport.

```
Pipeline Data Flow (with new steps marked ★)
═══════════════════════════════════════════════

scan_events.py → adapters → scan_summary.json
                                    │
                    ★ adapter_data_integrator.py ── merges Forebet/TotalCorner/Scores24
                                    │               into stats_cache (Phase 6)
                                    ▼
discover_fixtures.py ──► fixture list
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
    fetch_api_stats.py   fetch_odds_multi.py  ★ fetch_injuries.py (Phase 3)
    (budget-reserved ★)       │               │  ESPN get_injuries() → cache
              │               ▼               ▼
              ▼          odds_history     injuries → stats_cache/{sport}/{team}.json
    stats_cache/                          │
    ★ tennis_elo_latest.json (Phase 4)    │
              │                           │
              ▼                           │
    ★ validate_data_quality.py (Phase 8)  │
              │                           │
              ▼                           ▼
    deep_stats_report.py ◄── reads injuries + elo + adapter data
              │
              ▼
    compute_safety_scores.py ★ + Elo adjustment for tennis (Phase 4)
              │
              ▼
    gate_checker.py ★ Gate #4 auto-passes when injury data exists (Phase 3)
```

## Current Implementation Analysis

### Already Implemented

- `src/bet/api_clients/espn.py` → `get_injuries()` method — `src/bet/api_clients/espn.py:901-927` — Returns team/player/status/type per league. FREE, unlimited. Covers football, basketball, hockey, baseball, tennis, MMA.
- `scripts/api_clients/espn_adapter.py` → `get_injuries()` wrapper — `scripts/api_clients/espn_adapter.py:248-256` — Multi-league injury fetch already adapted for pipeline use.
- `scripts/probability_engine.py` → Elo functions — `scripts/probability_engine.py:592-640` — `elo_win_probability()`, `elo_adjusted_lambda()`, `load_tennis_elo()` all implemented. Expects `tennis_elo_latest.json`.
- `scripts/adapters/tennisabstract_adapter.py` → Elo parser — `scripts/adapters/tennisabstract_adapter.py:1-120` — Parses ATP/WTA Elo tables including per-surface ratings. Output in `betting/data/tennisabstract.com/structured_latest.json` (518 players).
- `scripts/api_clients/api_volleyball.py` → Volleyball API client — `scripts/api_clients/api_volleyball.py:1-60` — Full CRUD: fixtures, stats, H2H. Shares 100/day API-Sports key.
- `scripts/api_clients/api_handball.py` → Handball API client — Same pattern as volleyball.
- `scripts/api_clients/api_tennis.py` → Tennis API client — `scripts/api_clients/api_tennis.py:1-60` — Has STAT_TYPE_MAP for aces, double_faults, first_serve_pct, break_points_won.
- `scripts/gate_checker.py` → `_check_injuries()` — `scripts/gate_checker.py:100-109` — Checks for `injuries`/`injury_data` keys in candidate. Returns True when data present.
- `scripts/deep_stats_report.py` → `_build_s35_coach()` — `scripts/deep_stats_report.py:428-459` — Reads `coach`/`manager`/`formation` from cache, outputs "verify manually" when missing.
- `scripts/adapters/scores24_adapter.py` → Detail page parser — `scripts/adapters/scores24_adapter.py:1-60` — Extracts H2H, form, trends, odds, venue from match detail pages.
- `scripts/adapters/forebet_adapter.py` → Prediction parser — `scripts/adapters/forebet_adapter.py:1-50` — Extracts `forebet_probs`, `forebet_prediction`, `forebet_score`.
- `scripts/adapters/totalcorner_adapter.py` → Corner data parser — `scripts/adapters/totalcorner_adapter.py:1-50` — Extracts `corner_count`, `corner_handicap`, total goals lines.
- `scripts/adapters/soccerstats_adapter.py` → Corner/card/foul averages — Per-team league averages for football stat markets.
- `scripts/api_clients/serpapi_client.py` → Knowledge graph extraction — `scripts/api_clients/serpapi_client.py:150-185` — Extracts `coach`, `venue`, `rank`, `standing` from Google knowledge graph.
- `scripts/build_stats_cache.py` → Dual-write pattern — `scripts/build_stats_cache.py:1-60` — JSON cache + SQLite `team_form` table. 24h TTL for form, 7d for H2H.
- `scripts/normalize_stats.py` → Sport market definitions — `scripts/normalize_stats.py:68-70` — Volleyball (7 stat keys), handball (6 stat keys), tennis (7 stat keys) all defined.
- `scripts/fetch_api_stats.py` → Fallback chains — `scripts/fetch_api_stats.py:46-63` — Per-sport ordered API chains. Volleyball: `["api-volleyball", "thesportsdb", "serpapi"]`.

### To Be Modified

- `scripts/fetch_api_stats.py` — Add budget reservation per Tier 1 sport (volleyball gets guaranteed API calls before football exhausts quota). Add ESPN volleyball to fallback chain if ESPN volleyball API works.
- `scripts/run_full_scan_and_prepare.sh` — Add new pipeline steps: injury fetch (after stats), Elo persistence (after scan), adapter data integration (after scan), data quality validation (after all enrichment).
- `scripts/compute_safety_scores.py` — Integrate Elo adjustment for tennis markets (call `elo_adjusted_lambda` when Elo data available).
- `scripts/build_stats_cache.py` — Add `injuries` key support in cache schema. Add `coach`/`manager` key support.
- `scripts/deep_stats_report.py` — Read injury data from cache for §S3.6 section. Read Elo ratings for tennis analysis.
- `scripts/aggregate_and_select.py` — Preserve adapter-specific fields (forebet_probs, corner_count, scores24 trends) during aggregation instead of dropping them.
- `src/bet/api_clients/espn.py` → `ESPN_LEAGUES` — Investigate adding volleyball league codes if ESPN volleyball API exists.
- `scripts/adapters/tennisexplorer_adapter.py` — Enhance to extract match-level stats (aces, DFs, first serve, break points) from detail pages.

### To Be Created

- `scripts/fetch_injuries.py` — New script: calls ESPN `get_injuries()` per sport/league, merges into stats cache per team, outputs `injuries_{date}.json` summary.
- `scripts/persist_tennis_elo.py` — New script: reads TennisAbstract `structured_latest.json`, converts to `{player_name: elo_rating, ...}` format, writes `tennis_elo_latest.json`.
- `scripts/adapter_data_integrator.py` — New script: reads `scan_summary.json`, extracts adapter-specific rich fields (Forebet probs, TotalCorner corners, Scores24 H2H/trends, SoccerStats averages), merges into stats cache.
- `scripts/validate_data_quality.py` — New script: runs after enrichment, produces coverage report showing populated vs. empty fields per sport.
- `scripts/fetch_tennis_detailed_stats.py` — New script: scrapes TennisExplorer match detail pages for aces, DFs, first serve %, break points; writes to tennis stats cache.
- `scripts/fetch_standings_multi.py` — New script: fetches league standings for basketball (ESPN), hockey (ESPN), volleyball (API-Volleyball) in addition to existing football (Football-Data.org).

## Open Questions

| #   | Question                                                                        | Answer                                                                                                                                  | Status      |
| --- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------- |
| 1   | Does ESPN have volleyball API endpoints?                                        | ESPN's public API has `/sports/volleyball` but coverage is NCAA-focused, not European club volleyball. Not useful for Betclic betting.  | ✅ Resolved |
| 2   | Can TennisExplorer match detail pages be scraped for aces/DFs reliably?         | Yes — TennisExplorer has match detail pages with "Match Stats" section containing aces, DFs, first serve %, break points. Playwright already configured for tennisexplorer.com. | ✅ Resolved |
| 3   | How to handle API-Sports 100/day quota across 7 sports?                         | Reserve minimum 15 calls per Tier 1 sport (volleyball, tennis, handball) before football/basketball use remainder. Implemented via budget allocation in rate limiter. | ✅ Resolved |
| 4   | Does Scores24 have tennis H2H on match detail pages?                            | Yes — Scores24 detail pages include H2H section for all sports including tennis. Already parsed by scores24_adapter.py.                 | ✅ Resolved |
| 5   | Which ESPN sports support the /injuries endpoint?                               | Football (all 36 leagues), basketball (NBA/WNBA), hockey (NHL), baseball (MLB). Tennis and MMA may not have injury endpoints.            | ✅ Resolved |

## Implementation Plan

### Phase 1: P0 — Volleyball Stats Enrichment

#### Task 1.1 — [MODIFY] Fix volleyball stats enrichment pipeline

**Agent**: `tsh-software-engineer`

**Description**: Investigate and fix why volleyball stats cache has 0 team files despite API-Volleyball client existing and fixtures being discovered. Root cause analysis: the shared 100/day API-Sports quota is consumed by football/basketball enrichment (which runs first in the parallel enrichment step) before volleyball gets a turn. The fix involves two changes:

1. In `scripts/fetch_api_stats.py`, modify the enrichment budget allocation to **reserve a minimum number of API calls per Tier 1 sport** before allowing any single sport to consume the remainder. Currently, sports are enriched by tier priority but within Tier 1, football consumes disproportionately due to having the most fixtures.

2. Add a `SPORT_BUDGET_RESERVE` dict that guarantees minimum API calls: `{"volleyball": 15, "tennis": 10, "handball": 10}`. The existing `enrich_fixture()` already handles rate limiting — just need to pre-allocate budget windows.

**Files affected**:
- `scripts/fetch_api_stats.py` — Add budget reservation logic in `_enrich_sport_group()` and the main orchestration function
- `scripts/api_clients/rate_limiter.py` — Add `reserve_budget(sport, count)` method if needed

**Definition of Done**:
- [ ] `fetch_api_stats.py` reserves minimum 15 API calls for volleyball before football exhausts the shared quota
- [ ] Running `python3 scripts/fetch_api_stats.py --date $(date +%Y-%m-%d) --sports volleyball` produces at least 1 team cache file in `betting/data/stats_cache/volleyball/`
- [ ] Existing football/basketball/hockey enrichment continues to work (no regression)
- [ ] Unit test added to `tests/test_fetch_api_stats.py` verifying budget reservation logic

#### Task 1.2 — [MODIFY] Add Sofascore API as free volleyball stats source

**Agent**: `tsh-software-engineer`

**Description**: Sofascore's public API (`api.sofascore.com`) provides volleyball match statistics for free without an API key. The existing `sofascore_adapter.py` only extracts fixture listings. Create a dedicated `SofascoreStatsClient` in `scripts/api_clients/` that hits the Sofascore statistics endpoint for volleyball matches (`/event/{id}/statistics`). Add this as the FIRST entry in volleyball's fallback chain (before api-volleyball) since it's free and doesn't consume the shared API-Sports quota.

**Files affected**:
- `scripts/api_clients/sofascore_stats.py` — [CREATE] New client for Sofascore statistics API
- `scripts/api_clients/__init__.py` — Register new client in `CLIENT_REGISTRY`
- `scripts/fetch_api_stats.py` — Add `"sofascore-volleyball"` as first entry in volleyball fallback chain

**Definition of Done**:
- [ ] `SofascoreStatsClient` implements `resolve_team_id()`, `get_team_last_fixtures()`, `get_fixture_stats()` returning `NormalizedMatchStats`
- [ ] Volleyball fallback chain becomes `["sofascore-volleyball", "api-volleyball", "thesportsdb", "serpapi"]`
- [ ] Client returns at least `points`, `aces`, `blocks`, `sets_won` stat keys for volleyball matches
- [ ] Rate limiting respects Sofascore's rate limits (max 1 req/sec)
- [ ] Unit test verifying stats normalization for volleyball stat keys

#### Task 1.3 — [CREATE] Volleyball enrichment integration test

**Agent**: `tsh-software-engineer`

**Description**: Add an integration test that runs the full volleyball enrichment flow: fixture discovery → stats fetch → cache write → safety score input building. Verify that the dual-write pattern (JSON + SQLite) works for volleyball and that `normalize_stats.VOLLEYBALL_MARKETS` can be evaluated against the cache data.

**Files affected**:
- `tests/test_volleyball_enrichment.py` — [CREATE] Integration test

**Definition of Done**:
- [ ] Test verifies volleyball team cache files are created with expected stat keys (`points`, `aces`, `blocks`, `attack_pct`, `sets_won`, `total_points`, `errors`)
- [ ] Test verifies `build_safety_score_input()` produces valid input for volleyball markets
- [ ] Test verifies dual-write to both JSON cache and SQLite `team_form` table
- [ ] Test can run with mocked API responses (no real API calls in CI)

---

### Phase 2: P0 — Tennis Stats Enhancement

#### Task 2.1 — [MODIFY] Enhance TennisExplorer adapter for match-level statistics

**Agent**: `tsh-software-engineer`

**Description**: The current `tennisexplorer_adapter.py` only extracts surface metadata from listing pages. Enhance it to also parse **match detail pages** which contain detailed match statistics: aces, double faults, first serve percentage, break points won/total. TennisExplorer match detail URLs follow the pattern `/match-detail/?id=XXXXXX` and contain a "Match Stats" table. Playwright is already configured for tennisexplorer.com with stored cookies.

The adapter should detect whether it's parsing a listing page or a detail page (based on URL pattern) and extract the appropriate data. Detail page stats should be returned as additional fields in the parsed result.

**Files affected**:
- `scripts/adapters/tennisexplorer_adapter.py` — Add detail page parsing logic with match stats extraction
- `scripts/site_selectors.json` — Add selectors for TennisExplorer match detail page stats table

**Definition of Done**:
- [ ] Adapter detects listing vs. detail page URLs and parses accordingly
- [ ] Detail page parsing extracts: `aces`, `double_faults`, `first_serve_pct`, `break_points_won` for both players
- [ ] Stats are returned in the standard `{stat_key: {home: N, away: N}}` format
- [ ] Unit test with sample TennisExplorer detail page HTML verifying stat extraction
- [ ] Graceful fallback to surface-only extraction if stats table is missing

#### Task 2.2 — [CREATE] Tennis detailed stats enrichment script

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/fetch_tennis_detailed_stats.py` — a new enrichment step that fetches detailed tennis match statistics by scraping TennisExplorer match detail pages via Playwright. For each tennis player in the stats cache, find their recent matches on TennisExplorer and scrape the match stats (aces, DFs, first serve %, break points). Merge into the existing tennis stats cache alongside the ESPN sets/games data.

This script should:
1. Read existing tennis cache files to get player names
2. For each player, construct TennisExplorer search URL
3. Fetch recent match detail pages (up to 10 most recent)
4. Extract detailed stats from each match
5. Merge stats into existing cache entries (preserving ESPN data, adding new keys)
6. Dual-write to JSON cache + SQLite

**Files affected**:
- `scripts/fetch_tennis_detailed_stats.py` — [CREATE] New enrichment script
- `scripts/run_full_scan_and_prepare.sh` — Add as new pipeline step after fetch_api_stats.py

**Definition of Done**:
- [ ] Script fetches aces, double_faults, first_serve_pct, break_points_won for tennis players
- [ ] Merges with existing ESPN data (sets_won, games_won, total_sets) without overwriting
- [ ] Tennis cache files contain all 7 defined stat keys after enrichment
- [ ] Dual-write to JSON + SQLite maintained
- [ ] Integrated into `run_full_scan_and_prepare.sh` as step between stats fetch and analysis
- [ ] Rate-limited to max 1 request/second to TennisExplorer
- [ ] Handles Playwright failures gracefully (logs error, continues with next player)

#### Task 2.3 — [CREATE] Tennis H2H data collection

**Agent**: `tsh-software-engineer`

**Description**: Tennis cache files have empty `h2h: {}` because ESPN tennis doesn't provide H2H data. Implement H2H collection using two sources:

1. **Scores24 match detail pages** — Already parsed by `scores24_adapter.py`, which extracts H2H records from detail pages. The data exists in `scan_summary.json` for tennis matches but isn't routed to the stats cache.
2. **TennisExplorer H2H pages** — TennisExplorer has `/h2h/?id1=X&id2=Y` pages showing head-to-head records with match scores.

Modify `scripts/fetch_tennis_detailed_stats.py` (from Task 2.2) to also collect H2H data when two tennis players are scheduled to play. Use Scores24 data first (already parsed), fall back to TennisExplorer scraping.

**Files affected**:
- `scripts/fetch_tennis_detailed_stats.py` — Add H2H collection logic
- `scripts/build_stats_cache.py` — Ensure H2H merge works for tennis (player-based, not team-based)

**Definition of Done**:
- [ ] Tennis H2H data populated in cache for players with scheduled matches
- [ ] H2H includes match scores and date (enough to compute per-stat H2H values)
- [ ] `compute_safety_scores.py` receives non-empty `h2h_values` for tennis markets when H2H data exists
- [ ] Three-way cross-check (L10 + H2H + L5) works for tennis when H2H is available
- [ ] Unit test verifying H2H merge into tennis cache structure

---

### Phase 3: P1 — Injury/Suspension Data Collection

#### Task 3.1 — [CREATE] Injury data fetching script

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/fetch_injuries.py` — a new pipeline step that collects injury/suspension data from ESPN's `/injuries` endpoint. ESPN's `get_injuries()` method is already implemented in both `src/bet/api_clients/espn.py:901-927` and wrapped in `scripts/api_clients/espn_adapter.py:248-256`. This script needs to:

1. For each ESPN-supported sport (football, basketball, hockey, baseball): iterate through configured leagues and call `get_injuries()`
2. Group injuries by team
3. For each team with active injuries, write the injury list to that team's stats cache file under an `injuries` key
4. Output a summary JSON file `injuries_{date}.json` with counts per sport/team

**Files affected**:
- `scripts/fetch_injuries.py` — [CREATE] New script
- `scripts/run_full_scan_and_prepare.sh` — Add as new pipeline step (parallel with stats/odds fetch)

**Definition of Done**:
- [ ] Script calls ESPN `get_injuries()` for football (36 leagues), basketball (NBA/WNBA), hockey (NHL), baseball (MLB)
- [ ] Injuries are stored in stats cache: `stats_cache/{sport}/{team_slug}.json` → `injuries: [{player, status, type}, ...]`
- [ ] Summary file `betting/data/injuries_{date}.json` lists all injuries by sport/team
- [ ] Dual-write to SQLite if DB is available (new column or JSON field in `team_form` table)
- [ ] Integrated into `run_full_scan_and_prepare.sh` parallel enrichment step (alongside fetch_api_stats and fetch_odds_multi)
- [ ] ESPN rate limits respected (free, unlimited, but polite 1 req/sec)
- [ ] Unit test with mocked ESPN injury response

#### Task 3.2 — [MODIFY] Wire injury data into analysis pipeline

**Agent**: `tsh-software-engineer`

**Description**: Now that injury data exists in the stats cache, wire it into the downstream consumers:

1. `scripts/deep_stats_report.py` — §S3.6 currently always shows "No injury data in cache — verify on Flashscore/Sofascore". Modify to read the `injuries` key from cache and display actual injury lists when available.
2. `scripts/gate_checker.py` — Gate #4 (`_check_injuries`) currently always fails. The check already looks for `injuries`/`injury_data` keys. Ensure the candidate object passed to gate_checker includes the injury data from the cache.
3. The bridge between cache and candidate: identify where candidates are built (likely in `pipeline_orchestrator.py` or `deep_analysis_pool.py`) and ensure injury data from cache is included in the candidate dict.

**Files affected**:
- `scripts/deep_stats_report.py` — Modify `_build_s36_injuries()` (or similar) to read cache injuries
- `scripts/gate_checker.py` — No code change needed if candidate includes `injuries` key (verify)
- `scripts/deep_analysis_pool.py` — Ensure injury data is propagated to candidate objects

**Definition of Done**:
- [ ] `deep_stats_report.py` §S3.6 section displays actual injury list when data exists in cache
- [ ] `gate_checker.py` Gate #4 auto-passes when injury data is present in the candidate
- [ ] Candidates without injury data (niche sports) still fall through to manual check path
- [ ] No false positives — Gate #4 does NOT auto-pass with empty injury lists (team has no injuries = data exists but empty = passes correctly)
- [ ] Integration test verifying Gate #4 passes with ESPN-sourced injury data

---

### Phase 4: P1 — TennisAbstract Elo Integration

#### Task 4.1 — [CREATE] Tennis Elo persistence script

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/persist_tennis_elo.py` — reads the TennisAbstract adapter output from `betting/data/tennisabstract.com/structured_latest.json` (518 ATP + WTA players with Elo ratings) and converts it to the format expected by `probability_engine.load_tennis_elo()`:

```json
{
  "Jannik Sinner": {"elo": 2331.1, "hard_elo": 2268.9, "clay_elo": 2222.5, "grass_elo": 2094.0},
  "Carlos Alcaraz": {"elo": 2280.5, ...},
  ...
}
```

Output: `betting/data/tennis_elo_latest.json` (and date-specific `tennis_elo_{date}.json`)

This is a lightweight conversion — the heavy lifting (HTML parsing) is already done by the adapter.

**Files affected**:
- `scripts/persist_tennis_elo.py` — [CREATE] Conversion script
- `scripts/run_full_scan_and_prepare.sh` — Add after scan step (before analysis)

**Definition of Done**:
- [ ] Script reads `structured_latest.json` and writes `tennis_elo_latest.json` in the format `load_tennis_elo()` expects
- [ ] Both ATP and WTA players included (keyed by player display name)
- [ ] Per-surface Elo ratings (hard_elo, clay_elo, grass_elo) preserved
- [ ] `probability_engine.load_tennis_elo()` returns non-empty dict after this script runs
- [ ] Date-specific snapshot `tennis_elo_{date}.json` also written for historical tracking
- [ ] Integrated into `run_full_scan_and_prepare.sh` after scan (step 5.5 or similar)

#### Task 4.2 — [MODIFY] Integrate Elo into tennis safety score computation

**Agent**: `tsh-software-engineer`

**Description**: The probability engine has `elo_adjusted_lambda()` and `elo_win_probability()` but they're never called from the safety score pipeline. Integrate Elo data into tennis market evaluation:

1. In `scripts/compute_safety_scores.py` — when computing safety scores for tennis markets, load Elo data and use `elo_adjusted_lambda()` to adjust the Poisson λ parameter. This improves accuracy for games/sets totals markets.
2. In `scripts/deep_stats_report.py` — add Elo rating display in the tennis analysis header (§S3.1 or §S3.2 section).

The integration should be **additive** — if Elo data is missing for a player, the existing L10/L5-only calculation continues unchanged.

**Files affected**:
- `scripts/compute_safety_scores.py` — Add Elo adjustment in `rank_markets()` for tennis
- `scripts/deep_stats_report.py` — Display Elo ratings in tennis reports
- `scripts/probability_engine.py` — No changes needed (functions already exist)

**Definition of Done**:
- [ ] Tennis safety scores incorporate Elo adjustment when Elo data is available
- [ ] Surface-specific Elo used when surface is known (clay_elo for clay matches, etc.)
- [ ] Safety scores are unchanged for non-tennis sports (no regression)
- [ ] Safety scores are unchanged for tennis players without Elo data (graceful degradation)
- [ ] Deep stats report shows Elo rating in tennis match headers
- [ ] Unit test verifying Elo adjustment produces different (better) λ values

---

### Phase 5: P1 — Handball Stats Enrichment

#### Task 5.1 — [MODIFY] Fix handball stats enrichment (mirror volleyball fix)

**Agent**: `tsh-software-engineer`

**Description**: Handball has the same problem as volleyball — API-Handball client exists but the shared 100/day quota is consumed by higher-priority sports. Apply the same budget reservation fix from Task 1.1 to handball, and add Sofascore handball stats as a free alternative source (same pattern as Task 1.2 for volleyball).

**Files affected**:
- `scripts/fetch_api_stats.py` — Handball budget reservation (10 calls minimum) already part of Task 1.1's `SPORT_BUDGET_RESERVE`
- `scripts/api_clients/sofascore_stats.py` — Extend to support handball (add sport parameter, handball stat normalization)
- `scripts/fetch_api_stats.py` — Add `"sofascore-handball"` to handball fallback chain

**Definition of Done**:
- [ ] Handball fallback chain becomes `["sofascore-handball", "api-handball", "thesportsdb", "serpapi"]`
- [ ] Running `fetch_api_stats.py --sports handball` produces team cache files with stat keys: `goals`, `saves`, `turnovers`, `penalties`, `total_goals`
- [ ] Budget reservation ensures handball gets at least 10 API-Sports calls per day
- [ ] Dual-write to JSON + SQLite maintained for handball
- [ ] Integration test verifying handball cache population

---

### Phase 6: P2 — Adapter Data Integration

#### Task 6.1 — [CREATE] Adapter data integrator script

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/adapter_data_integrator.py` — reads `scan_summary.json` and extracts adapter-specific rich fields that are currently lost downstream. For each matched fixture, merges the supplementary data into the corresponding team's stats cache file under a new `adapter_data` key.

Data to extract and integrate:
- **Forebet**: `forebet_probs` (home/draw/away %), `forebet_prediction`, `forebet_score`, `forebet_avg`
- **TotalCorner**: `corner_count`, `corner_handicap`, `total_goals_line`
- **SoccerStats**: `stats` (team corner/card/foul league averages)
- **Scores24**: `h2h`, `form_home`, `form_away`, `trends`, `odds` (from detail pages)

The script should:
1. Read `scan_summary.json` and iterate over all URLs
2. For each parsed result with rich adapter fields, identify the teams
3. Match teams to existing stats cache files (using slugify + fuzzy matching)
4. Merge adapter data under `adapter_data.{source}` namespace in the cache file

**Files affected**:
- `scripts/adapter_data_integrator.py` — [CREATE] New script
- `scripts/run_full_scan_and_prepare.sh` — Add after scan step, before analysis

**Definition of Done**:
- [ ] Script reads scan_summary.json and extracts Forebet, TotalCorner, SoccerStats, Scores24 rich fields
- [ ] Adapter data merged into stats cache under `adapter_data.{source_name}` namespace
- [ ] Team name matching uses existing `slugify()` + fuzzy match with SequenceMatcher (threshold 0.85)
- [ ] Cache TTL respected — adapter data refreshed on each pipeline run
- [ ] Does not overwrite core form/l10/l5 data — additive only
- [ ] Unit test with sample scan_summary.json data verifying integration

#### Task 6.2 — [MODIFY] Feed adapter data into safety score pipeline

**Agent**: `tsh-software-engineer`

**Description**: Now that adapter data is in the stats cache, integrate it into the safety score computation:

1. **Forebet probabilities** — Use as a cross-validation source. If Forebet's predicted probability diverges >15% from Poisson model, flag in the report as a confidence check.
2. **TotalCorner corner data** — Use live/historical corner counts as supplementary data for football corner markets. Feed into `compute_safety_scores.py` as an additional data point for corner market hit rate estimation.
3. **SoccerStats league averages** — Use as league baseline for football corner/card/foul markets. Compare team L10 to league average to identify above/below-average teams.

**Files affected**:
- `scripts/compute_safety_scores.py` — Add optional `adapter_data` parameter to `rank_markets()`, use for cross-validation
- `scripts/deep_stats_report.py` — Display adapter supplementary data (Forebet probs, corner counts) in relevant sections
- `scripts/normalize_stats.py` — Add helper to extract adapter data from cache and format for safety score input

**Definition of Done**:
- [ ] Forebet probability shown as cross-validation in deep stats report when available
- [ ] TotalCorner corner counts integrated as supplementary data for football corner markets
- [ ] SoccerStats league averages shown as context for football stat markets
- [ ] Safety score computation is additive — works identically when adapter data is absent
- [ ] No new mandatory fields in safety score input schema
- [ ] Unit test verifying adapter data integration with and without data present

---

### Phase 7: P2 — Coach/Manager Data Collection

#### Task 7.1 — [MODIFY] Parse and persist SerpAPI coach data

**Agent**: `tsh-software-engineer`

**Description**: SerpAPI's Google knowledge graph sometimes returns `coach` attribute when querying team names. The data is already extracted in `serpapi_client.py` → `search_team_stats()` → `attributes` dict but never written to the stats cache. Modify the cache write path to persist coach data when available.

Additionally, create a lightweight `fetch_coach_data.py` script that proactively queries SerpAPI for coach info for teams in today's fixtures. Given SerpAPI's 250/month limit (~8/day), only query for Tier 1 football teams that don't already have coach data cached.

**Files affected**:
- `scripts/fetch_api_stats.py` — When SerpAPI is in the fallback chain and returns `knowledge_graph.coach`, persist to cache
- `scripts/build_stats_cache.py` — Add `coach` and `manager` key support in cache update logic
- `scripts/fetch_coach_data.py` — [CREATE] Lightweight script for proactive coach queries (SerpAPI budget-aware)

**Definition of Done**:
- [ ] Coach data from SerpAPI knowledge_graph persisted in stats cache under `coach` key
- [ ] `deep_stats_report.py` §S3.5 displays actual coach name when available
- [ ] `fetch_coach_data.py` respects SerpAPI 250/month limit (max 5 queries per pipeline run)
- [ ] Cache TTL for coach data: 30 days (coaches don't change often)
- [ ] Existing enrichment flow unchanged — coach data is opportunistic addition

---

### Phase 8: P3 — Data Quality Validation

#### Task 8.1 — [CREATE] Data quality validation script

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/validate_data_quality.py` — runs after all enrichment steps and produces a data quality report showing coverage gaps per sport. This gives the user visibility into what's actually populated before analysis starts.

Report sections:
1. **Per-sport coverage matrix**: For each of the 14 sports, show: # team cache files, # stat keys populated (avg), H2H coverage %, injury data %, Elo data (tennis only)
2. **Critical gaps alert**: Highlight any Tier 1 sport with <5 cache files or <3 stat keys
3. **API budget usage**: Show remaining API-Sports quota, ESPN request count, SerpAPI usage
4. **Adapter data coverage**: How many fixtures have Forebet/TotalCorner/Scores24 supplementary data
5. **Comparison to yesterday**: Show delta (more/fewer cache files, new stats keys)

Output: `betting/data/data_quality_{date}.json` + `betting/data/data_quality_{date}.md` (human-readable)

**Files affected**:
- `scripts/validate_data_quality.py` — [CREATE] New script
- `scripts/run_full_scan_and_prepare.sh` — Add as final validation step before analysis

**Definition of Done**:
- [ ] Script produces JSON + markdown reports covering all 14 sports
- [ ] Critical gaps (Tier 1 sport with 0 cache files) prominently flagged
- [ ] API budget usage section shows remaining daily quota
- [ ] Report is non-blocking — pipeline continues even if gaps exist
- [ ] Integrated into `run_full_scan_and_prepare.sh` as step between enrichment and analysis
- [ ] Unit test verifying report generation with sample cache data

---

### Phase 9: P3 — Niche Sport Web Scraping

#### Task 9.1 — [CREATE] Snooker stats scraper (CueTracker)

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/adapters/cuetracker_adapter.py` for scraping CueTracker.net match statistics. CueTracker provides frame-by-frame results and player statistics for snooker. Add this as a new scraping source in the scan URLs config and integrate into the snooker fallback chain.

Also create `scripts/adapters/dartsorakel_adapter.py` for DartsOrakel.com — provides darts match statistics (180s, checkouts, averages).

**Files affected**:
- `scripts/adapters/cuetracker_adapter.py` — [CREATE] CueTracker parser
- `scripts/adapters/dartsorakel_adapter.py` — [CREATE] DartsOrakel parser
- `scripts/adapters/__init__.py` — Register new adapters
- `config/scan_urls.json` — Add CueTracker and DartsOrakel URLs
- `scripts/fetch_api_stats.py` — Add `"cuetracker"` to snooker chain, `"dartsorakel"` to darts chain

**Definition of Done**:
- [ ] CueTracker adapter extracts frame scores, break building, century breaks for snooker matches
- [ ] DartsOrakel adapter extracts 180s, checkout percentages, averages for darts matches
- [ ] Adapters registered in `__init__.py` and URLs added to `scan_urls.json`
- [ ] Snooker fallback chain: `["cuetracker", "thesportsdb", "serpapi"]`
- [ ] Darts fallback chain: `["dartsorakel", "thesportsdb", "serpapi"]`
- [ ] Unit tests with sample HTML for each adapter

#### Task 9.2 — [MODIFY] Enhance HLTV adapter for CS2 match statistics

**Agent**: `tsh-software-engineer`

**Description**: The existing `hltv_adapter.py` extracts team names, format (BO1/3/5), and map names but no statistical data. HLTV match detail pages contain team statistics: K/D ratio, ADR (average damage per round), first kills, clutch wins, economy stats. Enhance the adapter to extract these stats from match detail pages.

**Files affected**:
- `scripts/adapters/hltv_adapter.py` — Add match detail page stat extraction
- `scripts/site_selectors.json` — Add HLTV match detail selectors
- `scripts/normalize_stats.py` — Verify esports stat keys cover K/D, ADR, etc.

**Definition of Done**:
- [ ] HLTV detail pages parsed for: kill_death_ratio, adr, first_kills, clutch_wins per team
- [ ] Stats returned in standard `{stat_key: {home: N, away: N}}` format
- [ ] Listing pages continue to work unchanged (backward compatible)
- [ ] Unit test with sample HLTV match detail HTML

---

### Phase 10: P3 — Standings & Venue Data

#### Task 10.1 — [CREATE] Multi-sport standings fetcher

**Agent**: `tsh-software-engineer`

**Description**: Create `scripts/fetch_standings_multi.py` to collect league standings for basketball (ESPN NBA/WNBA), hockey (ESPN NHL), and volleyball (API-Volleyball or Sofascore). Currently only `football_data_org.py` provides standings for 10 EU football leagues.

ESPN has standings endpoints for basketball and hockey (free, unlimited). For volleyball, use the API-Volleyball standings endpoint (budget-limited) or Sofascore standings API.

**Files affected**:
- `scripts/fetch_standings_multi.py` — [CREATE] Multi-sport standings fetcher
- `src/bet/api_clients/espn.py` — Verify/add `get_standings()` method if not already present
- `scripts/run_full_scan_and_prepare.sh` — Add as enrichment step (weekly, not daily)

**Definition of Done**:
- [ ] Standings fetched for NBA, WNBA, NHL via ESPN
- [ ] Standings fetched for at least 1 major volleyball league
- [ ] Output stored in `betting/data/standings_{sport}_{date}.json`
- [ ] Standings data available for contextual analysis (team position, playoff race, relegation zone)
- [ ] Run weekly (not daily) to conserve API budget

#### Task 10.2 — [MODIFY] Populate teams.venue from available sources

**Agent**: `tsh-software-engineer`

**Description**: The `teams.venue` column in SQLite exists but is never populated. Two sources already extract venue data:
1. **Scores24 detail pages** — `scores24_adapter.py` extracts `match_info.venue`
2. **SerpAPI knowledge_graph** — Sometimes contains `venue` or `arena` attributes

Modify the data flow to persist venue information when encountered:
1. In `adapter_data_integrator.py` (Task 6.1), when Scores24 data has venue info, write to the teams table
2. In `build_stats_cache.py`, add venue persistence to the DB dual-write

**Files affected**:
- `scripts/adapter_data_integrator.py` — Add venue extraction and DB persistence
- `scripts/build_stats_cache.py` — Add venue update in `_persist_to_db()` when venue data available

**Definition of Done**:
- [ ] Scores24 venue data persisted to `teams.venue` column in SQLite
- [ ] SerpAPI venue/arena data persisted when available
- [ ] Venue data does not overwrite if already populated (first-write-wins)
- [ ] Weather script can optionally use venue data for coordinate lookup (future enhancement)

---

### Phase 11: Code Review

#### Task 11.1 — [REUSE] Code review by `tsh-code-reviewer` agent

**Description**: Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` to review all changes across Phases 1–10. Focus areas:
- Backward compatibility — existing pipeline continues to work
- Rate limiting — all new API calls respect quotas
- Dual-write consistency — JSON cache and SQLite remain in sync
- Error handling — Playwright failures, API errors, missing data all handled gracefully
- Test coverage — all new scripts have unit tests, integration tests exist for critical paths

Run the full test suite: `python3 -m pytest tests/ -v`

**Definition of Done**:
- [ ] Code review passes or all findings addressed
- [ ] Full test suite passes (`pytest tests/ -v`)
- [ ] No regressions in existing pipeline (`bash scripts/run_full_scan_and_prepare.sh` completes successfully)
- [ ] Review report documented in Changelog

---

## Security Considerations

- **API keys**: New scripts must read API keys from `config/api_keys.json` (existing pattern), never hardcode credentials. SerpAPI key has 250/month limit — budget-aware scripts must check remaining quota before making requests.
- **Web scraping**: All Playwright-based scraping must use stored cookies from `scripts/playwright_storage/` and respect robots.txt. No aggressive scraping patterns (min 1 sec delay between requests).
- **Input validation**: Adapter parsers must sanitize HTML input (BeautifulSoup already handles this). Stats values must be validated as numeric before writing to cache/DB.
- **File path traversal**: `slugify()` function strips special characters. Verify no path traversal possible via malicious team names in API responses.
- **SQL injection**: All DB writes use parameterized queries via repository pattern (existing pattern in `src/bet/db/repositories.py`).

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] Volleyball stats cache contains ≥1 team file with ≥4 stat keys after a full pipeline run
- [ ] Tennis stats cache contains all 7 defined stat keys (sets_won, games_won, total_sets, aces, double_faults, first_serve_pct, break_points_won) for at least 10 players
- [ ] Tennis H2H data populated for ≥50% of tennis matches in today's fixtures
- [ ] Injury data available for all ESPN-supported sports (football, basketball, hockey, baseball)
- [ ] Gate #4 (injuries) auto-passes for matches in ESPN-supported sports
- [ ] Tennis Elo data loaded successfully for ≥500 ATP/WTA players
- [ ] Handball stats cache contains ≥1 team file with ≥3 stat keys
- [ ] Adapter data (Forebet/TotalCorner/Scores24) integrated for ≥50% of football fixtures
- [ ] Data quality report generated with correct coverage metrics
- [ ] All 14 sports appear in the data quality report (even if coverage is 0%)
- [ ] Full pipeline run (`run_full_scan_and_prepare.sh`) completes without errors
- [ ] `python3 -m pytest tests/ -v` passes with ≥95% of tests green
- [ ] No increase in API-Sports daily usage beyond 100/day shared limit
- [ ] JSON cache and SQLite DB remain in sync (spot-check 5 random teams)

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Player-level statistics** — All stats are team-aggregated. Per-player data (BallDontLie has it) would improve analysis but requires schema changes and significant refactoring.
- **Referee data collection** — No reliable free API provides referee assignments. Would require scraping Transfermarkt or similar.
- **Motivation/context scoring** — Automated detection of relegation battles, title races, cup elimination — requires a complex NLP pipeline or dedicated data source.
- **xG expansion beyond 6 EU leagues** — Understat only covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, RFPL. FBref has wider xG coverage but requires scraping.
- **Real-time odds streaming** — Current odds are snapshot-based. Real-time streaming would require WebSocket connections to odds providers.
- **Padel and speedway stats sources** — No viable free API or scrapable source identified for these sports.
- **teams.style_tags population** — Could be derived from statistical analysis (high possession = "possession-based", etc.) but adds complexity.

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-05-05 | Initial plan created |
