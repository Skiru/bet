# Odds Pipeline Cleanup & Unification

**Status:** IMPLEMENTED  
**Created:** 2026-05-14  
**Implemented:** 2026-05-14  
**Complements:** `specifications/scrapers-pipeline-integration.md` (stats/enrichment cleanup)

---

## 1. Executive Summary

The odds pipeline has grown organically into 5 parallel fetch paths, 6 source wrappers, and an evaluator that reads from 4 sources — of which 2 produce no data. The result is dead code, a non-functional multi-source orchestrator (`fetch_odds_multi.py` producing 0 events), a volleyball odds gap (zero working sources), and an evaluator Phase 6 calling broken Playwright clients.

This plan:
1. **Removes** 4 dead/broken odds paths (ESPN odds, BetExplorer odds stub, OddsPortal partial, Phase 6 dropping odds)
2. **Activates** odds-api.io as the volleyball solution and secondary source for all sports
3. **Consolidates** the evaluator to 2 clean paths: DB (Source 0) + The Odds API snapshot (Source 1)
4. **Repairs** `fetch_odds_multi.py` as a 3-source orchestrator (the-odds-api + odds-api-io + api-football-odds)
5. **Updates** all configuration maps, tests, and documentation

**Net effect:** Fewer files, no dead code, volleyball odds coverage, simpler evaluator, `fetch_odds_multi.py` actually works.

---

## 2. Architecture Decision Records

### ADR-1: Keep `fetch_odds_multi.py` as unified entry point

**Context:** Two approaches exist — run individual fetch scripts, or run `fetch_odds_multi.py` which orchestrates all sources. Currently `fetch_odds_multi.py` produces 0 events because most sources are broken.

**Decision:** Keep `fetch_odds_multi.py` as the **recommended** pipeline entry point. Individual scripts (`fetch_odds_api.py`, `fetch_odds_api_io.py`) remain available as direct alternatives.

**Rationale:**
- Multi-source adds cross-source dedup, merge, and unified DB write
- Pipeline orchestrator needs ONE command for "fetch all odds"
- Individual scripts are useful for debugging or targeted fetches

**Consequence:** `fetch_odds_multi.py` source registry shrinks from 5 → 3 sources. Dead sources removed.

---

### ADR-2: Remove ESPN as odds source

**Context:** `fetch_espn_odds.py` code works, DB writes work, but ESPN API returns `"odds": []` for all events since at least 2026-05-07. The evaluator's Source 3 reads `espn_enrichment_{date}.json` which is always empty.

**Decision:** Remove ESPN from the odds pipeline entirely. Keep `_convert_espn_odds_to_decimal()` utility in evaluator (tested, useful for American odds conversion). Keep ESPN as a **stats/fixtures** source in `UnifiedAPIClient.SOURCE_PRIORITY`.

**Rationale:**
- Zero data output = dead code in production
- ESPN still useful for fixtures, standings, ATS records — just not odds
- Removing from evaluator simplifies the loading loop

**Consequence:** Source 3 block removed from `_inject_ev_from_odds()`. `fetch_espn_odds.py` script preserved but no longer referenced in odds pipeline. `agent_protocol.py` SELF_HEALING_REGISTRY espn_data entry updated.

---

### ADR-3: Remove BetExplorer and OddsPortal from odds routing

**Context:**
- `betexplorer_source.py`: explicitly a **stub** — line 74 logs "no odds — client stub", returns empty `bookmakers[]`
- `oddsportal_source.py`: returns only H2H listing odds as "oddsportal_average" — no totals, spreads, or per-bookmaker data. Requires Playwright.
- `UnifiedAPIClient.ODDS_PRIORITY` routes all sports → `[oddsportal, betexplorer]` — both broken
- `UnifiedAPIClient.get_odds()` uses `ODDS_PRIORITY` — never returns data

**Decision:** Remove BetExplorer and OddsPortal from **all odds-specific routing**:
- Remove from `SPORT_SOURCE_PRIORITY` in `scripts/odds_sources/__init__.py`
- Remove from `_SOURCE_MODULES` in `fetch_odds_multi.py`
- Remove `ODDS_PRIORITY` dict from `src/bet/api_clients/unified.py`
- Remove `get_odds()` method from `UnifiedAPIClient`
- Keep both in `SOURCE_PRIORITY` (fixtures/stats) — they still work for fixture discovery
- **Keep `get_dropping_odds()` in UnifiedAPIClient** but mark as degraded (OddsPortal Playwright dependency)

**Rationale:**
- Broken code that appears to work is worse than no code
- Fixture discovery via BetExplorer/OddsPortal is separate from odds
- OddsPortal's H2H listing odds are too shallow to be useful (no line data, no per-bookmaker breakdown)

**Consequence:** `oddsportal_source.py` and `betexplorer_source.py` files remain (for fixture discovery via `UnifiedAPIClient`) but are removed from the odds pipeline. Tests referencing odds capabilities of these sources updated.

---

### ADR-4: Do NOT bridge discovery module odds into odds_history (deferred)

**Context:** `OddsAPIAdapter` in discovery module fetches events WITH odds from The Odds API but doesn't write to `odds_history`. Could be a "free" data source.

**Decision:** Defer. Do not bridge in this cleanup.

**Rationale:**
- Discovery uses SQLAlchemy ORM; pipeline uses raw sqlite3 via `get_db()` — mixing risks transaction conflicts
- The Odds API credit budget is shared — discovery already consumes credits for event discovery, writing odds separately would be double-counting
- The `fetch_odds_api.py` script already fetches the same data and writes to `odds_history`
- Adding bridge code increases coupling between discovery and pipeline modules
- Revisit after scrapers-pipeline-integration is complete

**Consequence:** No changes to discovery module. The Odds API data enters odds_history only via `fetch_odds_api.py`.

---

### ADR-5: odds-api.io is the volleyball odds solution

**Context:**
- The Odds API has NO volleyball coverage (`SPORT_KEY_MAP["volleyball"]` is missing/empty)
- odds-api.io supports volleyball via `SPORT_SLUG_MAP`
- OddsPortal/BetExplorer broken
- Volleyball is a Tier 1 sport (R4) with ZERO working odds sources

**Decision:** Activate `fetch_odds_api_io.py` as a standard pipeline step. It becomes the **primary** volleyball odds source and a secondary source for all 5 sports (265 bookmakers including Betclic PL).

**Rationale:**
- Free tier: 5,000 requests/hour (generous, vs 500 credits/month for The Odds API)
- Supports all 5 sports
- Code exists and works — just needs to be run in the pipeline
- Produces `odds_api_io_snapshot.json` which evaluator Source 2 already knows how to parse

**Consequence:** `fetch_odds_api_io.py` added to pipeline. `SPORT_SOURCE_PRIORITY["volleyball"]` changes from `[odds-api-io, oddsportal, betexplorer]` → `[odds-api-io]`.

---

### ADR-6: Evaluator simplifies to DB + 2 snapshot sources

**Context:** Evaluator currently has: Source 0 (DB), Source 1 (the-odds-api snapshot), Source 2 (odds-api-io snapshot — never exists), Source 3 (ESPN — always empty), Phase 6 (dropping odds — broken).

**Decision:** After cleanup, evaluator reads:
- **Source 0: DB `odds_history`** — richest source, ALL scripts write here (Betclic HTML, the-odds-api, odds-api-io, api-football)
- **Source 1: `odds_api_snapshot.json`** — The Odds API direct file (fast, no DB query overhead, pre-computed best_odds)
- **Source 2: `odds_api_io_snapshot.json`** — odds-api.io file (includes `value_bets` with pre-calculated EV)
- Remove Source 3 (ESPN) and Phase 6 (dropping odds)

**Rationale:**
- DB is the single source of truth for all odds data
- Snapshot files provide: (a) pre-computed data, (b) value_bets EV, (c) faster access for large scans
- ESPN and dropping odds produce zero data

**Consequence:** ~60 lines of dead code removed from `_inject_ev_from_odds()` and `main()`.

---

### ADR-7: Betclic HTML parse stays as-is

**Context:** `parse_betclic_html.py` reads manually-saved HTML, writes to DB `odds_history` (bookmaker="betclic"). The only source of Betclic-specific odds (R12).

**Decision:** No changes. Keep as separate workflow.

**Rationale:**
- User manually saves HTML from Betclic app — fundamentally different workflow from API fetches
- Already writes to DB, so evaluator Source 0 picks it up
- Integrating into `fetch_odds_multi.py` makes no sense (no API to call)
- 459 rows on a good day — working correctly

**Consequence:** No files changed. `parse_betclic_html.py` continues as S0.2 in pipeline.

---

### ADR-8: Remove `ODDS_PRIORITY` from UnifiedAPIClient

**Context:** `ODDS_PRIORITY` maps all sports → `[oddsportal, betexplorer]`. Both are broken for odds. `get_odds()` uses this map and never returns data.

**Decision:** Remove `ODDS_PRIORITY` dict and `get_odds()` method entirely. The odds pipeline does NOT route through `UnifiedAPIClient` — it routes through `scripts/odds_sources/` package and direct fetch scripts.

**Rationale:**
- `UnifiedAPIClient` is for stats/fixtures, not odds
- Odds have their own dedicated infrastructure (`fetch_odds_api.py`, `fetch_odds_multi.py`, `odds_sources/` package)
- Having a dead `ODDS_PRIORITY` map is misleading

**Consequence:** `unified.py` loses ~20 lines. No downstream impact — `get_odds()` was never called successfully.

---

## 3. Data Flow Diagram (After Cleanup)

```
                    ┌──────────────────────────────────────────────────┐
                    │              ODDS DATA SOURCES                    │
                    ├──────────────────────────────────────────────────┤
                    │                                                  │
                    │  ┌─────────────────┐  ┌──────────────────┐       │
                    │  │ The Odds API    │  │ odds-api.io      │       │
                    │  │ (Primary)       │  │ (Secondary)      │       │
                    │  │ 500 cr/mo       │  │ 5000 req/hr      │       │
                    │  │ 4 sports        │  │ 5 sports         │       │
                    │  │ NO volleyball   │  │ + volleyball ✓   │       │
                    │  └───────┬─────────┘  └───────┬──────────┘       │
                    │          │                     │                  │
                    │  ┌───────┴─────────┐  ┌───────┴──────────┐       │
                    │  │ fetch_odds_     │  │ fetch_odds_      │       │
                    │  │ api.py          │  │ api_io.py        │       │
                    │  │                 │  │                   │       │
                    │  │ → snapshot.json │  │ → io_snapshot.json│       │
                    │  │ → odds_history  │  │ → odds_history    │       │
                    │  └───────┬─────────┘  └───────┬──────────┘       │
                    │          │                     │                  │
                    │  ┌───────┴─────────┐  ┌───────┴──────────┐       │
                    │  │ api-football-   │  │ Betclic HTML     │       │
                    │  │ odds (football) │  │ parse (manual)   │       │
                    │  │ → odds_history  │  │ → odds_history   │       │
                    │  └───────┬─────────┘  └───────┬──────────┘       │
                    └──────────┼─────────────────────┼─────────────────┘
                               │                     │
                    ┌──────────┴─────────────────────┴─────────────────┐
                    │          fetch_odds_multi.py                      │
                    │  (orchestrates the-odds-api + odds-api-io +      │
                    │   api-football-odds; dedup + merge + DB write)    │
                    └──────────────────────┬───────────────────────────┘
                                           │
                    ┌──────────────────────┴───────────────────────────┐
                    │                  betting.db                       │
                    │              odds_history table                   │
                    │         (36K+ rows, all bookmakers)               │
                    │  Betclic | Bet365 | Pinnacle | the-odds-api |    │
                    │  odds-api-io | api-football | ...                 │
                    └──────────────────────┬───────────────────────────┘
                                           │
                    ┌──────────────────────┴───────────────────────────┐
                    │           odds_evaluator.py (S4)                 │
                    │                                                  │
                    │  Source 0: DB odds_history (ALL data)             │
                    │  Source 1: odds_api_snapshot.json (pre-computed)  │
                    │  Source 2: odds_api_io_snapshot.json (value_bets) │
                    │                                                  │
                    │  Priority: Betclic > Bet365 > market_best        │
                    │  EV = probability × odds − 1                     │
                    │  Writes: S3 JSON enriched + analysis_results DB  │
                    └──────────────────────────────────────────────────┘
```

---

## 4. Phase Breakdown

### Phase 1: Remove Dead Odds Paths from Evaluator

**Goal:** Remove code in `odds_evaluator.py` that reads from sources producing zero data.  
**Risk:** LOW — removing code that processes empty data.  
**Dependency:** None.

- [x] **1.1 [MODIFY] `scripts/odds_evaluator.py` — Remove Source 3 (ESPN) block**
  - **File:** `scripts/odds_evaluator.py`
  - **What:** Delete the Source 3 block (lines ~330-350) that reads `espn_enrichment_{date}.json`. This block parses `odds_decimal.moneyline` from ESPN data, but the file always contains `"odds": []`.
  - **Why:** ESPN API no longer returns odds data. Source 3 always produces 0 entries.
  - **How:** Remove the entire `# Source 3: ESPN DraftKings odds (free, unlimited)` block including the `espn_path` variable and try/except that follows it.
  - **Keep:** `_convert_espn_odds_to_decimal()` function at top of file — it's tested and useful as a general American-to-decimal converter.
  - **Test impact:** None — `test_odds_evaluator.py` only tests `_convert_espn_odds_to_decimal`, not the Source 3 loading path.
  - **Definition of done:** Source 3 block no longer exists in `_inject_ev_from_odds()`. `_convert_espn_odds_to_decimal()` still present and tested.

- [x] **1.2 [MODIFY] `scripts/odds_evaluator.py` — Remove Phase 6 (dropping odds)**
  - **File:** `scripts/odds_evaluator.py`
  - **What:** Delete the Phase 6 block in `main()` (lines ~600-615) that calls `UnifiedAPIClient().get_dropping_odds(s)` for all 5 sports.
  - **Why:** This calls `OddsPortalClient.get_dropping_odds()` which requires Playwright and returns unreliable data. The `all_dropping_count` metric is always 0 or error.
  - **How:** Remove the Phase 6 try/except block. Remove `all_dropping_count` variable. Remove `dropping_odds_count` from the `out.summary()` metrics dict.
  - **Test impact:** None — no tests cover Phase 6.
  - **Definition of done:** No `UnifiedAPIClient` import or usage in `odds_evaluator.py`. No `dropping_odds_count` in AGENT_SUMMARY output.

- [x] **1.3 [MODIFY] `scripts/odds_evaluator.py` — Update docstring**
  - **File:** `scripts/odds_evaluator.py`
  - **What:** Update the `_inject_ev_from_odds()` docstring to reflect 3 sources (DB, the-odds-api, odds-api-io) instead of 4.
  - **Why:** Docstring currently mentions ESPN DraftKings.
  - **Definition of done:** Docstring accurately lists current sources.

---

### Phase 2: Remove Dead Odds Routing from UnifiedAPIClient

**Goal:** Remove `ODDS_PRIORITY` map and `get_odds()` method that route to broken sources.  
**Risk:** LOW — these never return data.  
**Dependency:** Phase 1.2 (evaluator no longer imports UnifiedAPIClient).

- [x] **2.1 [MODIFY] `src/bet/api_clients/unified.py` — Remove `ODDS_PRIORITY` dict**
  - **File:** `src/bet/api_clients/unified.py`
  - **What:** Delete the `ODDS_PRIORITY` dict (lines ~23-29) that maps all sports to `[oddsportal, betexplorer]`.
  - **Why:** Both sources are broken for odds. Map is misleading.
  - **Definition of done:** `ODDS_PRIORITY` no longer exists in the file.

- [x] **2.2 [MODIFY] `src/bet/api_clients/unified.py` — Remove `get_odds()` method**
  - **File:** `src/bet/api_clients/unified.py`
  - **What:** Delete the `get_odds()` method (~lines 230-245) that uses `ODDS_PRIORITY`.
  - **Why:** Method never returns data because both source clients are broken for odds.
  - **Pre-check:** Verify no callers exist by searching for `\.get_odds\(` across the codebase. Expected: only `unified.py` itself.
  - **Definition of done:** `get_odds()` method no longer exists. No import errors.

- [x] **2.3 [MODIFY] `src/bet/api_clients/unified.py` — Add comment on `get_dropping_odds()`**
  - **File:** `src/bet/api_clients/unified.py`
  - **What:** Add a comment to `get_dropping_odds()` noting it depends on OddsPortal Playwright client and may not return data reliably.
  - **Why:** This method is kept (not removed) but the consumer (evaluator Phase 6) is removed. It may still be useful for manual investigation.
  - **Definition of done:** Method retained with degraded-source comment.

---

### Phase 3: Clean Odds Source Registry

**Goal:** Remove broken sources from the `scripts/odds_sources/` package priority maps.  
**Risk:** LOW — removing entries that produce empty results.  
**Dependency:** None (parallel with Phases 1-2).

- [x] **3.1 [MODIFY] `scripts/odds_sources/__init__.py` — Remove betexplorer/oddsportal from `SPORT_SOURCE_PRIORITY`**
  - **File:** `scripts/odds_sources/__init__.py`
  - **What:** Update `SPORT_SOURCE_PRIORITY` to remove `"oddsportal"` and `"betexplorer"` from all sport lists.
  - **Before:**
    ```python
    SPORT_SOURCE_PRIORITY = {
        "football": ["the-odds-api", "odds-api-io", "api-football-odds", "oddsportal", "betexplorer"],
        "tennis": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
        "basketball": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
        "hockey": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
        "volleyball": ["odds-api-io", "oddsportal", "betexplorer"],
    }
    ```
  - **After:**
    ```python
    SPORT_SOURCE_PRIORITY = {
        "football": ["the-odds-api", "odds-api-io", "api-football-odds"],
        "tennis": ["the-odds-api", "odds-api-io"],
        "basketball": ["the-odds-api", "odds-api-io"],
        "hockey": ["the-odds-api", "odds-api-io"],
        "volleyball": ["odds-api-io"],
    }
    ```
  - **Why:** betexplorer returns empty bookmakers[], oddsportal returns only H2H listing odds. Neither is useful for odds aggregation.
  - **Test impact:** `test_odds_sources.py::TestSupportedSports` may indirectly reference these via `SPORT_SOURCE_PRIORITY`. Verify.
  - **Definition of done:** `SPORT_SOURCE_PRIORITY` has 3 entries max per sport. No `oddsportal` or `betexplorer` strings.

- [x] **3.2 [MODIFY] `scripts/fetch_odds_multi.py` — Remove betexplorer/oddsportal from `_SOURCE_MODULES`**
  - **File:** `scripts/fetch_odds_multi.py`
  - **What:** Remove `"oddsportal"` and `"betexplorer"` entries from the `_SOURCE_MODULES` dict (lines ~53-57).
  - **Before:**
    ```python
    _SOURCE_MODULES = {
        "the-odds-api": ("odds_sources.the_odds_api", "SOURCE"),
        "odds-api-io": ("odds_sources.odds_api_io_source", "SOURCE"),
        "api-football-odds": ("odds_sources.api_football_odds", "SOURCE"),
        "oddsportal": ("odds_sources.oddsportal_source", "SOURCE"),
        "betexplorer": ("odds_sources.betexplorer_source", "SOURCE"),
    }
    ```
  - **After:**
    ```python
    _SOURCE_MODULES = {
        "the-odds-api": ("odds_sources.the_odds_api", "SOURCE"),
        "odds-api-io": ("odds_sources.odds_api_io_source", "SOURCE"),
        "api-football-odds": ("odds_sources.api_football_odds", "SOURCE"),
    }
    ```
  - **Why:** These sources add Playwright overhead and return no useful odds data.
  - **Test impact:** None directly — `fetch_odds_multi.py` has no dedicated test file.
  - **Definition of done:** 3 sources in `_SOURCE_MODULES`. Script runs without importing Playwright dependencies.

- [x] **3.3 [NO DELETE] `scripts/odds_sources/betexplorer_source.py` and `oddsportal_source.py`**
  - **Action:** Do NOT delete these files. They implement the `OddsSource` ABC and are importable modules. While removed from the odds pipeline, they might be used for fixture discovery via `UnifiedAPIClient.SOURCE_PRIORITY`.
  - **Alternative:** If a future cleanup removes them from fixture discovery too, delete then.
  - **Definition of done:** Files exist but are not referenced from `_SOURCE_MODULES` or `SPORT_SOURCE_PRIORITY`.

---

### Phase 4: Activate odds-api.io Pipeline Integration

**Goal:** Make `fetch_odds_api_io.py` a standard pipeline step, fixing the volleyball odds gap.  
**Risk:** MEDIUM — new pipeline step, needs testing with live API.  
**Dependency:** Phase 3 (clean registry).

- [x] **4.1 [MODIFY] `scripts/fetch_odds_api_io.py` — Add AGENT_SUMMARY output (R19)**
  - **File:** `scripts/fetch_odds_api_io.py`
  - **What:** Add `--verbose` flag and `AGENT_SUMMARY:{json}` output using `AgentOutput` from `agent_output.py`, matching the pattern in `fetch_odds_api.py`.
  - **Why:** Pipeline requires AGENT_SUMMARY for all scripts (R19). Currently the script has no structured output.
  - **How:**
    1. Import `from agent_output import AgentOutput, add_agent_args`
    2. Add `add_agent_args(parser)` to the argument parser
    3. Create `out = AgentOutput("s0_odds_api_io", verbose=args.verbose)`
    4. At end of `main()`, call `out.summary(verdict=..., metrics={...})`
    5. Metrics should include: `total_events`, `events_with_odds`, `total_value_bets`, `sports_covered`
  - **Test impact:** None — new functionality.
  - **Definition of done:** Script emits `AGENT_SUMMARY:{json}` when run with `--verbose`. Verdict is `OK` when events found, `PARTIAL` when some sports fail, `FAILED` when no data.

- [x] **4.2 [MODIFY] `scripts/fetch_odds_api_io.py` — Ensure snapshot file is produced**
  - **File:** `scripts/fetch_odds_api_io.py`
  - **What:** Verify that the main scan path saves to `betting/data/odds_api_io_snapshot.json` (not just value bets file). The `fetch_odds_snapshot()` function should already save this — confirm by reading the `api_clients/odds_api_io.py` code.
  - **Why:** Evaluator Source 2 reads `odds_api_io_snapshot.json`. If the file isn't produced, Source 2 is dead.
  - **Pre-check:** Read `api_clients/odds_api_io.py::fetch_odds_snapshot()` to verify it saves the snapshot file.
  - **Definition of done:** Running `fetch_odds_api_io.py --date YYYY-MM-DD` produces `betting/data/odds_api_io_snapshot.json`.

- [x] **4.3 [MODIFY] `scripts/agent_protocol.py` — Add fetch_odds_api_io.py to STRUCTURED_OUTPUT_PROTOCOL**
  - **File:** `scripts/agent_protocol.py`
  - **What:** Add `"fetch_odds_api_io.py"` to the `scripts_with_verbose` list in `STRUCTURED_OUTPUT_PROTOCOL`.
  - **Why:** Pipeline orchestrator checks this list to know which scripts support `--verbose`.
  - **Definition of done:** `"fetch_odds_api_io.py"` appears in `scripts_with_verbose`.

- [x] **4.4 [MODIFY] `scripts/agent_protocol.py` — Update espn_data description**
  - **File:** `scripts/agent_protocol.py`
  - **What:** Update the `espn_data` entry in `SELF_HEALING_REGISTRY` to clarify ESPN is for stats/standings only, not odds. Change description from "Fetch ESPN odds/predictions" to "Fetch ESPN standings, predictions, ATS/OU records".
  - **Why:** Prevent agents from calling `fetch_espn_odds.py` for odds data when it produces none.
  - **Definition of done:** `espn_data` description no longer mentions odds.

---

### Phase 5: Test Updates

**Goal:** Ensure all odds tests pass after changes.  
**Risk:** LOW — most tests mock at client layer.  
**Dependency:** Phases 1-4.

- [x] **5.1 [MODIFY] `tests/test_odds_sources.py` — Update `TestSupportedSports` if needed**
  - **File:** `tests/test_odds_sources.py`
  - **What:** Verify that `test_oddsportal_covers_5_sports` and `test_betexplorer_covers_5_sports` still pass. These test the source wrappers' `.supported_sports()` method, which is unchanged (files not deleted).
  - **Why:** Source files still exist, only removed from registry. Tests should still pass as-is.
  - **Action:** Run tests, fix only if broken.
  - **Definition of done:** All existing `test_odds_sources.py` tests pass.

- [x] **5.2 [MODIFY] `tests/test_odds_sources.py` — Add test for `SPORT_SOURCE_PRIORITY` content**
  - **File:** `tests/test_odds_sources.py`
  - **What:** Add a test verifying `SPORT_SOURCE_PRIORITY` contains only working sources:
    ```python
    def test_sport_source_priority_no_broken_sources():
        """SPORT_SOURCE_PRIORITY should not reference broken odds sources."""
        BROKEN = {"oddsportal", "betexplorer"}
        for sport, sources in SPORT_SOURCE_PRIORITY.items():
            for src in sources:
                assert src not in BROKEN, f"{sport} references broken source {src}"
    ```
  - **Why:** Prevents re-adding broken sources without updating this test.
  - **Definition of done:** New test exists and passes.

- [x] **5.3 [CREATE] `tests/test_fetch_odds_api_io.py` — Basic integration test**
  - **File:** `tests/test_fetch_odds_api_io.py`
  - **What:** Add a test that verifies `fetch_odds_api_io.py` produces AGENT_SUMMARY output and handles missing API key gracefully:
    ```python
    def test_agent_summary_emitted(capsys, monkeypatch):
        """Script should emit AGENT_SUMMARY even when API key is missing."""
        # Mock missing API key → script exits with error
        # Verify it doesn't crash and handles gracefully
    ```
  - **Why:** Validates Phase 4 changes.
  - **Definition of done:** Test exists and passes.

- [x] **5.4 [VERIFY] Run full odds test suite**
  - **Command:** `PYTHONPATH=src .venv/bin/python -m pytest tests/test_odds_evaluator.py tests/test_odds_sources.py -v`
  - **Expected:** All 83+ tests pass (existing + new).
  - **Definition of done:** 0 failures.

---

### Phase 6: Documentation & Configuration Updates

**Goal:** Update all references to removed/changed odds paths.  
**Risk:** LOW.  
**Dependency:** Phases 1-5.

- [x] **6.1 [MODIFY] `betting/sources/source-registry.md` — Update odds source table**
  - **File:** `betting/sources/source-registry.md`
  - **What:** Mark ESPN as "stats/standings only (no odds)". Mark BetExplorer as "fixture discovery only (odds stub)". Mark OddsPortal as "fixture discovery only (H2H listing only)". Add odds-api.io as active odds source.
  - **Definition of done:** Source registry accurately reflects working odds sources.

- [x] **6.2 [MODIFY] `.github/skills/bet-navigating-sources/SKILL.md` — Update odds fetch command**
  - **File:** `.github/skills/bet-navigating-sources/SKILL.md`
  - **What:** Update the `fetch_odds_multi.py` description to reflect 3 sources instead of 4-5. Add `fetch_odds_api_io.py` as volleyball-capable alternative.
  - **Definition of done:** Skill file matches reality.

- [x] **6.3 [MODIFY] `.github/skills/bet-evaluating-odds/SKILL.md` — Update source list**
  - **File:** `.github/skills/bet-evaluating-odds/SKILL.md`
  - **What:** Update odds evaluation skill to reflect 3 evaluator sources (DB, the-odds-api, odds-api-io) instead of 4+.
  - **Definition of done:** Skill file matches reality.

- [x] **6.4 [MODIFY] `.github/prompts/orchestrate-betting-day.prompt.md` — Add odds-api.io step**
  - **File:** `.github/prompts/orchestrate-betting-day.prompt.md`
  - **What:** In the S0 pre-pipeline section, add `fetch_odds_api_io.py` as a standard step alongside `fetch_odds_api.py`. Or reference `fetch_odds_multi.py` which now calls both.
  - **Definition of done:** Pipeline prompt includes odds-api.io in the workflow.

- [x] **6.5 [MODIFY] `.github/agents/bet-valuator.agent.md` — Update receives-from**
  - **File:** `.github/agents/bet-valuator.agent.md`
  - **What:** Update the "Receives output from" line to say "3-source odds aggregation" instead of "5-source".
  - **Definition of done:** Agent description matches reality.

---

## 5. Files Changed Summary

| File | Phase | Action | What Changes |
|------|-------|--------|-------------|
| `scripts/odds_evaluator.py` | 1 | MODIFY | Remove Source 3 (ESPN), Phase 6 (dropping odds), update docstring |
| `src/bet/api_clients/unified.py` | 2 | MODIFY | Remove `ODDS_PRIORITY`, `get_odds()`, comment `get_dropping_odds()` |
| `scripts/odds_sources/__init__.py` | 3 | MODIFY | Remove oddsportal/betexplorer from `SPORT_SOURCE_PRIORITY` |
| `scripts/fetch_odds_multi.py` | 3 | MODIFY | Remove oddsportal/betexplorer from `_SOURCE_MODULES` |
| `scripts/fetch_odds_api_io.py` | 4 | MODIFY | Add AGENT_SUMMARY, verify snapshot output |
| `scripts/agent_protocol.py` | 4 | MODIFY | Add to `scripts_with_verbose`, update espn_data |
| `tests/test_odds_sources.py` | 5 | MODIFY | Add broken-source-guard test |
| `tests/test_fetch_odds_api_io.py` | 5 | CREATE | Basic integration test |
| `betting/sources/source-registry.md` | 6 | MODIFY | Update odds source statuses |
| `.github/skills/bet-navigating-sources/SKILL.md` | 6 | MODIFY | Update source count |
| `.github/skills/bet-evaluating-odds/SKILL.md` | 6 | MODIFY | Update evaluator sources |
| `.github/prompts/orchestrate-betting-day.prompt.md` | 6 | MODIFY | Add odds-api.io step |
| `.github/agents/bet-valuator.agent.md` | 6 | MODIFY | Update source count |

**Files NOT changed (explicitly):**
- `scripts/fetch_espn_odds.py` — kept as-is, just no longer referenced in odds pipeline
- `scripts/parse_betclic_html.py` — no changes (ADR-7)
- `scripts/odds_sources/betexplorer_source.py` — kept, not deleted (ADR-3)
- `scripts/odds_sources/oddsportal_source.py` — kept, not deleted (ADR-3)
- `scripts/fetch_odds_api.py` — no changes needed
- `src/bet/discovery/sources/odds_api.py` — no changes (ADR-4)

---

## 6. Test Plan

### Existing Tests (must continue passing)

| Test File | Count | Risk |
|-----------|-------|------|
| `tests/test_odds_evaluator.py` | ~7 | NONE — tests `_convert_espn_odds_to_decimal` only, not removed |
| `tests/test_odds_sources.py` | ~76 | LOW — source wrapper files not deleted, ABC tests unaffected |

### New Tests

| Test | File | What It Validates |
|------|------|-------------------|
| `test_sport_source_priority_no_broken_sources` | `tests/test_odds_sources.py` | Guard against broken sources in priority map |
| `test_agent_summary_emitted` | `tests/test_fetch_odds_api_io.py` | odds-api.io script produces AGENT_SUMMARY |

### Manual Verification Checklist

After all phases, run these verification commands:

```bash
# 1. Full odds test suite
PYTHONPATH=src .venv/bin/python -m pytest tests/test_odds_evaluator.py tests/test_odds_sources.py tests/test_fetch_odds_api_io.py -v

# 2. No broken imports in evaluator
PYTHONPATH=src .venv/bin/python -c "from scripts.odds_evaluator import run_odds_eval; print('OK')"

# 3. No UnifiedAPIClient import in evaluator
grep -c "UnifiedAPIClient" scripts/odds_evaluator.py  # expected: 0

# 4. ODDS_PRIORITY removed
grep -c "ODDS_PRIORITY" src/bet/api_clients/unified.py  # expected: 0

# 5. fetch_odds_multi.py loads without Playwright
PYTHONPATH=src .venv/bin/python -c "from scripts.fetch_odds_multi import load_configured_sports; print(load_configured_sports())"

# 6. odds-api.io AGENT_SUMMARY
PYTHONPATH=src .venv/bin/python scripts/fetch_odds_api_io.py --date 2026-05-14 --verbose 2>&1 | grep AGENT_SUMMARY

# 7. Full test suite regression check
PYTHONPATH=src .venv/bin/python -m pytest tests/ --ignore=tests/scrapers -v --tb=short
```

---

## 7. Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| R1 | Removing Source 3 breaks EV calculation for some candidates | LOW | LOW | Source 3 (ESPN) always returns empty odds — no EV was ever injected from it |
| R2 | odds-api.io API key missing or invalid | MEDIUM | MEDIUM | Script already handles missing key gracefully (exits with error). Add AGENT_SUMMARY for visibility. Verify key in `config/api_keys.json` before running. |
| R3 | odds-api.io rate limit hit (5000/hr) | LOW | LOW | Pipeline runs ~50-100 requests per scan. Nowhere near 5000/hr. |
| R4 | `get_odds()` removal breaks an unknown caller | LOW | MEDIUM | Pre-check: grep for `.get_odds(` across codebase. Only `unified.py` has the method definition. |
| R5 | Tests referencing `SPORT_SOURCE_PRIORITY` fail after cleanup | LOW | LOW | Source files not deleted — `.supported_sports()` tests unaffected. Only registry tests need updating. |
| R6 | `fetch_odds_multi.py` still produces 0 events after cleanup | MEDIUM | MEDIUM | Root cause was broken sources (oddsportal produced 0, betexplorer produced 0). With 3 working sources, it should produce data. Test with `--dry-run` first. |
| R7 | Betclic HTML parse workflow disrupted | NONE | HIGH | No changes to `parse_betclic_html.py` (ADR-7). |
| R8 | Discovery module breaks due to `ODDS_PRIORITY` removal | NONE | HIGH | Discovery module doesn't use `UnifiedAPIClient.ODDS_PRIORITY` — it uses `OddsAPIAdapter` directly. Verified in codebase. |

---

## 8. Validation Criteria

### Phase 1 Complete When:
- [x] `grep -c "espn_enrichment" scripts/odds_evaluator.py` returns 0
- [x] `grep -c "UnifiedAPIClient" scripts/odds_evaluator.py` returns 0
- [x] `grep -c "dropping_odds" scripts/odds_evaluator.py` returns 0
- [x] `_convert_espn_odds_to_decimal` function still exists in file
- [x] `test_odds_evaluator.py` all pass

### Phase 2 Complete When:
- [x] `grep -c "ODDS_PRIORITY" src/bet/api_clients/unified.py` returns 0
- [x] `grep -c "def get_odds" src/bet/api_clients/unified.py` returns 0
- [x] `get_dropping_odds` still exists (with degraded comment)
- [x] `SOURCE_PRIORITY` and `STATS_PRIORITY` unchanged
- [x] No import errors: `python -c "from bet.api_clients.unified import UnifiedAPIClient"`

### Phase 3 Complete When:
- [x] `"oddsportal"` not in any `SPORT_SOURCE_PRIORITY` value
- [x] `"betexplorer"` not in any `SPORT_SOURCE_PRIORITY` value
- [x] `_SOURCE_MODULES` has exactly 3 entries
- [x] `betexplorer_source.py` and `oddsportal_source.py` files still exist (not deleted)

### Phase 4 Complete When:
- [x] `fetch_odds_api_io.py --verbose` emits `AGENT_SUMMARY:{json}`
- [x] Running the script produces `betting/data/odds_api_io_snapshot.json`
- [x] `"fetch_odds_api_io.py"` in `agent_protocol.py` `scripts_with_verbose`
- [x] `espn_data` description in agent_protocol no longer says "odds"

### Phase 5 Complete When:
- [x] All tests in `test_odds_evaluator.py` pass
- [x] All tests in `test_odds_sources.py` pass
- [x] New `test_fetch_odds_api_io.py` test passes
- [x] New `test_sport_source_priority_no_broken_sources` passes
- [x] Full test suite: 0 new failures

### Phase 6 Complete When:
- [x] `source-registry.md` accurately reflects working odds sources
- [x] Orchestrator prompt includes odds-api.io in workflow
- [x] Skill files updated
- [x] Agent description updated

---

## 9. Credit Budget Impact

| Source | Before | After | Notes |
|--------|--------|-------|-------|
| The Odds API | ~140 credits/run | ~140 credits/run | No change — same sport keys |
| odds-api.io | 0 (not run) | ~50-100 requests/run | Now active. 5000/hr free tier. |
| API-Football | ~10 requests/run | ~10 requests/run | No change |
| ESPN | 0 (free, no data) | 0 (removed from odds) | Kept for stats |
| OddsPortal | ~5 Playwright sessions | 0 | Removed from odds pipeline |
| BetExplorer | ~5 HTTP requests | 0 | Removed from odds pipeline |

**Net:** +50-100 odds-api.io requests (free), -10 broken requests. Credit budget unchanged for The Odds API.

---

## 10. Post-Implementation Fix (2026-05-14 PM)

**DB persistence bug in `fetch_odds_api_io.py`** — discovered during live testing:
- `event.get("sport")` returned a dict `{name, slug}`, not a string → `.lower()` crash
- `event.get("kickoff")` field doesn't exist → actual field is `"date"`
- Both bugs caused **zero** odds-api.io records to persist to DB (JSON snapshot worked fine)
- Fixed to use `_our_sport` and `date` fields. Live-tested: 1048 records persisted to `odds_history`
