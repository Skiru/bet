# Deep Stats API Clients — Improvements Plan

**Created:** 2026-05-07  
**Status:** Planning (for later implementation)  
**Priority:** Medium — data coverage is functional, improvements are quality-of-life

---

## Current State Summary

| Sport | Client | Fixtures | Match Stats | Player Form | Team History | H2H | Rankings |
|-------|--------|----------|-------------|-------------|--------------|-----|----------|
| Darts | `sofascore_darts.py` | ✅ 41/day | ✅ 182 | ✅ 15 players | N/A | ✅ 10 pairs | ❌ |
| Esports/Dota2 | `opendota.py` | ✅ 50 pro | ✅ 93 | N/A | ✅ 10 teams | ✅ 11 pairs | ❌ |
| Table Tennis | `ittf_client.py` | ✅ 2000+/day | ✅ 273 | ✅ 24 players | ✅ (teams) | ❌ | ❌ |
| Snooker | `snooker_org.py` | ❌ 401 | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## Phase 1: Critical Fixes (High Impact, Low Effort)

### 1.1 [MODIFY] Upgrade `seed_deep_stats.py` to seed ALL data types

**Current:** Only seeds fixtures + match stats  
**Target:** Seeds fixtures + match stats + player form + team history + H2H

```
Changes:
- seed_darts(): Add player form loop (top N players from fixtures)
- seed_darts(): Add H2H loop for today's matchup pairs  
- seed_opendota(): Add team_matches for top 10 teams by rating
- seed_opendota(): Add H2H for teams sharing recent fixtures
- seed_table_tennis(): Add player form for individual players from fixtures
- Add --sport flag to seed single sport
- Add --depth flag: "shallow" (fixtures only) vs "deep" (all data types)
- Add rate-limit awareness: pause & resume when 429 hit
```

**Effort:** ~2h  
**Files:** `scripts/seed_deep_stats.py`

### 1.2 [MODIFY] Fix OpenDota rate limiting (429 crash)

**Problem:** `get_h2h()` cascades into many `get_fixture_stats()` calls → hits 60 req/min cap → crashes  
**Fix:** Add exponential backoff on 429 in `_request()` (already in base class but `get_h2h` spawns too many sub-calls)

```
Options:
A) Add OPENDOTA_KEY env var (raises to 1200 req/min) — recommended
B) Add internal request queue with 50ms spacing between calls
C) Make get_h2h() batch-aware: check budget before each sub-fetch
```

**Effort:** ~30min (option A) or ~1h (option C)  
**Files:** `scripts/api_clients/opendota.py`

### 1.3 [MODIFY] Fix ITTF rankings — use working endpoint

**Problem:** `results.ittf.link/api/rankings` doesn't return data  
**Options:**
1. Scrape `https://www.ittf.com/rankings/` with Playwright (most accurate)
2. Use Sofascore category rankings (limited but functional)
3. Use WTT ranking pages via `fetch_with_playwright.py`

**Effort:** ~2h (option 1)  
**Files:** `scripts/api_clients/ittf_client.py`

---

## Phase 2: Coverage Expansion (Medium Impact, Medium Effort)

### 2.1 [CREATE] Add Padel client (`padel_client.py`)

**Source:** Sofascore (same pattern as darts/TT)  
**Data available:** Fixtures, set scores, H2H via team history  
**Sport endpoint:** `/sport/padel/scheduled-events/{date}`

**Effort:** ~2h (clone TT client pattern)  
**Files:** `scripts/api_clients/padel_client.py`, `tests/test_padel_client.py`

### 2.2 [CREATE] Add MMA/Combat client (`mma_client.py`)

**Source candidates:**
- UFC Stats API (undocumented, scraping required)
- Tapology.com (Playwright scraping)
- Sherdog.com (structured data)

**Data available:** Fighter records, fight history, win methods, H2H  
**Challenge:** No single clean API; requires Playwright adapter

**Effort:** ~4h  
**Files:** `scripts/api_clients/mma_client.py`, `tests/test_mma_client.py`

### 2.3 [MODIFY] Snooker API registration

**Blocker:** Requires emailing `webmaster@snooker.org` with app name  
**Action items:**
1. User sends registration email
2. Once approved, set `SNOOKER_ORG_APP_NAME` env var
3. Re-run `seed_deep_stats.py --sport snooker`

**Data available once unblocked:** Fixtures, results, H2H, rankings, player histories, ongoing matches  
**Effort:** ~15min (after registration approved)

### 2.4 [CREATE] Add Speedway client (`speedway_client.py`)

**Source candidates:**
- speedway-gp.com (official, limited API)
- speedwayresults.com (community, scraping)

**Data available:** Heat results, rider averages, track records  
**Effort:** ~3h

---

## Phase 3: Infrastructure & Quality (Lower Priority)

### 3.1 [MODIFY] Add scheduled seeding (cron job)

**Purpose:** Keep cache warm without manual runs  
**Implementation:**
```bash
# crontab entry
0 6 * * * cd /Users/mkoziol/projects/bet && PYTHONPATH=src:. python3 scripts/seed_deep_stats.py --depth deep 2>&1 >> logs/seed.log
```

**Considerations:**
- Respect daily API budgets (sofascore-darts=500, opendota=1000, ittf=300)
- Run at 06:00 Warsaw time (start of betting day)
- Skip already-cached data (TTL-aware)

### 3.2 [MODIFY] Add cache health monitoring

**Purpose:** Alert when cache is stale or missing data for upcoming fixtures  
**Implementation:**
- Script: `scripts/check_cache_health.py`
- Checks: All today's fixtures have player form data cached
- Output: Missing data report + auto-seed for gaps

**Effort:** ~1.5h

### 3.3 [MODIFY] Unify H2H storage format

**Current state:** Darts H2H stored as `{player_slug}.json` in root + Sofascore-based in subdirectories  
**Target:** Single canonical format: `{sport}/h2h/{id1}_vs_{id2}.json`

**Effort:** ~1h  
**Files:** `scripts/api_clients/sofascore_darts.py` (H2H cache key), migration script

### 3.4 [CREATE] Add integration test suite for live API responses

**Purpose:** Validate API response schemas haven't changed (APIs can break without notice)  
**Implementation:**
- `tests/test_api_live_schemas.py` — marks `@pytest.mark.live`
- Fetches 1 real response per client, validates structure
- Run weekly via CI or manual trigger

**Effort:** ~2h

### 3.5 [MODIFY] Add DB integration for deep stats

**Purpose:** Store player form + H2H in SQLite alongside fixtures (currently cache-only)  
**Tables needed:**
```sql
CREATE TABLE player_form (
    player_id TEXT, sport TEXT, match_date TEXT, 
    opponent TEXT, stats_json TEXT, source TEXT,
    PRIMARY KEY (player_id, sport, match_date)
);
CREATE TABLE h2h_records (
    entity1_id TEXT, entity2_id TEXT, sport TEXT,
    match_date TEXT, stats_json TEXT, source TEXT
);
```

**Effort:** ~3h  
**Depends on:** `scripts/db_data_loader.py` patterns

---

## Phase 4: New Data Dimensions (Aspirational)

### 4.1 Player/team rankings for all sports
- Darts: PDC Order of Merit (scrape `pdc.tv/order-of-merit`)
- Dota 2: Use existing team rating from `get_teams()`
- Table Tennis: Fix ITTF endpoint or scrape WTT site
- Snooker: Available via API once registered

### 4.2 Venue/surface data
- Table Tennis: Indoor always (N/A)
- Darts: Venue doesn't affect (N/A)
- Dota 2: Patch version tracking (affects meta)

### 4.3 Form trend analysis (computed)
- Auto-compute L5 vs L10 trend direction per player
- Flag "form improving" / "form declining" in cache
- Used by pipeline for three-way cross-check validation

---

## Dependency Map

```
Phase 1.2 (OpenDota rate limit) ← blocks → Phase 1.1 (full seeder)
Phase 2.3 (Snooker registration) ← blocks → Snooker data seeding
Phase 1.3 (ITTF rankings) ← independent
Phase 3.5 (DB integration) ← depends on → Phase 1.1 (all data types seeded)
```

---

## Estimated Total Effort

| Phase | Effort | Impact |
|-------|--------|--------|
| Phase 1 (Critical Fixes) | ~5h | High — unblocks full pipeline usage |
| Phase 2 (Coverage) | ~10h | Medium — adds 3 new sports |
| Phase 3 (Infrastructure) | ~9h | Medium — reliability & monitoring |
| Phase 4 (New Dimensions) | ~8h | Low — nice-to-have enrichments |

**Recommended next session:** Phase 1.1 + 1.2 (full seeder + rate limit fix)
