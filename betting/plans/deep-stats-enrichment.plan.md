# Implementation Plan: Deep Stats Enrichment Fix

**Date:** 2026-05-03  
**Status:** READY FOR IMPLEMENTATION  
**Priority:** CRITICAL — enrichment is 100% broken (0 teams enriched)

---

## Problem Summary

| Bug | Impact | Root Cause |
|-----|--------|-----------|
| `last` param forbidden on free plan | ALL enrichment fails → 0 stats | `get_team_last_fixtures()` uses `last=N` param |
| Stats per fixture = 1 API call | 80 teams × 10 fixtures = 800 calls/day | No budget-aware batching |
| Stats-first fallback produces safety_score=0 | Useless coupons with "?" everywhere | No real data behind candidates |
| No data gate | Events without stats still become coupon picks | Missing validation in builder |

## API Budget (May 3, 2026)

| API | Used | Remaining |
|-----|------|-----------|
| api-football | 57/100 | **43** |
| api-basketball | 21/100 | **79** |
| api-hockey | 21/100 | **79** |
| api-volleyball | 26/100 | **74** |

**Strategy:** Enrich max 3–4 teams per sport × 11 calls each = ~35–44 calls per API. Within budget.

---

## Phase 1: Fix API Client Methods (Bug 1)

### Task 1.1 — `[MODIFY]` `src/bet/api_clients/api_football.py`

**What:** Replace `get_team_last_fixtures()` to use `season=2024` instead of `last` param.

**Changes:**
```python
def get_team_last_fixtures(self, team_id: str, last_n: int = 10) -> list[dict]:
    """GET /fixtures?team={id}&season=2024 → filter to last N finished."""
    if not self._check_api_key():
        return []
    cache_key = f"football/team_fixtures/{team_id}"
    cached = self._check_cache(cache_key, ttl_hours=12)
    if cached:
        return cached.get("fixtures", [])
    try:
        data = self._request(
            "/fixtures",
            params={"team": team_id, "season": "2024"},
        )
        all_fixtures = data.get("response", [])
        # Filter to finished games only
        finished = [
            f for f in all_fixtures
            if f.get("fixture", {}).get("status", {}).get("short") in ("FT", "AET", "PEN")
        ]
        # Sort by date descending → take last_n most recent
        finished.sort(key=lambda f: f["fixture"].get("date", ""), reverse=True)
        result = [{"id": f["fixture"]["id"]} for f in finished[:last_n]]
        self._save_cache(cache_key, {"fixtures": result})
        return result
    except Exception:
        return []
```

**Dependencies:** None  
**Definition of done:** `get_team_last_fixtures("40")` returns 10 fixture IDs from season 2024 without errors. Unit test passes with mocked API response.

---

### Task 1.2 — `[MODIFY]` `src/bet/api_clients/api_basketball.py`

**What:** Same fix — replace `last` param with `season=2024-2025`.

**Changes:** Replace `params={"team": team_id, "last": str(last_n)}` with:
```python
params={"team": team_id, "season": "2024-2025"}
```
Then filter response to finished games (`status.short in ("FT", "AOT")`) and sort by date descending.

**Dependencies:** None  
**Definition of done:** Basketball `get_team_last_fixtures()` returns fixture IDs. Unit test passes.

---

### Task 1.3 — `[MODIFY]` `src/bet/api_clients/api_hockey.py`

**What:** Same fix — replace `last` param with `season=2024`.

**Changes:** Replace `params={"team": team_id, "last": str(last_n)}` with:
```python
params={"team": team_id, "season": "2024"}
```
Filter to finished games, sort descending, take last_n.

**Dependencies:** None  
**Definition of done:** Hockey `get_team_last_fixtures()` returns fixture IDs. Unit test passes.

---

### Task 1.4 — `[MODIFY]` `src/bet/api_clients/api_volleyball.py`

**What:** Same fix — replace `last` param with `season=2024`.

**Changes:** Identical pattern to hockey.

**Dependencies:** None  
**Definition of done:** Volleyball `get_team_last_fixtures()` returns fixture IDs. Unit test passes.

---

## Phase 2: Budget-Aware Enrichment (Bug 2 & 3)

### Task 2.1 — `[MODIFY]` `src/bet/stats/enrichment.py` → `_try_api_fetch()`

**What:** Add per-fixture stats caching to avoid redundant calls. Each `get_fixture_stats()` result should be cached by fixture_id (7 days TTL — finished fixture stats never change).

**Current flow:**
1. `resolve_team_id(name)` → 1 call (cached 7d) ✓
2. `get_team_last_fixtures(id)` → FAILS ✗
3. `get_fixture_stats(id)` × 10 → 10 calls each (no fixture-level cache)

**New flow:**
1. `resolve_team_id(name)` → 1 call (7d cache, most will hit cache)
2. `get_team_last_fixtures(id)` → 1 call (12h cache, uses `season=2024`)
3. For each fixture_id: `get_fixture_stats(id)` → skip if already in DB (`match_stats` table has rows for that fixture_id), else 1 call

**Changes to `_try_api_fetch()`:**
```python
def _try_api_fetch(team, sport: str, stat_keys: list[str], db_conn) -> bool:
    from bet.scanner.discovery import API_SPORTS
    client_name = API_SPORTS.get(sport)
    if not client_name:
        return False

    try:
        from bet.api_clients import get_client
        client = get_client(client_name)
        if not client.is_available():
            return False

        api_team_id = client.resolve_team_id(team.name)
        if not api_team_id:
            return False

        last_fixtures = client.get_team_last_fixtures(api_team_id, last_n=10)
        if not last_fixtures:
            return False

        stats_repo = StatsRepo(db_conn)
        stat_values: dict[str, list[float]] = {k: [] for k in stat_keys}

        for fix_data in last_fixtures:
            fix_id = str(fix_data.get("id", ""))
            if not fix_id:
                continue

            # Check if stats already in DB for this fixture+team
            existing = db_conn.execute(
                "SELECT stat_key, stat_value FROM match_stats "
                "WHERE fixture_id = (SELECT id FROM fixtures WHERE external_id = ?) "
                "AND team_id = ?",
                (fix_id, team.id),
            ).fetchall()

            if existing:
                # Use cached DB data
                for row in existing:
                    if row["stat_key"] in stat_keys:
                        stat_values[row["stat_key"]].append(row["stat_value"])
                continue

            # Fetch from API
            fix_stats = client.get_fixture_stats(fix_id)
            if not fix_stats:
                continue

            for ms in fix_stats:
                for stat_key, sides in ms.stats.items():
                    if stat_key not in stat_keys:
                        continue
                    if team.name.lower() in ms.home_team_name.lower():
                        val = sides.get("home", 0)
                    else:
                        val = sides.get("away", 0)
                    if isinstance(val, (int, float)):
                        stat_values[stat_key].append(float(val))

        # ... (rest unchanged — save form data)
```

**Key optimization:** Before calling `get_fixture_stats()`, check if `match_stats` table already has rows for that fixture. Finished fixture stats are immutable — never re-fetch.

**Dependencies:** Task 1.1–1.4 (fixed `get_team_last_fixtures()`)  
**Definition of done:** Enrichment fetches stats successfully. API call count per team = max 12 (1 resolve + 1 season fixtures + ≤10 fixture stats). Stats appear in `match_stats` table.

---

### Task 2.2 — `[MODIFY]` `src/bet/stats/enrichment.py` → `_try_api_fetch()` add fixture-stats caching in `get_fixture_stats()`

**What:** Add caching to the `get_fixture_stats()` method in each API client. Since finished fixture stats never change, use 7-day cache.

**Changes to `api_football.py` `get_fixture_stats()`:**
```python
def get_fixture_stats(self, fixture_id: str) -> list[APIMatchStats]:
    """GET /fixtures/statistics?fixture={id} → list of APIMatchStats."""
    if not self._check_api_key():
        return []
    
    # Cache finished fixture stats for 7 days (they never change)
    cache_key = f"football/fixture_stats/{fixture_id}"
    cached = self._check_cache(cache_key, ttl_hours=168)
    if cached:
        # Reconstruct from cache
        return [APIMatchStats(**d) for d in cached.get("stats", [])]
    
    try:
        data = self._request("/fixtures/statistics", params={"fixture": fixture_id})
    except Exception as e:
        print(f"[{self.api_name}] Error fetching stats for fixture {fixture_id}: {e}")
        return []
    # ... (parse response as before)
    # After building result:
    from dataclasses import asdict
    self._save_cache(cache_key, {"stats": [asdict(r) for r in result_list]})
    return result_list
```

Same pattern for basketball, hockey, volleyball.

**Dependencies:** None (parallel with Task 2.1)  
**Definition of done:** Second call to `get_fixture_stats("12345")` returns cached data without API call. Cache file exists at `betting/data/stats_cache/football/fixture_stats/12345.json`.

---

### Task 2.3 — `[MODIFY]` `src/bet/pipeline/orchestrator.py` → `_step_enrich()`

**What:** Reduce enrichment scope to only teams appearing in today's TOP fixtures. Max 5 fixtures per sport = ~10 teams × 4 sports = 40 teams max. With caching, most calls will hit cache after first run.

**Current:** Enriches up to 40 fixtures (all teams = 80 team enrichments)  
**New:** Enrich max 4 fixtures per sport (8 teams per sport), prioritized by competition importance.

**Changes:**
```python
# First pass: max 4 per sport (budget-conscious)
for sport_id, fixes in sport_buckets.items():
    priority_fixtures.extend(fixes[:4])
# No second pass — stay within budget
```

**Dependencies:** Task 2.1  
**Definition of done:** Enrichment step processes ≤ 16 fixtures total. API budget not exceeded (each sport uses ≤ 44 calls).

---

## Phase 3: Mandatory Data Gate (Bug 5)

### Task 3.1 — `[MODIFY]` `src/bet/pipeline/orchestrator.py` → `_step_analyze()`

**What:** Remove stats-first fallback. If a fixture has no form data, skip it entirely. Remove `generate_stats_first_candidates` import and usage.

**Changes:**
1. Remove import of `generate_stats_first_candidates`
2. Remove the block:
```python
# Stats-first fallback: if no form data produced candidates,
# generate baseline candidates so the user can manually evaluate
if not candidates and not home_form and not away_form:
    candidates = generate_stats_first_candidates(...)
    stats_first_count += len(candidates)
```
3. Remove `stats_first_count` tracking
4. Keep the `compute_all_markets()` call — it already returns empty list if no form data

**Dependencies:** None  
**Definition of done:** Analyze step only produces candidates with real data. `stats_first` key in step stats always = 0.

---

### Task 3.2 — `[MODIFY]` `src/bet/coupon/builder.py` → `build_coupons()`

**What:** Add minimum data requirements as an early filter.

**Changes — add filter before sorting:**
```python
def build_coupons(candidates, config, max_coupons=5):
    if not candidates:
        return []
    
    # MANDATORY DATA GATE: only candidates with real stats
    candidates = [
        c for c in candidates
        if c.safety_score > 0.0 and c.hit_rate_l10 > 0.0
    ]
    if not candidates:
        return []
    
    # Remove stats-first mode detection (no longer needed)
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (-(c.ev if c.ev is not None else 0), -c.safety_score),
    )
    # ... rest unchanged
```

Also remove the stats-first round-robin block (the `else` branch that interleaves sports) since it's no longer reachable.

**Dependencies:** Task 3.1  
**Definition of done:** `build_coupons()` never produces coupons with safety_score=0 legs. All output coupons have every leg backed by real L10/L5 data.

---

### Task 3.3 — `[MODIFY]` `src/bet/pipeline/orchestrator.py` → `_step_analyze()` filter

**What:** After collecting all candidates, enforce minimum threshold before passing to BUILD step.

**Changes:** Replace the existing filter:
```python
# Old: allows safety_score == 0.0 through
candidates = [
    c for c in candidates
    if c.safety_score >= config.min_safety_score or c.safety_score == 0.0
]
```
With:
```python
# MANDATORY DATA GATE: real stats required
candidates = [
    c for c in candidates
    if c.safety_score >= config.min_safety_score and c.safety_score > 0.0
]
```

**Dependencies:** Task 3.1  
**Definition of done:** `shared_state["candidates"]` only contains candidates with safety_score > 0.

---

## Phase 4: Deep Stats in Shopping List (Bug 4)

### Task 4.1 — `[MODIFY]` `src/bet/coupon/shopping_list.py` → `format_shopping_list()`

**What:** Add a deep stats section per pick showing L10/L5 averages, trend, hit rate breakdown, and recent form.

**Changes — extend the bet rendering loop to include stats detail:**
```python
def format_shopping_list(coupons, config):
    # ... (header unchanged)
    
    for coupon, bets in coupons:
        # ... (coupon header unchanged)
        
        for i, bet in enumerate(bets, 1):
            emoji = SPORT_EMOJI.get(bet.sport, "")
            safety_str = f"{bet.safety_score:.2f}" if bet.safety_score else "?"
            hit_str = f"{bet.hit_rate:.0%}" if bet.hit_rate else "?"
            min_odds_str = f"{bet.min_odds:.2f}" if bet.min_odds else "?"
            
            lines.append(f"{i}. {emoji} {bet.event_name} — {bet.market_pl}")
            lines.append(f"   Min kurs: {min_odds_str} | Bezpieczeństwo: {safety_str} | Trafialność: {hit_str}")
            if bet.navigation_hint:
                lines.append(f"   → Betclic: {bet.navigation_hint}")
            
            # DEEP STATS SECTION (new)
            if bet.stats_detail:
                lines.append(f"   📊 L10 avg: {bet.stats_detail['l10_avg']:.1f} | L5 avg: {bet.stats_detail['l5_avg']:.1f} | Trend: {bet.stats_detail['trend']}")
                lines.append(f"   📊 Hit L10: {bet.stats_detail['hit_l10']}/{bet.stats_detail['total_l10']} | Hit H2H: {bet.stats_detail.get('hit_h2h', '–')} | 3-Way: {'✓' if bet.stats_detail.get('aligned') else '✗'}")
                if bet.stats_detail.get('recent_values'):
                    recent = bet.stats_detail['recent_values'][:5]
                    recent_str = ", ".join(f"{v:.0f}" for v in recent)
                    lines.append(f"   📊 Last 5: [{recent_str}]")
            lines.append("")
```

**Dependencies:** Task 4.2 (Bet model must carry `stats_detail`)  
**Definition of done:** Shopping list markdown shows L10/L5 averages, hit rates, trend arrows, and last 5 values for each pick.

---

### Task 4.2 — `[MODIFY]` `src/bet/db/models.py` → `Bet` dataclass

**What:** Add `stats_detail: dict | None = None` field to `Bet` model for passing enriched stats to shopping list.

**Changes:**
```python
@dataclass
class Bet:
    # ... existing fields ...
    navigation_hint: str = ""
    stats_detail: dict | None = None  # NEW: L10/L5 data for shopping list
```

**Dependencies:** None  
**Definition of done:** `Bet` dataclass accepts `stats_detail` without breaking existing DB operations (field is transient, not persisted).

---

### Task 4.3 — `[MODIFY]` `src/bet/coupon/builder.py` → `_candidate_to_bet()`

**What:** Populate `stats_detail` from the `MarketCandidate` data when creating a `Bet`.

**Changes — find `_candidate_to_bet()` and add:**
```python
def _candidate_to_bet(candidate: MarketCandidate, coupon_id: int) -> Bet:
    # ... existing field mapping ...
    
    # Compute deep stats detail for shopping list
    stats_detail = {
        "l10_avg": round(statistics.mean(candidate.l10_values), 1) if hasattr(candidate, 'l10_values') and candidate.l10_values else None,
        "l5_avg": round(statistics.mean(candidate.l5_values), 1) if hasattr(candidate, 'l5_values') and candidate.l5_values else None,
        "trend": candidate.trend if hasattr(candidate, 'trend') else None,
        "hit_l10": candidate.hit_rate_l10,
        "total_l10": 10,
        "hit_h2h": candidate.hit_rate_h2h,
        "aligned": candidate.three_way_aligned,
        "recent_values": candidate.l10_values[:5] if hasattr(candidate, 'l10_values') and candidate.l10_values else None,
    }
    
    return Bet(
        # ... existing fields ...
        stats_detail=stats_detail,
    )
```

This requires the `MarketCandidate` to carry `l10_values`. See Task 4.4.

**Dependencies:** Task 4.2, Task 4.4  
**Definition of done:** Every `Bet` created from a `MarketCandidate` has a populated `stats_detail` dict.

---

### Task 4.4 — `[MODIFY]` `src/bet/db/models.py` → `MarketCandidate` dataclass

**What:** Add `l10_values`, `l5_values`, and `trend` fields to `MarketCandidate` so they flow through to the shopping list.

**Changes:**
```python
@dataclass
class MarketCandidate:
    # ... existing fields ...
    betclic_hit_rate: float | None
    # NEW fields for deep stats display
    l10_values: list[float] = field(default_factory=list)
    l5_values: list[float] = field(default_factory=list)
    trend: str = ""
```

**Dependencies:** None  
**Definition of done:** `MarketCandidate` carries raw L10/L5 values for downstream use.

---

### Task 4.5 — `[MODIFY]` `src/bet/stats/safety_scores.py` → `compute_all_markets()`

**What:** Pass `combined_l10` and `combined_l5` values through to the `MarketCandidate` result.

**Changes — in the candidate construction block:**
```python
candidate = MarketCandidate(
    # ... existing fields ...
    betclic_hit_rate=None,
    # NEW:
    l10_values=combined_l10[:10],
    l5_values=combined_l5[:5],
    trend=result["trend"],
)
```

**Dependencies:** Task 4.4  
**Definition of done:** Each `MarketCandidate` carries its source L10/L5 data.

---

## Phase 5: Remove Dead Code

### Task 5.1 — `[MODIFY]` `src/bet/stats/safety_scores.py`

**What:** Remove `generate_stats_first_candidates()` function entirely. It's dead code after Task 3.1.

**Dependencies:** Task 3.1  
**Definition of done:** Function removed, no import errors anywhere in project.

---

### Task 5.2 — `[MODIFY]` `src/bet/coupon/shopping_list.py`

**What:** Remove the stats-first mode detection block:
```python
all_zero_safety = all(...)
if all_zero_safety:
    lines.append("> **TRYB STATS-FIRST** ...")
```

**Dependencies:** Task 3.1, 3.2  
**Definition of done:** Shopping list never shows "TRYB STATS-FIRST" banner.

---

### Task 5.3 — `[MODIFY]` `src/bet/coupon/builder.py`

**What:** Remove stats-first round-robin interleaving code (the `else` branch in `build_coupons()`).

**Dependencies:** Task 3.2  
**Definition of done:** Builder always uses EV+safety sorting. No `has_stats` check needed.

---

## Phase 6: Tests

### Task 6.1 — `[CREATE]` `tests/test_api_season_fixtures.py`

**What:** Unit test for each API client's fixed `get_team_last_fixtures()`:
- Mock `_request()` to return season response with 30 fixtures (mix of FT, NS, LIVE)
- Assert only FT/AET/PEN fixtures returned
- Assert sorted by date descending
- Assert max `last_n` items returned
- Assert caching works (second call doesn't hit `_request()`)

**Dependencies:** Phase 1  
**Definition of done:** 4 test functions pass (one per sport API).

---

### Task 6.2 — `[CREATE]` `tests/test_data_gate.py`

**What:** Integration test for the mandatory data gate:
- Create candidates with safety_score=0 → `build_coupons()` returns []
- Create candidates with safety_score=0.65 → returns coupons
- Mixed candidates → only real-data ones used

**Dependencies:** Phase 3  
**Definition of done:** 3 test functions pass.

---

### Task 6.3 — `[CREATE]` `tests/test_enrichment_budget.py`

**What:** Test that enrichment respects budget:
- Mock API client with rate limiter showing 43 remaining
- Feed 20 fixtures → verify max API calls ≤ 43
- Verify DB-cached fixture stats are not re-fetched

**Dependencies:** Phase 2  
**Definition of done:** Budget test passes — enrichment never exceeds remaining daily quota.

---

## Execution Order (Critical Path)

```
Phase 1 (Tasks 1.1–1.4) — Parallel, no deps
    ↓
Phase 2 (Tasks 2.1–2.3) — Sequential, depends on Phase 1
    ↓
Phase 3 (Tasks 3.1–3.3) — Parallel with Phase 2
    ↓
Phase 4 (Tasks 4.2, 4.4 first → 4.5 → 4.3 → 4.1) — After Phase 3
    ↓
Phase 5 (Tasks 5.1–5.3) — After Phases 3+4
    ↓
Phase 6 (Tests) — After all code changes
```

## Expected Outcome

After implementation:
- `python -m bet.pipeline run --date 2026-05-03` enriches ~16 fixtures using ≤44 API calls per sport
- Every coupon pick has: L10 avg, L5 avg, trend, hit rates, recent form values
- No coupon contains a pick with safety_score=0 or missing stats
- Shopping list shows deep statistical justification for each leg
- Total API budget used tonight: ~30–40 calls per API (well within 43–79 remaining)

---

## Security Notes

- Cache key validation already prevents path traversal (existing `_validate_cache_key()`)
- No user input flows into SQL without parameterized queries (existing pattern)
- API keys loaded from `config/api_keys.json` — not hardcoded

## Constraints Respected

- ✅ SQLite single-thread writes (sequential enrichment, no `run_in_executor`)
- ✅ Max 100 calls/day/API on free plan
- ✅ `season` param limited to 2022–2024 on free plan
- ✅ No `last` param usage
- ✅ Max 3 legs/coupon, max 2.00 PLN/coupon
- ✅ Europe/Warsaw timezone
