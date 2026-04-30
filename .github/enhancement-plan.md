# Betting Pipeline Enhancement — Implementation Plan

## Task Details

| Field            | Value                                                                 |
| ---------------- | --------------------------------------------------------------------- |
| Title            | Aggressive Scanning, Deep Analysis, No-Rejection, Enhanced Coupons    |
| Description      | Transform the betting pipeline from ~100 URL surface scan to 200+ URL deep-dive with tournament link following, all-sport market definitions, advisory-only thresholds, enriched tactical/weather data, and a Python orchestrator with state tracking. |
| Priority         | HIGH                                                                  |
| Related Research | `.github/multi-agent-architecture.plan.md` (existing agent layer)     |

## Proposed Solution

Enhance the betting pipeline at the **scripts and data layer** (complementing the existing multi-agent architecture) across 7 phases:

```
┌─────────────────────────────────────────────────────────────┐
│                    PIPELINE ORCHESTRATOR                     │
│  pipeline_orchestrator.py — state tracking, error recovery  │
├─────────────┬──────────────┬────────────────┬───────────────┤
│  PHASE 1    │   PHASE 2    │    PHASE 3     │   PHASE 4     │
│  Foundation │   Scanning   │    APIs        │   Analysis    │
│  ─────────  │   ─────────  │    ────        │   ────────    │
│  14-sport   │   Deep-link  │    Tennis API  │   Tactical    │
│  markets    │   following  │    Volley API  │   profiles    │
│  No-reject  │   200+ URLs  │    Handball    │   Weather     │
│  policy     │   New adapt. │    Baseball    │   Coach data  │
├─────────────┴──────────────┴────────────────┴───────────────┤
│             PHASE 5: Enhanced Market Matrix                  │
│  All-sport matrix, cross-sport correlations, full output     │
├─────────────────────────────────────────────────────────────┤
│             PHASE 6: Orchestrator & State Management         │
│  Python entry point, pipeline state, retry logic             │
├─────────────────────────────────────────────────────────────┤
│             PHASE 7: Methodology & Documentation Updates     │
└─────────────────────────────────────────────────────────────┘
```

## Current Implementation Analysis

### Already Implemented

- `scan_events.py` — URL fetching + adapter-based parsing → `scripts/scan_events.py`
- `discover_fixtures.py` — Multi-API fixture discovery (football, basketball, hockey) → `scripts/discover_fixtures.py`
- `fetch_api_stats.py` — L10 form + H2H via API clients → `scripts/fetch_api_stats.py`
- `deep_analysis_pool.py` — Safety score ranking for cached stats → `scripts/deep_analysis_pool.py`
- `compute_safety_scores.py` — §3.0 safety score calculator → `scripts/compute_safety_scores.py`
- `normalize_stats.py` — Market definitions for football, basketball, hockey → `scripts/normalize_stats.py`
- `generate_market_matrix.py` — Full market matrix (no auto-rejection) → `scripts/generate_market_matrix.py`
- `aggregate_and_select.py` — Candidate aggregation with price gap filters → `scripts/aggregate_and_select.py`
- `build_stats_cache.py` — Persistent stats cache with TTL → `scripts/build_stats_cache.py`
- `run_full_scan_and_prepare.sh` — 13-step bash orchestrator → `scripts/run_full_scan_and_prepare.sh`
- 6 adapters (flashscore, sofascore, betexplorer, oddsportal, betclic, raw) → `scripts/adapters/`
- 7 API clients (api-football, football-data-org, understat, api-basketball, api-hockey, balldontlie, thesportsdb) → `scripts/api_clients/`
- `validate_coupons.py` — Coupon structural integrity + arithmetic checks → `scripts/validate_coupons.py`

### To Be Modified

- `scripts/normalize_stats.py` — Add `SPORT_STAT_KEYS` and `SPORT_MARKETS` for all 14 sports (currently only football, basketball, hockey)
- `scripts/aggregate_and_select.py` — Make price gap thresholds advisory-only (currently filters/rejects)
- `scripts/compute_safety_scores.py` — Update `MIN_MARKETS` for new sport definitions
- `scripts/scan_events.py` — Add `--deep` mode for tournament link discovery and following
- `scripts/run_full_scan_and_prepare.sh` — Expand from ~85 to 200+ URLs covering more regions/leagues
- `scripts/discover_fixtures.py` — Register and query new API clients (tennis, volleyball, handball, baseball)
- `scripts/fetch_api_stats.py` — Extend `FALLBACK_CHAINS` with new API clients, add `TIER_1_SPORTS` entries
- `scripts/deep_analysis_pool.py` — Include tactical/weather enrichment data in output
- `scripts/build_stats_cache.py` — Extend cache schema for tactical profile, coach data, weather
- `scripts/generate_market_matrix.py` — Show ALL markets per sport, add correlation data
- `scripts/validate_coupons.py` — Support market terminology for all 14 sports
- `scripts/adapters/__init__.py` — Register new adapters (soccerway, tennisexplorer, soccerstats)
- `scripts/adapters/flashscore_adapter.py` — Extract tournament/league sub-links for deep scanning
- `scripts/api_clients/__init__.py` — Register new API clients
- `scripts/requirements.txt` — Add new dependencies (requests-cache, python-weather API client)

### To Be Created

- `scripts/api_clients/api_tennis.py` — API-Sports tennis client (fixtures + match stats)
- `scripts/api_clients/api_volleyball.py` — API-Sports volleyball client (fixtures + match stats)
- `scripts/api_clients/api_handball.py` — API-Sports handball client (fixtures + match stats)
- `scripts/api_clients/api_baseball.py` — API-Sports baseball client (fixtures + match stats)
- `scripts/adapters/soccerway_adapter.py` — Dedicated Soccerway HTML parser for exotic leagues
- `scripts/adapters/tennisexplorer_adapter.py` — TennisExplorer match/stats parser
- `scripts/adapters/soccerstats_adapter.py` — SoccerStats corner/card data parser
- `scripts/deep_link_discovery.py` — Generic deep-link follower for tournament sub-pages
- `scripts/fetch_tactical_profile.py` — Coach history, tactical tendencies scraper
- `scripts/fetch_weather.py` — Weather API integration for outdoor sport venues
- `scripts/cross_sport_correlation.py` — Cross-sport market correlation analysis
- `scripts/pipeline_orchestrator.py` — Python orchestrator with state tracking, error recovery
- `scripts/pipeline_state.py` — Pipeline state management (step status, retry counts)
- `tests/test_new_api_clients.py` — Tests for new API clients
- `tests/test_new_adapters.py` — Tests for new adapters
- `tests/test_deep_link_discovery.py` — Tests for deep-link following
- `tests/test_market_definitions.py` — Tests for all 14-sport market definitions
- `tests/test_pipeline_orchestrator.py` — Tests for orchestrator state management

## Open Questions

| #   | Question | Answer | Status |
| --- | -------- | ------ | ------ |
| 1   | Does the user's API-Sports subscription include tennis, volleyball, handball, baseball endpoints? | API-Sports uses the same key across all sport APIs. The free tier (100 req/day for football) may have different limits per sport. Need to verify. | ❓ Open |
| 2   | Should the deep-link following be parallel (faster) or sequential (safer for rate limiting)? | Recommend sequential with configurable delay (FETCH_DELAY_SECONDS already exists at 3s) and optional `--parallel N` flag for trusted sources. | ✅ Resolved |
| 3   | Should the Python orchestrator fully replace the bash script or wrap it? | Wrap it — bash script is battle-tested. Python orchestrator adds state tracking on top and can call individual steps. | ✅ Resolved |
| 4   | Weather data source — free tier with venue coordinates? | OpenWeatherMap free tier (1000 calls/day) or Open-Meteo (completely free). Open-Meteo recommended for no API key requirement. | ✅ Resolved |
| 5   | What TransferMarkt data is available without violating TOS? | TransferMarkt blocks scraping but has community APIs (transfermarkt-api.vercel.app). Use for coach tenure length + last 3 clubs. Tactical tendencies from Flashscore coach tab or manual. | ✅ Resolved |

## Implementation Plan

### Phase 1: Foundation — Extended Market Definitions & No-Rejection Policy

> **Priority:** CRITICAL — enables all subsequent phases.
> **Dependencies:** None.
> **Estimated files changed:** 3 modified, 1 created.

#### Task 1.1 - [MODIFY] Extend `normalize_stats.py` with All-Sport Market Definitions

**Description**: Add `SPORT_STAT_KEYS` and `SPORT_MARKETS` entries for ALL 14 sports. Currently only football, basketball, hockey have definitions. Need: tennis, volleyball, handball, snooker, darts, table_tennis, esports, baseball, mma, padel, speedway.

**Files**: `scripts/normalize_stats.py`

**Specific changes**:
```python
# Add to SPORT_STAT_KEYS:
"tennis": ["aces", "double_faults", "first_serve_pct", "break_points_won", "games_won", "sets_won", "total_games"],
"volleyball": ["points", "aces", "blocks", "attack_pct", "sets_won", "total_points", "errors"],
"handball": ["goals", "saves", "turnovers", "penalties", "suspensions", "total_goals"],
"snooker": ["frames_won", "centuries", "highest_break", "total_frames"],
"darts": ["legs_won", "checkout_pct", "180s", "avg_score", "total_legs"],
"table_tennis": ["sets_won", "points_per_set", "total_sets"],
"esports": ["maps_won", "rounds_won", "kills", "total_maps"],
"baseball": ["runs", "hits", "errors", "strikeouts", "walks", "total_runs"],
"mma": ["takedowns", "strikes", "submission_attempts", "rounds"],
"padel": ["games_won", "break_points", "sets_won", "total_games"],
"speedway": ["heat_points", "total_points"],

# Add corresponding SPORT_MARKETS for each sport (O/U lines per stat)
```

**Definition of Done**:

- [ ] `SPORT_STAT_KEYS` has entries for all 14 sports
- [ ] `SPORT_MARKETS` has market definitions for all 14 sports with at least 3 markets each
- [ ] Each market has `name`, `stat_a`, `stat_b`, `is_combined` fields matching existing format
- [ ] `SPORT_MARKETS` dict includes all 14 sports as keys
- [ ] Existing football/basketball/hockey definitions unchanged
- [ ] `python3 -c "from scripts.normalize_stats import SPORT_MARKETS; assert len(SPORT_MARKETS) == 14"` passes

#### Task 1.2 - [MODIFY] Make `aggregate_and_select.py` Advisory-Only

**Description**: Change price gap threshold filtering from hard rejection to advisory tagging. Currently events with `price_gap_pct < -3.0` (low-risk) or `< -5.0` (high-risk) are filtered out. Change to: tag with `advisory_flag: "below_threshold"` but include in output.

**Files**: `scripts/aggregate_and_select.py`

**Specific changes**:
- Find the filtering logic that drops events below threshold
- Replace with tagging: add `"advisory_flag"` field to output JSON
- All events pass through regardless of price gap, EV, or safety score
- Output `picks_suggested.json` includes ALL events with their advisory flags

**Definition of Done**:

- [ ] `picks_suggested.json` contains ALL scanned events (no price-gap-based filtering)
- [ ] Each event has `advisory_flag` field: `"pass"`, `"below_lr_threshold"`, or `"below_hr_threshold"`
- [ ] Events below threshold are NOT removed from output
- [ ] Config thresholds (`LOW_RISK_GAP_THRESHOLD`, `HIGH_RISK_GAP_THRESHOLD`) still read from config and applied as tags
- [ ] Script still outputs valid JSON with same schema + new field

#### Task 1.3 - [MODIFY] Update `compute_safety_scores.py` MIN_MARKETS

**Description**: Update the `MIN_MARKETS` dict to match the new sport definitions from Task 1.1.

**Files**: `scripts/compute_safety_scores.py`

**Specific changes**: Ensure all 14 sports have appropriate `MIN_MARKETS` values based on their `SPORT_MARKETS` definitions.

**Definition of Done**:

- [ ] `MIN_MARKETS` dict has entries for all 14 sports
- [ ] Values are ≤ number of markets defined in `SPORT_MARKETS` for each sport
- [ ] Script runs without errors for all 14 sport types

#### Task 1.4 - [CREATE] Market Definitions Test

**Description**: Create a test file that validates all 14 sports have complete market definitions and that safety scores can be computed for each sport.

**Files**: `tests/test_market_definitions.py`

**Definition of Done**:

- [ ] Test validates all 14 sports exist in `SPORT_STAT_KEYS`
- [ ] Test validates all 14 sports exist in `SPORT_MARKETS`
- [ ] Test validates each market has required fields (`name`, `stat_a` or `stat_b`, `is_combined`)
- [ ] Test validates `compute_safety_scores.py` accepts each sport type
- [ ] All tests pass: `python3 -m pytest tests/test_market_definitions.py`

---

### Phase 2: Aggressive Scanning Infrastructure

> **Priority:** HIGH — user's #1 request.
> **Dependencies:** Phase 1 (sport definitions for adapter tagging).
> **Estimated files changed:** 5 modified, 4 created.

#### Task 2.1 - [CREATE] Deep-Link Discovery Module

**Description**: Create `scripts/deep_link_discovery.py` — a module that takes an initial URL, fetches the page, extracts tournament/league sub-links, and returns them for scanning. This enables `scan_events.py` to drill into sub-pages instead of only reading landing pages.

**Files**: `scripts/deep_link_discovery.py`

**Logic**:
```python
def discover_deep_links(html: str, base_url: str, domain: str) -> list[str]:
    """Extract tournament/league sub-links from a landing page.
    
    Rules:
    - Flashscore: follow /football/COUNTRY/LEAGUE/ links
    - BetExplorer: follow /soccer/COUNTRY/LEAGUE/ links
    - Sofascore: follow tournament detail links
    - Max depth: 1 level (landing → tournament page)
    - Deduplicate by normalized URL
    - Skip known non-event pages (rules, standings, news)
    """
```

**Domain-specific link patterns**:
```
flashscore.com: a[href*="/football/"][href*="/results/"] + a[href*="/football/"][not results/standings]
betexplorer.com: a[href*="/soccer/"] with league-like paths
sofascore.com: tournament detail links from event listing
soccerway.com: a[href*="/matches/"] links from competition pages
```

**Definition of Done**:

- [ ] Module exports `discover_deep_links(html, base_url, domain) -> list[str]`
- [ ] Supports Flashscore, BetExplorer, Sofascore, Soccerway link patterns
- [ ] Filters out non-event pages (standings, results archive, rules, news)
- [ ] Deduplicates URLs
- [ ] Returns only URLs within the same domain
- [ ] Unit tests in `tests/test_deep_link_discovery.py` pass

#### Task 2.2 - [MODIFY] Add `--deep` Mode to `scan_events.py`

**Description**: Extend `scan_events.py` with a `--deep` flag. When enabled, after fetching each URL, the script calls `deep_link_discovery.discover_deep_links()` and fetches discovered sub-pages.

**Files**: `scripts/scan_events.py`

**Specific changes**:
- Add `--deep` argument to argparse
- After fetching and parsing a URL, if `--deep` is enabled:
  1. Call `discover_deep_links(html, url, domain)`
  2. For each discovered sub-link not already in the URL list:
     - Fetch the sub-page
     - Parse with the appropriate adapter
     - Merge results into `all_extracted`
- Add `--max-deep-links N` argument (default: 50 per source domain) to prevent runaway
- Track and log: `[deep] Discovered {N} sub-links from {url}, following {M}`

**Definition of Done**:

- [ ] `--deep` flag added and functional
- [ ] `--max-deep-links` argument limits sub-page following per domain
- [ ] Deep-link discovery works for Flashscore football country pages
- [ ] Sub-page results merged into `scan_summary.json` with `"source_type": "deep-link"` tag
- [ ] Without `--deep`, behavior is identical to current
- [ ] Script logs deep-link discovery counts

#### Task 2.3 - [CREATE] Soccerway Adapter

**Description**: Create a dedicated Soccerway adapter. Currently Soccerway falls through to `raw_parse`. Soccerway has structured HTML with match tables that can be parsed more reliably.

**Files**: `scripts/adapters/soccerway_adapter.py`, `scripts/adapters/__init__.py`

**Definition of Done**:

- [ ] `parse(html, url)` function extracts matches with: home, away, time, league, sport
- [ ] Handles Soccerway's table-based match layout (`.match-row` or equivalent selectors)
- [ ] Registered in `ADAPTERS` dict in `__init__.py` as `"soccerway.com": soccerway_parse`
- [ ] Returns empty list on unparseable HTML (no crashes)
- [ ] Test with sample Soccerway HTML passes

#### Task 2.4 - [CREATE] TennisExplorer Adapter

**Description**: Create a TennisExplorer adapter for parsing tennis match listings and draw data.

**Files**: `scripts/adapters/tennisexplorer_adapter.py`, `scripts/adapters/__init__.py`

**Definition of Done**:

- [ ] Extracts match listings: player1, player2, tournament, round, time, odds
- [ ] Handles current draws and daily schedule pages
- [ ] Registered in `ADAPTERS` dict as `"tennisexplorer.com": tennisexplorer_parse`
- [ ] Returns empty list on unparseable HTML

#### Task 2.5 - [CREATE] SoccerStats Adapter

**Description**: Create a dedicated SoccerStats adapter for parsing corner/card/foul statistics tables.

**Files**: `scripts/adapters/soccerstats_adapter.py`, `scripts/adapters/__init__.py`

**Definition of Done**:

- [ ] Extracts team statistical data: corners/match, cards/match, fouls/match (home/away split)
- [ ] Handles league ranking tables
- [ ] Registered in `ADAPTERS` dict as `"soccerstats.com": soccerstats_parse`
- [ ] Returns empty list on unparseable HTML

#### Task 2.6 - [MODIFY] Enhance Flashscore Adapter for Deep Links

**Description**: Extend the Flashscore adapter to export a list of tournament sub-links discovered during parsing, so deep-link discovery can use adapter knowledge of the DOM structure.

**Files**: `scripts/adapters/flashscore_adapter.py`

**Specific changes**:
- Add `extract_tournament_links(html, url) -> list[str]` function
- Detect links matching `/football/{country}/{league}/` pattern
- Detect links for other sports: `/tennis/{tournament}/`, `/basketball/{country}/{league}/`, etc.
- Export function from module

**Definition of Done**:

- [ ] `extract_tournament_links(html, url)` returns list of sub-page URLs
- [ ] Handles football country/league links
- [ ] Handles tennis, basketball, volleyball tournament links
- [ ] `deep_link_discovery.py` can call this for Flashscore-specific link extraction

#### Task 2.7 - [MODIFY] Expand URL List in `run_full_scan_and_prepare.sh`

**Description**: Expand the scan URL list from ~85 to 200+ URLs. Add regional Flashscore pages for KEY sports (football 2nd/3rd divisions, continental tournaments, women's leagues), plus additional sport-specific pages.

**Files**: `scripts/run_full_scan_and_prepare.sh`

**Specific URLs to add** (grouped by category):

**Football — European 2nd tier (30 URLs)**:
```
https://www.flashscore.com/football/poland/
https://www.flashscore.com/football/poland/2-liga/
https://www.flashscore.com/football/romania/
https://www.flashscore.com/football/serbia/
https://www.flashscore.com/football/croatia/
https://www.flashscore.com/football/hungary/
https://www.flashscore.com/football/czech-republic/
https://www.flashscore.com/football/slovakia/
https://www.flashscore.com/football/ukraine/
https://www.flashscore.com/football/bulgaria/
https://www.flashscore.com/football/cyprus/
https://www.flashscore.com/football/iceland/
https://www.flashscore.com/football/finland/
https://www.flashscore.com/football/norway/
https://www.flashscore.com/football/sweden/
https://www.flashscore.com/football/denmark/
https://www.flashscore.com/football/switzerland/
https://www.flashscore.com/football/austria/
https://www.flashscore.com/football/greece/
https://www.flashscore.com/football/scotland/
https://www.flashscore.com/football/belgium/
https://www.flashscore.com/football/netherlands/
https://www.flashscore.com/football/turkey/
https://www.flashscore.com/football/england/championship/
https://www.flashscore.com/football/england/league-one/
https://www.flashscore.com/football/germany/2-bundesliga/
https://www.flashscore.com/football/italy/serie-b/
https://www.flashscore.com/football/france/ligue-2/
https://www.flashscore.com/football/spain/laliga2/
https://www.flashscore.com/football/portugal/
```

**Football — Americas, Asia, Africa (20 URLs)**:
```
https://www.flashscore.com/football/brazil/
https://www.flashscore.com/football/argentina/
https://www.flashscore.com/football/uruguay/
https://www.flashscore.com/football/mexico/
https://www.flashscore.com/football/usa/
https://www.flashscore.com/football/japan/
https://www.flashscore.com/football/south-korea/
https://www.flashscore.com/football/china/
https://www.flashscore.com/football/indonesia/
https://www.flashscore.com/football/australia/
https://www.flashscore.com/football/south-africa/
https://www.flashscore.com/football/nigeria/
https://www.flashscore.com/football/ghana/
https://www.flashscore.com/football/kenya/
https://www.flashscore.com/football/tunisia/
https://www.flashscore.com/football/cameroon/
https://www.flashscore.com/football/senegal/
https://www.flashscore.com/football/bolivia/
https://www.flashscore.com/football/venezuela/
https://www.flashscore.com/football/honduras/
```

**Women's football (5 URLs)**:
```
https://www.flashscore.com/football/europe/champions-league-women/
https://www.flashscore.com/football/england/wsl-women/
https://www.flashscore.com/football/spain/liga-f-women/
https://www.flashscore.com/football/usa/nwsl-women/
https://www.flashscore.com/football/france/division-1-women/
```

**Tennis deep pages (5 URLs)**:
```
https://www.flashscore.com/tennis/atp-singles/
https://www.flashscore.com/tennis/wta-singles/
https://www.flashscore.com/tennis/atp-doubles/
https://www.tennisexplorer.com/matches/
https://www.atptour.com/en/scores/current
```

**Basketball deep pages (5 URLs)**:
```
https://www.flashscore.com/basketball/europe/euroleague/
https://www.flashscore.com/basketball/europe/eurocup/
https://www.flashscore.com/basketball/spain/acb/
https://www.flashscore.com/basketball/poland/plk/
https://www.flashscore.com/basketball/turkey/bsl/
```

**Volleyball deep pages (5 URLs)**:
```
https://www.flashscore.com/volleyball/poland/plusliga/
https://www.flashscore.com/volleyball/italy/superlega/
https://www.flashscore.com/volleyball/france/ligue-a/
https://www.flashscore.com/volleyball/europe/champions-league/
https://www.flashscore.com/volleyball/brazil/superliga/
```

**Additional sport-specific (10 URLs)**:
```
https://www.flashscore.com/handball/europe/champions-league/
https://www.flashscore.com/handball/germany/bundesliga/
https://www.flashscore.com/handball/france/starligue/
https://www.hltv.org/matches
https://www.flashscore.com/esports/counter-strike/
https://www.flashscore.com/darts/pdc/
https://www.flashscore.com/mma/ufc/
https://www.soccerstats.com/
https://totalcorner.com/
https://www.betaminic.com/
```

**Add `--deep` flag to the scan command** so deep-link following is enabled by default.

**Definition of Done**:

- [ ] URL count ≥ 200 in the scan command
- [ ] All KEY sport regions represented (EU 2nd tier, Americas, Asia, Africa)
- [ ] Women's leagues included for football
- [ ] Deep-link following enabled via `--deep` flag
- [ ] `--max-deep-links 50` passed to prevent runaway
- [ ] Script still completes within reasonable time (with delay between fetches)

---

### Phase 3: New API Clients for Missing Sports

> **Priority:** HIGH — fills data gaps for Tier 1 & 2 sports.
> **Dependencies:** Phase 1 (market definitions referenced by clients).
> **Estimated files changed:** 3 modified, 5 created.
> **Can run in parallel with Phase 2.**

#### Task 3.1 - [CREATE] API-Tennis Client

**Description**: Create `scripts/api_clients/api_tennis.py` following the `APISportsClient` pattern. API-Sports provides a tennis API at `v1.tennis.api-sports.io` using the same API key as API-Football.

**Files**: `scripts/api_clients/api_tennis.py`

**Methods to implement**:
- `get_fixtures(date: str) -> list[NormalizedFixture]` — all tennis matches on a date
- `get_match_stats(fixture_id: str) -> NormalizedMatchStats` — per-match stats (aces, DFs, break points)
- `get_h2h(player1_id: str, player2_id: str) -> list[NormalizedMatchStats]` — H2H meetings
- `resolve_team_id(player_name: str) -> str` — player name → API ID

**STAT_TYPE_MAP**:
```python
STAT_TYPE_MAP = {
    "Aces": "aces",
    "Double Faults": "double_faults",
    "1st Serve %": "first_serve_pct",
    "Break Points Won": "break_points_won",
    "Games Won": "games_won",
    "Sets Won": "sets_won",
}
```

**Definition of Done**:

- [ ] Client follows `APISportsClient` base class pattern
- [ ] Uses `v1.tennis.api-sports.io` endpoint
- [ ] Loads API key from `config/api_keys.json` under `"api-tennis"` (or reuses `"api-sports"`)
- [ ] Returns `NormalizedFixture` and `NormalizedMatchStats` objects
- [ ] Cache integration via `_check_cache` / `_save_cache`
- [ ] Rate limiting via `RateLimiter`
- [ ] Graceful degradation on 429/quota errors
- [ ] Unit tests pass in `tests/test_new_api_clients.py`

#### Task 3.2 - [CREATE] API-Volleyball Client

**Description**: Create `scripts/api_clients/api_volleyball.py` using API-Sports volleyball endpoint `v1.volleyball.api-sports.io`.

**Files**: `scripts/api_clients/api_volleyball.py`

**STAT_TYPE_MAP**:
```python
STAT_TYPE_MAP = {
    "Points": "points",
    "Aces": "aces",
    "Blocks": "blocks",
    "Attack %": "attack_pct",
    "Sets Won": "sets_won",
    "Errors": "errors",
}
```

**Definition of Done**:

- [ ] Client follows `APISportsClient` pattern with `v1.volleyball.api-sports.io`
- [ ] `get_fixtures(date)`, `get_match_stats(fixture_id)`, `get_h2h()` implemented
- [ ] Returns normalized objects
- [ ] Rate limiting and cache integration
- [ ] Unit tests pass

#### Task 3.3 - [CREATE] API-Handball Client

**Description**: Create `scripts/api_clients/api_handball.py` using API-Sports handball endpoint `v1.handball.api-sports.io`.

**Files**: `scripts/api_clients/api_handball.py`

**STAT_TYPE_MAP**:
```python
STAT_TYPE_MAP = {
    "Goals": "goals",
    "Saves": "saves",
    "Turnovers": "turnovers",
    "Penalties": "penalties",
    "Suspensions": "suspensions",
}
```

**Definition of Done**:

- [ ] Client follows `APISportsClient` pattern with `v1.handball.api-sports.io`
- [ ] `get_fixtures(date)`, `get_match_stats(fixture_id)`, `get_h2h()` implemented
- [ ] Returns normalized objects
- [ ] Rate limiting and cache integration
- [ ] Unit tests pass

#### Task 3.4 - [CREATE] API-Baseball Client

**Description**: Create `scripts/api_clients/api_baseball.py` using API-Sports baseball endpoint `v1.baseball.api-sports.io`.

**Files**: `scripts/api_clients/api_baseball.py`

**STAT_TYPE_MAP**:
```python
STAT_TYPE_MAP = {
    "Runs": "runs",
    "Hits": "hits",
    "Errors": "errors",
    "Strikeouts": "strikeouts",
    "Walks": "walks",
    "Home Runs": "home_runs",
}
```

**Definition of Done**:

- [ ] Client follows `APISportsClient` pattern with `v1.baseball.api-sports.io`
- [ ] `get_fixtures(date)`, `get_match_stats(fixture_id)`, `get_h2h()` implemented
- [ ] Returns normalized objects
- [ ] Rate limiting and cache integration
- [ ] Unit tests pass

#### Task 3.5 - [MODIFY] Register New API Clients

**Description**: Register all new API clients in the client registry and update discover_fixtures.py to query them.

**Files**: `scripts/api_clients/__init__.py`, `scripts/discover_fixtures.py`, `scripts/fetch_api_stats.py`

**Specific changes in `__init__.py`**:
```python
from .api_tennis import APITennisClient
CLIENT_REGISTRY["api-tennis"] = APITennisClient

from .api_volleyball import APIVolleyballClient
CLIENT_REGISTRY["api-volleyball"] = APIVolleyballClient

from .api_handball import APIHandballClient
CLIENT_REGISTRY["api-handball"] = APIHandballClient

from .api_baseball import APIBaseballClient
CLIENT_REGISTRY["api-baseball"] = APIBaseballClient
```

**Specific changes in `discover_fixtures.py`**:
- Add tennis section querying `api-tennis`
- Add volleyball section querying `api-volleyball`
- Add handball section querying `api-handball`
- Add baseball section querying `api-baseball`

**Specific changes in `fetch_api_stats.py`**:
- Add to `FALLBACK_CHAINS`:
```python
"tennis": ["api-tennis"],
"volleyball": ["api-volleyball"],
"handball": ["api-handball"],
"baseball": ["api-baseball"],
```
- Add `"tennis", "volleyball", "handball"` to `TIER_1_SPORTS` set (tennis, volleyball are KEY)

**Definition of Done**:

- [ ] All 4 new clients registered in `CLIENT_REGISTRY`
- [ ] `discover_fixtures.py` queries all 4 new APIs
- [ ] `fetch_api_stats.py` has fallback chains for all new sports
- [ ] `python3 scripts/discover_fixtures.py --date $(date +%Y-%m-%d) --sports tennis` works
- [ ] Graceful handling when API key is missing (skip, don't crash)

#### Task 3.6 - [CREATE] API Client Tests

**Description**: Create comprehensive tests for all new API clients.

**Files**: `tests/test_new_api_clients.py`

**Definition of Done**:

- [ ] Tests mock HTTP responses (no real API calls in tests)
- [ ] Each client tested: fixture parsing, stat parsing, H2H parsing, error handling
- [ ] Rate limit handling tested (429 response → graceful skip)
- [ ] Missing API key handling tested (skip → empty list)
- [ ] All tests pass: `python3 -m pytest tests/test_new_api_clients.py`

---

### Phase 4: Deep Analysis Enrichment

> **Priority:** MEDIUM — enhances analysis quality.
> **Dependencies:** Phases 1-3 (needs market definitions and API data).
> **Estimated files changed:** 3 modified, 3 created.

#### Task 4.1 - [MODIFY] Extend Stats Cache Schema

**Description**: Extend `build_stats_cache.py` to support new data types: tactical profile, coach data, weather conditions. The cache already supports form (24h TTL) and H2H (7d TTL). Add new entry types.

**Files**: `scripts/build_stats_cache.py`

**Specific changes**:
- Add `COACH_TTL_HOURS = 168` (7 days — coach changes are infrequent)
- Add `WEATHER_TTL_HOURS = 3` (weather data is time-sensitive)
- Add cache key patterns: `{sport}/{team_slug}_coach.json`, `{sport}/{team_slug}_tactical.json`
- Extend `create_team_cache_entry()` to include optional fields: `coach_name`, `coach_tenure_months`, `tactical_style`, `pressing_intensity`

**Definition of Done**:

- [ ] New TTL constants defined for coach and weather data
- [ ] Cache read/write supports `_coach.json` and `_tactical.json` files
- [ ] Existing cache functionality unchanged
- [ ] `read_cache` and `update_cache` handle new entry types

#### Task 4.2 - [CREATE] Tactical Profile Fetcher

**Description**: Create `scripts/fetch_tactical_profile.py` — fetches coach history and tactical tendencies. Primary source: community TransferMarkt API (transfermarkt-api.vercel.app) for coach data. Tactical data from Flashscore's coach tab or inferred from team stats (pressing = high fouls+corners, defensive = low goals conceded).

**Files**: `scripts/fetch_tactical_profile.py`

**Functions**:
```python
def fetch_coach_info(team_name: str, sport: str) -> dict:
    """Returns: coach_name, tenure_months, previous_clubs, tactical_tendency"""

def infer_tactical_style(team_stats: dict) -> dict:
    """Infer from stats: pressing_intensity (high/medium/low), 
    counter_attack_tendency, defensive_solidity, set_piece_dependency"""
```

**Definition of Done**:

- [ ] `fetch_coach_info()` returns structured coach data or empty dict on failure
- [ ] `infer_tactical_style()` works from stats cache data (no external calls needed)
- [ ] Tactical style inference uses: fouls/match, corners/match, possession%, shots/match ratios
- [ ] Results cached via `build_stats_cache.py` with coach TTL
- [ ] Graceful degradation when TransferMarkt API is unavailable
- [ ] Football-specific (other sports return empty tactical profile)

#### Task 4.3 - [CREATE] Weather Data Fetcher

**Description**: Create `scripts/fetch_weather.py` — fetches weather data for outdoor sport venues using Open-Meteo API (free, no API key required).

**Files**: `scripts/fetch_weather.py`

**Functions**:
```python
def fetch_match_weather(venue_city: str, kickoff_time: str) -> dict:
    """Returns: temperature_c, wind_speed_kmh, precipitation_mm, 
    weather_code, weather_impact (none/low/medium/high)"""
```

**Weather impact rules**:
- Rain > 2mm/h → `high` (affects corners: rain → more slippery → more corners from long balls)
- Wind > 30 km/h → `medium` (affects shots accuracy, long balls)
- Temperature < 5°C → `low` (affects player stamina in later stages)

**Definition of Done**:

- [ ] Uses Open-Meteo API (no API key required)
- [ ] `fetch_match_weather()` returns structured weather data
- [ ] `weather_impact` field calculated based on rules
- [ ] Handles city → coordinates lookup (geocoding via Open-Meteo)
- [ ] Cached with 3h TTL via `build_stats_cache.py`
- [ ] Returns `{"weather_impact": "unknown"}` on any failure (never crashes)

#### Task 4.4 - [MODIFY] Integrate Enrichment into Deep Analysis Pool

**Description**: Extend `deep_analysis_pool.py` to include tactical profile and weather data in the output JSON/MD files.

**Files**: `scripts/deep_analysis_pool.py`

**Specific changes**:
- After building safety scores for an event, call `fetch_tactical_profile.py` functions
- For outdoor sports (football, tennis, baseball), call `fetch_weather.py`
- Add `tactical_profile` and `weather` fields to output event JSON
- Include in markdown output: "Tactical: [style], Coach: [name] ([tenure])"
- Include weather impact note: "Weather: [temp]°C, [wind]km/h wind — [impact]"

**Definition of Done**:

- [ ] `analysis_pool_{date}.json` events include `tactical_profile` field when available
- [ ] `analysis_pool_{date}.json` events include `weather` field for outdoor sports
- [ ] `analysis_pool_{date}.md` displays tactical and weather data per event
- [ ] Missing data is shown as "N/A" (never causes crash or event exclusion)
- [ ] Performance: enrichment adds < 30s total (weather and tactical calls are cached)

---

### Phase 5: Enhanced Market Matrix & Coupon Output

> **Priority:** MEDIUM — improves final deliverable quality.
> **Dependencies:** Phase 4 (enriched data in analysis pool).
> **Estimated files changed:** 3 modified, 1 created.

#### Task 5.1 - [MODIFY] Extend Market Matrix for All Sports

**Description**: Update `generate_market_matrix.py` to show ALL available markets per sport using the extended `SPORT_MARKETS` definitions from Phase 1.

**Files**: `scripts/generate_market_matrix.py`

**Specific changes**:
- Import `SPORT_MARKETS` for all 14 sports
- For each event, list ALL markets defined for its sport (not just football/basketball/hockey)
- Add market availability indicator: `✅` (odds found), `📊` (stats only), `❓` (neither)
- Sort markets by safety score when available, then alphabetically

**Definition of Done**:

- [ ] `market_matrix_{date}.md` shows markets for ALL 14 sports
- [ ] Each event lists ALL available market types for its sport
- [ ] Market availability indicator present per market
- [ ] Markets sorted by safety score (desc) when available
- [ ] No events filtered or excluded from the matrix

#### Task 5.2 - [CREATE] Cross-Sport Correlation Analysis

**Description**: Create `scripts/cross_sport_correlation.py` — analyzes correlations between picks across different sports to support coupon construction. Identifies which market types are independent (good for combining) vs correlated (risky to combine).

**Files**: `scripts/cross_sport_correlation.py`

**Functions**:
```python
def compute_correlations(picks: list[dict]) -> dict:
    """Returns correlation matrix between markets/sports.
    
    Output: {
        "independent_pairs": [("football_corners", "tennis_games"), ...],
        "correlated_pairs": [("basketball_points", "basketball_rebounds"), ...],
        "suggested_combos": [{"legs": [...], "correlation": "low", "reason": "..."}]
    }
    """
```

**Definition of Done**:

- [ ] Identifies same-event correlations (can't combine same match in core coupon)
- [ ] Identifies same-sport correlations (basketball points ↔ rebounds)
- [ ] Suggests independent cross-sport combinations
- [ ] Output is JSON format consumable by agents
- [ ] Runs as: `python3 scripts/cross_sport_correlation.py --picks picks_suggested.json`

#### Task 5.3 - [MODIFY] Update Coupon Validator for All Sports

**Description**: Extend `validate_coupons.py` to recognize Polish betting terms for all 14 sports (currently limited).

**Files**: `scripts/validate_coupons.py`

**Specific changes to `POLISH_TERMS`**:
```python
POLISH_TERMS = {
    # Existing
    "powyżej", "poniżej", "bramek", "gemów", "rzutów", "rożnych",
    "setów", "kartek", "zwycięstwo", "handicap", "łączna", "strzelą",
    "punktów", "framów", "goli", "runów", "mapowy", "setowy",
    "drużyny", "szansa", "remis", "podwójna",
    # New for additional sports
    "asów", "podwójnych", "breaków", "legów", "rzutów wolnych",
    "nóg", "strzałów", "kar", "przyłożeń", "biegów", "wyścigów",
    "rund", "walk", "obalenia", "ciosów", "uderzeń",
    "biegów domowych", "skuteczność",
}
```

**Definition of Done**:

- [ ] `POLISH_TERMS` includes betting terms for all 14 sports
- [ ] Validation recognizes tennis (gemy, sety, asy), volleyball (sety, punkty), handball (bramek), etc.
- [ ] Existing validation logic unchanged
- [ ] Script still reports valid/invalid correctly

#### Task 5.4 - [MODIFY] Update Betting Artifacts Instructions

**Description**: Update `betting-artifacts.instructions.md` to document the extended market matrix format and cross-sport correlation section.

**Files**: `.github/instructions/betting-artifacts.instructions.md`

**Specific changes**:
- Add documentation for the extended market matrix (all 14 sports)
- Add section for cross-sport correlation output
- Document new fields in analysis pool output (tactical_profile, weather)

**Definition of Done**:

- [ ] Market matrix section documents all 14 sports and their market types
- [ ] Cross-sport correlation section documented
- [ ] Tactical and weather enrichment fields documented
- [ ] No existing documentation removed

---

### Phase 6: Pipeline Orchestrator & State Management

> **Priority:** MEDIUM — improves operational reliability.
> **Dependencies:** Phases 1-5 (orchestrator manages all steps).
> **Estimated files changed:** 2 modified, 3 created.

#### Task 6.1 - [CREATE] Pipeline State Manager

**Description**: Create `scripts/pipeline_state.py` — tracks which pipeline steps have been completed, their status, and enables resume-on-failure.

**Files**: `scripts/pipeline_state.py`

**Data structure**:
```python
@dataclass
class PipelineState:
    date: str
    session: str  # full/day/night/morning
    version: str  # v1, v2, ...
    started_at: str
    steps: dict[str, StepStatus]  # step_name → status
    
@dataclass
class StepStatus:
    status: str  # pending/running/success/failed/skipped
    started_at: str | None
    completed_at: str | None
    output_files: list[str]
    error: str | None
    retry_count: int
```

**State file**: `betting/data/pipeline_state_{date}.json`

**Definition of Done**:

- [ ] `PipelineState` and `StepStatus` dataclasses defined
- [ ] `save_state(state)` and `load_state(date)` functions
- [ ] `update_step(date, step_name, status, **kwargs)` function
- [ ] State file written to `betting/data/pipeline_state_{date}.json`
- [ ] State survives process restart (can resume from last successful step)
- [ ] Unit tests pass in `tests/test_pipeline_orchestrator.py`

#### Task 6.2 - [CREATE] Python Pipeline Orchestrator

**Description**: Create `scripts/pipeline_orchestrator.py` — Python entry point that wraps `run_full_scan_and_prepare.sh` and adds state tracking, progress reporting, error recovery, and selective step execution.

**Files**: `scripts/pipeline_orchestrator.py`

**Pipeline steps managed**:
```
1. install_deps
2. playwright_setup
3. smoke_test
4. clean_stale
5. web_scan          (scan_events.py --deep)
6. api_fixtures      (discover_fixtures.py)
7. api_stats         (fetch_api_stats.py)
8. odds_multi        (fetch_odds_multi.py)
9. deep_analysis     (deep_analysis_pool.py)
10. aggregate        (aggregate_and_select.py)
11. betclic_extract  (quick_betclic_extract.py)
12. market_matrix    (generate_market_matrix.py)
13. correlation      (cross_sport_correlation.py)
14. tactical_enrich  (fetch_tactical_profile.py — batch)
15. weather_enrich   (fetch_weather.py — batch)
```

**CLI interface**:
```bash
python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --session full
python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --resume  # resume from last failure
python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --step web_scan  # run single step
python3 scripts/pipeline_orchestrator.py --date 2026-04-30 --status  # show pipeline status
```

**Definition of Done**:

- [ ] Runs all 15 pipeline steps in order
- [ ] Updates `pipeline_state_{date}.json` after each step
- [ ] `--resume` skips already-succeeded steps
- [ ] `--step NAME` runs a single step
- [ ] `--status` prints current pipeline state table
- [ ] Failed steps logged with error detail in state file
- [ ] Each step's stdout/stderr captured to `betting/data/logs/step_{N}_{name}.log`
- [ ] Exit code 0 if all steps succeed, 1 if any step failed
- [ ] Progress printed: `[5/15] web_scan... ✅ (45s)`

#### Task 6.3 - [MODIFY] Update Orchestrator Agent and Prompt

**Description**: Update `bet-orchestrator.agent.md` and `orchestrate-betting-day.prompt.md` to reference the new Python orchestrator.

**Files**: `.github/agents/bet-orchestrator.agent.md`, `.github/prompts/orchestrate-betting-day.prompt.md`

**Specific changes**:
- Add reference to `python3 scripts/pipeline_orchestrator.py` as an alternative entry point
- Document `--resume` capability for handling mid-pipeline failures
- Document `--status` for checking pipeline progress
- Keep `bash scripts/run_full_scan_and_prepare.sh` as the legacy entry point

**Definition of Done**:

- [ ] Agent documentation references new orchestrator
- [ ] Prompt includes new orchestrator command options
- [ ] Legacy bash script reference preserved
- [ ] Pipeline state file referenced in agent's data file patterns

#### Task 6.4 - [CREATE] Pipeline Orchestrator Tests

**Description**: Create tests for pipeline state management and orchestrator logic.

**Files**: `tests/test_pipeline_orchestrator.py`

**Definition of Done**:

- [ ] Tests cover: state creation, step status updates, resume logic, state persistence
- [ ] Tests mock subprocess calls (no actual pipeline execution in tests)
- [ ] Tests verify: failed step → resume skips succeeded steps
- [ ] Tests verify: `--status` output format
- [ ] All tests pass: `python3 -m pytest tests/test_pipeline_orchestrator.py`

---

### Phase 7: Methodology & Documentation Updates

> **Priority:** LOW — documentation alignment.
> **Dependencies:** Phases 1-6 (documents new capabilities).
> **Can run incrementally alongside other phases.**

#### Task 7.1 - [MODIFY] Update Analysis Methodology

**Description**: Update `analysis-methodology.instructions.md` to reference new capabilities: tactical analysis section, extended sport market definitions, weather integration.

**Files**: `.github/instructions/analysis-methodology.instructions.md`

**Specific changes**:
- Add §3.X TACTICAL MATCHUP ANALYSIS section (pressing intensity, counter-attack tendency, set-piece dependency)
- Add §3.Y WEATHER/VENUE IMPACT section (rain → corners boost, wind → shots impact)
- Reference new API clients in STEP 1 scanning mandate
- Reinforce NO AUTO-REJECTION with reference to advisory-only flags in `aggregate_and_select.py`

**Definition of Done**:

- [ ] Tactical analysis section added with clear stat-to-tactic mapping
- [ ] Weather impact section added with threshold table
- [ ] New API clients referenced in scanning mandate
- [ ] No existing methodology sections removed or contradicted

#### Task 7.2 - [MODIFY] Update Sport Analysis Protocols

**Description**: Add tactical matchup analysis subsections to sport-specific protocols in `sport-analysis-protocols.instructions.md`.

**Files**: `.github/instructions/sport-analysis-protocols.instructions.md`

**Specific changes**:
- Add "Tactical Profile" row to each sport's required stats table
- Add coach tenure as a context factor
- For football: add pressing intensity, counter-attack tendency columns
- For basketball: add pace rating, defensive rating columns
- For tennis: add surface-specific playstyle (baseline/serve-volley)

**Definition of Done**:

- [ ] Each KEY sport (football, tennis, basketball, volleyball) has a tactical profile section
- [ ] Coach tenure check referenced in context section per sport
- [ ] No existing protocols removed or contradicted

#### Task 7.3 - [MODIFY] Update Source Registry

**Description**: Update `betting/sources/source-registry.md` with new sources and API clients.

**Files**: `betting/sources/source-registry.md`

**Specific changes**:
- Add API-Tennis, API-Volleyball, API-Handball, API-Baseball entries
- Add Open-Meteo (weather) entry
- Add community TransferMarkt API entry
- Update fallback chains per sport with new clients

**Definition of Done**:

- [ ] All new API clients documented with role, URL, access notes
- [ ] Weather source documented
- [ ] Fallback chains updated for tennis, volleyball, handball, baseball

#### Task 7.4 - [MODIFY] Update Dependencies

**Description**: Update `scripts/requirements.txt` with any new Python dependencies needed by the new scripts.

**Files**: `scripts/requirements.txt`

**New dependencies** (if needed):
```
# Only add if not already covered by existing packages:
# requests (already present)
# beautifulsoup4 (already present)
# No new external dependencies expected — all new API clients use requests
```

**Definition of Done**:

- [ ] All imports in new scripts are satisfied by listed dependencies
- [ ] `pip install -r scripts/requirements.txt` succeeds
- [ ] No unnecessary dependencies added

---

## Security Considerations

- **API keys**: All new API clients (tennis, volleyball, handball, baseball) use the existing `config/api_keys.json` key management pattern. No new key storage mechanism needed. The `APISportsClient` base class handles key loading securely.
- **Input sanitization**: `build_stats_cache.py` already has `validate_sport()` to prevent path traversal. New cache entry types follow the same pattern.
- **No new network exposure**: All new scripts are clients (outbound HTTP only). No server endpoints created.
- **Rate limiting**: All new API clients inherit `RateLimiter` from base class, preventing API abuse.
- **Deep-link following**: `--max-deep-links` parameter prevents infinite crawling. Only same-domain links are followed (no open redirect risk).
- **Weather API**: Open-Meteo requires no API key and no authentication — no credential exposure risk.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] All 14 sports have market definitions in `normalize_stats.py`
- [ ] Safety scores can be computed for all 14 sports
- [ ] `aggregate_and_select.py` passes ALL events through (advisory-only mode)
- [ ] Deep-link following discovers ≥20 sub-pages from Flashscore football landing page
- [ ] New API clients return `NormalizedFixture` and `NormalizedMatchStats` objects
- [ ] `discover_fixtures.py` queries all registered API clients
- [ ] `run_full_scan_and_prepare.sh` URL count ≥ 200
- [ ] Tactical profile and weather data appear in `analysis_pool_{date}.json` for applicable events
- [ ] Market matrix shows markets for all 14 sports
- [ ] Pipeline orchestrator tracks state and supports resume-on-failure
- [ ] All new test files pass: `python3 -m pytest tests/`
- [ ] Existing tests remain passing (no regressions)

## Improvements (Out of Scope)

Potential improvements identified during planning that are not part of the current task:

- **Live odds streaming**: WebSocket connection to Betclic for real-time odds updates (requires reverse-engineering Betclic's WebSocket protocol)
- **ML-based safety score**: Train a model on historical Betclic bet outcomes to predict market safety (requires >500 settled bets for training)
- **Automated Betclic bet placement**: Browser automation to place bets directly (high risk, requires Betclic TOS review)
- **Database backend**: Replace JSON files with SQLite/PostgreSQL for faster queries on historical data
- **Parallel scanning**: Use async/aiohttp for concurrent URL fetching (significant refactor of scan_events.py)
- **Custom LLM integration**: Fine-tuned model for market analysis using historical data
- **Telegram/Discord notifications**: Push alerts for high-value picks approaching kickoff

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-04-30 | Initial plan created |
