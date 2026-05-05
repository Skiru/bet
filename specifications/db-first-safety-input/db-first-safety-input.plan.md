# DB-First Safety Input Pipeline — Implementation Plan

**Date:** 2026-05-05
**Author:** Architect
**Status:** Draft
**Scope:** Enable `rank_markets()` to receive data from SQLite DB instead of only JSON cache files

---

## 1. Solution Architecture

### Problem
`build_safety_input_from_cache()` in `scripts/normalize_stats.py` only reads JSON files from `betting/data/stats_cache/{sport}/{slug}.json`. The DB has 28,352 `team_form` rows and 1,334 teams but is never queried for safety score calculation, causing 0/1,440 candidates to get market rankings.

### Architecture Overview

```
                        ┌─────────────────────────────┐
                        │  analyze_candidate()         │
                        │  (deep_stats_report.py)      │
                        └─────────┬───────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │  build_safety_input()     │  ← NEW wrapper
                    │  (normalize_stats.py)     │
                    └──────┬──────────┬────────┘
                           │          │
                    ┌──────▼──┐  ┌────▼───────────┐
                    │ DB path │  │ JSON cache path │
                    │ (NEW)   │  │ (existing)      │
                    └──────┬──┘  └────┬───────────┘
                           │          │
              ┌────────────▼──────────▼─────────┐
              │  build_safety_score_input()      │  ← existing, unchanged
              │  Returns: {sport, team_a,        │
              │   team_b, competition, markets}  │
              └────────────┬────────────────────┘
                           │
                           ▼
              ┌────────────────────────────┐
              │  rank_markets()            │  ← existing, unchanged
              │  (compute_safety_scores.py)│
              └────────────────────────────┘
```

### Data Flow — DB Path

```
1. TeamRepo.resolve(name, sport_id) → team_id
2. StatsRepo.get_all_form_for_team(team_id, sport_id) → list[TeamForm]
   └─ stat_keys: "corners_home", "corners_away", ...
3. _strip_ha_suffix("corners_home") → ("corners", "home")
4. Two-tier extraction:
   ├─ Tier 1: match_stats has ≥5 rows → build NormalizedMatchStats
   └─ Tier 2: only team_form aggregates → build market dicts directly
5. H2H: team_form WHERE h2h_opponent_id = opponent_id
6. → build_safety_score_input() or direct market dict construction
```

### Stat Key Mapping

| DB `team_form.stat_key` | Bare key | Side | Usage for home team | Usage for away team |
|--------------------------|----------|------|---------------------|---------------------|
| `corners_home`           | `corners` | `home` | ✅ Use l10_avg/l10_values | — |
| `corners_away`           | `corners` | `away` | — | ✅ Use l10_avg/l10_values |
| `fouls_home`             | `fouls`   | `home` | ✅ | — |
| `fouls_away`             | `fouls`   | `away` | — | ✅ |

Rule: For team_a (home team in the fixture), select `{stat}_home` rows.
For team_b (away team in the fixture), select `{stat}_away` rows.

### Synthetic Value Generation

When `l10_values` is empty but `l10_avg` exists (97.4% of rows):

```python
def _synthesize_l10(l10_avg: float, l5_avg: float | None, count: int = 10) -> list[float]:
    """Generate synthetic per-match values from aggregates.

    Strategy: create 10 values centered on l10_avg with small jitter
    derived from the l10/l5 delta. This avoids artificial 100%/0% hit rates.
    """
    if l5_avg is not None and l10_avg > 0:
        # Use L5-L10 difference as proxy for variance
        delta = abs(l5_avg - l10_avg)
        spread = max(delta, l10_avg * 0.1)  # At least 10% spread
    else:
        spread = max(l10_avg * 0.15, 0.5)  # Default 15% spread

    values = []
    for i in range(count):
        # Deterministic spread: alternate above/below avg
        offset = spread * (1 - 2 * (i % 2)) * ((i // 2 + 1) / (count // 2))
        values.append(round(l10_avg + offset, 1))

    # Ensure l5 subset (first 5) averages closer to l5_avg if available
    if l5_avg is not None:
        l5_subset = values[:5]
        current_avg = sum(l5_subset) / 5
        if current_avg > 0:
            adjustment = l5_avg - current_avg
            values[:5] = [round(v + adjustment / 5, 1) for v in l5_subset]

    return values
```

**Known limitation:** Synthetic values produce approximate hit rates. The `source` field will be set to `"db-synthetic"` so downstream consumers can detect this and display appropriate confidence caveats.

---

## 2. Implementation Plan

### Phase 1: Utility Functions [normalize_stats.py]

- [x] **[CREATE] `_strip_ha_suffix(stat_key: str) -> tuple[str, str | None]`**
  - File: `scripts/normalize_stats.py`
  - Strips `_home` / `_away` suffix from DB stat_keys
  - Returns `(bare_key, side)` where side is `"home"`, `"away"`, or `None` (already bare)
  - Examples: `"corners_home"` → `("corners", "home")`, `"corners"` → `("corners", None)`
  - Definition of done: function handles all stat_keys in `SPORT_STAT_KEYS` with and without suffixes; pure function with no side effects

- [x] **[CREATE] `_synthesize_l10(l10_avg: float, l5_avg: float | None, count: int = 10) -> list[float]`**
  - File: `scripts/normalize_stats.py`
  - Generates deterministic synthetic per-match values from aggregate averages
  - Uses L10/L5 delta as variance proxy; minimum 10% spread to avoid degenerate 100%/0% hit rates
  - Definition of done: returns list of `count` floats; `sum(result)/len(result)` ≈ `l10_avg` (within 5%); no random state

- [x] **[CREATE] `PERCENTAGE_STATS` module-level set**
  - File: `scripts/normalize_stats.py`
  - Move the inline `PERCENTAGE_STATS` set (currently duplicated in `deep_stats_report.py:extract_team_stats`) to module level in `normalize_stats.py`
  - Value: `{"possession", "fg_pct", "three_pct", "ft_pct", "first_serve_pct", "faceoff_pct", "attack_pct", "checkout_pct"}`
  - Definition of done: set is defined once at module level; both `build_safety_input_from_db` and `extract_team_stats` reference it

### Phase 2: Core DB Function [normalize_stats.py]

- [x] **[CREATE] `_build_markets_from_db_form(sport, team_a_form, team_b_form, h2h_form, market_definitions) -> list[dict]`**
  - File: `scripts/normalize_stats.py`
  - Internal helper that converts DB `TeamForm` rows into market dicts
  - Logic:
    1. Group `team_form` rows by bare stat_key (strip `_home`/`_away`)
    2. For each market definition, find matching stat_key rows
    3. For team_a (home): use `{stat}_home` row; for team_b (away): use `{stat}_away` row
    4. Extract `l10_values` if populated; otherwise call `_synthesize_l10(l10_avg, l5_avg)`
    5. Extract H2H values from h2h_form rows (already stored with h2h_opponent_id)
    6. Build market dict: `{name, line, team_a_l10, team_b_l10, h2h_values, team_a_l5, team_b_l5, is_combined, source, team_swapped}`
    7. Auto-determine line from L10 averages (same logic as `build_safety_score_input`)
  - Handles percentage stats (no home+away summation)
  - Definition of done: returns list of market dicts in identical format to `build_safety_score_input()` output markets; handles missing stat_keys gracefully (skips market); handles both populated and empty l10_values

- [x] **[CREATE] `build_safety_input_from_db(sport: str, team_a: str, team_b: str, competition: str) -> dict | None`**
  - File: `scripts/normalize_stats.py`
  - Main DB-first function signature:
    ```python
    def build_safety_input_from_db(
        sport: str,
        team_a: str,
        team_b: str,
        competition: str,
    ) -> dict | None:
    ```
  - Logic:
    1. Import DB dependencies: `get_db`, `SportRepo`, `TeamRepo`, `StatsRepo`
    2. Resolve sport → sport_id; team names → team_ids (using `TeamRepo.resolve`)
    3. If team resolution fails → return `None` (caller falls back to JSON)
    4. Fetch team_form rows: `StatsRepo.get_all_form_for_team(team_id, sport_id)` for both teams
    5. Fetch H2H form: query `team_form WHERE team_id = team_a_id AND h2h_opponent_id = team_b_id`
    6. If no form data for either team → return `None`
    7. Call `_build_markets_from_db_form()` to convert form rows → market dicts
    8. If no markets produced → return `None`
    9. Return `{sport, team_a, team_b, competition, markets}` — same format as `build_safety_score_input()` output
  - All DB access wrapped in try/except → returns `None` on any DB error (safe fallback)
  - Prints diagnostic: `[normalize] DB-first: {N} markets built for {team_a} vs {team_b} (M synthetic)`
  - Definition of done: returns dict identical in schema to `build_safety_score_input()` output; returns `None` on any DB failure; does not raise exceptions

### Phase 3: Wrapper Function [normalize_stats.py]

- [x] **[CREATE] `build_safety_input(sport: str, team_a: str, team_b: str, competition: str, cache_dir: Path | None = None) -> dict | None`**
  - File: `scripts/normalize_stats.py`
  - Wrapper with fallback chain:
    ```python
    def build_safety_input(sport, team_a, team_b, competition, cache_dir=None):
        # 1. Try DB first
        result = build_safety_input_from_db(sport, team_a, team_b, competition)
        if result and result.get("markets"):
            return result
        # 2. Fall back to JSON cache
        return build_safety_input_from_cache(sport, team_a, team_b, competition, cache_dir)
    ```
  - Definition of done: tries DB first; falls back to cache on None/empty; preserves `cache_dir` parameter for cache path override; signature is backward-compatible with callers

### Phase 4: Update Callers

- [x] **[MODIFY] `scripts/deep_stats_report.py` — switch to `build_safety_input`**
  - Lines ~26-29: Update import to include `build_safety_input`
    ```python
    # Before:
    from scripts.normalize_stats import build_safety_input_from_cache, SPORT_STAT_KEYS
    # After:
    from scripts.normalize_stats import build_safety_input, build_safety_input_from_cache, SPORT_STAT_KEYS
    ```
  - Line ~628: Replace call site in `analyze_candidate()`
    ```python
    # Before:
    safety_input = build_safety_input_from_cache(sport, home, away, competition)
    # After:
    safety_input = build_safety_input(sport, home, away, competition)
    ```
  - Definition of done: `analyze_candidate()` calls `build_safety_input()` (DB-first wrapper); existing behavior preserved when DB has no data (JSON cache fallback)

- [x] **[MODIFY] `scripts/deep_analysis_pool.py` — switch to `build_safety_input`**
  - Lines ~25-28: Update import
    ```python
    # Before:
    from scripts.normalize_stats import build_safety_input_from_cache
    # After:
    from scripts.normalize_stats import build_safety_input
    ```
  - Line ~146: Replace call site
    ```python
    # Before:
    safety_input = build_safety_input_from_cache(sport, home_team, away_team, competition)
    # After:
    safety_input = build_safety_input(sport, home_team, away_team, competition)
    ```
  - Definition of done: `quick_analyze()` calls `build_safety_input()`; fallback import path updated too

- [x] **[MODIFY] `scripts/generate_market_matrix.py` — switch to `build_safety_input`**
  - Lines ~42-45: Update import
    ```python
    # Before:
    from normalize_stats import build_safety_input_from_cache, SPORT_MARKETS
    # After:
    from normalize_stats import build_safety_input, build_safety_input_from_cache, SPORT_MARKETS
    ```
  - Line ~473: Replace call site
    ```python
    # Before:
    safety_input = build_safety_input_from_cache(sport, home, away, competition)
    # After:
    safety_input = build_safety_input(sport, home, away, competition)
    ```
  - Definition of done: `_enrich_with_safety()` or equivalent calls `build_safety_input()`; `build_safety_input_from_cache` kept as fallback import for graceful degradation

### Phase 5: Tests

- [x] **[CREATE] `tests/test_db_safety_input.py`**
  - File: `tests/test_db_safety_input.py`
  - Test class: `TestStripHaSuffix`
    - `test_strips_home_suffix`: `"corners_home"` → `("corners", "home")`
    - `test_strips_away_suffix`: `"corners_away"` → `("corners", "away")`
    - `test_bare_key_passthrough`: `"corners"` → `("corners", None)`
    - `test_compound_key`: `"shots_on_target_home"` → `("shots_on_target", "home")`
  - Test class: `TestSynthesizeL10`
    - `test_produces_correct_count`: 10 values when count=10
    - `test_average_near_input`: mean of output ≈ l10_avg (within 5%)
    - `test_spread_avoids_degenerate`: not all values identical
    - `test_handles_zero_avg`: l10_avg=0 doesn't crash
    - `test_l5_influence`: first 5 values weighted toward l5_avg when provided
  - Test class: `TestBuildMarketsFromDbForm`
    - `test_combined_market_from_suffixed_keys`: football corners_home + corners_away → Corners Total O/U market
    - `test_team_specific_market`: Team A Corners O/U uses only home team's corners_home
    - `test_percentage_stat_not_summed`: possession uses home-only value
    - `test_skips_market_with_missing_stats`: market skipped when stat_key absent
    - `test_real_l10_values_preferred`: l10_values used over synthetic when populated
    - `test_synthetic_fallback`: l10_values empty → synthetic values generated
  - Test class: `TestBuildSafetyInputFromDb`
    - `test_returns_correct_format`: output has sport, team_a, team_b, competition, markets keys
    - `test_returns_none_on_unknown_team`: team not in DB → None
    - `test_returns_none_on_db_error`: DB connection fails → None (no exception)
    - `test_markets_compatible_with_rank_markets`: output feeds into `rank_markets()` without error
    - Uses in-memory SQLite DB with test data inserted via repos
  - Test class: `TestBuildSafetyInputWrapper`
    - `test_db_result_returned_when_available`: DB returns data → DB result used
    - `test_falls_back_to_cache_when_db_empty`: DB returns None → cache result used
    - `test_falls_back_on_db_exception`: DB raises → cache result used
    - Uses `unittest.mock.patch` on `build_safety_input_from_db`
  - Definition of done: all tests pass; no tests require network or real DB file; tests use in-memory SQLite or mocks; ≥80% branch coverage of new functions

- [ ] **[MODIFY] `tests/test_pipeline_modules.py`**
  - Update the existing mock to patch `build_safety_input` instead of / in addition to `build_safety_input_from_cache`
  - Line ~301: update `patch.object(dsr, "build_safety_input_from_cache", ...)` to also handle new import
  - Definition of done: existing pipeline module tests still pass with the new import structure

### Phase 6: Documentation Updates

- [ ] **[MODIFY] `scripts/pipeline_orchestrator.py` — update S3 step docstring**
  - Update the module docstring or S3 step description to mention DB-first data source
  - No logic changes needed — the orchestrator calls `generate_deep_stats()` which calls `analyze_candidate()` which will now use the new wrapper
  - Definition of done: S3 step description mentions "DB-first with JSON cache fallback"

- [ ] **[MODIFY] `.github/instructions/analysis-methodology.instructions.md`**
  - Add note in §3.0 or relevant section that safety score input now queries DB first
  - Mention synthetic value limitation when `l10_values` is empty
  - Definition of done: methodology docs reference DB-first pipeline; synthetic value caveat documented

---

## 3. Data Format Conversion Details

### Input: DB `team_form` row

```python
TeamForm(
    team_id=42,
    sport_id=1,
    stat_key="corners_home",       # ← suffixed
    l10_values=[],                 # ← usually empty
    l5_values=[],
    l10_avg=5.3,                   # ← aggregate
    l5_avg=5.8,
    h2h_values=[],
    h2h_opponent_id=None,
    trend="UP",
    source="api-football",
)
```

### Output: Market dict (per `build_safety_score_input()` contract)

```python
{
    "name": "Corners Total O/U",
    "line": 9.5,                    # auto-calculated from L10 avgs
    "team_a_l10": [5.8, 4.8, 6.3, 5.3, 4.3, 5.8, 4.8, 6.3, 5.3, 4.3],  # synthetic
    "team_b_l10": [4.5, 3.5, 5.0, 4.0, 3.0, 4.5, 3.5, 5.0, 4.0, 3.0],  # synthetic
    "h2h_values": [],
    "team_a_l5": [5.8, 4.8, 6.3, 5.3, 4.3],
    "team_b_l5": [4.5, 3.5, 5.0, 4.0, 3.0],
    "is_combined": True,
    "source": "db-synthetic",       # ← signals synthetic values
    "team_swapped": False,
}
```

### Conversion Pipeline

```
DB team_form rows
    │
    ▼  _strip_ha_suffix()
Group by bare_key: {"corners": {home: TeamForm, away: TeamForm}, ...}
    │
    ▼  For each SPORT_MARKETS entry
Match stat_a/stat_b to bare keys
    │
    ▼  Extract values
l10_values populated? → use directly (source="db")
l10_values empty?     → _synthesize_l10(l10_avg, l5_avg) (source="db-synthetic")
    │
    ▼  Build market dict
Same schema as build_safety_score_input() output
```

---

## 4. Security Considerations

- **SQL injection:** All DB queries use parameterized `?` placeholders via existing repository classes. No raw string interpolation.
- **Path traversal:** No file paths constructed from user input in the DB path. JSON cache path already uses `_slugify()` which strips special characters.
- **Error handling:** All DB access wrapped in `try/except` with graceful `None` returns — no stack traces or DB details leak to callers.
- **Data integrity:** Synthetic values are clearly marked with `source="db-synthetic"` to prevent them from being mistaken for real per-match data.

---

## 5. Quality Assurance

### Automated Testing Strategy

| Test Category | File | Method |
|---------------|------|--------|
| Unit: suffix stripping | `tests/test_db_safety_input.py` | Parametrized tests for all suffix patterns |
| Unit: synthetic values | `tests/test_db_safety_input.py` | Statistical property assertions (mean, spread) |
| Unit: market building | `tests/test_db_safety_input.py` | In-memory SQLite with test data |
| Integration: full chain | `tests/test_db_safety_input.py` | DB → `build_safety_input_from_db()` → `rank_markets()` |
| Regression: existing cache path | `tests/test_fetch_api_stats.py` | Existing `TestBuildSafetyInputFromCache` tests unchanged |
| Regression: pipeline modules | `tests/test_pipeline_modules.py` | Updated mock targets |

### Verification Criteria

1. **Functional:** Running `python3 scripts/deep_stats_report.py --date 2026-05-05 --top 5` produces non-zero market rankings for candidates that have DB data
2. **Fallback:** Candidates without DB data still get rankings via JSON cache path (no regression)
3. **Format compatibility:** Output of `build_safety_input_from_db()` passes `validate_input()` in `compute_safety_scores.py`
4. **No new dependencies:** Only uses existing DB infrastructure (`bet.db.connection`, `bet.db.repositories`)

---

## 6. File Impact Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/normalize_stats.py` | MODIFY | Add `_strip_ha_suffix`, `_synthesize_l10`, `PERCENTAGE_STATS`, `_build_markets_from_db_form`, `build_safety_input_from_db`, `build_safety_input` |
| `scripts/deep_stats_report.py` | MODIFY | Import + call site change (2 lines) |
| `scripts/deep_analysis_pool.py` | MODIFY | Import + call site change (2 lines) |
| `scripts/generate_market_matrix.py` | MODIFY | Import + call site change (2 lines) |
| `scripts/pipeline_orchestrator.py` | MODIFY | Docstring update only |
| `tests/test_db_safety_input.py` | CREATE | New test file (~200 lines) |
| `tests/test_pipeline_modules.py` | MODIFY | Update mock target (1 line) |
| `.github/instructions/analysis-methodology.instructions.md` | MODIFY | Add DB-first note |

**No schema changes required.** Existing DB tables are sufficient.
**No new Python dependencies.** All imports are from existing project modules.
