# Technical Specification: Pipeline Data Flow Fix — Scan → Stats Cache Bridge

**Author:** Architect Agent  
**Date:** 2026-05-05  
**Status:** Ready for Implementation  
**Priority:** CRITICAL  

---

## 1. Solution Architecture

### 1.1 Problem Summary

The pipeline has a data flow gap where rich statistical data collected by Playwright scan adapters (Scores24, Forebet, BetExplorer) is written to `scan_summary.json` but never propagated to `stats_cache/`. Downstream analysis (`deep_analysis_pool.py`, `generate_market_matrix.py`) reads ONLY from `stats_cache/`, which is populated ONLY by API clients. Result: 7+ sports with zero API coverage get zero analysis despite having rich scan data.

**Quantified impact (from today's scan):**
- Scores24 rich entries by sport: volleyball (1), handball (7), darts (15), table_tennis (30), esports (11), basketball (4), football (7), hockey (2), tennis (30)
- ALL of these have H2H match histories + 5-match form per team
- NONE of this data reaches `deep_analysis_pool.py`

### 1.2 Architecture Overview

```
                          scan_summary.json
                                │
                    ┌───────────┴───────────┐
                    │                       │
          discover_fixtures.py     [NEW] ingest_scan_stats.py
          (fixture metadata)        (rich data → stats_cache)
                    │                       │
                    │               ┌───────┴───────┐
                    │               │               │
                    │      score_parsers()    update_from_scan()
                    │      (sport-specific     (build_stats_cache.py)
                    │       transformation)           │
                    │                          ┌──────┴──────┐
                    │                          │             │
                    │                    stats_cache/    SQLite DB
                    │                    {sport}/{team}  (dual-write)
                    │                          │
                    └──────────┬───────────────┘
                               │
                     deep_analysis_pool.py
                     (build_safety_input_from_cache)
                               │
                     generate_market_matrix.py
```

**Data flow rule:** API data always takes priority. Scan data supplements (fills gaps), never overwrites.

### 1.3 Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Where to put score parsers | `ingest_scan_stats.py` | Scan-specific logic, not needed elsewhere |
| Where to put cache mutation | `build_stats_cache.py` (`update_from_scan()`) | All cache mutation in one file, reuse merge/TTL/dual-write |
| Pipeline insertion point | After step 8 (API stats), before step 9 (deep analysis) | API must populate first so scan knows what to skip |
| Merge strategy | API-priority with H2H-always-merge | API data is richer per-match; scan H2H often covers opponents API misses |
| Forebet handling | Phase 2 (scan odds supplement) | Forebet gives probabilities, not per-match stats; different concern |

---

## 2. Implementation Plan

### Phase 1: Score Parser Engine [CREATE `scripts/ingest_scan_stats.py`]

Create the main script that reads `scan_summary.json`, transforms adapter output into `stats_cache` format, and writes to cache.

#### Task 1.1: Create script skeleton with CLI

- [ ] **File:** `scripts/ingest_scan_stats.py`
- [ ] Standard argparse CLI: `--date YYYY-MM-DD` (optional, filters scan entries), `--force` (overwrite even valid API cache), `--dry-run` (report without writing)
- [ ] Read `scan_summary.json` from `betting/data/`
- [ ] Filter to entries that have rich data: `h2h` dict with `matches` list, OR `form_home`/`form_away` with entries
- [ ] Group entries by `(sport, home, away)` tuple for dedup
- [ ] Print summary at end: `"Ingested X teams across Y sports (Z new, W supplemented)"`

**Definition of Done:** Script runs without errors, reads scan_summary.json, and prints summary of discoverable rich entries. Verified by running `python3 scripts/ingest_scan_stats.py --dry-run` and seeing output.

#### Task 1.2: Implement sport-specific score parsers

Each parser converts raw scores from Scores24 adapter format into `stats` dict compatible with `SPORT_STAT_KEYS` in `normalize_stats.py`.

- [ ] `_parse_volleyball_scores(scores: list[int], team1: str, team2: str, our_team: str) -> dict`
  - Input: `[sets_t1, sets_t2, s1_t1, s1_t2, s2_t1, s2_t2, ...]`
  - Output: `{"sets_won": {"home": X, "away": Y}, "total_points": {"home": sum_team, "away": sum_opp}, "points": {"home": sum_team, "away": sum_opp}}`
  - Determine home/away based on whether `our_team` matches `team1` or `team2`
  
- [ ] `_parse_tennis_scores(scores: list[int], ...) -> dict`
  - Input: `[s1_p1, s1_p2, s2_p1, s2_p2, ...]` (games per set, pairs)
  - Output: `{"sets_won": {"home": X, "away": Y}, "total_games": {"home": sum_all, "away": sum_all}, "games_won": {"home": sum_player, "away": sum_opp}}`
  
- [ ] `_parse_football_scores(scores: list[int], ...) -> dict`
  - Input: `[goals_home, goals_away]`
  - Output: `{"goals": {"home": X, "away": Y}}`
  
- [ ] `_parse_basketball_scores(scores: list[int], ...) -> dict`
  - Input: `[total_home, total_away, q1_home, q1_away, ...]`
  - Output: `{"points": {"home": X, "away": Y}}`
  
- [ ] `_parse_handball_scores(scores: list[int], ...) -> dict`
  - Input: `[goals_home, goals_away, h1_home, h1_away]`
  - Output: `{"goals": {"home": X, "away": Y}, "total_goals": {"home": sum, "away": sum}}`

- [ ] `_parse_hockey_scores(scores: list[int], ...) -> dict`
  - Input: `[goals_home, goals_away, p1_home, p1_away, ...]`
  - Output: `{"goals": {"home": X, "away": Y}}`

- [ ] `_parse_table_tennis_scores(scores: list[int], ...) -> dict`
  - Input: `[sets_t1, sets_t2, s1_t1, s1_t2, ...]`
  - Output: `{"sets_won": ..., "total_sets": ..., "total_points": ..., "points_per_set": ...}`

- [ ] `_parse_snooker_scores(scores: list[int], ...) -> dict`
  - Input: `[frames_p1, frames_p2]`
  - Output: `{"frames_won": ..., "total_frames": ...}`

- [ ] `_parse_darts_scores(scores: list[int], ...) -> dict`
  - Input: `[legs_p1, legs_p2, ...]` or `[sets_p1, sets_p2, ...]`
  - Output: `{"legs_won": ..., "total_legs": ...}`

- [ ] `_parse_esports_scores(scores: list[int], ...) -> dict`
  - Input: `[maps_t1, maps_t2, ...]`
  - Output: `{"maps_won": ..., "total_maps": ...}`

- [ ] Dispatcher function: `parse_match_scores(sport: str, scores: list[int], team1: str, team2: str, our_team: str) -> dict`
  - Routes to sport-specific parser
  - Returns empty dict for unrecognized sports (graceful degradation)

**Definition of Done:** Each parser function has at least one unit test verifying correct transformation. `parse_match_scores` routes correctly to all parsers.

#### Task 1.3: Implement form data transformation

- [ ] `_transform_form_to_cache(sport: str, team: str, form_raw: list[dict]) -> dict`
  - Iterates form matches from adapter (e.g., `form_home`)
  - For each match: calls `parse_match_scores()` on `match["scores"]`
  - Builds `l10_matches` format: `[{"date": "...", "opponent": "...", "stats": {...}, "was_away": bool}]`
  - Computes `l10_avg` and `l5_avg` using `_compute_stat_averages()` from `build_stats_cache`
  - Returns `{"l10_matches": [...], "l10_avg": {...}, "l5_avg": {...}}`

**Definition of Done:** Function correctly transforms a list of Scores24 form entries into stats_cache form format. Verified by test.

#### Task 1.4: Implement H2H data transformation

- [ ] `_transform_h2h_to_cache(sport: str, team: str, opponent: str, h2h_raw: dict) -> dict`
  - Takes raw H2H from adapter: `{"home_wins": X, "away_wins": Y, "matches": [...]}`
  - For each match: calls `parse_match_scores()` on `match["scores"]`
  - Builds H2H cache format: `{"opponent-slug": {"last_updated": "...", "matches": [...], "avg": {...}}}`
  - Computes combined averages using `_compute_combined_stat_averages()` from `build_stats_cache`
  - Returns dict keyed by opponent slug

**Definition of Done:** Function correctly transforms Scores24 H2H data into stats_cache h2h format. Verified by test.

#### Task 1.5: Implement main ingestion orchestration

- [ ] Main `ingest_scan_data(date: str | None, force: bool, dry_run: bool) -> dict` function
  - Reads `scan_summary.json`
  - Iterates all URL entries, identifies entries from adapters that produce rich data (currently: `scores24.live`, `forebet.com`)
  - For each rich entry:
    1. Extract `sport`, `home`, `away`, `h2h`, `form_home`, `form_away`
    2. Transform form data for home team → `_transform_form_to_cache(sport, home, form_home)`
    3. Transform form data for away team → `_transform_form_to_cache(sport, away, form_away)`
    4. Transform H2H data → `_transform_h2h_to_cache(sport, home, away, h2h)`
    5. Call `update_from_scan()` for each team (see Phase 2)
  - Collect stats: teams ingested, sports covered, new vs supplemented
  - Return summary dict

**Definition of Done:** Function processes all scan_summary entries and calls update_from_scan for each team with transformed data.

---

### Phase 2: Cache Bridge Function [MODIFY `scripts/build_stats_cache.py`]

#### Task 2.1: Add `update_from_scan()` function

- [ ] **File:** `scripts/build_stats_cache.py`
- [ ] New function signature:
```python
def update_from_scan(
    sport: str,
    team: str,
    form_data: dict | None = None,    # Already transformed: {l10_matches, l10_avg, l5_avg}
    h2h_data: dict | None = None,     # Already transformed: {opp_slug: {matches, avg, last_updated}}
    scan_source: str = "scores24.live",
    force: bool = False,
) -> Path | None:
```
- [ ] **Merge logic:**
  1. Read existing cache via `read_cache(sport, team)`
  2. If existing cache has valid form data (≥5 matches from API source) AND `force=False`: skip form update, keep API form
  3. If no existing form or thin form (<5 matches) or `force=True`: use scan form data
  4. **H2H always merges:** scan H2H is added to existing H2H (existing H2H entries for same opponent are preserved if newer)
  5. Update sources list: append `scan_source` if not already present
  6. Call `update_cache()` to write
  7. Call `_persist_to_db()` for dual-write

- [ ] **Important:** Mark source clearly in the cache entry so downstream can distinguish API vs scan data

**Definition of Done:** Function writes valid cache entries. API data is never overwritten (unless `force=True`). H2H from scan is always added. Sources list shows scan source. Dual-write to DB works.

#### Task 2.2: Add scan-source merge tests

- [ ] Test: empty cache → scan writes form + h2h
- [ ] Test: existing API cache with 10 matches → scan skips form, adds h2h
- [ ] Test: existing API cache with 3 matches → scan overwrites form (thin cache)
- [ ] Test: existing h2h for opponent A + scan h2h for opponent B → both preserved
- [ ] Test: `force=True` overwrites even rich API cache

**Definition of Done:** All 5 merge scenarios pass.

---

### Phase 3: Pipeline Orchestration [MODIFY `scripts/run_full_scan_and_prepare.sh`]

#### Task 3.1: Insert scan ingestion step

- [ ] **File:** `scripts/run_full_scan_and_prepare.sh`
- [ ] Add new step `[8b/14]` between parallel enrichment (step 6-8) and deep analysis pool (step 9):
```bash
echo ""
echo "[8b/14] Ingesting scan statistics into stats cache..."
python3 "${SCRIPT_DIR}/ingest_scan_stats.py" --date "$(date '+%Y-%m-%d')" \
  || echo "[WARNING] Scan stats ingestion failed — continuing"
```
- [ ] Renumber remaining steps accordingly OR keep as 8b to minimize diff
- [ ] Add `ingest_scan_stats` output file to the summary section

**Definition of Done:** Pipeline runs end-to-end with the new step. Deep analysis pool sees scan-enriched cache data for sports that previously had NO_CACHE.

---

### Phase 4: Scan Odds Supplement (Optional Enhancement)

#### Task 4.1: Create scan odds bridge

- [ ] In `ingest_scan_stats.py`, add function to extract odds from scan entries
- [ ] Write to `betting/data/scan_odds_{date}.json` in same format as `odds_api_snapshot.json`
- [ ] Modify `deep_analysis_pool.py` `load_odds_snapshot()` to fall back to scan odds when API odds are missing

**Definition of Done:** Events without API odds but with scan odds show odds in analysis pool.

> **NOTE:** Phase 4 is optional / Phase 2 of the project. Phases 1-3 solve the critical data flow gap.

---

## 3. Test Plan

### 3.1 Unit Tests (`tests/test_ingest_scan_stats.py`)

| Test | Description |
|------|-------------|
| `test_parse_volleyball_scores` | [3,1, 25,17, 19,25, 25,21, 25,21] → correct sets_won, total_points |
| `test_parse_volleyball_scores_three_sets` | 5-set match → correct total_points |
| `test_parse_tennis_scores_two_sets` | [6,3, 7,5] → sets_won {home:2,away:0}, total_games 21 |
| `test_parse_tennis_scores_three_sets` | [6,3, 4,6, 7,5] → sets_won {home:2,away:1} |
| `test_parse_tennis_tiebreak` | [7,6, 6,7, 7,5] → correct handling |
| `test_parse_football_scores` | [2,1] → goals {home:2,away:1} |
| `test_parse_basketball_scores` | [110,105, 28,25, 30,28, 25,27, 27,25] → points |
| `test_parse_handball_scores` | [30,28, 16,14, 14,14] → goals, total_goals |
| `test_parse_table_tennis_scores` | [3,1, 11,8, 11,5, 9,11, 11,7] → sets_won, total_points |
| `test_parse_snooker_scores` | [6,3] → frames_won, total_frames |
| `test_parse_darts_scores` | [7,5] → legs_won, total_legs |
| `test_parse_esports_scores` | [2,1, 16,13, 10,16, 16,14] → maps_won, rounds_won |
| `test_parse_empty_scores` | [] → empty dict (graceful) |
| `test_parse_unknown_sport` | "cricket" → empty dict (graceful) |
| `test_transform_form_to_cache` | 5 volleyball form matches → correct l10_matches format |
| `test_transform_h2h_to_cache` | 4 H2H matches → correct opponent-slug keyed format with averages |
| `test_team_perspective_swap` | our_team is team2 → stats flipped to home perspective |

### 3.2 Unit Tests (`tests/test_build_stats_cache_scan.py`)

| Test | Description |
|------|-------------|
| `test_update_from_scan_empty_cache` | No prior cache → creates full entry |
| `test_update_from_scan_api_priority` | API cache with 10 matches → form untouched, H2H added |
| `test_update_from_scan_thin_cache` | API cache with 3 matches → form replaced by scan |
| `test_update_from_scan_h2h_merge` | Existing H2H for opp A + scan H2H for opp B → both kept |
| `test_update_from_scan_force` | `force=True` → overwrites rich API cache |
| `test_update_from_scan_sources` | Sources list includes both "api-football" and "scores24.live" |

### 3.3 Integration Tests

| Test | Description |
|------|-------------|
| `test_ingest_to_safety_score` | Ingest volleyball scan data → `build_safety_input_from_cache()` returns non-None |
| `test_pipeline_end_to_end` | Mock scan_summary with volleyball match → run ingest → run deep_analysis → verify event has markets |

### 3.4 Manual Verification

Run after implementation:
```bash
# 1. Check cache before
python3 scripts/build_stats_cache.py status

# 2. Run ingestion
python3 scripts/ingest_scan_stats.py --date 2026-05-05

# 3. Check cache after — should show new sport directories
python3 scripts/build_stats_cache.py status

# 4. Verify a specific team
python3 scripts/build_stats_cache.py read --sport volleyball --team "Modena Volley"

# 5. Run deep analysis and check NO_CACHE count decreased
python3 scripts/deep_analysis_pool.py --date 2026-05-05 2>&1 | grep -c NO_CACHE
```

---

## 4. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Path traversal via sport/team names | `validate_sport()` already blocks `/` and `..`; `slugify()` strips special chars |
| Malicious data in scan_summary.json | File is locally generated by our own scan_events.py, not user-uploaded |
| JSON injection | All writes use `json.dumps()` with safe encoding |
| File system exhaustion | Stats cache has TTL-based expiry; scan ingestion processes only today's entries |
| Concurrent writes to cache files | Same pattern as existing `update_from_api()` — last-writer-wins with merge |

No new security attack surface is introduced. All data flows are local filesystem operations on data generated by our own pipeline.

---

## 5. Quality Assurance

### 5.1 Automated Testing Strategy

- All score parsers have deterministic unit tests with known inputs/outputs
- Merge logic has scenario-based tests covering all priority rules  
- Integration test verifies the full chain: scan_summary → ingest → cache → safety_score_input
- Tests use `tmp_path` fixture for isolated cache directories (no interference with production data)

### 5.2 Code Review Checklist

- [ ] All `SPORT_STAT_KEYS` from `normalize_stats.py` are covered by score parsers
- [ ] `update_from_scan()` never overwrites API data without `force=True`
- [ ] H2H merge preserves existing entries for different opponents
- [ ] Sources list correctly tracks data provenance
- [ ] `_persist_to_db()` is called (dual-write pattern maintained)
- [ ] Edge cases handled: empty scores, missing h2h, missing form
- [ ] Pipeline step ordering is correct (after API stats, before deep analysis)
- [ ] No hardcoded paths — all use `Path(__file__).parent.parent` pattern
- [ ] Score parsers handle odd-length score arrays gracefully

### 5.3 Regression Verification

- Existing API-based cache flow is completely unchanged (`update_from_api()` not modified)
- `build_safety_input_from_cache()` in `normalize_stats.py` is unchanged — it already reads the cache format we're writing to
- `deep_analysis_pool.py` is unchanged — it already handles the cache it reads from
- Pipeline steps 1-8 and 9-14 are unchanged; only a new step 8b is inserted

---

## 6. Data Transformation Reference

### 6.1 Scores24 Volleyball Example

**Input** (from scan_summary.json):
```json
{
  "h2h": {
    "matches": [
      {"date": "2026-05-01", "team1": "Trentino Volley", "team2": "Modena Volley",
       "scores": [0, 3, 26, 28, 17, 25, 21, 25]}
    ]
  },
  "form_home": [
    {"date": "2026-05-01", "team1": "Modena Volley", "team2": "Trentino Volley",
     "opponent": "Trentino Volley", "scores": [3, 0, 25, 21, 25, 17, 25, 20], "result": "W"}
  ]
}
```

**Output** (to stats_cache/volleyball/modena-volley.json):
```json
{
  "team": "Modena Volley",
  "sport": "volleyball",
  "slug": "modena-volley",
  "last_updated": "2026-05-05T12:00:00+00:00",
  "form": {
    "l10_matches": [
      {
        "date": "2026-05-01",
        "opponent": "Trentino Volley",
        "stats": {
          "sets_won": {"home": 3, "away": 0},
          "total_points": {"home": 75, "away": 58},
          "points": {"home": 75, "away": 58}
        },
        "was_away": false
      }
    ],
    "l10_avg": {"sets_won_home": 3.0, "total_points_home": 75.0, "points_home": 75.0},
    "l5_avg": {"sets_won_home": 3.0, "total_points_home": 75.0, "points_home": 75.0}
  },
  "h2h": {
    "trentino-volley": {
      "last_updated": "2026-05-05T12:00:00+00:00",
      "matches": [
        {
          "date": "2026-05-01",
          "stats": {
            "sets_won": {"home": 3, "away": 0},
            "total_points": {"home": 79, "away": 53}
          }
        }
      ],
      "avg": {"sets_won_total": 3.0, "total_points_total": 132.0}
    }
  },
  "sources": ["scores24.live"]
}
```

### 6.2 Score Parsing Rules by Sport

| Sport | Scores Format | Extracted Stats |
|-------|--------------|-----------------|
| **Volleyball** | `[sets_t1, sets_t2, s1_t1, s1_t2, ...]` | `sets_won`, `total_points`, `points` |
| **Tennis** | `[s1_p1, s1_p2, s2_p1, s2_p2, ...]` | `sets_won`, `total_games`, `games_won` |
| **Football** | `[goals_h, goals_a]` | `goals` |
| **Basketball** | `[total_h, total_a, q1_h, q1_a, ...]` | `points` |
| **Handball** | `[goals_h, goals_a, h1_h, h1_a]` | `goals`, `total_goals` |
| **Hockey** | `[goals_h, goals_a, p1_h, p1_a, ...]` | `goals` |
| **Table Tennis** | `[sets_t1, sets_t2, s1_t1, s1_t2, ...]` | `sets_won`, `total_sets`, `total_points`, `points_per_set` |
| **Snooker** | `[frames_p1, frames_p2]` | `frames_won`, `total_frames` |
| **Darts** | `[legs_p1, legs_p2]` or `[sets_p1, sets_p2, l1_p1, l1_p2, ...]` | `legs_won`, `total_legs` |
| **Esports** | `[maps_t1, maps_t2, r1_t1, r1_t2, ...]` | `maps_won`, `total_maps`, `rounds_won` (if per-map) |
| **Baseball** | `[runs_h, runs_a, i1_h, i1_a, ...]` | `runs`, `total_runs` |
| **MMA** | `[rounds]` (single value or none) | `rounds` |

### 6.3 Home/Away Perspective Logic

Critical: Scores24 H2H/form uses `team1`/`team2` (position in listing), not home/away. When building cache for "our team":

```python
# Determine if our team is team1 or team2
if our_team.lower() in match["team1"].lower():
    is_team1 = True
elif our_team.lower() in match["team2"].lower():
    is_team1 = False
else:
    # Fuzzy match needed
    ...

# In cache format, "home" = our team's stats, "away" = opponent's stats
# This matches the convention in update_from_api() and _cache_to_normalized_matches()
if is_team1:
    stats = {"key": {"home": t1_value, "away": t2_value}}
else:
    stats = {"key": {"home": t2_value, "away": t1_value}}
```

This aligns with `build_stats_cache.py:update_from_api()` lines 296-319 where `is_away` detection flips home/away stats so "home" always = our team's perspective.

---

## 7. Files Summary

| Action | File | Changes |
|--------|------|---------|
| `[CREATE]` | `scripts/ingest_scan_stats.py` | ~350 lines. Score parsers + form/H2H transformers + CLI orchestrator |
| `[MODIFY]` | `scripts/build_stats_cache.py` | ~60 lines added. New `update_from_scan()` function |
| `[MODIFY]` | `scripts/run_full_scan_and_prepare.sh` | ~5 lines added. New step 8b |
| `[CREATE]` | `tests/test_ingest_scan_stats.py` | ~250 lines. Unit tests for all score parsers + transformers |
| `[CREATE]` | `tests/test_build_stats_cache_scan.py` | ~120 lines. Merge scenario tests for `update_from_scan()` |
| `[MODIFY]` (Phase 4) | `scripts/deep_analysis_pool.py` | ~15 lines. Optional scan odds fallback in `load_odds_snapshot()` |

**Total estimated new code:** ~800 lines (including tests)  
**Existing code modified:** ~65 lines across 2 files  
**Risk:** LOW — no existing functions are modified, only new functions added + pipeline step inserted
