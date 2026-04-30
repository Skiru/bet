# Multi-Source Odds Fallback System - Implementation Plan

## Task Details

| Field            | Value                                                        |
| ---------------- | ------------------------------------------------------------ |
| Jira ID          | N/A                                                          |
| Title            | Multi-Source Odds Fallback System                            |
| Description      | Build a multi-source odds retrieval system with 5+ sources so no sport is left without odds coverage. Fix Flashscore volleyball parser. Add API-Football /odds, OddsPortal scraper, BetExplorer scraper, and a unified aggregator. |
| Priority         | High                                                         |
| Related Research | N/A                                                          |

## Proposed Solution

Build a modular odds source system with a unified aggregator. Each odds source implements a common interface (`OddsSource` ABC) and returns events in the existing `odds_api_snapshot.json` format. A per-sport priority map defines which sources to try and in what order. The aggregator merges results, deduplicates events, tracks provenance, and outputs backward-compatible files.

### Architecture

```
                          fetch_odds_multi.py (CLI + aggregator)
                                  │
           ┌──────────────────────┼──────────────────────┐
           │                      │                      │
     ┌─────▼──────┐      ┌───────▼───────┐     ┌────────▼────────┐
     │ API Sources │      │  Playwright   │     │  Adapter-based  │
     │             │      │   Scrapers    │     │   Extraction    │
     └─────┬──────┘      └───────┬───────┘     └────────┬────────┘
           │                      │                      │
   ┌───────┼───────┐      ┌──────┼───────┐              │
   │               │      │              │              │
TheOddsAPI   APIFootball  OddsPortal  BetExplorer    Betclic
(existing)   /odds(NEW)   scraper(NEW) scraper(NEW)  adapter(EXIST)
   │               │      │              │              │
   ▼               ▼      ▼              ▼              ▼
   └───────────────────────┬─────────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │  Merged      │
                    │  Snapshot    │
                    │  (same fmt)  │
                    └──────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
    odds_api_snapshot.json │  odds_multi_sources.json
                odds_api_summary.csv
```

**Sport → Source Priority Map:**

| Sport         | Source 1       | Source 2         | Source 3        | Source 4     |
|---------------|----------------|------------------|-----------------|--------------|
| football      | The Odds API   | API-Football     | OddsPortal      | BetExplorer  |
| tennis        | The Odds API   | OddsPortal       | BetExplorer     | Betclic      |
| basketball    | The Odds API   | OddsPortal       | BetExplorer     | Betclic      |
| hockey        | The Odds API   | OddsPortal       | BetExplorer     | Betclic      |
| baseball      | The Odds API   | OddsPortal       | BetExplorer     | Betclic      |
| mma           | The Odds API   | OddsPortal       | BetExplorer     | Betclic      |
| volleyball    | OddsPortal     | BetExplorer      | Betclic         | —            |
| handball      | OddsPortal     | BetExplorer      | Betclic         | —            |
| esports       | OddsPortal     | BetExplorer      | Betclic         | —            |
| snooker       | OddsPortal     | BetExplorer      | Betclic         | —            |
| darts         | OddsPortal     | BetExplorer      | Betclic         | —            |
| table_tennis  | OddsPortal     | BetExplorer      | Betclic         | —            |
| padel         | BetExplorer    | Betclic          | —               | —            |
| speedway      | BetExplorer    | Betclic          | —               | —            |

**Key design decisions:**
- All sources output in the existing `odds_api_snapshot.json` event format (list of events with `bookmakers[].markets[].outcomes[]`)
- Each event gets a `_odds_source` field for provenance tracking
- Aggregator deduplicates by matching `(home_team, away_team, commence_time)` with fuzzy team name matching
- `fetch_odds_multi.py` replaces `fetch_odds_api.py` in the pipeline but `fetch_odds_api.py` remains usable standalone
- API-Football `/odds` uses the existing key (`d2040a4b3525e46e5f7d0392feed5384`), no new subscription needed
- Playwright scrapers reuse `fetch_with_playwright.fetch()` and existing adapter patterns
- All sources use the existing `RateLimiter` from `scripts/api_clients/rate_limiter.py`

## Current Implementation Analysis

### Already Implemented

- `scripts/fetch_odds_api.py` — The Odds API fetcher, outputs `odds_api_snapshot.json` + `odds_api_summary.csv`. Covers 6 sports.
- `scripts/api_clients/base_client.py` — `BaseAPIClient` (ABC with rate limiting, retry, caching) + `APISportsClient` (x-apisports-key auth). Lines 1-315.
- `scripts/api_clients/rate_limiter.py` — `RateLimiter` with file-based daily counters, per-API limits, thread-safe.
- `scripts/api_clients/api_football.py` — `APIFootballClient` extending `APISportsClient`. Has `get_fixtures()`, `get_fixture_stats()`, `get_h2h()`, `resolve_team_id()`. Does NOT have `/odds` endpoint.
- `scripts/adapters/__init__.py` — adapter registry with `get_adapter(domain)` and `dedup_results()`.
- `scripts/adapters/flashscore_adapter.py` — heuristic match extractor, two strategies (class-based + participant spans). Volleyball bug: team names merged with league headers, `time: null`.
- `scripts/adapters/oddsportal_adapter.py` — extracts events + odds from `<tr>` rows using regex. Returns `{home, away, odds: [...], source_url}`.
- `scripts/adapters/betclic_adapter.py` — Angular SPA parser, extracts team names, times, odds from `btn_label`, competition, match URLs.
- `scripts/adapters/sofascore_adapter.py` — generic event extractor, falls back to raw_adapter.
- `scripts/adapters/raw_adapter.py` — minimal heuristic parser for any HTML.
- `scripts/fetch_with_playwright.py` — Playwright fetcher with cookie handling, storage state persistence, retry, User-Agent rotation.
- `scripts/scan_events.py` — URL scanner using Playwright + adapters, outputs `scan_summary.json`.
- `scripts/run_full_scan_and_prepare.sh` — orchestrator, 10-step pipeline. Currently does NOT call `fetch_odds_api.py` (called separately).
- `config/api_keys.json` — all API keys including `api-football` key (shared with `api-basketball`, `api-hockey`).
- `config/betting_config.json` — 14 sports configured (4 KEY + 10 SUPPORT).
- `betting/sources/source-registry.md` — source documentation with roles and access notes.

### To Be Modified

- `scripts/adapters/flashscore_adapter.py` — Fix volleyball page parsing (league headers merged into team names, `time: null`). Add volleyball-specific parsing strategy that handles section headers separately from match rows.
- `scripts/adapters/oddsportal_adapter.py` — Enhance to extract structured odds with bookmaker names and market types (h2h, totals) from match listing pages, not just raw odds arrays.
- `scripts/adapters/__init__.py` — Register new `betexplorer_adapter.py` in `ADAPTERS` dict.
- `scripts/api_clients/rate_limiter.py` — Add daily limits for new sources: `"api-football-odds": 100`, `"oddsportal-scraper": 50`, `"betexplorer-scraper": 50`, `"betclic-scraper": 50`.
- `scripts/run_full_scan_and_prepare.sh` — Add step to call `fetch_odds_multi.py` after the scan (new step between 4 and 5, or replace a placeholder).
- `betting/sources/source-registry.md` — Document API-Football /odds as a new Tier A market source, document multi-source aggregator.

### To Be Created

- `scripts/odds_sources/__init__.py` — `OddsSource` ABC defining `fetch_odds(sport, date_from, date_to) -> list[dict]`, source registry, common utilities (team name normalization, event deduplication).
- `scripts/odds_sources/the_odds_api.py` — Wraps existing `fetch_odds_api.py` logic into `OddsSource` interface. Delegates to existing functions.
- `scripts/odds_sources/api_football_odds.py` — New `APISportsClient` subclass using `/odds?date=YYYY-MM-DD` endpoint. Transforms API-Football odds response into snapshot event format.
- `scripts/odds_sources/oddsportal_scraper.py` — Playwright-based odds scraper for OddsPortal. Navigates sport listing pages, extracts odds from match rows using enhanced adapter.
- `scripts/odds_sources/betexplorer_scraper.py` — Playwright-based odds scraper for BetExplorer. Navigates sport listing pages, extracts odds tables.
- `scripts/odds_sources/betclic_scraper.py` — Playwright-based odds extraction from Betclic sport pages. Uses existing `betclic_adapter.py` parse output.
- `scripts/adapters/betexplorer_adapter.py` — HTML parser for BetExplorer pages (match rows with odds columns).
- `scripts/fetch_odds_multi.py` — Unified multi-source odds aggregator CLI. Tries sources in sport-priority order, merges, deduplicates, outputs backward-compatible snapshot.
- `tests/test_odds_sources.py` — Unit tests for OddsSource implementations, event deduplication, team name matching, format conversion.
- `tests/test_flashscore_volleyball.py` — Unit tests for Flashscore volleyball parser fix with sample HTML.
- `tests/test_betexplorer_adapter.py` — Unit tests for BetExplorer adapter.

## Open Questions

| #   | Question                                                                 | Answer                                                                                              | Status       |
| --- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | ------------ |
| 1   | Does API-Football /odds count against the same 100 req/day as /fixtures? | Yes — all API-Football endpoints share the same 100 req/day limit on free tier.                     | ✅ Resolved  |
| 2   | Does OddsPortal block Playwright headless browsers?                      | OddsPortal works with Playwright per source-registry ("Access: OK"). Cookie consent handled by existing selectors. | ✅ Resolved  |
| 3   | Should `fetch_odds_api.py` be deprecated or kept as standalone?          | Keep as standalone (backward compat). The aggregator wraps it. Users can still call it directly.     | ✅ Resolved  |
| 4   | How many API-Football /odds requests per scan?                           | ~1 request per day covers all fixtures for that date. Paginated (10/page), so top leagues need ~3-5 pages = ~5 requests total. Budget: 5 credits/scan. | ✅ Resolved  |
| 5   | Sofascore API as 6th source?                                             | Deferred to improvements — Sofascore API is undocumented and may block automated access. Focus on reliable 5 sources first. | ✅ Resolved  |

## Implementation Plan

### Phase 1: Flashscore Volleyball Fix + BetExplorer Adapter

**Goal:** Fix the volleyball parsing bug and create the missing BetExplorer adapter.

#### Task 1.1 - [MODIFY] Fix Flashscore volleyball parser

**Description:** The Flashscore volleyball page structure differs from other sports. League/section headers (e.g., "PlusLiga - Playoffs") appear as text within the same container elements that hold match rows, causing them to be prepended to team names. Additionally, match times for volleyball events are not extracted (`time: null`).

Add a volleyball-specific parsing strategy before the generic heuristics:
1. Detect volleyball pages via URL pattern (`/volleyball` in URL)
2. For volleyball pages, use class-based selectors targeting Flashscore's event row structure: look for elements with classes containing `event__match`, `event__participant`, or similar volleyball-specific patterns
3. Strip league/section header text from team name fields by tracking current league section context
4. Extract time from sibling elements with time-like classes

**Files:** `scripts/adapters/flashscore_adapter.py`

**Definition of Done:**
- [x] Volleyball page HTML with merged league headers correctly separates league name from team names
- [x] Time extraction works for volleyball events (not `null` when time is present in DOM)
- [x] Non-volleyball sport parsing is unaffected (existing heuristics still work)
- [x] Unit tests pass with sample volleyball HTML fixtures

#### Task 1.2 - [CREATE] Unit tests for Flashscore volleyball fix

**Description:** Create test file with sample Flashscore volleyball HTML (both old broken format and expected correct output). Test that league headers are stripped, team names are clean, and times are extracted.

**Files:** `tests/test_flashscore_volleyball.py`

**Definition of Done:**
- [x] At least 3 test cases: normal volleyball page, page with multiple leagues, page with no events
- [x] Tests verify `home` and `away` fields don't contain league header text
- [x] Tests verify `time` is extracted when present
- [x] Tests verify non-volleyball HTML is unaffected by the changes

#### Task 1.3 - [CREATE] BetExplorer HTML adapter

**Description:** Create `scripts/adapters/betexplorer_adapter.py` to parse BetExplorer match listing pages. BetExplorer uses table-based layout with odds columns. Each match row contains: team names (with link), time/date, and 1X2 odds in table cells.

The adapter should:
1. Find match table rows (BetExplorer uses `<tr>` elements with match data)
2. Extract home/away team names from link text
3. Extract match time from the row
4. Extract odds from table cells (typically 3 cells for 1X2: home win, draw, away win)
5. Return results in the standard adapter format: `{home, away, time, odds: [...], source_url, raw}`

**Files:** `scripts/adapters/betexplorer_adapter.py`

**Definition of Done:**
- [x] Adapter has `parse(html: str, url: str) -> List[Dict]` function matching adapter protocol
- [x] Extracts team names, times, and odds from BetExplorer table structure
- [x] Falls back to `raw_adapter.parse` when structured parsing fails
- [x] Uses `dedup_results()` from `adapters.__init__`

#### Task 1.4 - [MODIFY] Register BetExplorer adapter

**Description:** Add `betexplorer_adapter.py` to the adapter registry in `scripts/adapters/__init__.py`. Map `"betexplorer.com"` to the new parser (replacing current `raw_parse` mapping).

**Files:** `scripts/adapters/__init__.py`

**Definition of Done:**
- [x] `betexplorer.com` key in `ADAPTERS` dict points to `betexplorer_parse`
- [x] Import added at top of file
- [x] Existing adapter mappings unchanged

#### Task 1.5 - [CREATE] Unit tests for BetExplorer adapter

**Description:** Create test file with sample BetExplorer HTML to verify match and odds extraction.

**Files:** `tests/test_betexplorer_adapter.py`

**Definition of Done:**
- [x] At least 3 test cases covering: standard match page, page with multiple sports, empty page
- [x] Tests verify team names, odds values, and times are correctly extracted
- [x] Tests verify fallback to raw_adapter when no structured data found

---

### Phase 2: API-Football /odds Client

**Goal:** Create a new API client that fetches pre-match odds from API-Football's `/odds` endpoint using the existing API key.

#### Task 2.1 - [CREATE] API-Football Odds client

**Description:** Create `scripts/odds_sources/api_football_odds.py` — a new client extending `APISportsClient` that calls the `/odds` endpoint.

API-Football `/odds` endpoint:
- URL: `https://v3.football.api-sports.io/odds`
- Params: `date=YYYY-MM-DD` (or `fixture=ID`, `league=ID&season=YYYY`)
- Auth: `x-apisports-key` header (existing key: `d2040a4b3525e46e5f7d0392feed5384`)
- Response: paginated (10 results/page), each item has `league`, `fixture`, `bookmakers[].bets[].values[]`
- Cost: 1 request per page. Free tier: 100 req/day (shared with all api-football endpoints).

The client should:
1. Extend `APISportsClient` with `_SHARES_FOOTBALL_KEY = True`
2. Implement `fetch_odds_for_date(date: str) -> list[dict]` that:
   - Calls `/odds?date=YYYY-MM-DD&page=1` and paginates through all pages
   - Transforms response into snapshot event format: `{id, sport_key, sport_title, commence_time, home_team, away_team, bookmakers: [{key, title, markets: [{key, outcomes: [{name, price, point?}]}]}]}`
   - Maps API-Football bet types to standard market keys: bet ID 1 → `h2h`, bet ID 5 → `totals` (Goals O/U), bet ID 45 → `totals_corners` (Corners O/U)
   - Tags events with `_our_sport: "football"` and `_odds_source: "api-football"`
3. Cache responses with 3-hour TTL (odds change frequently)
4. Handle pagination: follow `response.paging.total` pages, respect rate limits

**Files:** `scripts/odds_sources/api_football_odds.py`

**Definition of Done:**
- [ ] Client extends `APISportsClient` and uses existing `api-football` key
- [ ] `fetch_odds_for_date(date)` returns list of events in snapshot format
- [ ] Pagination handles multi-page responses correctly
- [ ] API-Football bet types mapped to standard market keys (h2h, totals at minimum)
- [ ] Rate limiter integration uses `api-football` quota (shared with stats calls)
- [ ] Response cached with 3-hour TTL
- [ ] Handles empty responses and API errors gracefully (returns `[]`)

#### Task 2.2 - [MODIFY] Add rate limiter entries

**Description:** Add daily limits for new odds sources to `API_DAILY_LIMITS` in `scripts/api_clients/rate_limiter.py`. Note: `api-football` already has `100` — the `/odds` calls share this limit. Add entries for Playwright scrapers to enforce daily caps.

**Files:** `scripts/api_clients/rate_limiter.py`

**Definition of Done:**
- [ ] Added: `"oddsportal-scraper": 50`, `"betexplorer-scraper": 50`, `"betclic-scraper": 50`
- [ ] Existing limits unchanged
- [ ] No changes to `api-football` limit (shared with /odds)

#### Task 2.3 - [CREATE] Unit tests for API-Football Odds client

**Description:** Create tests with mocked API responses verifying odds fetching, format conversion, pagination, and error handling.

**Files:** `tests/test_api_football_odds.py`

**Definition of Done:**
- [ ] Tests use same fixture/mock pattern as `tests/test_api_football.py` (patch `_load_api_key`, patch `CACHE_DIR`, use `tmp_path`)
- [ ] Test: single-page odds response correctly converted to snapshot format
- [ ] Test: multi-page pagination (mocked to return 2 pages)
- [ ] Test: empty response returns `[]`
- [ ] Test: API key missing returns `[]`
- [ ] Test: bet type mapping (bet ID 1 → h2h, bet ID 5 → totals)

---

### Phase 3: Playwright Odds Scrapers

**Goal:** Create Playwright-based odds scrapers for OddsPortal, BetExplorer, and Betclic that extract structured odds from match listing pages.

#### Task 3.1 - [CREATE] OddsSource ABC and package init

**Description:** Create `scripts/odds_sources/__init__.py` defining the `OddsSource` abstract base class and common utilities.

```python
class OddsSource(ABC):
    """Abstract base for all odds data sources."""
    name: str  # e.g., "the-odds-api", "api-football-odds"
    
    @abstractmethod
    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        """Fetch odds for a sport within a time window.
        
        Returns list of events in snapshot format:
        [{id, sport_key, sport_title, commence_time, home_team, away_team,
          bookmakers: [{key, title, markets: [{key, outcomes: [{name, price, point?}]}]}],
          _our_sport, _odds_source}]
        """
        ...
    
    @abstractmethod
    def supported_sports(self) -> list[str]:
        """Return list of sport keys this source can provide odds for."""
        ...
```

Also include:
- `normalize_team_name(name: str) -> str` — strip common suffixes (FC, SC, etc.), normalize whitespace, handle unicode
- `events_match(a: dict, b: dict) -> bool` — fuzzy match on `(home_team, away_team, commence_time)` with ±2h window and Levenshtein-based team name matching
- `merge_event_odds(existing: dict, new: dict) -> dict` — merge bookmakers from two sources for the same event
- `SPORT_SOURCE_PRIORITY: dict[str, list[str]]` — configurable priority map (from architecture diagram above)

**Files:** `scripts/odds_sources/__init__.py`

**Definition of Done:**
- [ ] `OddsSource` ABC defined with `fetch_odds()` and `supported_sports()` methods
- [ ] `normalize_team_name()` handles FC/SC/CF suffixes, extra whitespace, common unicode issues
- [ ] `events_match()` correctly identifies same events from different sources
- [ ] `merge_event_odds()` combines bookmaker lists without duplicates
- [ ] `SPORT_SOURCE_PRIORITY` dict maps all 14 sports to ordered source lists

#### Task 3.2 - [CREATE] The Odds API source wrapper

**Description:** Create `scripts/odds_sources/the_odds_api.py` wrapping the existing `fetch_odds_api.py` functions into the `OddsSource` interface. This is a thin wrapper — it calls `run_full_scan()` from `fetch_odds_api.py` and returns the events list.

**Files:** `scripts/odds_sources/the_odds_api.py`

**Definition of Done:**
- [ ] Implements `OddsSource` ABC
- [ ] `fetch_odds()` delegates to existing `fetch_odds_api.run_full_scan()` logic
- [ ] `supported_sports()` returns sports that have non-empty `SPORT_KEY_MAP` entries
- [ ] Tags events with `_odds_source: "the-odds-api"`
- [ ] Handles API key loading via existing `get_api_key()` function

#### Task 3.3 - [CREATE] OddsPortal odds scraper source

**Description:** Create `scripts/odds_sources/oddsportal_scraper.py` — a Playwright-based scraper that navigates OddsPortal sport listing pages and extracts odds.

OddsPortal URL patterns:
- Football: `https://www.oddsportal.com/football/`
- Volleyball: `https://www.oddsportal.com/volleyball/`
- Handball: `https://www.oddsportal.com/handball/`
- Esports: `https://www.oddsportal.com/esports/`
- All other sports follow the same pattern

Extraction approach:
1. Navigate to `https://www.oddsportal.com/{sport}/` using `fetch_with_playwright.fetch()`
2. Parse HTML with the enhanced `oddsportal_adapter.parse()` (Task 3.5)
3. Transform adapter output `{home, away, odds, time}` into snapshot event format
4. Map odds array positions to markets: `odds[0]` = home win, `odds[1]` = draw, `odds[2]` = away win (for 1X2 sports)
5. Use `RateLimiter` with `"oddsportal-scraper"` name, 1 credit per page fetch

Sport → URL mapping should cover all 14 sports in the config.

**Files:** `scripts/odds_sources/oddsportal_scraper.py`

**Definition of Done:**
- [ ] Implements `OddsSource` ABC
- [ ] `supported_sports()` returns all 14 sports
- [ ] `fetch_odds()` navigates correct URL per sport, parses with enhanced adapter
- [ ] Odds correctly mapped to h2h market in snapshot format
- [ ] Uses `RateLimiter` for request tracking
- [ ] Handles Playwright errors gracefully (returns `[]` on failure)
- [ ] 3-second delay between page fetches (matching `FETCH_DELAY_SECONDS` in `scan_events.py`)

#### Task 3.4 - [CREATE] BetExplorer odds scraper source

**Description:** Create `scripts/odds_sources/betexplorer_scraper.py` — similar to OddsPortal scraper but for BetExplorer.

BetExplorer URL patterns:
- Football: `https://www.betexplorer.com/football/`
- Volleyball: `https://www.betexplorer.com/volleyball/`
- Handball: `https://www.betexplorer.com/handball/`
- Snooker: `https://www.betexplorer.com/snooker/`
- Esports: `https://www.betexplorer.com/esports/`
- All sports follow same pattern (already in `run_full_scan_and_prepare.sh`)

Uses `betexplorer_adapter.py` (Task 1.3) to parse HTML.

**Files:** `scripts/odds_sources/betexplorer_scraper.py`

**Definition of Done:**
- [ ] Implements `OddsSource` ABC
- [ ] `supported_sports()` returns all 14 sports
- [ ] `fetch_odds()` navigates correct URL per sport, parses with BetExplorer adapter
- [ ] Odds mapped to h2h market in snapshot format
- [ ] Uses `RateLimiter` for request tracking
- [ ] Handles errors gracefully

#### Task 3.5 - [MODIFY] Enhance OddsPortal adapter for structured odds

**Description:** Enhance `scripts/adapters/oddsportal_adapter.py` to return structured odds with market type information. Currently it returns raw `odds: [1.50, 3.40, 5.00]` arrays. Enhance to:
1. Determine sport from URL (2-outcome vs 3-outcome markets)
2. Map odds positions to named outcomes: for 3-way sports `{home_win: odds[0], draw: odds[1], away_win: odds[2]}`, for 2-way `{home_win: odds[0], away_win: odds[1]}`
3. Extract bookmaker name if visible in the row (OddsPortal shows "best odds" or specific bookmaker)
4. Add `market_type: "h2h"` to results

**Files:** `scripts/adapters/oddsportal_adapter.py`

**Definition of Done:**
- [ ] Results include `market_type` field (default: `"h2h"`)
- [ ] Results include `odds_structured` dict with named outcomes when position mapping is deterministic
- [ ] Raw `odds` array still present for backward compatibility
- [ ] Existing tests/usage unaffected

#### Task 3.6 - [CREATE] Betclic odds scraper source

**Description:** Create `scripts/odds_sources/betclic_scraper.py` that extracts odds from Betclic pages. The existing `betclic_adapter.py` already parses team names, times, and odds from Betclic's Angular SPA. This source wraps the adapter output into snapshot format.

Betclic URLs per sport (already in `run_full_scan_and_prepare.sh`):
- Football: `https://www.betclic.pl/pilka-nozna-s1`
- Tennis: `https://www.betclic.pl/tenis-s2`
- Volleyball: `https://www.betclic.pl/siatkowka-s18`
- etc.

Important: Betclic blocks automated scraping (403). The Playwright fetcher with cookie handling and storage state may bypass this for some pages. If it fails, this source returns empty results gracefully.

**Files:** `scripts/odds_sources/betclic_scraper.py`

**Definition of Done:**
- [ ] Implements `OddsSource` ABC
- [ ] `supported_sports()` returns all 14 configured sports
- [ ] `fetch_odds()` uses Playwright to fetch Betclic pages, parses with `betclic_adapter`
- [ ] Betclic odds transformed to snapshot format with `bookmaker: "betclic"`
- [ ] Handles 403 errors gracefully (returns `[]`)
- [ ] Uses `RateLimiter` with `"betclic-scraper"` name

---

### Phase 4: Unified Aggregator + Integration

**Goal:** Create the `fetch_odds_multi.py` CLI aggregator and integrate it into the pipeline.

#### Task 4.1 - [CREATE] Multi-source odds aggregator

**Description:** Create `scripts/fetch_odds_multi.py` — the main CLI entry point that replaces manual `fetch_odds_api.py` calls.

Behavior:
1. Load `config/betting_config.json` to get list of all 14 sports
2. For each sport, iterate through `SPORT_SOURCE_PRIORITY[sport]`
3. Call each source's `fetch_odds(sport, date_from, date_to)`
4. Merge results: if an event from source B matches one already found by source A, merge their bookmaker lists (don't duplicate)
5. If an event is new (not found in prior sources), add it to the list
6. After all sources processed, save:
   - `betting/data/odds_api_snapshot.json` — backward-compatible snapshot (same format as current)
   - `betting/data/odds_api_summary.csv` — same CSV format as current
   - `betting/data/odds_multi_sources.json` — provenance log: `{sport: {source: count, events: [ids]}}`
7. Print summary: events per sport, sources used, coverage gaps

CLI interface:
```
python3 scripts/fetch_odds_multi.py                        # full scan, all sports, all sources
python3 scripts/fetch_odds_multi.py --sports volleyball    # specific sport only
python3 scripts/fetch_odds_multi.py --sources the-odds-api,oddsportal  # specific sources only
python3 scripts/fetch_odds_multi.py --dry-run              # show what would be fetched, no API calls
```

**Files:** `scripts/fetch_odds_multi.py`

**Definition of Done:**
- [ ] CLI accepts `--sports`, `--sources`, `--dry-run`, `--no-window` flags
- [ ] Iterates sources in priority order per sport
- [ ] Events from multiple sources correctly merged by fuzzy team+time matching
- [ ] Output `odds_api_snapshot.json` is format-identical to existing (backward compatible)
- [ ] Output `odds_api_summary.csv` has same columns as existing
- [ ] Output `odds_multi_sources.json` tracks provenance (which source provided which event)
- [ ] Each event has `_odds_source` field indicating primary source
- [ ] Summary printed with events per sport and coverage info
- [ ] Errors from individual sources logged but don't abort entire scan

#### Task 4.2 - [MODIFY] Update pipeline orchestrator

**Description:** Modify `scripts/run_full_scan_and_prepare.sh` to call `fetch_odds_multi.py` instead of requiring a manual `fetch_odds_api.py` call. Add it as a new step after the scan (step 4.5 or renumber).

Currently the orchestrator has 10 steps and does NOT call odds fetching at all. Add:
```bash
echo "[4.5/11] Fetching multi-source odds..."
python3 "${SCRIPT_DIR}/fetch_odds_multi.py" || echo "[WARNING] Multi-source odds fetch failed — run fetch_odds_api.py manually"
```

**Files:** `scripts/run_full_scan_and_prepare.sh`

**Definition of Done:**
- [ ] New step calls `python3 scripts/fetch_odds_multi.py`
- [ ] Step numbering updated (10→11 steps)
- [ ] Failure does not abort pipeline (uses `||` fallback)
- [ ] Output files listed in final summary section

#### Task 4.3 - [MODIFY] Update source registry

**Description:** Update `betting/sources/source-registry.md` to document:
1. API-Football /odds as a Tier A market source (football only, deep coverage with 20+ bookmakers and 60+ bet types)
2. Multi-source aggregator system and the `fetch_odds_multi.py` command
3. Updated coverage table showing which sports are now covered

**Files:** `betting/sources/source-registry.md`

**Definition of Done:**
- [ ] API-Football /odds documented with endpoint, parameters, coverage, and usage
- [ ] Multi-source aggregator documented with CLI usage
- [ ] Coverage note updated: all 14 sports now have odds coverage via OddsPortal + BetExplorer fallback
- [ ] The Odds API "NOT covered" note updated to mention fallback sources

---

### Phase 5: Tests + Code Review

**Goal:** Comprehensive test coverage and final quality verification.

#### Task 5.1 - [CREATE] Unit tests for odds sources

**Description:** Create `tests/test_odds_sources.py` with tests for:
1. `OddsSource` ABC — verify interface enforcement
2. `normalize_team_name()` — various name formats
3. `events_match()` — same event from different sources, different team name spellings, edge cases
4. `merge_event_odds()` — bookmaker list merging, deduplication
5. `TheOddsAPISource` — mock `fetch_odds_api` functions
6. `APIFootballOddsSource` — mock API responses (covered partly in Task 2.3)
7. `OddsPortalScraper` — mock Playwright fetch + adapter parse
8. `BetExplorerScraper` — mock Playwright fetch + adapter parse
9. `BetclicScraper` — mock Playwright fetch + adapter parse

**Files:** `tests/test_odds_sources.py`

**Definition of Done:**
- [ ] At least 15 test cases covering all source implementations
- [ ] `normalize_team_name()` tested with 10+ name variants (FC, SC, unicode, extra spaces)
- [ ] `events_match()` tested with matching and non-matching pairs
- [ ] `merge_event_odds()` tested with overlapping and non-overlapping bookmaker lists
- [ ] Each scraper source tested with mocked Playwright output
- [ ] All tests pass with `pytest tests/test_odds_sources.py`

#### Task 5.2 - [CREATE] Integration test for multi-source aggregator

**Description:** Create an integration test that verifies the full `fetch_odds_multi.py` flow with all sources mocked. Verify that:
1. Events from multiple sources are correctly merged
2. Output files are written in correct format
3. Provenance tracking is accurate
4. Sports with no source coverage produce empty results (not errors)

**Files:** `tests/test_fetch_odds_multi.py`

**Definition of Done:**
- [ ] Integration test runs with all external calls mocked (no real API/Playwright calls)
- [ ] Verifies `odds_api_snapshot.json` format matches expected schema
- [ ] Verifies `odds_api_summary.csv` columns match existing format
- [ ] Verifies `odds_multi_sources.json` tracks source provenance correctly
- [ ] Verifies event deduplication works across sources

#### Task 5.3 - [REUSE] Code review by `tsh-code-reviewer` agent

**Description:** Run `tsh-code-reviewer` agent via `tsh-review.prompt.md` to review all new and modified files. Pass the following test commands:
```bash
cd /Users/mkoziol/projects/bet && .venv/bin/pytest tests/ -v
```

**Definition of Done:**
- [ ] Code review passes or all findings addressed
- [ ] All tests pass
- [ ] No security issues identified

## Security Considerations

- **API key exposure:** API-Football key is already in `config/api_keys.json` (git-ignored). No new keys needed. The `/odds` endpoint uses the same key as existing stats endpoints.
- **Playwright scraping:** All Playwright fetches go through `fetch_with_playwright.py` which uses randomized User-Agents and persistent storage state. No credentials are stored in scraper code.
- **Rate limiting:** All sources have daily caps enforced by `RateLimiter`. Playwright scrapers have 3-second delays between fetches. API sources use existing retry + backoff.
- **Path traversal:** All cache keys go through `_validate_cache_key()` in `base_client.py`. New sources must use the same pattern.
- **Input validation:** Team names from external sources are sanitized via `normalize_team_name()` before any file operations (cache keys derived from team names).
- **No new network listeners:** All code is client-side (outbound requests only). No servers created.

## Quality Assurance

Acceptance criteria checklist to verify the implementation meets the defined requirements:

- [ ] `python3 scripts/fetch_odds_multi.py` runs without errors and produces `odds_api_snapshot.json`
- [ ] `odds_api_snapshot.json` contains events from at least 3 different `_odds_source` values
- [ ] Volleyball events appear in `odds_api_snapshot.json` (previously missing)
- [ ] Handball events appear in `odds_api_snapshot.json` (previously missing)
- [ ] `odds_api_snapshot.json` format is backward-compatible (existing pipeline code that reads it still works)
- [ ] `odds_api_summary.csv` has the same columns as before
- [ ] `odds_multi_sources.json` correctly tracks which source provided each event
- [ ] Flashscore volleyball pages produce clean team names (no league headers merged)
- [ ] `scripts/run_full_scan_and_prepare.sh` includes the odds multi-fetch step
- [ ] All existing tests still pass: `pytest tests/ -v`
- [ ] All new tests pass: `pytest tests/test_odds_sources.py tests/test_flashscore_volleyball.py tests/test_betexplorer_adapter.py tests/test_api_football_odds.py tests/test_fetch_odds_multi.py -v`
- [ ] No API key is hardcoded in any source file
- [ ] Rate limiter enforces daily caps for all new sources

## Improvements (Out of Scope)

- **Sofascore API odds source:** Sofascore has an undocumented JSON API (`api.sofascore.com/api/v1/`) that includes odds data. Adding this as a 6th source would provide another programmatic API option. Deferred because the API is undocumented, may change without notice, and may block automated access.
- **Live/in-play odds:** Current system only handles pre-match odds. Live odds from OddsPortal/BetExplorer could be added as a separate mode.
- **Totals/handicap extraction from scrapers:** Playwright scrapers initially extract only h2h (1X2) odds. OddsPortal and BetExplorer have sub-pages for totals, handicaps, etc. These could be added as a follow-up to extract richer market data from scrapers.
- **Selenium fallback:** For sites that heavily fingerprint Playwright (e.g., Cloudflare-protected), a Selenium/undetected-chromedriver fallback could be added.
- **Odds movement tracking:** Store historical odds snapshots and detect significant line movements between scans.
- **BetsAPI integration:** Paid API with volleyball, handball, esports coverage. Could replace Playwright scrapers for reliability. Deferred due to cost.
- **Flashscore odds extraction:** Flashscore shows odds on match pages (via JS rendering). A Playwright scraper could extract these, adding another source. Complex due to heavy JS rendering.

## Changelog

| Date       | Change Description   |
| ---------- | -------------------- |
| 2026-04-29 | Initial plan created |
