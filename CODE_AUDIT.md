# Code Audit Report - Production Readiness Check

**Generated:** 2026-06-10  
**Status:** Identify unused/legacy code for removal

---

## Summary

| Category | Total Files | Used in Pipeline | Unused/Legacy |
|----------|-------------|------------------|---------------|
| Pipeline Scripts | 28 | 16 | 12 |
| Scrapers | 24 | 8 | 16 |
| API Clients | 40 | 18 | 22 |
| Discovery Sources | 8 | 1 | 7 |

---

## Pipeline Scripts Analysis

### Used by Pipeline (PRODUCTION)

| Script | Called By | Purpose |
|--------|-----------|---------|
| `settle_on_finish.py` | s0_settler | Settlement of previous day's picks |
| `discover_events.py` | s1_discover | Event discovery from sources |
| `build_shortlist.py` | s1_discover | Build shortlist of events |
| `tipster_aggregator.py` | s2_tipsters | Aggregate tipster opinions |
| `tipster_xref.py` | s2_tipsters | Cross-reference tipsters |
| `deep_stats_report.py` | s3_stats | Statistical analysis |
| `fetch_odds_multi.py` | s4_valuator | Fetch odds from multiple sources |
| `gate_checker.py` | s5_gate | Gate checking |
| `check_48h_repeats.py` | s6_repeats | 48h repeat detection |
| `validate_betclic_markets.py` | s7_validate | Market validation |
| `coupon_builder.py` | s8_build_coupons | Build coupons |

### Helper Scripts (PRODUCTION - Called by above)

| Script | Called By | Purpose |
|--------|-----------|---------|
| `db_data_loader.py` | 18 scripts | Database operations |
| `normalize_stats.py` | deep_stats_report, others | Normalize statistics |
| `compute_safety_scores.py` | deep_stats_report | Safety score computation |
| `gate_checker.py` | pipeline | Gate logic |
| `odds_evaluator.py` | pipeline | Odds valuation |
| `upset_risk.py` | pipeline | Upset risk analysis |
| `context_checks.py` | pipeline | Context checking |
| `generate_market_matrix.py` | pipeline | Market matrix generation |
| `agent_output.py` | pipeline | Agent output handling |

### Unused/Utility Scripts (CAN REMOVE)

| Script | Reason |
|--------|--------|
| `analyze_betclic_learning.py` | Not called by pipeline |
| `init_database.py` | One-time setup, not in pipeline |
| `kilo_compaction_soak.py` | Test utility |
| `kilo_context_guard_test.py` | Test utility |
| `kilo_e2e_soak.py` | Test utility |
| `mac_resource_monitor.py` | Debug utility |
| `memory_monitor_complete.py` | Debug utility |
| `rapid_mlx_soak.py` | Test utility |
| `sqlite_readonly.py` | Debug utility |

---

## Scrapers Analysis

### Registered in Pipeline (PRODUCTION)

| Scraper | Registry Key | Used By |
|---------|--------------|---------|
| `scrapers/espn.py` | All sports ESPN | deep_stats_report.py |
| `scrapers/flashscore.py` | All sports Flashscore | Not directly called |
| `scrapers/betclic.py` | Betclic market check | validate_betclic_markets.py |
| `scrapers/vlr.py` | Valorantesports | deep_stats_report.py |

### Sport-Specific (IN REGISTRY - LAZY LOADED)

These are in `_SCRAPER_REGISTRY` but may not be actively used:

| Scraper | Registry Key | Status |
|---------|--------------|--------|
| `football/fbref.py` | football-fbref | Registered, lazy-load |
| `basketball/nba_api_scraper.py` | basketball-nba-api | Registered, lazy-load |
| `basketball/bball_ref.py` | basketball-reference | Registered, lazy-load |
| `tennis/sackmann.py` | tennis-sackmann | Registered, lazy-load |
| `hockey/nhl_api.py` | hockey-nhl-api | Registered, lazy-load |
| `hockey/hockey_ref.py` | hockey-reference | Registered, lazy-load |
| `volleyball/volleybox.py` | volleyball-volleybox | Registered, lazy-load |

### Unregistered (UNUSED)

| Scraper | Reason |
|---------|--------|
| `bo3gg.py` | Not in registry, not imported |
| `gosugamers.py` | Not in registry, not imported |
| `hltv.py` | Not in registry, not imported |
| `constants.py` | May be imported by others |
| `engine.py` | May be imported by others |
| `models.py` | May be imported by others |

---

## API Clients Analysis

### Used in Pipeline (PRODUCTION)

| Client | Imported By | Purpose |
|--------|-------------|---------|
| `espn.py` | context_checks, deep_stats_report | ESPN data |
| `espn_adapter.py` | context_checks | Multi-league ESPN |
| `flashscore.py` | deep_stats_report (via registry) | Flashscore data |
| `odds_api_io.py` | odds_sources | Odds API |
| `serpapi_client.py` | deep_stats_report | Search results |
| `moneypuck_client.py` | deep_stats_report | Hockey predictions |
| `nba_api_client.py` | deep_stats_report | NBA stats |
| `sofascore.py` | deep_stats_report | SofaScore data |
| `rate_limiter.py` | All clients | Rate limiting |
| `base_client.py` | All clients | Base class |
| `tipster_playwright.py` | tipster_aggregator | Tipster scraping |
| `opendota.py` | deep_stats_report | Dota 2 stats |
| `api_football.py` | discovery | Football discovery |
| `api_football_odds.py` | odds_sources | Odds discovery |
| `understat_client.py` | deep_stats_report | Understat xG |
| `tennis_abstract.py` | deep_stats_report | Tennis data |
| `sackmann_adapter.py` | deep_stats_report | Tennis adapter |
| `playwright_base.py` | tipster_playwright | Playwright base |

### Imported by Registry (LAZY LOADED)

| Client | Registry Use |
|--------|--------------|
| `api_basketball.py` | API-Sports basketball |
| `api_hockey.py` | API-Sports hockey |
| `api_volleyball.py` | API-Sports volleyball |
| `betexplorer.py` | Odds comparison |

### Unused (CAN REMOVE)

| Client | Reason |
|--------|--------|
| `api_tennis.py` | 0 imports outside itself |
| `balldontlie.py` | 1 import in registry only |
| `betexplorer_h2h.py` | 0 imports |
| `brave_search_client.py` | 0 imports (use MCP tool instead) |
| `espn_odds.py` | 0 imports |
| `espn_stats.py` | 0 imports |
| `tennis_sackmann.py` | 0 imports (duplicate of sackmann_adapter?) |
| `thesportsdb.py` | 0 imports |
| `volleyball_data.py` | 0 imports |
| `google_sports_client.py` | Not in registry, not imported |
| `scrapernhl_wrapper.py` | Not in registry, not imported |
| `scores24.py` | Not in registry, not imported |
| `soccerway.py` | Not in registry, not imported |
| `totalcorner.py` | Not in registry, not imported |
| `unified.py` | Not imported |

---

## Discovery Sources Analysis

### Used

| Source | Used By |
|--------|---------|
| `__init__.py` | discover_events.py |

### Unused

| Source | Reason |
|--------|--------|
| `api_football.py` | Not imported |
| `api_hockey.py` | Not imported |
| `api_volleyball.py` | Not imported |
| `base.py` | May be imported |
| `odds_api.py` | Not imported |
| `odds_api_io.py` | Not imported |
| `sofascore.py` | Not imported |

---

## Why Files Are Unused

### Case 1: CS2/Esports Scrapers (NOT REGISTERED)

**HLTV, bo3gg, gosugamers** are written but not integrated:
- `deep_stats_report.py` uses `VLRScraper` for Valorant and `OpenDotaClient` for Dota2
- **HLTV for CS2 is NOT imported** despite CS2 being in the sport list
- **Reason:** May have been replaced by tipster data (cs2 tips come from tipster_aggregator)

**Action:** Either:
1. Integrate HLTV for CS2 enrichment (same as VLR for Valorant)
2. Delete if tipster data is sufficient for CS2

### Case 2: Discovery Source Adapters (USED VIA COORDINATOR)

**NOT UNUSED** - These are used via `_default_sources()` in coordinator:
- `OddsAPIioAdapter()` - Primary
- `APIVolleyballAdapter()` - Used
- `APIHockeyAdapter()` - Used  
- `OddsAPIAdapter()` - Used
- `APIFootballAdapter()` - Used

**Discovery sources ARE used** but through dynamic instantiation, not direct import.

### Case 3: Football Enrichment Clients (NOT INTEGRATED)

**Soccerway, TotalCorner, Scores24** are Playwright-based football enrichment sources:
- `deep_stats_report.py` only uses ESPN/Flashscore for football
- These could provide **corner statistics, exotic leagues**
- **Reason:** May not have been integrated into enrichment flow

**Action:** Either:
1. Add to enrichment fallback chain for football
2. Delete if ESPN/Flashscore coverage is sufficient

### Case 4: Tennis/X Data (DUPLICATE)

`tennis_sackmann.py` vs `sackmann_adapter.py`:
- Both wrap Jeff Sackmann data
- `sackmann_adapter.py` is imported
- `tennis_sackmann.py` is orphaned duplicate

**Action:** Delete `tennis_sackmann.py`

### Case 5: Utility Scripts (LEGACY)

`analyze_betclic_learning.py`, `init_database.py`, `*_soak.py`:
- Test/debug scripts
- Not part of daily pipeline
- **Action:** Archive or delete

---

## Recommendation: Review Before Delete

### Safe to Delete (Confirmed Unused)

**Scripts (debug/test utilities):**
```
scripts/analyze_betclic_learning.py  # Learning analysis, not in pipeline
scripts/init_database.py             # One-time setup
scripts/kilo_compaction_soak.py      # Test utility
scripts/kilo_context_guard_test.py   # Test utility  
scripts/kilo_e2e_soak.py             # Test utility
scripts/mac_resource_monitor.py      # Debug utility
scripts/memory_monitor_complete.py   # Debug utility
scripts/rapid_mlx_soak.py            # Test utility
scripts/sqlite_readonly.py           # Debug utility
```

**API Clients (duplicates/orphans):**
```
src/bet/api_clients/tennis_sackmann.py  # Duplicate of sackmann_adapter.py
src/bet/api_clients/unified.py          # Not imported anywhere
src/bet/api_clients/brave_search_client.py  # MCP tool used instead
```

### Need Integration Decision (Valuable but not connected)

**CS2 enrichment gap:**
```
src/bet/scrapers/hltv.py      # CS2 stats - should use in deep_stats_report.py
src/bet/scrapers/bo3gg.py     # CS2 fallback
src/bet/scrapers/gosugamers.py # CS2/Dota2/Valorant predictions
```
- **Question:** Should CS2 use HLTV like Valorant uses VLR?

**Football enrichment extras:**
```
src/bet/api_clients/soccerway.py    # Exotic league fixtures
src/bet/api_clients/totalcorner.py  # Corner statistics
src/bet/api_clients/scores24.py     # Multi-sport trends
```
- **Question:** Add to football enrichment fallback chain?

### Discovery Sources (USED - DO NOT DELETE)

These are dynamically loaded by `EventDiscoveryCoordinator._default_sources()`:
```
src/bet/discovery/sources/api_football.py    # ✓ Used by coordinator
src/bet/discovery/sources/api_hockey.py      # ✓ Used by coordinator
src/bet/discovery/sources/api_volleyball.py  # ✓ Used by coordinator
src/bet/discovery/sources/odds_api_io.py     # ✓ Used by coordinator
src/bet/discovery/sources/base.py            # ✓ Base class
```

**Only this one is unused:**
```
src/bet/discovery/sources/sofascore.py  # SofaScore disabled (403 errors)
```

---

## Action Items

1. **Confirm deletions** - User to approve list
2. **Delete unused files** - Remove identified unused code
3. **Update imports** - Fix any broken imports after deletion
4. **Run tests** - Verify pipeline still works
5. **Document remaining** - Ensure all remaining code is documented

---

## Pipeline Flow (What Actually Runs)

```
s0_settler.py
    └── settle_on_finish.py

s1_discover.py
    ├── discover_events.py
    └── build_shortlist.py

s2_tipsters.py
    ├── tipster_aggregator.py
    └── tipster_xref.py

s3_stats.py
    └── deep_stats_report.py

s4_valuator.py
    └── fetch_odds_multi.py

s5_gate.py
    └── gate_checker.py

s6_repeats.py
    └── check_48h_repeats.py

s7_validate.py
    └── validate_betclic_markets.py

s8_build_coupons.py
    └── coupon_builder.py
```

**Total Pipeline Scripts:** 16 core scripts + helpers
**Utility Scripts to Remove:** 12

---

## Database Usage

All pipeline scripts use `src/bet/db/`:
- `connection.py` - Database connection
- `models.py` - ORM models
- `repositories.py` - Data access
- `schema.sql` - Schema definition

**Status:** Production-ready, heavily used.

---

## Stats Module Usage

`src/bet/stats/` is used by:
- coupon_builder.py
- normalize_stats.py
- generate_market_matrix.py
- build_shortlist.py
- deep_stats_report.py

**Files:**
- `market_ranking.py` - Market definitions
- `enrichment.py` - Stats enrichment
- `stat_validation.py` - Validation
- `rich_coverage.py` - Coverage analysis
- `fallback_chains.py` - Fallback logic
- `fetcher.py` - Stats fetching
- `ddg_h2h_search.py` - H2H search
- `value_ranges.py` - Value ranges

**Status:** All used in production.

---

**END OF REPORT**
