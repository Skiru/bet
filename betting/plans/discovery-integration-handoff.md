# Discovery Module Integration Handoff

> **Created:** 2026-05-14 | **Status:** Ready for integration | **Live-tested:** Yes (1734 events, 3 sources, 29s)

## 1. What Was Built

A complete replacement for `scripts/scan_events.py` event discovery, moving from web scraping (Playwright/Flashscore/BetExplorer) to **API-first discovery** using 3 structured sources.

### New Module: `src/bet/discovery/`

| File | Purpose | Key API |
|------|---------|---------|
| `__init__.py` | Public entry point | `discover_events(date, sports, verbose, db_path) → DiscoveryResult` |
| `models.py` | Pydantic v2 schemas + SA ORM model | `DiscoveredEvent`, `MergedFixture`, `DiscoveryResult`, `FixtureSourceModel` |
| `repository.py` | SQLAlchemy ORM repo for `fixture_sources` | `FixtureSourceRepo.upsert()`, `.bulk_upsert()`, `.get_by_fixture()` |
| `dedup.py` | Cross-source deduplication | `DeduplicationEngine.merge(events_by_source) → list[MergedFixture]` |
| `coordinator.py` | Orchestrates fetch→dedup→persist→JSON | `EventDiscoveryCoordinator.discover(date, sports, verbose) → DiscoveryResult` |
| `sources/__init__.py` | `SourceAdapter` Protocol (runtime_checkable) | `fetch_events(date, sport) → list[DiscoveredEvent]` |
| `sources/base.py` | Abstract base with error handling + timing | `AbstractSourceAdapter` |
| `sources/sofascore.py` | SofaScore Daily Schedule API | All 5 sports, 1500+ events |
| `sources/odds_api.py` | The Odds API | Football (10 leagues) + auto-discovered tennis/hockey |
| `sources/api_football.py` | API-Football | Football only, 249 events |

### New CLI Script: `scripts/discover_events.py`

```bash
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date 2026-05-14 --verbose
```

- Flags: `--date`, `--sports` (comma-separated), `--verbose`, `--stats-first`, `--db-path`
- Emits `AGENT_SUMMARY:{json}` (R19 compliant)
- Exit codes: 0=OK, 1=PARTIAL (some sources failed), 2=FAILED (no events)

### Other New/Modified Files

| File | Change |
|------|--------|
| `src/bet/utils.py` | **NEW** — `normalize_team_name()` relocated from `scripts/utils.py` (single source of truth) |
| `scripts/utils.py` | **MODIFIED** — now re-exports from `bet.utils` instead of defining locally |
| `src/bet/db/schema.sql` | **MODIFIED** — added `fixture_sources` table (schema v8) |
| `src/bet/db/schema.py` | **MODIFIED** — v8 migration with CREATE TABLE + backfill |
| `src/bet/db/models.py` | **MODIFIED** — added `FixtureSource` dataclass |
| `pyproject.toml` | **MODIFIED** — added `rapidfuzz>=3.0.0` |

### Test Coverage: 32 tests

| File | Tests | Coverage |
|------|-------|----------|
| `tests/discovery/test_repository.py` | 5 | SA session, upsert, conflict resolution, FK constraint |
| `tests/discovery/test_dedup.py` | 11 | Exact match, fuzzy (FC suffix, Kyiv/Kiev), temporal window, 3-source merge |
| `tests/discovery/test_sources.py` | 11 | Per-adapter with mocked HTTP/clients |
| `tests/discovery/test_coordinator.py` | 5 | Full pipeline, multi-source merge, partial/total failure, JSON output |

---

## 2. Live Test Results (2026-05-14)

```
Verdict:           OK
Total discovered:  1807
After dedup:       1734  (73 duplicates merged)
Duration:          29 seconds

Sources:
  [✓] sofascore:     1541 events, 1.0s  (football, volleyball, basketball, tennis, hockey)
  [✓] api-football:   249 events, 0.3s  (football)
  [✓] odds-api:        17 events, 27.7s (football, tennis, hockey)

By sport:
  football:   412
  tennis:     995
  basketball: 297
  hockey:      22
  volleyball:   8
```

**Compare to old scan_events.py:** The old scanner uses Flashscore API via `UnifiedAPIClient.get_fixtures()` — same SofaScore backend, but without cross-referencing against Odds API and API-Football. The new module provides **source-diversified discovery** with built-in dedup.

---

## 3. Architecture Decisions

### SQLAlchemy Hybrid Pattern
- **New table (`fixture_sources`)**: Full SA ORM via `FixtureSourceModel` registered against `bet.scrapers.engine.Base`
- **Existing tables (`fixtures`, `teams`, `competitions`, `sports`, `scan_results`)**: Raw SQL via `text()` because these tables aren't SA models
- **Rationale**: Avoids rewriting the entire DB layer. `fixture_sources` gets proper ORM. Existing tables stay compatible with legacy `sqlite3` code.

### Dedup Strategy
1. **Exact match**: `{sport}|{normalized_home}|{normalized_away}|{kickoff_date}` — O(1) lookup
2. **Fuzzy fallback**: rapidfuzz `token_sort_ratio` with threshold 85 + ±2h kickoff window
3. **Source priority**: sofascore (canonical names) → odds-api → api-football
4. **Identity tracking**: `id_to_index` dict for O(1) lookups (fixed from O(N²) in code review)

### Savepoint-per-fixture Persistence
Each fixture persists in its own `session.begin_nested()` savepoint. A single FK violation or data error doesn't wipe the entire batch — only that fixture is skipped.

---

## 4. What the Integration Agent Must Do

### Phase A: Wire into Orchestrator (replace scan_events.py)

#### A1. Update `orchestrate-betting-day.prompt.md` — STEP S1

Replace the scan command block (around line 385):

```diff
-# Unified scan via 7 sources (Flashscore, BetExplorer, Soccerway, ESPN + OddsPortal, TotalCorner, Scores24)
-python3 scripts/scan_events.py --date {date} --verbose 2>&1
+# API-first discovery via 3 sources (SofaScore, The Odds API, API-Football)
+PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date {date} --verbose 2>&1
```

**Key differences for the orchestrator:**
- `discover_events.py` is **fast** (~30s vs 10-15 min for scan_events.py)
- No `--parallel-sport` flag needed (concurrency is internal via ThreadPoolExecutor)
- `mode=sync` with `timeout=120000` is fine (was `mode=async` with `timeout=600000`)
- `AGENT_SUMMARY` format is the same (verdict, events, by_sport, sources, issues)

#### A2. Update `orchestrate-betting-day.prompt.md` — script list (line 245)

Replace `scan_events.py` with `discover_events.py` in the "14 analytical scripts" paragraph.

#### A3. Update `orchestrate-betting-day.prompt.md` — S1 review template (lines 395-415)

The bet-scanner delegation template references:
- `betting/data/global_events_api.json` — **change to** `betting/data/{date}_s1_events.json`
- "7 sources (Flashscore, BetExplorer...)" — **change to** "3 sources (SofaScore, Odds API, API-Football)"
- Deep data checks (H2H, form, injuries) — **remove** from S1 review (discovery doesn't fetch deep data; that's enrichment's job)

#### A4. Update `copilot-instructions.md` — Scripted Workflow section

Replace `scan_events.py` reference with `discover_events.py` in the pipeline step 1 comment block.

#### A5. Update `bet-orchestrator.agent.md` — Script Table (line 312)

```diff
-| scan_events.py | `python3 scripts/scan_events.py --parallel-sport --date YYYY-MM-DD --verbose` | 600000 | async |
+| discover_events.py | `PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date YYYY-MM-DD --verbose` | 120000 | sync |
```

Also update the list at line 79 that mentions `scan_events.py`.

#### A6. Update `agent_protocol.py`

- `STEP_AGENT_CONFIG` for S1: update script reference
- `SELF_HEALING_REGISTRY`: update scan-related entries
- `STRUCTURED_OUTPUT_PROTOCOL`: `scan_events.py` → `discover_events.py`
- `CLI_FLAGS`: remove `--parallel-sport`, `--deep-workers`, `--deep-limit` (scan_events-specific)

#### A7. Update `bet-scanner.agent.md`

Change the description from "Flashscore + ESPN scan" to "API-first discovery via SofaScore + Odds API + API-Football". Update the inline gates table — "7 sources" references are now "3 sources".

#### A8. Update `bet-scan.prompt.md` (internal prompt)

The S1 scan review prompt references source names and data format specific to the old scanner. Update to reference:
- New sources: sofascore, odds-api, api-football
- New output: `{date}_s1_events.json` (not `global_events_api.json`)
- No deep data at S1 (removed from scan, lives in enrichment only)

### Phase B: Downstream Compatibility Verification

These scripts should work **without changes** because the new module writes to the same DB tables (`fixtures`, `teams`, `competitions`, `scan_results`) with the same schema:

| Script | Reads from | Should work? |
|--------|-----------|--------------|
| `build_shortlist.py` | DB fixtures + scan_results | ✅ Same tables, same columns |
| `ingest_scan_stats.py` | DB scan_results | ✅ Same table — but verify it handles new source names |
| `data_enrichment_agent.py` | DB fixtures + shortlist JSON | ✅ Same format |
| `deep_stats_report.py` | Shortlist JSON | ✅ Same format |
| `gate_checker.py` | Shortlist JSON | ✅ Same format |
| `coupon_builder.py` | Gate output JSON | ✅ Same format |

**Must verify:**
- `ingest_scan_stats.py` — reads `scan_results.source_domain`. Old values: "flashscore", "betexplorer", etc. New values: "sofascore", "odds-api", "api-football". Check if any hardcoded source name comparisons break.
- `build_shortlist.py` — reads `scan_results` via DB query. Should work but verify the query.
- `inspect_pipeline.py` — the `--step s1` inspection checks. Update expected source names if needed.

### Phase C: Rename Legacy (Keep as Fallback)

```bash
mv scripts/scan_events.py scripts/_legacy_scan_events.py
```

Keep it available but prefixed with `_` so it's clearly deprecated. Don't delete — it's the fallback if the new module has issues in production.

### Phase D: Memory + Docs Updates

| File | Update needed |
|------|--------------|
| `memories/repo/agent-protocol-and-config.md` | Update S1 script reference, timeout, execution mode |
| `memories/repo/pipeline-knowledge-base.md` | Update scan_events references, add discovery module section |
| `.github/memories/repo/project-structure.md` | Update scanning line to reference discovery module |
| `.github/memories/repo/workflow.md` | Update scan command |
| `betting/sources/source-registry.md` | Add SofaScore Daily Schedule, Odds API, API-Football as discovery sources |

---

## 5. What NOT to Change

| Component | Why keep it |
|-----------|-------------|
| `UnifiedAPIClient` | Still needed for **enrichment** (deep data, H2H, form). Only discovery changes. |
| `scripts/scanners/` directory | 11 per-sport scanner groups — still used by `data_enrichment_agent.py` for deep data |
| `scripts/data_enrichment_agent.py` | Reads from DB fixtures (same format). No changes needed. |
| `scripts/deep_stats_report.py` | Reads shortlist JSON (same format). No changes needed. |
| All downstream scripts (S3-S10) | Format-compatible. No changes needed. |
| `scripts/ingest_scan_stats.py` | **Verify** but likely works unchanged (reads scan_results table) |

---

## 6. Known Minor Issues (from code review, not blocking)

| ID | Issue | Priority |
|----|-------|----------|
| mn2 | `FixtureSourceModel.to_dict()` returns `raw_data` as JSON string, not dict | Low — not called by any production code path yet |
| mn3 | Dual representation: `FixtureSourceModel` (SA) + `FixtureSource` (dataclass) for same table | Low — document in both files |
| mn4 | Tennis auto-discovery in Odds API has no cap on active keys | Medium — add `MAX_TENNIS_KEYS = 5` |
| mn5 | Test `test_outside_window_separate` has misleading name (actually tests merge) | Low — rename |
| mn6 | No test for savepoint isolation (one fixture fails, others persist) | Medium — add test |
| mn7 | `bulk_upsert` flushes per record (could batch) | Low — performance acceptable |

---

## 7. File Inventory (for git diff verification)

### New files (all committed to feature branch):
```
src/bet/discovery/__init__.py
src/bet/discovery/models.py
src/bet/discovery/repository.py
src/bet/discovery/dedup.py
src/bet/discovery/coordinator.py
src/bet/discovery/sources/__init__.py
src/bet/discovery/sources/base.py
src/bet/discovery/sources/sofascore.py
src/bet/discovery/sources/odds_api.py
src/bet/discovery/sources/api_football.py
src/bet/utils.py
scripts/discover_events.py
tests/discovery/__init__.py
tests/discovery/test_repository.py
tests/discovery/test_dedup.py
tests/discovery/test_sources.py
tests/discovery/test_coordinator.py
```

### Modified files:
```
scripts/utils.py            (normalize_team_name → re-export from bet.utils)
src/bet/db/schema.sql       (fixture_sources table, schema v8)
src/bet/db/schema.py        (v8 migration)
src/bet/db/models.py        (FixtureSource dataclass)
pyproject.toml              (rapidfuzz>=3.0.0)
```

### Deleted files:
```
src/bet/discovery/engine.py  (dead code — orphaned Base, never imported)
```

---

## 8. Quick Smoke Test Commands

```bash
# Unit tests (32 tests, <1s)
PYTHONPATH=src .venv/bin/python -m pytest tests/discovery/ -v --tb=short

# Live test (hits real APIs, ~30s)
PYTHONPATH=src .venv/bin/python scripts/discover_events.py --date $(date +%Y-%m-%d) --verbose

# Full suite regression (565 tests, ~2min)
PYTHONPATH=src .venv/bin/python -m pytest tests/ --ignore=tests/scrapers --tb=short -q
```
