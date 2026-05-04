# DB Integration Plan — 10 Core Pipeline Scripts

**Created:** 2026-05-04
**DB:** `betting/data/betting.db` (SQLite, WAL mode, 14 tables)
**Status:** 96,843 odds_history rows, 5,078 team_form, 1,103 teams, 551 fixtures — zero scripts use them.

---

## Current State: Per-Script I/O Map

### 1. `scan_events.py` (S1 — Playwright scan)

| Direction | File | Format |
|-----------|------|--------|
| READ | URLs from `--urls` / `--urls-file` | CLI args / JSON |
| WRITE | `betting/data/scan_summary.json` | `{url: [items]}` |
| WRITE | `betting/data/{domain}/structured_latest.json` | per-domain items |
| WRITE | `betting/data/scan_errors.json` | `[{url, error}]` |
| WRITE | `betting/data/{domain}/*.html` | raw HTML cache |

**DB repos:** SourceHealthRepo (record scan success/failure), FixtureRepo+TeamRepo (persist discovered events).

### 2. `discover_fixtures.py` (S1c — API fixture discovery)

| Direction | File | Format |
|-----------|------|--------|
| READ | API clients (api-football, api-basketball, etc.) | HTTP |
| READ | `betting/data/scan_summary.json` | `{url: [items]}` |
| WRITE | `betting/data/fixtures_{date}.json` | `{date, fixtures: [...], count}` |

**DB repos:** FixtureRepo.upsert, TeamRepo.find_or_create, CompetitionRepo.find_or_create, SportRepo.get_by_name.

### 3. `fetch_api_stats.py` (S4 — API stats enrichment)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/fixtures_{date}.json` | fixtures list |
| WRITE | `betting/data/api_stats_summary_{date}.json` | `{date, counts, results: [...]}` |
| WRITE | `betting/data/stats_cache/{sport}/{slug}.json` | via `build_stats_cache.update_from_api()` |

**DB repos:** FixtureRepo.get_by_date, StatsRepo.save_match_stats, StatsRepo.save_team_form, SourceHealthRepo.

### 4. `deep_analysis_pool.py` (S3a — safety-score pool)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/fixtures_{date}.json` | fixtures list |
| READ | `betting/data/odds_api_snapshot.json` | `{events: [...]}` |
| READ | `betting/data/stats_cache/{sport}/{slug}.json` | team form cache |
| READ | `betting/data/api_stats_summary_{date}.json` | enrichment summary |
| WRITE | `betting/data/analysis_pool_{date}.json` | `{events: [...]}` |
| WRITE | `betting/data/analysis_pool_{date}.md` | markdown report |

**DB repos:** FixtureRepo.get_by_date, OddsRepo, StatsRepo.get_form, StatsRepo.get_h2h_stats.

### 5. `generate_market_matrix.py` (S5 — full market matrix)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/fixtures_{date}.json` | fixtures list |
| READ | `betting/data/odds_api_snapshot.json` | odds events |
| READ | `betting/data/scan_summary.json` | scan items with odds |
| READ | `betting/data/odds_multi_sources.json` | multi-source odds |
| READ | `betting/data/picks_suggested.json` | suggested picks |
| READ | `betting/data/analysis_pool_{date}.json` | analysis pool |
| READ | `betting/data/stats_cache/` | via `build_safety_input_from_cache` |
| WRITE | `betting/data/market_matrix_{date}.json` | `{events: [...]}` |
| WRITE | `betting/data/market_matrix_{date}.md` | markdown matrix |
| WRITE | `betting/data/decision_matrix_{date}.md` | compact markdown |

**DB repos:** FixtureRepo, OddsRepo, StatsRepo.

### 6. `build_shortlist.py` (S2 — ranked shortlist)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/market_matrix_{date}.json` | market matrix |
| READ | `betting/data/odds_api_snapshot.json` | fixture verification |
| READ | `betting/data/fixtures_{date}.json` | fixture verification |
| READ | `betting/data/{date}_s1_tipster_prefetch.md` | tipster coverage |
| WRITE | `betting/data/{date}_s2_shortlist.json` | `{candidates: [...]}` |
| WRITE | `betting/data/{date}_s2_shortlist.md` | markdown |

**DB repos:** FixtureRepo (verification), OddsRepo (verification).

### 7. `deep_stats_report.py` (S3 — per-candidate 10-section analysis)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/analysis_pool_{date}.json` or shortlist JSON | candidates |
| READ | `betting/data/stats_cache/{sport}/{slug}.json` | team form/H2H |
| WRITE | `betting/data/{date}_s3_deep_stats.json` | `{analyses: [...]}` |
| WRITE | `betting/data/{date}_s3_deep_stats.md` | markdown report |

**DB repos:** StatsRepo (team_form, match_stats for L10/L5/H2H).

### 8. `gate_checker.py` (S7 — 17-point pick approval)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/{date}_s3_deep_stats.json` | S3 analyses |
| READ | `betting/journal/picks-ledger.csv` | 48h repeat check |
| WRITE | `betting/data/{date}_s7_gate_results.json` | `{gate_results: {approved, extended, rejected}}` |
| WRITE | `betting/data/{date}_s7_gate_results.md` | markdown |

**DB repos:** CouponRepo (48h repeat check from bets table instead of CSV).

### 9. `coupon_builder.py` (S8 — coupon construction)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/data/{date}_s7_gate_results.json` | gate results |
| READ | `config/betting_config.json` | bankroll, limits |
| WRITE | `betting/coupons/{date}.json` | coupons data |
| WRITE | `betting/coupons/{date}.md` | Polish-language coupon doc |

**DB repos:** CouponRepo.create_coupon, CouponRepo.add_bet, FixtureRepo (link bets to fixture IDs).

### 10. `settle_on_finish.py` (S0 — settlement)

| Direction | File | Format |
|-----------|------|--------|
| READ | `betting/journal/picks-ledger.csv` | pending picks |
| READ | `betting/journal/coupons-ledger.csv` | pending coupons |
| READ | `betting/data/odds_api_snapshot.json` | cached scores |
| READ | `betting/data/odds_api_scores.json` | API scores |
| READ | Playwright/Flashscore/Sofascore | live scores |
| WRITE | `betting/journal/picks-ledger.csv` | updated statuses |
| WRITE | `betting/journal/coupons-ledger.csv` | updated statuses |
| WRITE | `settle_log.txt` | log |

**DB repos:** CouponRepo.get_pending, CouponRepo.settle_bet, CouponRepo.settle_coupon, FixtureRepo.update_result.

---

## New Repository Methods Required

### FixtureRepo (3 new methods)

```python
def get_by_date_with_teams(self, date: str, sport_id: int | None = None) -> list[dict]:
    """JOIN fixtures + teams to return dicts with team names, competition name.
    Returns: [{fixture_id, sport, competition, home_team, away_team, kickoff, status, ...}]
    Used by: discover_fixtures, fetch_api_stats, deep_analysis_pool, market_matrix."""

def get_by_teams_and_date(self, home_name: str, away_name: str, date: str, sport_id: int) -> Fixture | None:
    """Resolve fixture by team names + date. Checks canonical name and aliases.
    Used by: settle_on_finish (match CSV event strings to DB fixtures)."""

def bulk_upsert(self, fixtures: list[Fixture]) -> list[int]:
    """Batch upsert multiple fixtures in one transaction.
    Used by: discover_fixtures (hundreds of fixtures per run)."""
```

### StatsRepo (3 new methods)

```python
def get_all_form_for_team(self, team_id: int, sport_id: int) -> list[TeamForm]:
    """All TeamForm rows for a team (all stat_keys, no H2H filter).
    Used by: deep_stats_report (replaces stats_cache/{slug}.json reads)."""

def get_team_form_record(self, team_id: int, stat_key: str, h2h_opponent_id: int | None = None) -> TeamForm | None:
    """Single TeamForm row. Used by: compute_safety_scores, build_safety_input."""

def bulk_save_match_stats(self, rows: list[tuple[int, int, str, float, str]]) -> None:
    """Batch insert/replace match_stats rows: (fixture_id, team_id, stat_key, stat_value, source).
    Used by: fetch_api_stats (thousands of stat rows per run)."""
```

### OddsRepo (2 new methods)

```python
def get_all_for_date(self, date: str) -> dict[int, list[OddsRecord]]:
    """All odds for fixtures on a date, keyed by fixture_id.
    Used by: deep_analysis_pool, market_matrix (replaces odds_api_snapshot.json reads)."""

def get_all_for_fixtures(self, fixture_ids: list[int]) -> dict[int, list[OddsRecord]]:
    """Batch odds lookup for a set of fixture IDs.
    Used by: market_matrix (efficient batch fetch)."""
```

### CouponRepo (3 new methods)

```python
def create_with_bets(self, coupon: Coupon, bets: list[Bet]) -> tuple[int, list[int]]:
    """Atomic coupon + legs creation. Returns (coupon_db_id, [bet_db_ids]).
    Used by: coupon_builder."""

def get_pending_bets_with_details(self, date: str | None = None) -> list[dict]:
    """Pending bets with fixture + team info via JOINs.
    Returns: [{bet_id, coupon_id, event_name, home_team, away_team, market, selection, odds, ...}]
    Used by: settle_on_finish (replaces CSV reads)."""

def get_recent_losses(self, hours: int = 48) -> list[dict]:
    """Bets with status='loss' settled within last N hours.
    Returns: [{team, market, lost_on}] for 48h repeat check.
    Used by: gate_checker (replaces picks-ledger.csv reads)."""
```

---

## Schema Changes

**None required.** The existing 14-table schema covers all data types. The `stats_cache/{slug}.json` files are denormalized views of `team_form` + `match_stats` which the DB already stores.

---

## Migration Strategy

**Dual-write pattern**: Each phase adds DB writes alongside existing JSON writes. JSON reads are replaced with DB reads only after DB writes are proven reliable. This allows rollback to JSON at any point.

```
Phase N:
  1. Add DB write (new code path)
  2. Keep JSON write (existing code)
  3. Replace JSON read → DB read
  4. Tests pass with DB-only reads
  5. Next phase, keep JSON writes as backup artifacts
```

---

## Phase Plan

### Phase 1: Foundation — Fixture & Team Persistence
**Scripts:** `discover_fixtures.py`, `scan_events.py`
**Goal:** All discovered fixtures + teams + competitions persist to DB.

- [x] **1.1** Add new FixtureRepo methods: `get_by_date_with_teams()`, `get_by_teams_and_date()`, `bulk_upsert()`
  - DoD: Methods exist in `repositories.py` with unit tests in `tests/test_db_repositories.py`
- [x] **1.2** Modify `discover_fixtures.py` to DB-write after discovery
  - After building fixtures list, resolve team names → TeamRepo.find_or_create, competition → CompetitionRepo.find_or_create, fixture → FixtureRepo.upsert
  - Add `--db` flag (default on) to enable DB persistence
  - Keep `fixtures_{date}.json` write for backward compatibility
  - DoD: Running `discover_fixtures.py --date 2026-05-05` populates fixtures, teams, competitions tables AND writes JSON
- [x] **1.3** Modify `scan_events.py` to record source health
  - After scanning, call SourceHealthRepo.record_success/failure per domain
  - DoD: `source_health` table has entries after a scan run
- [ ] **1.4** Integration test: run discover → verify DB fixture count matches JSON fixture count
  - DoD: `tests/test_discover_db.py` passes

### Phase 2: Stats Layer — Match Stats & Team Form
**Scripts:** `fetch_api_stats.py`
**Goal:** All fetched stats flow into `match_stats` + `team_form` tables.

- [x] **2.1** Add new StatsRepo methods: `get_all_form_for_team()`, `get_team_form_record()`, `bulk_save_match_stats()`
  - DoD: Methods exist with unit tests in `tests/test_db_repositories.py`
- [x] **2.2** Modify `fetch_api_stats.py` to DB-write
  - In `_store_in_cache()`: after writing to stats_cache JSON, also write to DB via StatsRepo
  - Resolve team names to IDs via TeamRepo (teams must exist from Phase 1)
  - Save each match's stats → `match_stats` table
  - Save computed L10/L5 form → `team_form` table (via build_stats_cache._persist_to_db)
  - Keep stats_cache JSON writes for backward compatibility
  - DoD: After `fetch_api_stats.py --date X`, `match_stats` and `team_form` tables have new rows
- [x] **2.3** Modify `build_stats_cache.py` helper to dual-write
  - `update_from_api()` already calls `_persist_to_db()` which writes TeamForm to DB via StatsRepo
  - DoD: Cache writes produce both JSON files and DB rows
- [ ] **2.4** Integration test: compare DB team_form L10 averages against stats_cache JSON L10 averages
  - DoD: `tests/test_stats_db.py` passes

### Phase 3: Odds Layer — Odds History
**Scripts:** `fetch_odds_api.py`, `fetch_odds_multi.py` (support scripts, not in the 10 but feed data)
**Goal:** All odds data flows into `odds_history` table.

- [x] **3.1** Add new OddsRepo methods: `get_all_for_date()`, `get_all_for_fixtures()`
  - DoD: Methods exist with unit tests in `tests/test_db_repositories.py`
- [x] **3.2** Modify `fetch_odds_api.py` to DB-write
  - After saving `odds_api_snapshot.json`, iterate events and call OddsRepo.save_odds for each bookmaker/market/outcome
  - Resolves fixture by matching team names → FixtureRepo.get_by_teams_and_date; creates fixture+teams if not found
  - DoD: After odds fetch, `odds_history` table has new rows matching JSON snapshot
- [ ] **3.3** Modify `fetch_odds_multi.py` to DB-write (same pattern)
  - DoD: Multi-source odds also in `odds_history`
- [ ] **3.4** Integration test: odds count in DB matches events in JSON
  - DoD: `tests/test_odds_db.py` passes

### Phase 4: Analysis Layer — DB Reads Replace JSON Reads
**Scripts:** `deep_analysis_pool.py`, `generate_market_matrix.py`, `build_shortlist.py`, `deep_stats_report.py`
**Goal:** These scripts read from DB instead of JSON files.

- [ ] **4.1** Modify `deep_analysis_pool.py` to read from DB
  - `load_fixtures()` → `FixtureRepo.get_by_date_with_teams(date)` with JSON fallback
  - `load_odds_snapshot()` → `OddsRepo.get_all_for_date(date)` with JSON fallback
  - Stats: add DB-backed `build_safety_input_from_db(sport, home_team_id, away_team_id)` in `normalize_stats.py`
  - Keep JSON output writes unchanged
  - DoD: Pool generation works with DB data; JSON fallback still works if DB is empty
- [ ] **4.2** Modify `generate_market_matrix.py` to read from DB
  - `load_fixtures()` → FixtureRepo with JSON fallback
  - `load_odds_api_snapshot()` → OddsRepo with JSON fallback
  - DoD: Market matrix generation works with DB data
- [ ] **4.3** Modify `build_shortlist.py` verification to use DB
  - `_load_verification_sources()` → FixtureRepo + OddsRepo
  - DoD: Fixture verification queries DB first
- [ ] **4.4** Modify `deep_stats_report.py` to read stats from DB
  - `extract_team_stats()` → StatsRepo.get_all_form_for_team with stats_cache fallback
  - `extract_h2h_stats()` → StatsRepo.get_h2h_stats with stats_cache fallback
  - DoD: Deep stats report works with DB data
- [ ] **4.5** Create shared `db_data_loader.py` helper module
  - Encapsulates the DB-read-with-JSON-fallback pattern to avoid duplicating fallback logic in every script
  - Functions: `load_fixtures_from_db(date)`, `load_odds_from_db(date)`, `load_team_form_from_db(team_name, sport)`, `load_h2h_from_db(team_a, team_b, sport)`
  - DoD: All Phase 4 scripts import from this module
- [ ] **4.6** Integration test: full pipeline S1→S5 with DB reads
  - DoD: `tests/test_pipeline_db.py` runs S1c → S4 → S5 and verifies market_matrix output matches

### Phase 5: Output Layer — Coupons & Gate to DB
**Scripts:** `gate_checker.py`, `coupon_builder.py`
**Goal:** Gate results and coupons persist to DB.

- [ ] **5.1** Add new CouponRepo methods: `create_with_bets()`, `get_pending_bets_with_details()`, `get_recent_losses()`
  - DoD: Methods exist with unit tests
- [ ] **5.2** Modify `gate_checker.py` to read 48h repeats from DB
  - `load_48h_repeats()` → CouponRepo.get_recent_losses(48) with CSV fallback
  - DoD: Gate checker reads recent losses from `bets` table
- [ ] **5.3** Modify `coupon_builder.py` to persist coupons to DB
  - After `build_coupons()`, iterate core + combo + singles coupons:
    - Create Coupon row → CouponRepo.create_coupon
    - For each leg, resolve fixture_id → FixtureRepo.get_by_teams_and_date, then CouponRepo.add_bet
  - Keep JSON + markdown writes unchanged
  - DoD: After coupon_builder run, `coupons` and `bets` tables have new rows
- [ ] **5.4** Integration test: coupons in DB match JSON output
  - DoD: `tests/test_coupon_db.py` passes

### Phase 6: Settlement — DB-Based Settlement
**Scripts:** `settle_on_finish.py`
**Goal:** Settlement reads/writes coupons+bets from DB, updates fixture results.

- [ ] **6.1** Modify `settle_on_finish.py` to use DB for pending bets
  - `read_csv(LEDGER)` → CouponRepo.get_pending_bets_with_details(date) with CSV fallback
  - On settlement: CouponRepo.settle_bet, CouponRepo.settle_coupon, FixtureRepo.update_result
  - Keep CSV writes for backward compatibility
  - DoD: Settlement updates both DB and CSV
- [ ] **6.2** Modify score sources to update DB
  - When a score is found, call FixtureRepo.update_result(fixture_id, score_home, score_away)
  - DoD: `fixtures` table reflects settled scores
- [ ] **6.3** Integration test: settle a mock pending bet, verify DB state
  - DoD: `tests/test_settle_db.py` passes

### Phase 7: Cleanup & Pipeline Wiring
**Goal:** Pipeline orchestrator uses PipelineRepo; remove JSON-only code paths once proven.

- [ ] **7.1** Modify `pipeline_orchestrator.py` to track steps in DB
  - PipelineRepo.start_step / complete_step / fail_step on each step
  - DoD: `pipeline_runs` table populated during full pipeline run
- [ ] **7.2** Add `--db-only` flag to all scripts
  - When set, skip JSON writes (DB is sole data store)
  - DoD: Full pipeline runs with `--db-only` and produces correct coupon output
- [ ] **7.3** Remove dead JSON fallback code paths
  - Only after `--db-only` is proven stable for ≥ 3 days
  - DoD: All `if not path.exists()` JSON fallbacks removed; scripts raise clear error if DB is empty

---

## Testing Strategy

### Unit Tests (`tests/test_repositories.py`)
- Each new repo method gets ≥2 tests (happy path + edge case)
- Use in-memory SQLite (`":memory:"`) — no disk I/O
- Verify: row counts, field values, upsert idempotency, NULL handling

### Integration Tests (`tests/test_*_db.py`)
- Per-phase integration test file
- Seed DB with realistic fixtures (from `fixtures_YYYY-MM-DD.json`), run script, verify DB state
- Use temporary DB file, cleaned up after test

### Regression Tests
- Run full pipeline on a past date with known outputs, compare JSON artifacts against baseline
- DoD: `tests/test_pipeline_regression.py` — diffs are empty or expected

### Backward Compatibility Contract
- Every script MUST work if DB is empty (JSON fallback)
- Every script MUST work if JSON files are missing (DB read)
- This dual-source behavior is tested in integration tests

---

## Dependency Graph (script data flow)

```
scan_events.py ──→ scan_summary.json ──┐
                                       ├──→ discover_fixtures.py ──→ fixtures table + fixtures_{date}.json
                                       │         │
                                       │         ▼
                                       │    fetch_api_stats.py ──→ match_stats + team_form tables + stats_cache/
                                       │         │
                                       │         ▼
                                       │    deep_analysis_pool.py ──→ analysis_pool_{date}.json
                                       │         │
fetch_odds_api.py ──→ odds_history ────┘         │
                                                  ▼
                                       generate_market_matrix.py ──→ market_matrix_{date}.json
                                                  │
                                                  ▼
                                       build_shortlist.py ──→ {date}_s2_shortlist.json
                                                  │
                                                  ▼
                                       deep_stats_report.py ──→ {date}_s3_deep_stats.json
                                                  │
                                                  ▼
                                       gate_checker.py ──→ {date}_s7_gate_results.json
                                                  │
                                                  ▼
                                       coupon_builder.py ──→ coupons + bets tables + coupons/{date}.json
                                                  │
                                                  ▼
                                       settle_on_finish.py ──→ bets.status, coupons.status, fixtures.score
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Team name mismatch (JSON name ≠ DB canonical) | TeamRepo.resolve() checks aliases via json_each; add missing aliases on first encounter |
| DB locking under parallel enrichment (Phase 2) | WAL mode already enabled; use short transactions; ThreadPoolExecutor shares one connection per thread |
| Stats cache format divergence | Phase 2.4 integration test compares DB vs JSON values |
| Settlement race condition (DB + CSV) | Settle writes DB first, then CSV; CSV is backup, not source of truth after Phase 6 |
| Empty DB on first run | Every reader has JSON fallback until Phase 7.2 |

---

## Estimated Complexity per Phase

| Phase | New Code | Modified Files | Tests |
|-------|----------|---------------|-------|
| 1 (Foundation) | ~120 LOC | repositories.py, discover_fixtures.py, scan_events.py | 6 tests |
| 2 (Stats) | ~80 LOC | repositories.py, fetch_api_stats.py, build_stats_cache.py | 5 tests |
| 3 (Odds) | ~60 LOC | repositories.py, fetch_odds_api.py, fetch_odds_multi.py | 4 tests |
| 4 (Analysis) | ~200 LOC | 4 scripts + new db_data_loader.py | 6 tests |
| 5 (Coupons) | ~100 LOC | repositories.py, gate_checker.py, coupon_builder.py | 5 tests |
| 6 (Settlement) | ~80 LOC | settle_on_finish.py | 3 tests |
| 7 (Cleanup) | ~50 LOC (deletions) | pipeline_orchestrator.py, all scripts | 2 tests |
