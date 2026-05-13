# API Client Layer Overhaul — Implementation Plan

**Created:** 2026-05-13
**Status:** DRAFT
**Scope:** 10 phases — new PlaywrightBaseClient, 5 new site clients, unified.py fix, dead client cleanup, registry + debug scripts.
**Excludes:** Flashscore (`flashscore.py`) and Sofascore (`sofascore.py`) — already implemented.

---

## Architecture Overview

### Class Hierarchy (after overhaul)

```
BaseAPIClient (ABC) — base_client.py
├── APISportsClient (HTTP + x-apisports-key)
│   ├── APIFootballClient
│   ├── APIBasketballClient
│   ├── APIHockeyClient
│   └── APIVolleyballClient
├── ESPNClient (HTTP, no key)
├── BetExplorerClient (HTTP-first, optional Playwright fallback) ← NEW
├── SoccerwayClient (HTTP-first, optional Playwright fallback) ← NEW
├── PlaywrightBaseClient (stealth Playwright + circuit breaker) ← NEW
│   ├── FlashscoreClient (refactored to extend PlaywrightBaseClient)
│   ├── OddsPortalClient ← NEW
│   ├── TotalCornerClient ← NEW
│   └── Scores24Client ← NEW
└── UnifiedAPIClient (composite router) — unified.py [MODIFIED]
```

### Design Principles

1. **All clients return `APIFixture` / `APIMatchStats`** — consistent downstream interface.
2. **All clients use `RateLimiter`** — entries already exist for `betexplorer-scraper`, `oddsportal-scraper`.
3. **HTTP-first when possible** — BetExplorer (235 matches/day via HTTP) and Soccerway (38 matches via HTTP) don't need Playwright for listings.
4. **Playwright only for JS-rendered SPAs** — OddsPortal (0 matches via HTTP), TotalCorner, Scores24.
5. **Circuit breaker per-subclass** — OddsPortal blocked ≠ Scores24 blocked. Each subclass maintains own `_failures` / `_circuit_open` state.
6. **Reuse existing adapter selectors** — `scripts/adapters/` has working CSS selectors. Verify via debug scripts, then port into client JS extraction or BeautifulSoup parsing.
7. **Debug DOM first, implement second** — every Playwright client starts with `_debug_X.py` that dumps container hierarchy.

### Data Flow

```
scan_events.py / deep_stats_report.py / fetch_odds_multi.py
    ↓ imports
src/bet/api_clients/__init__.py → CLIENT_REGISTRY → get_client("betexplorer")
    ↓ returns
BetExplorerClient.get_fixtures(date, sport) → list[APIFixture]
BetExplorerClient.get_odds(event_url) → dict (bookmaker odds)
    ↓ all return
APIFixture / APIMatchStats dataclasses → DB upsert via repositories
```

---

## Phase 1: Create PlaywrightBaseClient

**Goal:** Extract shared Playwright boilerplate from `flashscore.py` into a reusable base class. All future Playwright clients extend this.

### Tasks

- [ ] **[CREATE] `src/bet/api_clients/playwright_base.py`**

  Extract from `flashscore.py` (lines 100–245):

  ```python
  class PlaywrightBaseClient(BaseAPIClient):
      """Base class for Playwright-based DOM scraping clients.
      
      Provides: stealth browser init, cookie dismiss, Cloudflare detection,
      circuit breaker, page loading with retry, resource cleanup.
      """
      
      # Circuit breaker — class-level, per-subclass (not shared)
      _failures: int = 0
      _circuit_open: bool = False
      _circuit_opened_at: float = 0
      _CIRCUIT_COOLDOWN: int = 300      # seconds
      _FAILURE_THRESHOLD: int = 3
      
      # Cookie consent selector — override in subclasses
      _COOKIE_SELECTOR: str = "#onetrust-accept-btn-handler"
      _COOKIE_TIMEOUT: int = 2500
      
      def __init__(self, api_name, base_url, rate_limiter):
          super().__init__(api_name, base_url, rate_limiter)
          self.api_key = "no-key"  # bypass base key check
          self._playwright = None
          self._browser = None
      
      def _ensure_browser(self): ...       # lazy Playwright launch
      def _new_page(self) -> tuple: ...    # stealth context + page
      def _dismiss_cookies(self, page): ...# configurable selector
      def _handle_cloudflare(self, page) -> bool: ...  # inner_text check
      def _load_page(self, url, wait_ms=5000, max_retries=2) -> tuple: ...
      def close(self): ...                 # browser + playwright cleanup
      def __enter__(self): return self
      def __exit__(...): self.close()
      def __del__(self): self.close()
  ```

  Methods to extract verbatim from `flashscore.py`:
  | Method | Source lines | Notes |
  |--------|-------------|-------|
  | `_ensure_browser` | 110–121 | Unchanged |
  | `_new_page` | 123–140 | Unchanged |
  | `_dismiss_cookies` | 142–149 | Make `_COOKIE_SELECTOR` configurable |
  | `_handle_cloudflare` | 151–164 | Unchanged |
  | `_load_page` | 166–212 | Use `type(self)._failures` for per-subclass circuit breaker |
  | `close` | 214–226 | Unchanged |
  | `__enter__/__exit__/__del__` | 228–233 | Unchanged |

  Additional methods to add:
  - `_evaluate_js(page, js_code)` → wrapper with error handling + logging
  - `is_available() -> bool` → always True (no API key needed)

- [ ] **[MODIFY] `src/bet/api_clients/flashscore.py`**

  Refactor to extend `PlaywrightBaseClient`:
  - Remove: `_ensure_browser`, `_new_page`, `_dismiss_cookies`, `_handle_cloudflare`, `_load_page`, `close`, `__enter__`, `__exit__`, `__del__`, circuit breaker class attrs
  - Add: `from .playwright_base import PlaywrightBaseClient`
  - Change: `class FlashscoreClient(BaseAPIClient)` → `class FlashscoreClient(PlaywrightBaseClient)`
  - Keep: All JS extraction constants, `get_fixtures`, `get_fixture_stats`, `get_h2h`, `get_match_preview`, `get_team_last_fixtures`, `_parse_stats_text`, `SPORT_SLUGS`, `STAT_NAME_MAP`
  - Override: `_COOKIE_SELECTOR = "#onetrust-accept-btn-handler"` (same as default, but explicit)

- [ ] **[CREATE] `specifications/playwright-base-selectors.md`**

  Document the generic selectors and patterns used by PlaywrightBaseClient:
  - Cloudflare: `"Just a moment"`, `"cf-browser-verification"` in page.content()
  - Block detection: `page.inner_text('body')` length < 500
  - Stealth: `Stealth().apply_stealth_sync(page)` from `playwright_stealth`
  - Common GDPR selectors by site (for reference)

### Definition of Done
- [x] `PlaywrightBaseClient` passes import test — `from bet.api_clients.playwright_base import PlaywrightBaseClient` works
- [x] `FlashscoreClient` still extends `BaseAPIClient` (through inheritance chain) — `isinstance(client, BaseAPIClient)` is True
- [x] `FlashscoreClient.get_fixtures()` returns same results as before refactor (behavioral equivalence)
- [x] No duplicated Playwright boilerplate remains in `flashscore.py`
- [x] Circuit breaker is per-subclass: `FlashscoreClient._failures` is independent of `OddsPortalClient._failures`
- [ ] `specifications/playwright-base-selectors.md` created (task was skipped)

### Code Review Findings (2026-05-13)

**BUGS / MUST FIX:**

1. **Unused import `Optional`** — `playwright_base.py` line 5 imports `from typing import Optional` but `Optional` is never used anywhere in the file. Remove it.

2. **Unreachable dead code in `_load_page`** — The final `raise APIError(f"{self.api_name.capitalize()} exhausted retries for {url}")` after the `for` loop (last line of `_load_page`) is unreachable. On the last retry iteration, every failure path either `return`s or `raise`s inside the loop. This line can never execute when `max_retries >= 1`. Remove it or replace it with `assert False, "unreachable"` so it's clearly intentional.

**INCOMPLETE TASKS:**

3. **`specifications/playwright-base-selectors.md` not created** — The plan's Phase 1 task list includes `[CREATE] specifications/playwright-base-selectors.md`. This was skipped. Low priority but DoD is incomplete.

**MINOR SMELLS (no action required unless cleaning up):**

4. **`is_available()` override is redundant** — `PlaywrightBaseClient.__init__` sets `self.api_key = "no-key"`. The base class `is_available()` returns `bool(self.api_key)` which is `True` for `"no-key"`. The override in `playwright_base.py` returns `True` unconditionally — correct but unnecessary.

5. **`scripts.stealth_utils` cross-boundary import** — `playwright_base.py` imports `USER_AGENTS`, `BROWSER_ARGS` from `scripts.stealth_utils` (a `scripts/` module). A `src/` package importing from `scripts/` creates a coupling that will break if `src/` is ever packaged standalone. Graceful fallback with inline defaults mitigates the risk for now.

### Dependencies
- None (first phase)

---

## Phase 2: Fix unified.py

**Goal:** Make `UnifiedAPIClient` resilient, sport-aware, and extensible. Remove Sofascore assumption. Add BetExplorer as a fixture discovery source.

### Tasks

- [ ] **[MODIFY] `src/bet/api_clients/unified.py`**

  Current problems:
  1. Only routes through Flashscore → ESPN (2 sources)
  2. No BetExplorer, OddsPortal, or other sources
  3. `get_fixture_stats` and `get_deep_data` only try Flashscore
  4. No graceful handling when Flashscore circuit breaker is open

  Changes:
  - Add configurable source priority per sport:
    ```python
    SOURCE_PRIORITY = {
        "football":   ["flashscore", "betexplorer", "espn"],
        "tennis":     ["flashscore", "espn"],
        "basketball": ["flashscore", "betexplorer", "espn"],
        "hockey":     ["flashscore", "betexplorer", "espn"],
        "volleyball": ["flashscore", "betexplorer", "espn"],
    }
    ```
  - Lazy-init clients: only create BetExplorerClient/FlashscoreClient when first needed
  - `get_fixtures()`: iterate SOURCE_PRIORITY[sport], try each, merge + dedup by team names
  - `get_fixture_stats()`: try Flashscore → BetExplorer (if odds are stats) → return []
  - `get_deep_data()`: try Flashscore → return partial result on failure
  - Add `_client_cache: dict[str, BaseAPIClient]` for lazy client reuse
  - Guard all Playwright client calls with try/except to prevent circuit breaker propagation

- [ ] **[MODIFY] `src/bet/api_clients/__init__.py`**

  Add `UnifiedAPIClient` to exports (currently not exported).

### Definition of Done
- [x] `UnifiedAPIClient().get_fixtures(date, "football")` returns fixtures even when Flashscore is down (falls through to ESPN)
- [x] `UnifiedAPIClient().get_fixtures(date, "volleyball")` works (currently no ESPN volleyball league configured well)
- [x] No crash when BetExplorerClient is not yet available (Phase 3) — graceful import guard
- [x] Context manager (`with UnifiedAPIClient() as client:`) cleans up all child clients

### Code Review Findings (2026-05-13)

**MINOR SMELLS (no action required unless cleaning up):**

1. **`source` parameter unused in `get_fixture_stats` and `get_deep_data`** — Both methods accept `source: str | None = None` but ignore it entirely, always routing to Flashscore. Either remove the parameter now (cleaner) or add a `# TODO: Phase 3 — route to BetExplorer when source="betexplorer"` comment to signal intent.

2. **ESPN clients not lazy-cached** — `get_fixtures()` creates a new `ESPNClient(sport, league)` instance on every call per league. This is by design (ESPN requires sport+league at construction time, so it can't be keyed by name alone), but worth noting when ESPN adds OAuth or session state.

3. **`get_fixture_stats` BetExplorer fallback missing** — Plan spec says "try Flashscore → BetExplorer → return []". The implementation only tries Flashscore. Acceptable as Phase 3 stub, but the fallback path should be added when `BetExplorerClient` ships.

### Dependencies
- Phase 1 (PlaywrightBaseClient for Flashscore)
- Phase 3 (BetExplorerClient) — can be done with import guard initially

---

## Phase 3: Create BetExplorer Client

**Goal:** HTTP-first client for BetExplorer (betexplorer.com). 235 matches/day confirmed via HTTP. Provides fixtures, odds comparison, and results across all 5 sports.

### Pre-work: Debug Script

- [ ] **[CREATE] `scripts/_debug_betexplorer.py`**

  Debug script to dump BetExplorer DOM structure:
  ```python
  # 1. Load https://www.betexplorer.com/football/ with requests (HTTP-first)
  # 2. Parse with BeautifulSoup
  # 3. Dump: table structure, row classes, team name selectors, odds cells
  # 4. Load a match detail page (e.g., /football/england/premier-league/...)
  # 5. Dump: odds table structure, bookmaker rows, market tabs
  # 6. Test with all 5 sports: /football/, /tennis/, /basketball/, /hockey/, /volleyball/
  ```

  Reference: `scripts/adapters/betexplorer_adapter.py` has existing selectors to verify.

### Client Implementation

- [ ] **[CREATE] `src/bet/api_clients/betexplorer.py`**

  ```python
  class BetExplorerClient(BaseAPIClient):
      """BetExplorer client — HTTP-first odds comparison and fixture discovery.
      
      Uses requests + BeautifulSoup for HTML parsing.
      Optional Playwright fallback for JS-heavy detail pages.
      """
      
      SPORT_PATHS = {
          "football": "/football/",
          "tennis": "/tennis/",
          "basketball": "/basketball/",
          "hockey": "/hockey/",
          "volleyball": "/volleyball/",
      }
      
      def __init__(self, rate_limiter): ...
      def get_fixtures(self, date, sport="football") -> list[APIFixture]: ...
      def get_odds(self, match_url) -> dict: ...
      def get_results(self, date, sport="football") -> list[dict]: ...
      def get_fixture_stats(self, fixture_id) -> list: ...  # odds as "stats"
      def get_h2h(self, team1_id, team2_id, last_n=10) -> list[dict]: ...
  ```

  Methods detail:
  | Method | URL Pattern | Parser | Returns |
  |--------|------------|--------|---------|
  | `get_fixtures` | `/next/soccer/` or `/football/?year={Y}&month={M}&day={D}` | BeautifulSoup | `list[APIFixture]` |
  | `get_odds` | `/football/{country}/{league}/{match}/` | BeautifulSoup | `dict` with bookmaker odds |
  | `get_results` | `/results/soccer/` or by date | BeautifulSoup | `list[dict]` with scores |
  | `get_fixture_stats` | N/A — returns odds data as stats proxy | — | `list` |
  | `get_h2h` | Match detail page H2H section | BeautifulSoup | `list[dict]` |

  Key implementation details:
  - HTTP session with proper headers (Accept, Referer, User-Agent)
  - BeautifulSoup HTML parsing (no Playwright for listings)
  - Cache responses via `_check_cache` / `_save_cache` from base class
  - Rate limiter: `"betexplorer-scraper"` (50 req/day in rate_limiter.py)
  - Date parameter: construct URL with `?year=2026&month=5&day=13` query params
  - Sport auto-detection from SPORT_PATHS
  - Normalize team names (strip whitespace, Unicode normalization)

### Definition of Done
- [ ] `BetExplorerClient().get_fixtures("2026-05-13", "football")` returns ≥50 APIFixture objects
- [ ] `BetExplorerClient().get_fixtures("2026-05-13", "tennis")` returns results
- [ ] `BetExplorerClient().get_odds(match_url)` returns dict with ≥1 bookmaker odds
- [ ] Rate limiter tracks requests under `"betexplorer-scraper"`
- [ ] Debug script `_debug_betexplorer.py` passes with all 5 sports
- [ ] Cached responses are stored under `betting/data/stats_cache/betexplorer/`

### Dependencies
- Phase 1 (for `BaseAPIClient` — already exists, no actual blocking dependency)

---

## Phase 4: Create OddsPortal Client

**Goal:** Playwright-based client for OddsPortal (oddsportal.com). SPA — 0 matches via HTTP. Provides odds comparison, dropping odds, value bets. Critical for price gap analysis.

### Pre-work: Debug Script

- [x] **[CREATE] `scripts/_debug_oddsportal.py`**

  Debug script to dump OddsPortal SPA DOM:
  ```python
  # 1. Launch stealth Playwright
  # 2. Navigate to https://www.oddsportal.com/matches/football/
  # 3. Wait for SPA to render (networkidle or specific selector)
  # 4. Dump: container hierarchy, match row structure, odds cell format
  # 5. Navigate to a match detail page
  # 6. Dump: odds table with bookmaker names, odds values, market tabs
  # 7. Test GDPR/cookie banner dismissal
  # 8. Test with: football, tennis, basketball, hockey
  ```

  Reference: `scripts/adapters/oddsportal_adapter.py` has 3 parsing strategies (structured divs, table rows, link-based).

### Client Implementation

- [x] **[CREATE] `src/bet/api_clients/oddsportal.py`**

  ```python
  class OddsPortalClient(PlaywrightBaseClient):
      """OddsPortal client — Playwright SPA for odds comparison.
      
      Extracts: match listings, bookmaker odds per match, dropping odds,
      odds movements, and best-odds highlighting.
      """
      
      _COOKIE_SELECTOR = "#onetrust-accept-btn-handler"  # verify via debug
      
      SPORT_PATHS = {
          "football": "/matches/football/",
          "tennis": "/matches/tennis/",
          "basketball": "/matches/basketball/",
          "hockey": "/matches/hockey/",
          "volleyball": "/matches/volleyball/",
      }
      
      def __init__(self, rate_limiter): ...
      def get_fixtures(self, date, sport="football") -> list[APIFixture]: ...
      def get_odds(self, match_url) -> dict: ...
      def get_dropping_odds(self, sport="football") -> list[dict]: ...
      def get_fixture_stats(self, fixture_id) -> list: ...
      def get_h2h(self, team1_id, team2_id, last_n=10) -> list[dict]: ...
  ```

  Methods detail:
  | Method | URL Pattern | Extraction | Returns |
  |--------|------------|------------|---------|
  | `get_fixtures` | `/matches/football/{date}/` | JS evaluate → DOM rows | `list[APIFixture]` |
  | `get_odds` | `/football/{country}/{league}/{match}/` | JS evaluate → odds table | `dict` with multi-bookmaker odds |
  | `get_dropping_odds` | `/dropping-odds/` | JS evaluate → dropping odds table | `list[dict]` |
  | `get_fixture_stats` | delegates to `get_odds` | — | `list` |
  | `get_h2h` | Match detail page → H2H tab | JS evaluate | `list[dict]` |

  Key implementation details:
  - Extends `PlaywrightBaseClient` (Playwright required — pure SPA)
  - Cookie/GDPR dismissal (selector TBD — discover via debug script)
  - Wait for SPA render: `page.wait_for_selector(".eventRow, [class*='event']", timeout=15000)`
  - Rate limiter: `"oddsportal-scraper"` (50 req/day)
  - JS extraction functions for match listings + odds tables
  - Handle pagination (OddsPortal paginates match listings)
  - Parse odds format: decimal (EU) — OddsPortal defaults to decimal in EU locale

### Definition of Done
- [x] `OddsPortalClient().get_fixtures("2026-05-13", "football")` returns ≥20 APIFixture objects (50 fixtures, 24 leagues)
- [ ] `OddsPortalClient().get_odds(match_url)` returns dict with ≥3 bookmaker odds (JS extraction implemented, live test pending)
- [ ] `get_dropping_odds()` returns list of events with original and current odds (stub implemented, reuses fixture extractor)
- [x] Circuit breaker triggers after 3 consecutive failures and resets after 300s (per-subclass isolation verified)
- [x] Debug script `_debug_oddsportal.py` runs successfully (discovered all selectors)
- [x] Context manager properly cleans up Playwright resources (verified with `with` statement)

### Dependencies
- Phase 1 (PlaywrightBaseClient)

---

## Phase 5: Create TotalCorner Client

**Goal:** Playwright-based client for TotalCorner (totalcorner.com). Football-only. Provides corner predictions, averages, and handicap lines. Critical for football statistical markets (R5).

### Pre-work: Debug Script

- [x] **[CREATE] `scripts/_debug_totalcorner.py`** ✅ Created + run. DOM: `#inplay_match_table`, 333 rows, Quantcast CMP2 cookie.

### Client Implementation

- [x] **[CREATE] `src/bet/api_clients/totalcorner.py`** ✅ 45/45 tests pass. Code review fixes applied (M1-M3, m1-m8).

  ```python
  class TotalCornerClient(PlaywrightBaseClient):
      """TotalCorner client — football corner predictions via Playwright.
      
      Provides: corner averages, corner handicap lines, dangerous attack stats,
      over/under corner predictions, and half-time corner data.
      Football only.
      """
      
      def __init__(self, rate_limiter): ...
      def get_fixtures(self, date, sport="football") -> list[APIFixture]: ...
      def get_corner_predictions(self, match_url) -> dict: ...
      def get_fixture_stats(self, fixture_id) -> list: ...
      def get_h2h(self, team1_id, team2_id, last_n=10) -> list[dict]: ...
  ```

  Methods detail:
  | Method | URL Pattern | Extraction | Returns |
  |--------|------------|------------|---------|
  | `get_fixtures` | `/match/today` or `/match/YYYYMMDD` | JS evaluate → match table | `list[APIFixture]` |
  | `get_corner_predictions` | `/match/{id}/corner/` | JS evaluate → corner stats | `dict` with corner data |
  | `get_fixture_stats` | Wraps `get_corner_predictions` | — | `list[dict]` (corner stats as stats) |
  | `get_h2h` | Not available on TotalCorner | — | `[]` (empty — not supported) |

  Key output from `get_corner_predictions`:
  ```python
  {
      "home_corner_avg": 5.2,
      "away_corner_avg": 4.1,
      "total_corner_avg": 9.3,
      "corner_handicap": -1.0,  # home favored by 1 corner
      "over_under_line": 9.5,
      "dangerous_attacks_home": 45.2,
      "dangerous_attacks_away": 38.7,
      "ht_corner_avg": 4.8,
  }
  ```

  Key implementation details:
  - Football only — `get_fixtures` ignores sport parameter (always football)
  - Rate limiter: add `"totalcorner-scraper"` to `API_DAILY_LIMITS` (suggest 50/day)
  - Cache corner predictions per match: `betting/data/stats_cache/totalcorner/{match_id}.json`
  - Corner data integrates with safety score computation for corners markets

### Definition of Done
- [x] `TotalCornerClient().get_fixtures("2026-05-13")` returns APIFixture objects ✅
- [x] `TotalCornerClient().get_corner_predictions(url)` returns dict with corner averages ✅
- [ ] Data feeds into `compute_safety_scores.py` corner market analysis
- [x] Debug script `_debug_totalcorner.py` dumps valid selectors ✅
- [x] Rate limiter entry added to `rate_limiter.py` ✅ (50/day)

### Dependencies
- Phase 1 (PlaywrightBaseClient)

---

## Phase 6: Create Scores24 Client

**Goal:** Playwright-based client for Scores24 (scores24.live). Multi-sport deep data source with H2H, form, odds, and structured betting trends with hit rates.

### Pre-work: Debug Script

- [x] **[CREATE] `scripts/_debug_scores24.py`** ✅ Created + run. React SPA, styled-components, `a[href*="/m-"]` links, body text parsing.

### Client Implementation

- [x] **[CREATE] `src/bet/api_clients/scores24.py`** ✅ 45/45 tests pass. Dual parsing (JS links + body text). Code review fixes applied.

  ```python
  class Scores24Client(PlaywrightBaseClient):
      """Scores24 client — multi-sport deep data via Playwright.
      
      Provides: fixture listings, H2H with match scores, team form (last 5-10),
      multi-bookmaker odds, and structured betting trends with hit rates.
      """
      
      SPORT_PATHS = {
          "football": "/en/soccer",
          "tennis": "/en/tennis",
          "basketball": "/en/basketball",
          "hockey": "/en/ice-hockey",
          "volleyball": "/en/volleyball",
      }
      
      def __init__(self, rate_limiter): ...
      def get_fixtures(self, date, sport="football") -> list[APIFixture]: ...
      def get_match_detail(self, detail_url) -> dict: ...
      def get_trends(self, detail_url) -> list[dict]: ...
      def get_fixture_stats(self, fixture_id) -> list: ...
      def get_h2h(self, team1_id, team2_id, last_n=10) -> list[dict]: ...
  ```

  Methods detail:
  | Method | URL Pattern | Extraction | Returns |
  |--------|------------|------------|---------|
  | `get_fixtures` | `/en/soccer` | JS evaluate → match links | `list[APIFixture]` |
  | `get_match_detail` | `/en/soccer/m-{DD-MM-YYYY}-{slug}` | JS evaluate → full match data | `dict` (h2h, form, odds, info) |
  | `get_trends` | Detail URL + `#trends` | JS evaluate → trend categories | `list[dict]` with hit rates |
  | `get_fixture_stats` | Wraps `get_match_detail` → extracts stats | — | `list[dict]` |
  | `get_h2h` | Wraps `get_match_detail` → extracts h2h | — | `list[dict]` |

  Key output from `get_match_detail`:
  ```python
  {
      "match_info": {"home": "...", "away": "...", "tournament": "...", "venue": "..."},
      "odds": {"w1": 1.85, "x": 3.40, "w2": 4.20, "handicap": {...}, "totals": {...}},
      "h2h": [{"home": "...", "away": "...", "score": "2:1", "date": "..."}, ...],
      "form_home": [{"opponent": "...", "result": "W", "score": "3:1"}, ...],
      "form_away": [...],
      "trends": [
          {"category": "Over/Under", "tip": "Over 2.5", "hit_count": 7, "sample_size": 10, "hit_rate": 0.70, "odds": 1.85},
          ...
      ]
  }
  ```

  Key implementation details:
  - Multi-sport: maps sport names to URL paths (soccer, ice-hockey differ from internal names)
  - Rate limiter: add `"scores24-scraper"` to `API_DAILY_LIMITS` (suggest 100/day)
  - Trends are the unique value — structured hit rates are rare in free sources
  - Cache detail pages: `betting/data/stats_cache/scores24/{sport}/{match_slug}.json`
  - Cookie dismissal selector: TBD via debug script

### Definition of Done
- [x] `Scores24Client().get_fixtures("2026-05-13", "football")` returns APIFixture objects ✅
- [x] `Scores24Client().get_match_detail(url)` returns dict with h2h, odds ✅ (form_home/form_away = TODO)
- [x] `get_trends(url)` returns trends with parsed categories ✅
- [x] Works for all 5 sports (SPORT_PATHS verified) ✅
- [x] Debug script `_debug_scores24.py` runs successfully ✅
- [x] Rate limiter entry added ✅ (100/day)

### Dependencies
- Phase 1 (PlaywrightBaseClient)

---

## Phase 7: Create Soccerway Client

**Goal:** HTTP-first client for Soccerway (soccerway.com). Covers 200+ countries and 1000+ leagues — primary exotic league fixture discovery source. 38 matches confirmed via HTTP.

### Pre-work: Debug Script

- [x] **[CREATE] `scripts/_debug_soccerway.py`**

  Debug script — discovered that Soccerway is a JS SPA (LiveSport Media, same as Flashscore).
  HTTP returns empty SPA shell — requires Playwright for rendering.
  DOM uses same `event__match` classes as Flashscore.

### Client Implementation

- [x] **[CREATE] `src/bet/api_clients/soccerway.py`**

  **NOTE (2026-05-13):** Plan assumed HTTP-first but Soccerway is a JS SPA (LiveSport Media).
  Implemented as PlaywrightBaseClient subclass instead. 228 fixtures extracted successfully.

  ```python
  class SoccerwayClient(PlaywrightBaseClient):
      """Soccerway client — Playwright SPA for football fixture discovery.
      
      Covers 200+ countries, 1000+ leagues.
      Football only (soccerway.com is football-specific).
      """
      
      def __init__(self, rate_limiter): ...
      def get_fixtures(self, date, sport="football") -> list[APIFixture]: ...
      def get_standings(self, competition_url) -> list[dict]: ...
      def get_match_detail(self, match_url) -> dict: ...
      def get_fixture_stats(self, fixture_id) -> list: ...
      def get_h2h(self, team1_id, team2_id, last_n=10) -> list[dict]: ...
  ```

  Methods detail:
  | Method | URL Pattern | Parser | Returns |
  |--------|------------|--------|---------|
  | `get_fixtures` | `/matches/YYYY/MM/DD/` | BeautifulSoup | `list[APIFixture]` |
  | `get_standings` | `/national/{country}/{league}/YYYY/regular-season/tables/` | BeautifulSoup | `list[dict]` |
  | `get_match_detail` | `/matches/YYYY/MM/DD/{country}/{league}/{match}/` | BeautifulSoup | `dict` (venue, referee, H2H) |
  | `get_fixture_stats` | Match detail page → stats section | BeautifulSoup | `list[dict]` |
  | `get_h2h` | Match detail page → H2H section | BeautifulSoup | `list[dict]` |

  Key implementation details:
  - Football only — `get_fixtures` ignores sport parameter
  - HTTP-first: `requests` + `BeautifulSoup` (no Playwright for listings)
  - Soccerway selectors: `.team-a`, `.team-b`, `.score-time` (from adapter)
  - League headers: `.group-head` class for competition context
  - Rate limiter: add `"soccerway-scraper"` to `API_DAILY_LIMITS` (suggest 100/day)
  - Absolute match URLs (not relative — adapter already handles this)
  - Cache per date: `betting/data/stats_cache/soccerway/fixtures_{date}.json`

### Definition of Done
- [x] `SoccerwayClient().get_fixtures("2026-05-13")` returns ≥30 APIFixture objects — **228 fixtures across 89 competitions**
- [x] Fixtures include competition_name with country prefix (e.g., "ANGLIA: Premier League")
- [ ] `get_match_detail(url)` returns venue and lineup info when available
- [x] Debug script `_debug_soccerway.py` confirms selectors work
- [x] Rate limiter entry added (`soccerway-scraper: 100/day`)

### Dependencies
- Phase 1 (PlaywrightBaseClient) — required since Soccerway is a JS SPA

---

## Phase 8: Cleanup Dead Clients

**Goal:** Mark broken legacy clients as deprecated. Remove from fallback chains. Update registry.

### Tasks

- [ ] **[MODIFY] `scripts/api_clients/balldontlie.py`**
  - Add deprecation header: `# DEPRECATED 2026-05-11 — v1 API deprecated, 100% failure rate. DO NOT USE.`
  - Ensure `_HOST_BROKEN = True` is set (already is)
  - Override `get_fixtures()` to return `[]` immediately with warning log

- [ ] **[MODIFY] `scripts/api_clients/thesportsdb.py`**
  - Add deprecation header: `# DEPRECATED 2026-05-11 — 97.8% failure rate. DO NOT USE.`
  - Ensure `_HOST_BROKEN = True` is set (already is)
  - Override `get_fixtures()` to return `[]` immediately with warning log

- [ ] **[MODIFY] `scripts/api_clients/api_tennis.py`**
  - Add deprecation header: `# DEPRECATED 2026-05-11 — NXDOMAIN. Host does not resolve. DO NOT USE.`
  - Ensure `_HOST_BROKEN = True` is set (already is)
  - Override `get_fixtures()` to return `[]` immediately with warning log

- [ ] **[MODIFY] `scripts/api_clients/__init__.py`**
  - Remove broken clients from scripts-level CLIENT_REGISTRY (if registered)
  - Add comment explaining why they're excluded

- [ ] **[MODIFY] `betting/sources/source-registry.md`**
  - Move BallDontLie, TheSportsDB, API-Tennis to a "## Deprecated / Broken Sources" section
  - Add deprecation dates and reasons

### Definition of Done
- [ ] All 3 broken clients have `_HOST_BROKEN = True` and deprecation headers
- [ ] `get_fixtures()` on broken clients returns `[]` without making HTTP requests
- [ ] No broken client is registered in any CLIENT_REGISTRY
- [ ] source-registry.md has a clear "Deprecated" section

### Dependencies
- None (independent of all other phases)

---

## Phase 9: Update Registry and Routing

**Goal:** Register all new clients in CLIENT_REGISTRY. Update unified.py routing.

### Tasks

- [ ] **[MODIFY] `src/bet/api_clients/__init__.py`**

  Add registrations:
  ```python
  from bet.api_clients.betexplorer import BetExplorerClient
  CLIENT_REGISTRY["betexplorer"] = BetExplorerClient
  
  from bet.api_clients.oddsportal import OddsPortalClient
  CLIENT_REGISTRY["oddsportal"] = OddsPortalClient
  
  from bet.api_clients.totalcorner import TotalCornerClient
  CLIENT_REGISTRY["totalcorner"] = TotalCornerClient
  
  from bet.api_clients.scores24 import Scores24Client
  CLIENT_REGISTRY["scores24"] = Scores24Client
  
  from bet.api_clients.soccerway import SoccerwayClient
  CLIENT_REGISTRY["soccerway"] = SoccerwayClient
  ```

  Use lazy imports with try/except ImportError guards (like the existing scripts fallback pattern).

- [ ] **[MODIFY] `src/bet/api_clients/rate_limiter.py`**

  Add new entries to `API_DAILY_LIMITS`:
  ```python
  "totalcorner-scraper": 50,
  "scores24-scraper": 100,
  "soccerway-scraper": 100,
  ```
  
  (betexplorer-scraper and oddsportal-scraper already exist at 50/day)

- [ ] **[MODIFY] `src/bet/api_clients/unified.py`**

  Update source priority table (from Phase 2 changes) to include all new clients:
  ```python
  SOURCE_PRIORITY = {
      "football":   ["flashscore", "betexplorer", "soccerway", "espn"],
      "tennis":     ["flashscore", "scores24", "espn"],
      "basketball": ["flashscore", "betexplorer", "scores24", "espn"],
      "hockey":     ["flashscore", "betexplorer", "scores24", "espn"],
      "volleyball": ["flashscore", "betexplorer", "scores24", "espn"],
  }
  
  # Odds-specific routing (separate from fixture discovery)
  ODDS_PRIORITY = {
      "football":   ["oddsportal", "betexplorer"],
      "tennis":     ["oddsportal", "betexplorer"],
      "basketball": ["oddsportal", "betexplorer"],
      "hockey":     ["oddsportal", "betexplorer"],
      "volleyball": ["oddsportal", "betexplorer"],
  }
  
  # Stats-specific routing (for corner/card data)
  STATS_PRIORITY = {
      "football": ["totalcorner", "flashscore"],  # TotalCorner is corner-specific
  }
  ```

- [ ] **[MODIFY] `betting/sources/source-registry.md`**

  Update "API Fallback Chains" section to reflect new clients:
  ```
  Football fixtures:   Flashscore → BetExplorer → Soccerway → ESPN
  Football corners:    TotalCorner → Flashscore → ESPN
  Tennis fixtures:     Flashscore → Scores24 → ESPN
  Basketball fixtures: Flashscore → BetExplorer → Scores24 → ESPN
  Hockey fixtures:     Flashscore → BetExplorer → Scores24 → ESPN
  Volleyball fixtures: Flashscore → BetExplorer → Scores24 → ESPN
  
  Odds comparison:     OddsPortal → BetExplorer (all sports)
  Trends/hit rates:    Scores24 (all sports)
  ```

### Definition of Done
- [x] `get_client("betexplorer")` returns a `BetExplorerClient` instance
- [x] `get_client("oddsportal")` returns an `OddsPortalClient` instance
- [x] All 5 new clients registered in CLIENT_REGISTRY
- [x] Rate limiter has entries for all new scraper clients
- [x] source-registry.md reflects the new fallback chains
- [x] `UnifiedAPIClient` routes through the full priority chain

### Dependencies
- Phases 3-7 (all new clients must exist)

---

## Phase 10: Debug Scripts

**Goal:** Ensure every new Playwright client has a debug script for DOM discovery and selector validation. Scripts listed here that aren't covered in per-phase pre-work.

### Tasks

All debug scripts follow the same template:

```python
#!/usr/bin/env python3
"""Debug DOM structure for {SiteName}.

Dumps container hierarchy, team name selectors, odds cells, and league headers.
Run BEFORE implementing the client to discover correct CSS selectors.

Usage: PYTHONPATH=src python3 scripts/_debug_{name}.py [--sport football]
"""
import argparse
import sys
from playwright.sync_api import sync_playwright
try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None
try:
    from scripts.stealth_utils import USER_AGENTS, BROWSER_ARGS
except ImportError:
    USER_AGENTS = ["Mozilla/5.0 ..."]
    BROWSER_ARGS = ['--disable-blink-features=AutomationControlled']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", default="football")
    args = parser.parse_args()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=BROWSER_ARGS)
        ctx = browser.new_context(user_agent=random.choice(USER_AGENTS), viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()
        if Stealth:
            Stealth().apply_stealth_sync(page)
        
        # 1. Load listing page
        url = SPORT_URLS[args.sport]
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # 2. Dump body text length (block detection)
        body = page.inner_text('body')
        print(f"Body text length: {len(body)}")
        
        # 3. Dump container hierarchy
        hierarchy = page.evaluate("""() => {
            const dump = [];
            const walk = (el, depth) => {
                if (depth > 4) return;
                const classes = el.className || '';
                const id = el.id || '';
                if (classes || id) {
                    dump.push('  '.repeat(depth) + el.tagName + (id ? '#' + id : '') + (classes ? '.' + classes.split(' ').join('.') : ''));
                }
                for (const child of el.children) walk(child, depth + 1);
            };
            walk(document.body, 0);
            return dump.slice(0, 100);  // first 100 elements
        }""")
        for line in hierarchy:
            print(line)
        
        # 4. Dump first match row innerHTML
        first_row = page.evaluate("""() => {
            const row = document.querySelector('[class*="match"], [class*="event"], tr');
            return row ? row.innerHTML.substring(0, 500) : 'NO MATCH ROW FOUND';
        }""")
        print(f"\nFirst match row (500 chars):\n{first_row}")
        
        ctx.close()
        browser.close()

if __name__ == "__main__":
    main()
```

- [ ] **[VERIFY] `scripts/_debug_betexplorer.py`** — created in Phase 3
- [ ] **[VERIFY] `scripts/_debug_oddsportal.py`** — created in Phase 4
- [ ] **[VERIFY] `scripts/_debug_totalcorner.py`** — created in Phase 5
- [ ] **[VERIFY] `scripts/_debug_scores24.py`** — created in Phase 6
- [ ] **[VERIFY] `scripts/_debug_soccerway.py`** — created in Phase 7

Each debug script must verify:
1. Page loads without block (body text > 500 chars)
2. Match rows are identifiable via CSS selectors
3. Team names can be extracted
4. League/competition headers are present
5. For detail pages: odds cells are extractable
6. For each applicable sport (test all 5 where supported)

### Definition of Done
- [x] All 5 debug scripts exist and run without errors
- [x] Each script produces structured output showing: body length, container hierarchy, first match row
- [x] Selectors documented in each client's source code match what debug scripts discover

### Dependencies
- Phases 3-7 (run alongside each phase's pre-work)

---

## Execution Order

```
Phase 1 ────────────────────────────┐
                                    ├─→ Phase 2 (unified.py)
Phase 8 (cleanup, independent) ─────┤
                                    │
Phase 3 (BetExplorer, HTTP) ────────┤
Phase 7 (Soccerway, HTTP) ──────────┤
                                    │
Phase 4 (OddsPortal, Playwright) ───┤ ← all depend on Phase 1
Phase 5 (TotalCorner, Playwright) ──┤
Phase 6 (Scores24, Playwright) ─────┤
                                    │
                                    └─→ Phase 9 (registry) → Phase 10 (verify debug scripts)
```

**Parallelizable:**
- Phase 3 + Phase 7 (both HTTP-first, independent)
- Phase 4 + Phase 5 + Phase 6 (all Playwright, independent, all depend only on Phase 1)
- Phase 8 (independent of everything)

**Sequential:**
- Phase 1 → Phase 2 (unified.py needs PlaywrightBaseClient for graceful Flashscore handling)
- Phase 1 → Phases 4/5/6 (Playwright clients need PlaywrightBaseClient)
- All phases → Phase 9 (registry needs all clients)
- Phase 9 → Phase 10 (final verification)

---

## Security Considerations

1. **Path traversal prevention:** All cache keys validated via `BaseAPIClient._validate_cache_key()` — rejects `..` and absolute paths.
2. **Input validation:** Date parameters validated with `re.fullmatch(r"\d{4}-\d{2}-\d{2}", date)` before URL construction.
3. **No user-supplied URLs in Playwright:** URLs constructed from known base URLs + validated parameters only. Never pass arbitrary user URLs to `page.goto()`.
4. **Rate limiting as DoS prevention:** All clients use `RateLimiter` to cap daily requests and prevent abusing target sites.
5. **Resource cleanup:** `PlaywrightBaseClient` enforces browser cleanup via `__del__`, `__exit__`, and explicit `close()`. Prevents browser process leaks.
6. **Cookie consent:** Explicit opt-in click on known GDPR selectors only — no arbitrary JS execution for consent.
7. **Stealth mode:** Prevents detection and blocking, reducing the risk of IP bans that could affect the user's network.

## Quality Assurance

1. **Debug script first:** Every Playwright client starts with a debug script that dumps live DOM — no guessing selectors.
2. **Behavioral tests per client:** Each client must have at minimum:
   - `test_get_fixtures_returns_list` — verifies return type and APIFixture structure
   - `test_rate_limiter_integration` — verifies requests are tracked
   - `test_circuit_breaker` — verifies failure threshold and cooldown
3. **Integration test:** `unified.py` end-to-end test with mocked clients to verify fallback routing.
4. **Regression test for FlashscoreClient:** After Phase 1 refactor, run existing Flashscore tests to confirm behavioral equivalence.
5. **Adapter cross-reference:** For each new client, compare output against existing `scripts/adapters/` output to ensure consistency (same teams, same leagues, same fixture counts ±10%).

---

## Files Summary

### New Files (10)
| File | Phase | Type |
|------|-------|------|
| `src/bet/api_clients/playwright_base.py` | 1 | Base class |
| `src/bet/api_clients/betexplorer.py` | 3 | HTTP client |
| `src/bet/api_clients/oddsportal.py` | 4 | Playwright client |
| `src/bet/api_clients/totalcorner.py` | 5 | Playwright client |
| `src/bet/api_clients/scores24.py` | 6 | Playwright client |
| `src/bet/api_clients/soccerway.py` | 7 | HTTP client |
| `scripts/_debug_betexplorer.py` | 3 | Debug script |
| `scripts/_debug_oddsportal.py` | 4 | Debug script |
| `scripts/_debug_totalcorner.py` | 5 | Debug script |
| `scripts/_debug_scores24.py` | 6 | Debug script |
| `scripts/_debug_soccerway.py` | 7 | Debug script |
| `specifications/playwright-base-selectors.md` | 1 | Documentation |

### Modified Files (8)
| File | Phase | Changes |
|------|-------|---------|
| `src/bet/api_clients/flashscore.py` | 1 | Refactor to extend PlaywrightBaseClient |
| `src/bet/api_clients/unified.py` | 2, 9 | Resilient routing with new clients |
| `src/bet/api_clients/__init__.py` | 9 | Register 5 new clients |
| `src/bet/api_clients/rate_limiter.py` | 9 | Add 3 new rate limit entries |
| `scripts/api_clients/balldontlie.py` | 8 | Add deprecation header |
| `scripts/api_clients/thesportsdb.py` | 8 | Add deprecation header |
| `scripts/api_clients/api_tennis.py` | 8 | Add deprecation header |
| `betting/sources/source-registry.md` | 8, 9 | Update fallback chains, add deprecated section |
