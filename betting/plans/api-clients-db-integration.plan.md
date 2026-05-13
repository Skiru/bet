# Phase 11 — API Client DB Integration Plan

**Created:** 2026-05-13
**Status:** DRAFT
**Scope:** 8 phases — wire existing API client methods into pipeline scripts with DB persistence.
**Depends on:** Phases 1–10 (API Client Layer Overhaul) — all clients implemented and tested.
**Excludes:** API client code changes (Phase 1-10 is frozen). No new DB tables unless absolutely necessary.

---

## Architecture Overview

### Current State

```
scan_events.py ──→ UnifiedAPIClient.get_fixtures() ──→ FixtureRepo.upsert() ✅ DB
scan_events.py ──→ UnifiedAPIClient.get_deep_data() ──→ JSON output ONLY ❌ No DB
data_enrichment_agent.py ──→ raw HTTP + stealth_fetcher ──→ StatsRepo ⚠️ Bypasses clients
fetch_odds_multi.py ──→ scripts/odds_sources/ registry ──→ OddsRepo ⚠️ Bypasses clients
enrichment.py ──→ ESPN + API-Sports ──→ StatsRepo ⚠️ Missing client fallbacks
TotalCorner corner predictions ──→ NOT CALLED ❌
Scores24 trends ──→ NOT CALLED ❌
OddsPortal dropping odds ──→ NOT CALLED ❌
```

### Target State

```
scan_events.py ──→ UnifiedAPIClient.get_fixtures() ──→ FixtureRepo.upsert() ✅
scan_events.py ──→ UnifiedAPIClient.get_deep_data() ──→ StatsRepo + JSON ✅
data_enrichment_agent.py ──→ UnifiedAPIClient (Flashscore/Scores24) ──→ StatsRepo ✅
fetch_odds_multi.py ──→ UnifiedAPIClient.get_odds() + existing sources ──→ OddsRepo ✅
enrichment.py ──→ ESPN → API-Sports → FlashscoreClient → Scores24Client ──→ StatsRepo ✅
TotalCorner ──→ UnifiedAPIClient.get_fixture_stats("football") ──→ team_form ✅
Scores24 trends ──→ UnifiedAPIClient ──→ team_form or match_stats ✅
OddsPortal dropping odds ──→ odds_evaluator.py or fetch_odds_multi ──→ odds_history ✅
```

### Data Flow Contracts (R18)

| Producer | Output Format | Consumer | Input Format | Status |
|----------|--------------|----------|-------------|--------|
| `FlashscoreClient.get_fixture_stats()` | `list[APIMatchStats]` | `StatsRepo.save_match_stats()` | `(fixture_id, team_id, dict[str,float], source)` | NEEDS ADAPTER |
| `FlashscoreClient.get_match_preview()` | `dict` with `form_home`, `form_away`, `h2h` | `StatsRepo.save_team_form()` | `TeamForm` dataclass | NEEDS ADAPTER |
| `Scores24Client.get_trends()` | `list[dict]` with `category`, `tip`, `odds`, `description` | `StatsRepo.save_team_form()` | `TeamForm` dataclass | NEEDS ADAPTER |
| `TotalCornerClient.get_corner_predictions()` | `dict` with corner/DA data | `StatsRepo.save_team_form()` | `TeamForm` with `stat_key="corners_predicted"` | NEEDS ADAPTER |
| `OddsPortalClient.get_odds()` | `dict` with `bookmakers`, `average` | `OddsRepo.save()` | `OddsRecord` dataclass | NEEDS ADAPTER |
| `OddsPortalClient.get_dropping_odds()` | `list[dict]` with `url`, `text` | `OddsRepo.save()` | `OddsRecord` dataclass | NEEDS ADAPTER |
| `BetExplorerClient.get_odds()` | `dict` from listing page | `OddsRepo.save()` | `OddsRecord` dataclass | NEEDS ADAPTER |

---

## Phase 1: data_enrichment_agent.py → API Client Migration

**Goal:** Replace direct HTML scraping in `data_enrichment_agent.py` with `UnifiedAPIClient` calls. Keep the same DB write path (`StatsRepo.save_team_form()`). This eliminates duplicated Playwright management, rate limiting, and stealth logic already handled by the client layer.

**Priority:** HIGHEST — this is the biggest gap. The enrichment script runs for 5–10 minutes per betting day, scraping the same sites the clients already handle, but with inferior error handling and no circuit breaker.

**Risk:** MEDIUM — behavioral change in a critical pipeline script. Mitigated by keeping the same DB write path and adding the client as a new source layer, not replacing all existing code at once.

**Dependencies:** None (Phase 1-10 complete)

### Tasks

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Add UnifiedAPIClient as primary enrichment source

  **What changes:**
  1. Import `UnifiedAPIClient` from `bet.api_clients.unified`
  2. Add new function `_try_client_enrichment(team_name, sport, stat_keys)` that:
     - Creates/reuses a singleton `UnifiedAPIClient` (similar to `scan_events.py` pattern)
     - Calls `client.get_fixture_stats()` for the team's recent fixtures
     - Converts `APIMatchStats` / raw stat dicts → `{stat_key: [values]}` format
     - Returns `(stats_dict, error_or_none)` — same signature as `_try_flashscore()`
  3. Update `enrich_team()` call order: **client first** → Flashscore HTML fallback → Scores24 HTML fallback
  4. Update `enrich_team_deep()` to try `client.get_deep_data()` before ESPN API

  **Data flow (R18):**
  - READS: `UnifiedAPIClient.get_fixture_stats(event_id)` → returns `list` of stat dicts
  - READS: `UnifiedAPIClient.get_deep_data(event_id)` → returns `dict` with `stats`, `form`, `h2h`, `odds`
  - WRITES: `StatsRepo.save_team_form(TeamForm)` — UNCHANGED
  - WRITES: `_save_to_cache()` → JSON file cache — UNCHANGED
  - WRITES: `_save_to_db()` → `StatsRepo.save_match_stats()` — UNCHANGED

  **Key constraint:** The enrichment agent currently operates on TEAM NAMES, not fixture IDs. The new clients operate on fixture/event IDs. The adapter must:
  1. Look up the team's upcoming fixtures from DB (`FixtureRepo`)
  2. Use fixture `external_id` as the event_id for client calls
  3. Fall back to existing HTML scraping if no fixture found in DB

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Wire `FlashscoreClient` for team stats

  Add `_try_flashscore_client(team_name, sport)` that:
  1. Gets team's fixtures from DB for today's date
  2. For each fixture, calls `FlashscoreClient.get_fixture_stats(external_id)`
  3. Aggregates per-stat values from returned stats list
  4. Returns `(stats_dict, error)` — same interface as `_try_flashscore()`

  This replaces the manual URL building (`_build_flashscore_url`), raw HTTP fetch, and regex HTML parsing with a structured client call.

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Wire `Scores24Client` as fallback

  Add `_try_scores24_client(team_name, sport)` that:
  1. Gets team's fixtures from DB
  2. Calls `Scores24Client.get_match_detail(detail_url)` → structured stats
  3. Converts to `{stat_key: [values]}` format
  4. Returns `(stats_dict, error)`

  This replaces `_try_scores24()` which does manual HTML fetching and regex parsing.

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Cleanup singleton client lifecycle

  Ensure the `UnifiedAPIClient` singleton is properly closed on script exit:
  1. Add `atexit.register()` for `_enrich_client.close()`
  2. Or use the existing pattern from `scan_events.py` with `_get_enrich_client()`

  The client already exists as a singleton in `scan_events.py` (`_enrich_client`). Verify it's the same pattern.

### Definition of Done

- [ ] `data_enrichment_agent.py --team "FC Barcelona" --sport football` uses `UnifiedAPIClient` as first source
- [ ] Flashscore/Scores24 HTML scraping still works as fallback when client returns empty
- [ ] `StatsRepo.save_team_form()` receives the same `TeamForm` objects regardless of source
- [ ] `--verbose` output shows which source was used: `client/flashscore-client`, `flashscore-html`, `scores24-html`
- [ ] Rate limiting is handled by the client layer, not duplicated in the script
- [ ] No duplicate Playwright browser instances (script and client share via UnifiedAPIClient singleton)
- [ ] Existing `_save_to_cache()` JSON caching still works

---

## Phase 2: scan_events.py Deep Data → DB Persistence

**Goal:** When `scan_events.py` calls `UnifiedAPIClient.get_deep_data()`, persist the returned form/stats data to `team_form` and `match_stats` DB tables — not just the JSON output file.

**Priority:** HIGH — scan runs every day, fetches rich data, then discards it to JSON. Downstream scripts (deep_stats_report.py) must re-fetch the same data.

**Risk:** LOW — additive change. Existing JSON output is unchanged. DB writes are idempotent (upsert).

**Dependencies:** None

### Tasks

- [ ] **[MODIFY] `scripts/scan_events.py`** — Add DB persistence to `_enrich_single_event()`

  After `fetch_deep_data()` returns `(form, h2h, odds, stats)`:
  1. Import `get_db`, `StatsRepo`, `TeamRepo`, `SportRepo` from `bet.db`
  2. Resolve `home_team_id`, `away_team_id`, `fixture_id` from DB (already available in event dict from scan)
  3. If `stats` is non-empty: call `StatsRepo.save_match_stats(fixture_id, team_id, stats_dict, "scan-deep")`
  4. If `form` is non-empty: compute L10/L5 averages → call `StatsRepo.save_team_form(TeamForm(...))`
  5. Keep existing JSON output untouched

  **Data flow (R18):**
  - READS: `ev["id"]` (fixture external_id) — from scan result
  - READS: `ev["home_team"]`, `ev["away_team"]` — from scan result
  - READS: `UnifiedAPIClient.get_deep_data()` → `dict` with `stats: list`, `form: dict`, `h2h: dict`
  - WRITES: `StatsRepo.save_match_stats(fixture_id, team_id, {stat_key: value}, "scan-deep")`
  - WRITES: `StatsRepo.save_team_form(TeamForm)` — only if form data has L10 values
  - WRITES: JSON output file — UNCHANGED

- [ ] **[CREATE] `scripts/_helpers/deep_data_db_writer.py`** — Shared adapter for deep data → DB

  Extract the conversion logic into a reusable helper:
  ```python
  def persist_deep_data_to_db(
      conn, fixture_id: int, home_team_id: int, away_team_id: int,
      sport_id: int, deep_data: dict, source: str
  ) -> dict:
      """Convert deep data dict to DB records and persist.
      
      Returns: {"match_stats_saved": N, "team_form_saved": M}
      """
  ```

  This helper will be used by both `scan_events.py` (Phase 2) and potentially `data_enrichment_agent.py` (Phase 1).

- [ ] **[VERIFY] Data format compatibility** — `UnifiedAPIClient.get_deep_data()` output → StatsRepo input

  **get_deep_data() returns:**
  ```python
  {"stats": list, "form": {"homeTeam": {"form": [...]}, "awayTeam": {...}}, "h2h": {"teamDuel": [...]}, "odds": list}
  ```

  **StatsRepo.save_match_stats() expects:**
  ```python
  (fixture_id: int, team_id: int, stats: dict[str, float], source: str)
  ```

  **Conversion needed:** `stats` list → `dict[str, float]` keyed by stat name.
  **Conversion needed:** `form.homeTeam.form` list → `TeamForm.l10_values` with computed averages.

### Definition of Done

- [ ] After scan completes, `team_form` table has entries for scanned teams with `source='scan-deep'`
- [ ] After scan completes, `match_stats` table has entries for enriched fixtures with `source='scan-deep'`
- [ ] JSON output file is byte-identical to before (no regression)
- [ ] `deep_data_db_writer.py` has clear input/output docstrings (R18)
- [ ] DB writes are wrapped in try/except — scan never fails due to DB write errors
- [ ] `--verbose` output includes DB persistence count: `"db_stats_saved": 42`

---

## Phase 3: TotalCorner Corner Predictions Integration

**Goal:** Wire `TotalCornerClient.get_corner_predictions()` into the enrichment pipeline for football matches. Corner data is a key statistical market per R5 (STATS OVER OUTCOMES).

**Priority:** MEDIUM — corner data enriches football analysis significantly but is football-only.

**Risk:** LOW — additive. TotalCorner is already in `STATS_PRIORITY["football"]` in unified.py.

**Dependencies:** Phase 2 (shared `deep_data_db_writer.py` helper)

### Tasks

- [ ] **[MODIFY] `src/bet/api_clients/unified.py`** — Add `get_corner_predictions()` to UnifiedAPIClient

  New method that delegates to TotalCornerClient:
  ```python
  def get_corner_predictions(self, match_id: str) -> dict:
      """Fetch corner predictions for a football match."""
      client = self._get_client("totalcorner")
      if not client:
          return {}
      try:
          return client.get_corner_predictions(match_id)
      except Exception as e:
          logger.warning(f"TotalCorner corner predictions failed: {e}")
          return {}
  ```

  **Data flow (R18):**
  - READS: `TotalCornerClient.get_corner_predictions(match_id)` → `dict` with corner data
  - RETURNS: `dict` — same format, passed through

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Call corner predictions for football fixtures

  In the `--date` batch enrichment flow, after standard stat enrichment:
  1. Filter football fixtures from the batch
  2. For each: call `UnifiedAPIClient.get_corner_predictions(external_id)`
  3. If data returned: save to `team_form` with `stat_key="corners_predicted"`, `source="totalcorner"`
  4. The L10 values field stores the corner prediction values

  **Data flow (R18):**
  - READS: `UnifiedAPIClient.get_corner_predictions(match_id)` → `dict`
  - WRITES: `StatsRepo.save_team_form(TeamForm(stat_key="corners_predicted", l10_values=[...], source="totalcorner"))`

- [ ] **[VERIFY] TotalCorner match_id format compatibility**

  `TotalCornerClient.get_corner_predictions()` accepts:
  - TotalCorner internal match_id (from `get_fixtures()` listing cache)
  - Full URL (validated against totalcorner.com domain)
  - Relative path starting with `/`

  Need to verify: what `external_id` does `scan_events.py` store for TotalCorner-sourced fixtures? Does it match what `get_corner_predictions()` expects?

### Definition of Done

- [ ] Football fixtures enriched with corner prediction data in `team_form` table
- [ ] `stat_key="corners_predicted"` appears in team_form for football matches
- [ ] Corner data is available to `deep_stats_report.py` via `StatsRepo.get_form(team_id, "corners_predicted")`
- [ ] Non-football sports are not affected
- [ ] Rate limiting respected (TotalCorner has daily cap in RateLimiter)

---

## Phase 4: Scores24 Trends Integration

**Goal:** Wire `Scores24Client.get_trends()` into the pipeline. Trends provide structured betting tips with categories (Match Result, Over/Under, Corners, Cards) — unique value from Scores24.

**Priority:** MEDIUM — trends data enriches the statistical analysis with pre-computed signals.

**Risk:** LOW — additive. Scores24 is already in `SOURCE_PRIORITY` in unified.py for tennis/basketball/hockey/volleyball.

**Dependencies:** Phase 2 (shared DB writer helper)

### Tasks

- [ ] **[MODIFY] `src/bet/api_clients/unified.py`** — Add `get_trends()` to UnifiedAPIClient

  New method:
  ```python
  def get_trends(self, detail_url: str) -> list[dict]:
      """Fetch betting trends from Scores24."""
      client = self._get_client("scores24")
      if not client:
          return []
      try:
          return client.get_trends(detail_url)
      except Exception as e:
          logger.warning(f"Scores24 trends failed: {e}")
          return []
  ```

- [ ] **[MODIFY] `scripts/data_enrichment_agent.py`** — Integrate trends into enrichment flow

  After standard stat enrichment, for each fixture:
  1. Check if Scores24 was the scan source (fixture has scores24 detail URL stored)
  2. If detail_url available: call `UnifiedAPIClient.get_trends(detail_url)`
  3. Convert trends to team_form entries:
     - Each trend category (e.g., "Corners predictions") → `stat_key` = `"trend_corners"`
     - Odds from tip → stored in `l10_values` as numeric signal
     - Description stored in JSON cache file for agent analysis
  4. Save via `StatsRepo.save_team_form()`

  **Data flow (R18):**
  - READS: `Scores24Client.get_trends(detail_url)` → `list[dict]` with `category`, `tip`, `odds`, `description`
  - WRITES: `StatsRepo.save_team_form(TeamForm(stat_key="trend_{category}", source="scores24-trends"))`
  - WRITES: JSON cache at `betting/data/stats_cache/{sport}/trends_{team_slug}.json`

- [ ] **[VERIFY] detail_url availability** — Where does Scores24 detail_url come from?

  `Scores24Client.get_fixtures()` returns `APIFixture` objects. Check if:
  1. `APIFixture.external_id` stores the detail_url
  2. Or if `scan_results.raw_data` JSON stores it
  3. If neither: need to construct it from team names (slug-based URL)

### Definition of Done

- [ ] Scores24 trends data persisted to `team_form` with `source="scores24-trends"`
- [ ] Trend categories mapped to meaningful `stat_key` values
- [ ] `deep_stats_report.py` can read trend data via `StatsRepo.get_form(team_id, "trend_corners")`
- [ ] Trends are fetched only when detail_url is available — no blind URL construction
- [ ] Rate limiting respected (Scores24 daily cap in RateLimiter)
- [ ] `--verbose` output shows trends fetched count

---

## Phase 5: fetch_odds_multi.py → OddsPortal/BetExplorer Integration

**Goal:** Add `OddsPortalClient` and `BetExplorerClient` as odds sources in `fetch_odds_multi.py` alongside existing API sources (the-odds-api, odds-api-io, api-football-odds).

**Priority:** MEDIUM — more odds sources = better price comparison = better EV detection.

**Risk:** MEDIUM — modifying a working odds pipeline. Existing sources must continue to work. New sources add Playwright overhead.

**Dependencies:** None

### Tasks

- [ ] **[CREATE] `scripts/odds_sources/oddsportal_source.py`** — OddsPortal adapter for odds_sources registry

  Create a source module following the existing pattern (`the_odds_api.py`, `odds_api_io_source.py`):
  ```python
  class OddsPortalSource:
      def supported_sports(self) -> list[str]: ...
      def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]: ...
  ```

  Implementation:
  1. Internally uses `OddsPortalClient` from `bet.api_clients.oddsportal`
  2. `fetch_odds()` calls `client.get_fixtures(date, sport)` to discover events
  3. For each event with a match URL: calls `client.get_odds(match_url)` for bookmaker odds
  4. Converts client output to the `events` format expected by `fetch_odds_multi.py`:
     ```python
     {"home_team": str, "away_team": str, "commence_time": str,
      "bookmakers": [{"title": str, "markets": [{"key": str, "outcomes": [...]}]}],
      "_our_sport": str, "_source": "oddsportal"}
     ```

  **Data flow (R18):**
  - READS: `OddsPortalClient.get_fixtures()` → `list[APIFixture]`
  - READS: `OddsPortalClient.get_odds(match_url)` → `dict` with bookmaker odds
  - RETURNS: `list[dict]` in fetch_odds_multi.py event format

- [ ] **[CREATE] `scripts/odds_sources/betexplorer_source.py`** — BetExplorer adapter

  Same pattern:
  1. Uses `BetExplorerClient` from `bet.api_clients.betexplorer`
  2. `fetch_odds()` calls `client.get_fixtures(date, sport)` — HTTP-first, fast
  3. Listing odds are embedded in fixture results (no detail page needed)
  4. Converts to `events` format with `_source: "betexplorer"`

- [ ] **[MODIFY] `scripts/fetch_odds_multi.py`** — Register new sources

  Add to `_SOURCE_MODULES`:
  ```python
  _SOURCE_MODULES = {
      "the-odds-api": ("odds_sources.the_odds_api", "SOURCE"),
      "odds-api-io": ("odds_sources.odds_api_io_source", "SOURCE"),
      "api-football-odds": ("odds_sources.api_football_odds", "SOURCE"),
      "oddsportal": ("odds_sources.oddsportal_source", "SOURCE"),
      "betexplorer": ("odds_sources.betexplorer_source", "SOURCE"),
  }
  ```

- [ ] **[MODIFY] `scripts/odds_sources/__init__.py`** — Update SPORT_SOURCE_PRIORITY

  Add OddsPortal and BetExplorer to the priority chains (AFTER existing API sources to avoid Playwright overhead when API data is available):
  ```python
  SPORT_SOURCE_PRIORITY = {
      "football":   ["the-odds-api", "odds-api-io", "api-football-odds", "oddsportal", "betexplorer"],
      "tennis":     ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
      "basketball": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
      "hockey":     ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
      "volleyball": ["odds-api-io", "oddsportal", "betexplorer"],
  }
  ```

- [ ] **[VERIFY] Event format compatibility** — New source output → `events_match()` / `merge_event_odds()`

  The `fetch_odds_multi.py` dedup logic uses `events_match(existing, new)` and `merge_event_odds()`. Verify:
  1. New source events have `home_team` and `away_team` fields
  2. `commence_time` is in ISO format
  3. `bookmakers` list follows the nested market/outcome structure
  4. `_our_sport` and `_source` fields are set

### Definition of Done

- [ ] `python3 scripts/fetch_odds_multi.py --sources oddsportal` returns events with bookmaker odds
- [ ] `python3 scripts/fetch_odds_multi.py --sources betexplorer` returns events with listing odds
- [ ] Full run (`--sources` omitted) tries all sources in priority order
- [ ] Existing API sources (the-odds-api, odds-api-io) continue to work unmodified
- [ ] Events from Playwright sources merge correctly with API events (dedup by team names)
- [ ] `_persist_odds_to_db()` handles events from new sources without changes
- [ ] `--dry-run` shows new sources in scan plan

---

## Phase 6: OddsPortal Dropping Odds Integration

**Goal:** Wire `OddsPortalClient.get_dropping_odds()` into the odds evaluation pipeline. Dropping odds signal line movement — a key indicator for value detection and drift.

**Priority:** LOW-MEDIUM — useful but not blocking. Line movement detection is currently manual.

**Risk:** LOW — additive feature. Does not modify existing odds flow.

**Dependencies:** Phase 5 (OddsPortal source adapter exists)

### Tasks

- [ ] **[MODIFY] `scripts/odds_evaluator.py`** — Add dropping odds signal

  After standard odds evaluation:
  1. Import `UnifiedAPIClient` or use the OddsPortal source adapter from Phase 5
  2. Call `OddsPortalClient.get_dropping_odds(sport)` for each sport
  3. Cross-reference dropping odds events with today's shortlist
  4. For matches where odds are dropping: add `"drift_signal": True` to evaluation output
  5. Flag events where drift > 8% (R12 mandatory re-evaluation)

  **Data flow (R18):**
  - READS: `OddsPortalClient.get_dropping_odds(sport)` → `list[dict]` with `url`, `text`
  - READS: Shortlist from `betting/data/{date}_s2_shortlist.json` — for cross-reference
  - WRITES: `odds_history` table with `is_closing=False`, `source="oddsportal-dropping"`
  - WRITES: Evaluation output JSON with `drift_signal` field added

- [ ] **[MODIFY] `src/bet/api_clients/unified.py`** — Add `get_dropping_odds()` method

  ```python
  def get_dropping_odds(self, sport: str = "football") -> list:
      """Fetch dropping odds from OddsPortal."""
      client = self._get_client("oddsportal")
      if not client:
          return []
      try:
          return client.get_dropping_odds(sport)
      except Exception as e:
          logger.warning(f"Dropping odds failed: {e}")
          return []
  ```

- [ ] **[VERIFY] Dropping odds output format**

  Current `get_dropping_odds()` returns:
  ```python
  [{"url": "/football/...", "text": "Team A - Team B 1.85 → 1.72 ..."}]
  ```

  Need to verify: Is this enough to cross-reference with shortlist? May need team name extraction from `text` field or URL parsing.

### Definition of Done

- [ ] `odds_evaluator.py --verbose` output includes dropping odds signals
- [ ] Events with significant drift (>8%) flagged in evaluation output
- [ ] Dropping odds data persisted to `odds_history` for historical tracking
- [ ] Non-OddsPortal runs (when OddsPortal is rate-limited/blocked) degrade gracefully

---

## Phase 7: enrichment.py Module Enhancement

**Goal:** Update `src/bet/stats/enrichment.py` to use new API clients as additional fallback layers beyond ESPN and API-Sports. This module is the async enrichment engine used for bulk operations.

**Priority:** MEDIUM — improves enrichment yield but requires careful async/sync bridging since new clients are synchronous (Playwright).

**Risk:** MEDIUM — async module calling sync Playwright clients needs thread pool isolation to avoid SQLite threading issues.

**Dependencies:** Phase 1 (client integration pattern established)

### Tasks

- [ ] **[MODIFY] `src/bet/stats/enrichment.py`** — Add FlashscoreClient as L3 fallback

  After ESPN (L1) and API-Sports (L2), add FlashscoreClient as L3:
  ```python
  async def _enrich_team(team, sport, stat_keys, db_conn, pool) -> bool:
      # L1: ESPN (existing)
      # L2: API-Sports (existing)
      # L3: FlashscoreClient (NEW)
      if not api_fetched:
          client_fetched = await asyncio.to_thread(
              _try_flashscore_client, team, sport, stat_keys, db_conn
          )
          if client_fetched:
              fetched = True
      # L4: Scores24Client (NEW)
      ...
  ```

  **Data flow (R18):**
  - READS: `FlashscoreClient.get_fixture_stats(event_id)` → `list` of stat dicts
  - READS: `Scores24Client.get_match_detail(detail_url)` → `dict` with match data
  - WRITES: `StatsRepo.save_team_form(TeamForm)` — same path as existing
  - WRITES: `StatsRepo.save_match_stats(fixture_id, team_id, stats, source)` — same path

  **Threading concern:** `enrichment.py` is async. FlashscoreClient/Scores24Client use Playwright (sync). Must use `asyncio.to_thread()` to run client calls in thread pool. SQLite connection cannot cross threads — each thread needs its own connection or use `check_same_thread=False`.

- [ ] **[MODIFY] `src/bet/stats/enrichment.py`** — Add Scores24Client as L4 fallback

  Same pattern as L3 but with Scores24Client:
  1. Call `Scores24Client.get_match_detail()` for structured match data
  2. Extract stat values from returned dict
  3. Save to `match_stats` and `team_form` tables

- [ ] **[VERIFY] Thread safety** — SQLite connection sharing

  Current `enrichment.py` runs tasks sequentially to avoid SQLite threading issues:
  ```python
  # Run sequentially to avoid concurrent writes to shared sqlite3.Connection
  for task_coro in tasks:
      r = await task_coro
  ```

  When adding `asyncio.to_thread()` calls to Playwright clients, verify:
  1. Each thread gets its own DB connection (via `get_db()` context manager)
  2. Or client calls are made in the main thread (sequential, no threading issue)
  3. The existing sequential execution pattern may make `to_thread()` unnecessary — just call sync client methods directly within the async function

### Definition of Done

- [ ] `enrichment.py` tries ESPN → API-Sports → FlashscoreClient → Scores24Client in order
- [ ] Each fallback layer only triggers if previous layers returned no data
- [ ] `enrichment.py` `enrich_fixtures()` returns higher `"fetched"` counts than before
- [ ] No SQLite threading errors under any code path
- [ ] Rate limiting handled by client layer — no manual rate limiting in enrichment.py
- [ ] Source field in `team_form` correctly identifies which layer provided data

---

## Phase 8: Verification & Testing

**Goal:** End-to-end data flow verification for all integration points. Verify R18 compliance — every producer/consumer boundary has matching data formats.

**Priority:** REQUIRED — must run after each preceding phase.

**Risk:** LOW

**Dependencies:** All preceding phases

### Tasks

- [ ] **[CREATE] `scripts/_test_db_integration.py`** — Integration verification script

  Automated checks:
  1. **Phase 1 check:** Run `data_enrichment_agent.py --team "Real Madrid" --sport football --verbose` → verify `team_form` row exists with `source` containing "client" or "flashscore-client"
  2. **Phase 2 check:** Run `scan_events.py --date {today} --verbose` → query `team_form` for scanned teams → verify rows with `source='scan-deep'` exist
  3. **Phase 3 check:** Query `team_form WHERE stat_key='corners_predicted'` → verify non-zero count for football
  4. **Phase 4 check:** Query `team_form WHERE stat_key LIKE 'trend_%'` → verify non-zero count
  5. **Phase 5 check:** Run `fetch_odds_multi.py --sources oddsportal --dry-run` → verify source appears in plan
  6. **Phase 6 check:** Query `odds_history WHERE source='oddsportal-dropping'` → verify schema compatibility
  7. **Phase 7 check:** Call `enrich_fixtures()` with test fixtures → verify fallback chain progression

- [ ] **[VERIFY] R18 — Data format compatibility matrix**

  For each integration point, verify actual data with a test run:

  | Integration | Producer Output | Consumer Input | Match? |
  |------------|----------------|---------------|--------|
  | Phase 1: Client → save_team_form | FlashscoreClient stats → TeamForm | StatsRepo.save_team_form(TeamForm) | ☐ |
  | Phase 2: Deep data → match_stats | get_deep_data().stats → dict | StatsRepo.save_match_stats(fid, tid, dict, src) | ☐ |
  | Phase 3: Corner → team_form | get_corner_predictions() → dict | StatsRepo.save_team_form(TeamForm) | ☐ |
  | Phase 4: Trends → team_form | get_trends() → list[dict] | StatsRepo.save_team_form(TeamForm) | ☐ |
  | Phase 5: OddsPortal → odds_history | get_odds() → dict | OddsRepo.save(OddsRecord) | ☐ |
  | Phase 6: Dropping → odds_history | get_dropping_odds() → list | OddsRepo.save(OddsRecord) | ☐ |
  | Phase 7: Client → enrichment | Client stats → enrichment.py | StatsRepo (same as Phase 1) | ☐ |

- [ ] **[VERIFY] Rate limiter daily cap compliance**

  After running full pipeline with all integrations:
  1. Check `RateLimiter` counters for each client
  2. Verify no client exceeded daily cap
  3. Verify circuit breakers didn't open spuriously

- [ ] **[VERIFY] Idempotency** — Run pipeline twice, verify no duplicate rows

  1. Run scan → enrichment → odds for the same date
  2. Run again
  3. Query `team_form`, `match_stats`, `odds_history` — counts should not double
  4. `StatsRepo.save_team_form()` uses DELETE+INSERT in SAVEPOINT — idempotent ✅
  5. `OddsRepo.save()` uses INSERT OR IGNORE — idempotent ✅
  6. `StatsRepo.save_match_stats()` uses INSERT OR REPLACE — idempotent ✅

### Definition of Done

- [ ] All 7 R18 compatibility checks pass
- [ ] `_test_db_integration.py` runs without errors
- [ ] No SQLite constraint violations in any test
- [ ] Rate limiter caps respected across full pipeline run
- [ ] Idempotency verified — double run produces same row count

---

## Implementation Order & Dependencies

```
Phase 1 (data_enrichment_agent.py) ──→ Phase 3 (TotalCorner) ──→ Phase 4 (Scores24 Trends)
                                    ↘                             ↗
Phase 2 (scan_events.py DB write)  ──→ Phase 7 (enrichment.py)
                                    ↗
Phase 5 (fetch_odds_multi.py)     ──→ Phase 6 (Dropping Odds)

Phase 8 (Verification) runs after EACH phase, not just at the end.
```

**Recommended execution order:**
1. Phase 2 (LOW risk, fast, unblocks Phase 7)
2. Phase 1 (HIGHEST priority, MEDIUM risk)
3. Phase 5 (independent, MEDIUM risk)
4. Phase 3 (depends on Phase 2 helper)
5. Phase 4 (depends on Phase 2 helper)
6. Phase 7 (depends on Phase 1 pattern)
7. Phase 6 (depends on Phase 5)
8. Phase 8 (final verification)

---

## Files Modified Summary

| File | Phases | Changes |
|------|--------|---------|
| `scripts/data_enrichment_agent.py` | 1, 3, 4 | Add client-based enrichment, corner predictions, trends |
| `scripts/scan_events.py` | 2 | Add DB persistence for deep data |
| `scripts/fetch_odds_multi.py` | 5 | Register OddsPortal + BetExplorer sources |
| `scripts/odds_evaluator.py` | 6 | Add dropping odds signal |
| `scripts/odds_sources/__init__.py` | 5 | Update SPORT_SOURCE_PRIORITY |
| `src/bet/api_clients/unified.py` | 3, 4, 6 | Add get_corner_predictions(), get_trends(), get_dropping_odds() |
| `src/bet/stats/enrichment.py` | 7 | Add FlashscoreClient/Scores24Client fallback layers |

| File | Phases | Changes |
|------|--------|---------|
| `scripts/odds_sources/oddsportal_source.py` | 5 | NEW — OddsPortal adapter for odds registry |
| `scripts/odds_sources/betexplorer_source.py` | 5 | NEW — BetExplorer adapter for odds registry |
| `scripts/_helpers/deep_data_db_writer.py` | 2 | NEW — Shared deep data → DB conversion helper |
| `scripts/_test_db_integration.py` | 8 | NEW — Integration verification script |

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| 1 | MEDIUM | Keep HTML scraping as fallback. Test with single team before batch. |
| 2 | LOW | Additive DB writes. JSON output unchanged. Wrapped in try/except. |
| 3 | LOW | Football-only. TotalCorner already rate-limited. |
| 4 | LOW | Additive. Scores24 already rate-limited. |
| 5 | MEDIUM | New sources added AFTER existing API sources in priority chain. |
| 6 | LOW | Additive feature. Graceful degradation if OddsPortal blocked. |
| 7 | MEDIUM | Async/sync bridging. SQLite threading. Test thoroughly. |
| 8 | LOW | Verification only. |

## Non-Goals

- No new DB tables (use existing team_form, match_stats, odds_history)
- No changes to API client code (Phase 1-10 frozen)
- No changes to DB schema or migrations
- No new Playwright browser management — everything through UnifiedAPIClient
- No changes to existing JSON output formats
