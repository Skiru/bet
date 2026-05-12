# Volleyball Adapter Improvements — Implementation Plan

**Created:** 2026-05-12
**Status:** Draft
**Scope:** Improve volleyball data coverage by syncing scanner config, extending normalized schema, fixing validation, improving existing adapters, and registering ESPN volleyball.

---

## Technical Context

### Scanner Architecture

All 11 sport scanners inherit from `BaseSportScanner` (`scripts/scanners/base_scanner.py`). The scan lifecycle is: `fetch URLs → parse via adapters → discover deep links → write to DB (ScanResultRepo) + JSON → validate`.

Each scanner declares:
- `urls` — seed URLs to scan
- `timeout_per_page` — max seconds per fetch
- `max_deep_links` — cap on deep link follows
- `required_stat_keys` — stat keys the sport should produce (CURRENTLY UNUSED in validation)
- `min_expected_events` — threshold for scan pass/fail

The **hockey scanner** (`hockey_scanner.py`) already implements config-driven URLs: it loads from `config/scan_urls.json` via direct JSON read with hardcoded fallback. A shared `config_loader.py` module exists with `get_urls_for_sport()` but is NOT used by any scanner yet.

### Adapter Architecture

Adapters live in `scripts/adapters/`. The `ADAPTERS` dict maps domain → parse function. `normalize_adapter_output()` maps raw adapter output to `ENRICHED_EVENT_DEFAULTS` schema. Currently the schema covers: predictions, odds, corners, form, h2h, cards, fouls, shots — but has **no volleyball-specific fields**.

Six generic adapters handle volleyball today:
- **flashscore_adapter** — detects `volleyball` from URL, extracts fixtures
- **sofascore_adapter** — REST API, returns fixtures with `sofascore_id` but no deep-link URL
- **scores24_adapter** — detail pages with H2H/form/trends, maps `volleyball` sport
- **oddsportal_adapter** — 2-way odds
- **betexplorer_adapter** — table odds
- **forebet_adapter** — prediction probabilities

### API Client Architecture

`src/bet/api_clients/__init__.py` maintains two maps: `API_SPORTS` (API-Sports v1 clients) and `API_ESPN` (ESPN hidden API). The `CLIENT_REGISTRY` dict maps `api-name → class/factory`. ESPN client (`espn.py`) has full volleyball support: `ESPN_SPORT_MAP` includes volleyball, `ESPN_LEAGUES` has `fivb.m`, `fivb.w`, `ncaa.m`, `ncaa.w`, and `VOLLEYBALL_STAT_MAP` defines 13 stat fields. But `API_ESPN` and `CLIENT_REGISTRY` do NOT register an ESPN volleyball client.

### Config vs Scanner Drift

| Aspect | Scanner (hardcoded) | Config (`scan_urls.json`) | Gap |
|--------|-------------------|--------------------------|-----|
| URLs | 17 | 43 | 26 missing URLs |
| max_deep_links | 15 | 20 | Scanner ignores config |
| Sofascore | In fallback only | In main URL list | Not in main scan |

### Validation Gap

`BaseSportScanner.validate()` (line 354) only checks `events_found < min_expected_events`. The `required_stat_keys` abstract property is declared and overridden by every scanner but **never checked**. Volleyball scans pass validation with zero volleyball stats.

---

## Phase 1: Foundation (Config, Schema, Validation)

### Task 1: [MODIFY] sync_volleyball_scanner_with_config
- **File(s):** `scripts/scanners/volleyball_scanner.py`
- **What:**
  1. Import `json` and define `_CONFIG_PATH` pointing to `config/scan_urls.json`
  2. Replace hardcoded `urls` property with config-driven loading (same pattern as `hockey_scanner.py`): read `sports.volleyball.urls` from config, fall back to current hardcoded list
  3. Read `max_deep_links` from config's `sports.volleyball.max_deep_links` (20), fall back to current 15
  4. Add class-level URL cache (`_cached_urls = None`) to avoid re-reading config per scan
- **Why:** 26 leagues are configured but not scanned. Config is the source of truth for URLs but the scanner ignores it. The hockey scanner already solved this exact problem.
- **Dependencies:** None
- **Definition of done:** `VolleyballScanner().urls` returns all 43 URLs from config. `max_deep_links` returns 20. If config file is missing/corrupt, falls back to hardcoded 17 URLs.
- **Test strategy:** Unit test: mock config file → assert URLs loaded. Unit test: missing config → assert fallback URLs. Verify URL count matches config with `len(VolleyballScanner().urls)`.

### Task 2: [MODIFY] add_volleyball_fields_to_normalized_schema
- **File(s):** `scripts/adapters/__init__.py`
- **What:**
  1. Add a `"volleyball"` dict to `ENRICHED_EVENT_DEFAULTS` with keys: `sets_won_home`, `sets_won_away`, `total_points`, `kills`, `aces`, `blocks`, `digs`, `assists`, `errors`, `hitting_pct`, `attack_pct`, `service_errors`, `period_scores` (already exists at top level — volleyball uses it for set scores)
  2. In `normalize_adapter_output()`, add a block that merges `event.get("volleyball")` dict into `normalized["volleyball"]` if present, similar to existing `predictions`/`corners` merge blocks
- **Why:** Without volleyball fields in the schema, adapters that extract volleyball stats have nowhere to put them. The normalizer silently drops sport-specific data. This is the prerequisite for adapters to emit volleyball stats.
- **Dependencies:** None
- **Definition of done:** `ENRICHED_EVENT_DEFAULTS["volleyball"]` exists with all stat keys defaulting to `None`. `normalize_adapter_output()` correctly merges volleyball data from adapter output.
- **Test strategy:** Unit test: pass event with `{"volleyball": {"kills": 45}}` → assert normalized output has `normalized["volleyball"]["kills"] == 45`. Unit test: event without volleyball key → assert defaults are None.

### Task 3: [MODIFY] fix_base_scanner_stat_validation
- **File(s):** `scripts/scanners/base_scanner.py`
- **What:**
  1. Extend `validate()` method to check that at least N% of events (configurable, suggest 10%) have at least one key from `required_stat_keys` present in their `raw_data`
  2. Add stat coverage gap to the returned `gaps` list (e.g., `"volleyball: 0/45 events have required stats (points, aces, blocks, attack_pct, sets_won)"`)
  3. This is a WARNING-level gap, not a scan failure — set `validation_passed` based only on event count (existing behavior), but include stat gaps in `gaps_description` so the pipeline agent can act on it
- **Why:** `required_stat_keys` is declared by every scanner but never validated. Volleyball scans pass with zero volleyball stats and nobody notices. Making this a warning (not failure) avoids breaking other scanners while surfacing the data quality issue.
- **Dependencies:** None
- **Definition of done:** After scan, `gaps` list includes stat coverage info when stat keys are missing from results. Existing event-count validation is unchanged. Gap message includes sport name, count, and missing keys.
- **Test strategy:** Unit test: mock scan results with 0 stat keys → assert gap message present. Unit test: mock results with stats → assert no stat gap.

---

## Phase 2: Adapter Improvements

### Task 4: [MODIFY] sofascore_emit_deep_link_url
- **File(s):** `scripts/adapters/sofascore_adapter.py`
- **What:**
  1. When `sofascore_id` is present, also emit `match_url` as `f"https://www.sofascore.com/{sport}/match/{home_slug}-{away_slug}/{sofascore_id}"` (or simpler: `f"https://api.sofascore.com/api/v1/event/{sofascore_id}"` for API access)
  2. This enables downstream enrichment scripts to fetch per-match statistics from Sofascore's event detail API
- **Why:** Sofascore emits `sofascore_id` which gets mapped to `match_id` by the normalizer, but no `match_url` is set. Deep enrichment scripts need a URL to fetch match-level stats (lineups, statistics, incidents). The API endpoint `api/v1/event/{id}/statistics` returns per-team stats including volleyball fields.
- **Dependencies:** Task 2 (schema must have volleyball fields for stats to populate)
- **Definition of done:** Parsed events include `match_url` pointing to Sofascore event API. Normalizer preserves it in output.
- **Test strategy:** Unit test: mock Sofascore API response → assert `match_url` contains sofascore_id. Live test: fetch one volleyball event → verify `match_url` is a valid Sofascore URL.

### Task 5: [MODIFY] validate_flashscore_volleyball_parsing
- **File(s):** `scripts/adapters/flashscore_adapter.py`
- **What:**
  1. Verify that `_detect_sport_from_url()` correctly returns `"volleyball"` for volleyball URLs (it does — line 24)
  2. Verify set score extraction: Flashscore volleyball pages show set scores (e.g., "3-1 (25-22, 23-25, 25-20, 25-18)"). Check if `period_scores` parsing handles volleyball format
  3. If set scores are not extracted, add volleyball-aware parsing in the score extraction block that detects volleyball sport and parses set-by-set scores into `period_scores`
  4. Add `"volleyball"` dict with `sets_won_home`/`sets_won_away` derived from set count
- **Why:** Flashscore is the primary fixture source for volleyball. Sport detection works but set score extraction may not handle volleyball's format (best-of-5 sets with point scores per set). Period scores are critical for volleyball statistical analysis.
- **Dependencies:** Task 2 (volleyball schema fields)
- **Definition of done:** Flashscore volleyball pages produce events with correct `sport="volleyball"`, `period_scores` containing set-by-set scores when available, and `volleyball.sets_won_home`/`sets_won_away` populated.
- **Test strategy:** Live test: fetch a Flashscore volleyball page with finished/live match → verify period_scores has set scores. Unit test: mock HTML with volleyball scores → verify extraction.

### Task 6: [MODIFY] scores24_volleyball_stat_extraction
- **File(s):** `scripts/adapters/scores24_adapter.py`
- **What:**
  1. In `_parse_detail_page()`, detect volleyball sport and add extraction for volleyball-specific stats from the match detail page: total points, aces, blocks, attack percentage
  2. Scores24 detail pages have stats tables — add selectors/regex for volleyball stat rows
  3. Emit extracted stats in the `"volleyball"` dict key so normalizer can merge them
- **Why:** Scores24 is the strongest H2H/form source for volleyball. Detail pages contain stat tables that the current generic parser doesn't extract into structured volleyball fields. This data feeds safety score calculation.
- **Dependencies:** Task 2 (volleyball schema)
- **Definition of done:** Scores24 volleyball detail page parsing extracts available volleyball stats into `event["volleyball"]` dict. H2H extraction continues to work unchanged.
- **Test strategy:** Live test: fetch a Scores24 volleyball detail page → verify volleyball stats extracted. Unit test: mock detail page HTML with volleyball stat table → verify structured output.

### Task 7: [MODIFY] register_espn_volleyball_client
- **File(s):** `src/bet/api_clients/__init__.py`
- **What:**
  1. Add `"volleyball": "espn-volleyball"` to `API_ESPN` map
  2. Register `CLIENT_REGISTRY["espn-volleyball"] = _espn_factory("volleyball", "fivb.m")` (default to FIVB men's; other leagues available: `fivb.w`, `ncaa.m`, `ncaa.w`)
- **Why:** ESPN client already has full volleyball support (sport mapping, league codes, `VOLLEYBALL_STAT_MAP` with 13 stats), but is not registered in `API_ESPN` or `CLIENT_REGISTRY`. This is a 2-line fix that unlocks free volleyball stats with no rate limits.
- **Dependencies:** None
- **Definition of done:** `get_client("espn-volleyball")` returns a working `ESPNClient` configured for volleyball. `API_ESPN["volleyball"]` resolves to `"espn-volleyball"`.
- **Test strategy:** Unit test: call `get_client("espn-volleyball")` → assert returns ESPNClient instance. Integration test: fetch scheduled events for volleyball → verify response structure.

---

## Phase 3: Testing & Documentation

### Task 8: [MODIFY] add_volleyball_live_test_urls
- **File(s):** `scripts/_live_test_adapters.py`
- **What:**
  1. Add volleyball test URLs to `TEST_URLS`:
     - `"flashscore.com"` already tests football — add a separate volleyball entry or modify test harness to support multiple URLs per adapter
     - Add `"sofascore.com"` volleyball URL: `"https://api.sofascore.com/api/v1/sport/volleyball/scheduled-events/{today}"`
     - Add `"scores24.live"` volleyball URL: `"https://scores24.live/en/volleyball"`
  2. Add volleyball-specific `EXPECTED_FIELDS` entries
  3. Since the test harness maps domain→URL (one per domain), create a `VOLLEYBALL_TEST_URLS` dict that the `--sport volleyball` flag can activate for volleyball-specific testing
- **Why:** Zero volleyball test coverage. All six adapters that handle volleyball are untested for volleyball input. Failures are only discovered during production scans.
- **Dependencies:** Tasks 4-6 (adapter improvements should be done first so tests pass)
- **Definition of done:** Running `python3 scripts/_live_test_adapters.py --adapter flashscore.com --sport volleyball` (or equivalent) executes volleyball-specific tests. At least 3 adapters have volleyball test URLs.
- **Test strategy:** Run the live test harness → verify volleyball URLs are fetched and parsed without errors.

### Task 9: [MODIFY] update_volleyball_scanning_skill
- **File(s):** `.github/skills/bet-scanning-volleyball/SKILL.md`
- **What:**
  1. Update "Source URLs" table: add all 43 config URLs (or reference config as source of truth)
  2. Update "Adapter Mapping" table: add ESPN volleyball entry, note Sofascore deep-link capability
  3. Update "Data Quality Standards": add `volleyball` schema fields to required stats
  4. Update "Known Issues": mark ESPN registration as resolved, note config sync is done
  5. Add "Config-Driven URLs" section explaining that scanner reads from `config/scan_urls.json`
  6. Update fallback chain: add ESPN as L2 for statistical data
- **Why:** SKILL.md is agent knowledge — it tells the pipeline agent what sources exist, what fields to expect, and what known issues to work around. Stale docs = agents make wrong decisions.
- **Dependencies:** Tasks 1-7 (document what was actually implemented)
- **Definition of done:** SKILL.md accurately reflects the current state of volleyball scanning after all improvements are applied.
- **Test strategy:** Manual review: verify every source/adapter/field mentioned in SKILL.md matches the actual code.

### Task 10: [EXECUTE] live_test_all_volleyball_adapters
- **File(s):** N/A (execution task)
- **What:**
  1. Run live adapter tests for all volleyball URLs
  2. For each adapter: verify events are parsed, sport is detected, expected fields are populated
  3. Fix any adapter failures discovered during testing
  4. Document results in the Changelog section below
- **Why:** Implementation without testing is incomplete. Live tests catch real-world parsing issues (site layout changes, missing data, API format changes).
- **Dependencies:** Tasks 1-8 (all implementation complete)
- **Definition of done:** All volleyball adapters pass live tests with ≥1 event parsed per source. Any failures are documented with fix actions.
- **Test strategy:** This IS the test task. Run `_live_test_adapters.py` with volleyball URLs and verify.

---

## Dependency Graph

```
Phase 1 (parallel):
  Task 1 (config sync)     ─────────────┐
  Task 2 (schema)          ──┬───────────┤
  Task 3 (validation)       │           │
                             │           │
Phase 2 (after Task 2):      │           │
  Task 4 (sofascore)    ←───┘           │
  Task 5 (flashscore)   ←───┘           │
  Task 6 (scores24)      ←───┘           │
  Task 7 (ESPN)          ─── (independent)│
                                         │
Phase 3 (after Phase 2):                 │
  Task 8 (live tests)    ←──────────────┘
  Task 9 (SKILL.md)      ←──────────────┘
  Task 10 (execute tests) ←── Task 8
```

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Flashscore HTML layout changed | Set score extraction fails | Fallback to raw score string; Sofascore API as alternate |
| Scores24 volleyball detail pages lack stats table | No volleyball stats from Scores24 | ESPN + Sofascore event API as alternate stat sources |
| ESPN volleyball endpoints return empty data | No free stats source | API-Sports volleyball client exists as paid fallback |
| Config sync breaks existing behavior | Scanner produces different results | Hardcoded URLs as fallback; existing URLs are subset of config |

## Estimation Hints

- Tasks 1, 7: Small (config wiring, 2-line registration)
- Tasks 2, 3: Small-Medium (schema extension, validation addition)
- Tasks 4, 5, 6: Medium (adapter modifications requiring HTML/API inspection)
- Tasks 8, 9: Medium (test harness extension, documentation update)
- Task 10: Variable (depends on failures found)

---

## Changelog

<!-- Fill during implementation -->

| Date | Task | Change | Commit |
|------|------|--------|--------|
| | | | |
